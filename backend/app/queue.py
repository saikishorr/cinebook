"""Cloud queue dispatch, or local confirmation after the response."""
import importlib.util
import json
import logging
import sys
import types
from functools import lru_cache
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.holds import get_hold_store

logger = logging.getLogger(__name__)
sqs = None


@lru_cache
def local_worker():
    # Only inline mode needs sibling worker source; the API image does not ship it.
    directory = Path(__file__).resolve().parents[2] / "worker"
    package = types.ModuleType("cinebook_local_worker")
    package.__path__ = [str(directory)]
    sys.modules[package.__name__] = package
    modules = {}
    for name in ("demo_sms", "confirm_booking"):
        qualified = f"{package.__name__}.{name}"
        spec = importlib.util.spec_from_file_location(qualified, directory / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
        modules[name] = module
    # Read settings directly; never mutate process environment during a request.
    modules["demo_sms"]._allowed_numbers = lambda: settings.sms_demo_number_set
    modules["demo_sms"]._site_url = lambda: settings.public_site_url.rstrip("/")
    format_time = modules["demo_sms"]._show_time
    modules["demo_sms"]._show_time = lambda start: format_time(start, settings.app_timezone)
    return modules["confirm_booking"]


def sweep_local():
    with psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row) as connection:
        local_worker().sweep_stale_pending(connection)


def send_booking_message(booking: dict) -> None:
    if settings.queue_backend == "inline":
        try:
            from app.email import send_confirmation
            with psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row) as connection:
                result = local_worker()._process_record(
                    connection, booking, release_hold=get_hold_store().release_hold,
                    send_email=send_confirmation)
            logger.info(result)
        except Exception:
            logger.exception("Inline confirmation failed for %s", booking["booking_ref"])
        return
    _send_sqs({key: booking[key] for key in ("booking_ref", "booking_id", "hold_id", "show_id")})


def _send_sqs(message):
    global sqs
    if sqs is None:
        import boto3
        from botocore.config import Config
        sqs = boto3.client("sqs", region_name=settings.aws_region,
                           config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 2}))
    sqs.send_message(QueueUrl=settings.booking_queue_url, MessageBody=json.dumps(message),
                     MessageGroupId=f"show-{message['show_id']}",
                     MessageDeduplicationId=("cancel-" if message.get("action") else "") + message["booking_ref"])


def send_cancellation_message(booking):
    # The existing cloud worker already has the SES sender and send permission.
    # The API role has neither: use its existing queue permission without new cloud settings.
    _send_sqs({"action": "CANCELLED", "show_id": booking["show_id"], "booking_ref": booking["booking_ref"],
               "booking": {**{key: booking[key] for key in ("booking_ref", "email", "refund_ref")},
                           "cinema_name": booking.get("cinema_name", "CineBook Demo Cinema"),
                           "cinema_area": booking.get("cinema_area", "Pune")}})
