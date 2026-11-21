-- Undo 002_sms_chat_links.sql (removes the demo SMS data). Only for starting this step again.
BEGIN;
DROP TABLE IF EXISTS sms_messages;
DROP TABLE IF EXISTS chat_links;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_sms_consent_needs_phone;
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_sms_phone_format;
ALTER TABLE bookings DROP COLUMN IF EXISTS sms_consent;
ALTER TABLE bookings DROP COLUMN IF EXISTS sms_phone;
COMMIT;
