"""The SMS choice on POST /bookings is checked before any seat hold is touched."""
from tests.conftest import DEMO_NUMBERS


def _book(client, **extra):
    body = {"hold_id": "no-such-hold", "full_name": "Test Person", "email": "test@example.com", **extra}
    return client.post("/bookings", json=body)


def test_consent_without_phone_is_refused(client):
    response = _book(client, sms_consent=True)
    assert response.status_code == 422
    assert "mobile number" in response.json()["detail"]


def test_invalid_phone_is_refused(client):
    response = _book(client, sms_consent=True, phone="12345")
    assert response.status_code == 422
    assert "valid mobile number" in response.json()["detail"]


def test_number_not_on_the_demo_list_is_refused(client):
    response = _book(client, sms_consent=True, phone="9999999999")
    assert response.status_code == 422
    assert "not registered for demo SMS" in response.json()["detail"]


def test_registered_number_passes_the_sms_check(client):
    # Passes the SMS check, then stops at the (fake) hold: 404 or 503, never 422.
    response = _book(client, sms_consent=True, phone=DEMO_NUMBERS[0][3:])
    assert response.status_code in (404, 503)


def test_no_consent_means_no_sms_check(client):
    response = _book(client, phone="12345")
    assert response.status_code in (404, 503)
