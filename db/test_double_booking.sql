-- Double-booking test: everything is rolled back at the end
BEGIN;

-- Two customers
INSERT INTO customers (full_name, email)
VALUES ('Test One', 'one@test.com'), ('Test Two', 'two@test.com');

-- Each makes a booking for the same (first) show
INSERT INTO bookings (booking_ref, customer_id, show_id, status, total_amount)
SELECT 'BKTEST1', id, (SELECT min(id) FROM shows), 'CONFIRMED', 200
FROM customers WHERE email = 'one@test.com';

INSERT INTO bookings (booking_ref, customer_id, show_id, status, total_amount)
SELECT 'BKTEST2', id, (SELECT min(id) FROM shows), 'CONFIRMED', 200
FROM customers WHERE email = 'two@test.com';

-- Customer 1 takes the first seat of that show's screen  -> should SUCCEED
INSERT INTO booking_seats (booking_id, show_id, seat_id, price)
SELECT b.id, b.show_id,
       (SELECT min(s.id) FROM seats s JOIN shows sh ON sh.screen_id = s.screen_id WHERE sh.id = b.show_id),
       200
FROM bookings b WHERE b.booking_ref = 'BKTEST1';

-- Customer 2 tries the SAME seat for the SAME show -> should FAIL
INSERT INTO booking_seats (booking_id, show_id, seat_id, price)
SELECT b.id, b.show_id,
       (SELECT min(s.id) FROM seats s JOIN shows sh ON sh.screen_id = s.screen_id WHERE sh.id = b.show_id),
       200
FROM bookings b WHERE b.booking_ref = 'BKTEST2';

ROLLBACK;