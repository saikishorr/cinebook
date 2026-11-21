from functools import lru_cache
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.phone import parse_number_list

class Settings(BaseSettings):
    # Read configuration from the environment or a .env file.
    database_url: str
    app_timezone: str = "Asia/Kolkata"
    cors_origins: str = "*"
    hold_seconds: int = 300
    # "From" address on the demo emails saved in backend/outbox/.
    sender_email: str = "cinebook@localhost"
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
    # Phase 3: chat assistant. Check the key and model with scripts/check-gemini.py.
    chat_provider: str = "gemini"          # gemini | fake (tests)
    chat_model_id: str = ""                # empty = chat switched off
    gemini_api_key: str = ""               # secret: keep it in backend/.env only
    tmdb_api_key: str = ""
    chat_max_message_chars: int = 500
    chat_max_output_tokens: int = 300
    chat_messages_per_hour: int = 30       # per chat link
    chat_history_turns: int = 8            # earlier messages sent to the model for context
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_limits(self):
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
