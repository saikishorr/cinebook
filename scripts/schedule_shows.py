"""Batch-persist CineBook's generated demo programmes, preserving existing shows."""
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.scheduling import schedule_shows, clear_hidden_shows  # noqa: E402, F401


def main():
    import psycopg
    from dotenv import dotenv_values
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="replace unbooked, unheld future demo shows at active cinemas")
    args = parser.parse_args()
    values = dotenv_values(ROOT / "backend/.env")
    with psycopg.connect(values["DATABASE_URL"], autocommit=True) as connection:
        result = schedule_shows(connection,rebuild=args.rebuild)
    print(f"Created {result['created']} weekly demo shows; freed {result['cleared']} unbooked, unheld shows.")


if __name__ == "__main__":
    main()
