"""Phase 2: the Demo Phone inbox - shows the demo SMS sent to one registered number.

POST /demo-phone/inbox with {"phone": "...", "access_code": "..."}.
POST (not GET) keeps the phone number and the code out of web addresses and access logs.
"""
import secrets
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import Connection

from app.config import settings
from app.db import get_connection
from app.models import DemoInbox, DemoInboxRequest
from app.phone import normalize_phone
from app.ratelimit import SlidingWindowLimiter, client_key

router = APIRouter(prefix="/demo-phone", tags=["demo phone"])

# After 10 wrong attempts in 15 minutes a visitor must wait, so the code cannot be guessed.
failures = SlidingWindowLimiter(limit=10, window_seconds=15 * 60)
_WRONG = "The phone number or access code is not correct"


@router.post("/inbox", response_model=DemoInbox)
def read_inbox(body: DemoInboxRequest, request: Request, connection: Connection = Depends(get_connection)):
    allowed = settings.sms_demo_number_set
    if not settings.demo_phone_access_code or not allowed:
        raise HTTPException(status_code=503, detail="The Demo Phone is not set up on this server")
    key = client_key(request)
    if failures.blocked(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again in 15 minutes.")

    try:
        phone = normalize_phone(body.phone)
    except ValueError:
        phone = None
    code_ok = secrets.compare_digest(body.access_code.encode(), settings.demo_phone_access_code.encode())
    # One message for every failure, so the page does not reveal which numbers are registered.
    if not code_ok or phone not in allowed:
        failures.record(key)
        raise HTTPException(status_code=401, detail=_WRONG)

    with connection.cursor() as cursor:
        cursor.execute("""SELECT m.id, m.body, m.status, m.created_at, b.booking_ref, cl.code AS chat_code
                          FROM sms_messages AS m JOIN bookings AS b ON b.id = m.booking_id
                          LEFT JOIN chat_links AS cl ON cl.booking_id = m.booking_id AND cl.revoked_at IS NULL
                          WHERE m.to_phone = %s
                          ORDER BY m.created_at DESC LIMIT 50""", (phone,))
        rows = cursor.fetchall()
    zone = ZoneInfo(settings.app_timezone)
    for row in rows:
        row["created_at"] = row["created_at"].astimezone(zone)
    return {"phone": phone, "messages": rows}
