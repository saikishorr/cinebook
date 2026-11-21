-- Phase 3 / Step 3.3: chat assistant conversations.
-- Upgrades an EXISTING database (keeps all data). Safe to run more than once.
-- Needs 002_sms_chat_links.sql first (the chat_links table).
-- Run with:  psql -U postgres -d moviebooking -v ON_ERROR_STOP=1 -f db/migrations/003_chat_messages.sql
BEGIN;

-- One row per message in a chat. A conversation belongs to a chat link, and so to one booking.
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_link_id BIGINT NOT NULL REFERENCES chat_links(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),               -- who wrote it
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 4000),
    -- For assistant messages: how the question was handled.
    --   ANSWERED = answered from the booking / website information
    --   REFUSED  = politely declined (outside what the assistant is for)
    --   ERROR    = the model could not be reached; a fallback message was shown
    outcome TEXT CHECK (outcome IN ('ANSWERED', 'REFUSED', 'ERROR')),
    model TEXT,                                                             -- which model answered
    input_tokens INTEGER CHECK (input_tokens >= 0),                         -- usage, for cost tracking
    output_tokens INTEGER CHECK (output_tokens >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Customer messages have no outcome; assistant messages always have one.
    CONSTRAINT chat_messages_outcome_matches_role
        CHECK ((role = 'user' AND outcome IS NULL) OR (role = 'assistant' AND outcome IS NOT NULL))
);

-- Reading a conversation in order, and counting a link's recent messages for the hourly limit.
CREATE INDEX IF NOT EXISTS idx_chat_messages_link_id ON chat_messages (chat_link_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_link_created ON chat_messages (chat_link_id, created_at);

COMMIT;
