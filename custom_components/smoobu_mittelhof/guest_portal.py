"""Admin-only guest inbox/draft HTTP API. No invoice issuance in this release.

Persistent drafts contain guest personal data: use an admin account and protect HA backups.
Conversations are fetched live from Smoobu and NEVER copied to HA entity attributes.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .bookings import valid_bookings
from .const import DOMAIN
from .guest_finance import approve_message, booking_fingerprint, make_draft, revise_draft, utc_now, invoice_preflight, compose_message, request_invoice_demo_preview
from .invoice_numbers import planned_number, house_from_label

DRAFT_STORAGE_KEY = f"{DOMAIN}.guest_drafts"
DRAFT_STORAGE_VERSION = 1


class GuestDraftRepository:
    """Serialized HA Store writes and read-only snapshots with no entity exposure."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store[dict[str, Any]](hass, DRAFT_STORAGE_VERSION, DRAFT_STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._drafts: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        saved = await self._store.async_load()
        if isinstance(saved, dict) and isinstance(saved.get("drafts"), dict):
            self._drafts = saved["drafts"]

    async def _save(self) -> None:
        await self._store.async_save({"drafts": self._drafts})

    async def get(self, booking_id: str) -> dict[str, Any] | None:
        async with self._lock:
            value = self._drafts.get(str(booking_id))
            return deepcopy(value) if value else None

    async def list_summaries(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "booking_id": key,
                    "channel": d.get("source_channel"),
                    "invoice_status": d.get("invoice", {}).get("status"),
                    "message_status": d.get("message", {}).get("status"),
                    "revision": d.get("revision"),
                    "updated_at": d.get("updated_at"),
                }
                for key, d in self._drafts.items()
            ]

    async def prepare(
        self, booking: dict[str, Any], *, acknowledge_source: bool = False
    ) -> dict[str, Any]:
        """Automated sync only marks discrepancies; admin acknowledgement clears them.

        Previous manual edits are never replaced by a fresh Smoobu price.
        """
        key = str(booking["id"])
        fingerprint = booking_fingerprint(booking)
        async with self._lock:
            existing = self._drafts.get(key)
            if existing is None:
                self._drafts[key] = make_draft(booking)
                await self._save()
            elif existing["source_fingerprint"] != fingerprint:
                if not existing.get("source_change_pending"):
                    existing["source_change_pending"] = True
                    existing["revision"] += 1
                    existing["updated_at"] = utc_now()
                    if existing["message"]["status"] not in ("sent", "sending", "delivery_unknown"):
                        existing["message"]["status"] = "draft"
                        existing["message"]["approved_revision"] = None
                    existing["invoice"]["status"] = "draft"
                    existing["invoice_review"] = {
                        "state": "draft", "requested_revision": None, "requested_at": None
                    }
                    existing["audit"].append({"at": utc_now(), "event": "booking_changed_needs_review"})
                    await self._save()
                if acknowledge_source:
                    refreshed = make_draft(booking)
                    existing["source_fingerprint"] = fingerprint
                    existing["source_channel"] = refreshed["source_channel"]
                    existing["source_channel_class"] = refreshed["source_channel_class"]
                    existing["booking_context"] = refreshed["booking_context"]
                    existing["source_change_pending"] = False
                    existing["invoice_review"] = {
                        "state": "draft", "requested_revision": None, "requested_at": None
                    }
                    existing["revision"] += 1
                    existing["updated_at"] = utc_now()
                    existing["audit"].append({"at": utc_now(), "event": "source_change_acknowledged"})
                    await self._save()
            return deepcopy(self._drafts[key])

    async def revise(self, booking_id: str, revision: int, changes: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            current = self._drafts.get(booking_id)
            if not current:
                raise LookupError("Kein Entwurf")
            if current["revision"] != revision:
                raise RuntimeError("Entwurf wurde zwischenzeitlich geändert")
            if current["message"]["status"] in ("sending", "delivery_unknown"):
                raise RuntimeError("Nachrichtenversand ist noch ungeklärt")
            updated = revise_draft(current, changes)
            # An invoice edit invalidates message approval because payment text may depend on it.
            if current["message"]["status"] == "approved":
                updated["message"]["status"] = "draft"
                updated["message"]["approved_revision"] = None
            self._drafts[booking_id] = updated
            await self._save()
            return deepcopy(updated)

    async def regenerate_message(self, booking_id: str, revision: int) -> dict[str, Any]:
        """Explicitly rebuild text after manual payment edits; never sends it."""
        async with self._lock:
            current = self._drafts.get(booking_id)
            if not current or current["revision"] != revision:
                raise RuntimeError("Entwurf zwischenzeitlich geändert")
            if current["message"]["status"] in ("sent", "sending", "delivery_unknown"):
                raise RuntimeError("Bereits versendete oder unklare Nachricht darf nicht ersetzt werden")
            updated = deepcopy(current)
            text = compose_message(updated.get("booking_context") or {}, updated["invoice"])
            updated["message"].update(
                subject=text["subject"], body=text["body"], status="draft",
                approved_revision=None
            )
            updated["revision"] += 1
            updated["invoice_review"] = {
                "state": "draft", "requested_revision": None, "requested_at": None
            }
            updated["updated_at"] = utc_now()
            updated["audit"].append({"at": utc_now(), "event": "message_regenerated"})
            self._drafts[booking_id] = updated
            await self._save()
            return deepcopy(updated)

    async def request_demo_invoice_preview(self, booking_id: str, revision: int) -> dict[str, Any]:
        """Only queue the exact reviewed revision for a private DEMO test renderer."""
        async with self._lock:
            current = self._drafts.get(booking_id)
            if current is None or current["revision"] != revision:
                raise RuntimeError("Rechnungsentwurf ist zwischenzeitlich geändert worden")
            updated = request_invoice_demo_preview(current)
            self._drafts[booking_id] = updated
            await self._save()
            return deepcopy(updated)

    async def approve(self, booking_id: str, revision: int) -> dict[str, Any]:
        async with self._lock:
            current = self._drafts.get(booking_id)
            if not current:
                raise LookupError("Kein Entwurf")
            if current["revision"] != revision:
                raise RuntimeError("Entwurf wurde zwischenzeitlich geändert")
            updated = approve_message(current)
            self._drafts[booking_id] = updated
            await self._save()
            return deepcopy(updated)

    async def claim_send(self, booking_id: str, revision: int) -> dict[str, Any]:
        """Persist an in-flight marker BEFORE the network call to prevent double sends."""
        async with self._lock:
            current = self._drafts.get(booking_id)
            if not current or current["revision"] != revision:
                raise RuntimeError("Entwurfsrevision ist nicht aktuell")
            msg = current["message"]
            if msg["status"] != "approved" or msg.get("approved_revision") != revision:
                raise RuntimeError("Nachricht ist nicht für diese Revision freigegeben")
            msg["status"] = "sending"
            current["audit"].append({"at": utc_now(), "event": "send_claimed"})
            await self._save()
            return deepcopy(current)

    async def mark_sent(self, booking_id: str) -> None:
        async with self._lock:
            draft = self._drafts[booking_id]
            draft["message"]["status"] = "sent"
            draft["audit"].append({"at": utc_now(), "event": "message_sent_to_smoobu"})
            await self._save()

    async def mark_unknown(self, booking_id: str) -> None:
        async with self._lock:
            draft = self._drafts[booking_id]
            draft["message"]["status"] = "delivery_unknown"
            draft["audit"].append({"at": utc_now(), "event": "delivery_uncertain_manual_check"})
            await self._save()


def _get_runtime(hass: HomeAssistant):
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise web.HTTPServiceUnavailable(text="Smoobu Integration nicht geladen")
    return next(iter(entries.values()))


def _require_admin(request: web.Request) -> None:
    user = request.get("hass_user")
    if user is None or not user.is_admin:
        raise web.HTTPForbidden(text="Nur HA-Administratoren")


async def _checked_booking(runtime, booking_id: str) -> dict[str, Any]:
    if not booking_id.isdigit() or int(booking_id) < 1:
        raise web.HTTPBadRequest(text="Buchungs-ID ungültig")
    try:
        booking = await runtime.api.get_booking(int(booking_id))
    except Exception as exc:
        raise web.HTTPBadGateway(text="Smoobu-Buchung konnte nicht geladen werden") from exc
    apartment = booking.get("apartment") or {}
    if int(apartment.get("id") or 0) not in runtime.houses:
        raise web.HTTPNotFound(text="Buchung gehört nicht zu den konfigurierten Unterkünften")
    if booking.get("is-blocked-booking") or booking.get("type") not in ("reservation", "modification of booking"):
        raise web.HTTPConflict(text="Stornierte oder gesperrte Buchung")
    return booking


async def _parse_body(request: web.Request) -> dict[str, Any]:
    if request.content_length and request.content_length > 65536:
        raise web.HTTPRequestEntityTooLarge(max_size=65536, actual_size=request.content_length)
    try:
        body = await request.json()
    except (ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text="Ungültiges JSON") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="JSON-Objekt erforderlich")
    return body


class GuestThreadsView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/threads"
    name = "api:smoobu_mittelhof:guest_threads"
    requires_auth = True

    async def get(self, request: web.Request):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        try:
            result = await runtime.api.get_message_threads(page_number=1, page_size=100)
        except Exception as exc:
            raise web.HTTPBadGateway(text="Smoobu-Posteingang nicht erreichbar") from exc
        threads = [
            thread for thread in result.get("threads", [])
            if int((thread.get("apartment") or {}).get("id") or 0) in runtime.houses
        ]
        summaries = await runtime.guest_drafts.list_summaries()
        return self.json({"threads": threads, "unread_messages": result.get("unread_messages", 0),
                          "page_count": result.get("page_count", 1),
                          "drafts": summaries,
                          "message_send_enabled": runtime.guest_message_send_enabled})


class GuestBookingView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}"
    name = "api:smoobu_mittelhof:guest_booking"
    requires_auth = True

    async def get(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        try:
            messages = await runtime.api.get_booking_messages(booking_id)
        except Exception as exc:
            raise web.HTTPBadGateway(text="Smoobu-Gespräch nicht erreichbar") from exc
        draft = await runtime.guest_drafts.get(booking_id)
        # Do not expose NUKI/guest-app tokens or unfiltered booking raw payload.
        return self.json({
            "booking": {
                "id": booking.get("id"),
                "house": (booking.get("apartment") or {}).get("name"),
                "guest": booking.get("guest-name"),
                "arrival": booking.get("arrival"),
                "departure": booking.get("departure"),
                "channel": booking.get("channel"),
                "price": booking.get("price"),
                "price_paid_flag": booking.get("price-paid"),
            },
            "messages": messages,
            "draft": draft,
            "invoice_preflight": invoice_preflight(draft["invoice"]) if draft else None,
            "proposed_invoice_number": planned_number(
                runtime.houses.get(int((booking.get("apartment") or {}).get("id") or 0), ""),
                str(booking.get("arrival") or ""),
            ),
            "source_changed": bool(draft and (draft.get("source_change_pending") or draft["source_fingerprint"] != booking_fingerprint(booking))),
        })


class GuestDraftView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/draft"
    name = "api:smoobu_mittelhof:guest_draft"
    requires_auth = True

    async def post(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        return self.json(await runtime.guest_drafts.prepare(booking, acknowledge_source=True))

    async def patch(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        body = await _parse_body(request)
        booking = await _checked_booking(runtime, booking_id)
        current = await runtime.guest_drafts.get(booking_id)
        if current and current["source_fingerprint"] != booking_fingerprint(booking):
            await runtime.guest_drafts.prepare(booking)
            raise web.HTTPConflict(text="Buchung hat sich geändert; Entwurf erneut prüfen")
        try:
            draft = await runtime.guest_drafts.revise(booking_id, int(body["revision"]), body["changes"])
            return self.json(draft)
        except (ValueError, TypeError, KeyError) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except (RuntimeError, LookupError) as exc:
            raise web.HTTPConflict(text=str(exc)) from exc


class InvoiceDemoPreviewRequestView(HomeAssistantView):
    """Admin-only request to export a DEMO draft; NEVER issues or mails anything."""
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/preview-request"
    name = "api:smoobu_mittelhof:invoice_preview_request"
    requires_auth = True

    async def post(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        draft = await runtime.guest_drafts.get(booking_id)
        if not draft:
            raise web.HTTPConflict(text="Rechnungsentwurf fehlt")
        if (draft.get("source_change_pending") or
                draft["source_fingerprint"] != booking_fingerprint(booking)):
            await runtime.guest_drafts.prepare(booking)
            raise web.HTTPConflict(text="Buchungsstand wurde geändert; bitte erneut prüfen")
        apartment_id = int((booking.get("apartment") or {}).get("id") or 0)
        label = runtime.houses.get(apartment_id, "")
        if not planned_number(label, str(booking.get("arrival") or "")):
            raise web.HTTPConflict(text="Hausnummer 13/14/15 muss eindeutig zugeordnet sein")
        payload = await _parse_body(request)
        try:
            revision = int(payload["revision"])
            return self.json(
                await runtime.guest_drafts.request_demo_invoice_preview(booking_id, revision)
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except RuntimeError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc


class InvoiceDraftExportView(HomeAssistantView):
    """Read-only authenticated export for the SEPARATE PRIVATE invoice test engine.

    This endpoint cannot assign an invoice number or issue/send an invoice.
    """
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/invoice-export"
    name = "api:smoobu_mittelhof:invoice_export"
    requires_auth = True

    async def get(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        draft = await runtime.guest_drafts.get(booking_id)
        if draft is None:
            raise web.HTTPConflict(text="Bitte zuerst einen Rechnungsentwurf vorbereiten")
        if (draft.get("source_change_pending") or
                draft["source_fingerprint"] != booking_fingerprint(booking)):
            await runtime.guest_drafts.prepare(booking)
            raise web.HTTPConflict(text="Buchungsdaten seit Entwurf verändert")
        apartment = booking.get("apartment") or {}
        apartment_id = int(apartment.get("id") or 0)
        label = runtime.houses.get(apartment_id, "")
        proposal = planned_number(label, str(booking.get("arrival") or ""))
        if not proposal:
            raise web.HTTPConflict(
                text="Hausnummer 13/14/15 nicht eindeutig aus konfigurierter Unterkunft ableitbar"
            )
        review = draft.get("invoice_review") or {}
        if (review.get("state") != "requested" or review.get("requested_revision") != draft["revision"]:
            raise web.HTTPConflict(text="Bitte erst DEMO-Musterprüfung für aktuelle Revision anfordern")
        # Do not leak raw Smoobu records, access codes, messages or tokens.
        inv = draft["invoice"]
        allowed_fields = (
            "recipient_name", "recipient_street", "recipient_postal_code",
            "recipient_city", "recipient_country", "description", "total_gross",
            "paid_amount", "payment_flow", "payment_verified", "payment_note",
            "tax_note", "due_date", "line_items",
        )
        response = {
            "schema_version": "mittelhof.invoice-draft.v1",
            "booking_id": str(booking_id),
            "apartment_id": apartment_id,
            "house_number": house_from_label(label),
            "arrival": str(booking.get("arrival") or ""),
            "departure": str(booking.get("departure") or ""),
            "proposed_invoice_number": proposal,
            "source_fingerprint": draft["source_fingerprint"],
            "source_revision": draft["revision"],
            "source_changed": False,
            "preview_request": {"state": "requested", "revision": draft["revision"]},
            "invoice": {key: inv.get(key) for key in allowed_fields},
        }
        return self.json(response)


class GuestMessageActionView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/{action}"
    name = "api:smoobu_mittelhof:guest_message_action"
    requires_auth = True

    async def post(self, request: web.Request, booking_id: str, action: str):
        _require_admin(request)
        if action not in ("regenerate", "approve", "send"):
            raise web.HTTPNotFound()
        runtime = _get_runtime(request.app["hass"])
        if action == "send" and not runtime.guest_message_send_enabled:
            raise web.HTTPForbidden(text="Gastversand ist in den Integrationsoptionen deaktiviert")
        body = await _parse_body(request)
        try:
            revision = int(body["revision"])
        except (ValueError, TypeError, KeyError) as exc:
            raise web.HTTPBadRequest(text="revision erforderlich") from exc
        booking = await _checked_booking(runtime, booking_id)
        current = await runtime.guest_drafts.get(booking_id)
        if not current:
            raise web.HTTPConflict(text="Kein Entwurf")
        if current["source_fingerprint"] != booking_fingerprint(booking):
            await runtime.guest_drafts.prepare(booking)
            raise web.HTTPConflict(text="Buchung wurde geändert; Freigabe ungültig")
        try:
            if action == "regenerate":
                return self.json(await runtime.guest_drafts.regenerate_message(booking_id, revision))
            if action == "approve":
                return self.json(await runtime.guest_drafts.approve(booking_id, revision))
            claimed = await runtime.guest_drafts.claim_send(booking_id, revision)
        except (ValueError, RuntimeError, LookupError) as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        try:
            await runtime.api.send_message_to_guest(
                booking_id, claimed["message"]["subject"], claimed["message"]["body"]
            )
        except Exception as exc:
            # A timeout after server acceptance is possible. Do NOT automatically retry.
            await runtime.guest_drafts.mark_unknown(booking_id)
            raise web.HTTPBadGateway(text="Zustellung unklar; bitte in Smoobu prüfen, nicht erneut senden") from exc
        await runtime.guest_drafts.mark_sent(booking_id)
        return self.json(await runtime.guest_drafts.get(booking_id))


def register_guest_views(hass: HomeAssistant) -> None:
    for view in (GuestThreadsView(), GuestBookingView(), GuestDraftView(), InvoiceDemoPreviewRequestView(), InvoiceDraftExportView(), GuestMessageActionView()):
        hass.http.register_view(view)


async def sync_guest_drafts(runtime) -> None:
    """Prepare future/active bookings from existing HA polling; never send."""
    # Broader than the calendar horizon so a reservation 12+ months ahead is prepared.
    # Failure must not interrupt the already installed Smoobu/laundry/NUKI workflows.
    today = date.today()
    try:
        source = await runtime.api.get_reservations(
            today - timedelta(days=30), today + timedelta(days=730)
        )
    except Exception:
        source = runtime.coordinator.data or []
    bookings = valid_bookings(source, runtime.houses)
    for booking in bookings:
        if booking.get("is-blocked-booking"):
            continue
        try:
            await runtime.guest_drafts.prepare(booking)
        except (ValueError, KeyError, TypeError):
            # Incomplete Smoobu records should not break calendar/coordinator updates.
            continue
