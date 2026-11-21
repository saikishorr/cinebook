BEGIN;
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
COMMIT;
