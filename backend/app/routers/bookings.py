import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from psycopg import Connection
from psycopg.errors import UniqueViolation
from app.holds import get_hold_store
from app.holds.base import StoreUnavailable
from app import queue
from app.config import settings
from app.db import get_connection
from app.cinema_queries import CINEMA_FIELDS
from app.models import BookingAccepted, BookingDetails, CreateBookingRequest, CancelBookingRequest
from app.ratelimit import SlidingWindowLimiter, client_key
from app.cancellation import cancel_booking_row, email_cancellation
from app.user_auth import booking_user
from app.phone import mask_phone, normalize_phone
from app.pricing import seat_price

router = APIRouter(prefix="/bookings", tags=["bookings"])
logger = logging.getLogger(__name__)
lookup_limiter = SlidingWindowLimiter(30, 60)
cancel_limiter = SlidingWindowLimiter(10, 15 * 60)


def _new_booking_ref() -> str:
    return "BK" + "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))


def _sms_phone_for(request: CreateBookingRequest) -> str | None:
    """Phase 2: the number to send the demo SMS to, or None when the customer did not ask for one.

    Checked before anything else, so an unusable number never costs a seat hold."""
    if not request.sms_consent:
        return None
    if not request.phone or not request.phone.strip():
        raise HTTPException(status_code=422, detail="Enter your mobile number to receive the SMS")
    try:
        phone = normalize_phone(request.phone)
    except ValueError as error:
        raise HTTPException(status_code=422,
                            detail="Enter a valid mobile number, for example 9812345678 or +919812345678") from error
    if phone not in settings.sms_demo_number_set:
        raise HTTPException(status_code=422,
                            detail="This number is not registered for demo SMS. Ask your trainer to add it, "
                                   "or untick the SMS option.")
    return phone


def _release_claim(hold_id: str, booking_ref: str) -> None:
    try:
        get_hold_store().unclaim_hold(hold_id, booking_ref)
    except StoreUnavailable as error:
        logger.warning("Could not release booking hold claim: %s", error)


@router.post("", response_model=BookingAccepted, status_code=202)
def create_booking(request: CreateBookingRequest, background_tasks: BackgroundTasks, connection: Connection = Depends(get_connection),
                   user=Depends(booking_user)):
    if user is not None:
        # The ticket belongs to the signed-in account: its email receives the confirmation.
        request = request.model_copy(update={"email": user["email"]})
    sms_phone = _sms_phone_for(request)
    if settings.queue_backend == "inline":
        queue.sweep_local()
    try:
        hold = get_hold_store().get_hold(request.hold_id)
    except StoreUnavailable as error:
        raise HTTPException(status_code=503, detail="Seat hold service is unavailable") from error
    if hold is None:
        raise HTTPException(status_code=404, detail="Hold not found")
    if int(hold["expires_at"]) <= time.time():
        raise HTTPException(status_code=409, detail="Your hold has expired")

    # Price is always calculated from PostgreSQL's current show and seat records.
    for attempt in range(3):
        # Claim first so concurrent clicks cannot create two bookings from the same hold.
        booking_ref = _new_booking_ref()
        try:
            claim_status, existing_ref = get_hold_store().claim_hold(request.hold_id, booking_ref)
        except StoreUnavailable as error:
            raise HTTPException(status_code=503, detail="Seat hold service is unavailable") from error
        if claim_status == "EXPIRED_OR_MISSING":
            raise HTTPException(status_code=409, detail="Your hold has expired")
        if claim_status == "ALREADY_CLAIMED":
            with connection.cursor() as cursor:
                cursor.execute("""SELECT b.status, s.start_time FROM bookings AS b
                                  JOIN shows AS s ON s.id = b.show_id WHERE b.booking_ref = %s""", (existing_ref,))
                row = cursor.fetchone()
            if row and row["start_time"] <= datetime.now(timezone.utc):
                raise HTTPException(status_code=409, detail="This show has already started")
            return {"booking_ref": existing_ref, "status": row["status"] if row else "PENDING"}

        try:
            # One transaction keeps the customer, booking, and all seat rows together.
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("""SELECT s.id, s.screen_id, s.regular_price, s.premium_price, s.recliner_price, s.start_time,
                                             s.status FROM shows AS s WHERE s.id = %s""", (hold["show_id"],))
                    show = cursor.fetchone()
                    if show is None:
                        raise HTTPException(status_code=409, detail="Your hold has expired")
                    if show["status"] != "SCHEDULED":
                        raise HTTPException(status_code=409, detail="This show has been cancelled by the cinema")
                    if show["start_time"] <= datetime.now(timezone.utc):
                        raise HTTPException(status_code=409, detail="This show has already started")
                    cursor.execute("""SELECT id, row_label, seat_number, seat_type FROM seats
                                      WHERE screen_id = %s AND id = ANY(%s) ORDER BY row_label, seat_number""",
                                   (show["screen_id"], hold["seat_ids"]))
                    seats = cursor.fetchall()
                    if len(seats) != len(hold["seat_ids"]):
                        raise HTTPException(status_code=409, detail="Your hold has expired")
                    priced_seats = [(seat, seat_price(show, seat["seat_type"])) for seat in seats]
                    total = sum((price for _, price in priced_seats), start=0)
                    cursor.execute("""INSERT INTO customers (full_name, email, phone)
                                      VALUES (%s, %s, %s)
                                      ON CONFLICT (email) DO UPDATE SET email = customers.email
                                      RETURNING id""", (request.full_name, request.email, request.phone))
                    customer_id = cursor.fetchone()["id"]
                    cursor.execute("""INSERT INTO bookings (booking_ref, customer_id, show_id, status, total_amount,
                                                          sms_phone, sms_consent, customer_name, customer_phone, user_id)
                                      VALUES (%s, %s, %s, 'PENDING', %s, %s, %s, %s, %s, %s) RETURNING id""",
                                   (booking_ref, customer_id, hold["show_id"], total,
                                    sms_phone, sms_phone is not None, request.full_name, request.phone,
                                    user["id"] if user else None))
                    booking_id = cursor.fetchone()["id"]
                    for seat, price in priced_seats:
                        cursor.execute("""INSERT INTO booking_seats (booking_id, show_id, seat_id, price)
                                          VALUES (%s, %s, %s, %s)""",
                                       (booking_id, hold["show_id"], seat["id"], price))
            break
        except UniqueViolation as error:
            constraint = getattr(error.diag, "constraint_name", None)
            if constraint == "bookings_booking_ref_key" and attempt < 2:
                # Free the old reference before trying the next random value.
                _release_claim(request.hold_id, booking_ref)
                continue
            _release_claim(request.hold_id, booking_ref)
            if constraint == "bookings_booking_ref_key":
                raise HTTPException(status_code=503, detail="Could not create booking") from error
            if constraint in ("booking_seats_show_id_seat_id_key", "booking_seats_show_id_seat_id_key1"):
                raise HTTPException(status_code=409, detail="One or more seats have already been sold") from error
            raise
        except HTTPException:
            _release_claim(request.hold_id, booking_ref)
            raise
        except Exception:
            _release_claim(request.hold_id, booking_ref)
            raise
    else:
        _release_claim(request.hold_id, booking_ref)
        raise HTTPException(status_code=503, detail="Could not create booking")

    connection.commit()
    # Send after commit so a worker can always read the complete booking from PostgreSQL.
    try:
        message = {"booking_ref": booking_ref, "booking_id": booking_id,
                   "hold_id": request.hold_id, "show_id": int(hold["show_id"])}
        if settings.queue_backend == "inline":
            background_tasks.add_task(queue.send_booking_message, message)
        else:
            queue.send_booking_message(message)
    except Exception as error:
        # Keep the failed order for audit, while removing its seat rows so seats can be sold again.
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE bookings SET status = 'FAILED' WHERE id = %s", (booking_id,))
                cursor.execute("DELETE FROM booking_seats WHERE booking_id = %s", (booking_id,))
        _release_claim(request.hold_id, booking_ref)
        logger.warning("Could not send booking to SQS: %s", error)
        raise HTTPException(status_code=503, detail="Booking service is temporarily unavailable") from error
    return {"booking_ref": booking_ref, "status": "PENDING"}


@router.get("/{booking_ref}", response_model=BookingDetails)
def read_booking(booking_ref: str, request: Request, connection: Connection = Depends(get_connection)):
    if not lookup_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    return _booking_details(booking_ref, connection)


def _booking_details(booking_ref, connection):
    with connection.cursor() as cursor:
        cursor.execute(f"""SELECT {CINEMA_FIELDS}, sc.format AS screen_format, b.booking_ref, b.status, COALESCE(b.customer_name, c.full_name) AS full_name, c.email,
                                 COALESCE(b.customer_phone, c.phone) AS phone,
                                 m.title AS movie_title, sc.name AS screen_name, s.start_time,
                                 b.total_amount, b.payment_ref, b.created_at, b.confirmed_at,
                                 b.sms_consent, b.sms_phone, b.cancelled_at, b.refund_ref,
                                 m.language AS movie_language, m.duration_minutes
                          FROM bookings AS b JOIN customers AS c ON c.id = b.customer_id
                          JOIN shows AS s ON s.id = b.show_id JOIN movies AS m ON m.id = s.movie_id
                          JOIN screens AS sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id WHERE b.booking_ref = %s""", (booking_ref,))
        booking = cursor.fetchone()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        cursor.execute("""SELECT seat.row_label, seat.seat_number, seat.seat_type, bs.price
                          FROM booking_seats AS bs JOIN seats AS seat ON seat.id = bs.seat_id
                          WHERE bs.booking_id = (SELECT id FROM bookings WHERE booking_ref = %s)
                          ORDER BY seat.row_label, seat.seat_number""", (booking_ref,))
        booking["seats"] = cursor.fetchall()
    booking["sms_phone_masked"] = mask_phone(booking.pop("sms_phone"))
    zone = ZoneInfo(settings.app_timezone)
    booking["start_time"] = booking["start_time"].astimezone(zone)
    booking["created_at"] = booking["created_at"].astimezone(zone)
    if booking["confirmed_at"] is not None:
        booking["confirmed_at"] = booking["confirmed_at"].astimezone(zone)
    booking["email_masked"] = booking["email"][:1] + "***@" + booking["email"].split("@", 1)[-1]
    phone = booking["phone"]
    try:
        phone = normalize_phone(phone) if phone else None
    except ValueError:
        pass
    booking["phone_masked"] = mask_phone(phone)
    deadline = booking["start_time"] - timedelta(minutes=settings.cancel_cutoff_minutes)
    booking["cancel_deadline"] = deadline if booking["status"] == "CONFIRMED" else None
    booking["cancellable"] = booking["status"] == "CONFIRMED" and datetime.now(timezone.utc) < deadline
    if booking["cancelled_at"]:
        booking["cancelled_at"] = booking["cancelled_at"].astimezone(zone)
    return booking


@router.post("/{booking_ref}/cancel", response_model=BookingDetails)
def cancel_booking(booking_ref: str, body: CancelBookingRequest, request: Request,
                   connection: Connection = Depends(get_connection)):
    if not cancel_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again in 15 minutes.")
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("""SELECT b.id, b.status, b.show_id, s.start_time FROM bookings b
                          JOIN customers c ON c.id = b.customer_id JOIN shows s ON s.id = b.show_id
                          WHERE b.booking_ref = %s AND lower(c.email) = lower(%s) FOR UPDATE OF b""",
                       (booking_ref, body.email))
        booking = cursor.fetchone()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking["status"] != "CONFIRMED":
            raise HTTPException(status_code=409, detail="Only confirmed bookings can be cancelled")
        if datetime.now(timezone.utc) >= booking["start_time"] - timedelta(minutes=settings.cancel_cutoff_minutes):
            minutes = settings.cancel_cutoff_minutes
            period = f"{minutes // 60} hour{'s' if minutes != 60 else ''}" if minutes % 60 == 0 else f"{minutes} minutes"
            raise HTTPException(status_code=409, detail=f"Bookings can only be cancelled up to {period} before the show")
        cancel_booking_row(cursor, booking["id"], "CUSTOMER")
    connection.commit()
    email_cancellation(connection, booking_ref, booking["show_id"])
    return _booking_details(booking_ref, connection)
