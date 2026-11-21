"""Phase 3, Step 3.1 - connect the CineBook Assistant to the Gemini API (free tier).

Run from the project folder (with the virtual environment active):
    python scripts\\check-gemini.py

What it does:
  1. Asks for your Gemini API key (typing is hidden; the key is never printed).
  2. Lists the models your key can use and tries small, fast ones, asking each to reply "OK".
  3. Saves CHAT_PROVIDER, CHAT_MODEL_ID and GEMINI_API_KEY in backend\\.env (a git-ignored file).
Get a key at https://aistudio.google.com -> "Get API key". Uses only Python's standard library.
"""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta"
ENV_FILE = os.path.join("backend", ".env")
# Small, fast models first. Any other "flash-lite", then "flash", model the key offers is tried after these.
PREFERENCES = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
               "gemini-3.5-flash", "gemini-3.1-flash-lite"]
SKIP_WORDS = ("tts", "live", "image", "audio", "embedding", "vision", "robotics", "computer-use")


def call(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{API}/{path}", data=data, method=method,
                                     headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def error_text(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {})
            return f"HTTP {error.code} {detail.get('status', '')}: {detail.get('message', '')}"[:300]
        except Exception:
            return f"HTTP {error.code}"
    return f"{error.__class__.__name__}: {error}"[:300]


def list_models(key: str) -> list[str]:
    names, token = [], ""
    while True:
        page = call("GET", "models?pageSize=200" + (f"&pageToken={token}" if token else ""), key)
        for model in page.get("models", []):
            if "generateContent" in model.get("supportedGenerationMethods", []):
                names.append(model["name"].removeprefix("models/"))
        token = page.get("nextPageToken", "")
        if not token:
            return names


def candidates(names: list[str]) -> list[str]:
    usable = [n for n in names if n.startswith("gemini") and not any(word in n for word in SKIP_WORDS)]
    ordered = [n for n in PREFERENCES if n in usable]
    ordered += sorted(n for n in usable if "flash-lite" in n and n not in ordered)
    ordered += sorted(n for n in usable if "flash" in n and n not in ordered)
    return ordered[:8]


def try_model(key: str, model: str) -> tuple[bool, str]:
    body = {
        "systemInstruction": {"parts": [{"text": "You are a connection test. Reply with exactly: OK"}]},
        "contents": [{"role": "user", "parts": [{"text": "Are you there?"}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 200},
    }
    try:
        result = call("POST", f"models/{model}:generateContent", key, body)
    except Exception as error:
        return False, error_text(error)
    candidate = (result.get("candidates") or [{}])[0]
    text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])).strip()
    usage = result.get("usageMetadata", {})
    detail = (f"answered {text!r} (finish: {candidate.get('finishReason', '?')}; "
              f"{usage.get('promptTokenCount', '?')} tokens in, {usage.get('candidatesTokenCount', '?')} out, "
              f"{usage.get('thoughtsTokenCount', 0)} thinking)")
    return bool(text), detail


def read_env() -> tuple[list[str], str]:
    if not os.path.exists(ENV_FILE):
        return [], "\n"
    with open(ENV_FILE, "r", encoding="utf-8-sig", newline="") as handle:
        raw = handle.read()
    return raw.replace("\r\n", "\n").split("\n"), ("\r\n" if "\r\n" in raw else "\n")


def save(values: dict[str, str]) -> None:
    lines, newline = read_env()
    lines = [line for line in lines if line.split("=", 1)[0] not in values]
    while lines and not lines[-1].strip():
        lines.pop()
    lines += [f"{name}={value}" for name, value in values.items()]
    with open(ENV_FILE, "w", encoding="utf-8", newline="") as handle:
        handle.write(newline.join(lines) + newline)


def main() -> int:
    if not os.path.isdir("backend"):
        print("Run this from the project folder.")
        return 1
    existing = next((line.split("=", 1)[1] for line in read_env()[0] if line.startswith("GEMINI_API_KEY=")), "")
    prompt = "Gemini API key (hidden; press Enter to keep the saved one): " if existing else "Gemini API key (typing is hidden): "
    key = getpass.getpass(prompt).strip() or existing
    if not key:
        print("No key entered - nothing changed.")
        return 1

    print("Checking the Gemini API ...")
    try:
        names = list_models(key)
    except Exception as error:
        print(f"Could not list models: {error_text(error)}")
        print("Check the key (copy it again from https://aistudio.google.com) and your internet connection.")
        return 1
    options = candidates(names)
    print(f"Your key can use {len(names)} models; trying {len(options)} small ones.")
    for model in options:
        ok, detail = try_model(key, model)
        print(f"  {'OK    ' if ok else 'FAILED'}  {model}")
        print(f"          {detail}")
        if ok:
            save({"CHAT_PROVIDER": "gemini", "CHAT_MODEL_ID": model, "GEMINI_API_KEY": key})
            print()
            print(f"Chosen model: {model}")
            print(f"Saved CHAT_PROVIDER, CHAT_MODEL_ID and GEMINI_API_KEY in {ENV_FILE} (git-ignored; the key was not printed).")
            return 0
    print()
    print("No model answered. Nothing was changed. Paste this output (it contains no key) to your guide/trainer.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
