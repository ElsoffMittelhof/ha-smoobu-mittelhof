"""Shared reservations coordinator."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SmoobuApiClient, SmoobuApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SmoobuCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: SmoobuApiClient,
        *,
        update_interval_minutes: int,
        horizon_days: int,
        lookback_days: int,
        houses: dict[int, str],
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval_minutes),
        )
        self.client = client
        self.horizon_days = horizon_days
        self.lookback_days = lookback_days
        self.houses = houses

    async def _async_update_data(self) -> list[dict[str, Any]]:
        today = dt_util.now().date()
        start = today - timedelta(days=self.lookback_days)
        end = today + timedelta(days=self.horizon_days)
        try:
            return await self.client.get_reservations(start, end)
        except SmoobuApiError as err:
            raise UpdateFailed(str(err)) from err
