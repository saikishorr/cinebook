"""Phase 3: the chat assistant. A stand-in model is used, so these tests are fast, free and repeatable.

They prove the rules that do not depend on the model: what the model is (and is not) sent,
how its reply is checked, and the limits. Step 3.6 tests the real model's judgement.
"""
import pytest

from app import chat_llm
from app.chat_engine import (ERROR_TEXT, INSTRUCTIONS, MAX_REPLY_CHARS, REFUSAL_TEXT, UNKNOWN_TEXT,
                             history_for_model, parse_reply)
from app.config import settings
from tests.conftest import new_code, run_sql


def _send(client, code, message):
    return client.post(f"/chat-links/{code}/messages", json={"message": message})


@pytest.fixture
def spy(monkeypatch):
    """Records what the stand-in model receives and lets a test choose its reply."""
    record = {"calls": [], "reply": "[ANSWER] Your show is at 7:30 PM."}

    def responder(system, messages):
        record["calls"].append({"system": system, "messages": messages})
        if isinstance(record["reply"], Exception):
            raise record["reply"]
        return record["reply"]

    monkeypatch.setattr(chat_llm, "fake_responder", responder)
    return record


# ---------------------------------------------------------------- conversation basics
def test_new_chat_is_empty_and_enabled(client, sample):
    data = client.get(f"/chat-links/{sample['code']}/messages").json()
    assert data["enabled"] is True
    assert data["messages"] == []
    assert data["remaining_this_hour"] == settings.chat_messages_per_hour
    assert data["max_message_chars"] == settings.chat_max_message_chars


def test_question_and_answer_are_saved_in_order(client, sample, spy):
    response = _send(client, sample["code"], "  What time is my show?  ")
    assert response.status_code == 200
    data = response.json()
    assert data["user_message"]["content"] == "What time is my show?"          # trimmed
    assert data["reply"]["content"] == "Your show is at 7:30 PM."              # tag removed
    assert data["reply"]["outcome"] == "ANSWERED"
    assert data["remaining_this_hour"] == settings.chat_messages_per_hour - 1
    history = client.get(f"/chat-links/{sample['code']}/messages").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["outcome"] is None and history[1]["outcome"] == "ANSWERED"


def test_earlier_turns_are_sent_to_the_model(client, sample, spy):
    _send(client, sample["code"], "What time is my show?")
    spy["reply"] = "[REFUSE]"
    _send(client, sample["code"], "Tell me a joke")
    spy["reply"] = "[ANSWER] Screen 1."
    _send(client, sample["code"], "And which screen?")
    sent = spy["calls"][-1]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user", "assistant", "user"]
    assert sent[1]["content"] == "[ANSWER] Your show is at 7:30 PM."            # earlier replies keep their tags
    assert sent[3]["content"] == "[REFUSE]"
    assert sent[-1]["content"] == "And which screen?"


# ---------------------------------------------------------------- what the model is told
def test_model_gets_this_booking_and_website_information(client, sample, spy):
    _send(client, sample["code"], "Hello")
    system = spy["calls"][0]["system"]
    assert sample["booking_ref"] in system
    assert "Customer first name: Test" in system
    assert "CURRENT DATE AND TIME" in system and "India time" in system
    assert "NOW SHOWING" in system and "SHOWTIMES" in system and "HELP AND INFO" in system
    assert "Seats are held for 5 minutes" in system                             # from the Help page
    assert REFUSAL_TEXT not in system                                           # the model never writes the refusal


def test_model_never_gets_contact_details_or_other_bookings(client, sample, spy, database_url):
    _send(client, sample["code"], "What is my email and phone number?")
    sent = spy["calls"][0]["system"] + " ".join(m["content"] for m in spy["calls"][0]["messages"][:-1])
    assert "@example.com" not in sent.replace("help@cinebook.example", "")      # the customer's email is absent
    assert sample["phone"] not in sent and sample["phone"][3:] not in sent      # so is the phone number
    assert "Person" not in sent                                                 # and the surname
    other = run_sql(database_url, "SELECT booking_ref FROM bookings WHERE id <> %s ORDER BY id DESC LIMIT 1",
                    (sample["booking_id"],))
    if other:
        assert other[0] not in sent                                             # no other customer's booking


# ---------------------------------------------------------------- checking the model's reply
def test_refusal_always_uses_the_fixed_sentence(client, sample, spy):
    spy["reply"] = "[REFUSE] The capital of France is Paris, but I should not say that."
    data = _send(client, sample["code"], "What is the capital of France?").json()
    assert data["reply"]["outcome"] == "REFUSED"
    assert data["reply"]["content"] == REFUSAL_TEXT                             # nothing the model wrote is shown


@pytest.mark.parametrize("raw, outcome, shown", [
    ("[ANSWER] Doors open 15 minutes before.", "ANSWERED", "Doors open 15 minutes before."),
    ("[answer]   Lower-case tag is accepted.", "ANSWERED", "Lower-case tag is accepted."),
    ("No tag at all.", "ANSWERED", "No tag at all."),
    ("[REFUSE]", "REFUSED", REFUSAL_TEXT),
    ("[refuse] anything", "REFUSED", REFUSAL_TEXT),
    ("[ANSWER] Sure! [REFUSE]", "REFUSED", REFUSAL_TEXT),
    ("[ANSWER]", "REFUSED", REFUSAL_TEXT),
    ("", "REFUSED", REFUSAL_TEXT),
])
def test_parse_reply(raw, outcome, shown):
    assert parse_reply(raw) == (outcome, shown)


def test_reply_that_repeats_the_instructions_is_never_shown():
    # A model sometimes "answers" by quoting one of its own rules. That must not reach the customer.
    rule = next(line for line in INSTRUCTIONS.splitlines() if line.startswith("- You know only"))
    assert parse_reply("[ANSWER] " + rule[2:]) == ("REFUSED", REFUSAL_TEXT)
    assert parse_reply(rule[2:]) == ("REFUSED", REFUSAL_TEXT)
    assert parse_reply("[ANSWER] My rules say: answer only from the information in this message.")[0] == "REFUSED"


@pytest.mark.parametrize("reply", [
    UNKNOWN_TEXT,
    "Please arrive at least 20 minutes before the show. Doors open 15 minutes before the start time.",
    "I cannot cancel your booking. You can cancel at the box office up to 2 hours before the show starts.",
    "Hello Asha! I am the CineBook Assistant. I can help with your booking, showtimes and cinema information.",
])
def test_normal_answers_are_not_mistaken_for_instructions(reply):
    assert parse_reply("[ANSWER] " + reply) == ("ANSWERED", reply)


def test_very_long_reply_is_shortened():
    outcome, text = parse_reply("[ANSWER] " + "word " * 1000)
    assert outcome == "ANSWERED" and len(text) <= MAX_REPLY_CHARS + 3 and text.endswith("...")


def test_history_keeps_complete_pairs_and_skips_failed_turns():
    rows = [
        {"role": "user", "content": "q1", "outcome": None},
        {"role": "assistant", "content": "a1", "outcome": "ANSWERED"},
        {"role": "user", "content": "q2", "outcome": None},
        {"role": "assistant", "content": ERROR_TEXT, "outcome": "ERROR"},        # failed turn: left out
        {"role": "user", "content": "q3", "outcome": None},                     # unanswered: left out
    ]
    assert history_for_model(rows, 8) == [{"role": "user", "content": "q1"},
                                          {"role": "assistant", "content": "[ANSWER] a1"}]
    assert history_for_model(rows, 0) == []


# ---------------------------------------------------------------- limits and failures
def test_message_that_is_too_long_is_refused(client, sample, spy):
    response = _send(client, sample["code"], "x" * (settings.chat_max_message_chars + 1))
    assert response.status_code == 422
    assert spy["calls"] == []                                                   # the model was never called


def test_blank_message_is_refused(client, sample, spy):
    assert _send(client, sample["code"], "   ").status_code == 422
    assert spy["calls"] == []


def test_hourly_limit_per_link(client, sample, spy, monkeypatch):
    monkeypatch.setattr(settings, "chat_messages_per_hour", 2)
    assert _send(client, sample["code"], "one").status_code == 200
    assert _send(client, sample["code"], "two").json()["remaining_this_hour"] == 0
    response = _send(client, sample["code"], "three")
    assert response.status_code == 429
    assert "message limit" in response.json()["detail"]
    assert len(spy["calls"]) == 2


def test_model_failure_gives_a_polite_fallback(client, sample, spy):
    spy["reply"] = chat_llm.LlmError("Gemini HTTP 429 RESOURCE_EXHAUSTED")
    data = _send(client, sample["code"], "What time is my show?").json()
    assert data["reply"]["outcome"] == "ERROR"
    assert data["reply"]["content"] == ERROR_TEXT
    assert "429" not in data["reply"]["content"]                                # technical details are not shown


def test_chat_is_off_without_a_model(client, sample, monkeypatch):
    monkeypatch.setattr(settings, "chat_model_id", "")
    assert client.get(f"/chat-links/{sample['code']}/messages").json()["enabled"] is False
    assert _send(client, sample["code"], "Hello").status_code == 503


def test_unknown_and_revoked_links(client, sample, database_url):
    assert _send(client, new_code(), "Hello").status_code == 404
    assert client.get("/chat-links/short/messages").status_code == 404
    run_sql(database_url, "UPDATE chat_links SET revoked_at = now() WHERE code = %s", (sample["code"],))
    assert _send(client, sample["code"], "Hello").status_code == 410
    assert client.get(f"/chat-links/{sample['code']}/messages").status_code == 410
