"""Worker tests use the LOCAL database in worker/.env. Email and seat-hold calls are replaced
with fakes, so nothing is sent and AWS is not contacted. Test data is removed afterwards."""
import os
import secrets

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "backend", ".env"))
os.environ.setdefault("AWS_REGION", "ap-south-1")

import confirm_booking  # noqa: E402  (after the settings are loaded)

DEMO = "+919800000001"


@pytest.fixture(autouse=True)
def fake_aws(monkeypatch):
    sent = []
    monkeypatch.setattr(confirm_booking, "_release_hold", lambda *args: None)
    monkeypatch.setattr(confirm_booking, "_send_confirmation", lambda booking, seats: sent.append(booking["email"]))
    monkeypatch.setenv("SMS_DEMO_NUMBERS", f"{DEMO},+919800000002")
    monkeypatch.setenv("PUBLIC_SITE_URL", "http://localhost:5173")
    import boto3
    def no_aws(*args, **kwargs):
        raise AssertionError("Worker tests must not contact AWS")
    monkeypatch.setattr(boto3, "client", no_aws)
    return sent


@pytest.fixture
def connection():
    url = os.getenv("DATABASE_URL")
    try:
        conn = psycopg.connect(url, row_factory=dict_row, autocommit=True, connect_timeout=3)
    except Exception as error:
        pytest.skip(f"Local database not reachable ({error.__class__.__name__})")
    with conn:
        yield conn


@pytest.fixture
def make_booking(connection):
    """Creates PENDING bookings like the API does; deletes them (and their links/SMS) afterwards."""
    created = []

    def _make(sms_phone=DEMO, sms_consent=True, seats=2):
        tag = secrets.token_hex(3).upper()
        with connection.cursor() as cur:
            cur.execute("SELECT id, screen_id FROM shows ORDER BY id LIMIT 1")
            show = cur.fetchone()
            cur.execute("""SELECT id FROM seats WHERE screen_id = %s
                           AND id NOT IN (SELECT seat_id FROM booking_seats WHERE show_id = %s)
                           ORDER BY id LIMIT %s""", (show["screen_id"], show["id"], seats))
            seat_ids = [r["id"] for r in cur.fetchall()]
            cur.execute("INSERT INTO customers (full_name, email) VALUES (%s, %s) RETURNING id",
                        ("Worker Test", f"worker-{tag.lower()}@example.com"))
            customer_id = cur.fetchone()["id"]
            cur.execute("""INSERT INTO bookings (booking_ref, customer_id, show_id, total_amount, sms_phone, sms_consent)
                           VALUES (%s, %s, %s, 500, %s, %s) RETURNING id""",
                        (f"WT{tag}", customer_id, show["id"], sms_phone, sms_consent))
            booking_id = cur.fetchone()["id"]
            for seat_id in seat_ids:
                cur.execute("INSERT INTO booking_seats (booking_id, show_id, seat_id, price) VALUES (%s, %s, %s, 250)",
                            (booking_id, show["id"], seat_id))
        created.append((booking_id, customer_id))
        return {"booking_id": booking_id, "booking_ref": f"WT{tag}", "hold_id": "test-hold", "show_id": show["id"]}

    yield _make
    with connection.cursor() as cur:
        for booking_id, customer_id in created:
            cur.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
            cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
