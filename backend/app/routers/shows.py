from datetime import date, datetime, time, timedelta, timezone
import logging
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from app.config import settings
from app.cinema_queries import show_select
from app.db import get_connection
from app.models import SeatMap, ShowDetails, ShowSummary
from app.holds import get_hold_store
from app.holds.base import StoreUnavailable
from app.pricing import seat_price_sql

router = APIRouter(prefix="/shows", tags=["shows"])
logger = logging.getLogger(__name__)

@router.get("", response_model=list[ShowSummary])
def list_shows_on_date(show_date: date = Query(alias="date"), connection: Connection = Depends(get_connection)):
    # Turn the requested local calendar date into a timezone-aware half-open range.
    zone = ZoneInfo(settings.app_timezone)
    start = datetime.combine(show_date, time.min, tzinfo=zone)
    end = datetime.combine(show_date + timedelta(days=1), time.min, tzinfo=zone)
    with connection.cursor() as cursor:
        cursor.execute(show_select() + """ WHERE ci.is_active AND s.status = 'SCHEDULED'
                          AND s.start_time >= %s AND s.start_time < %s ORDER BY s.start_time, s.id""", (start, end))
        rows = cursor.fetchall()
        for row in rows:
            row["start_time"] = row["start_time"].astimezone(zone)
        return rows

@router.get("/{show_id}", response_model=ShowDetails)
def get_show(show_id: int, connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute(show_select(details=True) + " WHERE s.id = %s", (show_id,))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Show {show_id} not found")
        row["start_time"] = row["start_time"].astimezone(ZoneInfo(settings.app_timezone))
        return row

@router.get("/{show_id}/seats", response_model=SeatMap)
def get_show_seats(show_id: int, connection: Connection = Depends(get_connection)):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT s.*, sc.layout_name, sc.total_rows, sc.seats_per_row, sc.section_names
                          FROM shows s JOIN screens sc ON sc.id = s.screen_id WHERE s.id = %s""", (show_id,))
        show = cursor.fetchone()
        if show is None:
            raise HTTPException(status_code=404, detail=f"Show {show_id} not found")
        if show["start_time"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="This show has already started")
        # A pending or confirmed booking marks its seat as booked for this show.
        cursor.execute(f"""SELECT seat.id, seat.row_label, seat.seat_number, seat.seat_type,
                                 seat.row_index, seat.col, seat.accessible, {seat_price_sql()} AS price,
                                 CASE WHEN EXISTS (
                                     SELECT 1 FROM booking_seats AS bs
                                     JOIN bookings AS b ON b.id = bs.booking_id
                                     WHERE bs.show_id = s.id AND bs.seat_id = seat.id
                                       AND b.status IN ('PENDING', 'CONFIRMED')
                                 ) THEN 'BOOKED' ELSE 'AVAILABLE' END AS status
                          FROM seats AS seat JOIN shows s ON s.screen_id = seat.screen_id WHERE s.id = %s
                          ORDER BY seat.row_index NULLS LAST, seat.row_label, seat.seat_number""", (show_id,))
        seats = cursor.fetchall()
    # DynamoDB's TTL cleanup is delayed, so ignore rows whose expiry has passed here.
    try:
        held_seats = get_hold_store().held_seat_ids(show_id)
    except StoreUnavailable as error:
        logger.warning("Could not read seat holds for show %s; using PostgreSQL only: %s", show_id, error)
        held_seats = set()
    for seat in seats:
        # A confirmed or pending booking always takes precedence over a temporary hold.
        if seat["status"] != "BOOKED" and seat["id"] in held_seats:
            seat["status"] = "HELD"
    booked = sum(seat["status"] == "BOOKED" for seat in seats)
    held = sum(seat["status"] == "HELD" for seat in seats)
    section_rows = {}
    for index, seat in enumerate(seats):
        group = section_rows.setdefault(seat["seat_type"], {"labels": [], "back": 0, "price": seat["price"]})
        if seat["row_label"] not in group["labels"]:
            group["labels"].append(seat["row_label"])
        group["back"] = index
    codes = {"REGULAR": "R", "PREMIUM": "P", "RECLINER": "L"}
    sections = [{"name": show["section_names"][codes[kind]], "seat_type": kind,
                 "price": group["price"], "row_labels": group["labels"]}
                for kind, group in sorted(section_rows.items(), key=lambda item: -item[1]["back"])]
    grid = {"rows": show["total_rows"], "cols": show["seats_per_row"]} if show["layout_name"] else None
    return SeatMap(show_id=show_id, seats=seats, layout_name=show["layout_name"], grid=grid, sections=sections,
                   available_count=len(seats) - booked - held,
                   held_count=held, booked_count=booked)
