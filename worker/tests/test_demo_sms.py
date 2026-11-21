"""Step 2.4: the worker creates the chat link and the demo SMS when it confirms a booking."""
import json
import re
from datetime import datetime, timezone

import confirm_booking
from demo_sms import SMS_LIMIT, build_sms_text
from tests.conftest import DEMO

WHEN = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)          # 7:30 PM in India


# ---------------------------------------------------------------- the message text (no database)
def test_normal_message_fits_one_sms():
    text = build_sms_text("BKA50LS9", "Dune: Part Two", WHEN, "Screen 2", ["F7", "F8"],
                          "http://localhost:5173/c/Ab3dEf7hJk")
    assert "DEMO" in text and "BKA50LS9" in text
    assert "Pune" in text and "CineBook" in text
    assert text.endswith("/c/Ab3dEf7hJk")
    assert len(text) <= SMS_LIMIT


def test_long_seat_list_and_title_are_shortened():
    seats = [f"F{n}" for n in range(1, 13)]
    text = build_sms_text("BKA50LS9", "A Very Long Movie Title That Goes On And On Forever", WHEN, "Screen 2",
                          seats, "https://d1234abcd5678ef.cloudfront.net/c/Ab3dEf7hJk")
    assert len(text) <= SMS_LIMIT
    assert "F1 +11 more" in text
    assert text.endswith("/c/Ab3dEf7hJk")                       # the link is never cut


def test_long_cinema_and_movie_stay_within_160_characters():
    text = build_sms_text("BKABC123", "An Extremely Long Movie Name With Many Words" * 3, WHEN,
                          "Audi 1", ["G11", "G12", "G13"], "http://localhost:5173/c/Ab3dEf7hJk",
                          "PVR INOX Icon Pavilion Mall With An Extremely Long Cinema Name" * 2, "Shivajinagar")
    assert len(text) <= 160 and "DEMO" in text and "Shivajinagar" in text and "PVR" in text
    assert text.endswith("/c/Ab3dEf7hJk")


# ---------------------------------------------------------------- the worker with the local database
def _run(body):
    event = {"Records": [{"messageId": "m1", "body": json.dumps(body)}]}
    return confirm_booking.lambda_handler(event, None)


def _rows(connection, booking_id):
    with connection.cursor() as cur:
        cur.execute("SELECT code FROM chat_links WHERE booking_id = %s", (booking_id,))
        links = cur.fetchall()
        cur.execute("SELECT to_phone, body FROM sms_messages WHERE booking_id = %s", (booking_id,))
        return links, cur.fetchall()


def test_confirmation_writes_link_and_sms(connection, make_booking, fake_aws):
    body = make_booking()
    assert _run(body) == {"batchItemFailures": []}
    links, sms = _rows(connection, body["booking_id"])
    assert len(links) == 1 and re.fullmatch(r"[A-Za-z0-9]{10}", links[0]["code"])
    assert len(sms) == 1 and sms[0]["to_phone"] == DEMO
    assert sms[0]["body"].endswith(f"/c/{links[0]['code']}")
    assert body["booking_ref"] in sms[0]["body"]
    assert len(fake_aws) == 1                                      # the email still goes out


def test_repeated_message_does_not_duplicate(connection, make_booking):
    body = make_booking()
    _run(body)
    _run(body)                                                     # SQS can deliver a message twice
    links, sms = _rows(connection, body["booking_id"])
    assert len(links) == 1 and len(sms) == 1


def test_no_consent_means_no_link_and_no_sms(connection, make_booking):
    body = make_booking(sms_phone=None, sms_consent=False)
    _run(body)
    assert _rows(connection, body["booking_id"]) == ([], [])


def test_number_removed_from_demo_list_is_skipped(connection, make_booking, monkeypatch):
    body = make_booking()
    monkeypatch.setenv("SMS_DEMO_NUMBERS", "+919800000002")
    assert _run(body) == {"batchItemFailures": []}                 # booking still confirmed
    assert _rows(connection, body["booking_id"]) == ([], [])


def test_sms_failure_never_undoes_the_booking(connection, make_booking, monkeypatch):
    body = make_booking()
    monkeypatch.setattr("demo_sms.build_sms_text", lambda *args: 1 / 0)   # simulate a bug
    assert _run(body) == {"batchItemFailures": []}
    with connection.cursor() as cur:
        cur.execute("SELECT status FROM bookings WHERE id = %s", (body["booking_id"],))
        assert cur.fetchone()["status"] == "CONFIRMED"
    assert _rows(connection, body["booking_id"]) == ([], [])       # the half-made link was rolled back
