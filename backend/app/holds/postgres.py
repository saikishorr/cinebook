"""Short, independent transactions: hold claims must commit before bookings."""
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.holds.base import SeatsUnavailable, StoreUnavailable


@contextmanager
def _connection():
    try:
        with psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row) as connection:
            yield connection
    except psycopg.Error as error:
        raise StoreUnavailable("PostgreSQL seat hold operation failed") from error


def create_hold(hold_id, show_id, seat_ids, expires_at, created_at):
    expiry = datetime.fromtimestamp(expires_at, timezone.utc)
    with _connection() as connection, connection.transaction(), connection.cursor() as cursor:
        # Sorted inserts give competing requests the same lock order.
        cursor.execute("DELETE FROM seat_hold_seats WHERE show_id = %s AND seat_id = ANY(%s) AND expires_at <= now()",
                       (show_id, seat_ids))
        cursor.execute("DELETE FROM seat_holds WHERE expires_at <= now() AND booking_ref IS NULL")
        cursor.execute("""INSERT INTO seat_holds (hold_id, show_id, seat_ids, expires_at, created_at)
                          VALUES (%s, %s, %s, %s, %s)""",
                       (hold_id, show_id, seat_ids, expiry, datetime.fromtimestamp(created_at, timezone.utc)))
        cursor.execute("""INSERT INTO seat_hold_seats (show_id, seat_id, hold_id, expires_at)
                          SELECT %s, id, %s, %s FROM unnest(%s::bigint[]) AS id ORDER BY id
                          ON CONFLICT DO NOTHING RETURNING seat_id""", (show_id, hold_id, expiry, seat_ids))
        if len(cursor.fetchall()) != len(seat_ids):
            raise SeatsUnavailable


def get_hold(hold_id):
    with _connection() as connection:
        row = connection.execute("SELECT * FROM seat_holds WHERE hold_id = %s", (hold_id,)).fetchone()
    if row:
        row["expires_at"] = int(row["expires_at"].timestamp())
        row["created_at"] = int(row["created_at"].timestamp())
    return row


def claim_hold(hold_id, booking_ref):
    with _connection() as connection, connection.transaction():
        row = connection.execute("""UPDATE seat_holds SET booking_ref = %s
                                    WHERE hold_id = %s AND booking_ref IS NULL AND expires_at > now()
                                    RETURNING hold_id""", (booking_ref, hold_id)).fetchone()
        if row:
            return "CLAIMED", None
        row = connection.execute("SELECT booking_ref FROM seat_holds WHERE hold_id = %s", (hold_id,)).fetchone()
        if row and row["booking_ref"]:
            return "ALREADY_CLAIMED", row["booking_ref"]
        return "EXPIRED_OR_MISSING", None


def unclaim_hold(hold_id, booking_ref):
    with _connection() as connection:
        connection.execute("UPDATE seat_holds SET booking_ref = NULL WHERE hold_id = %s AND booking_ref = %s",
                           (hold_id, booking_ref))


def release_hold(hold_id, show_id, seat_ids):
    # Cascading deletion cannot touch seats subsequently acquired by another hold.
    with _connection() as connection:
        connection.execute("DELETE FROM seat_holds WHERE hold_id = %s AND show_id = %s", (hold_id, show_id))


def held_seat_ids(show_id):
    with _connection() as connection:
        return {row["seat_id"] for row in connection.execute(
            "SELECT seat_id FROM seat_hold_seats WHERE show_id = %s AND expires_at > now()", (show_id,))}
