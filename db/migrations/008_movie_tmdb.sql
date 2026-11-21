-- Movies imported from TMDB (The Movie Database) remember their TMDB id,
-- so a re-import updates the same row instead of adding a duplicate.
BEGIN;
ALTER TABLE movies ADD COLUMN IF NOT EXISTS tmdb_id BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS movies_tmdb_id_key ON movies (tmdb_id);
COMMIT;
