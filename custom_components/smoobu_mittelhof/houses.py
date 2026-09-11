"""Configured Smoobu accommodation helpers."""
from __future__ import annotations

from typing import Any

from homeassistant.util import slugify


def parse_houses(value: Any) -> dict[int, str]:
    """Parse houses from dict/list or newline text (apartment_id=Name)."""
    result: dict[int, str] = {}

    if isinstance(value, dict):
        for raw_id, raw_name in value.items():
            try:
                apartment_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            name = str(raw_name or "").strip()
            if apartment_id > 0 and name:
                result[apartment_id] = name
        return result

    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                apartment_id = int(item.get("id", item.get("apartment_id")))
            except (TypeError, ValueError):
                continue
            name = str(item.get("name", item.get("house")) or "").strip()
            if apartment_id > 0 and name:
                result[apartment_id] = name
        return result

    for line in str(value or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            raw_id, raw_name = line.split("=", 1)
        elif ":" in line:
            raw_id, raw_name = line.split(":", 1)
        else:
            continue
        try:
            apartment_id = int(raw_id.strip())
        except ValueError:
            continue
        name = raw_name.strip()
        if apartment_id > 0 and name:
            result[apartment_id] = name

    return result


def format_houses(houses: dict[int, str]) -> str:
    """Return canonical editable text."""
    return "\n".join(f"{apartment_id}={name}" for apartment_id, name in houses.items())


def discover_houses(bookings: list[dict[str, Any]]) -> dict[int, str]:
    """Discover apartment IDs and names from reservation rows."""
    result: dict[int, str] = {}
    for booking in bookings:
        if not isinstance(booking, dict):
            continue
        apartment = booking.get("apartment") or {}
        try:
            apartment_id = int(apartment.get("id"))
        except (TypeError, ValueError):
            continue
        if apartment_id <= 0:
            continue
        name = str(apartment.get("name") or f"Apartment {apartment_id}").strip()
        result.setdefault(apartment_id, name)
    return result


def house_slug(name: str, apartment_id: int | None = None) -> str:
    """Stable HA-friendly slug for a configured accommodation."""
    value = slugify(str(name or "").strip())
    if value:
        return value
    return f"apartment_{apartment_id}" if apartment_id else "apartment"
