from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.cinema_queries import day_bounds, local_show_rows, show_select
from app.config import settings
from app.db import get_connection
from app.models import Movie, ShowSummary

router = APIRouter(prefix="/movies", tags=["movies"])
_SELECT = """SELECT m.id, m.title, m.description, m.duration_minutes, m.language, m.certificate,
                    m.poster_url, m.genres, m.backdrop_url, m.trailer_url, m.release_date,
                    times.cinemas_count, times.next_show_at
             FROM movies m LEFT JOIN LATERAL (
                 SELECT count(DISTINCT ci.id) AS cinemas_count, min(s.start_time) AS next_show_at
                 FROM shows s JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                 WHERE s.movie_id = m.id AND ci.is_active AND s.status = 'SCHEDULED' AND s.start_time > now()
             ) times ON TRUE"""


def _local_movies(rows):
    for row in rows:
        if row["next_show_at"]:
            row["next_show_at"] = row["next_show_at"].astimezone(ZoneInfo(settings.app_timezone))
    return rows


@router.get("", response_model=list[Movie])
def list_movies(language: str | None = None, q: str | None = None, showing: bool = False,
                 connection: Connection = Depends(get_connection)):
    where, params = ["m.is_active"], []
    if language is not None:
        where.append("lower(m.language) = lower(%s)")
        params.append(language)
    if q is not None:
        # strpos treats user '%' and '_' as literal title characters.
        where.append("strpos(lower(m.title), lower(%s)) > 0")
        params.append(q)
    if showing:
        where.append("times.cinemas_count > 0")
    with connection.cursor() as cursor:
        cursor.execute(_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY m.title", params)
        return _local_movies(cursor.fetchall())


def _require_movie(cursor, movie_id):
    cursor.execute("SELECT id FROM movies WHERE id = %s", (movie_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Movie {movie_id} not found")


@router.get("/{movie_id}/shows", response_model=list[ShowSummary])
def list_movie_shows(movie_id: int, show_date: date | None = Query(default=None, alias="date"),
                     cinema_id: int | None = None, connection: Connection = Depends(get_connection)):
    where = ["s.movie_id = %s", "s.status = 'SCHEDULED'", "s.start_time > now()", "ci.is_active"]
    params = [movie_id]
    if show_date:
        where.extend(["s.start_time >= %s", "s.start_time < %s"])
        params.extend(day_bounds(show_date))
    if cinema_id is not None:
        where.append("ci.id = %s")
        params.append(cinema_id)
    with connection.cursor() as cursor:
        _require_movie(cursor, movie_id)
        cursor.execute(show_select() + " WHERE " + " AND ".join(where) + " ORDER BY ci.name, s.start_time, s.id", params)
        return local_show_rows(cursor.fetchall())


@router.get("/{movie_id}/show-dates", response_model=list[str])
def movie_show_dates(movie_id: int, connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        _require_movie(cursor, movie_id)
        cursor.execute("""SELECT DISTINCT (s.start_time AT TIME ZONE %s)::date AS day
                          FROM shows s JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                          WHERE s.movie_id = %s AND ci.is_active AND s.status = 'SCHEDULED' AND s.start_time > now()
                          ORDER BY day""", (settings.app_timezone, movie_id))
        return [row["day"].isoformat() for row in cursor.fetchall()]


@router.get("/{movie_id}", response_model=Movie)
def get_movie(movie_id: int, connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute(_SELECT + " WHERE m.id = %s AND m.is_active", (movie_id,))
        rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Movie {movie_id} not found")
    return _local_movies(rows)[0]
