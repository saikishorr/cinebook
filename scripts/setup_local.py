"""Database setup used by the PowerShell entry point; no psql or AWS CLI needed."""
import argparse
import logging
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]


def apply_migrations(connection, fresh=False):
    connection.execute("""CREATE TABLE IF NOT EXISTS schema_migrations
                          (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    for path in sorted((ROOT / "db/migrations").glob("[0-9]*.sql")):
        if path.stem.endswith("_down"):
            continue
        if connection.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (path.stem,)).fetchone():
            continue
        with connection.transaction():
            if not fresh:
                # Migrations include their own BEGIN/COMMIT for manual psql use.
                source = path.read_text(encoding="utf-8").replace("BEGIN;", "").replace("COMMIT;", "")
                connection.execute(source)
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
        print(f"Recorded {path.stem}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    env_path = ROOT / "backend/.env"
    if not env_path.exists():
        raise SystemExit("Create backend/.env from backend/.env.example first.")
    values = dotenv_values(env_path)
    database_url = values.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL in backend/.env first.")
    params = conninfo_to_dict(database_url)
    database = params.get("dbname", "moviebooking")
    admin_params = {**params, "dbname": "postgres"}
    with psycopg.connect(make_conninfo(**admin_params), autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            print(f"Created database {database}")
    with psycopg.connect(database_url, autocommit=True) as connection:
        empty = not connection.execute("""SELECT 1 FROM information_schema.tables
                                          WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                                          AND table_name <> 'schema_migrations' LIMIT 1""").fetchone()
        if args.reset or empty:
            with connection.transaction():
                connection.execute((ROOT / "db/schema.sql").read_text(encoding="utf-8"))
                # schema.sql includes every migration; record them without replaying.
                connection.execute("DELETE FROM schema_migrations")
                apply_migrations(connection, fresh=True)
            print("Installed fresh schema")
        else:
            apply_migrations(connection)
        with connection.transaction():
            connection.execute((ROOT / "db/seed.sql").read_text(encoding="utf-8"))
            connection.execute((ROOT / "db/add_upcoming_shows.sql").read_text(encoding="utf-8"))
            from import_cinemas import import_curated, load_curated
            result = import_curated(connection, load_curated())
            print(f"Created {result['created']} simulated shows at real Pune cinemas")
    worker_env = ROOT / "worker/.env"
    if not worker_env.exists():
        # Copy dotenv syntax unchanged, including quoted passwords; never print values.
        worker_env.write_text(env_path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created worker/.env")
    print("Local database is ready. Run .\\scripts\\run-local.ps1")


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error:
        # Connection exceptions can include passwords in a DSN; keep the message generic.
        logging.error("Database setup failed. Check PostgreSQL is running and DATABASE_URL credentials are correct.")
        raise SystemExit(1) from None
