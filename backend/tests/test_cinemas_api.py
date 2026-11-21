"""Exact additive cinema contract, scoped fixtures, real local confirmation."""
import secrets
from datetime import datetime, time, timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.rows import dict_row, tuple_row

from app.config import settings
from tests.test_local_contract import show as show, _book
from tests.test_migrations import isolated_schema as isolated_schema


@pytest.fixture
def catalogue(database_url):
    tag = secrets.token_hex(5)
    zone = ZoneInfo(settings.app_timezone)
    day = datetime.now(zone).date() + timedelta(days=2)
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        cinemas, screens, movies, shows = [], [], [], []
        for index, name in enumerate(("A Cinema", "Z Cinema", "Hidden Cinema")):
            cinema = conn.execute("""INSERT INTO cinemas (name, chain, area, address, latitude, longitude, is_active)
                                     VALUES (%s, 'PVR INOX', %s, %s, 18.5, 73.8, %s) RETURNING id""",
                                  (name + " " + tag, "Area " + tag, "Address " + tag, index != 2)).fetchone()["id"]
            cinemas.append(cinema)
            for fmt in ("2D", "IMAX"):
                screen = conn.execute("""INSERT INTO screens (cinema_id, name, total_rows, seats_per_row, format)
                                         VALUES (%s, %s, 2, 4, %s) RETURNING id""", (cinema, fmt, fmt)).fetchone()["id"]
                screens.append(screen)
                conn.execute("""INSERT INTO seats (screen_id, row_label, seat_number, seat_type)
                                SELECT %s, 'A', n, 'REGULAR' FROM generate_series(1,4) n""", (screen,))
        for index, language in enumerate(("Hindi", "Marathi", "Malayalam")):
            movies.append(conn.execute("""INSERT INTO movies (title, duration_minutes, language, certificate)
                                          VALUES (%s, 120, %s, 'U') RETURNING id""", (f"Contract {tag} {index}", language)).fetchone()["id"])
        for screen, movie, offset, hour in ((screens[2], movies[0], 0, 10), (screens[0], movies[0], 0, 14),
                                          (screens[1], movies[0], 1, 11), (screens[0], movies[1], 0, 18),
                                          (screens[4], movies[0], 2, 11)):
            start = datetime.combine(day + timedelta(days=offset), time(hour), zone)
            shows.append(conn.execute("""INSERT INTO shows (screen_id, movie_id, start_time, regular_price, premium_price)
                                         VALUES (%s, %s, %s, 220, 380) RETURNING id""", (screen, movie, start)).fetchone()["id"])
        yield {"cinemas": cinemas, "screens": screens, "movies": movies, "shows": shows, "day": day, "tag": tag}
        conn.execute("DELETE FROM shows WHERE id = ANY(%s)", (shows,))
        conn.execute("DELETE FROM seats WHERE screen_id = ANY(%s)", (screens,))
        conn.execute("DELETE FROM screens WHERE id = ANY(%s)", (screens,))
        conn.execute("DELETE FROM cinemas WHERE id = ANY(%s)", (cinemas,))
        conn.execute("DELETE FROM movies WHERE id = ANY(%s)", (movies,))


def test_cinema_endpoints_filters_order_and_404(client, catalogue):
    c = catalogue
    all_rows = client.get("/cinemas").json()
    assert [r["name"] for r in all_rows] == sorted(r["name"] for r in all_rows)
    assert c["cinemas"][2] not in [r["id"] for r in all_rows]
    filtered = client.get("/cinemas", params={"area": "area " + c["tag"], "chain": "pvr inox"}).json()
    assert [r["id"] for r in filtered] == c["cinemas"][:2]
    cinema = client.get(f"/cinemas/{c['cinemas'][0]}").json()
    assert cinema == filtered[0]
    assert set(cinema) == {"id", "name", "chain", "area", "address", "latitude", "longitude", "screens_count", "formats", "location_precision"}
    assert cinema["screens_count"] == 2 and cinema["formats"] == ["2D", "IMAX"]
    assert isinstance(cinema["latitude"], float) and cinema["address"]
    areas = client.get("/cinemas/areas").json()
    assert areas == sorted(set(areas)) and "Area " + c["tag"] in areas
    for key in (c["cinemas"][2], 999999999):
        for path in (f"/cinemas/{key}", f"/cinemas/{key}/shows"):
            response = client.get(path)
            assert response.status_code == 404 and response.json() == {"detail": f"Cinema {key} not found"}
    assert client.get("/cinemas", params={"area": "no such area"}).json() == []
    assert client.get("/cinemas", params={"movie_id": c["movies"][2]}).json() == []
    rows = client.get("/cinemas", params={"movie_id": c["movies"][0], "date": str(c["day"] + timedelta(days=1))}).json()
    assert [r["id"] for r in rows] == [c["cinemas"][0]]
    assert client.get("/cinemas", params={"date": "bad"}).status_code == 422


def test_show_lists_details_dates_and_movie_counts(client, catalogue):
    c = catalogue
    movie_id = c["movies"][0]
    row = client.get(f"/movies/{movie_id}").json()
    assert row["cinemas_count"] == 2 and row["next_show_at"].endswith("+05:30")
    assert datetime.fromisoformat(row["next_show_at"]).hour == 10
    all_shows = client.get(f"/movies/{movie_id}/shows").json()
    assert len(all_shows) == 3
    assert [r["cinema_id"] for r in all_shows] == [c["cinemas"][0], c["cinemas"][0], c["cinemas"][1]]
    dates = client.get(f"/movies/{movie_id}/show-dates").json()
    assert dates == [str(c["day"]), str(c["day"] + timedelta(days=1))]
    assert client.get(f"/movies/{c['movies'][2]}/show-dates").json() == []
    for suffix in ("shows", "show-dates"):
        response = client.get(f"/movies/999999999/{suffix}")
        assert response.status_code == 404 and response.json() == {"detail": "Movie 999999999 not found"}
    by_movie = client.get(f"/movies/{movie_id}/shows", params={"date": str(c["day"]), "cinema_id": c["cinemas"][0]}).json()
    assert [r["id"] for r in by_movie] == [c["shows"][1]]
    by_cinema = client.get(f"/cinemas/{c['cinemas'][0]}/shows", params={"date": str(c["day"])}).json()
    assert [r["id"] for r in by_cinema] == [c["shows"][1], c["shows"][3]]
    assert client.get(f"/cinemas/{c['cinemas'][0]}/shows").json() == []  # default today
    by_date = client.get("/shows", params={"date": str(c["day"])}).json()
    details = client.get(f"/shows/{c['shows'][2]}").json()
    for row in [*by_movie, *by_cinema, *by_date, details]:
        assert all(key in row for key in ("cinema_id", "cinema_name", "cinema_area", "cinema_chain", "screen_format"))
        assert row["start_time"].endswith("+05:30")
    assert details["screen_format"] == "IMAX" and details["cinema_address"]
    assert details["cinema_latitude"] == 18.5 and details["cinema_longitude"] == 73.8
    assert client.get(f"/movies/{movie_id}/shows?date=bad").status_code == 422
    filtered = client.get("/movies", params={"q": c["tag"], "language": "hindi", "showing": "true"}).json()
    assert [r["id"] for r in filtered] == [movie_id]
    assert c["movies"][2] in [r["id"] for r in client.get("/movies", params={"q": c["tag"]}).json()]
    assert c["movies"][2] not in [r["id"] for r in client.get("/movies", params={"q": c["tag"], "showing": True}).json()]
    hidden = client.get(f"/movies/{c['movies'][2]}").json()
    assert hidden["cinemas_count"] == 0 and hidden["next_show_at"] is None


def test_real_cinema_booking_hold_chat_email_sms_demo(client, show, database_url, monkeypatch, tmp_path):
    from app import email
    monkeypatch.setattr(email, "OUTBOX", tmp_path)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        cinema = conn.execute("""SELECT ci.* FROM cinemas ci JOIN screens sc ON sc.cinema_id = ci.id
                                 JOIN shows s ON s.screen_id = sc.id WHERE s.id = %s""", (show["id"],)).fetchone()
    assert (cinema["source_key"] or cinema["osm_id"]) and cinema["is_active"]
    ref, hold = _book(client, show, sms_consent=True, phone="9800000001")
    booking = client.get(f"/bookings/{ref}").json()
    assert booking["status"] == "CONFIRMED" and booking["screen_format"]
    for field in ("name", "area", "address"):
        assert booking["cinema_" + field] == cinema[field]
    message = BytesParser(policy=policy.default).parsebytes(next(tmp_path.glob("*.eml")).read_bytes()).get_content()
    assert "DEMO TICKET - not valid for entry" in message
    assert cinema["name"] in message and cinema["area"] in message
    with psycopg.connect(database_url) as conn:
        sms, code = conn.execute("""SELECT sm.body, cl.code FROM bookings b JOIN sms_messages sm ON sm.booking_id = b.id
                                   JOIN chat_links cl ON cl.booking_id = b.id WHERE b.booking_ref = %s""", (ref,)).fetchone()
    assert "DEMO" in sms and len(sms) <= 160 and cinema["area"] in sms
    assert cinema["name"][:8] in sms
    chat = client.get(f"/chat-links/{code}").json()
    assert chat["cinema_name"] == cinema["name"] and chat["cinema_address"] == cinema["address"]
    # Hold fields are available before checkout as well.
    response = client.post(f"/shows/{show['id']}/holds", json={"seat_ids": [show["seats"][1]]})
    held = response.json()
    assert held["cinema_name"] == cinema["name"] and held["cinema_area"] == cinema["area"]
    assert client.get(f"/holds/{held['hold_id']}").json()["cinema_address"] == cinema["address"]


def test_009_legacy_booking_survives(isolated_schema):
    conn = isolated_schema
    root = Path(__file__).resolve().parents[2]
    conn.execute((root / "db/schema.sql").read_text().split("-- 009_cinemas")[0])
    screen = conn.execute("INSERT INTO screens (name,total_rows,seats_per_row) VALUES ('Screen 1',8,12) RETURNING id").fetchone()[0]
    movie = conn.execute("INSERT INTO movies (title,duration_minutes,language,certificate) VALUES ('Legacy',120,'Hindi','U') RETURNING id").fetchone()[0]
    show = conn.execute("INSERT INTO shows (movie_id,screen_id,start_time,regular_price,premium_price) VALUES (%s,%s,now()+interval '1 day',200,300) RETURNING id", (movie,screen)).fetchone()[0]
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Legacy Person','legacy@example.com') RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,status,total_amount) VALUES ('LEGACY',%s,%s,'CONFIRMED',200)", (customer,show))
    conn.execute((root / "db/migrations/009_cinemas.sql").read_text())
    assert conn.execute("SELECT cinema_id IS NOT NULL FROM screens").fetchone() == (True,)
    conn.row_factory = dict_row
    from app.routers.bookings import _booking_details
    booking = _booking_details("LEGACY", conn)
    assert booking["cinema_name"] == "CineBook Demo Cinema" and booking["movie_title"] == "Legacy"
    assert booking["full_name"] == "Legacy Person"
    assert not conn.execute("SELECT is_active FROM cinemas").fetchone()["is_active"]
    conn.row_factory = tuple_row
