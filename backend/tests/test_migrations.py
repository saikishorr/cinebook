"""Fresh installation and upgrades agree, without touching the developer's tables."""
import importlib.util
import secrets
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_schema(database_url):
    name = "test_migrations_" + secrets.token_hex(6)
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(name)))
        try:
            yield connection
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def _setup_module():
    spec = importlib.util.spec_from_file_location("local_setup", ROOT / "scripts/setup_local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(connection):
    return connection.execute("""SELECT table_name, column_name, data_type, is_nullable, column_default
                                 FROM information_schema.columns WHERE table_schema = current_schema()
                                 ORDER BY table_name, ordinal_position""").fetchall()


def test_upgrade_matches_fresh_and_preserves_data(isolated_schema):
    conn = isolated_schema
    schema = (ROOT / "db/schema.sql").read_text()
    conn.execute(schema)
    fresh_columns = _columns(conn)
    # Recreate the original 003 schema, then exercise the existing-database upgrade path.
    conn.execute(schema.split("-- 004_seat_holds")[0])
    # The baseline reset deliberately leaves the migration ledger (it contains no data yet).
    conn.execute("INSERT INTO customers (full_name, email) VALUES ('Keep me', 'keep@example.com')")
    setup = _setup_module()
    setup.apply_migrations(conn)
    setup.apply_migrations(conn)
    assert conn.execute("SELECT full_name FROM customers WHERE email = 'keep@example.com'").fetchone() == ("Keep me",)
    assert _columns(conn) == fresh_columns
    expected = len([p for p in (ROOT / "db/migrations").glob("[0-9]*.sql") if not p.stem.endswith("_down")])
    assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == expected


def test_new_migrations_down_then_up(isolated_schema):
    conn = isolated_schema
    conn.execute((ROOT / "db/schema.sql").read_text())
    for name in ("012_admin_sessions", "011_seat_layouts", "010_cinema_source", "009_cinemas", "008_movie_tmdb", "007_schema_migrations", "006_booking_cancellation", "005_movie_details", "004_seat_holds"):
        conn.execute((ROOT / f"db/migrations/{name}_down.sql").read_text())
    assert conn.execute("SELECT to_regclass('seat_holds')").fetchone() == (None,)
    _setup_module().apply_migrations(conn)
    assert conn.execute("SELECT genres FROM movies LIMIT 1").fetchone() is None
    assert conn.execute("SELECT count(*) FROM seat_holds").fetchone() == (0,)
