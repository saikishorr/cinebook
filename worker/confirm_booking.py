"""Confirm queued bookings, release their seat holds, and email customers."""
import html
import json
import logging
import os
import secrets
from decimal import Decimal
from zoneinfo import ZoneInfo

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import ClientError
from psycopg.rows import dict_row

try:
    from .demo_sms import write_demo_sms
except ImportError:
    from demo_sms import write_demo_sms

logger = logging.getLogger(__name__)

# Keep AWS clients warm between Lambda invocations and bound network waits.
_aws_config = Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2})
_region = os.getenv("AWS_REGION")
dynamodb = None
ses = None


def _client(service):
    global dynamodb, ses
    if service == "dynamodb":
        if dynamodb is None:
            dynamodb = boto3.client(service, region_name=_region, config=_aws_config)
        return dynamodb
    if ses is None:
        ses = boto3.client(service, region_name=_region, config=_aws_config)
    return ses


def _release_hold(hold_id: str, show_id: int, seat_ids: list[int]) -> None:
    table = os.environ["DYNAMODB_TABLE"]
    for seat_id in seat_ids:
        try:
            _client("dynamodb").delete_item(
                TableName=table,
                Key={"pk": {"S": f"SHOW#{show_id}"}, "sk": {"S": f"SEAT#{seat_id}"}},
                ConditionExpression="hold_id = :hold_id",
                ExpressionAttributeValues={":hold_id": {"S": hold_id}},
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code not in ("ConditionalCheckFailedException", "ResourceNotFoundException"):
                raise
    try:
        _client("dynamodb").delete_item(
            TableName=table,
            Key={"pk": {"S": f"HOLD#{hold_id}"}, "sk": {"S": "META"}},
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise


def _send_confirmation(booking: dict, seats: list[str]) -> None:
    zone = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))
    show_time = booking["start_time"].astimezone(zone).strftime("%a, %d %b %Y, %I:%M %p").replace(" 0", " ")
    amount = f"INR {booking['total_amount']:.2f}"
    seat_text = ", ".join(seats)
    subject = f"Your CineBook booking {booking['booking_ref']} is confirmed"
    lines = [
        "DEMO TICKET - not valid for entry",
        f"Cinema: {booking['cinema_name']} ({booking['cinema_area']})",
        "Real cinema metadata; CineBook showtimes, prices and seats are simulated. No cinema affiliation.",
        f"Booking reference: {booking['booking_ref']}",
        f"Customer: {booking['full_name']}",
        f"Movie: {booking['movie_title']}",
        f"Screen: {booking['screen_name']}",
        f"Date and time: {show_time}",
        f"Seats: {seat_text}",
        f"Total: {amount}",
        f"Payment reference: {booking['payment_ref']}",
    ]
    safe_lines = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    _client("sesv2").send_email(
        FromEmailAddress=os.environ["SES_SENDER_EMAIL"],
        Destination={"ToAddresses": [booking["email"]]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": "Your booking is confirmed.\n\n" + "\n".join(lines), "Charset": "UTF-8"},
                    "Html": {"Data": f"<html><body><h1>Your booking is confirmed</h1><ul>{safe_lines}</ul></body></html>", "Charset": "UTF-8"},
                },
            }
        },
    )


def _process_record(connection, body: dict, release_hold=None, send_email=None) -> str:
    release_hold = release_hold or _release_hold
    send_email = send_email or _send_confirmation
    booking_id = body["booking_id"]
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """SELECT b.id, b.booking_ref, b.status, b.total_amount, b.show_id,
                      COALESCE(b.customer_name, c.full_name) AS full_name, c.email, s.start_time, m.title AS movie_title,
                      sc.name AS screen_name, ci.name AS cinema_name, ci.area AS cinema_area, ci.address AS cinema_address, h.hold_id, b.sms_phone, b.sms_consent
               FROM bookings AS b
               JOIN customers AS c ON c.id = b.customer_id
               JOIN shows AS s ON s.id = b.show_id
               JOIN movies AS m ON m.id = s.movie_id
               JOIN screens AS sc ON sc.id = s.screen_id JOIN cinemas ci ON ci.id = sc.cinema_id
               JOIN (SELECT %s::text AS hold_id) AS h ON TRUE
               WHERE b.id = %s AND b.booking_ref = %s FOR UPDATE OF b""",
            (body["hold_id"], booking_id, body["booking_ref"]),
        )
        booking = cursor.fetchone()
        if booking is None:
            raise ValueError(f"Booking {body.get('booking_ref')} was not found")
        if booking["status"] in ("CONFIRMED", "FAILED", "CANCELLED"):
            return f"SKIPPED {booking['booking_ref']} ({booking['status']})"
        if booking["status"] != "PENDING":
            raise ValueError(f"Unexpected booking status: {booking['status']}")
        cursor.execute(
            """SELECT seat.id, seat.row_label, seat.seat_number, seat.seat_type
               FROM booking_seats AS bs JOIN seats AS seat ON seat.id = bs.seat_id
               WHERE bs.booking_id = %s ORDER BY seat.row_label, seat.seat_number""",
            (booking_id,),
        )
        seat_rows = cursor.fetchall()
        seat_names = [f"{row['row_label']}{row['seat_number']}" + (" (Recliner)" if row["seat_type"] == "RECLINER" else "") for row in seat_rows]
        payment_ref = "SIMPAY-" + secrets.token_hex(6).upper()
        # The conditional update prevents duplicate SQS deliveries charging twice.
        with connection.transaction():
            cursor.execute(
                """UPDATE bookings SET status = 'CONFIRMED', payment_ref = %s, confirmed_at = now()
                   WHERE id = %s AND status = 'PENDING'""",
                (payment_ref, booking_id),
            )
            if cursor.rowcount != 1:
                return f"SKIPPED {booking['booking_ref']} (already processed)"
            # Phase 2: chat link + demo SMS, committed together with the confirmation.
            sms_note = write_demo_sms(connection, cursor, booking, seat_names)
        booking["payment_ref"] = payment_ref

    release_hold(booking["hold_id"], int(booking["show_id"]), [int(row["id"]) for row in seat_rows])
    email_sent = False
    try:
        send_email(booking, seat_names)
        email_sent = True
    except Exception:
        logger.exception("Could not send confirmation email for %s", booking["booking_ref"])
    message = (f"CONFIRMED {booking['booking_ref']} ({len(seat_names)} seats, "
               f"INR {Decimal(booking['total_amount']):.2f}) - email {'sent' if email_sent else 'failed'} - {sms_note}")
    return message


def lambda_handler(event, context):
    """Process each SQS record independently so only failed messages retry."""
    failures = []
    database_url = os.environ["DATABASE_URL"]
    # A single connection serves the whole batch invocation.
    records = event.get("Records", [])
    try:
        with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as connection:
            for record in records:
                message_id = record["messageId"]
                try:
                    body = json.loads(record["body"])
                    if body.get("action") == "CANCELLED":
                        _send_cancellation(body["booking"])
                        result = f"Cancellation email sent for {body['booking_ref']}"
                    else:
                        result = _process_record(connection, body)
                    logger.info(result)
                except Exception:
                    logger.exception("Could not process booking message %s", message_id)
                    failures.append({"itemIdentifier": message_id})
    except Exception:
        # If the shared connection cannot open, make every message eligible for retry.
        logger.exception("Could not open the booking database connection")
        failures = [{"itemIdentifier": record["messageId"]} for record in records]
    return {"batchItemFailures": failures}


def _send_cancellation(booking):
    _client("sesv2").send_email(
        FromEmailAddress=os.environ["SES_SENDER_EMAIL"],
        Destination={"ToAddresses": [booking["email"]]},
        Content={"Simple": {
            "Subject": {"Data": f"Your CineBook booking {booking['booking_ref']} is cancelled", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": f"DEMO TICKET - not valid for entry\n"
                                      f"Cinema: {booking.get('cinema_name', 'CineBook Demo Cinema')} ({booking.get('cinema_area', 'Pune')})\n"
                                      f"Booking {booking['booking_ref']} has been cancelled.\n"
                                      f"Simulated refund reference: {booking['refund_ref']}\nNo real money was taken.",
                              "Charset": "UTF-8"}}}})


def sweep_stale_pending(connection, older_than_minutes=10):
    """Safe to call from a future scheduled Lambda or from local startup."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("""WITH stale AS (
                            UPDATE bookings SET status = 'FAILED'
                            WHERE status = 'PENDING' AND created_at < now() - (%s * interval '1 minute')
                            RETURNING id
                          ) DELETE FROM booking_seats WHERE booking_id IN (SELECT id FROM stale)""",
                       (older_than_minutes,))
        return cursor.rowcount
