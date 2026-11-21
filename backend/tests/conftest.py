"""Shared test setup.

The tests use the database in backend/.env (your LOCAL PostgreSQL). Each test that needs
data creates its own throw-away booking and deletes it again, so your data is not changed.
"""
import secrets
import string

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app import chat_llm
from app.routers import chat, chat_links, demo_phone
from app.routers import bookings
from app.routers import admin

DEMO_NUMBERS = ["+919800000001", "+919800000002"]
ACCESS_CODE = "TestCode123"
_ALPHABET = string.ascii_letters + string.digits


@pytest.fixture(autouse=True)
def demo_settings(monkeypatch):
    """Use fixed test numbers and code instead of the real ones, and start every test with clean limits."""
    monkeypatch.setattr(settings, "sms_demo_numbers", ",".join(DEMO_NUMBERS))
    monkeypatch.setattr(settings, "demo_phone_access_code", ACCESS_CODE)
    # Older booking tests predate customer accounts; tests/test_accounts.py switches login back on.
    monkeypatch.setattr(settings, "require_login_for_booking", False)
    chat_links.limiter.reset()
    demo_phone.failures.reset()
    bookings.lookup_limiter.reset()
    bookings.cancel_limiter.reset()
    admin.login_failures.reset()
    # Phase 3: the tests never call a real AI model - a stand-in answers instead.
    chat.limiter.reset()
    monkeypatch.setattr(settings, "chat_provider", "fake")
    monkeypatch.setattr(settings, "chat_model_id", "fake-model")
    monkeypatch.setattr(chat_llm, "fake_responder", chat_llm._default_fake)
    # A regression must fail locally instead of contacting a live model or the network.
    import urllib.request
    def no_network(*args, **kwargs):
        raise AssertionError("Tests must not contact the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)


@pytest.fixture(scope="session")
def database_url():
    try:
        psycopg.connect(settings.database_url, connect_timeout=3).close()
    except Exception as error:
        pytest.skip(f"Local database not reachable ({error.__class__.__name__}); start PostgreSQL first")
    return settings.database_url


@pytest.fixture(scope="session")
def client(database_url):
    with TestClient(app) as test_client:
        yield test_client


def new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(10))


@pytest.fixture
def sample(database_url):
    """A confirmed booking with a chat link and one demo SMS. Removed after the test."""
    tag = secrets.token_hex(3).upper()
    code = new_code()
    with psycopg.connect(database_url, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id, screen_id FROM shows ORDER BY id LIMIT 1")
        show_id, screen_id = cursor.fetchone()
        cursor.execute("""SELECT id FROM seats WHERE screen_id = %s
                          AND id NOT IN (SELECT seat_id FROM booking_seats WHERE show_id = %s)
                          ORDER BY id LIMIT 2""", (screen_id, show_id))
        seat_ids = [row[0] for row in cursor.fetchall()]
        cursor.execute("""INSERT INTO customers (full_name, email, phone) VALUES (%s, %s, %s) RETURNING id""",
                       ("Test Person", f"pytest-{tag.lower()}@example.com", DEMO_NUMBERS[0]))
        customer_id = cursor.fetchone()[0]
        cursor.execute("""INSERT INTO bookings (booking_ref, customer_id, show_id, status, total_amount,
                                                sms_phone, sms_consent, confirmed_at)
                          VALUES (%s, %s, %s, 'CONFIRMED', 500, %s, TRUE, now()) RETURNING id""",
                       (f"PT{tag}", customer_id, show_id, DEMO_NUMBERS[0]))
        booking_id = cursor.fetchone()[0]
        for seat_id in seat_ids:
            cursor.execute("""INSERT INTO booking_seats (booking_id, show_id, seat_id, price)
                              VALUES (%s, %s, %s, 250)""", (booking_id, show_id, seat_id))
        cursor.execute("INSERT INTO chat_links (code, booking_id) VALUES (%s, %s)", (code, booking_id))
        cursor.execute("""INSERT INTO sms_messages (booking_id, to_phone, body) VALUES (%s, %s, %s)""",
                       (booking_id, DEMO_NUMBERS[0], f"CineBook: Booking PT{tag} confirmed. Chat: /c/{code}"))
    yield {"booking_id": booking_id, "booking_ref": f"PT{tag}", "code": code, "phone": DEMO_NUMBERS[0],
           "seat_count": len(seat_ids)}
    with psycopg.connect(database_url, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))   # cascades to seats, link, SMS
        cursor.execute("DELETE FROM customers WHERE id = %s", (customer_id,))


def run_sql(database_url: str, sql: str, params: tuple = ()):
    with psycopg.connect(database_url, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone() if cursor.description else None
