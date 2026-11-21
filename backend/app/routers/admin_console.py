"""The CineBook admin console: dashboard, bookings, customers, cinemas, shows, staff and the audit log.

Every endpoint checks a permission from app/permissions.py, and every change writes an audit row
in the same transaction as the change itself.
"""
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from app import audit
from app.admin_auth import hash_password, require_admin, require_permission
from app.cancellation import cancel_booking_row, email_cancellation
from app.config import settings
from app.db import get_connection
from app.models import BookingDetails
from app.permissions import ROLE_LABELS, ROLES, permissions_for
from app.scheduling import schedule_shows

router = APIRouter(prefix="/admin", tags=["admin console"])
logger = logging.getLogger(__name__)
BookingStatus = Literal["PENDING", "CONFIRMED", "FAILED", "CANCELLED"]


def _zone():
    return ZoneInfo(settings.app_timezone)


def _local(value):
    return value.astimezone(_zone()) if value else value


def _day_range(first: date, last: date):
    zone = _zone()
    return datetime.combine(first, time.min, zone), datetime.combine(last + timedelta(days=1), time.min, zone)


# ---------------------------------------------------------------- who am I
class AdminMe(BaseModel):
    id: int
    username: str
    full_name: str | None
    role: str
    role_label: str
    permissions: list[str]


@router.get("/me", response_model=AdminMe)
def admin_me(admin=Depends(require_admin)):
    role = admin.get("role") or "SUPER_ADMIN"
    return {"id": admin["id"], "username": admin["username"], "full_name": admin.get("full_name"), "role": role,
            "role_label": ROLE_LABELS[role], "permissions": permissions_for(role)}


# ---------------------------------------------------------------- dashboard
class DayPoint(BaseModel):
    date: date
    revenue: str
    bookings: int
    tickets: int


class Ranked(BaseModel):
    id: int
    name: str
    tickets: int
    revenue: str


class RecentBooking(BaseModel):
    booking_ref: str
    status: BookingStatus
    customer_name: str
    movie_title: str
    cinema_name: str
    total_amount: str
    created_at: datetime


class Dashboard(BaseModel):
    period_days: int
    kpis: dict[str, str | int | float]
    revenue_by_day: list[DayPoint]
    top_films: list[Ranked]
    top_cinemas: list[Ranked]
    status_breakdown: dict[str, int]
    recent_bookings: list[RecentBooking]


@router.get("/dashboard", response_model=Dashboard)
def dashboard(days: int = Query(7, ge=1, le=90), admin=Depends(require_permission("dashboard.view")),
              connection: Connection = Depends(get_connection)):
    zone = _zone()
    today = datetime.now(zone).date()
    first = today - timedelta(days=days - 1)
    start, end = _day_range(first, today)
    today_start, _ = _day_range(today, today)
    q = lambda sql, params=(): connection.execute(sql, params).fetchone()  # noqa: E731

    confirmed = q("""SELECT count(*) AS bookings, COALESCE(sum(b.total_amount), 0) AS revenue,
                            COALESCE(sum((SELECT count(*) FROM booking_seats bs WHERE bs.booking_id = b.id)), 0) AS tickets
                     FROM bookings b WHERE b.status = 'CONFIRMED' AND b.created_at >= %s AND b.created_at < %s""", (start, end))
    today_row = q("""SELECT count(*) AS bookings, COALESCE(sum(b.total_amount), 0) AS revenue,
                            COALESCE(sum((SELECT count(*) FROM booking_seats bs WHERE bs.booking_id = b.id)), 0) AS tickets
                     FROM bookings b WHERE b.status = 'CONFIRMED' AND b.created_at >= %s""", (today_start,))
    cancelled = q("""SELECT count(*) AS n, COALESCE(sum(total_amount), 0) AS refunded FROM bookings
                     WHERE status = 'CANCELLED' AND cancelled_at >= %s AND cancelled_at < %s""", (start, end))
    # Occupancy of the coming week: booked seats / all seats, over scheduled shows at active cinemas.
    occupancy = q("""SELECT COALESCE(sum(cap.seats), 0) AS capacity,
                            COALESCE(sum((SELECT count(*) FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id
                                          WHERE bs.show_id = s.id AND b.status IN ('PENDING','CONFIRMED'))), 0) AS sold,
                            count(*) AS shows
                     FROM shows s JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
                     JOIN (SELECT screen_id, count(*) AS seats FROM seats GROUP BY screen_id) cap ON cap.screen_id = s.screen_id
                     WHERE ci.is_active AND s.status = 'SCHEDULED' AND s.start_time > now() AND s.start_time < now() + interval '7 days'""")
    counts = q("""SELECT (SELECT count(*) FROM movies WHERE is_active) AS films,
                         (SELECT count(*) FROM cinemas WHERE is_active) AS cinemas,
                         (SELECT count(*) FROM users) AS customers,
                         (SELECT count(*) FROM users WHERE created_at >= %s) AS new_customers""", (start,))

    series = connection.execute("""
        SELECT d::date AS date, COALESCE(sum(b.total_amount), 0)::text AS revenue, count(b.id) AS bookings,
               COALESCE(sum((SELECT count(*) FROM booking_seats bs WHERE bs.booking_id = b.id)), 0) AS tickets
        FROM generate_series(%s::date, %s::date, interval '1 day') d
        LEFT JOIN bookings b ON b.status = 'CONFIRMED' AND (b.created_at AT TIME ZONE %s)::date = d::date
        GROUP BY d ORDER BY d""", (first, today, settings.app_timezone)).fetchall()

    def ranked(group_sql, name_sql):
        return connection.execute(f"""
            SELECT {group_sql} AS id, {name_sql} AS name, count(bs.id) AS tickets, COALESCE(sum(bs.price), 0)::text AS revenue
            FROM bookings b JOIN booking_seats bs ON bs.booking_id = b.id JOIN shows s ON s.id = b.show_id
            JOIN movies m ON m.id = s.movie_id JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
            WHERE b.status = 'CONFIRMED' AND b.created_at >= %s AND b.created_at < %s
            GROUP BY 1, 2 ORDER BY tickets DESC, revenue DESC LIMIT 5""", (start, end)).fetchall()

    statuses = {row["status"]: row["n"] for row in connection.execute(
        "SELECT status, count(*) AS n FROM bookings WHERE created_at >= %s AND created_at < %s GROUP BY status", (start, end))}
    recent = connection.execute("""
        SELECT b.booking_ref, b.status, COALESCE(b.customer_name, c.full_name) AS customer_name, m.title AS movie_title,
               ci.name AS cinema_name, b.total_amount::text AS total_amount, b.created_at
        FROM bookings b JOIN customers c ON c.id = b.customer_id JOIN shows s ON s.id = b.show_id
        JOIN movies m ON m.id = s.movie_id JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
        ORDER BY b.created_at DESC LIMIT 8""").fetchall()
    for row in recent:
        row["created_at"] = _local(row["created_at"])

    capacity = occupancy["capacity"] or 0
    return {
        "period_days": days,
        "kpis": {
            "revenue_today": str(today_row["revenue"]), "bookings_today": today_row["bookings"], "tickets_today": today_row["tickets"],
            "revenue_period": str(confirmed["revenue"]), "bookings_period": confirmed["bookings"], "tickets_period": confirmed["tickets"],
            "average_order": str(round(confirmed["revenue"] / confirmed["bookings"], 2) if confirmed["bookings"] else 0),
            "cancellations_period": cancelled["n"], "refunded_period": str(cancelled["refunded"]),
            "occupancy_next_7_days_pct": round(100 * occupancy["sold"] / capacity, 1) if capacity else 0.0,
            "upcoming_shows_7_days": occupancy["shows"], "active_films": counts["films"], "active_cinemas": counts["cinemas"],
            "customers_total": counts["customers"], "new_customers_period": counts["new_customers"],
        },
        "revenue_by_day": series,
        "top_films": ranked("m.id", "m.title"),
        "top_cinemas": ranked("ci.id", "ci.name"),
        "status_breakdown": statuses,
        "recent_bookings": recent,
    }


# ---------------------------------------------------------------- bookings
class AdminBookingRow(BaseModel):
    booking_ref: str
    status: BookingStatus
    customer_name: str
    email: str
    movie_title: str
    cinema_name: str
    screen_name: str
    start_time: datetime
    seats_count: int
    total_amount: str
    created_at: datetime
    user_id: int | None


class BookingPage(BaseModel):
    total: int
    items: list[AdminBookingRow]


class AdminBookingDetail(BookingDetails):
    user_id: int | None
    cancelled_by: str | None
    show_id: int


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.get("/bookings", response_model=BookingPage)
def list_bookings(q: str | None = Query(None, max_length=100), status: BookingStatus | None = None,
                  cinema_id: int | None = None, show_date: date | None = Query(None, alias="date"),
                  limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                  admin=Depends(require_permission("bookings.view")), connection: Connection = Depends(get_connection)):
    where, params = ["TRUE"], []
    if q and q.strip():
        needle = f"%{q.strip()}%"
        where.append("(b.booking_ref ILIKE %s OR c.email ILIKE %s OR COALESCE(b.customer_name, c.full_name) ILIKE %s)")
        params += [needle, needle, needle]
    if status:
        where.append("b.status = %s")
        params.append(status)
    if cinema_id:
        where.append("ci.id = %s")
        params.append(cinema_id)
    if show_date:
        day_start, day_end = _day_range(show_date, show_date)
        where.append("s.start_time >= %s AND s.start_time < %s")
        params += [day_start, day_end]
    base = f"""FROM bookings b JOIN customers c ON c.id = b.customer_id JOIN shows s ON s.id = b.show_id
               JOIN movies m ON m.id = s.movie_id JOIN screens sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
               WHERE {' AND '.join(where)}"""
    total = connection.execute(f"SELECT count(*) AS n {base}", params).fetchone()["n"]
    rows = connection.execute(f"""
        SELECT b.booking_ref, b.status, COALESCE(b.customer_name, c.full_name) AS customer_name, c.email, m.title AS movie_title,
               ci.name AS cinema_name, sc.name AS screen_name, s.start_time, b.total_amount::text AS total_amount, b.created_at, b.user_id,
               (SELECT count(*) FROM booking_seats bs WHERE bs.booking_id = b.id) AS seats_count
        {base} ORDER BY b.created_at DESC LIMIT %s OFFSET %s""", params + [limit, offset]).fetchall()
    for row in rows:
        row["start_time"], row["created_at"] = _local(row["start_time"]), _local(row["created_at"])
    return {"total": total, "items": rows}


def _admin_booking(connection, booking_ref):
    from app.routers.bookings import _booking_details
    detail = _booking_details(booking_ref, connection)
    extra = connection.execute("SELECT user_id, cancelled_by, show_id FROM bookings WHERE booking_ref = %s", (booking_ref,)).fetchone()
    return {**detail, **extra}


@router.get("/bookings/{booking_ref}", response_model=AdminBookingDetail)
def read_booking(booking_ref: str, admin=Depends(require_permission("bookings.view")),
                 connection: Connection = Depends(get_connection)):
    return _admin_booking(connection, booking_ref)


@router.post("/bookings/{booking_ref}/cancel", response_model=AdminBookingDetail)
def cancel_booking(booking_ref: str, body: CancelRequest, admin=Depends(require_permission("bookings.cancel")),
                   connection: Connection = Depends(get_connection)):
    """Staff may cancel and refund at any time (no 2-hour cutoff), e.g. for a complaint at the box office."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT id, status, show_id FROM bookings WHERE booking_ref = %s FOR UPDATE", (booking_ref,))
        booking = cursor.fetchone()
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking["status"] not in ("CONFIRMED", "PENDING"):
            raise HTTPException(status_code=409, detail="Only confirmed or pending bookings can be cancelled")
        refund = cancel_booking_row(cursor, booking["id"], f"ADMIN:{admin['username']}")
        audit.record(connection, admin, "booking.cancel", "booking", booking_ref, reason=body.reason, refund_ref=refund)
    connection.commit()
    email_cancellation(connection, booking_ref, booking["show_id"])
    return _admin_booking(connection, booking_ref)


# ---------------------------------------------------------------- customers
class CustomerRow(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    is_blocked: bool
    created_at: datetime
    last_login_at: datetime | None
    bookings: int
    spent: str


class CustomerPage(BaseModel):
    total: int
    items: list[CustomerRow]


class CustomerUpdate(BaseModel):
    is_blocked: bool
    reason: str | None = Field(default=None, max_length=300)


_CUSTOMER_SELECT = """SELECT u.id, u.full_name, u.email, u.phone, u.is_blocked, u.created_at, u.last_login_at,
    (SELECT count(*) FROM bookings b WHERE b.user_id = u.id AND b.status = 'CONFIRMED') AS bookings,
    (SELECT COALESCE(sum(total_amount), 0) FROM bookings b WHERE b.user_id = u.id AND b.status = 'CONFIRMED')::text AS spent
    FROM users u"""


def _customer_rows(rows):
    for row in rows:
        row["created_at"], row["last_login_at"] = _local(row["created_at"]), _local(row["last_login_at"])
    return rows


@router.get("/customers", response_model=CustomerPage)
def list_customers(q: str | None = Query(None, max_length=100), limit: int = Query(25, ge=1, le=100),
                   offset: int = Query(0, ge=0), admin=Depends(require_permission("customers.view")),
                   connection: Connection = Depends(get_connection)):
    where, params = "", []
    if q and q.strip():
        where = " WHERE u.email ILIKE %s OR u.full_name ILIKE %s OR u.phone ILIKE %s"
        params = [f"%{q.strip()}%"] * 3
    total = connection.execute(f"SELECT count(*) AS n FROM users u{where}", params).fetchone()["n"]
    rows = connection.execute(f"{_CUSTOMER_SELECT}{where} ORDER BY u.created_at DESC LIMIT %s OFFSET %s",
                              params + [limit, offset]).fetchall()
    return {"total": total, "items": _customer_rows(rows)}


@router.patch("/customers/{user_id}", response_model=CustomerRow)
def update_customer(user_id: int, body: CustomerUpdate, admin=Depends(require_permission("customers.block")),
                    connection: Connection = Depends(get_connection)):
    with connection.transaction():
        row = connection.execute("UPDATE users SET is_blocked = %s WHERE id = %s RETURNING id", (body.is_blocked, user_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        if body.is_blocked:
            connection.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))   # signs them out everywhere
        audit.record(connection, admin, "customer.block" if body.is_blocked else "customer.unblock", "user", user_id,
                     reason=body.reason)
    connection.commit()
    return _customer_rows(connection.execute(f"{_CUSTOMER_SELECT} WHERE u.id = %s", (user_id,)).fetchall())[0]


# ---------------------------------------------------------------- cinemas
class AdminCinema(BaseModel):
    id: int
    name: str
    chain: str
    area: str
    address: str | None
    is_active: bool
    screens_count: int
    seats_total: int
    upcoming_shows: int
    bookings_7_days: int


class CinemaUpdate(BaseModel):
    is_active: bool


_CINEMA_SELECT = """SELECT ci.id, ci.name, ci.chain, ci.area, ci.address, ci.is_active,
    (SELECT count(*) FROM screens sc WHERE sc.cinema_id = ci.id) AS screens_count,
    (SELECT count(*) FROM seats st JOIN screens sc ON sc.id = st.screen_id WHERE sc.cinema_id = ci.id) AS seats_total,
    (SELECT count(*) FROM shows s JOIN screens sc ON sc.id = s.screen_id
      WHERE sc.cinema_id = ci.id AND s.status = 'SCHEDULED' AND s.start_time > now()) AS upcoming_shows,
    (SELECT count(*) FROM bookings b JOIN shows s ON s.id = b.show_id JOIN screens sc ON sc.id = s.screen_id
      WHERE sc.cinema_id = ci.id AND b.status = 'CONFIRMED' AND b.created_at > now() - interval '7 days') AS bookings_7_days
    FROM cinemas ci"""


@router.get("/cinemas", response_model=list[AdminCinema])
def list_cinemas(admin=Depends(require_permission("dashboard.view")), connection: Connection = Depends(get_connection)):
    # The curated Pune cinemas (and anything active); old OpenStreetMap imports stay hidden.
    return connection.execute(f"{_CINEMA_SELECT} WHERE ci.source_key IS NOT NULL OR ci.is_active ORDER BY ci.is_active DESC, ci.name").fetchall()


@router.patch("/cinemas/{cinema_id}", response_model=AdminCinema)
def update_cinema(cinema_id: int, body: CinemaUpdate, admin=Depends(require_permission("cinemas.manage")),
                  connection: Connection = Depends(get_connection)):
    try:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(641902109)")
            row = connection.execute("UPDATE cinemas SET is_active = %s WHERE id = %s RETURNING id", (body.is_active, cinema_id)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Cinema not found")
            audit.record(connection, admin, "cinema.activate" if body.is_active else "cinema.deactivate", "cinema", cinema_id)
            # Deactivating frees the cinema's unbooked future shows; activating gives it a weekly programme.
            schedule_shows(connection)
        connection.commit()
    except ValueError as error:
        connection.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None
    return connection.execute(f"{_CINEMA_SELECT} WHERE ci.id = %s", (cinema_id,)).fetchone()


# ---------------------------------------------------------------- shows
class AdminShow(BaseModel):
    id: int
    movie_id: int
    movie_title: str
    screen_name: str
    screen_format: str
    start_time: datetime
    status: Literal["SCHEDULED", "CANCELLED"]
    cancelled_reason: str | None
    seats_total: int
    seats_sold: int
    bookings: int
    revenue: str


class ShowCancelResult(BaseModel):
    show: AdminShow
    cancelled_bookings: int


_SHOW_SELECT = """SELECT s.id, s.movie_id, m.title AS movie_title, sc.name AS screen_name, sc.format AS screen_format, s.start_time,
    s.status, s.cancelled_reason,
    (SELECT count(*) FROM seats st WHERE st.screen_id = s.screen_id) AS seats_total,
    (SELECT count(*) FROM booking_seats bs JOIN bookings b ON b.id = bs.booking_id
      WHERE bs.show_id = s.id AND b.status IN ('PENDING','CONFIRMED')) AS seats_sold,
    (SELECT count(*) FROM bookings b WHERE b.show_id = s.id AND b.status = 'CONFIRMED') AS bookings,
    (SELECT COALESCE(sum(total_amount), 0) FROM bookings b WHERE b.show_id = s.id AND b.status = 'CONFIRMED')::text AS revenue
    FROM shows s JOIN movies m ON m.id = s.movie_id JOIN screens sc ON sc.id = s.screen_id"""


def _show_rows(rows):
    for row in rows:
        row["start_time"] = _local(row["start_time"])
    return rows


@router.get("/shows", response_model=list[AdminShow])
def list_shows(cinema_id: int, show_date: date = Query(alias="date"), admin=Depends(require_permission("dashboard.view")),
               connection: Connection = Depends(get_connection)):
    start, end = _day_range(show_date, show_date)
    return _show_rows(connection.execute(
        f"{_SHOW_SELECT} WHERE sc.cinema_id = %s AND s.start_time >= %s AND s.start_time < %s ORDER BY sc.name, s.start_time",
        (cinema_id, start, end)).fetchall())


@router.post("/shows/{show_id}/cancel", response_model=ShowCancelResult)
def cancel_show(show_id: int, body: CancelRequest, admin=Depends(require_permission("shows.manage")),
                connection: Connection = Depends(get_connection)):
    """Cancel a show (e.g. projector failure): every booking on it is cancelled and refunded, and it cannot be booked again."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT id, status, start_time FROM shows WHERE id = %s FOR UPDATE", (show_id,))
        show = cursor.fetchone()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        if show["status"] != "SCHEDULED":
            raise HTTPException(status_code=409, detail="This show is already cancelled")
        if show["start_time"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="This show has already started")
        cursor.execute("UPDATE shows SET status = 'CANCELLED', cancelled_reason = %s WHERE id = %s", (body.reason, show_id))
        cursor.execute("SELECT id, booking_ref FROM bookings WHERE show_id = %s AND status IN ('CONFIRMED','PENDING') FOR UPDATE",
                       (show_id,))
        affected = cursor.fetchall()
        for booking in affected:
            cancel_booking_row(cursor, booking["id"], f"ADMIN:{admin['username']}")
        # Unfinished checkouts on this show can no longer complete.
        cursor.execute("DELETE FROM seat_holds WHERE show_id = %s", (show_id,))
        audit.record(connection, admin, "show.cancel", "show", show_id, reason=body.reason,
                     cancelled_bookings=[b["booking_ref"] for b in affected])
    connection.commit()
    for booking in affected:
        email_cancellation(connection, booking["booking_ref"], show_id)
    show_row = _show_rows(connection.execute(f"{_SHOW_SELECT} WHERE s.id = %s", (show_id,)).fetchall())[0]
    return {"show": show_row, "cancelled_bookings": len(affected)}


# ---------------------------------------------------------------- staff accounts
class StaffRow(BaseModel):
    id: int
    username: str
    full_name: str | None
    role: str
    role_label: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class StaffCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=2, max_length=100)
    role: Literal["SUPER_ADMIN", "MANAGER", "SUPPORT"]
    password: str = Field(min_length=8, max_length=128)


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    role: Literal["SUPER_ADMIN", "MANAGER", "SUPPORT"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


def _staff(connection, where="", params=()):
    rows = connection.execute(f"""SELECT id, username, full_name, role, is_active, created_at, last_login_at FROM admin_users
                                  {where} ORDER BY is_active DESC, username""", params).fetchall()
    for row in rows:
        row["role_label"] = ROLE_LABELS.get(row["role"], row["role"])
        row["created_at"], row["last_login_at"] = _local(row["created_at"]), _local(row["last_login_at"])
    return rows


@router.get("/staff", response_model=list[StaffRow])
def list_staff(admin=Depends(require_permission("staff.manage")), connection: Connection = Depends(get_connection)):
    return _staff(connection)


@router.post("/staff", response_model=StaffRow, status_code=201)
def create_staff(body: StaffCreate, admin=Depends(require_permission("staff.manage")),
                 connection: Connection = Depends(get_connection)):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", body.username):
        raise HTTPException(status_code=422, detail="Username may use letters, numbers, dots, dashes and underscores only")
    try:
        with connection.transaction():
            row = connection.execute("""INSERT INTO admin_users (username, full_name, role, password_hash)
                                        VALUES (%s, %s, %s, %s) RETURNING id""",
                                     (body.username, body.full_name.strip(), body.role, hash_password(body.password))).fetchone()
            audit.record(connection, admin, "staff.create", "admin_user", row["id"], username=body.username, role=body.role)
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="That username is already taken") from None
    connection.commit()
    return _staff(connection, "WHERE id = %s", (row["id"],))[0]


@router.patch("/staff/{staff_id}", response_model=StaffRow)
def update_staff(staff_id: int, body: StaffUpdate, admin=Depends(require_permission("staff.manage")),
                 connection: Connection = Depends(get_connection)):
    if staff_id == admin["id"] and (body.is_active is False or (body.role and body.role != admin.get("role"))):
        raise HTTPException(status_code=409, detail="You cannot disable your own account or change your own role")
    with connection.transaction():
        current = connection.execute("SELECT id, role, is_active FROM admin_users WHERE id = %s FOR UPDATE", (staff_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Staff account not found")
        role = body.role or current["role"]
        active = current["is_active"] if body.is_active is None else body.is_active
        if current["role"] == "SUPER_ADMIN" and current["is_active"] and (role != "SUPER_ADMIN" or not active):
            others = connection.execute("""SELECT count(*) AS n FROM admin_users
                                           WHERE role = 'SUPER_ADMIN' AND is_active AND id <> %s""", (staff_id,)).fetchone()["n"]
            if others == 0:
                raise HTTPException(status_code=409, detail="CineBook must keep at least one active super admin")
        sets, params, changes = [], [], {}
        for column, value in (("full_name", body.full_name and body.full_name.strip()), ("role", body.role), ("is_active", body.is_active)):
            if value is not None:
                sets.append(f"{column} = %s")
                params.append(value)
                changes[column] = value
        if body.password:
            sets.append("password_hash = %s")
            params.append(hash_password(body.password))
            changes["password"] = "reset"
        if not sets:
            raise HTTPException(status_code=422, detail="Nothing to change")
        connection.execute(f"UPDATE admin_users SET {', '.join(sets)} WHERE id = %s", params + [staff_id])
        if body.password or body.is_active is False or body.role:
            connection.execute("DELETE FROM admin_sessions WHERE admin_user_id = %s AND token_hash <> %s",
                               (staff_id, admin["token_hash"]))   # new rights take effect at the next sign-in
        audit.record(connection, admin, "staff.update", "admin_user", staff_id, **changes)
    connection.commit()
    return _staff(connection, "WHERE id = %s", (staff_id,))[0]


# ---------------------------------------------------------------- audit log
class AuditRow(BaseModel):
    id: int
    admin_username: str
    action: str
    target_type: str | None
    target_id: str | None
    details: dict
    created_at: datetime


class AuditPage(BaseModel):
    total: int
    items: list[AuditRow]


@router.get("/audit", response_model=AuditPage)
def list_audit(action: str | None = Query(None, max_length=60), limit: int = Query(50, ge=1, le=200),
               offset: int = Query(0, ge=0), admin=Depends(require_permission("audit.view")),
               connection: Connection = Depends(get_connection)):
    where, params = ("WHERE action LIKE %s", [f"{action}%"]) if action else ("", [])
    total = connection.execute(f"SELECT count(*) AS n FROM admin_audit_log {where}", params).fetchone()["n"]
    rows = connection.execute(f"""SELECT id, admin_username, action, target_type, target_id, details, created_at
                                  FROM admin_audit_log {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
                              params + [limit, offset]).fetchall()
    for row in rows:
        row["created_at"] = _local(row["created_at"])
    return {"total": total, "items": rows}


_ = ROLES  # re-exported for tests
