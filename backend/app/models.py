from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

class Movie(BaseModel):
    cinemas_count: int
    next_show_at: datetime | None
    id: int
    title: str
    description: str | None
    duration_minutes: int
    language: str
    certificate: str
    poster_url: str | None
    genres: list[str] = Field(default_factory=list)
    backdrop_url: str | None = None
    trailer_url: str | None = None
    release_date: date | None = None

class ShowSummary(BaseModel):
    recliner_price: Decimal | None
    cinema_id: int
    cinema_name: str
    cinema_area: str
    cinema_chain: str
    screen_format: str
    seats_total: int
    seats_available: int
    id: int
    movie_id: int
    screen_id: int
    start_time: datetime
    regular_price: Decimal
    premium_price: Decimal
    status: Literal["SCHEDULED", "CANCELLED"]
    screen_name: str
    movie_title: str | None = None

class ShowDetails(ShowSummary):
    cinema_address: str | None
    cinema_latitude: float
    cinema_longitude: float
    movie_title: str
    movie_language: str
    duration_minutes: int

class SeatInShow(BaseModel):
    id: int
    row_label: str
    seat_number: int
    seat_type: Literal["REGULAR", "PREMIUM", "RECLINER"]
    row_index: int | None
    col: int | None
    accessible: bool
    price: Decimal
    status: Literal["AVAILABLE", "HELD", "BOOKED"]

class SeatGrid(BaseModel):
    rows: int
    cols: int


class SeatSection(BaseModel):
    name: str
    seat_type: Literal["REGULAR", "PREMIUM", "RECLINER"]
    price: Decimal
    row_labels: list[str]


class SeatMap(BaseModel):
    layout_name: str | None
    grid: SeatGrid | None
    sections: list[SeatSection]
    show_id: int
    seats: list[SeatInShow]
    available_count: int
    held_count: int
    booked_count: int

class CreateHoldRequest(BaseModel):
    seat_ids: list[int]

class HeldSeat(BaseModel):
    id: int
    row_label: str
    seat_number: int
    seat_type: Literal["REGULAR", "PREMIUM", "RECLINER"]
    price: Decimal

class HoldResponse(BaseModel):
    cinema_name: str
    cinema_area: str
    cinema_address: str | None
    hold_id: str
    show_id: int
    seat_ids: list[int]
    seats: list[HeldSeat]
    total_amount: Decimal
    expires_at: datetime
    seconds_remaining: int

class HoldStatus(HoldResponse):
    status: Literal["ACTIVE", "EXPIRED"]

class CreateBookingRequest(BaseModel):
    hold_id: str
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
    phone: str | None = Field(default=None, max_length=20)
    # Phase 2: the customer ticked "Send me an SMS with my booking and a chat link".
    sms_consent: bool = False

class BookingAccepted(BaseModel):
    booking_ref: str
    status: Literal["PENDING", "CONFIRMED", "FAILED", "CANCELLED"]

class BookingSeat(BaseModel):
    row_label: str
    seat_number: int
    seat_type: Literal["REGULAR", "PREMIUM", "RECLINER"]
    price: Decimal

class CancelBookingRequest(BaseModel):
    email: str


class BookingDetails(BaseModel):
    cinema_name: str
    cinema_area: str
    cinema_address: str | None
    screen_format: str
    email_masked: str
    phone_masked: str | None
    movie_language: str
    duration_minutes: int
    cancellable: bool
    cancel_deadline: datetime | None
    cancelled_at: datetime | None
    refund_ref: str | None
    booking_ref: str
    status: Literal["PENDING", "CONFIRMED", "FAILED", "CANCELLED"]
    full_name: str
    email: str
    phone: str | None
    movie_title: str
    screen_name: str
    start_time: datetime
    seats: list[BookingSeat]
    total_amount: Decimal
    payment_ref: str | None
    created_at: datetime
    confirmed_at: datetime | None
    # Phase 2: shown on the confirmation page ("SMS sent to +91 ******5678").
    sms_consent: bool = False
    sms_phone_masked: str | None = None

# ---------------------------------------------------------------- Phase 2: chat links and Demo Phone
class ChatLinkSummary(BaseModel):
    cinema_name: str
    cinema_area: str
    cinema_address: str | None
    """What a chat link reveals: the booking, never the customer's email or phone."""
    code: str
    booking_ref: str
    status: Literal["PENDING", "CONFIRMED", "FAILED", "CANCELLED"]
    first_name: str
    movie_title: str
    movie_language: str
    screen_name: str
    start_time: datetime
    seats: list[str]
    total_amount: Decimal

class DemoInboxRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    access_code: str = Field(min_length=1, max_length=64)


class Cinema(BaseModel):
    location_precision: Literal["building", "area"] | None
    id: int
    name: str
    chain: str
    area: str
    address: str | None
    latitude: float
    longitude: float
    screens_count: int
    formats: list[str]

class DemoSmsMessage(BaseModel):
    id: int
    body: str
    booking_ref: str
    chat_code: str | None
    status: Literal["DELIVERED", "FAILED"]
    created_at: datetime

class DemoInbox(BaseModel):
    phone: str
    messages: list[DemoSmsMessage]

# ---------------------------------------------------------------- Phase 3: Help & info
class HelpItem(BaseModel):
    q: str
    a: str

class HelpSection(BaseModel):
    id: str
    title: str
    items: list[HelpItem]

class HelpInfo(BaseModel):
    title: str
    updated: str
    notice: str
    sections: list[HelpSection]

# ---------------------------------------------------------------- Phase 3: chat assistant
class ChatMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    outcome: Literal["ANSWERED", "REFUSED", "ERROR"] | None
    created_at: datetime

class ChatHistory(BaseModel):
    enabled: bool                      # False when no model is configured
    messages: list[ChatMessage]
    remaining_this_hour: int
    max_message_chars: int

class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

class ChatSendResponse(BaseModel):
    user_message: ChatMessage
    reply: ChatMessage
    remaining_this_hour: int
