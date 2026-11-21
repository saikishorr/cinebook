"""Validate editable demo floor plans and turn occupied cells into seat records."""
import json
import re
from pathlib import Path

LAYOUT_ROOT = Path(__file__).resolve().parents[2] / "db/data/seat_layouts"
SEAT_TYPES = {"R": "REGULAR", "P": "PREMIUM", "L": "RECLINER", "W": "REGULAR"}
DEFAULT_SECTIONS = {"R": "Regular", "P": "Prime", "L": "Recliner"}


def validate_layout(data, filename="<layout>"):
    def fail(row, message):
        raise ValueError(f"{filename}: row {row}: {message}")
    if not isinstance(data, dict):
        fail("<layout>", "expected a JSON object")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        fail("<layout>", "name must be a nonempty string")
    rows = data.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        fail("<layout>", "provide 1 to 30 rows")
    labels, width, seat_count = set(), None, 0
    for index, value in enumerate(rows):
        if not isinstance(value, str) or len(parts := value.split(maxsplit=1)) != 2:
            fail(index + 1, "expected '<label> <pattern>'")
        label, pattern = parts
        if not re.fullmatch(r"[A-Z]+", label):
            fail(label, "label must match [A-Z]+")
        if label in labels:
            fail(label, "duplicate row label")
        labels.add(label)
        if not re.fullmatch(r"[RPLW.]+", pattern):
            fail(label, "pattern may contain only R, P, L, W and '.'")
        if len(pattern) > 40:
            fail(label, "at most 40 grid columns are allowed")
        if width is not None and len(pattern) != width:
            fail(label, f"width {len(pattern)} differs from {width}; pad rows with '.'")
        width = len(pattern)
        seat_count += sum(char != "." for char in pattern)
    if not seat_count:
        fail("<layout>", "at least one seat is required")
    sections = data.get("section_names", DEFAULT_SECTIONS)
    if not isinstance(sections, dict) or any(k not in DEFAULT_SECTIONS or not isinstance(v, str) or not v.strip()
                                               for k, v in sections.items()):
        fail("<layout>", "section_names maps R, P and L to nonempty names")
    return {**data, "section_names": {**DEFAULT_SECTIONS, **sections}}


def load_layout(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: row <file>: cannot read layout ({error})") from None
    return validate_layout(data, str(path))


def build_seats(layout):
    rows = []
    for row_index, value in enumerate(layout["rows"]):
        label, pattern = value.split(maxsplit=1)
        number = 0
        for col, char in enumerate(pattern, start=1):
            if char == ".":
                continue
            number += 1
            rows.append({"row_label": label, "seat_number": number, "seat_type": SEAT_TYPES[char],
                         "row_index": row_index, "col": col, "accessible": char == "W"})
    return rows


def select_layout(source_key, screen_name, template, root=LAYOUT_ROOT):
    # Both components come from editable files; keep overrides inside the layout directory.
    for component in (source_key, screen_name, template):
        if not component or component in (".", "..") or any(c in component for c in '/\\:\0'):
            raise ValueError("Layout source key, screen name and template must be plain path components")
    override = Path(root) / "screens" / source_key / f"{screen_name}.json"
    path = override if override.exists() else Path(root) / f"{template}.json"
    name = str(path.relative_to(root).with_suffix("")).replace("\\", "/")
    return name, load_layout(path)
