"""IT.NRW statistics calculation ported from the working Node-RED flow."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from .const import VALID_BOOKING_TYPES
from .bookings import parse_date

MODE_NODE_RED = "node_red_compatible"
MODE_CALENDAR = "calendar_month"


def statistics_period(year: int, month: int, mode: str) -> tuple[date, date, date, date]:
    """Return query_from, query_to, calculation_start, calculation_end_exclusive."""
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    if mode == MODE_NODE_RED:
        # Intentional compatibility with the user's current working flow:
        # query starts on day 2; calculation adds one day to the query 'to'.
        query_from = date(year, month, 2)
        query_to = next_month
        calc_start = query_from
        calc_end = next_month + timedelta(days=1)
        return query_from, query_to, calc_start, calc_end
    query_from = date(year, month, 1)
    query_to = next_month
    return query_from, query_to, query_from, next_month


def calculate_statistics(
    bookings: Iterable[dict[str, Any]],
    year: int,
    month: int,
    mode: str = MODE_NODE_RED,
    apartment_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    query_from, query_to, month_start, month_end = statistics_period(year, month, mode)
    by_language: dict[str, dict[str, Any]] = {}
    allowed = {int(value) for value in apartment_ids} if apartment_ids is not None else None
    for booking in bookings:
        if booking.get("type") not in VALID_BOOKING_TYPES:
            continue
        if allowed is not None:
            try:
                apartment_id = int((booking.get("apartment") or {}).get("id"))
            except (TypeError, ValueError):
                continue
            if apartment_id not in allowed:
                continue
        check_in = parse_date(booking.get("arrival"))
        check_out = parse_date(booking.get("departure"))
        if not check_in or not check_out:
            continue
        overlap_start = max(check_in, month_start)
        overlap_end = min(check_out, month_end)
        nights = max(0, (overlap_end - overlap_start).days)
        guests = int(booking.get("adults") or 0) + int(booking.get("children") or 0)
        language = str(booking.get("language") or "unknown")
        row = by_language.setdefault(
            language,
            {"language": language, "totalOvernightStays": 0, "totalArrivals": 0},
        )
        if nights > 0:
            row["totalOvernightStays"] += guests * nights
        if check_in.year == year and check_in.month == month:
            row["totalArrivals"] += guests
    language_stats = sorted(by_language.values(), key=lambda row: row["language"])
    return {
        "year": year,
        "month": month,
        "mode": mode,
        "query_from": query_from.isoformat(),
        "query_to": query_to.isoformat(),
        "calculation_from": month_start.isoformat(),
        "calculation_to_exclusive": month_end.isoformat(),
        "total_arrivals": sum(row["totalArrivals"] for row in language_stats),
        "total_overnight_stays": sum(row["totalOvernightStays"] for row in language_stats),
        "language_stats": language_stats,
    }


async def async_generate_statistics(hass, runtime, year: int, month: int, mode: str = MODE_NODE_RED) -> dict[str, Any]:
    """Fetch one reporting period, calculate it and persist the latest result."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from .const import SIGNAL_STATISTICS_UPDATED

    query_from, query_to, _, _ = statistics_period(year, month, mode)
    bookings = await runtime.api.get_reservations(query_from, query_to)
    result = calculate_statistics(bookings, year, month, mode, runtime.houses)
    await runtime.store.async_set_statistics(result)
    async_dispatcher_send(hass, SIGNAL_STATISTICS_UPDATED)
    return result
