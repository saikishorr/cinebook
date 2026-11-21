"""Real PostgreSQL checks for local mode and the additive frontend contract."""
import importlib.util
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from app import queue
from app.config import Settings, settings
from app.holds import postgres
from app.holds.base import SeatsUnavailable
from app.logging_config import request_id
from app.phone import normalize_phone
from app.routers import bookings


@pytest.fixture
def show(database_url):
    tag = secrets.token_hex(6)
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        screen = conn.execute("SELECT sc.id FROM screens sc JOIN cinemas ci ON ci.id = sc.cinema_id WHERE ci.is_active ORDER BY sc.id LIMIT 1").fetchone()["id"]
        movie = conn.execute("SELECT id FROM movies WHERE is_active ORDER BY id LIMIT 1").fetchone()["id"]
        start = datetime.now(timezone.utc) + timedelta(days=3, microseconds=secrets.randbelow(1000000))
        row = conn.execute("""INSERT INTO shows (movie_id, screen_id, start_time, regular_price, premium_price)
                              VALUES (%s, %s, %s, 200, 350) RETURNING id""", (movie, screen, start)).fetchone()
        seats = [r["id"] for r in conn.execute("SELECT id FROM seats WHERE screen_id = %s ORDER BY id", (screen,))]
        data = {"id": row["id"], "movie_id": movie, "seats": seats, "start": start,
                "email": f"contract-{tag}@example.com"}
        yield data
        conn.execute("DELETE FROM seat_holds WHERE show_id = %s", (row["id"],))
        conn.execute("DELETE FROM bookings WHERE show_id = %s", (row["id"],))
        conn.execute("DELETE FROM customers WHERE email = %s", (data["email"],))
        conn.execute("DELETE FROM shows WHERE id = %s", (row["id"],))


def _hold(client, show, index=0):
    response = client.post(f"/shows/{show['id']}/holds", json={"seat_ids": [show["seats"][index]]})
    assert response.status_code == 201, response.text
    return response.json()["hold_id"]


def _book(client, show, **extra):
    hold = _hold(client, show, extra.pop("index", 0))
    response = client.post("/bookings", json={"hold_id": hold, "full_name": "Original Person",
                                            "email": show["email"], **extra})
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "PENDING"
    return response.json()["booking_ref"], hold


def test_postgres_concurrent_holds_and_lifecycle(show):
    barrier = threading.Barrier(2)
    now = int(time.time())
    ids = [secrets.token_hex(8), secrets.token_hex(8)]

    def create(hold):
        barrier.wait()
        try:
            postgres.create_hold(hold, show["id"], show["seats"][:2], now + 300, now)
            return hold
        except SeatsUnavailable:
            return None

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(create, ids))
    assert sum(result is not None for result in results) == 1
    winner = next(r for r in results if r)
    assert postgres.get_hold(next(i for i in ids if i != winner)) is None
    assert postgres.held_seat_ids(show["id"]) == set(show["seats"][:2])
    assert postgres.claim_hold(winner, "FIRST") == ("CLAIMED", None)
    assert postgres.claim_hold(winner, "SECOND") == ("ALREADY_CLAIMED", "FIRST")
    postgres.unclaim_hold(winner, "SECOND")
    assert postgres.get_hold(winner)["booking_ref"] == "FIRST"
    postgres.unclaim_hold(winner, "FIRST")
    assert postgres.claim_hold(winner, "SECOND") == ("CLAIMED", None)
    postgres.release_hold(winner, show["id"], show["seats"][:2])
    assert postgres.get_hold(winner) is None
    assert postgres.claim_hold(winner, "THIRD") == ("EXPIRED_OR_MISSING", None)
    postgres.create_hold("expired", show["id"], show["seats"][:1], now - 1, now - 300)
    assert postgres.claim_hold("expired", "OLD") == ("EXPIRED_OR_MISSING", None)
    assert postgres.held_seat_ids(show["id"]) == set()
    postgres.create_hold("replacement", show["id"], show["seats"][:1], now + 300, now)
    postgres.release_hold("expired", show["id"], show["seats"][:1])
    assert postgres.held_seat_ids(show["id"]) == {show["seats"][0]}


def test_local_flow_confirm_sms_chat_cancel(client, show, database_url, tmp_path, monkeypatch):
    from app import email
    monkeypatch.setattr(email, "OUTBOX", tmp_path)
    monkeypatch.setattr(settings, "sms_demo_numbers", "9800000001")
    ref, hold = _book(client, show, sms_consent=True, phone="9800000001")
    data = client.get(f"/bookings/{ref}").json()
    assert data["status"] == "CONFIRMED"
    assert data["email"] == show["email"] and data["phone"] == "9800000001"
    assert data["email_masked"] == "c***@example.com"
    assert data["phone_masked"] == "+91 ******0001"
    assert data["movie_language"] and data["duration_minutes"] > 0
    assert data["cancellable"] is True
    assert datetime.fromisoformat(data["cancel_deadline"]) == show["start"] - timedelta(minutes=120)
    assert data["cancelled_at"] is None and data["refund_ref"] is None
    assert data["start_time"].endswith("+05:30")
    assert postgres.get_hold(hold) is None
    with psycopg.connect(database_url) as conn:
        code, count = conn.execute("""SELECT cl.code, (SELECT count(*) FROM sms_messages WHERE booking_id = b.id)
                                      FROM chat_links cl JOIN bookings b ON b.id = cl.booking_id
                                      WHERE b.booking_ref = %s""", (ref,)).fetchone()
    assert count == 1
    assert client.get(f"/chat-links/{code}").json()["booking_ref"] == ref
    assert client.get(f"/chat-links/{code}/messages").status_code == 200
    response = client.post(f"/bookings/{ref}/cancel", json={"email": show["email"].upper()})
    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancel_deadline"] is None and cancelled["cancellable"] is False
    assert cancelled["cancelled_at"].endswith("+05:30")
    assert cancelled["refund_ref"].startswith("SIMREF-")
    assert len(list(tmp_path.glob("*.eml"))) == 2
    seat = next(s for s in client.get(f"/shows/{show['id']}/seats").json()["seats"] if s["id"] == show["seats"][0])
    assert seat["status"] == "AVAILABLE"
    again = client.post(f"/bookings/{ref}/cancel", json={"email": show["email"]})
    assert again.json() == {"detail": "Only confirmed bookings can be cancelled"}
    assert again.status_code == 409


def test_movie_and_show_contract_availability_and_chat(client, show, database_url):
    movies = client.get("/movies").json()
    movie = client.get(f"/movies/{show['movie_id']}").json()
    assert movie == next(m for m in movies if m["id"] == movie["id"])
    assert movie["genres"] and movie["release_date"]
    assert all(movie[key] is None or isinstance(movie[key], str) for key in ("backdrop_url", "trailer_url"))
    assert client.get("/movies/999999999").json() == {"detail": "Movie 999999999 not found"}
    with psycopg.connect(database_url, autocommit=True) as conn:
        inactive = conn.execute("INSERT INTO movies (title, duration_minutes, language, certificate, is_active) VALUES ('Inactive test', 100, 'Hindi', 'U', FALSE) RETURNING id").fetchone()[0]
        try:
            response = client.get(f"/movies/{inactive}")
            assert response.status_code == 404
            assert response.json() == {"detail": f"Movie {inactive} not found"}
        finally:
            conn.execute("DELETE FROM movies WHERE id = %s", (inactive,))
    _hold(client, show)
    paths = [f"/movies/{show['movie_id']}/shows", f"/shows?date={show['start'].astimezone(__import__('zoneinfo').ZoneInfo(settings.app_timezone)).date()}", f"/shows/{show['id']}"]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        row = data if isinstance(data, dict) else next(r for r in data if r["id"] == show["id"])
        assert row["seats_total"] == len(show["seats"])
        assert row["seats_available"] == len(show["seats"]) - 1
        assert row["start_time"].endswith("+05:30")
    ref, _ = _book(client, show, index=1)
    # Chat uses the identical expression, including a held seat only once if also booked.
    from app.availability import availability_columns
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = conn.execute(f"SELECT {availability_columns()} FROM shows s WHERE id = %s", (show["id"],)).fetchone()
        assert row["seats_available"] == len(show["seats"]) - 2
        from app.chat_engine import build_context
        booking_id = conn.execute("SELECT id FROM bookings WHERE booking_ref = %s", (ref,)).fetchone()["id"]
        context = build_context(conn.cursor(), booking_id)
        assert f"{len(show['seats']) - 2} seats free" in context


@pytest.mark.parametrize("status", ["PENDING", "FAILED", "CANCELLED"])
def test_cancellation_nonconfirmed(client, show, database_url, status):
    ref, _ = _book(client, show)
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("UPDATE bookings SET status = %s WHERE booking_ref = %s", (status, ref))
    data = client.get(f"/bookings/{ref}").json()
    assert data["cancel_deadline"] is None and not data["cancellable"]
    response = client.post(f"/bookings/{ref}/cancel", json={"email": show["email"]})
    assert response.status_code == 409
    assert response.json() == {"detail": "Only confirmed bookings can be cancelled"}


def test_cancellation_unknown_wrong_email_cutoff_and_email_failure(client, show, monkeypatch):
    ref, _ = _book(client, show)
    for reference, email in ((ref, "wrong@example.com"), ("UNKNOWN", show["email"])):
        response = client.post(f"/bookings/{reference}/cancel", json={"email": email})
        assert response.status_code == 404 and response.json() == {"detail": "Booking not found"}
    monkeypatch.setattr(settings, "cancel_cutoff_minutes", 60 * 24 * 60)
    assert not client.get(f"/bookings/{ref}").json()["cancellable"]
    response = client.post(f"/bookings/{ref}/cancel", json={"email": show["email"]})
    assert response.status_code == 409
    assert response.json() == {"detail": "Bookings can only be cancelled up to 1440 hours before the show"}
    monkeypatch.setattr(settings, "cancel_cutoff_minutes", 120)
    monkeypatch.setattr("app.email.send_cancellation", lambda *args: 1 / 0)   # moved to app/cancellation.py
    assert client.post(f"/bookings/{ref}/cancel", json={"email": show["email"]}).status_code == 200
    assert client.get(f"/bookings/{ref}").json()["status"] == "CANCELLED"


def test_exact_default_cutoff_message(client, show, database_url):
    ref, _ = _book(client, show)
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("UPDATE shows SET start_time = now() + interval '1 hour' WHERE id = %s", (show["id"],))
    response = client.post(f"/bookings/{ref}/cancel", json={"email": show["email"]})
    assert response.status_code == 409
    assert response.json() == {"detail": "Bookings can only be cancelled up to 2 hours before the show"}


def test_booking_limits_and_unknown_lookup(client):
    responses = [client.get("/bookings/UNKNOWN") for _ in range(31)]
    assert all(r.status_code == 404 and r.json() == {"detail": "Booking not found"} for r in responses[:30])
    assert responses[-1].status_code == 429
    responses = [client.post("/bookings/UNKNOWN/cancel", json={"email": "x@example.com"}) for _ in range(11)]
    assert [r.status_code for r in responses] == [404] * 10 + [429]


def test_customer_snapshot_and_reference_retry(client, show, monkeypatch, database_url):
    ref, _ = _book(client, show, phone="9800000001")
    references = iter([ref, "BK" + secrets.token_hex(3).upper()])
    monkeypatch.setattr(bookings, "_new_booking_ref", lambda: next(references))
    captured = []
    original = queue.send_booking_message

    def send(message):
        assert postgres.get_hold(message["hold_id"])["booking_ref"] == message["booking_ref"]
        captured.append(message["booking_ref"])
        original(message)

    monkeypatch.setattr(queue, "send_booking_message", send)
    second, _ = _book(client, show, index=1, full_name="Different Person", phone="9800000002")
    assert captured == [second] and second != ref
    assert client.get(f"/bookings/{ref}").json()["full_name"] == "Original Person"
    assert client.get(f"/bookings/{second}").json()["full_name"] == "Different Person"
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT full_name, phone FROM customers WHERE email = %s", (show["email"],)).fetchone() == ("Original Person", "9800000001")


def test_reference_retry_exhaustion_releases_claim(client, show, monkeypatch):
    ref, _ = _book(client, show)
    monkeypatch.setattr(bookings, "_new_booking_ref", lambda: ref)
    hold = _hold(client, show, 1)
    response = client.post("/bookings", json={"hold_id": hold, "full_name": "Test Person", "email": show["email"]})
    assert response.status_code == 503 and response.json() == {"detail": "Could not create booking"}
    assert postgres.get_hold(hold)["booking_ref"] is None


def test_missing_phone_mask_and_new_booking_sweeps_old_pending(client, show, database_url, monkeypatch):
    monkeypatch.setattr(queue.local_worker(), "_process_record", lambda *args, **kwargs: 1 / 0)
    ref, _ = _book(client, show)
    assert client.get(f"/bookings/{ref}").json()["phone_masked"] is None
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("UPDATE bookings SET created_at = now() - interval '11 minutes' WHERE booking_ref = %s", (ref,))
    _book(client, show, index=1)
    assert client.get(f"/bookings/{ref}").json()["status"] == "FAILED"


def test_inline_startup_sweeps(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.main import lifespan
    calls = []
    monkeypatch.setattr(queue, "sweep_local", lambda: calls.append(True))
    class Pool:
        def open(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr("app.main.create_pool", lambda url: Pool())
    async def start():
        async with lifespan(SimpleNamespace(state=SimpleNamespace())):
            assert calls == [True]
    asyncio.run(start())


def test_inline_failure_stays_pending_then_sweeper_frees_seats(client, show, monkeypatch, database_url):
    worker = queue.local_worker()
    monkeypatch.setattr(worker, "_process_record", lambda *args, **kwargs: 1 / 0)
    ref, _ = _book(client, show)
    assert client.get(f"/bookings/{ref}").json()["status"] == "PENDING"
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("UPDATE bookings SET created_at = now() - interval '11 minutes' WHERE booking_ref = %s", (ref,))
        worker.sweep_stale_pending(conn)
        assert conn.execute("SELECT status FROM bookings WHERE booking_ref = %s", (ref,)).fetchone()["status"] == "FAILED"
        assert not conn.execute("SELECT 1 FROM booking_seats WHERE show_id = %s", (show["id"],)).fetchone()


def test_settings_queue_validation_and_cloud_defaults(monkeypatch):
    for key in ("HOLDS_BACKEND", "QUEUE_BACKEND", "EMAIL_BACKEND", "BOOKING_QUEUE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="BOOKING_QUEUE_URL is required"):
        Settings(_env_file=None, database_url="postgresql://localhost/test", booking_queue_url="")
    local = Settings(_env_file=None, database_url="postgresql://localhost/test", queue_backend="inline")
    assert local.holds_backend == "dynamodb" and local.email_backend == "ses"
    assert local.cancel_cutoff_minutes == 120


def test_dependency_pins_match_tested_versions():
    from importlib.metadata import version
    from packaging.requirements import Requirement
    root = Path(__file__).resolve().parents[2]
    for path in (root / "backend/requirements.txt", root / "backend/requirements-dev.txt", root / "worker/requirements.txt"):
        for line in path.read_text().splitlines():
            if not line or line.startswith(("#", "-r")):
                continue
            requirement = Requirement(line)
            assert len(list(requirement.specifier)) == 1
            assert next(iter(requirement.specifier)).operator == "=="
            assert version(requirement.name) in requirement.specifier


def test_eval_accepts_online_guidance_and_rejects_claimed_cancellation(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root)
    spec = importlib.util.spec_from_file_location("chat_eval_contract", root / "backend/eval/chat_eval.py")
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)
    facts = {"seats": ["A1"], "clock": "7:30", "screen": "Screen 1", "movie": "Film", "ref": "BKTEST",
             "movies": ["Film"], "premium": "350", "other_ref": "OTHERREF", "email": "private@example.com"}
    cases = [c for c in evaluation.cases(facts) if "cancel" in c["q"].lower()]
    assert len(cases) == 2
    for case in cases:
        assert evaluation.check(case, "ANSWERED", "I cannot cancel bookings. Use the booking page up to 2 hours before the show.", facts) == []
    assert evaluation.check(cases[1], "ANSWERED", "Your booking has been cancelled. Use the booking page.", facts)


def test_request_id_logs_and_cors(client, monkeypatch, caplog):
    seen = []
    from app.routers import help as help_router
    original = help_router.load_help

    def load():
        seen.append(request_id.get())
        logging.getLogger("app.test").info("request log test")
        return original()

    monkeypatch.setattr(help_router, "load_help", load)
    with caplog.at_level(logging.INFO):
        response = client.get("/help", headers={"Origin": "https://example.test"})
    assert response.headers["x-request-id"] == seen[0] != "-"
    assert "access-control-allow-credentials" not in response.headers
    assert any(r.message == "request log test" and r.request_id == seen[0] for r in caplog.records)
    health = client.get("/health").json()
    assert health == {"status": "ok", "database": "ok", "holds_backend": "postgres", "queue_backend": "inline"}


@pytest.mark.parametrize("raw", ["9800000000", "09800000000", "919800000000", "+91 98000-00000", "00919800000000", "+14155550123", "bad", "", None])
def test_worker_phone_matches_api(raw):
    path = Path(__file__).resolve().parents[2] / "worker/demo_sms.py"
    spec = importlib.util.spec_from_file_location("phone_parity_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        expected = normalize_phone(raw)
    except ValueError:
        with pytest.raises(ValueError):
            module.normalize_phone(raw)
    else:
        assert module.normalize_phone(raw) == expected
