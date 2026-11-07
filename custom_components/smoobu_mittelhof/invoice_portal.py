"""Admin-only proxy to the PRIVATE Mittelhof ZUGFeRD DEMO preview service.

No PDF library or private logo is distributed via HACS. No final issue, email
attachment or invoice correction is possible from this API.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .guest_finance import booking_fingerprint
from .guest_portal import (
    _checked_booking, _get_runtime, _parse_body, _require_admin,
)
from .invoice_numbers import planned_number, house_from_label

SERVICE_FILE = "invoice_service.json"
EXPORT_FIELDS = (
    "recipient_name", "recipient_street", "recipient_postal_code",
    "recipient_city", "recipient_country", "description", "total_gross",
    "paid_amount", "payment_flow", "payment_verified", "payment_note",
    "tax_note", "due_date", "line_items",
)
ALLOWED_ACTIONS = {"build", "verify", "approve", "archive"}
MAX_PDF_BYTES = 5_000_000
MAX_RESPONSE_BYTES = 100_000


def _read_invoice_service_config(config_dir: Path) -> dict | None:
    filename = config_dir / SERVICE_FILE
    if not filename.exists():
        return None
    if filename.is_symlink() or not filename.is_file() or filename.stat().st_size > 4096:
        raise ValueError("Privater Rechnungsdienst-Konfigurationspfad ungültig")
    # Reject secrets readable by other OS users on POSIX HA deployments.
    if os.name == "posix" and filename.stat().st_mode & 0o077:
        raise ValueError("Rechnungsdienst-Konfiguration nur für Dateibesitzer lesbar (chmod 600)")
    obj = json.loads(filename.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("enabled") is not True:
        return None
    url = str(obj.get("url") or "").rstrip("/")
    token = str(obj.get("token") or "")
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path or parsed.scheme not in ("http", "https")):
        raise ValueError("Ungültige Rechnungsdienst-URL")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Rechnungsdienst nur HTTPS oder HTTP-Loopback erlaubt")
    if not 32 <= len(token) <= 256:
        raise ValueError("Rechnungsdienst benötigt ein mindestens 32-stelliges Token")
    return {"url": url, "token": token}


def _export_payload(booking_id: str, booking: dict, draft: dict, runtime) -> dict:
    """Recompute a safe copy; never send Smoobu tokens/messages/NUKI data."""
    if not draft or draft.get("source_change_pending"):
        raise ValueError("Buchungsstand oder Rechnungsentwurf ist veraltet")
    if draft.get("source_fingerprint") != booking_fingerprint(booking):
        raise ValueError("Smoobu-Buchung wurde zwischenzeitlich verändert")
    review = draft.get("invoice_review") or {}
    if (review.get("state") != "requested" or
            review.get("requested_revision") != draft.get("revision")):
        raise ValueError("Musterprüfung für aktuelle Entwurfsrevision zuerst anfordern")
    apartment = booking.get("apartment") or {}
    apartment_id = int(apartment.get("id") or 0)
    label = runtime.houses.get(apartment_id, "")
    proposed = planned_number(label, str(booking.get("arrival") or ""))
    if not proposed:
        raise ValueError("Hausnummer 13/14/15 ist nicht eindeutig")
    inv = draft["invoice"]
    return {
        "schema_version": "mittelhof.invoice-draft.v1",
        "booking_id": booking_id,
        "apartment_id": apartment_id,
        "house_number": house_from_label(label),
        "arrival": str(booking.get("arrival") or ""),
        "departure": str(booking.get("departure") or ""),
        "proposed_invoice_number": proposed,
        "source_fingerprint": draft["source_fingerprint"],
        "source_revision": draft["revision"],
        "source_changed": False,
        "preview_request": {"state": "requested", "revision": draft["revision"]},
        "invoice": {key: inv.get(key) for key in EXPORT_FIELDS},
    }


async def _service_request(hass, service: dict, method: str, path: str, data=None,
                           *, wants_pdf: bool = False):
    url = service["url"] + path
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=150 if path.endswith("/verify") else 45)
    try:
        async with session.request(
            method, url,
            headers={"Authorization": "Bearer " + service["token"],
                     "Accept": "application/pdf" if wants_pdf else "application/json"},
            json=data if method == "POST" else None,
            timeout=timeout,
            allow_redirects=False,
        ) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                raise web.HTTPBadGateway(
                    text="Privater Musterrechnungsdienst hat die Aktion abgelehnt"
                )
            limit = MAX_PDF_BYTES if wants_pdf else MAX_RESPONSE_BYTES
            raw = await response.content.read(limit + 1)
            if len(raw) > limit:
                raise web.HTTPBadGateway(text="Musterrechnungsantwort über Limit")
            if wants_pdf:
                if not raw.startswith(b"%PDF-"):
                    raise web.HTTPBadGateway(text="Kein gültiger PDF-Dateikopf")
                return raw
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise web.HTTPBadGateway(text="Ungültige Antwort des Rechnungsdienstes")
            return result
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise web.HTTPBadGateway(
            text="Privater Musterrechnungsdienst ist nicht erreichbar oder ungültig"
        ) from exc


def _check_service_binding(data: dict, booking_id: str, draft: dict, proposal: str) -> None:
    if (data.get("planned_invoice_number") != proposal or
            data.get("source_revision") != draft["revision"] or
            data.get("booking_id_sha256") != sha256(booking_id.encode("ascii")).hexdigest()):
        raise web.HTTPConflict(text="Musterbeleg gehört nicht zur aktuellen Buchungsrevision")
    if data.get("invoice_issued") is not False or data.get("real_invoice_enabled") is not False:
        raise web.HTTPConflict(text="Unbekannter Rechnungsdienst-Zustand")


class InvoiceServiceView(HomeAssistantView):
    """Server-side HA-authenticated, bearer-proxy for local DEMO invoice service."""
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/invoice-service/{action}"
    name = "api:smoobu_mittelhof:invoice_service"
    requires_auth = True

    async def _context(self, request: web.Request, booking_id: str):
        _require_admin(request)
        runtime = _get_runtime(request.app["hass"])
        booking = await _checked_booking(runtime, booking_id)
        draft = await runtime.guest_drafts.get(booking_id)
        if not draft:
            raise web.HTTPConflict(text="Kein Rechnungsentwurf für diese Buchung")
        try:
            export = _export_payload(booking_id, booking, draft, runtime)
        except ValueError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        try:
            cfg = await request.app["hass"].async_add_executor_job(
                _read_invoice_service_config, runtime.config_directory
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise web.HTTPServiceUnavailable(text="Rechnungsdienst-Konfiguration ungültig") from exc
        return runtime, draft, export, cfg

    async def get(self, request: web.Request, booking_id: str, action: str):
        if action not in ("status", "pdf"):
            raise web.HTTPNotFound()
        _, draft, export, cfg = await self._context(request, booking_id)
        if cfg is None:
            return self.json({"configured": False, "preview_created": False})
        num = export["proposed_invoice_number"]
        uri = "/v1/previews/" + num
        if action == "status":
            state = await _service_request(request.app["hass"], cfg, "GET", uri)
            if state is None:
                return self.json({"configured": True, "preview_created": False})
            _check_service_binding(state, booking_id, draft, num)
            return self.json({"configured": True, "preview_created": True, **state})
        state = await _service_request(request.app["hass"], cfg, "GET", uri)
        if state is None:
            raise web.HTTPNotFound(text="Musterrechnung wurde noch nicht erstellt")
        _check_service_binding(state, booking_id, draft, num)
        pdf = await _service_request(
            request.app["hass"], cfg, "GET", uri + "/pdf?revision=" + str(draft["revision"]),
            wants_pdf=True
        )
        if pdf is None:
            raise web.HTTPNotFound(text="Muster-PDF fehlt")
        return self.json({
            "filename": "DEMO-" + num + ".pdf",
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "test_only": True,
            "invoice_issued": False,
        })

    async def post(self, request: web.Request, booking_id: str, action: str):
        if action not in ALLOWED_ACTIONS:
            raise web.HTTPNotFound()
        runtime, draft, export, cfg = await self._context(request, booking_id)
        if cfg is None:
            raise web.HTTPServiceUnavailable(text="Privater Musterrechnungsdienst nicht konfiguriert")
        body = await _parse_body(request)
        if type(body.get("revision")) is not int or body["revision"] != draft["revision"]:
            raise web.HTTPConflict(text="Veraltete Entwurfsrevision")
        num = export["proposed_invoice_number"]
        if action == "build":
            state = await _service_request(request.app["hass"], cfg, "POST",
                                           "/v1/previews", export)
        else:
            uri = "/v1/previews/" + num + "/" + action
            payload = {"revision": draft["revision"]}
            if action == "approve":
                user = request.get("hass_user")
                payload["reviewer"] = str(user.name or user.id)
                payload["confirmation"] = str(body.get("confirmation") or "")
            state = await _service_request(request.app["hass"], cfg, "POST", uri, payload)
        if state is None:
            raise web.HTTPBadGateway(text="Privater Musterrechnungsdienst lieferte keine Antwort")
        _check_service_binding(state, booking_id, draft, num)
        return self.json({"configured": True, "preview_created": True, **state})


def register_invoice_service_view(hass):
    hass.http.register_view(InvoiceServiceView())
