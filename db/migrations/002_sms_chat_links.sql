-- Phase 2 / Step 2.2: demo SMS with a chat link.
-- Upgrades an EXISTING database (keeps all data). Safe to run more than once.
-- Run with:  psql -U postgres -d moviebooking -v ON_ERROR_STOP=1 -f db/migrations/002_sms_chat_links.sql
BEGIN;

-- 1. Bookings remember the SMS choice made at checkout.
--    The phone is copied onto the booking (the customer's own phone can change on a later booking).
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS sms_phone TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS sms_consent BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_sms_phone_format;
ALTER TABLE bookings ADD CONSTRAINT bookings_sms_phone_format
    CHECK (sms_phone IS NULL OR sms_phone ~ '^\+[1-9][0-9]{7,14}$');          -- international form, e.g. +919812345678

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_sms_consent_needs_phone;
ALTER TABLE bookings ADD CONSTRAINT bookings_sms_consent_needs_phone
    CHECK (NOT sms_consent OR sms_phone IS NOT NULL);                         -- consent without a number is meaningless

-- 2. One permanent chat link per booking. The code is random, so it cannot be guessed.
CREATE TABLE IF NOT EXISTS chat_links (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK (code ~ '^[A-Za-z0-9]{10}$'),
    booking_id BIGINT NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,                                                   -- set to switch one link off; NULL = active
    open_count INTEGER NOT NULL DEFAULT 0 CHECK (open_count >= 0),
    last_opened_at TIMESTAMPTZ
);

-- 3. The demo SMS "sent" for a booking, shown in the Demo Phone inbox.
CREATE TABLE IF NOT EXISTS sms_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'BOOKING_CONFIRMED' CHECK (kind IN ('BOOKING_CONFIRMED')),
    to_phone TEXT NOT NULL CHECK (to_phone ~ '^\+[1-9][0-9]{7,14}$'),
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 480),            -- up to 3 SMS segments
    channel TEXT NOT NULL DEFAULT 'DEMO_INBOX' CHECK (channel IN ('DEMO_INBOX')),
    status TEXT NOT NULL DEFAULT 'DELIVERED' CHECK (status IN ('DELIVERED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (booking_id, kind)                                                 -- a retried worker never sends twice
);

-- The Demo Phone inbox lists one number's messages, newest first.
CREATE INDEX IF NOT EXISTS idx_sms_messages_to_phone_created ON sms_messages (to_phone, created_at DESC);

COMMIT;
