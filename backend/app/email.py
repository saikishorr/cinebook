"""Email delivery shared by local confirmation and cancellation."""
import logging
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)
OUTBOX = Path(__file__).resolve().parents[1] / "outbox"
_ses = None


def _send(booking, subject, body):
    if settings.email_backend == "log":
        message = EmailMessage()
        message["From"] = settings.ses_sender_email or "cinebook@localhost"
        message["To"] = booking["email"]
        message["Subject"] = subject
        message.set_content(body)
        OUTBOX.mkdir(parents=True, exist_ok=True)
        (OUTBOX / f"{booking['booking_ref']}-{uuid4().hex}.eml").write_bytes(message.as_bytes())
        logger.info("Demo email: %s\n%s", subject, body)
        return
    global _ses
    if _ses is None:
        import boto3
        from botocore.config import Config
        _ses = boto3.client("sesv2", region_name=settings.aws_region,
                            config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2}))
    _ses.send_email(FromEmailAddress=settings.ses_sender_email,
                    Destination={"ToAddresses": [booking["email"]]},
                    Content={"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}}}})


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
    if settings.email_backend == "ses" and settings.queue_backend == "sqs":
        from app.queue import send_cancellation_message
        send_cancellation_message(booking)
        return
    _send(booking, f"Your CineBook booking {booking['booking_ref']} is cancelled",
          f"DEMO TICKET - not valid for entry\nCinema: {booking['cinema_name']} ({booking['cinema_area']})\n"
          f"Booking {booking['booking_ref']} has been cancelled.\n"
          f"Simulated refund reference: {booking['refund_ref']}\nNo real money was taken.")
