"""Help & info: the cinema's published policies and facilities.

One source for two readers: the website's Help page (GET /help) and the chat assistant,
which may answer only from this text. Edit app/content/help_info.json to change both.
"""
import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).parent / "content" / "help_info.json"


@lru_cache
def load_help() -> dict:
    with open(_FILE, encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def help_as_text() -> str:
    """The same content as plain text, for the assistant's instructions."""
    data = load_help()
    lines = [data["notice"], ""]
    for section in data["sections"]:
        lines.append(f"## {section['title']}")
        for item in section["items"]:
            lines.append(f"Q: {item['q']}")
            lines.append(f"A: {item['a']}")
        lines.append("")
    return "\n".join(lines).strip()
