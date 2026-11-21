BEGIN;
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
COMMIT;
