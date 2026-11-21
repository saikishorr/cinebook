"""Request context follows synchronous endpoints and background tasks."""
import logging
from contextvars import ContextVar

request_id = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id.get()
        return True


def configure_logging(level):
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.addFilter(RequestIdFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from uuid import uuid4
        # Generate locally so untrusted header text cannot be inserted into log lines.
        value = uuid4().hex
        token = request_id.set(value)

        async def with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", value.encode()))
            await send(message)
        try:
            await self.app(scope, receive, with_header)
        finally:
            request_id.reset(token)
