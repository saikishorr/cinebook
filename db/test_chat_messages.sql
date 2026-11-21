-- Step 3.3 check: proves the chat_messages rules work. Everything is rolled back, so no data is left behind.
-- Run with:  psql -U postgres -d moviebooking -f db/test_chat_messages.sql
\set ON_ERROR_STOP 0
\echo '--- table and columns ---'
SELECT column_name, data_type FROM information_schema.columns
 WHERE table_name = 'chat_messages' ORDER BY ordinal_position;

BEGIN;
-- A throw-away chat link on the latest booking to test with.
CREATE TEMP TABLE t AS
  WITH link AS (INSERT INTO chat_links (code, booking_id)
                SELECT 'Tt3stC0de9', id FROM bookings
                WHERE id NOT IN (SELECT booking_id FROM chat_links) ORDER BY id DESC LIMIT 1
                RETURNING id)
  SELECT id FROM link;
\echo '--- 1. customer message: expect INSERT 0 1'
INSERT INTO chat_messages (chat_link_id, role, content) SELECT id, 'user', 'What time is my show?' FROM t;
\echo '--- 2. assistant answer with outcome and usage: expect INSERT 0 1'
INSERT INTO chat_messages (chat_link_id, role, content, outcome, model, input_tokens, output_tokens)
  SELECT id, 'assistant', 'Your show starts at 7:30 PM.', 'ANSWERED', 'test-model', 900, 12 FROM t;
SAVEPOINT s;
\echo '--- 3. unknown role (only user or assistant allowed): expect ERROR ... violates check constraint'
INSERT INTO chat_messages (chat_link_id, role, content) SELECT id, 'system', 'x' FROM t;
ROLLBACK TO s;
\echo '--- 4. assistant message without an outcome: expect ERROR chat_messages_outcome_matches_role'
INSERT INTO chat_messages (chat_link_id, role, content) SELECT id, 'assistant', 'Hello' FROM t;
ROLLBACK TO s;
\echo '--- 5. customer message with an outcome: expect ERROR chat_messages_outcome_matches_role'
INSERT INTO chat_messages (chat_link_id, role, content, outcome) SELECT id, 'user', 'Hi', 'ANSWERED' FROM t;
ROLLBACK TO s;
\echo '--- 6. unknown outcome: expect ERROR chat_messages_outcome_check'
INSERT INTO chat_messages (chat_link_id, role, content, outcome) SELECT id, 'assistant', 'Hi', 'MAYBE' FROM t;
ROLLBACK TO s;
\echo '--- 7. empty message: expect ERROR chat_messages_content_check'
INSERT INTO chat_messages (chat_link_id, role, content) SELECT id, 'user', '' FROM t;
ROLLBACK TO s;
\echo '--- 8. conversation in order: expect 2 rows, user then assistant'
SELECT role, content, outcome FROM chat_messages WHERE chat_link_id = (SELECT id FROM t) ORDER BY id;
\echo '--- 9. deleting the chat link removes its messages: expect DELETE 1 then count 0'
DELETE FROM chat_links WHERE id = (SELECT id FROM t);
SELECT count(*) FROM chat_messages WHERE chat_link_id = (SELECT id FROM t);
ROLLBACK;
\echo '--- done: all test changes rolled back ---'
