"""Demo emails for confirmation and cancellation, saved as .eml files in backend/outbox/."""
import logging
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)
OUTBOX = Path(__file__).resolve().parents[1] / "outbox"


def _send(booking, subject, body):
    message = EmailMessage()
    message["From"] = settings.sender_email or "cinebook@localhost"
    message["To"] = booking["email"]
    message["Subject"] = subject
    message.set_content(body)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    (OUTBOX / f"{booking['booking_ref']}-{uuid4().hex}.eml").write_bytes(message.as_bytes())
    logger.info("Demo email: %s\n%s", subject, body)


def send_confirmation(booking, seats):
    from zoneinfo import ZoneInfo
    when = booking["start_time"].astimezone(ZoneInfo(settings.app_timezone)).isoformat()
    _send(booking, f"Your CineBook booking {booking['booking_ref']} is confirmed",
          f"DEMO TICKET - not valid for entry\nReal cinema metadata; CineBook showtimes, prices and seats are simulated. No cinema affiliation.\n"
          f"Cinema: {booking['cinema_name']} ({booking['cinema_area']})\n"
          f"Hello {booking['full_name']},\nBooking: {booking['booking_ref']}\n"
          f"Movie: {booking['movie_title']}\nScreen: {booking['screen_name']}\n"
          f"Show: {when}\nSeats: {', '.join(seats)}\nTotal: INR {booking['total_amount']:.2f}\n"
          f"Payment: {booking['payment_ref']}")


def send_cancellation(booking):
    _send(booking, f"Your CineBook booking {booking['booking_ref']} is cancelled",
          f"DEMO TICKET - not valid for entry\nCinema: {booking['cinema_name']} ({booking['cinema_area']})\n"
          f"Booking {booking['booking_ref']} has been cancelled.\n"
          f"Simulated refund reference: {booking['refund_ref']}\nNo real money was taken.")
