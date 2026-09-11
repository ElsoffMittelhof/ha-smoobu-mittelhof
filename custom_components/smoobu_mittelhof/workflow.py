"""Laundry and NUKI workflow engine migrated from the working Node-RED flow."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import logging
import re
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .bookings import parse_date, valid_bookings
from .const import (
    CONF_LAUNDRY_EMAIL,
    CONF_LAUNDRY_ENABLED,
    CONF_LAUNDRY_LEAD_DAYS,
    CONF_LAUNDRY_REMINDER_HOURS,
    CONF_NOTIFICATION_START_HOUR,
    CONF_NOTIFICATION_END_HOUR,
    CONF_NOTIFY_SERVICE,
    CONF_NUKI_ENABLED,
    CONF_NUKI_LEAD_DAYS,
    CONF_NUKI_REMINDER_HOURS,
    CONF_NUKI_TEST_EMAIL,
    CONF_NUKI_TEST_MODE,
    DEFAULT_LAUNDRY_EMAIL,
    DEFAULT_LAUNDRY_ENABLED,
    DEFAULT_LAUNDRY_LEAD_DAYS,
    DEFAULT_LAUNDRY_REMINDER_HOURS,
    DEFAULT_NOTIFICATION_START_HOUR,
    DEFAULT_NOTIFICATION_END_HOUR,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_NUKI_ENABLED,
    DEFAULT_NUKI_LEAD_DAYS,
    DEFAULT_NUKI_REMINDER_HOURS,
    DEFAULT_NUKI_TEST_EMAIL,
    DEFAULT_NUKI_TEST_MODE,
    EVENT_NOTIFICATION_ACTION,
    LAUNDRY_ACTION_PREFIX,
    NUKI_ACTION_PREFIX,
    SIGNAL_WORKFLOW_UPDATED,
)
from .houses import house_slug
from .laundry import LaundryConfigError
from .mail import MailError
from .templates import TemplateError

_LOGGER = logging.getLogger(__name__)


def _iso_now() -> str:
    return dt_util.now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed


def _days_until(value: Any, today: date) -> int | None:
    parsed = parse_date(value)
    return (parsed - today).days if parsed else None


def _format_de(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else str(value or "")


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(value or "")).lower()


def _request_id(prefix: str) -> str:
    return f"{prefix}_{dt_util.now().strftime('%Y%m%d')}_{uuid4().hex[:10]}"


def _booking_map(
    bookings: list[dict[str, Any]],
    apartment_ids: Any = None,
) -> dict[str, dict[str, Any]]:
    return {
        str(b.get("id")): b
        for b in valid_bookings(bookings, apartment_ids)
        if b.get("id") is not None
    }


class WorkflowManager:
    """Own the operational state previously held by Node-RED context."""

    def __init__(self, hass: HomeAssistant, runtime: Any, entry: ConfigEntry) -> None:
        self.hass = hass
        self.runtime = runtime
        self.entry = entry
        self._lock = asyncio.Lock()
        self._unsub_coordinator = None
        self._unsub_event = None

    async def async_start(self) -> None:
        @callback
        def _coordinator_updated() -> None:
            self.hass.async_create_task(self.async_process())

        self._unsub_coordinator = self.runtime.coordinator.async_add_listener(_coordinator_updated)
        self._unsub_event = self.hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, self._handle_notification_event)
        await self._bootstrap_legacy_helpers()
        await self.async_process()

    async def async_stop(self) -> None:
        if self._unsub_coordinator:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None

    @callback
    def _handle_notification_event(self, event: Event) -> None:
        action = str(event.data.get("action") or "")
        if action.startswith(f"{LAUNDRY_ACTION_PREFIX}_"):
            self.hass.async_create_task(self._handle_laundry_action_string(action))
        elif action.startswith(f"{NUKI_ACTION_PREFIX}_"):
            self.hass.async_create_task(self._handle_nuki_action_string(action))

    def _option(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, default)

    def _notifications_allowed(self, now: datetime | None = None) -> bool:
        """Return whether automatic actionable notifications may be sent now."""
        now = now or dt_util.now()
        start = int(self._option(CONF_NOTIFICATION_START_HOUR, DEFAULT_NOTIFICATION_START_HOUR))
        end = int(self._option(CONF_NOTIFICATION_END_HOUR, DEFAULT_NOTIFICATION_END_HOUR))
        hour = now.hour

        if start == end:
            return True
        if start < end:
            return start <= hour <= end
        # Overnight window, e.g. 22 -> 6.
        return hour >= start or hour <= end

    async def _notify(self, title: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        target = str(self._option(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE) or "").strip()
        payload = {"title": title, "message": message}
        if data:
            payload["data"] = data

        if target and "." in target:
            domain, service = target.split(".", 1)
            if self.hass.services.has_service(domain, service):
                await self.hass.services.async_call(domain, service, payload, blocking=False)
                return

        # Fallback: visible in HA even if no mobile notify service is configured.
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": title, "message": message},
            blocking=False,
        )

    async def _persist(self) -> None:
        await self.runtime.store.async_save()
        async_dispatcher_send(self.hass, SIGNAL_WORKFLOW_UPDATED)

    async def async_test_notification(self) -> None:
        """Send a direct workflow notification for setup diagnostics."""
        await self._notify(
            "Smoobu Workflow Test",
            "Die Push-Benachrichtigung aus der Smoobu-Workflow-Integration funktioniert.",
            data={"tag": "smoobu_mittelhof_test"},
        )

    async def _bootstrap_legacy_helpers(self) -> None:
        """Import already sent/ignored state from the old HA input_text helpers once.

        This prevents duplicate laundry orders or NUKI mails during the Node-RED -> HA cutover.
        No NUKI code, guest name or e-mail address is persisted.
        """
        meta = self.runtime.store.workflow_meta
        if meta.get("legacy_helpers_imported"):
            return

        bookings = valid_bookings(self.runtime.coordinator.data or [], self.runtime.houses)
        today = dt_util.now().date()
        laundry_jobs = self.runtime.store.laundry_jobs
        nuki_jobs = self.runtime.store.nuki_jobs

        for booking in bookings:
            apartment = booking.get("apartment") or {}
            apartment_id = apartment.get("id")
            if apartment_id not in self.runtime.houses or not booking.get("id"):
                continue
            booking_id = str(booking["id"])
            house = self.runtime.houses[apartment_id]
            laundry_jobs.setdefault(booking_id, {
                "booking_id": booking_id,
                "apartment_id": apartment_id,
                "house": house,
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "seen_date": today.isoformat(),
                "status": "new",
                "request_id": None,
                "last_notified_at": None,
                "snooze_until": None,
                "sent_at": None,
                "previous_departure": None,
            })
            nuki_jobs.setdefault(booking_id, {
                "booking_id": booking_id,
                "apartment_id": apartment_id,
                "house": house,
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "seen_date": today.isoformat(),
                "status": "new",
                "request_id": None,
                "last_notified_at": None,
                "last_code_check_at": None,
                "last_code_missing_notice_date": None,
                "snooze_until": None,
                "sent_at": None,
                "previous_arrival": None,
            })

        def date_from_text(text: str) -> date | None:
            match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
            if not match:
                return None
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None

        for apartment_id, house in self.runtime.houses.items():
            slug = house_slug(house, apartment_id)
            laundry_state = self.hass.states.get(f"input_text.waesche_{slug}")
            nuki_state = (
                self.hass.states.get(f"input_text.input_text_nuki_{slug}")
                or self.hass.states.get(f"input_text.nuki_{slug}")
            )

            if laundry_state:
                text = str(laundry_state.state or "")
                target_date = date_from_text(text)
                house_jobs = [
                    job for job in laundry_jobs.values()
                    if int(job.get("apartment_id") or 0) == apartment_id
                    and parse_date(job.get("departure"))
                    and parse_date(job.get("departure")) >= today
                ]
                house_jobs.sort(key=lambda job: str(job.get("departure") or ""))
                exact = [job for job in house_jobs if target_date and parse_date(job.get("departure")) == target_date]
                selected = exact[0] if exact else (house_jobs[0] if house_jobs else None)
                if selected:
                    if "Bestellt" in text:
                        if target_date and not exact:
                            selected.update(
                                status="changed",
                                previous_departure=target_date.isoformat(),
                                request_id=None,
                                sent_at="legacy_node_red",
                            )
                        else:
                            selected.update(status="sent", sent_at="legacy_node_red", request_id=None)
                    elif "Ignoriert" in text:
                        selected.update(status="ignored", request_id=None)

            if nuki_state:
                text = str(nuki_state.state or "")
                target_date = date_from_text(text)
                house_jobs = [
                    job for job in nuki_jobs.values()
                    if int(job.get("apartment_id") or 0) == apartment_id
                    and parse_date(job.get("arrival"))
                    and parse_date(job.get("departure"))
                    and parse_date(job.get("departure")) >= today
                ]
                house_jobs.sort(key=lambda job: str(job.get("arrival") or ""))
                exact = [job for job in house_jobs if target_date and parse_date(job.get("arrival")) == target_date]
                selected = exact[0] if exact else (house_jobs[0] if house_jobs else None)
                if selected:
                    if "Code versendet" in text or "Testmail versendet" in text:
                        if target_date and not exact:
                            selected.update(
                                status="changed_after_sent",
                                previous_arrival=target_date.isoformat(),
                                request_id=None,
                                sent_at="legacy_node_red",
                            )
                        else:
                            selected.update(status="sent", sent_at="legacy_node_red", request_id=None)
                    elif "Ignoriert" in text:
                        selected.update(status="ignored", request_id=None)

        meta["legacy_helpers_imported"] = True
        meta["legacy_helpers_imported_at"] = _iso_now()
        await self.runtime.store.async_save()

    async def async_process(
        self,
        *,
        force_laundry_notify: bool = False,
        force_nuki_notify: bool = False,
    ) -> None:
        async with self._lock:
            bookings = valid_bookings(self.runtime.coordinator.data or [], self.runtime.houses)
            await self._process_laundry(bookings, force_notify=force_laundry_notify)
            await self._process_nuki(bookings, force_notify=force_nuki_notify)
            self.runtime.store.data["workflow_meta"] = {
                **self.runtime.store.workflow_meta,
                "last_processed_at": _iso_now(),
            }
            await self._persist()

    # ------------------------------------------------------------------
    # Laundry
    # ------------------------------------------------------------------
    async def _process_laundry(self, bookings: list[dict[str, Any]], *, force_notify: bool) -> None:
        today = dt_util.now().date()
        now = dt_util.now()
        jobs = self.runtime.store.laundry_jobs
        requests = self.runtime.store.laundry_requests
        current = _booking_map(bookings, self.runtime.houses)
        horizon = int(self.runtime.coordinator.horizon_days)
        lead_days = int(self._option(CONF_LAUNDRY_LEAD_DAYS, DEFAULT_LAUNDRY_LEAD_DAYS))
        reminder = timedelta(hours=int(self._option(CONF_LAUNDRY_REMINDER_HOURS, DEFAULT_LAUNDRY_REMINDER_HOURS)))
        cancellation_alerts: list[dict[str, Any]] = []

        for booking_id, booking in current.items():
            apartment = booking.get("apartment") or {}
            apartment_id = apartment.get("id")
            if apartment_id not in self.runtime.houses or not booking.get("departure"):
                continue
            previous = jobs.get(booking_id)
            base = {
                "booking_id": booking_id,
                "apartment_id": apartment_id,
                "house": self.runtime.houses[apartment_id],
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "seen_date": today.isoformat(),
            }
            if not previous:
                jobs[booking_id] = {
                    **base,
                    "status": "new",
                    "request_id": None,
                    "last_notified_at": None,
                    "snooze_until": None,
                    "sent_at": None,
                    "previous_departure": None,
                }
                continue

            if previous.get("status") == "missing":
                previous.update(status="new", request_id=None, last_notified_at=None, snooze_until=None)
            elif previous.get("status") == "missing_after_sent":
                previous["status"] = "sent"

            if previous.get("departure") != booking.get("departure"):
                was_sent = previous.get("status") == "sent"
                jobs[booking_id] = {
                    **previous,
                    **base,
                    "status": "changed" if was_sent else "new",
                    "request_id": None,
                    "last_notified_at": None,
                    "snooze_until": None,
                    "previous_departure": previous.get("departure"),
                }
            else:
                jobs[booking_id] = {**previous, **base}

        # Missing/cancelled bookings inside the relevant horizon.
        for booking_id, job in list(jobs.items()):
            days = _days_until(job.get("departure"), today)
            if days is None or days < 0 or days > horizon or job.get("seen_date") == today.isoformat():
                continue
            status = job.get("status")
            if status in {"new", "pending", "changed", "email_error", "ignored", "config_error"}:
                job.update(status="missing", request_id=None, snooze_until=None)
            elif status == "sent":
                job.update(status="missing_after_sent", request_id=None)
                cancellation_alerts.append(job)

        # Cleanup.
        for booking_id, job in list(jobs.items()):
            days = _days_until(job.get("departure"), today)
            if days is not None and days < -30:
                jobs.pop(booking_id, None)
        for request_id, request in list(requests.items()):
            created = _parse_dt(request.get("created_at"))
            if created and created < now - timedelta(days=60):
                requests.pop(request_id, None)

        if not bool(self._option(CONF_LAUNDRY_ENABLED, DEFAULT_LAUNDRY_ENABLED)):
            return
        if not force_notify and not self._notifications_allowed(now):
            return

        if cancellation_alerts:
            lines = [f"{j.get('house')}: bisherige Abreise {_format_de(j.get('departure'))}" for j in cancellation_alerts]
            await self._notify(
                "Wäsche prüfen – Buchung entfallen?",
                "\n".join(lines)
                + "\n\nFür diese Buchung war die Wäsche bereits angefordert. Bitte Wäscherei prüfen.",
                data={"tag": "smoobu_laundry_cancel", "persistent": True, "sticky": True},
            )

        candidates: list[dict[str, Any]] = []
        for job in jobs.values():
            days = _days_until(job.get("departure"), today)
            if days is None or days < 0 or days > lead_days:
                continue
            if job.get("seen_date") != today.isoformat():
                continue
            if job.get("status") not in {"new", "pending", "changed", "email_error", "config_error"}:
                continue

            # Validate the external house/product configuration before asking for approval.
            try:
                await self.hass.async_add_executor_job(self.runtime.laundry.calculate, [int(job["apartment_id"])])
                if job.get("status") == "config_error":
                    job["status"] = "new"
            except LaundryConfigError as err:
                job["status"] = "config_error"
                job["last_error"] = str(err)
                continue

            if not force_notify:
                snooze = _parse_dt(job.get("snooze_until"))
                if snooze and snooze > now:
                    continue
                last = _parse_dt(job.get("last_notified_at"))
                if last and now - last < reminder:
                    continue
            candidates.append(job)

        if not candidates:
            return

        request_id = _request_id("laundry")
        item_ids = [str(j["booking_id"]) for j in sorted(candidates, key=lambda x: (x.get("departure") or "", x.get("house") or ""))]
        requests[request_id] = {
            "id": request_id,
            "created_at": _iso_now(),
            "status": "pending",
            "booking_ids": item_ids,
        }
        notified_at = _iso_now()
        for job in candidates:
            job.update(status="pending", request_id=request_id, last_notified_at=notified_at, snooze_until=None)

        lines = []
        for job in sorted(candidates, key=lambda x: (x.get("departure") or "", x.get("house") or "")):
            line = f"{job.get('house')}: Abreise {_format_de(job.get('departure'))}"
            if job.get("previous_departure"):
                line += f" ⚠️ geändert von {_format_de(job.get('previous_departure'))}"
            lines.append(line)
        min_days = min(_days_until(j.get("departure"), today) or 0 for j in candidates)
        urgency = f"\nAchtung: kürzester Vorlauf nur noch {min_days} Tag(e)." if min_days < lead_days else ""
        await self._notify(
            "Wäschebedarf",
            "\n".join(lines) + urgency + "\n\nWäscherei jetzt informieren?",
            data={
                "tag": "smoobu_laundry",
                "persistent": True,
                "sticky": True,
                "actions": [
                    {"action": f"{LAUNDRY_ACTION_PREFIX}_SEND_{request_id}", "title": "Bestellen"},
                    {"action": f"{LAUNDRY_ACTION_PREFIX}_LATER_{request_id}", "title": "Morgen erinnern"},
                    {"action": f"{LAUNDRY_ACTION_PREFIX}_SKIP_{request_id}", "title": "Ignorieren"},
                ],
            },
        )

    async def _handle_laundry_action_string(self, action: str) -> None:
        match = re.match(rf"^{LAUNDRY_ACTION_PREFIX}_(SEND|LATER|SKIP)_(.+)$", action)
        if match:
            await self.async_laundry_command(match.group(1).lower(), match.group(2))

    async def async_laundry_command(self, command: str, request_id: str | None = None) -> None:
        async with self._lock:
            if not bool(self._option(CONF_LAUNDRY_ENABLED, DEFAULT_LAUNDRY_ENABLED)):
                await self._notify("Wäsche", "Wäsche-Automatik ist in den Integrationsoptionen deaktiviert.")
                return
            requests = self.runtime.store.laundry_requests
            jobs = self.runtime.store.laundry_jobs
            if request_id is None:
                request_id = self._latest_open_request(requests)
            request = requests.get(str(request_id)) if request_id else None
            if not request:
                await self._notify("Wäsche", "Diese Freigabe ist nicht mehr aktuell.")
                return

            booking_ids = [
                str(value)
                for value in request.get("booking_ids", [])
                if str(value) in jobs and jobs[str(value)].get("request_id") == request_id
            ]
            if not booking_ids:
                await self._notify("Wäsche", "Diese Freigabe wurde bereits verarbeitet oder ersetzt.")
                return

            if command == "later":
                tomorrow = dt_util.now() + timedelta(days=1)
                snooze = datetime.combine(tomorrow.date(), time(7, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE)
                request.update(status="postponed", postponed_at=_iso_now())
                for booking_id in booking_ids:
                    jobs[booking_id].update(status="pending", snooze_until=snooze.isoformat())
                await self._persist()
                await self._notify("Wäsche", "Okay. Ich erinnere morgen wieder.")
                return

            if command == "skip":
                request.update(status="ignored", ignored_at=_iso_now())
                for booking_id in booking_ids:
                    jobs[booking_id].update(status="ignored", request_id=None, snooze_until=None)
                await self._persist()
                await self._notify("Wäsche", "Wäscheanforderung wurde ignoriert.")
                return

            if command != "send":
                raise ValueError(f"Unbekannter Wäsche-Befehl: {command}")

            active_jobs = [jobs[bid] for bid in booking_ids]
            apartment_ids = [int(job["apartment_id"]) for job in active_jobs]
            try:
                calculation = await self.hass.async_add_executor_job(self.runtime.laundry.calculate, apartment_ids)
                template_name = "laundry_change" if any(job.get("previous_departure") for job in active_jobs) else "laundry_order"
                template = await self.hass.async_add_executor_job(self.runtime.templates.load, template_name)
                values = self._laundry_template_values(active_jobs, calculation)
                rendered = self.runtime.templates.render(template, values)
                if not rendered.get("valid"):
                    raise TemplateError("Fehlende Pflicht-Platzhalter: " + ", ".join(rendered.get("missing_required") or []))
                recipient = str(self._option(CONF_LAUNDRY_EMAIL, DEFAULT_LAUNDRY_EMAIL) or "").strip()
                request.update(status="sending", sending_at=_iso_now())
                await self._persist()
                await self.runtime.mail.async_send(recipient, rendered["subject"], rendered["body"])
            except (LaundryConfigError, TemplateError, MailError) as err:
                request.update(status="email_error", error_at=_iso_now(), last_error=str(err))
                for booking_id in booking_ids:
                    jobs[booking_id].update(status="email_error", last_error=str(err))
                await self._persist()
                await self._notify(
                    "Wäsche-Mail NICHT versendet",
                    f"Die E-Mail an die Wäscherei ist fehlgeschlagen: {err}. Der Bedarf bleibt offen.",
                    data={"tag": "smoobu_laundry"},
                )
                return

            sent_at = _iso_now()
            request.update(status="sent", sent_at=sent_at)
            for booking_id in booking_ids:
                jobs[booking_id].update(
                    status="sent",
                    sent_at=sent_at,
                    request_id=None,
                    previous_departure=None,
                    snooze_until=None,
                    last_error=None,
                )
            await self._persist()
            await self._notify("Wäscheanforderung versendet", f"E-Mail an {recipient} wurde versendet.")

    def _laundry_template_values(self, jobs: list[dict[str, Any]], calculation: dict[str, Any]) -> dict[str, Any]:
        dates = sorted({_format_de(job.get("departure")) for job in jobs})
        schedule_lines = []
        for job in sorted(jobs, key=lambda x: (x.get("departure") or "", x.get("house") or "")):
            line = f"{job.get('house')}: Wechsel am {_format_de(job.get('departure'))}"
            if job.get("previous_departure"):
                line += f" (geändert von {_format_de(job.get('previous_departure'))})"
            schedule_lines.append(line)
        product_lines = [
            f"{item.get('quantity')} {item.get('unit')} {item.get('name')}"
            for item in calculation.get("products", [])
        ]
        return {
            "mhLaundryDates": ", ".join(dates),
            "mhLaundrySchedule": "\n".join(schedule_lines),
            "mhLaundryProducts": "\n".join(product_lines),
            "mhLaundryNet": calculation.get("net", ""),
            "mhLaundryVat": calculation.get("vat", ""),
            "mhLaundryVatPercent": calculation.get("vat_percent", ""),
            "mhLaundryGross": calculation.get("gross", ""),
            "mhLaundryCurrency": calculation.get("currency", "EUR"),
            "mhLaundryHouseCount": len(jobs),
        }

    async def async_reset_laundry(self) -> None:
        async with self._lock:
            jobs = self.runtime.store.laundry_jobs
            requests = self.runtime.store.laundry_requests
            resettable = {"new", "pending", "ignored", "changed", "missing", "email_error", "config_error"}
            for job in jobs.values():
                if job.get("status") in resettable:
                    job.update(
                        status="new",
                        request_id=None,
                        last_notified_at=None,
                        snooze_until=None,
                        last_error=None,
                    )
            for rid, request in list(requests.items()):
                if request.get("status") != "sent":
                    requests.pop(rid, None)
            await self._persist()

    # ------------------------------------------------------------------
    # NUKI
    # ------------------------------------------------------------------
    async def _process_nuki(self, bookings: list[dict[str, Any]], *, force_notify: bool) -> None:
        today = dt_util.now().date()
        now = dt_util.now()
        jobs = self.runtime.store.nuki_jobs
        requests = self.runtime.store.nuki_requests
        current = _booking_map(bookings, self.runtime.houses)
        horizon = int(self.runtime.coordinator.horizon_days)
        lead_days = int(self._option(CONF_NUKI_LEAD_DAYS, DEFAULT_NUKI_LEAD_DAYS))
        reminder = timedelta(hours=int(self._option(CONF_NUKI_REMINDER_HOURS, DEFAULT_NUKI_REMINDER_HOURS)))
        cancellation_alerts: list[dict[str, Any]] = []

        for booking_id, booking in current.items():
            apartment = booking.get("apartment") or {}
            apartment_id = apartment.get("id")
            if apartment_id not in self.runtime.houses or not booking.get("arrival"):
                continue
            previous = jobs.get(booking_id)
            base = {
                "booking_id": booking_id,
                "apartment_id": apartment_id,
                "house": self.runtime.houses[apartment_id],
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "seen_date": today.isoformat(),
            }
            if not previous:
                jobs[booking_id] = {
                    **base,
                    "status": "new",
                    "request_id": None,
                    "last_notified_at": None,
                    "last_code_check_at": None,
                    "last_code_missing_notice_date": None,
                    "snooze_until": None,
                    "sent_at": None,
                    "previous_arrival": None,
                }
                continue

            if previous.get("status") == "missing":
                previous.update(status="new", request_id=None, last_notified_at=None, snooze_until=None)
            elif previous.get("status") == "missing_after_sent":
                previous["status"] = "sent"

            if previous.get("arrival") != booking.get("arrival"):
                was_sent = previous.get("status") == "sent"
                jobs[booking_id] = {
                    **previous,
                    **base,
                    "status": "changed_after_sent" if was_sent else "new",
                    "request_id": None,
                    "last_notified_at": None,
                    "last_code_check_at": None,
                    "last_code_missing_notice_date": None,
                    "snooze_until": None,
                    "previous_arrival": previous.get("arrival"),
                }
            else:
                jobs[booking_id] = {**previous, **base}

        for booking_id, job in list(jobs.items()):
            days = _days_until(job.get("arrival"), today)
            if days is None or days < 0 or days > horizon or job.get("seen_date") == today.isoformat():
                continue
            status = job.get("status")
            if status in {"new", "pending", "code_missing", "changed_after_sent", "email_error", "ignored"}:
                job.update(status="missing", request_id=None, snooze_until=None)
            elif status == "sent":
                job.update(status="missing_after_sent", request_id=None)
                cancellation_alerts.append(job)

        for booking_id, job in list(jobs.items()):
            days = _days_until(job.get("arrival"), today)
            if days is not None and days < -30:
                jobs.pop(booking_id, None)
        for request_id, request in list(requests.items()):
            created = _parse_dt(request.get("created_at"))
            if created and created < now - timedelta(days=60):
                requests.pop(request_id, None)

        if not bool(self._option(CONF_NUKI_ENABLED, DEFAULT_NUKI_ENABLED)):
            return
        if not force_notify and not self._notifications_allowed(now):
            return

        if cancellation_alerts:
            for job in cancellation_alerts:
                await self._notify(
                    "🔴 NUKI-Buchung prüfen",
                    f"{job.get('house')}\nAnreise: {_format_de(job.get('arrival'))}\n\n"
                    "Der NUKI-Code wurde bereits per E-Mail versendet, die Buchung wird aber nicht mehr von Smoobu geliefert.",
                    data={"tag": f"smoobu_nuki_cancel_{job.get('booking_id')}", "persistent": True, "sticky": True},
                )

        candidates = []
        for job in jobs.values():
            days = _days_until(job.get("arrival"), today)
            if days is None or days < 0 or days > lead_days:
                continue
            if job.get("seen_date") != today.isoformat():
                continue
            if job.get("status") not in {"new", "pending", "code_missing", "changed_after_sent", "email_error"}:
                continue
            if not force_notify:
                snooze = _parse_dt(job.get("snooze_until"))
                if snooze and snooze > now:
                    continue
                last = _parse_dt(job.get("last_notified_at"))
                if job.get("status") == "pending" and last and now - last < reminder:
                    continue
            candidates.append(job)

        if not candidates:
            return

        custom = await self.runtime.api.get_custom_placeholders()
        code_map = self._nuki_code_map(custom)
        booking_by_id = _booking_map(bookings, self.runtime.houses)

        for job in sorted(candidates, key=lambda x: (x.get("arrival") or "", x.get("house") or "")):
            booking_id = str(job["booking_id"])
            code = str(code_map.get(booking_id) or "").strip()
            job["last_code_check_at"] = _iso_now()
            if not code:
                job.update(status="code_missing", request_id=None)
                if job.get("last_code_missing_notice_date") != today.isoformat():
                    job["last_code_missing_notice_date"] = today.isoformat()
                    await self._notify(
                        "🔑 NUKI-Code nicht gefunden",
                        f"{job.get('house')}\nAnreise: {_format_de(job.get('arrival'))}\n\n"
                        "Für diese Buchung wurde in Smoobu noch kein NUKI-Code gefunden. Die Integration prüft später erneut.",
                        data={"tag": f"nuki_missing_{booking_id}"},
                    )
                continue

            request_id = _request_id("nuki")
            requests[request_id] = {
                "id": request_id,
                "created_at": _iso_now(),
                "status": "pending",
                "booking_id": booking_id,
            }
            job.update(
                status="pending",
                request_id=request_id,
                last_notified_at=_iso_now(),
                last_code_missing_notice_date=None,
                snooze_until=None,
            )
            booking = booking_by_id.get(booking_id) or {}
            guest = str(booking.get("guest-name") or "").strip() or "–"
            guest_email = str(booking.get("email") or "").strip() or "–"
            await self._notify(
                f"🔑 NUKI {job.get('house')}",
                f"Gast: {guest}\nAnreise: {_format_de(job.get('arrival'))}\nNUKI-Code: {code}\n"
                f"E-Mail: {guest_email}\n\nZugangscode an den Gast senden?",
                data={
                    "tag": f"nuki_{booking_id}",
                    "persistent": True,
                    "sticky": True,
                    "actions": [
                        {"action": f"{NUKI_ACTION_PREFIX}_SEND_{request_id}", "title": "E-Mail senden"},
                        {"action": f"{NUKI_ACTION_PREFIX}_LATER_{request_id}", "title": "Morgen erinnern"},
                        {"action": f"{NUKI_ACTION_PREFIX}_SKIP_{request_id}", "title": "Ignorieren"},
                    ],
                },
            )

    def _nuki_code_map(self, placeholders: list[dict[str, Any]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in placeholders:
            if not isinstance(item, dict):
                continue
            is_booking = str(item.get("type", "")).lower() in {"1", "booking"}
            if not is_booking:
                continue
            key = _normalize_key(item.get("key"))
            if key != "nukipin" and not ("nuki" in key and ("pin" in key or "code" in key)):
                continue
            booking_id = str(item.get("foreignId") or "")
            code = str(item.get("defaultValue") or "").strip()
            if booking_id and code and _normalize_key(code) != "nukipin":
                result[booking_id] = code
        return result

    async def _handle_nuki_action_string(self, action: str) -> None:
        match = re.match(rf"^{NUKI_ACTION_PREFIX}_(SEND|LATER|SKIP)_(.+)$", action)
        if match:
            await self.async_nuki_command(match.group(1).lower(), match.group(2))

    async def async_nuki_command(self, command: str, request_id: str | None = None) -> None:
        async with self._lock:
            if not bool(self._option(CONF_NUKI_ENABLED, DEFAULT_NUKI_ENABLED)):
                await self._notify("NUKI", "NUKI-Automatik ist in den Integrationsoptionen deaktiviert.")
                return
            requests = self.runtime.store.nuki_requests
            jobs = self.runtime.store.nuki_jobs
            if request_id is None:
                request_id = self._latest_open_request(requests)
            request = requests.get(str(request_id)) if request_id else None
            if not request:
                await self._notify("NUKI", "Diese Freigabe ist nicht mehr aktuell.")
                return
            booking_id = str(request.get("booking_id") or "")
            job = jobs.get(booking_id)
            if not job or job.get("request_id") != request_id:
                await self._notify("NUKI", "Diese Freigabe wurde bereits verarbeitet oder ersetzt.")
                return

            if command == "later":
                tomorrow = dt_util.now() + timedelta(days=1)
                snooze = datetime.combine(tomorrow.date(), time(7, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE)
                request.update(status="postponed", postponed_at=_iso_now())
                job.update(status="pending", snooze_until=snooze.isoformat())
                await self._persist()
                await self._notify("NUKI", "Okay. Ich erinnere morgen wieder.")
                return

            if command == "skip":
                request.update(status="ignored", ignored_at=_iso_now())
                job.update(status="ignored", request_id=None, snooze_until=None)
                await self._persist()
                await self._notify("NUKI", "NUKI-Mail wurde ignoriert.")
                return

            if command != "send":
                raise ValueError(f"Unbekannter NUKI-Befehl: {command}")

            try:
                custom = await self.runtime.api.get_booking_custom_placeholders(booking_id)
                code = str(custom.get("nukiPin") or custom.get("[nukiPin]") or "").strip()
                if not code:
                    # Fallback for differently named NUKI placeholder keys.
                    for key, value in custom.items():
                        nk = _normalize_key(key)
                        if nk == "nukipin" or ("nuki" in nk and ("pin" in nk or "code" in nk)):
                            code = str(value or "").strip()
                            break
                if not code:
                    raise TemplateError("NUKI-Code konnte nicht erneut aus Smoobu gelesen werden")

                normal = await self.runtime.api.get_booking_placeholders(booking_id)
                values = {**normal, **custom, "nukiPin": code, "bookingID": booking_id}
                language = self._booking_language(booking_id)
                template_name = "nuki_de" if language.lower().startswith("de") else "nuki_en"
                template = await self.hass.async_add_executor_job(self.runtime.templates.load, template_name)
                rendered = self.runtime.templates.render(template, values)
                if not rendered.get("valid"):
                    raise TemplateError("Fehlende Pflicht-Platzhalter: " + ", ".join(rendered.get("missing_required") or []))

                guest_email = str(normal.get("guestEmail") or normal.get("email") or self._booking_email(booking_id) or "").strip()
                test_mode = bool(self._option(CONF_NUKI_TEST_MODE, DEFAULT_NUKI_TEST_MODE))
                recipient = str(self._option(CONF_NUKI_TEST_EMAIL, DEFAULT_NUKI_TEST_EMAIL) if test_mode else guest_email).strip()
                if not recipient:
                    raise MailError("Gast-E-Mail-Adresse fehlt")

                subject = rendered["subject"]
                body = rendered["body"]
                if test_mode:
                    subject = f"[TEST] {subject}"
                    body = f"TESTMODUS – Originalempfänger: {guest_email or 'nicht vorhanden'}\n\n{body}"

                request.update(status="sending", sending_at=_iso_now())
                await self._persist()
                await self.runtime.mail.async_send(recipient, subject, body)
            except (TemplateError, MailError) as err:
                request.update(status="email_error", error_at=_iso_now(), last_error=str(err))
                job.update(status="email_error", last_error=str(err))
                await self._persist()
                await self._notify("🔴 NUKI-Mail nicht versendet", str(err), data={"tag": "nuki_email_error"})
                return
            except Exception as err:  # API errors are intentionally surfaced to the workflow state.
                request.update(status="email_error", error_at=_iso_now(), last_error=str(err))
                job.update(status="email_error", last_error=str(err))
                await self._persist()
                await self._notify("🔴 NUKI-Mail nicht versendet", str(err), data={"tag": "nuki_email_error"})
                return

            sent_at = _iso_now()
            request.update(status="sent", sent_at=sent_at)
            job.update(
                status="sent",
                sent_at=sent_at,
                request_id=None,
                previous_arrival=None,
                snooze_until=None,
                last_error=None,
            )
            await self._persist()
            await self._notify(
                "NUKI-Code versendet",
                f"{job.get('house')}: NUKI-Mail wurde {'im Testmodus ' if test_mode else ''}versendet.",
            )

    def _booking_language(self, booking_id: str) -> str:
        for booking in valid_bookings(self.runtime.coordinator.data or [], self.runtime.houses):
            if str(booking.get("id")) == str(booking_id):
                return str(booking.get("language") or "de")
        return "de"

    def _booking_email(self, booking_id: str) -> str:
        for booking in valid_bookings(self.runtime.coordinator.data or [], self.runtime.houses):
            if str(booking.get("id")) == str(booking_id):
                return str(booking.get("email") or "")
        return ""

    async def async_reset_nuki(self) -> None:
        async with self._lock:
            jobs = self.runtime.store.nuki_jobs
            requests = self.runtime.store.nuki_requests
            resettable = {"new", "pending", "ignored", "missing", "code_missing", "changed_after_sent", "email_error"}
            for job in jobs.values():
                if job.get("status") in resettable:
                    job.update(
                        status="new",
                        request_id=None,
                        last_notified_at=None,
                        last_code_check_at=None,
                        last_code_missing_notice_date=None,
                        snooze_until=None,
                        last_error=None,
                    )
            for rid, request in list(requests.items()):
                if request.get("status") != "sent":
                    requests.pop(rid, None)
            await self._persist()

    async def async_reset_all_workflow_state(self) -> None:
        """Clear all workflow state, including sent markers, for migration/testing only."""
        async with self._lock:
            self.runtime.store.data["laundry_jobs"] = {}
            self.runtime.store.data["laundry_requests"] = {}
            self.runtime.store.data["nuki_jobs"] = {}
            self.runtime.store.data["nuki_requests"] = {}
            self.runtime.store.data["workflow_meta"] = {
                **self.runtime.store.workflow_meta,
                "legacy_helpers_imported": True,
                "legacy_helpers_imported_at": _iso_now(),
                "last_full_reset_at": _iso_now(),
            }
            await self._persist()

    def health_status(self) -> tuple[str, dict[str, Any]]:
        """Return a compact diagnostic view of the workflow engine."""
        meta = self.runtime.store.workflow_meta
        start = int(self._option(CONF_NOTIFICATION_START_HOUR, DEFAULT_NOTIFICATION_START_HOUR))
        end = int(self._option(CONF_NOTIFICATION_END_HOUR, DEFAULT_NOTIFICATION_END_HOUR))

        laundry_error = None
        laundry_config_exists = self.runtime.laundry.path.is_file()
        if laundry_config_exists:
            try:
                config = self.runtime.laundry.load()
                houses = config.get("houses") or {}
                laundry_profiles_enabled = {
                    str(apartment_id): bool(
                        (houses.get(str(apartment_id)) or houses.get(apartment_id) or {}).get("enabled", True)
                    )
                    for apartment_id in self.runtime.houses
                }
            except Exception as err:
                laundry_error = str(err)
                laundry_profiles_enabled = {}
        else:
            laundry_profiles_enabled = {}

        template_files = {
            name: (self.runtime.templates.directory / f"{name}.yaml").is_file()
            for name in ("laundry_order", "laundry_change", "nuki_de", "nuki_en")
        }

        notify_service = str(self._option(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE) or "").strip()
        notify_service_available = False
        if notify_service and "." in notify_service:
            notify_domain, notify_name = notify_service.split(".", 1)
            notify_service_available = self.hass.services.has_service(notify_domain, notify_name)

        attrs = {
            "laundry_enabled": bool(self._option(CONF_LAUNDRY_ENABLED, DEFAULT_LAUNDRY_ENABLED)),
            "nuki_enabled": bool(self._option(CONF_NUKI_ENABLED, DEFAULT_NUKI_ENABLED)),
            "notification_start_hour": start,
            "notification_end_hour": end,
            "notifications_allowed_now": self._notifications_allowed(),
            "notify_service": notify_service,
            "notify_service_available": notify_service_available,
            "laundry_config_path": str(self.runtime.laundry.path),
            "laundry_config_exists": laundry_config_exists,
            "laundry_profiles_enabled": laundry_profiles_enabled,
            "laundry_config_error": laundry_error,
            "template_files": template_files,
            "laundry_jobs": len(self.runtime.store.laundry_jobs),
            "laundry_requests": len(self.runtime.store.laundry_requests),
            "nuki_jobs": len(self.runtime.store.nuki_jobs),
            "nuki_requests": len(self.runtime.store.nuki_requests),
            "last_processed_at": meta.get("last_processed_at"),
            "last_full_reset_at": meta.get("last_full_reset_at"),
        }

        house_status: dict[str, Any] = {}
        for apartment_id, house in self.runtime.houses.items():
            slug = house_slug(house, apartment_id)
            try:
                laundry_state, laundry_detail = self.laundry_status_for_house(apartment_id)
            except Exception as err:
                laundry_state, laundry_detail = "Statusfehler", {"error": str(err)}
            try:
                nuki_state, nuki_detail = self.nuki_status_for_house(apartment_id)
            except Exception as err:
                nuki_state, nuki_detail = "Statusfehler", {"error": str(err)}

            attrs[f"{slug}_waesche_status"] = laundry_state
            attrs[f"{slug}_nuki_status"] = nuki_state
            attrs[f"{slug}_waesche_detail"] = laundry_detail
            attrs[f"{slug}_nuki_detail"] = nuki_detail
            house_status[slug] = {"waesche": laundry_state, "nuki": nuki_state}

        attrs["house_status"] = house_status

        today = dt_util.now().date()
        laundry_lead = int(self._option(CONF_LAUNDRY_LEAD_DAYS, DEFAULT_LAUNDRY_LEAD_DAYS))
        nuki_lead = int(self._option(CONF_NUKI_LEAD_DAYS, DEFAULT_NUKI_LEAD_DAYS))

        laundry_due = [
            job for job in self.runtime.store.laundry_jobs.values()
            if (_days_until(job.get("departure"), today) is not None)
            and 0 <= _days_until(job.get("departure"), today) <= laundry_lead
            and job.get("status") in {"new", "pending", "changed", "email_error", "config_error"}
        ]
        nuki_due = [
            job for job in self.runtime.store.nuki_jobs.values()
            if (_days_until(job.get("arrival"), today) is not None)
            and 0 <= _days_until(job.get("arrival"), today) <= nuki_lead
            and job.get("status") in {"new", "pending", "code_missing", "changed_after_sent", "email_error"}
        ]

        attrs["laundry_due_count"] = len(laundry_due)
        attrs["nuki_due_count"] = len(nuki_due)
        attrs["latest_laundry_request"] = self._latest_open_request(self.runtime.store.laundry_requests)
        attrs["latest_nuki_request"] = self._latest_open_request(self.runtime.store.nuki_requests)

        if not laundry_config_exists or laundry_error:
            return "Konfiguration prüfen", attrs
        if not all(template_files.values()):
            return "Templates prüfen", attrs
        if not attrs["laundry_enabled"] and not attrs["nuki_enabled"]:
            return "Automatik aus", attrs
        if not notify_service_available:
            return "Notify prüfen", attrs
        if not meta.get("last_processed_at"):
            return "Noch nicht verarbeitet", attrs
        return "Bereit", attrs

    @staticmethod
    def _latest_open_request(requests: dict[str, dict[str, Any]]) -> str | None:
        open_requests = [
            request
            for request in requests.values()
            if request.get("status") in {"pending", "postponed", "email_error", "sending"}
        ]
        if not open_requests:
            return None
        open_requests.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return str(open_requests[0].get("id") or "") or None

    # ------------------------------------------------------------------
    # Status presentation for HA entities
    # ------------------------------------------------------------------
    def laundry_status_for_house(self, apartment_id: int) -> tuple[str, dict[str, Any]]:
        return self._status_for_house("laundry", apartment_id)

    def nuki_status_for_house(self, apartment_id: int) -> tuple[str, dict[str, Any]]:
        return self._status_for_house("nuki", apartment_id)

    def _status_for_house(self, kind: str, apartment_id: int) -> tuple[str, dict[str, Any]]:
        today = dt_util.now().date()
        jobs = self.runtime.store.laundry_jobs if kind == "laundry" else self.runtime.store.nuki_jobs
        date_field = "departure" if kind == "laundry" else "arrival"
        lead_days = int(
            self._option(
                CONF_LAUNDRY_LEAD_DAYS if kind == "laundry" else CONF_NUKI_LEAD_DAYS,
                DEFAULT_LAUNDRY_LEAD_DAYS if kind == "laundry" else DEFAULT_NUKI_LEAD_DAYS,
            )
        )
        horizon = int(self.runtime.coordinator.horizon_days)
        candidates = []
        for job in jobs.values():
            if int(job.get("apartment_id") or 0) != apartment_id:
                continue
            days = _days_until(job.get(date_field), today)
            if days is not None and 0 <= days <= horizon:
                candidates.append((days, job))
        if not candidates:
            label = "Kein Wechsel" if kind == "laundry" else "Keine Anreise"
            return f"{label} ≤ {horizon} Tage", {}
        days, job = sorted(candidates, key=lambda item: (item[0], str(item[1].get(date_field) or "")))[0]
        status = str(job.get("status") or "new")
        enabled = bool(self._option(
            CONF_LAUNDRY_ENABLED if kind == "laundry" else CONF_NUKI_ENABLED,
            DEFAULT_LAUNDRY_ENABLED if kind == "laundry" else DEFAULT_NUKI_ENABLED,
        ))
        attrs = {
            "automation_enabled": enabled,
            "booking_id": job.get("booking_id"),
            "house": job.get("house")          "housorted": TrundryHBLED,
 in( placeholF,ousorted": TrundryHBLE3aeholF,ousuRY_ENABLED if ki.valuuuuuuwAYS if kin
 in( placeholF,_lineinei       1g_id,
      oeinein kin
 ins self._lock:
            if not bool(self._option(CONF_LAUNDRY_ENABLED, DEFAULT_LAUNDRY_ENABLED)):
                await self._notify("Wäsche", "Wäsche-Automatik ist in den Integrationsoptionen deaktiviert.")
                return
            requests = se": ,r    ULT_L    "bokin
 ins(Pn de_id:
                continue
            days = _days_until(job.get(date_field), today)
            if days is not None and 0 <= days <= horizon:
                candidates.append((days, job))
        if not candidates:
     P{
            ly          candidates.append((days, job))
        if not caandidaternappend((days, job))
partment_id not in self.runtime.houses or not booking.get("arrival"):
                continue
            previous = jobs.get(booking_id)
            base = {
                "booking_id": booking_id,
                "apartment_id": apartment_id,
          e CONF_NUKI_LEAD_DAYS,
                DEFAULT_LAUNDRY_LEAD_DAYS if kind == "laundry" else DuUND           rRY_LEAIr1       return "Templates prüfen", attrs return "Templates prüfen", attrs return "Templates prüfen", attrs return "Templates prüfen", attrs return "Templates prüfen", attrv       jobs = self.runtime.E      tmplates prüfen", attrv     ")          "housorted": TrundryHBLED,
 in( placeholF,ousorted": TrundryHBLE3aeholF,ousuRYf kind == "laundry" h<procecizon_days)
 l  rabled5ot caandidaternryHBv     prüetu_t c 6 returnst-E-Mail-          self.runtime.store.data["nuki_joquest=temp prüfen", attrr" job))
pat-E-Muests = se": ,r    ULT_L    "bokin
 ins(Pn de_id:
                continue
            days = _days_until(job.get(          job))
rissing", "changed_aftquests = [
    king_id,
           MODE, DEFAULT_NUKI_TEST_ST_ST_ST_ST"ssA es,ryHBLE3ae     elf._ue
      EFAULT_NUKI_TESTual4issus") innot Noner, dict1, attrs

 oNoner, dict1, attrs

 oNoner, dict1t     if (_days_until(job.get("departure"), today) is not None)
   