"""Select entities for IT.NRW reporting period."""
from __future__ import annotations

from datetime import date

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INTEGRATION_NAME, SIGNAL_STATISTICS_SELECTION_UPDATED
from .runtime import SmoobuRuntime

MONTHS = [
    "01 Januar",
    "02 Februar",
    "03 März",
    "04 April",
    "05 Mai",
    "06 Juni",
    "07 Juli",
    "08 August",
    "09 September",
    "10 Oktober",
    "11 November",
    "12 Dezember",
]


def _default_selection() -> tuple[str, str]:
    today = date.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        month = 12
        year -= 1
    return MONTHS[month - 1], str(year)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime: SmoobuRuntime = hass.data[DOMAIN][entry.entry_id]
    default_month, default_year = _default_selection()
    selection = runtime.store.statistics_selection
    changed = False
    if "month" not in selection:
        selection["month"] = default_month
        changed = True
    if "year" not in selection:
        selection["year"] = default_year
        changed = True
    if changed:
        await runtime.store.async_save()

    current_year = date.today().year
    years = [str(year) for year in range(2024, max(2035, current_year + 6) + 1)]
    async_add_entities([
        StatisticsMonthSelect(runtime, entry.entry_id),
        StatisticsYearSelect(runtime, entry.entry_id, years),
    ])


class StatisticsMonthSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "IT.NRW Monat"
    _attr_icon = "mdi:calendar-month"
    _attr_options = MONTHS
    _attr_suggested_object_id = "smoobu_mittelhof_it_nrw_monat"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{entry_id}_it_nrw_month"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": INTEGRATION_NAME,
            "manufacturer": "Smoobu",
        }

    @property
    def current_option(self) -> str | None:
        return str(self._runtime.store.statistics_selection.get("month") or MONTHS[0])

    async def async_select_option(self, option: str) -> None:
        if option not in MONTHS:
            return
        selection = self._runtime.store.statistics_selection
        selection["month"] = option
        await self._runtime.store.async_save()
        async_dispatcher_send(self.hass, SIGNAL_STATISTICS_SELECTION_UPDATED)
        self.async_write_ha_state()


class StatisticsYearSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "IT.NRW Jahr"
    _attr_icon = "mdi:calendar"
    _attr_suggested_object_id = "smoobu_mittelhof_it_nrw_jahr"

    def __init__(self, runtime: SmoobuRuntime, entry_id: str, years: list[str]) -> None:
        self._runtime = runtime
        self._attr_options = years
        self._attr_unique_id = f"{entry_id}_it_nrw_year"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": INTEGRATION_NAME,
            "manufacturer": "Smoobu",
        }

    @property
    def current_option(self) -> str | None:
        value = str(self._runtime.store.statistics_selection.get("year") or date.today().year)
        return value if value in self._attr_options else self._attr_options[0]

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            return
        selection = self._runtime.store.statistics_selection
        selection["year"] = option
        await self._runtime.store.async_save()
        async_dispatcher_send(self.hass, SIGNAL_STATISTICS_SELECTION_UPDATED)
        self.async_write_ha_state()
