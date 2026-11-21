"""Phase 2: the demo SMS with a chat link, written when a booking is confirmed.

Nothing is sent over the phone network. The SMS is stored in the sms_messages table and
shown on the website's Demo Phone page; the link in it opens /c/<code> on the website.
"""
import logging
import os
import re
import secrets
import string
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

SMS_LIMIT = 160                      # one standard SMS
_ALPHABET = string.ascii_letters + string.digits


_E164 = re.compile(r"\+[1-9]\d{7,14}")


def normalize_phone(raw: str | None) -> str:
    """Return the number in +<country><number> form, or raise ValueError."""
    value = re.sub(r"[\s\-().]", "", raw or "")
    if value.startswith("00"):
        value = "+" + value[2:]
    if re.fullmatch(r"[6-9]\d{9}", value):          # 10-digit Indian mobile
        return "+91" + value
    if re.fullmatch(r"0[6-9]\d{9}", value):         # with a leading 0
        return "+91" + value[1:]
    if re.fullmatch(r"91[6-9]\d{9}", value):        # 91 without the +
        return "+" + value
    if _E164.fullmatch(value):
        return value
    raise ValueError("not a valid phone number")


def _allowed_numbers() -> set[str]:
    numbers = set()
    for value in os.getenv("SMS_DEMO_NUMBERS", "").split(","):
        try:
            numbers.add(normalize_phone(value))
        except ValueError:
            continue
    return numbers


def _site_url() -> str:
    return os.getenv("PUBLIC_SITE_URL", "http://localhost:5173").rstrip("/")


def _show_time(start_time, app_timezone=None) -> str:
    when = start_time.astimezone(ZoneInfo(app_timezone or os.getenv("APP_TIMEZONE", "Asia/Kolkata")))
    hour = when.strftime("%I").lstrip("0")
    return f"{when:%a} {when.day} {when:%b} {hour}:{when:%M} {when:%p}"      # Sun 12 Oct 7:30 PM


def build_sms_text(booking_ref: str, movie: str, start_time, screen: str, seats: list[str], link: str,
                   cinema_name: str = "CineBook Demo Cinema", cinema_area: str = "Pune") -> str:
    """Keep the link intact while shortening venue and movie text to one demo SMS."""
    when = _show_time(start_time).split(" ", 1)[-1].replace(" AM", "AM").replace(" PM", "PM")
    seats = sorted(seats, key=lambda label: "Recliner" not in label)
    seat_text = ",".join(seats)
    if len(seats) > 1:
        seat_text = f"{seats[0]} +{len(seats) - 1} more"
    venue = cinema_name
    area = cinema_area[:30]
    title = movie

    def compose():
        return f"CineBook DEMO {booking_ref}: {title}; {venue}, {area}; {when}; {screen}; Seats {seat_text}. Chat: {link}"

    def shorten(value, room):
        return value if len(value) <= room else value[:room - 3].rstrip() + "..."

    # Preserve the venue and area wherever possible; film titles lose detail first.
    if len(compose()) > SMS_LIMIT:
        title = shorten(movie, max(5, len(movie) - (len(compose()) - SMS_LIMIT)))
    if len(compose()) > SMS_LIMIT:
        venue = shorten(cinema_name, max(8, len(cinema_name) - (len(compose()) - SMS_LIMIT)))
    if len(compose()) > SMS_LIMIT:
        # Long configured URLs still keep their complete link; omit optional labels next.
        seat_text = seats[0] if seats else "-"
    if len(compose()) > SMS_LIMIT:
        raise ValueError("PUBLIC_SITE_URL is too long to fit a demo SMS with its booking and cinema")
    return compose()


def _chat_link_code(cursor, booking_id: int) -> str:
    """Create the booking's permanent chat link (or return the one that already exists)."""
    for _ in range(5):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        cursor.execute("""INSERT INTO chat_links (code, booking_id) VALUES (%s, %s)
                          ON CONFLICT DO NOTHING""", (code, booking_id))
        cursor.execute("SELECT code FROM chat_links WHERE booking_id = %s", (booking_id,))
        row = cursor.fetchone()
        if row:
            return row["code"]
        # Only reached if the random code was already used by another booking: try another one.
    raise RuntimeError("Could not create a unique chat link code")


def write_demo_sms(connection, cursor, booking: dict, seat_names: list[str]) -> str:
    """Create the chat link and the demo SMS for a just-confirmed booking. Returns a short log note.

    Runs inside the confirmation transaction, but in its own savepoint: if anything here fails,
    only the SMS part is undone - the booking stays confirmed.
    """
    phone = booking.get("sms_phone")
    if not booking.get("sms_consent") or not phone:
        return "no SMS requested"
    if phone not in _allowed_numbers():
        logger.warning("Demo SMS skipped for %s: number is no longer on the demo list", booking["booking_ref"])
        return "demo SMS skipped (number not registered)"
    try:
        with connection.transaction():                    # savepoint
            code = _chat_link_code(cursor, booking["id"])
            text = build_sms_text(booking["booking_ref"], booking["movie_title"], booking["start_time"],
                                  booking["screen_name"], seat_names, f"{_site_url()}/c/{code}",
                                  booking.get("cinema_name", "CineBook Demo Cinema"), booking.get("cinema_area", "Pune"))
            cursor.execute("""INSERT INTO sms_messages (booking_id, kind, to_phone, body)
                              VALUES (%s, 'BOOKING_CONFIRMED', %s, %s)
                              ON CONFLICT (booking_id, kind) DO NOTHING""",
                           (booking["id"], phone, text))
        return f"demo SMS written ({len(text)} chars)"
    except Exception:
        logger.exception("Could not write the demo SMS for %s", booking["booking_ref"])
        return "demo SMS FAILED"
