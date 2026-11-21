-- Add the two example screens. ON CONFLICT keeps this seed repeatable.
INSERT INTO screens (cinema_id, name, total_rows, seats_per_row)
SELECT c.id, v.name, v.rows, v.columns FROM cinemas c
CROSS JOIN (VALUES ('Screen 1', 8, 12), ('Screen 2', 6, 10)) v(name, rows, columns)
WHERE c.osm_id IS NULL AND c.name = 'CineBook Demo Cinema'
ON CONFLICT (cinema_id, name) DO UPDATE
SET total_rows = EXCLUDED.total_rows,
    seats_per_row = EXCLUDED.seats_per_row;

-- Build each screen's seat grid with generate_series; rear rows are premium.
INSERT INTO seats (screen_id, row_label, seat_number, seat_type)
SELECT s.id,
       chr(64 + r.row_no),
       n.seat_no,
       CASE
           WHEN s.name = 'Screen 1' AND r.row_no IN (7, 8) THEN 'PREMIUM'
           WHEN s.name = 'Screen 2' AND r.row_no = 6 THEN 'PREMIUM'
           ELSE 'REGULAR'
       END
FROM screens AS s
CROSS JOIN LATERAL generate_series(1, s.total_rows) AS r(row_no)
CROSS JOIN LATERAL generate_series(1, s.seats_per_row) AS n(seat_no)
WHERE s.name IN ('Screen 1', 'Screen 2') AND s.cinema_id IN (SELECT id FROM cinemas WHERE osm_id IS NULL AND name = 'CineBook Demo Cinema')
ON CONFLICT (screen_id, row_label, seat_number) DO UPDATE
SET seat_type = EXCLUDED.seat_type;

-- Three fictional films in a Hindi and English mix.
INSERT INTO movies (title, description, duration_minutes, language, certificate, poster_url)
SELECT v.title, v.description, v.duration_minutes, v.language, v.certificate, v.poster_url
FROM (VALUES
    ('Monsoon Junction', 'Two strangers uncover a family secret during a rain-soaked train journey.', 142, 'Hindi', 'UA', NULL),
    ('The Last Signal', 'A radio astronomer receives a message that may change life on Earth.', 128, 'English', 'UA', NULL),
    ('Chandni Chowk Express', 'A quick-witted chef races across Delhi to save her family restaurant.', 119, 'Hindi', 'U', NULL)
) AS v(title, description, duration_minutes, language, certificate, poster_url)
WHERE NOT EXISTS (SELECT 1 FROM movies AS m WHERE m.title = v.title);

-- Schedule four daily shows for each screen for the next seven Kolkata calendar days.
-- Movie selection rotates through the three sample films over the full schedule.
WITH movie_list AS (
    SELECT id, row_number() OVER (ORDER BY title) AS movie_no
    FROM movies
    WHERE title IN ('Monsoon Junction', 'The Last Signal', 'Chandni Chowk Express')
      -- Once real movies are imported (scripts/import_tmdb.py) the samples are hidden;
      -- then this seed must not hand the coming week's shows back to them.
      AND is_active
), schedule AS (
    SELECT s.id AS screen_id,
           ((now() AT TIME ZONE 'Asia/Kolkata')::date + d.day_offset + t.show_time)
               AT TIME ZONE 'Asia/Kolkata' AS start_time,
           row_number() OVER (ORDER BY d.day_offset, t.time_no, s.name) AS show_no
    FROM screens AS s
    CROSS JOIN generate_series(1, 7) AS d(day_offset)
    CROSS JOIN (VALUES
        (1, TIME '10:00'),
        (2, TIME '14:00'),
        (3, TIME '18:00'),
        (4, TIME '21:30')
    ) AS t(time_no, show_time)
    WHERE s.name IN ('Screen 1', 'Screen 2') AND s.cinema_id IN (SELECT id FROM cinemas WHERE osm_id IS NULL AND name = 'CineBook Demo Cinema')
)
INSERT INTO shows (movie_id, screen_id, start_time, regular_price, premium_price, status)
SELECT m.id, schedule.screen_id, schedule.start_time, 200.00, 350.00, 'SCHEDULED'
FROM schedule
JOIN movie_list AS m ON m.movie_no = ((schedule.show_no - 1) % 3) + 1
ON CONFLICT (screen_id, start_time) DO NOTHING;

-- Add catalog details to both new and previously seeded films.
UPDATE movies SET genres = ARRAY['Drama', 'Mystery'], release_date = DATE '2026-10-03'
WHERE title = 'Monsoon Junction';
UPDATE movies SET genres = ARRAY['Science Fiction', 'Thriller'], release_date = DATE '2026-10-10'
WHERE title = 'The Last Signal';
UPDATE movies SET genres = ARRAY['Comedy', 'Adventure'], release_date = DATE '2026-10-17'
WHERE title = 'Chandni Chowk Express';
