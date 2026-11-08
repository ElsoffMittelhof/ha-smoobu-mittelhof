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
from .smoobu_sources import guest_invoice_address, source_price_lines

DRAFT_STORAGE_KEY = f"{DOMAIN}.guest_drafts"
DRAFT_STORAGE_VERSION = 1


class GuestInboxState:
    """Private HA read markers (not Smoobu's shared read state).

    Existing threads/bookings become a baseline on initial use, so a first
    install cannot flood the new inbox with years of old activity.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.guest_inbox_state")
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] = {}

    async def async_load(self) -> None:
        old = await self._store.async_load()
        self._state = old if isinstance(old, dict) else {}

    async def observe(self, threads: list[dict], drafts: list[dict], api) -> dict:
        async with self._lock:
            last_seen = self._state.setdefault("last_seen", {})
            pending = self._state.setdefault("pending_messages", {})
            seen_bookings = self._state.setdefault("seen_bookings", {})
            if not self._state.get("initialized"):
                for t in threads:
                    bid = str((t.get("booking") or {}).get("id") or "")
                    latest = str((t.get("latest_message") or {}).get("id") or "")
                    if bid.isdigit() and latest:
                        last_seen[bid] = latest
                for d in drafts:
                    bid = str(d.get("booking_id") or "")
                    if bid.isdigit():
                        seen_bookings[bid] = True
                self._state["initialized"] = True
                await self._store.async_save(self._state)
                return {"new_bookings": [], "new_messages": [], "initial_snapshot": True,
                        "message_scan_limit_reached": False}
            changed = []
            for t in threads:
                bid = str((t.get("booking") or {}).get("id") or "")
                latest = str((t.get("latest_message") or {}).get("id") or "")
                if bid.isdigit() and latest and latest != last_seen.get(bid) and latest != pending.get(bid):
                    changed.append((bid, latest))
            # Only changed threads trigger extra Smoobu traffic. If 30+ change,
            # do not mark the remainder as read; retry on next refresh.
            for bid, latest in changed[:30]:
                try:
                    messages = await api.get_booking_messages(bid)
                    match = next((m for m in messages if str(m.get("id")) == latest), None)
                except Exception:
                    continue
                if match is not None and str(match.get("type")) == "1":
                    pending[bid] = latest
                elif match is not None:
                    last_seen[bid] = latest
                    pending.pop(bid, None)
            new_ids = [d for d in drafts
                       if str(d.get("booking_id") or "").isdigit()
                       and str(d.get("booking_id") or "") not in seen_bookings]
            await self._store.async_save(self._state)
            visible = {str((t.get("booking") or {}).get("id") or "") for t in threads}
            return {
                "new_messages": [bid for bid in pending if bid in visible],
                "new_bookings": new_ids[:100],
                "initial_snapshot": False,
                "message_scan_limit_reached": len(changed) > 30,
            }

    async def mark_opened(self, booking_id: str, messages: list[dict]) -> None:
        ids = [int(m["id"]) for m in messages
               if str(m.get("id") or "").isdigit()]
        async with self._lock:
            self._state.setdefault("seen_bookings", {})[booking_id] = True
            if ids:
                self._state.setdefault("last_seen", {})[booking_id] = str(max(ids))
            self._state.setdefault("pending_messages", {}).pop(booking_id, None)
            await self._store.async_save(self._state)


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
                    "guest": (d.get("booking_context") or {}).get("guest"),
                    "house": (d.get("booking_context") or {}).get("house"),
                    "arrival": (d.get("booking_context") or {}).get("arrival"),
                    "departure": (d.get("booking_context") or {}).get("departure"),
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

    async def enrich_pristine(self, booking: dict) -> None:
        """Upgrade only untouched auto-generated drafts, preserving manual edits."""
        key = str(booking["id"])
        async with self._lock:
            current = self._drafts.get(key)
            if not current or current.get("revision") != 1:
                return
            if len(current.get("audit") or []) != 1 or current["audit"][0].get("event") != "prepared":
                return
            if current.get("source_fingerprint") != booking_fingerprint(booking):
                return
            fresh = make_draft(booking)
            if fresh["invoice"]["line_items"] == current["invoice"]["line_items"] and (
                    fresh["invoice"].get("recipient_country") == current["invoice"].get("recipient_country")):
                return
            # Preserve audit origin; all invoice fields were untouched until now.
            fresh["created_at"] = current["created_at"]
            fresh["revision"] = 2
            fresh["audit"] = list(current["audit"]) + [{"at": utc_now(), "event": "source_enriched"}]
            self._drafts[key] = fresh
            await self._save()

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
    runtime = next(iter(entries.values()))
    if not getattr(runtime, "guest_portal_enabled", False) or runtime.guest_drafts is None:
        raise web.HTTPServiceUnavailable(text="Gästeverwaltung in den Integrationsoptionen noch nicht aktiviert")
    return runtime


async def _billing_source(runtime, booking: dict) -> tuple[dict, list[dict], list[str]]:
    """Do not expose raw guest API response; fall back to known booking address."""
    guest = None
    guest_id = booking.get("guestId")
    if guest_id is not None and str(guest_id).isdigit() and int(guest_id) > 0:
        try:
            guest = await runtime.api.get_guest(int(guest_id))
        except Exception:
            pass  # Missing guest endpoint must not break the booking view.
    address = guest_invoice_address(booking, guest)
    rows, warnings = source_price_lines(booking)
    if booking.get("_price_elements_unavailable"):
        warnings.append("Smoobu-Einzelpositionen derzeit nicht abrufbar")
    if not address.get("recipient_country"):
        warnings.append("ISO-Ländercode konnte aus Smoobu nicht sicher zugeordnet werden")
    return address, rows, warnings

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
        threads = []
        total_pages = 1
        try:
            for page in range(1, 6):
                response = await runtime.api.get_message_threads(page_number=page, page_size=100)
                total_pages = max(1, int(response.get("page_count") or 1))
                if not isinstance(response.get("threads"), list):
                    raise ValueError("Ungültiger Smoobu-Gesprächsindex")
                threads.extend(t for t in response["threads"] if isinstance(t, dict)
                               and int((t.get("apartment") or {}).get("id") or 0) in runtime.houses)
                if page >= total_pages:
                    break
        except Exception as exc:
            raise web.HTTPBadGateway(text="Smoobu-Posteingang nicht erreichbar") from exc
        summaries = await runtime.guest_drafts.list_summaries()
        status = await runtime.guest_inbox.observe(threads, summaries, runtime.api)
        return self.json({
            "threads": threads, "page_count": total_pages,
            "truncated": total_pages > 5, "drafts": summaries,
            "message_send_enabled": runtime.guest_message_send_enabled,
            **status,
        })

class GuestBookingView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}"
    name = "api:smoobu_mittelhof:guest_booking"
    requires_auth = True

    async def get(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        addr, rows, warnings = await _billing_source(runtime, booking)
        enriched = dict(booking, _guest_invoice_address=addr)
        await runtime.guest_drafts.enrich_pristine(enriched)
        try:
            messages = await runtime.api.get_booking_messages(booking_id)
        except Exception as exc:
            raise web.HTTPBadGateway(text="Smoobu-Gespräch nicht erreichbar") from exc
        await runtime.guest_inbox.mark_opened(booking_id, messages)
        draft = await runtime.guest_drafts.get(booking_id)
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
            "messages": messages, "draft": draft,
            "source_lines": rows, "source_address": addr, "source_warnings": warnings,
            "invoice_preflight": invoice_preflight(draft["invoice"]) if draft else None,
            "proposed_invoice_number": planned_number(
                runtime.houses.get(int((booking.get("apartment") or {}).get("id") or 0), ""),
                str(booking.get("arrival") or ""),
            ),
            "source_changed": bool(draft and (draft.get("source_change_pending") or
                             draft["source_fingerprint"] != booking_fingerprint(booking))),
        })

class GuestDraftView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/draft"
    name = "api:smoobu_mittelhof:guest_draft"
    requires_auth = True

    async def post(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        address, _, _ = await _billing_source(runtime, booking)
        enriched = dict(booking, _guest_invoice_address=address)
        draft = await runtime.guest_drafts.prepare(enriched, acknowledge_source=True)
        await runtime.guest_drafts.enrich_pristine(enriched)
        return self.json(await runtime.guest_drafts.get(booking_id) or draft)

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
        if (review.get("state") != "requested" or
                review.get("requested_revision") != draft["revision"]):
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
