"""Native Home Assistant calendars for Smoobu bookings."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bookings import booking_channel, house_bookings, next_booking, parse_date, valid_bookings
from .const import CONF_SHOW_GUEST_NAMES, DEFAULT_SHOW_GUEST_NAMES, DOMAIN, INTEGRATION_NAME
from .runtime import SmoobuRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime: SmoobuRuntime = hass.data[DOMAIN][entry.entry_id]
    show_names = bool(entry.options.get(CONF_SHOW_GUEST_NAMES, DEFAULT_SHOW_GUEST_NAMES))
    entities: list[CalendarEntity] = [SmoobuCalendar(runtime, entry.entry_id, None, show_names)]
    entities.extend(SmoobuCalendar(runtime, entry.entry_id, apartment_id, show_names) for apartment_id in runtime.houses)
    async_add_entities(entities)


class SmoobuCalendar(CalendarEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int | None, show_names: bool) -> None:
        self._runtime = runtime
        self._entry_id = entry_id
        self._apartment_id = apartment_id
        self._show_names = show_names
        suffix = "alle" if apartment_id is None else str(apartment_id)
        self._attr_unique_id = f"{entry_id}_calendar_{suffix}"
        self._attr_name = "Buchungen" if apartment_id is not None else "Alle Buchungen"
        if apartment_id is None:
            self._attr_device_info = {
                "identifiers": {(DOMAIN, entry_id)},
                "name": INTEGRATION_NAME,
                "manufacturer": "Smoobu",
            }
        else:
            self._attr_device_info = {
                "identifiers": {(DOMAIN, f"{entry_id}_{apartment_id}")},
                "via_device": (DOMAIN, entry_id),
                "name": runtime.houses[apartment_id],
                "manufacturer": "Smoobu",
            }

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        bookings = self._runtime.coordinator.data or []
        if self._apartment_id is None:
            candidates = []
            for booking in valid_bookings(bookings, self._runtime.houses):
                arrival = parse_date(booking.get("arrival"))
                departure = parse_date(booking.get("departure"))
                if arrival and departure and departure >= today:
                    candidates.append((arrival, booking))
            booking = min(candidates, key=lambda item: item[0])[1] if candidates else None
        else:
            booking = next_booking(bookings, self._apartment_id, today)
        return self._to_event(booking) if booking else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        start = start_date.date()
        # Calendar end bound is exclusive; Smoobu receives an inclusive-ish date range.
        end = end_date.date()
        bookings = await self._runtime.api.get_reservations(start, end)
        if self._apartment_id is not None:
            bookings = house_bookings(bookings, self._apartment_id)
        else:
            bookings = valid_bookings(bookings, self._runtime.houses)
        events = [event for booking in bookings if (event := self._to_event(booking)) is not None]
        events = [event for event in events if event.end > start and event.start < end]
        return sorted(events, key=lambda event: event.start)

    def _to_event(self, booking: dict[str, Any]) -> CalendarEvent | None:
        arrival = parse_date(booking.get("arrival"))
        departure = parse_date(booking.get("departure"))
        if not arrival or not departure or departure <= arrival:
            return None
        apartment = booking.get("apartment") or {}
        apartment_id = apartment.get("id")
        house = self._runtime.houses.get(int(apartment_id or 0), str(apartment.get("name") or "Unterkunft"))
        guest = str(booking.get("guest-name") or "").strip()
        summary = f"{house} – {guest}" if self._show_names and guest else f"{house} – belegt"
        people = int(booking.get("adults") or 0) + int(booking.get("children") or 0)
        description_parts = [f"Buchungs-ID: {booking.get('id')}", f"Personen: {people}"]
        channel = booking_channel(booking)
        if channel:
            description_parts.append(f"Kanal: {channel}")
        if self._show_names and guest:
            description_parts.insert(0, f"Gast: {guest}")
        return CalendarEvent(
            start=arrival,
            end=departure,
            summary=summary,
            description="\n".join(description_parts),
            uid=f"smoobu_{booking.get('id')}",
        )
