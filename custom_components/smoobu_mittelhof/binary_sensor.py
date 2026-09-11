"""Arrival/departure binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bookings import house_bookings, parse_date
from .const import DOMAIN
from .entity import SmoobuEntity
from .runtime import SmoobuRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime: SmoobuRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DayMarkerSensor(runtime, entry.entry_id, apartment_id, field)
        for apartment_id in runtime.houses
        for field in ("arrival", "departure")
    )


class DayMarkerSensor(SmoobuEntity, BinarySensorEntity):
    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int, field: str) -> None:
        super().__init__(runtime.coordinator, entry_id, apartment_id)
        self._field = field
        self._attr_unique_id = f"{entry_id}_{apartment_id}_{field}_today"
        self._attr_name = "Anreise heute" if field == "arrival" else "Abreise heute"
        self._attr_icon = "mdi:login" if field == "arrival" else "mdi:logout"

    @property
    def is_on(self) -> bool:
        today = dt_util.now().date()
        return any(
            parse_date(booking.get(self._field)) == today
            for booking in house_bookings(self.coordinator.data or [], self._apartment_id)
        )
