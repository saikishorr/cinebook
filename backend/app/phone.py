"""Phone number helpers for the demo SMS feature.

Numbers are stored in international (E.164) form, for example +919812345678.
Indian mobile numbers typed the usual ways are converted automatically:
9812345678, 09812345678, 919812345678, +91 98123-45678 -> +919812345678
"""
import re

_E164 = re.compile(r"\+[1-9]\d{7,14}")


def normalize_phone(raw: str | None) -> str:
    """Return the number in +<country><number> form, or raise ValueError."""
    value = re.sub(r"[\s\-().]", "", raw or "")
    if value.startswith("00"):
        value = "+" + value[2:]
    if re.fullmatch(r"[6-9]\d{9}", value):          # 10-digit Indian mobile
        return "+91" + value
    if re.fullmatch(r"0[6-9]\d{9}", value):         # with a leading 0
        return "+91" + value[1:]
    if re.fullmatch(r"91[6-9]\d{9}", value):        # 91 without the +
        return "+" + value
    if _E164.fullmatch(value):
        return value
    raise ValueError("not a valid phone number")


def parse_number_list(text: str) -> frozenset[str]:
    """Turn 'a, b, c' from the settings into a set of valid numbers (invalid entries are ignored)."""
    numbers = set()
    for item in (text or "").split(","):
        try:
            numbers.add(normalize_phone(item))
        except ValueError:
            continue
    return frozenset(numbers)


def mask_phone(phone: str | None) -> str | None:
    """Show only the country code and the last four digits: +91 ******5678."""
    if not phone:
        return None
    country = "+91" if phone.startswith("+91") else phone[:3]
    return f"{country} {'*' * (len(phone) - len(country) - 4)}{phone[-4:]}"
