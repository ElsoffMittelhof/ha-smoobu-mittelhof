"""Smoobu sensors."""
from __future__ import annotations

from datetime import date
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bookings import active_booking, next_arrival_booking, next_booking, next_departure_booking, parse_date
from .const import (
    CONF_SHOW_GUEST_NAMES,
    DEFAULT_SHOW_GUEST_NAMES,
    DOMAIN,
    INTEGRATION_NAME,
    SIGNAL_STATISTICS_UPDATED,
    SIGNAL_WORKFLOW_UPDATED,
)
from .entity import SmoobuEntity
from .houses import house_slug
from .runtime import SmoobuRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime: SmoobuRuntime = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    show_guest_names = bool(entry.options.get(CONF_SHOW_GUEST_NAMES, DEFAULT_SHOW_GUEST_NAMES))

    for apartment_id in runtime.houses:
        entities.extend([
            OccupancySensor(runtime, entry.entry_id, apartment_id),
            GuestSensor(runtime, entry.entry_id, apartment_id, show_guest_names),
            NextDateSensor(runtime, entry.entry_id, apartment_id, "arrival"),
            NextDateSensor(runtime, entry.entry_id, apartment_id, "departure"),
            WorkflowStatusSensor(runtime, entry.entry_id, apartment_id, "laundry"),
            WorkflowStatusSensor(runtime, entry.entry_id, apartment_id, "nuki"),
        ])
    entities.append(StatisticsSensor(hass, runtime, entry.entry_id))
    entities.append(WorkflowHealthSensor(runtime, entry.entry_id))
    async_add_entities(entities)


class OccupancySensor(SmoobuEntity, SensorEntity):
    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int) -> None:
        super().__init__(runtime.coordinator, entry_id, apartment_id)
        self._runtime = runtime
        self._attr_unique_id = f"{entry_id}_{apartment_id}_occupancy"
        self._attr_name = "Belegung"
        self._attr_icon = "mdi:home-account"
        self._attr_suggested_object_id = f"{house_slug(runtime.houses[apartment_id], apartment_id)}_belegung"

    @property
    def native_value(self) -> str:
        booking = active_booking(self.coordinator.data or [], self._apartment_id, dt_util.now().date())
        return "belegt" if booking else "frei"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        booking = active_booking(self.coordinator.data or [], self._apartment_id, dt_util.now().date())
        if not booking:
            return {}
        return {
            "booking_id": booking.get("id"),
            "arrival": booking.get("arrival"),
            "departure": booking.get("departure"),
            "adults": booking.get("adults"),
            "children": booking.get("children"),
        }


class GuestSensor(SmoobuEntity, SensorEntity):
    """Current guest when occupied, otherwise the guest of the next booking."""

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int, show_guest_names: bool) -> None:
        super().__init__(runtime.coordinator, entry_id, apartment_id)
        self._runtime = runtime
        self._show_guest_names = show_guest_names
        self._attr_unique_id = f"{entry_id}_{apartment_id}_guest"
        self._attr_name = "Gast"
        self._attr_icon = "mdi:account"
        self._attr_suggested_object_id = f"{house_slug(runtime.houses[apartment_id], apartment_id)}_gast"

    def _booking(self) -> tuple[dict[str, Any] | None, str | None]:
        today = dt_util.now().date()
        bookings = self.coordinator.data or []
        current = active_booking(bookings, self._apartment_id, today)
        if current:
            return current, "current"
        upcoming = next_arrival_booking(bookings, self._apartment_id, today)
        if upcoming:
            return upcoming, "next"
        return None, None

    @property
    def native_value(self) -> str | None:
        booking, _role = self._booking()
        if not booking:
            return None
        if not self._show_guest_names:
            return "verborgen"
        guest = str(booking.get("guest-name") or "").strip()
        return guest or "unbekannt"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        booking, role = self._booking()
        if not booking:
            return {}
        attrs: dict[str, Any] = {
            "booking_role": role,
            "booking_id": booking.get("id"),
            "arrival": booking.get("arrival"),
            "departure": booking.get("departure"),
            "adults": booking.get("adults"),
            "children": booking.get("children"),
        }
        channel = booking.get("channel")
        if isinstance(channel, dict):
            attrs["channel"] = channel.get("name")
        elif channel:
            attrs["channel"] = channel
        if self._show_guest_names:
            attrs["guest"] = str(booking.get("guest-name") or "").strip()
        return attrs


class NextDateSensor(SmoobuEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int, field: str) -> None:
        super().__init__(runtime.coordinator, entry_id, apartment_id)
        self._field = field
        self._attr_unique_id = f"{entry_id}_{apartment_id}_next_{field}"
        self._attr_name = "Nächste Anreise" if field == "arrival" else "Nächste Abreise"
        self._attr_icon = "mdi:login" if field == "arrival" else "mdi:logout"
        suffix = "nachste_anreise" if field == "arrival" else "nachste_abreise"
        self._attr_suggested_object_id = f"{house_slug(runtime.houses[apartment_id], apartment_id)}_{suffix}"

    @property
    def native_value(self) -> date | None:
        today = dt_util.now().date()
        if self._field == "arrival":
            booking = next_arrival_booking(self.coordinator.data or [], self._apartment_id, today)
        else:
            booking = next_departure_booking(self.coordinator.data or [], self._apartment_id, today)
        return parse_date(booking.get(self._field)) if booking else None


class WorkflowStatusSensor(SensorEntity):
    """Persistent workflow status independent from API coordinator availability."""

    _attr_has_entity_name = True

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, apartment_id: int, kind: str) -> None:
        self._runtime = runtime
        self._apartment_id = apartment_id
        self._kind = kind

        slug = house_slug(runtime.houses[apartment_id], apartment_id)

        if kind == "laundry":
            self._attr_unique_id = f"{entry_id}_{apartment_id}_laundry_status_v3"
            self._attr_name = "Laundry Status"
            self._attr_icon = "mdi:washing-machine"
            self._attr_suggested_object_id = f"{slug}_laundry_status"
        else:
            self._attr_unique_id = f"{entry_id}_{apartment_id}_nuki_status_v3"
            self._attr_name = "NUKI Status"
            self._attr_icon = "mdi:key-chain"
            self._attr_suggested_object_id = f"{slug}_nuki_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry_id}_{apartment_id}")},
            "via_device": (DOMAIN, entry_id),
            "name": runtime.houses[apartment_id],
            "manufacturer": "Smoobu",
            "model": "Accommodation",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_WORKFLOW_UPDATED,
                self._workflow_updated,
            )
        )

    @callback
    def _workflow_updated(self) -> None:
        self.async_write_ha_state()

    def _status(self) -> tuple[str, dict[str, Any]]:
        if not self._runtime.workflow:
            return "Nicht bereit", {"workflow_ready": False}

        try:
            if self._kind == "laundry":
                return self._runtime.workflow.laundry_status_for_house(self._apartment_id)
            return self._runtime.workflow.nuki_status_for_house(self._apartment_id)
        except Exception as err:
            _LOGGER.exception(
                "Fehler beim Ermitteln des %s-Status für Apartment %s",
                self._kind,
                self._apartment_id,
            )
            return "Statusfehler", {"workflow_ready": True, "error": str(err)}

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        value = self._status()[0]
        return str(value) if value not in (None, "") else "Nicht initialisiert"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._status()[1]


class WorkflowHealthSensor(SensorEntity):
    """Diagnostic sensor for the migrated laundry/NUKI workflow engine."""

    _attr_has_entity_name = True
    _attr_name = "Workflow Status"
    _attr_icon = "mdi:state-machine"
    _attr_suggested_object_id = "smoobu_mittelhof_workflow_status"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{entry_id}_workflow_health"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": INTEGRATION_NAME,
            "manufacturer": "Smoobu",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_WORKFLOW_UPDATED,
                self._workflow_updated,
            )
        )

    @callback
    def _workflow_updated(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        if not self._runtime.workflow:
            return "Nicht bereit"
        return self._runtime.workflow.health_status()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._runtime.workflow:
            return {"workflow_ready": False}
        return self._runtime.workflow.health_status()[1]


class StatisticsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "IT.NRW Statistik"
    _attr_icon = "mdi:chart-box"
    _attr_suggested_object_id = "smoobu_mittelhof_it_nrw_statistik"

    def __init__(self, hass: HomeAssistant, runtime: SmoobuRuntime, entry_id: str) -> None:
        self._hass = hass
        self._runtime = runtime
        self._attr_unique_id = f"{entry_id}_it_nrw_statistics"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": INTEGRATION_NAME,
            "manufacturer": "Smoobu",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_STATISTICS_UPDATED, self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        stats = self._runtime.store.statistics
        if not stats:
            return None
        year, month = stats.get("year"), stats.get("month")
        return f"{int(year):04d}-{int(month):02d}" if year and month else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._runtime.store.statistics)
