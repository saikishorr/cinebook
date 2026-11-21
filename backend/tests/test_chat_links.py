"""GET /chat-links/{code}"""
from tests.conftest import new_code, run_sql


def test_valid_link_returns_booking_summary(client, sample):
    response = client.get(f"/chat-links/{sample['code']}")
    assert response.status_code == 200
    data = response.json()
    assert data["booking_ref"] == sample["booking_ref"]
    assert data["first_name"] == "Test"
    assert len(data["seats"]) == sample["seat_count"]
    # Privacy: the link never reveals contact details.
    assert "email" not in data and "phone" not in data and "full_name" not in data


def test_each_visit_is_counted(client, sample, database_url):
    client.get(f"/chat-links/{sample['code']}")
    client.get(f"/chat-links/{sample['code']}")
    count, = run_sql(database_url, "SELECT open_count FROM chat_links WHERE code = %s", (sample["code"],))
    assert count == 2


def test_unknown_code_is_not_found(client, database_url):
    assert client.get(f"/chat-links/{new_code()}").status_code == 404


def test_badly_formed_code_is_not_found(client):
    assert client.get("/chat-links/short").status_code == 404


def test_revoked_link_is_gone(client, sample, database_url):
    run_sql(database_url, "UPDATE chat_links SET revoked_at = now() WHERE code = %s", (sample["code"],))
    response = client.get(f"/chat-links/{sample['code']}")
    assert response.status_code == 410
    assert "switched off" in response.json()["detail"]


def test_too_many_lookups_are_slowed_down(client):
    statuses = [client.get("/chat-links/short").status_code for _ in range(61)]
    assert statuses[:60] == [404] * 60
    assert statuses[60] == 429
