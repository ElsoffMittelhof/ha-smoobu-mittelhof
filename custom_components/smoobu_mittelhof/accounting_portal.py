"""Admin-only accounting export for Lexware Office L (manual PDF import).

No Lexware writes and no invoice issuance. Smoobu payments are never trusted.
"""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.storage import Store

from .accounting_core import approve_snapshot, prepare_booking, render_pdf
from .const import DOMAIN
from .guest_portal import _get_runtime, _require_admin, _checked_booking, _parse_body

KEY = f"{DOMAIN}.accounting_records"
STORE_VERSION = 1


class AccountingRepository:
    def __init__(self, hass):
        self._store = Store(hass, STORE_VERSION, KEY)
        self._lock = asyncio.Lock()
        self._records = {}

    async def async_load(self):
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            self._records = data["records"]

    async def get(self, bid):
        async with self._lock:
            return deepcopy(self._records.get(str(bid)))

    async def list(self):
        async with self._lock:
            return [
                {"booking_id": bid, "status": value.get("status"),
                 "source_fingerprint": value.get("source_fingerprint"),
                 "sha256": value.get("sha256"),
                 "reviewed_at": value.get("reviewed_at"),
                 "uploaded_at": value.get("uploaded_at"),
                 "document_kind": value.get("document_kind", "booking_record"),
                 "invoice_reference": value.get("invoice_reference") }
                for bid, value in self._records.items()
            ]

    async def approve(self, prepared, rates, edits=None):
        snapshot = approve_snapshot(prepared, rates, edits)
        bid = prepared["booking_id"]
        async with self._lock:
            previous = self._records.get(bid)
            if previous and previous.get("status") in ("uploaded_manually", "invoice_reference"):
                if previous.get("sha256") != snapshot["sha256"]:
                    raise ValueError("Bereits als hochgeladen oder Rechnung referenziert: manuellen Korrekturprozess verwenden")
                return deepcopy(previous)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            record = {
                "status": "ready", "source_fingerprint": snapshot["source_fingerprint"],
                "sha256": snapshot["sha256"], "reviewed_at": now, "uploaded_at": None,
                "snapshot": snapshot, "document_kind": "booking_record",
            }
            # Never overwrite a reviewed export with an unreviewed Smoobu update.
            self._records[bid] = record
            await self._store.async_save({"records": self._records})
            return deepcopy(record)

    async def confirm_uploaded(self, bid, expected_sha):
        async with self._lock:
            record = self._records.get(bid)
            if not record or record.get("sha256") != expected_sha:
                raise ValueError("Keine passende, geprüfte Belegrevision vorhanden")
            if record["status"] == "uploaded_manually":
                return deepcopy(record)
            if record["status"] != "ready":
                raise ValueError("Beleg nicht exportbereit")
            record["status"] = "uploaded_manually"
            record["uploaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            await self._store.async_save({"records": self._records})
            return deepcopy(record)


    async def set_invoice_reference(self, prepared, reference):
        """Record an EXISTING outside-issued invoice; never create one here."""
        bid = prepared["booking_id"]
        if (not isinstance(reference, str) or not reference.strip()
                or len(reference.strip()) > 120
                or any(ord(ch) < 32 for ch in reference)):
            raise ValueError("Gültige externe Rechnungsreferenz erforderlich")
        async with self._lock:
            old = self._records.get(bid)
            if old and old.get("status") == "uploaded_manually":
                raise ValueError("Buchungsbeleg bereits in Lexware erfasst: Dublette zuerst manuell klären")
            if old and old.get("status") == "invoice_reference":
                if (old.get("invoice_reference") == reference.strip() and
                        old.get("source_fingerprint") == prepared["source_fingerprint"]):
                    return deepcopy(old)
                raise ValueError("Bestehende Rechnungsreferenz darf nicht überschrieben werden")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            record = {
                "status": "invoice_reference",
                "document_kind": "invoice",
                "invoice_reference": reference.strip(),
                "source_fingerprint": prepared["source_fingerprint"],
                "sha256": None, "snapshot": None,
                "reviewed_at": now, "uploaded_at": None,
            }
            self._records[bid] = record
            await self._store.async_save({"records": self._records})
            return deepcopy(record)


def _accounting_runtime(request):
    _require_admin(request)
    runtime = _get_runtime(request.app["hass"])
    if runtime.accounting is None:
        raise web.HTTPServiceUnavailable(text="Buchhaltungsdaten noch nicht initialisiert")
    return runtime


async def _current_source(runtime, booking_id):
    # _checked_booking already loads the full Smoobu detail (including the
    # price-elements fallback) and verifies the configured apartment.
    # A second network fetch could return inconsistent/partial data and was
    # redundant for both the GET preview and the POST approval operation.
    booking = await _checked_booking(runtime, booking_id)
    try:
        apt_id = int((booking.get("apartment") or {}).get("id") or 0)
        prepared = prepare_booking(booking, runtime.houses[apt_id])
    except (KeyError, ValueError, TypeError) as exc:
        raise web.HTTPConflict(
            text="Buchung kann nicht für die Buchhaltung geprüft werden: " + str(exc)
        ) from exc
    return prepared


class AccountingListView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/accounting"
    name = "api:smoobu_mittelhof:accounting_list"
    requires_auth = True

    async def get(self, request):
        runtime = _accounting_runtime(request)
        return self.json({"records": await runtime.accounting.list(),
                          "lexware_api_enabled": False, "payment_status_verified": False})


class AccountingBookingView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting"
    name = "api:smoobu_mittelhof:accounting_booking"
    requires_auth = True

    async def get(self, request, booking_id):
        runtime = _accounting_runtime(request)
        prepared = await _current_source(runtime, booking_id)
        record = await runtime.accounting.get(booking_id)
        changed = bool(record and record["source_fingerprint"] != prepared["source_fingerprint"])
        public_record = ({k: v for k, v in record.items() if k != "snapshot"}
                         if record else None)
        date_revision_required = bool(
            record and record.get("document_kind") == "booking_record"
            and (not isinstance(record.get("snapshot"), dict)
                 or record["snapshot"].get("schema") != "mittelhof.accounting.v4"
                 or record["snapshot"].get("document_date") != prepared["document_date"]
                 or record["snapshot"].get("document_number") != prepared["document_number"]
                 or record["snapshot"].get("accounting_type") != prepared["accounting_type"]
                 or record["snapshot"].get("service_date") != prepared["service_date"])
        )
        if public_record is not None and isinstance(record.get("snapshot"), dict):
            public_record["reviewed_rows"] = record["snapshot"].get("rows", [])
        return self.json({
            "source": prepared,
            "record": public_record,
            "source_changed": changed,
            "date_revision_required": date_revision_required,
        })

    async def post(self, request, booking_id):
        runtime = _accounting_runtime(request)
        body = await _parse_body(request)
        prepared = await _current_source(runtime, booking_id)
        if body.get("source_fingerprint") != prepared["source_fingerprint"]:
            raise web.HTTPConflict(text="Smoobu-Buchung hat sich seit der Prüfung geändert")
        if body.get("confirm_warnings") is not True and prepared["warnings"]:
            raise web.HTTPConflict(text="Alle Quellenwarnungen vor Freigabe ausdrücklich bestätigen")
        if body.get("confirm_tax_review") is not True:
            raise web.HTTPConflict(text="Steuerpositionen müssen explizit geprüft werden")
        try:
            if body.get("document_kind", "booking_record") != "booking_record":
                raise ValueError("Gastrechnungen werden nicht über PDF-Buchungsbelege ausgestellt")
            record = await runtime.accounting.approve(prepared, body.get("rates"), body.get("edits"))
        except ValueError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        return self.json({k: v for k, v in record.items() if k != "snapshot"})


class AccountingInvoiceReferenceView(HomeAssistantView):
    """Admin confirms an existing issued invoice number, NOT issuing it."""
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting/invoice-reference"
    name = "api:smoobu_mittelhof:accounting_invoice_reference"
    requires_auth = True

    async def post(self, request, booking_id):
        runtime = _accounting_runtime(request)
        body = await _parse_body(request)
        source = await _current_source(runtime, booking_id)
        if source["source_fingerprint"] != body.get("source_fingerprint"):
            raise web.HTTPConflict(text="Quellbuchung wurde geändert")
        if body.get("confirm_existing_invoice") is not True:
            raise web.HTTPConflict(text="Bereits ausgestellte Gastrechnung ausdrücklich bestätigen")
        try:
            record = await runtime.accounting.set_invoice_reference(
                source, body.get("invoice_reference"))
        except ValueError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        return self.json({k: v for k, v in record.items() if k != "snapshot"})


class AccountingPdfView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting/pdf"
    name = "api:smoobu_mittelhof:accounting_pdf"
    requires_auth = True

    async def get(self, request, booking_id):
        runtime = _accounting_runtime(request)
        prepared = await _current_source(runtime, booking_id)
        record = await runtime.accounting.get(booking_id)
        if not record or record["source_fingerprint"] != prepared["source_fingerprint"]:
            raise web.HTTPConflict(text="Beleg nicht geprüft oder Smoobu-Buchung geändert")
        if record["status"] not in ("ready", "uploaded_manually"):
            raise web.HTTPConflict(text="Beleg nicht freigegeben")
        snapshot = record.get("snapshot")
        if not isinstance(snapshot, dict) or record.get("sha256") != snapshot.get("sha256"):
            raise web.HTTPConflict(text="Belegintegrität nicht verifizierbar")
        if (snapshot.get("schema") != "mittelhof.accounting.v4"
                or snapshot.get("document_date") != prepared["document_date"]
                or snapshot.get("document_number") != prepared["document_number"]
                or snapshot.get("accounting_type") != prepared["accounting_type"]
                or snapshot.get("service_date") != prepared["service_date"]):
            raise web.HTTPConflict(
                text="Ältere Belegrevision ohne geprüfte Lexware-Belegnummer oder Leistungsdatum; "
                     "bitte Beleg erneut prüfen. Bereits verbuchte Belege nicht überschreiben."
            )
        payload = await request.app["hass"].async_add_executor_job(render_pdf, snapshot)
        return self.json({
            "filename": "mittelhof-buchhaltungsbeleg-" + booking_id + "-" +
                        snapshot["sha256"][:12] + ".pdf",
            "pdf_base64": base64.b64encode(payload).decode("ascii"),
            "sha256": sha256(payload).hexdigest(),
            "document_hash": record["sha256"],
            "status": record["status"],
        })


class AccountingUploadView(HomeAssistantView):
    url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting/uploaded"
    name = "api:smoobu_mittelhof:accounting_uploaded"
    requires_auth = True

    async def post(self, request, booking_id):
        runtime = _accounting_runtime(request)
        body = await _parse_body(request)
        prepared = await _current_source(runtime, booking_id)
        record = await runtime.accounting.get(booking_id)
        if not record or record["source_fingerprint"] != prepared["source_fingerprint"]:
            raise web.HTTPConflict(text="Beleg wurde nach Freigabe verändert")
        snapshot = record.get("snapshot")
        if (not isinstance(snapshot, dict) or snapshot.get("schema") != "mittelhof.accounting.v4"
                or snapshot.get("document_date") != prepared["document_date"]):
            raise web.HTTPConflict(text="Lexware-Belegnummer/Leistungsdatum fehlt oder ist veraltet; erneute Prüfung nötig")
        if body.get("confirm_manual_upload") is not True:
            raise web.HTTPConflict(text="Manuellen Upload erst nach erfolgter Lexware-Erfassung bestätigen")
        try:
            result = await runtime.accounting.confirm_uploaded(booking_id, body.get("sha256"))
        except ValueError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        return self.json({k: v for k, v in result.items() if k != "snapshot"})



class AccountingBundleView(HomeAssistantView):
    """Create a bounded ZIP of already reviewed PDFs and a CSV manifest.

    Does not mark any record as imported into Lexware.
    """
    url = "/api/smoobu_mittelhof/guest/v1/accounting/bundle"
    name = "api:smoobu_mittelhof:accounting_bundle"
    requires_auth = True

    async def post(self, request):
        from io import BytesIO, StringIO
        import csv
        from zipfile import ZipFile, ZIP_DEFLATED
        runtime = _accounting_runtime(request)
        body = await _parse_body(request)
        ids = body.get("booking_ids")
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 25 or
                any(not isinstance(bid, str) or not bid.isdigit() for bid in ids) or
                len(set(ids)) != len(ids)):
            raise web.HTTPBadRequest(text="1 bis 25 unterschiedliche Buchungs-IDs erwartet")
        items = []
        for bid in ids:
            source = await _current_source(runtime, bid)
            record = await runtime.accounting.get(bid)
            if not record or record["status"] not in ("ready", "uploaded_manually"):
                raise web.HTTPConflict(text="Nicht freigegebener Buchhaltungsbeleg: " + bid)
            if record["source_fingerprint"] != source["source_fingerprint"]:
                raise web.HTTPConflict(text="Smoobu-Buchung zwischenzeitlich geändert: " + bid)
            snapshot = record.get("snapshot")
            if not isinstance(snapshot, dict) or snapshot.get("sha256") != record.get("sha256"):
                raise web.HTTPConflict(text="Belegintegrität ungültig: " + bid)
            if (snapshot.get("schema") != "mittelhof.accounting.v4"
                    or snapshot.get("document_date") != source["document_date"]
                    or snapshot.get("document_number") != source["document_number"]
                    or snapshot.get("accounting_type") != source["accounting_type"]
                    or snapshot.get("service_date") != source["service_date"]):
                raise web.HTTPConflict(text="Belegnummer/Leistungsdatum noch nicht geprüft: " + bid)
            items.append((bid, snapshot))
        def bundle():
            memory = BytesIO()
            manifest = StringIO()
            writer = csv.writer(manifest)
            writer.writerow(["booking_id", "source_sha256", "pdf_sha256", "gross_eur", "channel"])
            with ZipFile(memory, "w", compression=ZIP_DEFLATED) as archive:
                for bid, snapshot in items:
                    pdf = render_pdf(snapshot)
                    name = "mittelhof-buchhaltungsbeleg-" + bid + "-" + snapshot["sha256"][:12] + ".pdf"
                    archive.writestr(name, pdf)
                    writer.writerow([bid, snapshot["sha256"], sha256(pdf).hexdigest(),
                                     snapshot["total_gross"], snapshot["channel"]])
                archive.writestr("manifest.csv", manifest.getvalue().encode("utf-8-sig"))
            return memory.getvalue()
        payload = await request.app["hass"].async_add_executor_job(bundle)
        if len(payload) > 10_000_000:
            raise web.HTTPRequestEntityTooLarge(max_size=10_000_000, actual_size=len(payload))
        return self.json({
            "filename": "mittelhof-lexware-belege.zip",
            "zip_base64": base64.b64encode(payload).decode("ascii"),
            "sha256": sha256(payload).hexdigest(), "count": len(items),
        })


def register_accounting_views(hass):
    for view in (AccountingListView(), AccountingBookingView(),
                 AccountingPdfView(), AccountingUploadView(), AccountingBundleView(),
                 AccountingInvoiceReferenceView()):
        hass.http.register_view(view)
