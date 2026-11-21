DROP TABLE IF EXISTS admin_audit_log CASCADE;
DROP TABLE IF EXISTS user_sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS admin_sessions;
DROP TABLE IF EXISTS cinemas CASCADE;
DROP TABLE IF EXISTS seat_hold_seats CASCADE;
DROP TABLE IF EXISTS seat_holds CASCADE;
-- Reset the application schema in dependency order so this file can be rerun.
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS sms_messages CASCADE;
DROP TABLE IF EXISTS chat_links CASCADE;
DROP TABLE IF EXISTS booking_seats CASCADE;
DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS shows CASCADE;
DROP TABLE IF EXISTS seats CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;
DROP TABLE IF EXISTS movies CASCADE;
DROP TABLE IF EXISTS screens CASCADE;

-- Films available for scheduling.
CREATE TABLE movies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    language TEXT NOT NULL,
    certificate TEXT NOT NULL CHECK (certificate IN ('U', 'UA', 'A')),
    poster_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auditoriums and their seat-grid dimensions.
CREATE TABLE screens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    total_rows INTEGER NOT NULL CHECK (total_rows > 0),
    seats_per_row INTEGER NOT NULL CHECK (seats_per_row > 0)
);

-- Physical seats belonging to each screen.
CREATE TABLE seats (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    screen_id BIGINT NOT NULL REFERENCES screens(id),
    row_label TEXT NOT NULL CHECK (row_label ~ '^[A-Z]+$'),
    seat_number INTEGER NOT NULL CHECK (seat_number > 0),
    seat_type TEXT NOT NULL CHECK (seat_type IN ('REGULAR', 'PREMIUM')),
    UNIQUE (screen_id, row_label, seat_number)
);

-- Scheduled movie performances in a screen.
CREATE TABLE shows (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    movie_id BIGINT NOT NULL REFERENCES movies(id),
    screen_id BIGINT NOT NULL REFERENCES screens(id),
    start_time TIMESTAMPTZ NOT NULL,
    regular_price NUMERIC(10,2) NOT NULL CHECK (regular_price >= 0),
    premium_price NUMERIC(10,2) NOT NULL CHECK (premium_price >= 0),
    status TEXT NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED', 'CANCELLED')),
    UNIQUE (screen_id, start_time)
);

-- People who can make ticket bookings.
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A customer's order for one scheduled show.
CREATE TABLE bookings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_ref TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    show_id BIGINT NOT NULL REFERENCES shows(id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED')),
    total_amount NUMERIC(10,2) NOT NULL CHECK (total_amount >= 0),
    payment_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ
);

-- Seats reserved in a booking; uniqueness prevents a seat being sold twice for a show.
CREATE TABLE booking_seats (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    show_id BIGINT NOT NULL REFERENCES shows(id),
    seat_id BIGINT NOT NULL REFERENCES seats(id),
    price NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    UNIQUE (show_id, seat_id)
);

-- Staff login credentials; the application stores password hashes here.
CREATE TABLE admin_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index foreign-key lookups and showtime queries.
CREATE INDEX idx_seats_screen_id ON seats(screen_id);
CREATE INDEX idx_shows_movie_id ON shows(movie_id);
CREATE INDEX idx_shows_screen_id ON shows(screen_id);
CREATE INDEX idx_shows_start_time ON shows(start_time);
CREATE INDEX idx_bookings_customer_id ON bookings(customer_id);
CREATE INDEX idx_bookings_show_id ON bookings(show_id);
CREATE INDEX idx_booking_seats_booking_id ON booking_seats(booking_id);
CREATE INDEX idx_booking_seats_show_id ON booking_seats(show_id);
CREATE INDEX idx_booking_seats_seat_id ON booking_seats(seat_id);

-- ---------------------------------------------------------------- Phase 2: demo SMS with a chat link
-- (identical to migrations/002_sms_chat_links.sql, so a fresh database gets everything in one run)
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

-- ---------------------------------------------------------------- Phase 3: chat assistant conversations
-- (identical to migrations/003_chat_messages.sql)
-- One row per message in a chat. A conversation belongs to a chat link, and so to one booking.
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_link_id BIGINT NOT NULL REFERENCES chat_links(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),               -- who wrote it
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 4000),
    -- For assistant messages: how the question was handled.
    --   ANSWERED = answered from the booking / website information
    --   REFUSED  = politely declined (outside what the assistant is for)
    --   ERROR    = the model could not be reached; a fallback message was shown
    outcome TEXT CHECK (outcome IN ('ANSWERED', 'REFUSED', 'ERROR')),
    model TEXT,                                                             -- which model answered
    input_tokens INTEGER CHECK (input_tokens >= 0),                         -- usage, for cost tracking
    output_tokens INTEGER CHECK (output_tokens >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Customer messages have no outcome; assistant messages always have one.
    CONSTRAINT chat_messages_outcome_matches_role
        CHECK ((role = 'user' AND outcome IS NULL) OR (role = 'assistant' AND outcome IS NOT NULL))
);

-- Reading a conversation in order, and counting a link's recent messages for the hourly limit.
CREATE INDEX IF NOT EXISTS idx_chat_messages_link_id ON chat_messages (chat_link_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_link_created ON chat_messages (chat_link_id, created_at);

-- 004_seat_holds

CREATE TABLE IF NOT EXISTS seat_holds (
    hold_id TEXT PRIMARY KEY,
    show_id BIGINT NOT NULL REFERENCES shows(id),
    seat_ids BIGINT[] NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    booking_ref TEXT
);
CREATE TABLE IF NOT EXISTS seat_hold_seats (
    show_id BIGINT NOT NULL,
    seat_id BIGINT NOT NULL REFERENCES seats(id),
    hold_id TEXT NOT NULL REFERENCES seat_holds(hold_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (show_id, seat_id)
);
CREATE INDEX IF NOT EXISTS idx_seat_holds_expires ON seat_holds (expires_at);


-- 005_movie_details

ALTER TABLE movies ADD COLUMN IF NOT EXISTS genres TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE movies ADD COLUMN IF NOT EXISTS backdrop_url TEXT;
ALTER TABLE movies ADD COLUMN IF NOT EXISTS trailer_url TEXT;
ALTER TABLE movies ADD COLUMN IF NOT EXISTS release_date DATE;


-- 006_booking_cancellation

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS refund_ref TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_name TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_phone TEXT;


-- 007_schema_migrations

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------- Movies imported from TMDB
-- (identical to migrations/008_movie_tmdb.sql)
ALTER TABLE movies ADD COLUMN IF NOT EXISTS tmdb_id BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS movies_tmdb_id_key ON movies (tmdb_id);

-- 009_cinemas

CREATE TABLE IF NOT EXISTS cinemas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    osm_id TEXT UNIQUE,
    name TEXT NOT NULL,
    chain TEXT NOT NULL,
    area TEXT NOT NULL,
    address TEXT,
    city TEXT NOT NULL DEFAULT 'Pune',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO cinemas (name, chain, area, latitude, longitude, is_active)
SELECT 'CineBook Demo Cinema', 'Independent', 'Pune', 18.5204, 73.8567, FALSE
WHERE NOT EXISTS (SELECT 1 FROM cinemas WHERE osm_id IS NULL AND name = 'CineBook Demo Cinema');
ALTER TABLE screens ADD COLUMN IF NOT EXISTS cinema_id BIGINT REFERENCES cinemas(id);
UPDATE screens SET cinema_id = (SELECT id FROM cinemas WHERE osm_id IS NULL AND name = 'CineBook Demo Cinema' ORDER BY id LIMIT 1)
WHERE cinema_id IS NULL;
ALTER TABLE screens ALTER COLUMN cinema_id SET NOT NULL;
ALTER TABLE screens ADD COLUMN IF NOT EXISTS format TEXT NOT NULL DEFAULT '2D'
    CHECK (format IN ('2D', '3D', 'IMAX', '4DX', 'ICE', 'Dolby Atmos'));
ALTER TABLE screens DROP CONSTRAINT IF EXISTS screens_name_key;
ALTER TABLE screens DROP CONSTRAINT IF EXISTS screens_cinema_name_key;
ALTER TABLE screens ADD CONSTRAINT screens_cinema_name_key UNIQUE (cinema_id, name);
CREATE INDEX IF NOT EXISTS idx_screens_cinema_id ON screens (cinema_id);
CREATE INDEX IF NOT EXISTS idx_cinemas_active ON cinemas (is_active);


-- 010_cinema_source

ALTER TABLE cinemas ADD COLUMN IF NOT EXISTS source_key TEXT UNIQUE;
ALTER TABLE cinemas ADD COLUMN IF NOT EXISTS location_precision TEXT
    CHECK (location_precision IN ('building', 'area'));


-- 011_seat_layouts

ALTER TABLE seats DROP CONSTRAINT IF EXISTS seats_seat_type_check;
ALTER TABLE seats ADD CONSTRAINT seats_seat_type_check CHECK (seat_type IN ('REGULAR', 'PREMIUM', 'RECLINER'));
ALTER TABLE seats ADD COLUMN IF NOT EXISTS row_index INTEGER;
ALTER TABLE seats ADD COLUMN IF NOT EXISTS col INTEGER;
ALTER TABLE seats ADD COLUMN IF NOT EXISTS accessible BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE screens ADD COLUMN IF NOT EXISTS layout_name TEXT;
-- Persist editable section labels so the cloud API never needs local layout files.
ALTER TABLE screens ADD COLUMN IF NOT EXISTS section_names JSONB NOT NULL
    DEFAULT '{"R":"Regular","P":"Prime","L":"Recliner"}';
ALTER TABLE shows ADD COLUMN IF NOT EXISTS recliner_price NUMERIC(10,2) CHECK (recliner_price >= 0);


-- 012_admin_sessions

CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    admin_user_id BIGINT REFERENCES admin_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires ON admin_sessions (expires_at);


-- ---------------------------------------------------------------- Accounts, staff roles, audit log
-- (identical to migrations/013_accounts_roles_audit.sql)
-- Customer accounts (sign-in to book), staff roles, and an audit log of admin actions.

-- 1. Customers sign in with email + password. Emails are unique regardless of case.
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL CHECK (char_length(full_name) BETWEEN 2 AND 100),
    email TEXT NOT NULL CHECK (char_length(email) BETWEEN 3 AND 254),
    phone TEXT,
    password_hash TEXT NOT NULL,
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (lower(email));

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions (expires_at);

-- A booking made while signed in belongs to that account (older bookings have none).
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_created_at ON bookings (created_at);

-- 2. Staff roles. Existing staff accounts become super admins so nobody is locked out.
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'SUPER_ADMIN';
ALTER TABLE admin_users DROP CONSTRAINT IF EXISTS admin_users_role_check;
ALTER TABLE admin_users ADD CONSTRAINT admin_users_role_check CHECK (role IN ('SUPER_ADMIN', 'MANAGER', 'SUPPORT'));
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- 3. Every admin change is recorded: who, what, on which record, and when.
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_user_id BIGINT REFERENCES admin_users(id) ON DELETE SET NULL,
    admin_username TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log (created_at DESC);

-- 4. Why a show or booking was cancelled by staff.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS cancelled_reason TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_by TEXT;   -- 'CUSTOMER' or 'ADMIN:<username>'

