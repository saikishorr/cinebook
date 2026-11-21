"""Phase 2: the page a customer reaches from the link in their SMS.

GET /chat-links/{code} returns a short summary of the booking behind the link.
Links never expire; a single link can be switched off by setting chat_links.revoked_at.
"""
import re
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Connection

from app.config import settings
from app.db import get_connection
from app.cinema_queries import CINEMA_FIELDS
from app.models import ChatLinkSummary
from app.ratelimit import SlidingWindowLimiter, client_key

router = APIRouter(prefix="/chat-links", tags=["chat links"])

_CODE = re.compile(r"[A-Za-z0-9]{10}")
# 60 look-ups a minute per visitor is plenty for a person and slows down anyone guessing codes.
limiter = SlidingWindowLimiter(limit=60, window_seconds=60)


@router.get("/{code}", response_model=ChatLinkSummary)
def read_chat_link(code: str, request: Request, connection: Connection = Depends(get_connection)):
    if not limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    if not _CODE.fullmatch(code):
        raise HTTPException(status_code=404, detail="This chat link is not valid")

    with connection.transaction():
        with connection.cursor() as cursor:
            # Count the visit and fetch the link in one statement; revoked links are not counted.
            cursor.execute("""UPDATE chat_links SET open_count = open_count + 1, last_opened_at = now()
                              WHERE code = %s AND revoked_at IS NULL
                              RETURNING booking_id""", (code,))
            link = cursor.fetchone()
            if link is None:
                cursor.execute("SELECT 1 FROM chat_links WHERE code = %s", (code,))
                if cursor.fetchone():
                    raise HTTPException(status_code=410, detail="This chat link has been switched off")
                raise HTTPException(status_code=404, detail="This chat link is not valid")

            cursor.execute(f"""SELECT {CINEMA_FIELDS}, b.booking_ref, b.status, b.total_amount, COALESCE(b.customer_name, c.full_name) AS full_name,
                                     m.title AS movie_title, m.language AS movie_language,
                                     sc.name AS screen_name, s.start_time
                              FROM bookings AS b JOIN customers AS c ON c.id = b.customer_id
                              JOIN shows AS s ON s.id = b.show_id JOIN movies AS m ON m.id = s.movie_id
                              JOIN screens AS sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                              WHERE b.id = %s""", (link["booking_id"],))
            booking = cursor.fetchone()
            cursor.execute("""SELECT seat.row_label || seat.seat_number AS label
                              FROM booking_seats AS bs JOIN seats AS seat ON seat.id = bs.seat_id
                              WHERE bs.booking_id = %s ORDER BY seat.row_label, seat.seat_number""",
                           (link["booking_id"],))
            seats = [row["label"] for row in cursor.fetchall()]

    return {
        "cinema_name": booking["cinema_name"],
        "cinema_area": booking["cinema_area"],
        "cinema_address": booking["cinema_address"],
        "code": code,
        "booking_ref": booking["booking_ref"],
        "status": booking["status"],
        "first_name": booking["full_name"].split()[0],
        "movie_title": booking["movie_title"],
        "movie_language": booking["movie_language"],
        "screen_name": booking["screen_name"],
        "start_time": booking["start_time"].astimezone(ZoneInfo(settings.app_timezone)),
        "seats": seats,
        "total_amount": booking["total_amount"],
    }
