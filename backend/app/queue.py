"""Booking confirmation, run in the API process right after the response."""
import importlib.util
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


@lru_cache
def local_worker():
    # Load the sibling worker/ modules by path; they are not an installed package.
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
    try:
        from app.email import send_confirmation
        with psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row) as connection:
            result = local_worker()._process_record(
                connection, booking, release_hold=get_hold_store().release_hold,
                send_email=send_confirmation)
        logger.info(result)
    except Exception:
        logger.exception("Confirmation failed for %s", booking["booking_ref"])
