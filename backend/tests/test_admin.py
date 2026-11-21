"""Admin requests run against an isolated schema, with no network or real-account changes."""
import base64
import hashlib
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from psycopg.rows import dict_row, tuple_row

from app.admin_auth import hash_password, verify_password
from app.config import settings
from app.db import get_connection
from app.main import app
from app.routers import admin as routes
from app.scheduling import schedule_shows
from tests.test_cinema_import import importer
from tests.test_migrations import isolated_schema as isolated_schema

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Offline test password 123"


@pytest.fixture
def admin_env(client, isolated_schema):
    conn = isolated_schema
    conn.row_factory = dict_row
    conn.execute((ROOT / "db/schema.sql").read_text())
    importer.import_curated(conn, importer.load_curated()[:2], schedule=False)
    movie_ids = []
    for index, language in enumerate(("Hindi", "Marathi", "English")):
        movie_ids.append(conn.execute("INSERT INTO movies (title,language,certificate,duration_minutes) VALUES (%s,%s,'U',120) RETURNING id",
                                      (f"Admin Film {index}",language)).fetchone()["id"])
    conn.execute("INSERT INTO movies (title,language,certificate,duration_minutes,is_active) VALUES ('Monsoon Junction','Hindi','U',120,FALSE)")
    schedule_shows(conn)
    user_id = conn.execute("INSERT INTO admin_users (username,password_hash) VALUES ('trainer',%s) RETURNING id", (hash_password(PASSWORD),)).fetchone()["id"]
    def connection_override():
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
    app.dependency_overrides[get_connection] = connection_override
    try:
        response = client.post("/admin/login", json={"username":"trainer","password":PASSWORD})
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        yield {"connection":conn,"headers":{"Authorization":"Bearer " + token},"token":token,"movies":movie_ids,"user_id":user_id}
    finally:
        app.dependency_overrides.pop(get_connection, None)
        conn.row_factory = tuple_row


def test_scrypt_format_random_salts_and_verification():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first.startswith("scrypt$16384$8$1$") and first != second
    assert verify_password(PASSWORD,first) and not verify_password("wrong",first)
    assert not verify_password(PASSWORD,"old/plain/hash")
    assert not verify_password(PASSWORD,"scrypt$999999999$8$1$00$00")


def test_login_hash_only_ttl_no_cache_logout(client, admin_env):
    env = admin_env
    assert len(base64.urlsafe_b64decode(env["token"] + "=")) == 32
    row = env["connection"].execute("SELECT * FROM admin_sessions").fetchone()
    assert row["token_hash"] == hashlib.sha256(env["token"].encode()).hexdigest()
    assert env["token"] not in str(row)
    assert 43180 <= (row["expires_at"] - datetime.now(timezone.utc)).total_seconds() <= 43200
    response = client.get("/admin/movies", headers=env["headers"])
    assert response.headers["cache-control"] == "no-store"
    result = client.post("/admin/logout",headers=env["headers"])
    assert result.status_code == 204 and not result.content
    assert result.headers["cache-control"] == "no-store"
    assert not env["connection"].execute("SELECT 1 FROM admin_sessions").fetchone()
    assert client.get("/admin/movies",headers=env["headers"]).json() == {"detail":"Please sign in again"}


def test_auth_every_endpoint_expiry_and_wrong_credentials(client, admin_env):
    for method,path,body in [("get","/admin/movies",None),("get","/admin/movies/export",None),
        ("get","/admin/tmdb/search?q=Film",None),("post","/admin/logout",None),
        ("patch","/admin/movies/1",{"is_active":True}),
        ("post","/admin/movies",{"title":"Film","language":"Hindi","certificate":"U"})]:
        response = getattr(client,method)(path,**({"json":body} if body else {}))
        assert response.status_code == 401 and response.json() == {"detail":"Please sign in again"}
        assert response.headers["cache-control"] == "no-store"
    conn = admin_env["connection"]
    conn.execute("UPDATE admin_sessions SET expires_at = now() - interval '1 second'")
    response = client.get("/admin/movies",headers=admin_env["headers"])
    assert response.status_code == 401 and response.json() == {"detail":"Please sign in again"}
    for username in ("trainer","unknown"):
        response = client.post("/admin/login",json={"username":username,"password":"wrong"})
        assert response.status_code == 401 and response.json() == {"detail":"Wrong username or password"}
        assert response.headers["cache-control"] == "no-store"


def test_login_failure_limiter_and_success_does_not_consume_failures(client, admin_env):
    routes.login_failures.reset()
    response = client.post("/admin/login",json={"username":"trainer","password":PASSWORD})
    assert response.status_code == 200
    for _ in range(10):
        assert client.post("/admin/login",json={"username":"trainer","password":"bad"}).status_code == 401
    assert client.post("/admin/login",json={"username":"trainer","password":PASSWORD}).status_code == 429


def test_admin_list_deactivate_keeps_booking_and_hold_activate_schedules(client, admin_env, caplog):
    env, conn = admin_env, admin_env["connection"]
    movie = env["movies"][0]
    old = conn.execute("SELECT * FROM shows WHERE movie_id = %s AND start_time > now() ORDER BY id LIMIT 2", (movie,)).fetchall()
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Protected','protected@example.com') RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('KEEPME',%s,%s,200)", (customer,old[0]["id"]))
    seat = conn.execute("SELECT id FROM seats WHERE screen_id = %s LIMIT 1", (old[1]["screen_id"],)).fetchone()["id"]
    conn.execute("INSERT INTO seat_holds (hold_id,show_id,seat_ids,expires_at) VALUES ('keep',%s,%s,now()+interval '5 minutes')", (old[1]["id"],[seat]))
    with caplog.at_level(logging.INFO):
        response = client.patch(f"/admin/movies/{movie}",json={"is_active":False},headers=env["headers"])
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert conn.execute("SELECT count(*) AS n FROM shows WHERE movie_id = %s AND start_time > now()", (movie,)).fetchone()["n"] == 2
    assert conn.execute("SELECT * FROM shows WHERE id = %s", (old[0]["id"],)).fetchone() == old[0]
    assert any("trainer" in r.message and f"movie_id={movie}" in r.message for r in caplog.records)
    assert PASSWORD not in caplog.text and env["token"] not in caplog.text
    listed = client.get("/admin/movies",headers=env["headers"]).json()
    assert len(listed) == 3 and listed[-1]["id"] == movie
    assert all("cinemas_count" in r and "upcoming_shows" in r and "tmdb_id" in r for r in listed)
    response = client.patch(f"/admin/movies/{movie}",json={"is_active":True},headers=env["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] and response.json()["upcoming_shows"] >= 14
    assert client.patch("/admin/movies/9999999",json={"is_active":True},headers=env["headers"]).status_code == 404


def test_add_manual_film_full_programme_export_and_no_duplicates(client, admin_env):
    env, conn = admin_env, admin_env["connection"]
    counts_before = {r["movie_id"]:r["n"] for r in conn.execute("SELECT movie_id,count(*) AS n FROM shows GROUP BY movie_id")}
    body = {"tmdb_id":None,"title":"New Marathi Film","language":"Marathi","certificate":"UA"}
    response = client.post("/admin/movies",json=body,headers=env["headers"])
    assert response.status_code == 201, response.text
    movie = response.json()
    assert movie["is_active"] and movie["poster_url"] is None and movie["tmdb_id"] is None
    assert movie["upcoming_shows"] >= 14
    overlaps = conn.execute("""WITH ordered AS (
        SELECT s.start_time, lag(s.start_time + (m.duration_minutes+20)*interval '1 minute')
        OVER (PARTITION BY s.screen_id ORDER BY s.start_time) AS previous_end
        FROM shows s JOIN movies m ON m.id=s.movie_id)
        SELECT count(*) AS n FROM ordered WHERE start_time < previous_end""").fetchone()["n"]
    assert overlaps == 0
    for film in env["movies"]:
        assert conn.execute("SELECT count(*) AS n FROM shows WHERE movie_id = %s", (film,)).fetchone()["n"] >= 14
    assert any(conn.execute("SELECT count(*) AS n FROM shows WHERE movie_id = %s", (film,)).fetchone()["n"] < counts_before[film] for film in env["movies"])
    again = client.post("/admin/movies",json=body,headers=env["headers"])
    assert again.status_code == 201 and again.json()["id"] == movie["id"]
    exported = client.get("/admin/movies/export",headers=env["headers"])
    assert exported.headers["cache-control"] == "no-store"
    data = exported.json()
    assert {"_readme","researched_on","films","left_out"} == set(data)
    manual = next(f for f in data["films"] if f["title"] == body["title"])
    assert manual["tmdb"] is False and manual["duration_minutes"] == 140
    assert not any(f["title"] == "Monsoon Junction" for f in data["films"])


def test_tmdb_search_missing_key_fake_details_and_limit(client, admin_env, monkeypatch):
    env = admin_env
    monkeypatch.setattr(settings,"tmdb_api_key","")
    for path, method, body in (("/admin/tmdb/search?q=Film","get",None),
        ("/admin/movies","post",{"tmdb_id":987,"title":"Dubbed film","language":"Hindi","certificate":"UA"})):
        response = getattr(client,method)(path,headers=env["headers"],**({"json":body} if body else {}))
        assert response.status_code == 503 and response.json() == {"detail":"TMDB_API_KEY is not set on the server"}
    monkeypatch.setattr(settings,"tmdb_api_key","SERVER-ONLY-KEY")
    calls = []
    def get(self,path,**params):
        calls.append(path)
        if path == "/search/movie":
            return {"results":[{"id":i,"title":f"Film {i}","original_language":"hi","release_date":"2026-11-20","poster_path":"/poster.jpg"} for i in range(12)]}
        assert path == "/movie/987"
        return {"id":987,"title":"Remote name","original_language":"en","runtime":142,"overview":"Remote plot", "poster_path":"/poster.jpg", "genres":[{"name":"Drama"}],"release_date":"2026-11-20"}
    monkeypatch.setattr(routes.tmdb.Tmdb,"get",get)
    response = client.get("/admin/tmdb/search?q=Film",headers=env["headers"])
    assert response.status_code == 200 and len(response.json()) == 10
    assert set(response.json()[0]) == {"tmdb_id","title","original_language","release_date","poster_url"}
    assert "SERVER-ONLY-KEY" not in response.text
    response = client.post("/admin/movies",json={"tmdb_id":987,"title":"Dubbed film","language":"Hindi","certificate":"UA"},headers=env["headers"])
    assert response.status_code == 201, response.text
    assert response.json()["duration_minutes"] == 142 and response.json()["genres"] == ["Drama"]
    assert response.json()["poster_url"].endswith("/poster.jpg") and response.json()["language"] == "Hindi"
    assert response.json()["upcoming_shows"] >= 14 and "/movie/987" in calls


def test_create_admin_password_reset_revokes_sessions(admin_env):
    spec = importlib.util.spec_from_file_location("create_admin_test", ROOT / "scripts/create_admin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    conn = admin_env["connection"]
    module.create_admin(conn,"trainer","New hidden password 456")
    assert not conn.execute("SELECT 1 FROM admin_sessions").fetchone()
    stored = conn.execute("SELECT password_hash FROM admin_users WHERE username = 'trainer'").fetchone()["password_hash"]
    assert verify_password("New hidden password 456",stored) and not verify_password(PASSWORD,stored)
