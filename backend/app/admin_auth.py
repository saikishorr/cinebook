"""Small scrypt password hashes and revocable opaque admin sessions."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from app.db import get_connection

_N, _R, _P = 16384, 8, 1
_bearer = HTTPBearer(auto_error=False)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=64, maxmem=64 * 1024 * 1024)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algorithm, n, r, p, salt, expected = stored.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (_N, _R, _P):
            raise ValueError
        salt, expected = bytes.fromhex(salt), bytes.fromhex(expected)
        if len(salt) != 16 or len(expected) != 64:
            raise ValueError
    except (ValueError, AttributeError):
        # Unknown users and legacy/unusable hashes still pay the scrypt cost.
        salt, expected = b"\0" * 16, b"\0" * 64
    actual = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=64, maxmem=64 * 1024 * 1024)
    return secrets.compare_digest(actual, expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(connection, admin_user_id):
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    connection.execute("DELETE FROM admin_sessions WHERE expires_at <= now()")
    connection.execute("INSERT INTO admin_sessions (token_hash, admin_user_id, expires_at) VALUES (%s,%s,%s)",
                       (token_hash(token), admin_user_id, expires))
    return token, expires


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                  connection: Connection = Depends(get_connection)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Please sign in again")
    with connection.cursor() as cursor:
        # A disabled staff account loses access at once, even with a session still open.
        cursor.execute("""SELECT au.id, au.username, au.role, au.full_name FROM admin_sessions s
                          JOIN admin_users au ON au.id = s.admin_user_id
                          WHERE s.token_hash = %s AND s.expires_at > now() AND au.is_active""",
                       (token_hash(credentials.credentials),))
        admin = cursor.fetchone()
    connection.commit()
    if admin is None:
        raise HTTPException(status_code=401, detail="Please sign in again")
    return {**admin, "token_hash": token_hash(credentials.credentials)}


def require_permission(permission: str):
    """Dependency: the signed-in staff member must hold `permission` (see app/permissions.py)."""
    from app.permissions import allowed

    def check(admin=Depends(require_admin)):
        if not allowed(admin.get("role") or "SUPER_ADMIN", permission):
            raise HTTPException(status_code=403, detail="Your role does not allow this action")
        return admin
    return check


class AdminNoCacheMiddleware:
    def __init__(self, app, prefix=""):
        self.app = app
        self.path = prefix + "/admin"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (scope["path"] == self.path or scope["path"].startswith(self.path + "/")):
            return await self.app(scope, receive, send)
        async def no_cache(message):
            if message["type"] == "http.response.start":
                headers = [(k,v) for k,v in message.get("headers", []) if k.lower() not in (b"cache-control", b"pragma")]
                message["headers"] = headers + [(b"cache-control", b"no-store"), (b"pragma", b"no-cache")]
            await send(message)
        await self.app(scope, receive, no_cache)
