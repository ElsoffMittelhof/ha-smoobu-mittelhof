"""Persistent non-secret state for Smoobu Workflow."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class SmoobuStateStore:
    """Keep workflow and report state while avoiding NUKI codes and guest contact data."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {
            "statistics": {},
            "statistics_selection": {},
            "laundry_jobs": {},
            "laundry_requests": {},
            "nuki_jobs": {},
            "nuki_requests": {},
            "workflow_meta": {},
        }

    async def async_load(self) -> None:
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            for key in self.data:
                value = loaded.get(key)
                if isinstance(value, dict):
                    self.data[key] = value

    async def async_save(self) -> None:
        await self._store.async_save(self.data)

    @property
    def statistics(self) -> dict[str, Any]:
        value = self.data.get("statistics")
        return value if isinstance(value, dict) else {}

    async def async_set_statistics(self, result: dict[str, Any]) -> None:
        self.data["statistics"] = deepcopy(result)
        await self.async_save()

    @property
    def statistics_selection(self) -> dict[str, Any]:
        value = self.data.get("statistics_selection")
        return value if isinstance(value, dict) else {}

    async def async_set_statistics_selection(self, selection: dict[str, Any]) -> None:
        self.data["statistics_selection"] = deepcopy(selection)
        await self.async_save()

    @property
    def laundry_jobs(self) -> dict[str, dict[str, Any]]:
        value = self.data.get("laundry_jobs")
        return value if isinstance(value, dict) else {}

    @property
    def laundry_requests(self) -> dict[str, dict[str, Any]]:
        value = self.data.get("laundry_requests")
        return value if isinstance(value, dict) else {}

    @property
    def nuki_jobs(self) -> dict[str, dict[str, Any]]:
        value = self.data.get("nuki_jobs")
        return value if isinstance(value, dict) else {}

    @property
    def nuki_requests(self) -> dict[str, dict[str, Any]]:
        value = self.data.get("nuki_requests")
        return value if isinstance(value, dict) else {}

    @property
    def workflow_meta(self) -> dict[str, Any]:
        value = self.data.get("workflow_meta")
        return value if isinstance(value, dict) else {}

    async def async_set_workflow_state(
        self,
        *,
        laundry_jobs: dict[str, dict[str, Any]] | None = None,
        laundry_requests: dict[str, dict[str, Any]] | None = None,
        nuki_jobs: dict[str, dict[str, Any]] | None = None,
        nuki_requests: dict[str, dict[str, Any]] | None = None,
        workflow_meta: dict[str, Any] | None = None,
    ) -> None:
        if laundry_jobs is not None:
            self.data["laundry_jobs"] = deepcopy(laundry_jobs)
        if laundry_requests is not None:
            self.data["laundry_requests"] = deepcopy(laundry_requests)
        if nuki_jobs is not None:
            self.data["nuki_jobs"] = deepcopy(nuki_jobs)
        if nuki_requests is not None:
            self.data["nuki_requests"] = deepcopy(nuki_requests)
        if workflow_meta is not None:
            self.data["workflow_meta"] = deepcopy(workflow_meta)
        await self.async_save()
