"""Authenticated live film selection; the chat assistant has no access to these operations."""
import logging
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from psycopg import Connection
from pydantic import BaseModel, Field

from app import tmdb
from app import audit
from app.admin_auth import new_session, require_admin, require_permission, verify_password
from app.permissions import ROLE_LABELS, permissions_for
from app.config import settings
from app.db import get_connection
from app.models import Movie
from app.ratelimit import SlidingWindowLimiter, client_key
from app.routers.movies import _SELECT, _local_movies
from app.scheduling import schedule_shows

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["film admin"])
login_failures = SlidingWindowLimiter(10, 15 * 60)
SAMPLE_TITLES = ["Monsoon Junction", "The Last Signal", "Chandni Chowk Express"]


class LoginRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    username: str
    full_name: str | None = None
    role: str = "SUPER_ADMIN"
    role_label: str = "Super admin"
    permissions: list[str] = []


class AdminMovie(Movie):
    is_active: bool
    tmdb_id: int | None
    upcoming_shows: int


class MovieActivation(BaseModel):
    is_active: bool


class AddMovie(BaseModel):
    tmdb_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=300)
    language: str = Field(min_length=1, max_length=80)
    certificate: Literal["U", "UA", "A"]


class TmdbSearchResult(BaseModel):
    tmdb_id: int
    title: str
    original_language: str
    release_date: str | None
    poster_url: str | None


def _admin_select():
    return _SELECT.replace("SELECT m.id,", """SELECT m.is_active, m.tmdb_id,
        (SELECT count(*) FROM shows s JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
         WHERE s.movie_id = m.id AND ci.is_active AND s.status = 'SCHEDULED' AND s.start_time > now()) AS upcoming_shows, m.id,""", 1)


def _movie(connection, movie_id):
    with connection.cursor() as cursor:
        cursor.execute(_admin_select() + " WHERE m.id = %s AND NOT (m.title = ANY(%s))", (movie_id, SAMPLE_TITLES))
        rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Movie {movie_id} not found")
    return _local_movies(rows)[0]


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, connection: Connection = Depends(get_connection)):
    key = client_key(request)
    if login_failures.blocked(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again in 15 minutes.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, username, password_hash, role, full_name, is_active FROM admin_users WHERE username = %s",
                       (body.username,))
        admin = cursor.fetchone()
    valid = verify_password(body.password, admin["password_hash"] if admin else "")
    # A disabled account gets the same answer as a wrong password, so it reveals nothing.
    if not admin or not valid or not admin["is_active"]:
        login_failures.record(key)
        logger.info("Admin login failed username=%r movie_id=-", body.username)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token, expires = new_session(connection, admin["id"])
    connection.execute("UPDATE admin_users SET last_login_at = now() WHERE id = %s", (admin["id"],))
    connection.commit()
    logger.info("Admin login username=%r movie_id=-", admin["username"])
    return {"token": token, "expires_at": expires.astimezone(ZoneInfo(settings.app_timezone)), "username": admin["username"],
            "full_name": admin["full_name"], "role": admin["role"], "role_label": ROLE_LABELS[admin["role"]],
            "permissions": permissions_for(admin["role"])}


@router.post("/logout", status_code=204)
def logout(admin=Depends(require_admin), connection: Connection = Depends(get_connection)):
    connection.execute("DELETE FROM admin_sessions WHERE token_hash = %s", (admin["token_hash"],))
    connection.commit()
    logger.info("Admin logout username=%r movie_id=-", admin["username"])
    return Response(status_code=204)


@router.get("/movies", response_model=list[AdminMovie])
def list_movies(admin=Depends(require_permission("films.manage")), connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute(_admin_select() + ' WHERE NOT (m.title = ANY(%s)) ORDER BY m.is_active DESC, m.title COLLATE "C", m.id', (SAMPLE_TITLES,))
        rows = cursor.fetchall()
    logger.info("Admin movies listed username=%r movie_id=*", admin["username"])
    return _local_movies(rows)


@router.get("/movies/export")
def export_movies(admin=Depends(require_permission("films.manage")), connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT title, language, certificate, tmdb_id, duration_minutes FROM movies
                          WHERE is_active AND NOT (title = ANY(%s)) ORDER BY title""", (SAMPLE_TITLES,))
        rows = cursor.fetchall()
    films = []
    for row in rows:
        entry = {key: row[key] for key in ("title", "language", "certificate")}
        if row["tmdb_id"] is not None:
            entry["tmdb_id"] = row["tmdb_id"]
        else:
            entry.update(tmdb=False, duration_minutes=row["duration_minutes"])
        films.append(entry)
    logger.info("Admin movies exported username=%r movie_id=*", admin["username"])
    return {"_readme": "Exported live CineBook film selections. Importing this file fully refreshes live selection.",
            "researched_on": datetime.now(ZoneInfo(settings.app_timezone)).date().isoformat(), "films": films, "left_out": []}


@router.patch("/movies/{movie_id}", response_model=AdminMovie)
def activate_movie(movie_id: int, body: MovieActivation, admin=Depends(require_permission("films.manage")), connection: Connection = Depends(get_connection)):
    logger.info("Admin movie activation requested username=%r movie_id=%s", admin["username"], movie_id)
    _movie(connection, movie_id)
    try:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(641902109)")
            connection.execute("UPDATE movies SET is_active = %s WHERE id = %s", (body.is_active, movie_id))
            audit.record(connection, admin, "film.activate" if body.is_active else "film.deactivate", "movie", movie_id)
            if body.is_active:
                schedule_shows(connection, movie_ids=[movie_id])
            else:
                schedule_shows(connection)
        connection.commit()
    except ValueError as error:
        connection.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None
    logger.info("Admin movie activation username=%r movie_id=%s is_active=%s", admin["username"], movie_id, body.is_active)
    return _movie(connection, movie_id)


def _tmdb_client():
    if not settings.tmdb_api_key.strip() or settings.tmdb_api_key == "CHANGE_ME":
        raise HTTPException(status_code=503, detail="TMDB_API_KEY is not set on the server")
    return tmdb.Tmdb(settings.tmdb_api_key)


@router.get("/tmdb/search", response_model=list[TmdbSearchResult])
def search_tmdb(q: str = Query(min_length=1, max_length=200), admin=Depends(require_permission("films.manage"))):
    logger.info("Admin TMDB search requested username=%r movie_id=-", admin["username"])
    client = _tmdb_client()
    try:
        results = client.get("/search/movie", query=q, language="en-IN", include_adult="false").get("results", [])
    except (SystemExit, OSError, ValueError):
        raise HTTPException(status_code=502, detail="TMDB service is unavailable") from None
    logger.info("Admin TMDB search username=%r movie_id=-", admin["username"])
    return [{"tmdb_id": r["id"], "title": r.get("title", ""), "original_language": r.get("original_language", ""),
             "release_date": r.get("release_date") or None,
             "poster_url": f"{tmdb.IMAGES}/w500{r['poster_path']}" if r.get("poster_path") else None} for r in results[:10]]


@router.post("/movies", response_model=AdminMovie, status_code=201)
def add_movie(body: AddMovie, admin=Depends(require_permission("films.manage")), connection: Connection = Depends(get_connection)):
    logger.info("Admin movie add requested username=%r movie_id=-", admin["username"])
    values = {"description": None, "duration_minutes": tmdb.DEFAULT_RUNTIME, "poster_url": None,
              "backdrop_url": None, "trailer_url": None, "genres": [], "release_date": None}
    if body.tmdb_id is not None:
        client = _tmdb_client()
        try:
            values.update(tmdb.details(client, {"id": body.tmdb_id}))
        except (SystemExit, OSError, ValueError, KeyError):
            raise HTTPException(status_code=502, detail="TMDB service is unavailable") from None
    values.update(body.model_dump())
    if not body.title.strip() or not body.language.strip() or body.title in SAMPLE_TITLES:
        raise HTTPException(status_code=422, detail="Enter a non-sample movie title and language")
    try:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(641902109)")
            with connection.cursor() as cursor:
                cursor.execute("""SELECT id FROM movies WHERE (tmdb_id = %s AND %s::bigint IS NOT NULL)
                                  OR (tmdb_id IS NULL AND %s::bigint IS NULL AND lower(title) = lower(%s)) LIMIT 1""",
                               (body.tmdb_id, body.tmdb_id, body.tmdb_id, body.title))
                existing = cursor.fetchone()
                if existing:
                    if body.tmdb_id is not None:
                        cursor.execute("""UPDATE movies SET is_active = TRUE, title = %(title)s, language = %(language)s,
                                          certificate = %(certificate)s, description = %(description)s, duration_minutes = %(duration_minutes)s,
                                          poster_url = %(poster_url)s, backdrop_url = %(backdrop_url)s, trailer_url = %(trailer_url)s,
                                          genres = %(genres)s, release_date = %(release_date)s WHERE id = %(id)s RETURNING id""",
                                       {**values, "id": existing["id"]})
                    else:
                        cursor.execute("""UPDATE movies SET is_active = TRUE, title = %(title)s, language = %(language)s,
                                          certificate = %(certificate)s WHERE id = %(id)s RETURNING id""", {**values, "id": existing["id"]})
                else:
                    cursor.execute("""INSERT INTO movies (tmdb_id,title,language,certificate,description,duration_minutes,
                                      poster_url,backdrop_url,trailer_url,genres,release_date,is_active)
                                      VALUES (%(tmdb_id)s,%(title)s,%(language)s,%(certificate)s,%(description)s,%(duration_minutes)s,
                                      %(poster_url)s,%(backdrop_url)s,%(trailer_url)s,%(genres)s,%(release_date)s,TRUE) RETURNING id""", values)
                movie_id = cursor.fetchone()["id"]
            audit.record(connection, admin, "film.add", "movie", movie_id, title=body.title, tmdb_id=body.tmdb_id)
            schedule_shows(connection, movie_ids=[movie_id])
        connection.commit()
    except ValueError as error:
        connection.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None
    logger.info("Admin movie added username=%r movie_id=%s", admin["username"], movie_id)
    return _movie(connection, movie_id)
