"""Smoobu Workflow integration."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmoobuApiClient
from .const import (
    CONF_API_KEY,
    CONF_API_SECRET,
    CONF_CONFIG_DIRECTORY,
    CONF_HORIZON_DAYS,
    CONF_HOUSES,
    CONF_LOOKBACK_DAYS,
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
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PASSWORD,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_SENDER,
    DEFAULT_SMTP_SSL,
    DEFAULT_SMTP_STARTTLS,
    DEFAULT_SMTP_USERNAME,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SmoobuCoordinator
from .houses import discover_houses, format_houses, parse_houses
from .laundry import LaundryRepository
from .mail import MailSettings, MailTransport
from .runtime import SmoobuRuntime
from .services import async_register_services
from .storage import SmoobuStateStore
from .templates import TemplateRepository
from .workflow import WorkflowManager

FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_URL = "/smoobu_mittelhof/frontend"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if FRONTEND_DIR.exists():
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(FRONTEND_DIR), False)]
        )
    await async_register_services(hass)
    return True


async def _discover_legacy_houses(hass: HomeAssistant, entry: ConfigEntry) -> dict[int, str]:
    """Recover pre-v0.3 house IDs/names without embedding installation-specific values."""
    houses: dict[int, str] = {}

    store = SmoobuStateStore(hass)
    await store.async_load()
    for jobs in (store.laundry_jobs, store.nuki_jobs):
        for job in jobs.values():
            try:
                apartment_id = int(job.get("apartment_id"))
            except (TypeError, ValueError):
                continue
            name = str(job.get("house") or "").strip()
            if apartment_id > 0 and name:
                houses.setdefault(apartment_id, name)

    try:
        client = SmoobuApiClient(
            async_get_clientsession(hass),
            entry.data[CONF_API_KEY],
            entry.data[CONF_API_SECRET],
        )
        today = date.today()
        bookings = await client.get_reservations(today - timedelta(days=365), today + timedelta(days=365))
        for apartment_id, name in discover_houses(bookings).items():
            houses.setdefault(apartment_id, name)
    except Exception:
        # Existing local workflow state is sufficient when Smoobu is temporarily unavailable.
        pass

    return houses


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    options = dict(entry.options)

    if entry.version < 2:
        options[CONF_SHOW_GUEST_NAMES] = True

    if entry.version < 3:
        if CONF_CONFIG_DIRECTORY not in options:
            # Preserve the path used by all private pre-v0.3 installations.
            options[CONF_CONFIG_DIRECTORY] = "smoobu_mittelhof"

        if not parse_houses(options.get(CONF_HOUSES, entry.data.get(CONF_HOUSES, ""))):
            houses = await _discover_legacy_houses(hass, entry)
            if houses:
                options[CONF_HOUSES] = format_houses(houses)

        hass.config_entries.async_update_entry(entry, options=options, version=3)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    houses = parse_houses(entry.options.get(CONF_HOUSES, entry.data.get(CONF_HOUSES, "")))
    if not houses:
        raise ConfigEntryError(
            "No Smoobu accommodations are configured. Open the integration options and add apartment_id=Name entries."
        )

    client = SmoobuApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data[CONF_API_SECRET],
    )
    coordinator = SmoobuCoordinator(
        hass,
        client,
        update_interval_minutes=int(entry.options.get(CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES)),
        horizon_days=int(entry.options.get(CONF_HORIZON_DAYS, DEFAULT_HORIZON_DAYS)),
        lookback_days=int(entry.options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS)),
        houses=houses,
    )

    store = SmoobuStateStore(hass)
    await store.async_load()
    config_dir = Path(hass.config.path(entry.options.get(CONF_CONFIG_DIRECTORY, DEFAULT_CONFIG_DIRECTORY)))

    mail_settings = MailSettings(
        host=str(entry.options.get(CONF_SMTP_HOST, DEFAULT_SMTP_HOST)),
        port=int(entry.options.get(CONF_SMTP_PORT, DEFAULT_SMTP_PORT)),
        username=str(entry.options.get(CONF_SMTP_USERNAME, DEFAULT_SMTP_USERNAME)),
        password=str(entry.options.get(CONF_SMTP_PASSWORD, DEFAULT_SMTP_PASSWORD)),
        sender=str(entry.options.get(CONF_SMTP_SENDER, DEFAULT_SMTP_SENDER)),
        starttls=bool(entry.options.get(CONF_SMTP_STARTTLS, DEFAULT_SMTP_STARTTLS)),
        use_ssl=bool(entry.options.get(CONF_SMTP_SSL, DEFAULT_SMTP_SSL)),
    )

    runtime = SmoobuRuntime(
        api=client,
        coordinator=coordinator,
        store=store,
        templates=TemplateRepository(config_dir / "templates"),
        laundry=LaundryRepository(config_dir / "laundry.yaml"),
        mail=MailTransport(hass, mail_settings),
        config_directory=config_dir,
        houses=houses,
    )
    runtime.workflow = WorkflowManager(hass, runtime, entry)
    hass.data[DOMAIN][entry.entry_id] = runtime

    await coordinator.async_config_entry_first_refresh()
    await runtime.workflow.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime: SmoobuRuntime | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime and runtime.workflow:
        await runtime.workflow.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unloaded
