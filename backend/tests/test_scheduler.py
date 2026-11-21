"""Persisted programmes preserve booked and held shows across repeated imports."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from tests.test_cinema_import import importer
from tests.test_migrations import isolated_schema as isolated_schema

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("schedule_shows_test", ROOT / "scripts/schedule_shows.py")
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


def test_batch_scheduler_idempotence_and_protected_hidden_shows(isolated_schema):
    conn = isolated_schema
    conn.execute((ROOT / "db/schema.sql").read_text())
    importer.import_cinemas(conn, importer.load_snapshot()[:3])
    for i, language in enumerate(("Hindi", "Marathi", "English", "Telugu")):
        conn.execute("INSERT INTO movies (title,duration_minutes,language,certificate) VALUES (%s,120,%s,'U')", (f"Film {i}",language))
    now = datetime.now(timezone.utc)
    result = scheduler.schedule_shows(conn, days=3, now=now)
    assert result["created"] > 50
    assert scheduler.schedule_shows(conn, days=3, now=now)["created"] == 0
    movie = conn.execute("SELECT min(id) FROM movies").fetchone()[0]
    rows = conn.execute("SELECT id,screen_id,movie_id,start_time,regular_price,premium_price FROM shows WHERE movie_id = %s AND start_time > %s ORDER BY id LIMIT 2", (movie,now)).fetchall()
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Protected','protected@example.com') RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('PROTECTED',%s,%s,200)", (customer,rows[0][0]))
    seat = conn.execute("SELECT min(id) FROM seats WHERE screen_id = %s", (rows[1][1],)).fetchone()[0]
    conn.execute("INSERT INTO seat_holds (hold_id,show_id,seat_ids,expires_at) VALUES ('protected-hold',%s,%s,now()+interval '5 minutes')", (rows[1][0],[seat]))
    conn.execute("UPDATE movies SET is_active = FALSE WHERE id = %s", (movie,))
    rerun = scheduler.schedule_shows(conn, days=3, now=now)
    assert rerun["cleared"] > 0
    protected = conn.execute("SELECT id,screen_id,movie_id,start_time,regular_price,premium_price FROM shows WHERE id = ANY(%s) ORDER BY id", ([r[0] for r in rows],)).fetchall()
    assert protected == rows
    assert scheduler.schedule_shows(conn, days=3, now=now)["created"] == 0
    conn.execute("UPDATE seat_holds SET expires_at = now() - interval '1 second' WHERE hold_id = 'protected-hold'")
    scheduler.schedule_shows(conn, days=3, now=now)
    assert conn.execute("SELECT 1 FROM shows WHERE id = %s", (rows[1][0],)).fetchone() is None
