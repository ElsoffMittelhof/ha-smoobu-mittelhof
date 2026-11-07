"""Read-only Mittelhof house-arrival invoice number proposal.

No number is allocated in HA. A private SQLite journal must prohibit collisions.
"""
from __future__ import annotations

from datetime import date
import re

_PREFIX = re.compile(r"^(?:Mittelhof\s+)?(?:Ferienhaus|Ferienwohnung|Wohnung|Apartment|Haus|FH)\s*(13|14|15)(?:\s*[-–:]\s*.*)?$", re.IGNORECASE)
_BARE = re.compile(r"^(13|14|15)$")


def house_from_label(label: str) -> str | None:
    """Return a house only when its configured name is unambiguous."""
    normalized = str(label or "").strip()
    match = _PREFIX.fullmatch(normalized) or _BARE.fullmatch(normalized)
    return match.group(1) if match else None


def planned_number(label: str, arrival: str) -> str | None:
    house = house_from_label(label)
    if house is None or not isinstance(arrival, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", arrival):
        return None
    try:
        day = date.fromisoformat(arrival)
    except ValueError:
        return None
    return f"{house}{day:%Y%m%d}"
