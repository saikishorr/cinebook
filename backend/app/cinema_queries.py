"""Shared additive cinema fields and local calendar bounds."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.availability import availability_columns
from app.config import settings

SHOW_JOINS = """FROM shows s JOIN screens sc ON sc.id = s.screen_id
                JOIN cinemas ci ON ci.id = sc.cinema_id JOIN movies m ON m.id = s.movie_id"""
CINEMA_FIELDS = "ci.name AS cinema_name, ci.area AS cinema_area, ci.address AS cinema_address"


def show_select(details=False):
    detail = ", ci.address AS cinema_address, ci.latitude AS cinema_latitude, ci.longitude AS cinema_longitude" if details else ""
    return f"""SELECT {availability_columns()}, s.id, s.movie_id, s.screen_id, s.start_time,
                      s.regular_price, s.premium_price, s.recliner_price, s.status, sc.name AS screen_name,
                      m.title AS movie_title, m.language AS movie_language, m.duration_minutes,
                      ci.id AS cinema_id, ci.name AS cinema_name, ci.area AS cinema_area,
                      ci.chain AS cinema_chain, sc.format AS screen_format {detail} {SHOW_JOINS}"""


def day_bounds(day):
    zone = ZoneInfo(settings.app_timezone)
    return datetime.combine(day, time.min, zone), datetime.combine(day + timedelta(days=1), time.min, zone)


def local_show_rows(rows):
    zone = ZoneInfo(settings.app_timezone)
    for row in rows:
        row["start_time"] = row["start_time"].astimezone(zone)
    return rows


def cinema_for_show(cursor, show_id):
    cursor.execute(f"SELECT {CINEMA_FIELDS} {SHOW_JOINS} WHERE s.id = %s", (show_id,))
    return cursor.fetchone()
