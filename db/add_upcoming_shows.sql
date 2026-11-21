-- Adds sample shows for today (remaining) and the next 7 days: 4 shows a day on each screen.
-- Safe to run at any time and as often as you like: existing shows and bookings are never changed
-- (ON CONFLICT DO NOTHING). Use it when the showtimes on the website have run out.
-- Run with:  psql -U postgres -d moviebooking -f db/add_upcoming_shows.sql
INSERT INTO shows (movie_id, screen_id, start_time, regular_price, premium_price, status)
SELECT m.id, s.id, slot.start_time, 200.00, 350.00, 'SCHEDULED'
FROM screens AS s
CROSS JOIN LATERAL (
    SELECT ((now() AT TIME ZONE 'Asia/Kolkata')::date + d.day_offset + t.show_time) AT TIME ZONE 'Asia/Kolkata' AS start_time,
           -- A number that depends only on the calendar day, the time slot and the screen, so every run picks the same movie.
           ((now() AT TIME ZONE 'Asia/Kolkata')::date + d.day_offset - DATE '2026-01-01') * 4 + t.time_no + s.id AS slot_no
    FROM generate_series(0, 7) AS d(day_offset)
    CROSS JOIN (VALUES (1, TIME '10:00'), (2, TIME '14:00'), (3, TIME '18:00'), (4, TIME '21:30')) AS t(time_no, show_time)
) AS slot
JOIN (SELECT id, row_number() OVER (ORDER BY title) - 1 AS movie_no, count(*) OVER () AS movie_count
      FROM movies WHERE is_active) AS m
  ON m.movie_no = slot.slot_no % m.movie_count
WHERE slot.start_time > now() AND s.cinema_id IN (SELECT id FROM cinemas WHERE osm_id IS NULL AND name = 'CineBook Demo Cinema')
ON CONFLICT (screen_id, start_time) DO NOTHING;

SELECT count(*) AS upcoming_shows FROM shows WHERE start_time > now() AND status = 'SCHEDULED';
