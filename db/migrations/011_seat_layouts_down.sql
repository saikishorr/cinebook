BEGIN;
-- Preserve seats and historic booking prices when reverting the old seat-type vocabulary.
UPDATE seats SET seat_type = 'PREMIUM' WHERE seat_type = 'RECLINER';
ALTER TABLE seats DROP CONSTRAINT IF EXISTS seats_seat_type_check;
ALTER TABLE seats ADD CONSTRAINT seats_seat_type_check CHECK (seat_type IN ('REGULAR', 'PREMIUM'));
ALTER TABLE seats DROP COLUMN IF EXISTS row_index;
ALTER TABLE seats DROP COLUMN IF EXISTS col;
ALTER TABLE seats DROP COLUMN IF EXISTS accessible;
ALTER TABLE screens DROP COLUMN IF EXISTS layout_name;
ALTER TABLE screens DROP COLUMN IF EXISTS section_names;
ALTER TABLE shows DROP COLUMN IF EXISTS recliner_price;
COMMIT;
