"""Customer accounts: sign-up, sign-in and the session behind the booking flow.

Passwords use the same scrypt hashing as staff accounts (app/admin_auth.py). A session is an opaque
random token; only its SHA-256 is stored, so a database leak does not expose live sessions.
"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from app.admin_auth import token_hash
from app.config import settings
from app.db import get_connection

_bearer = HTTPBearer(auto_error=False)
SIGN_IN_AGAIN = "Please sign in to continue"


def new_user_session(connection, user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.user_session_days)
    connection.execute("DELETE FROM user_sessions WHERE expires_at <= now()")
    connection.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                       (token_hash(token), user_id, expires))
    return token, expires


def _lookup(credentials, connection):
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    with connection.cursor() as cursor:
        cursor.execute("""SELECT u.id, u.full_name, u.email, u.phone, u.is_blocked, u.created_at
                          FROM user_sessions s JOIN users u ON u.id = s.user_id
                          WHERE s.token_hash = %s AND s.expires_at > now()""", (token_hash(credentials.credentials),))
        user = cursor.fetchone()
    connection.commit()
    if user is None:
        return None
    return {**user, "token_hash": token_hash(credentials.credentials)}


def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                  connection: Connection = Depends(get_connection)):
    """The signed-in customer, or None. A staff token is simply not a customer session."""
    return _lookup(credentials, connection)


def require_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(status_code=401, detail=SIGN_IN_AGAIN)
    if user["is_blocked"]:
        raise HTTPException(status_code=403, detail="This account has been blocked. Please contact CineBook support.")
    return user


def booking_user(user=Depends(optional_user)):
    """For the hold and booking endpoints: a signed-in, unblocked customer when login is required."""
    if not settings.require_login_for_booking:
        return user
    return require_user(user)
