BEGIN;
-- Global screen-name uniqueness cannot represent multiple 'Audi 1' names.
-- Prefix only duplicates with their cinema id before restoring the old constraint.
UPDATE screens SET name = name || ' (cinema ' || cinema_id || ')'
WHERE name IN (SELECT name FROM screens GROUP BY name HAVING count(*) > 1);
ALTER TABLE screens DROP CONSTRAINT IF EXISTS screens_cinema_name_key;
ALTER TABLE screens DROP COLUMN IF EXISTS format;
ALTER TABLE screens DROP COLUMN IF EXISTS cinema_id;
ALTER TABLE screens ADD CONSTRAINT screens_name_key UNIQUE (name);
DROP TABLE IF EXISTS cinemas;
COMMIT;
