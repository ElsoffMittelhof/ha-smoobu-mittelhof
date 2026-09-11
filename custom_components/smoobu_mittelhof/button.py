"""Integration buttons."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INTEGRATION_NAME
from .runtime import SmoobuRuntime
from .statistics import MODE_NODE_RED, async_generate_statistics


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime: SmoobuRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RefreshButton(runtime, entry.entry_id),
        GenerateStatisticsButton(runtime, entry.entry_id),
        LaundryResendButton(runtime, entry.entry_id),
        LaundryResetButton(runtime, entry.entry_id),
        NukiResendButton(runtime, entry.entry_id),
        NukiResetButton(runtime, entry.entry_id),
        ProcessWorkflowsButton(runtime, entry.entry_id),
    ])


class BaseButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, suffix: str) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{entry_id}_{suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": INTEGRATION_NAME,
            "manufacturer": "Smoobu",
        }


class RefreshButton(BaseButton):
    _attr_name = "Jetzt aktualisieren"
    _attr_icon = "mdi:refresh"
    _attr_suggested_object_id = "smoobu_mittelhof_jetzt_aktualisieren"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "refresh")

    async def async_press(self) -> None:
        await self._runtime.coordinator.async_request_refresh()


class GenerateStatisticsButton(BaseButton):
    _attr_name = "IT.NRW Statistik erstellen"
    _attr_icon = "mdi:chart-box-plus-outline"
    _attr_suggested_object_id = "smoobu_mittelhof_it_nrw_statistik_erstellen"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "it_nrw_generate")

    async def async_press(self) -> None:
        selection = self._runtime.store.statistics_selection
        month_text = str(selection.get("month") or "01 Januar")
        month = int(month_text[:2])
        year = int(selection.get("year") or 2026)
        await async_generate_statistics(self.hass, self._runtime, year, month, MODE_NODE_RED)


class LaundryResendButton(BaseButton):
    _attr_name = "Wäsche Push erneut senden"
    _attr_icon = "mdi:bell-ring"
    _attr_suggested_object_id = "smoobu_mittelhof_waesche_push_erneut_senden"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "laundry_resend")

    async def async_press(self) -> None:
        await self._runtime.workflow.async_process(force_laundry_notify=True)


class LaundryResetButton(BaseButton):
    _attr_name = "Wäsche offene Status zurücksetzen"
    _attr_icon = "mdi:restart-alert"
    _attr_suggested_object_id = "smoobu_mittelhof_waesche_status_zuruecksetzen"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "laundry_reset")

    async def async_press(self) -> None:
        await self._runtime.workflow.async_reset_laundry()
        await self._runtime.workflow.async_process(force_laundry_notify=True)


class NukiResendButton(BaseButton):
    _attr_name = "NUKI Push erneut senden"
    _attr_icon = "mdi:key-chain-variant"
    _attr_suggested_object_id = "smoobu_mittelhof_nuki_push_erneut_senden"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "nuki_resend")

    async def async_press(self) -> None:
        await self._runtime.workflow.async_process(force_nuki_notify=True)


class NukiResetButton(BaseButton):
    _attr_name = "NUKI offene Status zurücksetzen"
    _attr_icon = "mdi:key-remove"
    _attr_suggested_object_id = "smoobu_mittelhof_nuki_status_zuruecksetzen"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "nuki_reset")

    async def async_press(self) -> None:
        await self._runtime.workflow.async_reset_nuki()
        await self._runtime.workflow.async_process(force_nuki_notify=True)


class ProcessWorkflowsButton(BaseButton):
    _attr_name = "Wäsche + NUKI jetzt prüfen"
    _attr_icon = "mdi:play-circle-outline"
    _attr_suggested_object_id = "smoobu_mittelhof_workflows_jetzt_pruefen"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "process_workflows")

    async def async_press(self) -> None:
        await self._runtime.workflow.async_process(
            force_laundry_notify=True,
            force_nuki_notify=True,
        )
