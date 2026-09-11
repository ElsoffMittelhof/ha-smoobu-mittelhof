"""Booking helpers."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .const import VALID_BOOKING_TYPES


def valid_bookings(
    bookings: Iterable[dict[str, Any]],
    apartment_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Filter reservation-like records, optionally to configured apartments, and dedupe."""
    allowed = {int(value) for value in apartment_ids} if apartment_ids is not None else None
    current: dict[str, dict[str, Any]] = {}

    for booking in bookings:
        if not isinstance(booking, dict) or booking.get("type") not in VALID_BOOKING_TYPES:
            continue
        apartment = booking.get("apartment") or {}
        try:
            apartment_id = int(apartment.get("id"))
        except (TypeError, ValueError):
            continue
        if allowed is not None and apartment_id not in allowed:
            continue
        if not booking.get("id"):
            continue

        key = str(booking["id"])
        if key not in current or booking.get("type") == "modification of booking":
            current[key] = booking

    return list(current.values())


def house_bookings(bookings: Iterable[dict[str, Any]], apartment_id: int) -> list[dict[str, Any]]:
    values = [
        booking
        for booking in valid_bookings(bookings, {apartment_id})
        if int((booking.get("apartment") or {}).get("id") or 0) == apartment_id
    ]
    return sorted(values, key=lambda item: (str(item.get("arrival") or ""), str(item.get("departure") or "")))


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def active_booking(bookings: Iterable[dict[str, Any]], apartment_id: int, today: date) -> dict[str, Any] | None:
    for booking in house_bookings(bookings, apartment_id):
        arrival = parse_date(booking.get("arrival"))
        departure = parse_date(booking.get("departure"))
        if arrival and departure and arrival <= today < departure:
            return booking
    return None


def next_booking(bookings: Iterable[dict[str, Any]], apartment_id: int, today: date) -> dict[str, Any] | None:
    current = active_booking(bookings, apartment_id, today)
    return current or next_arrival_booking(bookings, apartment_id, today)


def next_arrival_booking(bookings: Iterable[dict[str, Any]], apartment_id: int, today: date) -> dict[str, Any] | None:
    upcoming: list[tuple[date, dict[str, Any]]] = []
    for booking in house_bookings(bookings, apartment_id):
        arrival = parse_date(booking.get("arrival"))
        if arrival and arrival >= today:
            upcoming.append((arrival, booking))
    return min(upcoming, key=lambda item: item[0])[1] if upcoming else None


def next_departure_booking(bookings: Iterable[dict[str, Any]], apartment_id: int, today: date) -> dict[str, Any] | None:
    upcoming: list[tuple[date, dict[str, Any]]] = []
    for booking in house_bookings(bookings, apartment_id):
        departure = parse_date(booking.get("departure"))
        if departure and departure >= today:
            upcoming.append((departure, booking))
    return min(upcoming, key=lambda item: item[0])[1] if upcoming else None


def booking_channel(booking: dict[str, Any]) -> str:
    channel = booking.get("channel")
    if isinstance(channel, dict):
        return str(channel.get("name") or "")
    return str(channel or "")
