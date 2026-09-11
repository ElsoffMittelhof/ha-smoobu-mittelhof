"""Home Assistant actions exposed by Smoobu Workflow."""
from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .bookings import booking_channel, valid_bookings
from .const import (
    DOMAIN,
    INTEGRATION_NAME,
    SERVICE_CALCULATE_LAUNDRY,
    SERVICE_GENERATE_STATISTICS,
    SERVICE_GENERATE_SELECTED_STATISTICS,
    SERVICE_GET_BOOKINGS,
    SERVICE_LAUNDRY_COMMAND,
    SERVICE_NUKI_COMMAND,
    SERVICE_PREVIEW_TEMPLATE,
    SERVICE_PROCESS_WORKFLOWS,
    SERVICE_RELOAD_FILES,
    SERVICE_RESET_LAUNDRY,
    SERVICE_RESET_NUKI,
    SERVICE_RESET_ALL_WORKFLOW_STATE,
    SERVICE_SEND_TEST_EMAIL,
    SERVICE_SEND_TEST_NOTIFICATION,
)
from .runtime import SmoobuRuntime
from .statistics import MODE_CALENDAR, MODE_NODE_RED, async_generate_statistics


def _runtime(hass: HomeAssistant) -> SmoobuRuntime:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise vol.Invalid("Smoobu Workflow ist nicht konfiguriert oder geladen")
    return next(iter(entries.values()))


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration actions once at integration setup."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_BOOKINGS):
        return

    async def get_bookings(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass)
        start = call.data["start_date"]
        end = call.data["end_date"]
        apartment_id = call.data.get("apartment_id")
        bookings = await runtime.api.get_reservations(
            start, end, exclude_blocked=False, apartment_id=apartment_id
        )
        rows = []
        for booking in valid_bookings(bookings, runtime.houses):
            apartment = booking.get("apartment") or {}
            rows.append({
                "booking_id": booking.get("id"),
                "house": runtime.houses.get(int(apartment.get("id") or 0), apartment.get("name")),
                "apartment_id": apartment.get("id"),
                "guest": booking.get("guest-name"),
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "price": booking.get("price"),
                "commission": booking.get("commission-included", booking.get("commission")),
                "email": booking.get("email"),
                "phone": booking.get("phone"),
                "language": booking.get("language"),
                "channel": booking_channel(booking),
                "adults": booking.get("adults"),
                "children": booking.get("children"),
                "notice": booking.get("notice"),
                "guest_app_url": booking.get("guest-app-url"),
                "type": booking.get("type"),
                "is_blocked": bool(booking.get("is-blocked-booking")),
            })
        return {"start_date": str(start), "end_date": str(end), "bookings": rows}

    async def generate_statistics(call: ServiceCall) -> dict[str, Any] | None:
        runtime = _runtime(hass)
        year = int(call.data["year"])
        month = int(call.data["month"])
        mode = str(call.data.get("mode", MODE_NODE_RED))
        result = await async_generate_statistics(hass, runtime, year, month, mode)
        return result if call.return_response else None

    async def generate_selected_statistics(call: ServiceCall) -> None:
        """Generate the selected IT.NRW reporting month immediately."""
        runtime = _runtime(hass)
        selection = runtime.store.statistics_selection
        month_text = str(selection.get("month") or "01 Januar")
        year_text = str(selection.get("year") or date.today().year)

        try:
            month = int(month_text[:2])
            year = int(year_text)
        except (TypeError, ValueError) as err:
            raise vol.Invalid("Ungültige IT.NRW Monats-/Jahresauswahl") from err

        await async_generate_statistics(hass, runtime, year, month, MODE_NODE_RED)

    async def preview_template(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass)
        booking_id = str(call.data["booking_id"])
        template = await hass.async_add_executor_job(runtime.templates.load, str(call.data["template"]))
        normal = await runtime.api.get_booking_placeholders(booking_id)
        custom = await runtime.api.get_booking_custom_placeholders(booking_id)
        values = {**normal, **custom, "bookingID": booking_id}
        return runtime.templates.render(template, values)

    async def calculate_laundry(call: ServiceCall) -> dict[str, Any]:
        runtime = _runtime(hass)
        ids = [int(value) for value in call.data["apartment_ids"]]
        return await hass.async_add_executor_job(runtime.laundry.calculate, ids)

    async def reload_files(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await hass.async_add_executor_job(runtime.laundry.load)
        # Templates are intentionally loaded on demand, so edits become active immediately.

    async def process_workflows(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_process(
            force_laundry_notify=bool(call.data.get("force_laundry_notify", False)),
            force_nuki_notify=bool(call.data.get("force_nuki_notify", False)),
        )

    async def laundry_command(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_laundry_command(
            str(call.data["command"]),
            str(call.data["request_id"]) if call.data.get("request_id") else None,
        )

    async def nuki_command(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_nuki_command(
            str(call.data["command"]),
            str(call.data["request_id"]) if call.data.get("request_id") else None,
        )

    async def send_test_email(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        recipient = str(call.data["to"])
        await runtime.mail.async_send(
            recipient,
            "[TEST] Smoobu Workflow SMTP",
            "Diese Testmail wurde direkt von der Home-Assistant-Integration Smoobu Workflow versendet.",
        )

    async def send_test_notification(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_test_notification()

    async def reset_laundry(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_reset_laundry()

    async def reset_nuki(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_reset_nuki()

    async def reset_all_workflow_state(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        await runtime.workflow.async_reset_all_workflow_state()
        await runtime.workflow.async_process(
            force_laundry_notify=bool(call.data.get("process_now", False)),
            force_nuki_notify=bool(call.data.get("process_now", False)),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_BOOKINGS,
        get_bookings,
        schema=vol.Schema({
            vol.Required("start_date"): vol.Coerce(date.fromisoformat),
            vol.Required("end_date"): vol.Coerce(date.fromisoformat),
            vol.Optional("apartment_id"): vol.Coerce(int),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_STATISTICS,
        generate_statistics,
        schema=vol.Schema({
            vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=2000, max=2100)),
            vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Optional("mode", default=MODE_NODE_RED): vol.In([MODE_NODE_RED, MODE_CALENDAR]),
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_SELECTED_STATISTICS,
        generate_selected_statistics,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW_TEMPLATE,
        preview_template,
        schema=vol.Schema({
            vol.Required("booking_id"): vol.Coerce(str),
            vol.Required("template"): str,
        }),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALCULATE_LAUNDRY,
        calculate_laundry,
        schema=vol.Schema({vol.Required("apartment_ids"): [vol.Coerce(int)]}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, SERVICE_RELOAD_FILES, reload_files)
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROCESS_WORKFLOWS,
        process_workflows,
        schema=vol.Schema({
            vol.Optional("force_laundry_notify", default=False): bool,
            vol.Optional("force_nuki_notify", default=False): bool,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAUNDRY_COMMAND,
        laundry_command,
        schema=vol.Schema({
            vol.Required("command"): vol.In(["send", "later", "skip"]),
            vol.Optional("request_id"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NUKI_COMMAND,
        nuki_command,
        schema=vol.Schema({
            vol.Required("command"): vol.In(["send", "later", "skip"]),
            vol.Optional("request_id"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEST_EMAIL,
        send_test_email,
        schema=vol.Schema({vol.Required("to"): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEST_NOTIFICATION,
        send_test_notification,
    )
    hass.services.async_register(DOMAIN, SERVICE_RESET_LAUNDRY, reset_laundry)
    hass.services.async_register(DOMAIN, SERVICE_RESET_NUKI, reset_nuki)
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_ALL_WORKFLOW_STATE,
        reset_all_workflow_state,
        schema=vol.Schema({
            vol.Optional("process_now", default=False): bool,
        }),
    )
