from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.cinema_queries import day_bounds, local_show_rows, show_select
from app.config import settings
from app.db import get_connection
from app.models import Cinema, ShowSummary

router = APIRouter(prefix="/cinemas", tags=["cinemas"])
_SELECT = """SELECT ci.id, ci.name, ci.chain, ci.area, ci.address, ci.latitude, ci.longitude, ci.location_precision,
                    count(sc.id) AS screens_count,
                    COALESCE(array_agg(DISTINCT sc.format ORDER BY sc.format) FILTER (WHERE sc.id IS NOT NULL), '{}') AS formats
             FROM cinemas ci LEFT JOIN screens sc ON sc.cinema_id = ci.id"""


@router.get("", response_model=list[Cinema])
def list_cinemas(area: str | None = None, chain: str | None = None, movie_id: int | None = None,
                 show_date: date | None = Query(default=None, alias="date"), connection: Connection = Depends(get_connection)):
    where, params = ["ci.is_active"], []
    for column, value in (("area", area), ("chain", chain)):
        if value is not None:
            where.append(f"lower(ci.{column}) = lower(%s)")
            params.append(value)
    if movie_id is not None or show_date is not None:
        terms = ["s.screen_id = screen.id", "s.status = 'SCHEDULED'", "s.start_time > now()", "m.is_active"]
        if movie_id is not None:
            terms.append("s.movie_id = %s")
            params.append(movie_id)
        if show_date:
            terms.extend(["s.start_time >= %s", "s.start_time < %s"])
            params.extend(day_bounds(show_date))
        where.append("""EXISTS (SELECT 1 FROM screens screen JOIN shows s ON s.screen_id = screen.id
                         JOIN movies m ON m.id = s.movie_id WHERE screen.cinema_id = ci.id AND """ + " AND ".join(terms) + ")")
    with connection.cursor() as cursor:
        cursor.execute(_SELECT + " WHERE " + " AND ".join(where) + ' GROUP BY ci.id ORDER BY ci.name COLLATE "C", ci.id', params)
        return cursor.fetchall()


@router.get("/areas", response_model=list[str])
def cinema_areas(connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute('SELECT DISTINCT area COLLATE "C" AS area FROM cinemas WHERE is_active ORDER BY area')
        return [r["area"] for r in cursor.fetchall()]


def require_cinema(cursor, cinema_id):
    cursor.execute(_SELECT + " WHERE ci.id = %s AND ci.is_active GROUP BY ci.id", (cinema_id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Cinema {cinema_id} not found")
    return row


@router.get("/{cinema_id}", response_model=Cinema)
def get_cinema(cinema_id: int, connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        return require_cinema(cursor, cinema_id)


@router.get("/{cinema_id}/shows", response_model=list[ShowSummary])
def cinema_shows(cinema_id: int, show_date: date | None = Query(default=None, alias="date"),
                  connection: Connection = Depends(get_connection)):
    day = show_date or datetime.now(ZoneInfo(settings.app_timezone)).date()
    with connection.cursor() as cursor:
        require_cinema(cursor, cinema_id)
        cursor.execute(show_select() + """ WHERE ci.id = %s AND s.status = 'SCHEDULED'
                          AND s.start_time >= %s AND s.start_time < %s ORDER BY s.start_time, s.id""",
                       (cinema_id, *day_bounds(day)))
        return local_show_rows(cursor.fetchall())
