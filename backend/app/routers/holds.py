from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg import Connection
from app.config import settings
from app.user_auth import booking_user
from app.db import get_connection
from app.cinema_queries import cinema_for_show
from app.models import CreateHoldRequest, HoldResponse, HoldStatus
from app.holds import get_hold_store
from app.holds.base import SeatsUnavailable, StoreUnavailable
from app.pricing import seat_price

router = APIRouter(tags=["holds"])
logger = logging.getLogger(__name__)


def _unavailable(error: Exception):
    logger.warning("Seat hold operation failed: %s", error)
    raise HTTPException(status_code=503, detail="Seat hold service is unavailable") from error


@router.post("/shows/{show_id}/holds", response_model=HoldResponse, status_code=201)
def create_seat_hold(show_id: int, request: CreateHoldRequest, connection: Connection = Depends(get_connection),
                     user=Depends(booking_user)):
    if not 1 <= len(request.seat_ids) <= 10 or len(set(request.seat_ids)) != len(request.seat_ids):
        raise HTTPException(status_code=422, detail="Provide 1 to 10 unique seat IDs")
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, screen_id, regular_price, premium_price, recliner_price, status, start_time FROM shows WHERE id = %s", (show_id,))
        show = cursor.fetchone()
        if show is None:
            raise HTTPException(status_code=404, detail=f"Show {show_id} not found")
        if show["status"] != "SCHEDULED":
            raise HTTPException(status_code=409, detail="Show is not scheduled")
        if show["start_time"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="This show has already started")
        cursor.execute("""SELECT id, row_label, seat_number, seat_type FROM seats
                          WHERE screen_id = %s AND id = ANY(%s) ORDER BY row_label, seat_number""",
                       (show["screen_id"], request.seat_ids))
        seat_rows = cursor.fetchall()
        if len(seat_rows) != len(request.seat_ids):
            raise HTTPException(status_code=400, detail="One or more seats do not belong to this show's screen")
        cursor.execute("""SELECT COUNT(*) AS count FROM booking_seats AS bs JOIN bookings AS b ON b.id = bs.booking_id
                          WHERE bs.show_id = %s AND bs.seat_id = ANY(%s) AND b.status IN ('PENDING', 'CONFIRMED')""",
                       (show_id, request.seat_ids))
        if cursor.fetchone()["count"]:
            raise HTTPException(status_code=409, detail="One or more seats are no longer available")
    seats = [{**seat, "price": seat_price(show, seat["seat_type"])} for seat in seat_rows]
    now = datetime.now(timezone.utc)
    expiry = int(now.timestamp()) + settings.hold_seconds
    hold_id = uuid4().hex
    try:
        get_hold_store().create_hold(hold_id, show_id, request.seat_ids, expiry, int(now.timestamp()))
    except SeatsUnavailable as error:
        raise HTTPException(status_code=409, detail="One or more seats are no longer available") from error
    except StoreUnavailable as error:
        _unavailable(error)
    with connection.cursor() as cursor:
        cinema = cinema_for_show(cursor, show_id)
    expires_at = datetime.fromtimestamp(expiry, ZoneInfo(settings.app_timezone))
    return HoldResponse(**cinema, hold_id=hold_id, show_id=show_id, seat_ids=request.seat_ids, seats=seats,
                        total_amount=sum((seat["price"] for seat in seats)), expires_at=expires_at,
                        seconds_remaining=max(0, expiry - int(datetime.now(timezone.utc).timestamp())))


@router.get("/holds/{hold_id}", response_model=HoldStatus)
def read_seat_hold(hold_id: str, connection: Connection = Depends(get_connection)):
    try:
        item = get_hold_store().get_hold(hold_id)
    except StoreUnavailable as error:
        _unavailable(error)
    if item is None:
        raise HTTPException(status_code=404, detail="Hold not found")
    with connection.cursor() as cursor:
        cursor.execute("""SELECT id, row_label, seat_number, seat_type FROM seats
                          WHERE id = ANY(%s) ORDER BY row_label, seat_number""", (item["seat_ids"],))
        rows = cursor.fetchall()
        # Prices are stored by the show, so read them when a hold is inspected.
        cursor.execute("SELECT regular_price, premium_price, recliner_price FROM shows WHERE id = %s", (item["show_id"],))
        show = cursor.fetchone()
    seats = [{**seat, "price": seat_price(show, seat["seat_type"])} for seat in rows] if show else []
    now = int(datetime.now(timezone.utc).timestamp())
    remaining = max(0, int(item["expires_at"]) - now)
    with connection.cursor() as cursor:
        cinema = cinema_for_show(cursor, int(item["show_id"]))
    return HoldStatus(**cinema, hold_id=hold_id, show_id=int(item["show_id"]), seat_ids=item["seat_ids"], seats=seats,
                      total_amount=sum((seat["price"] for seat in seats)),
                      expires_at=datetime.fromtimestamp(int(item["expires_at"]), ZoneInfo(settings.app_timezone)),
                      seconds_remaining=remaining, status="ACTIVE" if int(item["expires_at"]) > now else "EXPIRED")


@router.delete("/holds/{hold_id}", status_code=204)
def delete_seat_hold(hold_id: str):
    try:
        item = get_hold_store().get_hold(hold_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Hold not found")
        get_hold_store().release_hold(hold_id, int(item["show_id"]), item["seat_ids"])
    except HTTPException:
        raise
    except StoreUnavailable as error:
        _unavailable(error)
    return Response(status_code=204)
