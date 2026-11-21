"""Cancelling a booking: one place, used by customers, staff and show cancellations."""
import logging
import secrets

logger = logging.getLogger(__name__)


def cancel_booking_row(cursor, booking_id: int, cancelled_by: str) -> str:
    """Mark the booking CANCELLED with a simulated refund and free its seats. Caller owns the transaction."""
    refund_ref = "SIMREF-" + secrets.token_hex(6).upper()
    cursor.execute("""UPDATE bookings SET status = 'CANCELLED', cancelled_at = now(), refund_ref = %s, cancelled_by = %s
                      WHERE id = %s""", (refund_ref, cancelled_by, booking_id))
    # Deleting the seat rows is what lets the seats be sold again.
    cursor.execute("DELETE FROM booking_seats WHERE booking_id = %s", (booking_id,))
    return refund_ref


def email_cancellation(connection, booking_ref: str, show_id: int) -> None:
    """Send the cancellation email after commit. A failed email never undoes a cancellation."""
    from app.email import send_cancellation
    from app.routers.bookings import _booking_details
    try:
        send_cancellation({**_booking_details(booking_ref, connection), "show_id": show_id})
    except Exception:
        logger.exception("Could not send cancellation email for %s", booking_ref)
