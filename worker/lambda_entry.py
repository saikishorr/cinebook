"""AWS Lambda entry point for the booking confirmation worker.

On a cold start it builds DATABASE_URL from Parameter Store (the password is
never stored in the function's settings), then hands over to the unchanged
worker code in confirm_booking.py.
"""
import logging
import os

import boto3

# Lambda's default log level is WARNING; show the worker's INFO lines in CloudWatch.
logging.getLogger().setLevel(logging.INFO)


def _database_url() -> str:
    prefix = os.environ.get("DB_PARAM_PREFIX", "/cinebook/prod/db")
    wanted = ["host", "master-username", "master-password"]
    response = boto3.client("ssm").get_parameters(
        Names=[f"{prefix}/{name}" for name in wanted], WithDecryption=True
    )
    values = {p["Name"].rsplit("/", 1)[1]: p["Value"] for p in response["Parameters"]}
    missing = [name for name in wanted if name not in values]
    if missing:
        raise RuntimeError(f"Missing Parameter Store values under {prefix}: {missing}")
    database = os.environ.get("DB_NAME", "moviebooking")
    return (
        f"postgresql://{values['master-username']}:{values['master-password']}"
        f"@{values['host']}:5432/{database}?sslmode=require"
    )


if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = _database_url()

from confirm_booking import lambda_handler  # noqa: E402  (import after DATABASE_URL is set)

__all__ = ["lambda_handler"]
