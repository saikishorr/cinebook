-- Undo 003_chat_messages.sql (deletes all saved chat conversations). Only for starting this step again.
BEGIN;
DROP TABLE IF EXISTS chat_messages;
COMMIT;
