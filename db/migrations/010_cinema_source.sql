BEGIN;
ALTER TABLE cinemas ADD COLUMN IF NOT EXISTS source_key TEXT UNIQUE;
ALTER TABLE cinemas ADD COLUMN IF NOT EXISTS location_precision TEXT
    CHECK (location_precision IN ('building', 'area'));
COMMIT;
