"""Validated booking accounting snapshots and minimal PDF rendering.

No invoices are issued, no guest messages sent, no payment status inferred.
Pure Python to keep the production integration free from PDF runtime dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
import re
import textwrap

from .guest_finance import booking_fingerprint, channel_name
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
    source_rows, warnings = source_price_lines(booking)
    # Smoobu numbers are EUR booking totals; never treat foreign currency amounts as EUR.
    if any(str(w).startswith("Nicht-EUR-Position") for w in warnings):
        raise ValueError("Fremdwährungs-Preisposition: kein automatischer EUR-Buchhaltungsbeleg")
    rows = []
    for row in source_rows:
        rows.append({
            "description": str(row.get("description") or "")[:160],
            "gross": str(money(row["gross"])),
            "position_type": str(row.get("position_type") or ""),
            "suggested_tax_rate": str(row.get("tax_rate") or ""),
            "quantity": row.get("quantity", 1),
        })
    if sum((money(r["gross"]) for r in rows), Decimal("0.00")) != total:
        warnings.append("Positionssumme stimmt nicht mit dem Buchungsbrutto überein")
    return {
        "booking_id": bid,
        "house": str(house)[:100],
        "guest": str(booking.get("guest-name") or "")[:160],
        "channel": channel_name(booking)[:120],
        "arrival": str(booking.get("arrival") or "")[:10],
        "departure": str(booking.get("departure") or "")[:10],
        "total_gross": str(total),
        "source_fingerprint": booking_fingerprint(booking),
        "rows": rows,
        "warnings": warnings,
    }


def approve_snapshot(prepared, rates):
    """Explicit rate selection per position, even when Smoobu suggests 7%.

    A nonempty warning is never silently dismissed: the admin confirms it.
    """
    rows = prepared["rows"]
    if not isinstance(rates, list) or len(rows) != len(rates):
        raise ValueError("Steuersatz für jede Position explizit auswählen")
    out = []
    totals = {}
    for row, rate in zip(rows, rates, strict=True):
        if type(rate) is not str or rate not in ALLOWED_RATES:
            raise ValueError("Unbekannter oder nicht freigegebener Steuersatz")
        gross = money(row["gross"])
        tax = (gross * Decimal(rate) / (Decimal("100") + Decimal(rate))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        totals[rate] = totals.get(rate, Decimal("0.00")) + tax
        out.append({
            "description": row["description"], "gross": str(gross),
            "tax_rate": rate, "vat_included": str(tax),
            "quantity": row["quantity"],
        })
    if sum((money(x["gross"]) for x in out), Decimal("0.00")) != money(prepared["total_gross"]):
        raise ValueError("Smoobu-Brutto und Positionen stimmen nicht überein")
    if not prepared["arrival"] or not prepared["departure"] or not prepared["house"]:
        raise ValueError("Haus oder Aufenthaltszeitraum fehlen")
    snapshot = {key: prepared[key] for key in (
        "booking_id", "house", "guest", "channel", "arrival", "departure",
        "total_gross", "source_fingerprint"
    )}
    snapshot["rows"] = out
    snapshot["tax_totals"] = {rate: str(value) for rate, value in sorted(totals.items())}
    snapshot["document_kind"] = "internal_booking_record"
    snapshot["schema"] = "mittelhof.accounting.v1"
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
        "Interner Buchungsnachweis - KEINE Rechnung / Zahlungsaufforderung",
        "",
        "Buchungsreferenz: " + snapshot["booking_id"],
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
