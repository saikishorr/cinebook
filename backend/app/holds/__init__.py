from app.config import settings
from app.holds.base import HoldStore


def get_hold_store() -> HoldStore:
    # Modules have no live connections until an operation is requested.
    if settings.holds_backend == "postgres":
        from app.holds import postgres
        return postgres
    from app.holds import dynamodb
    return dynamodb
