"""POST /demo-phone/inbox"""
from app.config import settings
from tests.conftest import ACCESS_CODE, DEMO_NUMBERS


def _inbox(client, phone, code=ACCESS_CODE):
    return client.post("/demo-phone/inbox", json={"phone": phone, "access_code": code})


def test_inbox_shows_the_numbers_messages(client, sample):
    response = _inbox(client, sample["phone"][3:])          # typed without +91
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == sample["phone"]
    mine = [m for m in data["messages"] if m["booking_ref"] == sample["booking_ref"]]
    assert len(mine) == 1
    assert mine[0]["chat_code"] == sample["code"]


def test_other_registered_number_does_not_see_these_messages(client, sample):
    data = _inbox(client, DEMO_NUMBERS[1]).json()
    assert all(m["booking_ref"] != sample["booking_ref"] for m in data["messages"])


def test_wrong_access_code_is_refused(client):
    response = _inbox(client, DEMO_NUMBERS[0], code="wrong-code")
    assert response.status_code == 401


def test_unregistered_number_gets_the_same_refusal(client):
    response = _inbox(client, "+919999999999")
    assert response.status_code == 401
    assert response.json()["detail"] == _inbox(client, DEMO_NUMBERS[0], code="nope").json()["detail"]


def test_repeated_wrong_attempts_are_locked_out(client):
    statuses = [_inbox(client, DEMO_NUMBERS[0], code="wrong").status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    # Even the right code is refused during the lock-out.
    assert _inbox(client, DEMO_NUMBERS[0]).status_code == 429


def test_demo_phone_is_off_without_an_access_code(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_phone_access_code", "")
    assert _inbox(client, DEMO_NUMBERS[0]).status_code == 503
