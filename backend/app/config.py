from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.phone import parse_number_list

class Settings(BaseSettings):
    # Read configuration from the environment or a .env file.
    database_url: str
    app_timezone: str = "Asia/Kolkata"
    cors_origins: str = "*"
    dynamodb_table: str = "seat-holds"
    aws_region: str = "ap-south-1"
    hold_seconds: int = 300
    holds_backend: Literal["dynamodb", "postgres"] = "dynamodb"
    queue_backend: Literal["sqs", "inline"] = "sqs"
    email_backend: Literal["ses", "log"] = "ses"
    booking_queue_url: str = ""
    ses_sender_email: str = ""
    cancel_cutoff_minutes: int = 120
    # Customer accounts: holding seats and paying need a signed-in customer (BookMyShow-style).
    require_login_for_booking: bool = True
    user_session_days: int = 30
    log_level: str = "INFO"
    api_workers: int = 2
    api_prefix: str = ""
    # Phase 2: demo SMS. Numbers allowed to receive demo SMS, comma-separated (+919812345678, ...).
    sms_demo_numbers: str = ""
    public_site_url: str = "http://localhost:5173"
    # Shared code that opens the Demo Phone inbox. Empty = Demo Phone switched off.
    demo_phone_access_code: str = ""
    # Phase 3: chat assistant. Set by infra/scripts/check-gemini.py (or check-bedrock.py).
    chat_provider: str = "gemini"          # gemini | bedrock | fake (tests)
    chat_model_id: str = ""                # empty = chat switched off
    gemini_api_key: str = ""               # secret: .env locally, SecureString in Parameter Store
    tmdb_api_key: str = ""
    bedrock_region: str = ""               # empty = same as aws_region
    chat_max_message_chars: int = 500
    chat_max_output_tokens: int = 300
    chat_messages_per_hour: int = 30       # per chat link
    chat_history_turns: int = 8            # earlier messages sent to the model for context
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_queue(self):
        if self.queue_backend == "sqs" and not self.booking_queue_url.strip():
            raise ValueError("BOOKING_QUEUE_URL is required when QUEUE_BACKEND=sqs")
        if self.cancel_cutoff_minutes < 0 or self.api_workers < 1:
            raise ValueError("CANCEL_CUTOFF_MINUTES must be nonnegative and API_WORKERS positive")
        return self

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if value and (not value.startswith("/") or value.endswith("/")):
            raise ValueError('API_PREFIX must be empty or start with "/" and not end with "/"')
        return value

    @property
    def sms_demo_number_set(self) -> frozenset[str]:
        return parse_number_list(self.sms_demo_numbers)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
