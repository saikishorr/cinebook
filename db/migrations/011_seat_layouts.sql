BEGIN;
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
COMMIT;
