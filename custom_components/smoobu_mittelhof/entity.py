"""Base entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_NAME
from .coordinator import SmoobuCoordinator


class SmoobuEntity(CoordinatorEntity[SmoobuCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SmoobuCoordinator, entry_id: str, apartment_id: int | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._apartment_id = apartment_id

        if apartment_id is None:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name=INTEGRATION_NAME,
                manufacturer="Smoobu",
                model="Cloud API",
            )
        else:
            house = coordinator.houses[apartment_id]
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{apartment_id}")},
                via_device=(DOMAIN, entry_id),
                name=house,
                manufacturer="Smoobu",
                model="Accommodation",
            )
