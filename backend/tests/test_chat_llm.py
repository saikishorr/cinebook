"""Phase 3: the model connections, tested without any network call."""
import io
import json
import urllib.error

import pytest

from app import chat_llm
from app.config import settings

MESSAGES = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "[ANSWER] a1"},
            {"role": "user", "content": "q2"}]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "gemini")
    monkeypatch.setattr(settings, "chat_model_id", "gemini-test")
    monkeypatch.setattr(settings, "gemini_api_key", "SECRET-KEY-123")
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["url"], sent["headers"], sent["body"] = request.full_url, dict(request.header_items()), json.loads(request.data)
        if isinstance(sent.get("raise"), Exception):
            raise sent["raise"]
        return _Response(json.dumps(sent.get("result", {
            "candidates": [{"content": {"parts": [{"text": "[ANSWER] Hello"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 5}})).encode())

    monkeypatch.setattr(chat_llm.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_gemini_request_and_reply(gemini):
    reply = chat_llm.generate("SYSTEM TEXT", MESSAGES)
    assert reply.text == "[ANSWER] Hello" and reply.input_tokens == 900 and reply.output_tokens == 5
    assert gemini["url"].endswith("/models/gemini-test:generateContent")
    assert "SECRET-KEY-123" not in gemini["url"]                                # key is in a header, not the address
    assert gemini["headers"]["X-goog-api-key"] == "SECRET-KEY-123"
    assert gemini["body"]["systemInstruction"]["parts"][0]["text"] == "SYSTEM TEXT"
    assert [c["role"] for c in gemini["body"]["contents"]] == ["user", "model", "user"]
    assert gemini["body"]["generationConfig"]["maxOutputTokens"] == settings.chat_max_output_tokens


def test_gemini_error_does_not_leak_the_key(gemini):
    gemini["raise"] = urllib.error.HTTPError("https://x/?key=SECRET-KEY-123", 429, "Too Many", {},
                                             io.BytesIO(b'{"error":{"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded"}}'))
    with pytest.raises(chat_llm.LlmError) as caught:
        chat_llm.generate("s", MESSAGES)
    assert "429" in str(caught.value) and "RESOURCE_EXHAUSTED" in str(caught.value)
    assert "SECRET-KEY-123" not in str(caught.value)


def test_gemini_empty_answer_is_an_error(gemini):
    gemini["result"] = {"candidates": [{"finishReason": "SAFETY"}]}
    with pytest.raises(chat_llm.LlmError, match="SAFETY"):
        chat_llm.generate("s", MESSAGES)


def test_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "chat_provider", "gemini")
    monkeypatch.setattr(settings, "chat_model_id", "gemini-test")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert chat_llm.is_configured() is False                                    # Gemini needs a key
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    assert chat_llm.is_configured() is True
    monkeypatch.setattr(settings, "chat_model_id", "")
    assert chat_llm.is_configured() is False                                    # no model = chat off
