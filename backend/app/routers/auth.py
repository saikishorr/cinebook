"""Customer accounts: sign up, sign in, profile, and the customer's own bookings.

POST /auth/register   POST /auth/login   POST /auth/logout   GET|PATCH /auth/me
GET  /me/bookings     POST /me/bookings/{ref}/cancel
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg import Connection
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from app.admin_auth import hash_password, verify_password
from app.cancellation import cancel_booking_row, email_cancellation
from app.config import settings
from app.db import get_connection
from app.models import BookingDetails, CreateBookingRequest
from app.phone import normalize_phone
from app.ratelimit import SlidingWindowLimiter, client_key
from app.user_auth import new_user_session, require_user

router = APIRouter(tags=["customer accounts"])
logger = logging.getLogger(__name__)
login_failures = SlidingWindowLimiter(10, 15 * 60)
signups = SlidingWindowLimiter(10, 60 * 60)
EMAIL_PATTERN = CreateBookingRequest.model_fields["email"].metadata[0].pattern


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=20)


class UserProfile(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserProfile


class MyBooking(BaseModel):
    booking_ref: str
    status: str
    movie_title: str
    poster_url: str | None
    cinema_name: str
    cinema_area: str
    screen_name: str
    start_time: datetime
    seats: list[str]
    total_amount: str
    created_at: datetime
    cancellable: bool


def _clean_phone(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    try:
        return normalize_phone(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="Enter a valid mobile number, for example 9812345678") from None


def _profile(user: dict) -> dict:
    zone = ZoneInfo(settings.app_timezone)
    return {key: user[key] for key in ("id", "full_name", "email", "phone")} | {"created_at": user["created_at"].astimezone(zone)}


def _session_response(connection, user: dict) -> dict:
    token, expires = new_user_session(connection, user["id"])
    connection.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    connection.commit()
    return {"token": token, "expires_at": expires.astimezone(ZoneInfo(settings.app_timezone)), "user": _profile(user)}


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest, request: Request, connection: Connection = Depends(get_connection)):
    if not signups.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many sign-ups from this network. Please try again later.")
    phone = _clean_phone(body.phone)
    try:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute("""INSERT INTO users (full_name, email, phone, password_hash) VALUES (%s, %s, %s, %s)
                              RETURNING id, full_name, email, phone, created_at""",
                           (body.full_name.strip(), body.email.strip(), phone, hash_password(body.password)))
            user = cursor.fetchone()
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.") from None
    logger.info("Customer account created user_id=%s", user["id"])
    return _session_response(connection, user)


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, connection: Connection = Depends(get_connection)):
    key = client_key(request)
    if login_failures.blocked(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again in 15 minutes.")
    with connection.cursor() as cursor:
        cursor.execute("""SELECT id, full_name, email, phone, created_at, password_hash, is_blocked FROM users
                          WHERE lower(email) = lower(%s)""", (body.email.strip(),))
        user = cursor.fetchone()
    # verify_password costs the same for unknown emails, so timing does not reveal who has an account.
    if not verify_password(body.password, user["password_hash"] if user else "") or user is None:
        login_failures.record(key)
        raise HTTPException(status_code=401, detail="Wrong email or password")
    if user["is_blocked"]:
        raise HTTPException(status_code=403, detail="This account has been blocked. Please contact CineBook support.")
    return _session_response(connection, user)


@router.post("/auth/logout", status_code=204)
def logout(user=Depends(require_user), connection: Connection = Depends(get_connection)):
    connection.execute("DELETE FROM user_sessions WHERE token_hash = %s", (user["token_hash"],))
    connection.commit()
    return Response(status_code=204)


@router.get("/auth/me", response_model=UserProfile)
def me(user=Depends(require_user)):
    return _profile(user)


@router.patch("/auth/me", response_model=UserProfile)
def update_me(body: ProfileUpdate, user=Depends(require_user), connection: Connection = Depends(get_connection)):
    name = body.full_name.strip() if body.full_name is not None else user["full_name"]
    phone = _clean_phone(body.phone) if body.phone is not None else user["phone"]
    connection.execute("UPDATE users SET full_name = %s, phone = %s WHERE id = %s", (name, phone, user["id"]))
    connection.commit()
    return _profile({**user, "full_name": name, "phone": phone})


@router.get("/me/bookings", response_model=list[MyBooking])
def my_bookings(user=Depends(require_user), connection: Connection = Depends(get_connection)):
    zone = ZoneInfo(settings.app_timezone)
    with connection.cursor() as cursor:
        cursor.execute("""SELECT b.id, b.booking_ref, b.status, b.total_amount::text AS total_amount, b.created_at,
                                 m.title AS movie_title, m.poster_url, ci.name AS cinema_name, ci.area AS cinema_area,
                                 sc.name AS screen_name, s.start_time,
                                 COALESCE((SELECT array_agg(seat.row_label || seat.seat_number ORDER BY seat.row_label, seat.seat_number)
                                           FROM booking_seats bs JOIN seats seat ON seat.id = bs.seat_id
                                           WHERE bs.booking_id = b.id), '{}') AS seats
                          FROM bookings b JOIN shows s ON s.id = b.show_id JOIN movies m ON m.id = s.movie_id
                          JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                          WHERE b.user_id = %s AND b.status <> 'FAILED'
                          ORDER BY s.start_time DESC LIMIT 200""", (user["id"],))
        rows = cursor.fetchall()
    cutoff = timedelta(minutes=settings.cancel_cutoff_minutes)
    now = datetime.now(timezone.utc)
    for row in rows:
        row["cancellable"] = row["status"] == "CONFIRMED" and now < row["start_time"] - cutoff
        row["start_time"] = row["start_time"].astimezone(zone)
        row["created_at"] = row["created_at"].astimezone(zone)
    return rows


@router.post("/me/bookings/{booking_ref}/cancel", response_model=BookingDetails)
def cancel_my_booking(booking_ref: str, user=Depends(require_user), connection: Connection = Depends(get_connection)):
    from app.routers.bookings import _booking_details
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("""SELECT b.id, b.status, b.show_id, s.start_time FROM bookings b JOIN shows s ON s.id = b.show_id
                          WHERE b.booking_ref = %s AND b.user_id = %s FOR UPDATE OF b""", (booking_ref, user["id"]))
        booking = cursor.fetchone()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking["status"] != "CONFIRMED":
            raise HTTPException(status_code=409, detail="Only confirmed bookings can be cancelled")
        if datetime.now(timezone.utc) >= booking["start_time"] - timedelta(minutes=settings.cancel_cutoff_minutes):
            hours = settings.cancel_cutoff_minutes / 60
            raise HTTPException(status_code=409,
                                detail=f"Bookings can only be cancelled up to {hours:g} hour{'s' if hours != 1 else ''} before the show")
        cancel_booking_row(cursor, booking["id"], "CUSTOMER")
    connection.commit()
    email_cancellation(connection, booking_ref, booking["show_id"])
    return _booking_details(booking_ref, connection)
