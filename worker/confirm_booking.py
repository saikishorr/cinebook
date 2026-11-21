"""Confirm pending bookings, release their seat holds, write the demo SMS and email customers.

The API runs this right after a booking is created. It passes in its own seat-hold release and
email functions, so this module has no storage or mail service of its own.
"""
import logging
import secrets
from decimal import Decimal

try:
    from .demo_sms import write_demo_sms
except ImportError:
    from demo_sms import write_demo_sms

logger = logging.getLogger(__name__)


def _process_record(connection, body: dict, *, release_hold, send_email) -> str:
    booking_id = body["booking_id"]
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """SELECT b.id, b.booking_ref, b.status, b.total_amount, b.show_id,
                      COALESCE(b.customer_name, c.full_name) AS full_name, c.email, s.start_time, m.title AS movie_title,
                      sc.name AS screen_name, ci.name AS cinema_name, ci.area AS cinema_area, ci.address AS cinema_address, h.hold_id, b.sms_phone, b.sms_consent
               FROM bookings AS b
               JOIN customers AS c ON c.id = b.customer_id
               JOIN shows AS s ON s.id = b.show_id
               JOIN movies AS m ON m.id = s.movie_id
               JOIN screens AS sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
               JOIN (SELECT %s::text AS hold_id) AS h ON TRUE
               WHERE b.id = %s AND b.booking_ref = %s FOR UPDATE OF b""",
            (body["hold_id"], booking_id, body["booking_ref"]),
        )
        booking = cursor.fetchone()
        if booking is None:
            raise ValueError(f"Booking {body.get('booking_ref')} was not found")
        if booking["status"] in ("CONFIRMED", "FAILED", "CANCELLED"):
            return f"SKIPPED {booking['booking_ref']} ({booking['status']})"
        if booking["status"] != "PENDING":
            raise ValueError(f"Unexpected booking status: {booking['status']}")
        cursor.execute(
            """SELECT seat.id, seat.row_label, seat.seat_number, seat.seat_type
               FROM booking_seats AS bs JOIN seats AS seat ON seat.id = bs.seat_id
               WHERE bs.booking_id = %s ORDER BY seat.row_label, seat.seat_number""",
            (booking_id,),
        )
        seat_rows = cursor.fetchall()
        seat_names = [f"{row['row_label']}{row['seat_number']}" + (" (Recliner)" if row["seat_type"] == "RECLINER" else "") for row in seat_rows]
        payment_ref = "SIMPAY-" + secrets.token_hex(6).upper()
        # The conditional update prevents a repeated confirmation charging twice.
        with connection.transaction():
            cursor.execute(
                """UPDATE bookings SET status = 'CONFIRMED', payment_ref = %s, confirmed_at = now()
                   WHERE id = %s AND status = 'PENDING'""",
                (payment_ref, booking_id),
            )
            if cursor.rowcount != 1:
                return f"SKIPPED {booking['booking_ref']} (already processed)"
            # Phase 2: chat link + demo SMS, committed together with the confirmation.
            sms_note = write_demo_sms(connection, cursor, booking, seat_names)
        booking["payment_ref"] = payment_ref

    release_hold(booking["hold_id"], int(booking["show_id"]), [int(row["id"]) for row in seat_rows])
    email_sent = False
    try:
        send_email(booking, seat_names)
        email_sent = True
    except Exception:
        logger.exception("Could not send confirmation email for %s", booking["booking_ref"])
    message = (f"CONFIRMED {booking['booking_ref']} ({len(seat_names)} seats, "
               f"INR {Decimal(booking['total_amount']):.2f}) - email {'sent' if email_sent else 'failed'} - {sms_note}")
    return message


def sweep_stale_pending(connection, older_than_minutes=10):
    """Mark bookings stuck in PENDING as FAILED and free their seats. Called at API startup."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("""WITH stale AS (
                            UPDATE bookings SET status = 'FAILED'
                            WHERE status = 'PENDING' AND created_at < now() - (%s * interval '1 minute')
                            RETURNING id
                          ) DELETE FROM booking_seats WHERE booking_id IN (SELECT id FROM stale)""",
                       (older_than_minutes,))
        return cursor.rowcount
