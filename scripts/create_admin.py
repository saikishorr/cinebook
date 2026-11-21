"""Create or reset a film-admin account using hidden password input."""
import argparse
import getpass
import logging
import re
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.admin_auth import hash_password  # noqa: E402


def create_admin(connection, username, password):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("Username must be 1-64 letters, numbers, underscores, dots or hyphens")
    if len(password) < 8:
        raise ValueError("Use a password of at least 8 characters")
    with connection.transaction():
        row = connection.execute("""INSERT INTO admin_users (username,password_hash) VALUES (%s,%s)
                                    ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash RETURNING id""",
                                 (username,hash_password(password))).fetchone()
        user_id = row["id"] if isinstance(row,dict) else row[0]
        # Password resets revoke existing sessions immediately.
        connection.execute("DELETE FROM admin_sessions WHERE admin_user_id = %s", (user_id,))
    connection.commit()
    logging.getLogger(__name__).info("Admin account saved username=%r movie_id=-", username)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username")
    args = parser.parse_args()
    username = args.username or input("Admin username: ").strip()
    password = getpass.getpass("Admin password (at least 8 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match; nothing was changed.")
    values = dotenv_values(ROOT / "backend/.env")
    if not values.get("DATABASE_URL"):
        raise SystemExit("Create backend/.env with DATABASE_URL and run setup-local.ps1 first.")
    with psycopg.connect(values["DATABASE_URL"]) as connection:
        create_admin(connection, username, password)
    print(f"Admin account {username!r} saved. Sign in through the admin page.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except psycopg.Error:
        raise SystemExit("Could not save the admin account. Check DATABASE_URL and run setup-local.ps1 first.") from None
