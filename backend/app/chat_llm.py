"""Phase 3: the connection to the AI model - the only file that knows which model service is used.

generate(system, messages) sends the instructions and the conversation to the model chosen by
CHAT_PROVIDER and returns its reply. Everything else in the assistant is independent of the vendor.

  gemini  - Google Gemini API (API key in GEMINI_API_KEY)
  fake    - a stand-in used by the automated tests: no network, no cost
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from app.config import settings

logger = logging.getLogger(__name__)
TIMEOUT_SECONDS = 20
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"


@dataclass
class LlmReply:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmError(Exception):
    """The model could not produce a reply (network problem, rate limit, blocked or empty answer)."""


def is_configured() -> bool:
    if not settings.chat_model_id:
        return False
    if settings.chat_provider == "gemini":
        return bool(settings.gemini_api_key)
    return settings.chat_provider == "fake"


def generate(system: str, messages: list[dict]) -> LlmReply:
    """messages: [{"role": "user" | "assistant", "content": "..."}], oldest first, ending with the new question."""
    provider = settings.chat_provider
    if provider == "gemini":
        return _gemini(system, messages)
    if provider == "fake":
        return LlmReply(text=fake_responder(system, messages), model=settings.chat_model_id or "fake")
    raise LlmError(f"Unknown CHAT_PROVIDER: {provider}")


# ---------------------------------------------------------------- Google Gemini API
def _gemini(system: str, messages: list[dict]) -> LlmReply:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        # Gemini calls the assistant's turns "model".
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                     for m in messages],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": settings.chat_max_output_tokens},
    }
    request = urllib.request.Request(
        f"{GEMINI_API}/models/{settings.chat_model_id}:generateContent",
        data=json.dumps(body).encode("utf-8"), method="POST",
        # The key travels in a header, never in the address, so it cannot end up in logs.
        headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {})
            reason = f"{detail.get('status', '')} {detail.get('message', '')}".strip()
        except Exception:
            reason = ""
        raise LlmError(f"Gemini HTTP {error.code} {reason}"[:300]) from None
    except Exception as error:                       # timeouts, DNS, connection resets
        raise LlmError(f"Gemini request failed: {error.__class__.__name__}") from None

    candidate = (result.get("candidates") or [{}])[0]
    text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])).strip()
    if not text:
        raise LlmError(f"Gemini returned no text (finish reason: {candidate.get('finishReason', 'unknown')})")
    usage = result.get("usageMetadata", {})
    return LlmReply(text=text, model=settings.chat_model_id,
                    input_tokens=usage.get("promptTokenCount"), output_tokens=usage.get("candidatesTokenCount"))


# ---------------------------------------------------------------- Stand-in for tests
def _default_fake(system: str, messages: list[dict]) -> str:
    return "[ANSWER] This is a test reply."


# Tests replace this function to control what "the model" says and to inspect what it was sent.
fake_responder: Callable[[str, list[dict]], str] = _default_fake
