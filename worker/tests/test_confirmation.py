"""Injected side effects and the stale message recovery boundary."""
import importlib.util
import json
from pathlib import Path

import pytest

import confirm_booking
import demo_sms


def test_injected_effects(connection, make_booking):
    body = make_booking()
    releases, emails = [], []
    result = confirm_booking._process_record(connection, body,
        release_hold=lambda *args: releases.append(args),
        send_email=lambda *args: emails.append(args))
    assert result.startswith("CONFIRMED")
    assert releases[0][0] == body["hold_id"]
    assert len(releases[0][2]) == 2 and len(emails[0][1]) == 2
    assert confirm_booking._process_record(connection, body).startswith("SKIPPED")
    assert len(releases) == 1 and len(emails) == 1


def test_email_failure_keeps_confirmation(connection, make_booking):
    body = make_booking()
    def fail(*args):
        raise RuntimeError("mail unavailable")
    result = confirm_booking._process_record(connection, body, release_hold=lambda *args: None, send_email=fail)
    assert "email failed" in result
    assert connection.execute("SELECT status FROM bookings WHERE id = %s", (body["booking_id"],)).fetchone()["status"] == "CONFIRMED"


def test_sweeper_and_late_worker(connection, make_booking):
    stale = make_booking(seats=1)
    recent = make_booking(seats=1)
    connection.execute("UPDATE bookings SET created_at = now() - interval '11 minutes' WHERE id = %s", (stale["booking_id"],))
    confirm_booking.sweep_stale_pending(connection)
    assert connection.execute("SELECT status FROM bookings WHERE id = %s", (stale["booking_id"],)).fetchone()["status"] == "FAILED"
    assert connection.execute("SELECT status FROM bookings WHERE id = %s", (recent["booking_id"],)).fetchone()["status"] == "PENDING"
    assert confirm_booking._process_record(connection, stale).startswith("SKIPPED")
    assert not connection.execute("SELECT 1 FROM booking_seats WHERE booking_id = %s", (stale["booking_id"],)).fetchone()


def test_allowed_numbers_normalized(monkeypatch):
    monkeypatch.setenv("SMS_DEMO_NUMBERS", "9800000000, junk, +91 98000-00001,09800000000")
    assert demo_sms._allowed_numbers() == {"+919800000000", "+919800000001"}


def test_queued_cancellation_email(connection, monkeypatch):
    calls = []
    monkeypatch.setattr(confirm_booking, "ses", type("SES", (), {"send_email": lambda self, **kwargs: calls.append(kwargs)})())
    monkeypatch.setenv("SES_SENDER_EMAIL", "sender@example.com")
    booking = {"booking_ref": "BKABC123", "email": "test@example.com", "refund_ref": "SIMREF-123"}
    body = {"action": "CANCELLED", "booking_ref": booking["booking_ref"], "booking": booking}
    event = {"Records": [{"messageId": "cancel", "body": json.dumps(body)}]}
    assert confirm_booking.lambda_handler(event, None) == {"batchItemFailures": []}
    assert calls[0]["FromEmailAddress"] == "sender@example.com"
    assert "SIMREF-123" in calls[0]["Content"]["Simple"]["Body"]["Text"]["Data"]


def test_import_without_region_or_credentials(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    spec = importlib.util.spec_from_file_location("isolated_confirmation", Path(confirm_booking.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.dynamodb is None and module.ses is None


@pytest.mark.parametrize("raw", [None, "bad", "9800000000", "09800000000", "919800000000", "00919800000000", "+1 (415) 555-0123"])
def test_phone_parity(raw):
    path = Path(__file__).resolve().parents[2] / "backend/app/phone.py"
    spec = importlib.util.spec_from_file_location("api_phone", path)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    try:
        expected = api.normalize_phone(raw)
    except ValueError:
        with pytest.raises(ValueError):
            demo_sms.normalize_phone(raw)
    else:
        assert demo_sms.normalize_phone(raw) == expected
