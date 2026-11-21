"""Injected side effects and the stale message recovery boundary."""
import importlib.util
from pathlib import Path

import pytest

import confirm_booking
import demo_sms
from tests.conftest import confirm


def test_injected_effects(connection, make_booking):
    body = make_booking()
    releases, emails = [], []
    result = confirm_booking._process_record(connection, body,
        release_hold=lambda *args: releases.append(args),
        send_email=lambda *args: emails.append(args))
    assert result.startswith("CONFIRMED")
    assert releases[0][0] == body["hold_id"]
    assert len(releases[0][2]) == 2 and len(emails[0][1]) == 2
    assert confirm(connection, body).startswith("SKIPPED")
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
    assert confirm(connection, stale).startswith("SKIPPED")
    assert not connection.execute("SELECT 1 FROM booking_seats WHERE booking_id = %s", (stale["booking_id"],)).fetchone()


def test_allowed_numbers_normalized(monkeypatch):
    monkeypatch.setenv("SMS_DEMO_NUMBERS", "9800000000, junk, +91 98000-00001,09800000000")
    assert demo_sms._allowed_numbers() == {"+919800000000", "+919800000001"}


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
