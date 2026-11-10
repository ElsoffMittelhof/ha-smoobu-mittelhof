"""Validated booking accounting snapshots and minimal PDF rendering.

No invoices are issued, no guest messages sent, no payment status inferred.
Pure Python to keep the production integration free from PDF runtime dependencies.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
import re
import textwrap

from .guest_finance import booking_fingerprint, channel_name, booking_due_date, source_booking_date
from .smoobu_sources import source_price_lines

ALLOWED_RATES = {"0", "7", "19"}


def money(value):
    try:
        amount = Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError) as exc:
        raise ValueError("Betrag ungültig") from exc
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Betrag nicht centgenau")
    return amount.quantize(Decimal("0.01"))


# In Smoobu provider settlement amounts are *not* guest charges.
# Match narrowly, do not silently remove an unknown price element.
SETTLEMENT_NAMES = {
    "commission": "platform_commission",
    "cancellation host fee": "cancellation_settlement",
    "cancelation host fee": "cancellation_settlement",
    "cancellation payout": "cancellation_settlement",
    "cancelation payout": "cancellation_settlement",
}
GUEST_PET_NAMES = {"pass_through_pet_fee", "passthroughpetfee", "pass through pet fee"}
GUEST_EXTRA_NAMES = {"additional guest fee", "additionalguestfee"}


def _source_kind(element):
    import unicodedata
    label = str(element.get("name") or element.get("type") or "").strip().casefold()
    label = "".join(c for c in unicodedata.normalize("NFKD", label)
                    if not unicodedata.combining(c))
    key = " ".join(label.replace("-", " ").replace("_", " ").split())
    role = SETTLEMENT_NAMES.get(key)
    if role:
        return role
    if key in GUEST_PET_NAMES or key.replace(" ", "") == "passthroughpetfee":
        return "dog"
    if key in GUEST_EXTRA_NAMES or key.replace(" ", "") == "additionalguestfee":
        return "extra_person"
    return None


def _default_document_kind(channel):
    value = channel.casefold()
    if "tomas" in value or "direkt" in value or "direct" in value:
        return "invoice"
    # Website bookings are ambiguous: bank transfer vs. card / PayPal.
    # Require a human choice; never assume that "homepage" means invoice.
    return "booking_record"


def _created_date(booking):
    """Smoobu documents 'created-at' as YYYY-MM-DD HH:MM.

    Use the ORIGINAL booking creation date, never today's export date,
    arrival date, or last-modified timestamp.
    """
    raw = booking.get("created-at")
    if not isinstance(raw, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", raw):
        return None
    value = raw[:10]
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _display_date(value):
    return date.fromisoformat(value).strftime("%d.%m.%Y")


def _require_booking_date(prepared):
    booked = prepared.get("booking_created_at")
    if not isinstance(booked, str):
        raise ValueError("Smoobu-Buchungsdatum 'created-at' fehlt; keine Belegdaten erfinden")
    try:
        date.fromisoformat(booked)
    except ValueError as exc:
        raise ValueError("Smoobu-Buchungsdatum ungültig; Belegfreigabe gesperrt") from exc
    return booked


def _format_booking_date_lines(snapshot):
    booked = snapshot["booking_created_at"]
    return [
        "Buchungsdatum: " + _display_date(booked),
        "Belegdatum: " + _display_date(snapshot["document_date"]),
        "Fälligkeitsdatum: " + _display_date(snapshot["due_date"]),
    ]


def prepare_booking(booking, house):
    if booking.get("is-blocked-booking") or booking.get("type") not in (
        "reservation", "modification of booking"
    ):
        raise ValueError("Keine aktive reguläre Reservierung")
    bid = str(booking.get("id") or "")
    if not re.fullmatch(r"[1-9][0-9]{0,17}", bid):
        raise ValueError("Buchungs-ID fehlt")
    total = money(booking.get("price"))
    if total <= 0:
        raise ValueError("Buchungsbrutto muss positiv sein")
    originals = booking.get("priceElements")
    if originals is not None and not isinstance(originals, list):
        raise ValueError("Smoobu-Preispositionen sind keine Liste")
    ignored, filtered = [], []
    for element in originals or []:
        if not isinstance(element, dict):
            continue
        # Child elements already included in parents are not additional revenue.
        if element.get("priceIncludedInId") is not None:
            continue
        kind = _source_kind(element)
        if kind in ("platform_commission", "cancellation_settlement"):
            ignored.append({
                "description": str(element.get("name") or element.get("type") or "")[:160],
                "gross": str(money(element.get("amount"))),
                "reason": kind,
            })
            continue
        filtered.append(element)
    source = dict(booking)
    source["priceElements"] = filtered
    source_rows, warnings = source_price_lines(source)
    if any(str(w).startswith("Nicht-EUR-Position") for w in warnings):
        raise ValueError("Fremdwährungs-Preisposition: kein EUR-Buchhaltungsbeleg")
    rows = []
    for idx, (row, element) in enumerate(zip(source_rows, filtered, strict=False)):
        overridden_kind = _source_kind(element)
        if overridden_kind in ("dog", "extra_person"):
            row = dict(row)
            row["position_type"] = overridden_kind
            row["tax_rate"] = "7"
            warnings = [w for w in warnings if
                        not (w.startswith("Unbekannte Leistungsart: ") and
                             str(element.get("name") or element.get("type") or "") in w)]
        rows.append({
            "source_index": idx,
            "description": str(row.get("description") or "")[:160],
            "gross": str(money(row["gross"])),
            "position_type": str(row.get("position_type") or ""),
            "suggested_tax_rate": str(row.get("tax_rate") or ""),
            "quantity": row.get("quantity", 1),
        })
    # No priceElements: source_price_lines provides a single unclassified gross fallback.
    if not filtered and not originals and source_rows:
        rows = [{
            "source_index": 0,
            "description": str(source_rows[0].get("description") or "")[:160],
            "gross": str(money(source_rows[0]["gross"])),
            "position_type": "", "suggested_tax_rate": "", "quantity": 1,
        }]
    if sum((money(r["gross"]) for r in rows), Decimal("0.00")) != total:
        warnings.append("Gastpreispositionen weichen vom Buchungsbrutto ab – vor Export korrigieren")
    channel = channel_name(booking)[:120]
    booked = source_booking_date(booking)
    due = booking_due_date(booking)
    if not due:
        warnings.append(
            "Zahlungsziel nicht ableitbar: Buchungskanal, ursprüngliches Buchungsdatum "
            "und An-/Abreisetage prüfen; Belegfreigabe gesperrt"
        )
    if not booked:
        warnings.append("Buchungsdatum (created-at) fehlt oder ist ungültig: Belegfreigabe gesperrt")
    return {
        "booking_id": bid,
        "document_number": bid,
        "accounting_type": "Einnahme",
        "service_date": str(booking.get("departure") or "")[:10],
        "booking_created_at": booked,
        "document_date": booked,
        "due_date": due,
        "house": str(house)[:100],
        "guest": str(booking.get("guest-name") or "")[:160],
        "channel": channel,
        "arrival": str(booking.get("arrival") or "")[:10],
        "departure": str(booking.get("departure") or "")[:10],
        "total_gross": str(total),
        "source_fingerprint": booking_fingerprint(booking),
        "rows": rows,
        "ignored_settlement_lines": ignored,
        "suggested_document_kind": _default_document_kind(channel),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _edited_rows(prepared, edits):
    originals = prepared["rows"]
    if edits is None:
        return [dict(row) for row in originals]
    if (not isinstance(edits, list) or not 1 <= len(edits) <= 50
            or len(edits) > len(originals)):
        raise ValueError("1 bis 50 ausgewählte Gastpositionen zulässig")
    used = set()
    result = []
    for edit in edits:
        if not isinstance(edit, dict) or type(edit.get("source_index")) is not int:
            raise ValueError("Belegposition ohne gültige Quellenreferenz")
        idx = edit["source_index"]
        if idx in used or idx < 0 or idx >= len(originals):
            raise ValueError("Doppelte oder unbekannte Gastpreisposition")
        used.add(idx)
        original = originals[idx]
        desc = str(edit.get("description") or "").strip()
        if not desc or len(desc) > 160 or any(ord(ch) < 32 for ch in desc):
            raise ValueError("Ungültiger Positionstext")
        gross = money(edit.get("gross"))
        if gross <= 0:
            raise ValueError("Gastposition muss einen positiven Bruttobetrag haben")
        result.append({**original, "description": desc, "gross": str(gross)})
    return result


def approve_snapshot(prepared, rates, edits=None):
    """An explicit, auditable operator-selected guest-price breakdown.

    Provider commission/cancellation settlements never become guest revenue.
    Deleted/edited rows are allowed only if the reviewed total still exactly
    equals the authoritative booking gross amount.
    """
    booked = _require_booking_date(prepared)
    try:
        date.fromisoformat(prepared["due_date"])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Zahlungsziel nach Mittelhof-Kanalregel fehlt oder ist ungültig") from exc
    rows = _edited_rows(prepared, edits)
    if not isinstance(rates, list) or len(rows) != len(rates):
        raise ValueError("Steuersatz für jede gewählte Position ausdrücklich bestätigen")
    out, totals = [], {}
    for row, rate in zip(rows, rates, strict=True):
        if type(rate) is not str or rate not in ALLOWED_RATES:
            raise ValueError("Steuersatz nicht freigegeben")
        gross = money(row["gross"])
        tax = (gross * Decimal(rate) / (Decimal("100") + Decimal(rate))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        totals[rate] = totals.get(rate, Decimal("0.00")) + tax
        out.append({
            "source_index": row["source_index"],
            "description": row["description"], "gross": str(gross),
            "tax_rate": rate, "vat_included": str(tax),
            "quantity": row["quantity"],
        })
    if sum((money(x["gross"]) for x in out), Decimal("0.00")) != money(prepared["total_gross"]):
        raise ValueError("Freigegebene Gastpositionen müssen exakt dem Smoobu-Buchungsbrutto entsprechen")
    if not prepared["arrival"] or not prepared["departure"] or not prepared["house"]:
        raise ValueError("Haus oder Aufenthaltszeitraum fehlen")
    try:
        arrival = date.fromisoformat(prepared["arrival"])
        checkout = date.fromisoformat(prepared["service_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Checkoutdatum fehlt oder ist ungültig; Leistungsdatum kann nicht gebildet werden") from exc
    if checkout <= arrival:
        raise ValueError("Checkoutdatum darf nicht vor oder am Anreisetag liegen")
    if prepared["document_number"] != prepared["booking_id"]:
        raise ValueError("Belegnummer stimmt nicht mit der Buchungs-ID überein")
    if prepared.get("accounting_type") != "Einnahme":
        raise ValueError("Interner Buchhaltungsbeleg muss als Einnahme gekennzeichnet sein")
    snapshot = {key: prepared[key] for key in (
        "booking_id", "document_number", "accounting_type", "service_date",
        "booking_created_at", "document_date", "due_date",
        "house", "guest", "channel", "arrival", "departure",
        "total_gross", "source_fingerprint"
    )}
    snapshot["rows"] = out
    snapshot["tax_totals"] = {rate: str(value) for rate, value in sorted(totals.items())}
    snapshot["source_excluded"] = [
        {"source_index": r["source_index"], "description": r["description"],
         "gross": r["gross"]} for r in prepared["rows"]
        if r["source_index"] not in {x["source_index"] for x in out}
    ]
    snapshot["source_changes"] = [
        {"source_index": r["source_index"], "original_description": orig["description"],
         "original_gross": orig["gross"]}
        for r in out for orig in prepared["rows"]
        if orig["source_index"] == r["source_index"] and
        (r["description"] != orig["description"] or r["gross"] != orig["gross"])
    ]
    snapshot["ignored_settlement_lines"] = prepared.get("ignored_settlement_lines", [])
    snapshot["document_kind"] = "internal_booking_record"
    snapshot["schema"] = "mittelhof.accounting.v5"
    digest = sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")).hexdigest()
    snapshot["sha256"] = digest
    return snapshot


def _pdf_escape(value):
    data = str(value).encode("cp1252", errors="replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def render_pdf(snapshot):
    """Single or multi-page valid PDF 1.4 with WinAnsi Helvetica.

    This is an internal booking document, deliberately not a tax invoice.
    """
    lines = [
        "MITTELHOF - BUCHHALTUNGSBELEG",
        "Belegtyp: " + snapshot["accounting_type"],
        "Interner Buchungsnachweis - KEINE Rechnung / Zahlungsaufforderung",
        "",
        "Buchungsreferenz: " + snapshot["booking_id"],
        "Belegnummer: " + snapshot["document_number"],
        *_format_booking_date_lines(snapshot),
        "Leistungsdatum: " + _display_date(snapshot["service_date"]),
        "Unterkunft: " + snapshot["house"],
        "Gast: " + (snapshot["guest"] or "Nicht verfügbar"),
        "Buchungskanal: " + (snapshot["channel"] or "Unbekannt"),
        "Aufenthalt: " + snapshot["arrival"] + " bis " + snapshot["departure"],
        "",
        "Preispositionen (Beträge in EUR, inkl. ausgewiesener USt):",
    ]
    for row in snapshot["rows"]:
        value = "%s EUR | %s %% USt | USt %s EUR" % (
            row["gross"], row["tax_rate"], row["vat_included"]
        )
        title = str(row["description"]).replace("\n", " ").replace("\r", " ")
        for part in textwrap.wrap(title, width=82, break_long_words=True) or [""]:
            lines.append(part)
        lines.append("  " + value)
    lines.extend(["", "GASTBRUTTO: " + snapshot["total_gross"] + " EUR", ""])
    for rate, total in snapshot["tax_totals"].items():
        lines.append("Darin enthaltene USt " + rate + " %: " + total + " EUR")
    lines.extend([
        "", "Zahlung nicht geprüft. Plattformprovision separat verbuchen.",
        "Dieser Beleg dokumentiert Smoobu-Buchungsdaten; kein Zahlungsnachweis.",
        "Portal-Originalbelege und Abrechnungen separat aufbewahren.",
        "Quelle: Smoobu | Hash: " + snapshot["sha256"],
    ])
    pages = [lines[i:i+44] for i in range(0, len(lines), 44)]
    objects = [b""]
    def obj(payload):
        objects.append(payload)
        return len(objects)-1
    catalog = obj(b"")
    pages_id = obj(b"")
    font_id = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for page_no, page in enumerate(pages, 1):
        stream_lines = [b"BT /F1 10 Tf 46 795 Td 13 TL"]
        for line in page:
            stream_lines.append(b"(" + _pdf_escape(line) + b") Tj T*")
        stream_lines.append(b"ET")
        stream = b"\n".join(stream_lines) + b"\n"
        stream_id = obj(b"<< /Length " + str(len(stream)).encode() +
                        b" >>\nstream\n" + stream + b"endstream")
        page_id = obj(b"<< /Type /Page /Parent " + str(pages_id).encode() +
                      b" 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 " +
                      str(font_id).encode() + b" 0 R >> >> /Contents " +
                      str(stream_id).encode() + b" 0 R >>")
        page_ids.append(page_id)
    objects[catalog] = b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>"
    objects[pages_id] = (b"<< /Type /Pages /Count " + str(len(page_ids)).encode() +
                        b" /Kids [" + b" ".join(str(x).encode() + b" 0 R" for x in page_ids) +
                        b"] >>")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects[1:], 1):
        offsets.append(len(output))
        output.extend(str(index).encode() + b" 0 obj\n" + payload + b"\nendobj\n")
    start = len(output)
    output.extend(b"xref\n0 " + str(len(objects)).encode() + b"\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(("%010d 00000 n \n" % offset).encode())
    output.extend(b"trailer\n<< /Size " + str(len(objects)).encode() +
                  b" /Root " + str(catalog).encode() + b" 0 R >>\nstartxref\n" +
                  str(start).encode() + b"\n%%EOF\n")
    return bytes(output)
