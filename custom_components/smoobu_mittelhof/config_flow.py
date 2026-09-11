"""Config flow for Smoobu Workflow."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmoobuApiClient, SmoobuApiError, SmoobuAuthError
from .const import (
    CONF_API_KEY,
    CONF_API_SECRET,
    CONF_CONFIG_DIRECTORY,
    CONF_HORIZON_DAYS,
    CONF_HOUSES,
    CONF_LAUNDRY_EMAIL,
    CONF_LAUNDRY_ENABLED,
    CONF_LAUNDRY_LEAD_DAYS,
    CONF_LAUNDRY_REMINDER_HOURS,
    CONF_LOOKBACK_DAYS,
    CONF_NOTIFICATION_END_HOUR,
    CONF_NOTIFICATION_START_HOUR,
    CONF_NOTIFY_SERVICE,
    CONF_NUKI_ENABLED,
    CONF_NUKI_LEAD_DAYS,
    CONF_NUKI_REMINDER_HOURS,
    CONF_NUKI_TEST_EMAIL,
    CONF_NUKI_TEST_MODE,
    CONF_SHOW_GUEST_NAMES,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_SMTP_SSL,
    CONF_SMTP_STARTTLS,
    CONF_SMTP_USERNAME,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_CONFIG_DIRECTORY,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LAUNDRY_EMAIL,
    DEFAULT_LAUNDRY_ENABLED,
    DEFAULT_LAUNDRY_LEAD_DAYS,
    DEFAULT_LAUNDRY_REMINDER_HOURS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_NOTIFICATION_END_HOUR,
    DEFAULT_NOTIFICATION_START_HOUR,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_NUKI_ENABLED,
    DEFAULT_NUKI_LEAD_DAYS,
    DEFAULT_NUKI_REMINDER_HOURS,
    DEFAULT_NUKI_TEST_EMAIL,
    DEFAULT_NUKI_TEST_MODE,
    DEFAULT_SHOW_GUEST_NAMES,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PASSWORD,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_SENDER,
    DEFAULT_SMTP_SSL,
    DEFAULT_SMTP_STARTTLS,
    DEFAULT_SMTP_USERNAME,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    INTEGRATION_NAME,
)
from .houses import discover_houses, format_houses, parse_houses


async def _validate_and_discover(
    hass: HomeAssistant,
    api_key: str,
    api_secret: str,
) -> dict[int, str]:
    client = SmoobuApiClient(async_get_clientsession(hass), api_key, api_secret)
    today = date.today()
    bookings = await client.get_reservations(today - timedelta(days=365), today + timedelta(days=365))
    return discover_houses(bookings)


class SmoobuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    def __init__(self) -> None:
        self._pending_data: dict[str, Any] = {}
        self._discovered_houses: dict[int, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._discovered_houses = await _validate_and_discover(
                    self.hass,
                    user_input[CONF_API_KEY],
                    user_input[CONF_API_SECRET],
                )
            except SmoobuAuthError:
                errors["base"] = "invalid_auth"
            except SmoobuApiError:
                errors["base"] = "cannot_connect"
            else:
                self._pending_data = dict(user_input)
                return await self.async_step_houses()

        schema = vol.Schema({
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_API_SECRET): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_houses(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested = format_houses(self._discovered_houses)

        if user_input is not None:
            houses = parse_houses(user_input.get(CONF_HOUSES))
            if not houses:
                errors[CONF_HOUSES] = "invalid_houses"
            else:
                await self.async_set_unique_id("smoobu_workflow")
                self._abort_if_unique_id_configured()
                data = {**self._pending_data, CONF_HOUSES: format_houses(houses)}
                return self.async_create_entry(title=INTEGRATION_NAME, data=data)

        schema = vol.Schema({
            vol.Required(CONF_HOUSES, default=suggested): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        })
        return self.async_show_form(step_id="houses", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return SmoobuOptionsFlow()


class SmoobuOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options = self.config_entry.options
        current_houses = options.get(CONF_HOUSES, self.config_entry.data.get(CONF_HOUSES, ""))

        if user_input is not None:
            houses = parse_houses(user_input.get(CONF_HOUSES))
            if not houses:
                errors[CONF_HOUSES] = "invalid_houses"
            else:
                user_input[CONF_HOUSES] = format_houses(houses)
                return self.async_create_entry(data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_HOUSES, default=current_houses): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(CONF_UPDATE_INTERVAL_MINUTES, default=DEFAULT_UPDATE_INTERVAL_MINUTES): vol.All(int, vol.Range(min=15, max=1440)),
            vol.Required(CONF_HORIZON_DAYS, default=DEFAULT_HORIZON_DAYS): vol.All(int, vol.Range(min=14, max=365)),
            vol.Required(CONF_LOOKBACK_DAYS, default=DEFAULT_LOOKBACK_DAYS): vol.All(int, vol.Range(min=0, max=30)),
            vol.Required(CONF_SHOW_GUEST_NAMES, default=DEFAULT_SHOW_GUEST_NAMES): bool,
            vol.Required(CONF_CONFIG_DIRECTORY, default=DEFAULT_CONFIG_DIRECTORY): str,
            vol.Optional(CONF_NOTIFY_SERVICE, default=DEFAULT_NOTIFY_SERVICE): str,
            vol.Required(CONF_NOTIFICATION_START_HOUR, default=DEFAULT_NOTIFICATION_START_HOUR): vol.All(int, vol.Range(min=0, max=23)),
            vol.Required(CONF_NOTIFICATION_END_HOUR, default=DEFAULT_NOTIFICATION_END_HOUR): vol.All(int, vol.Range(min=0, max=23)),
            vol.Required(CONF_LAUNDRY_ENABLED, default=DEFAULT_LAUNDRY_ENABLED): bool,
            vol.Required(CONF_LAUNDRY_LEAD_DAYS, default=DEFAULT_LAUNDRY_LEAD_DAYS): vol.All(int, vol.Range(min=0, max=30)),
            vol.Required(CONF_LAUNDRY_REMINDER_HOURS, default=DEFAULT_LAUNDRY_REMINDER_HOURS): vol.All(int, vol.Range(min=1, max=48)),
            vol.Optional(CONF_LAUNDRY_EMAIL, default=DEFAULT_LAUNDRY_EMAIL): str,
            vol.Required(CONF_NUKI_ENABLED, default=DEFAULT_NUKI_ENABLED): bool,
            vol.Required(CONF_NUKI_LEAD_DAYS, default=DEFAULT_NUKI_LEAD_DAYS): vol.All(int, vol.Range(min=0, max=30)),
            vol.Required(CONF_NUKI_REMINDER_HOURS, default=DEFAULT_NUKI_REMINDER_HOURS): vol.All(int, vol.Range(min=1, max=48)),
            vol.Required(CONF_NUKI_TEST_MODE, default=DEFAULT_NUKI_TEST_MODE): bool,
            vol.Optional(CONF_NUKI_TEST_EMAIL, default=DEFAULT_NUKI_TEST_EMAIL): str,
            vol.Optional(CONF_SMTP_HOST, default=DEFAULT_SMTP_HOST): str,
            vol.Required(CONF_SMTP_PORT, default=DEFAULT_SMTP_PORT): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Optional(CONF_SMTP_USERNAME, default=DEFAULT_SMTP_USERNAME): str,
            vol.Optional(CONF_SMTP_PASSWORD, default=DEFAULT_SMTP_PASSWORD): str,
            vol.Optional(CONF_SMTP_SENDER, default=DEFAULT_SMTP_SENDER): str,
            vol.Required(CONF_SMTP_STARTTLS, default=DEFAULT_SMTP_STARTTLS): bool,
            vol.Required(CONF_SMTP_SSL, default=DEFAULT_SMTP_SSL): bool,
        })
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, options),
            errors=errors,
        )
