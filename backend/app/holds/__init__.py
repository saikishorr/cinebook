from app.holds.base import HoldStore


def get_hold_store() -> HoldStore:
    # Seat holds live in PostgreSQL (tables seat_holds and seat_hold_seats).
    from app.holds import postgres
    return postgres
