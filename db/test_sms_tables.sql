-- Step 2.2 check: proves the new rules work. Everything is rolled back, so no data is left behind.
-- Run with:  psql -U postgres -d moviebooking -f db/test_sms_tables.sql
\set ON_ERROR_STOP 0
\echo '--- columns and tables ---'
SELECT column_name, data_type, column_default FROM information_schema.columns
 WHERE table_name = 'bookings' AND column_name IN ('sms_phone', 'sms_consent') ORDER BY column_name;
SELECT table_name FROM information_schema.tables WHERE table_name IN ('chat_links', 'sms_messages') ORDER BY 1;

BEGIN;
-- A throw-away booking to test with.
CREATE TEMP TABLE t AS SELECT id FROM bookings ORDER BY id DESC LIMIT 1;
\echo '--- 1. valid phone + consent: expect UPDATE 1'
UPDATE bookings SET sms_phone = '+919800000000', sms_consent = TRUE WHERE id = (SELECT id FROM t);
SAVEPOINT s;
\echo '--- 2. bad phone format: expect ERROR bookings_sms_phone_format'
UPDATE bookings SET sms_phone = '98000 00000' WHERE id = (SELECT id FROM t);
ROLLBACK TO s;
\echo '--- 3. consent without a phone: expect ERROR bookings_sms_consent_needs_phone'
UPDATE bookings SET sms_phone = NULL, sms_consent = TRUE WHERE id = (SELECT id FROM t);
ROLLBACK TO s;
\echo '--- 4. chat link: expect INSERT 0 1'
INSERT INTO chat_links (code, booking_id) SELECT 'Ab3dEf7hJk', id FROM t;
SAVEPOINT s2;
\echo '--- 5. second link for the same booking: expect ERROR duplicate key (one link per booking)'
INSERT INTO chat_links (code, booking_id) SELECT 'Zz9yXx8wVv', id FROM t;
ROLLBACK TO s2;
\echo '--- 6. badly formed code: expect ERROR chat_links_code_check'
INSERT INTO chat_links (code, booking_id) SELECT 'short', id FROM t;
ROLLBACK TO s2;
\echo '--- 7. demo SMS: expect INSERT 0 1'
INSERT INTO sms_messages (booking_id, to_phone, body) SELECT id, '+919800000000', 'CineBook: test message' FROM t;
SAVEPOINT s3;
\echo '--- 8. same SMS again (a retry): expect ERROR duplicate key'
INSERT INTO sms_messages (booking_id, to_phone, body) SELECT id, '+919800000000', 'CineBook: test message' FROM t;
ROLLBACK TO s3;
\echo '--- 9. inbox query uses the new index: expect "Index Scan" or "Bitmap" on idx_sms_messages_to_phone_created'
SET LOCAL enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT body FROM sms_messages WHERE to_phone = '+919800000000' ORDER BY created_at DESC;
ROLLBACK;
\echo '--- done: all test changes rolled back ---'
