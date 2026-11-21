"""GET /help and the Help & info content file."""
from app.help_info import help_as_text, load_help


def test_content_file_is_complete():
    data = load_help()
    assert data["title"] and data["notice"]
    assert len(data["sections"]) >= 4
    ids = [section["id"] for section in data["sections"]]
    assert len(ids) == len(set(ids))                       # section ids are unique
    for section in data["sections"]:
        assert section["title"] and section["items"]
        for item in section["items"]:
            assert item["q"].strip() and item["a"].strip()


def test_content_matches_how_the_system_behaves():
    text = help_as_text()
    assert "5 minutes" in text          # the seat hold time (HOLD_SECONDS = 300)
    assert "Up to 10 seats" in text     # the API's limit per booking


def test_help_endpoint_returns_the_same_content(client):
    response = client.get("/help")
    assert response.status_code == 200
    assert response.json() == load_help()


def test_text_version_contains_every_answer():
    text = help_as_text()
    for section in load_help()["sections"]:
        for item in section["items"]:
            assert item["a"] in text
