"""Conservative draft preparation for guest communication and future ZUGFeRD invoices.

No invoice is issued here. No channel is assumed to have collected payment.
All money is stored as decimal strings to avoid float rounding.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

FINGERPRINT_FIELDS = (
    "id", "arrival", "departure", "channel", "guest-name", "email",
    "price", "price-paid", "prepayment", "prepayment-paid", "deposit",
    "modifiedAt", "price-details", "city-tax", "commission-included",
    "deposit-paid", "type", "is-blocked-booking",
)
PAYMENT_FLOWS = {"unverified", "platform", "guest_invoice", "already_paid"}
INVOICE_EDITABLE = {
    "recipient_name", "recipient_address", "description", "total_gross",
    "paid_amount", "due_date", "payment_flow", "payment_note", "tax_note",
    "line_items", "payment_verified",
}
MESSAGE_EDITABLE = {"subject", "body"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decimal_money(value: Any) -> str:
    """Return normalized 2-decimal string; reject invalid/negative input."""
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as err:
        raise ValueError("Ungültiger Geldbetrag") from err
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Betrag muss positiv und auf Cent genau sein")
    return str(amount.quantize(Decimal("0.01")))


def signed_line_money(value: Any) -> str:
    """Price elements can contain negative discounts; never round silently."""
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as err:
        raise ValueError("Ungültiger Positionsbetrag") from err
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Positionsbetrag muss auf Cent genau sein")
    return str(amount.quantize(Decimal("0.01")))


def channel_name(booking: dict[str, Any]) -> str:
    channel = booking.get("channel")
    return str(channel.get("name") or "") if isinstance(channel, dict) else str(channel or "")


def booking_fingerprint(booking: dict[str, Any]) -> str:
    """Hash only billing-relevant source fields, not volatile API metadata."""
    values = {field: booking.get(field) for field in FINGERPRINT_FIELDS}
    values["channel"] = channel_name(booking)
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_channel(channel: str) -> str:
    lowered = channel.casefold()
    if "airbnb" in lowered or "naturhäuschen" in lowered or "nature house" in lowered or "naturhaeuschen" in lowered:
        return "platform_possible"
    if "booking.com" in lowered or "booking" in lowered:
        return "booking_model_unknown"
    if "tomas" in lowered or "direkt" in lowered or "website" in lowered or "homepage" in lowered:
        return "guest_invoice_possible"
    return "unknown"


def normalize_lines(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise ValueError("Rechnungspositionen müssen eine Liste sein")
    if len(raw) > 50:
        raise ValueError("Zu viele Rechnungspositionen")
    lines = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Rechnungsposition muss ein Objekt sein")
        label = str(item.get("description") or "").strip()
        if not label or len(label) > 250:
            raise ValueError("Positionsbezeichnung fehlt oder ist zu lang")
        lines.append({
            "description": label,
            "gross": signed_line_money(item.get("gross", "0.00")),
            "tax_rate": str(item.get("tax_rate") or "").strip(),  # empty = unresolved
        })
    return lines


def make_draft(booking: dict[str, Any]) -> dict[str, Any]:
    booking_id = str(booking.get("id") or "").strip()
    if not booking_id.isdigit() or int(booking_id) < 1:
        raise ValueError("Buchungs-ID fehlt")
    amount = decimal_money(booking.get("price") or 0)
    channel = channel_name(booking)
    guest = str(booking.get("guest-name") or "").strip()
    house = str((booking.get("apartment") or {}).get("name") or "")
    arrival, departure = str(booking.get("arrival") or ""), str(booking.get("departure") or "")
    text = (
        f"Guten Tag {guest or 'lieber Gast'},\n\n"
        f"vielen Dank für Ihre Buchung von {house or 'unserer Unterkunft'} "
        f"({arrival} bis {departure}).\n\n"
        "Wir bereiten Ihre Buchungsunterlagen vor. Die Zahlungsabwicklung "
        "wird derzeit geprüft. Eine etwaige Zahlungsaufforderung erhalten "
        "Sie nach gesonderter Bestätigung.\n\n"
        "Mit freundlichen Grüßen\nIhr Gastgeberteam"
    )
    elements = booking.get("priceElements")
    lines = []
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, dict) or element.get("priceIncludedInId"):
                continue
            lines.append({
                "description": str(element.get("name") or element.get("type") or "Leistung")[:250],
                "gross": signed_line_money(element.get("amount") or 0),
                "tax_rate": "",
            })
    if not lines:
        lines = [{"description": f"Aufenthalt {house} {arrival}–{departure}", "gross": amount, "tax_rate": ""}]
    now = utc_now()
    return {
        "booking_id": booking_id,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "source_fingerprint": booking_fingerprint(booking),
        "source_channel": channel,
        "source_channel_class": classify_channel(channel),
        "invoice": {
            "status": "draft",
            "recipient_name": guest,
            "recipient_address": "",
            "description": f"Übernachtung {house}, {arrival}–{departure}",
            "total_gross": amount,
            "paid_amount": "0.00",  # never infer paid from channel
            "payment_verified": False,
            "payment_flow": "unverified",
            "payment_note": "",
            "tax_note": "",
            "due_date": "",
            "line_items": lines,
            "logo_asset": "configured_local_logo",
        },
        "message": {"status": "draft", "subject": "Ihre Buchung – Informationen",
                    "body": text, "approved_revision": None},
        "audit": [{"at": now, "event": "prepared"}],
    }


def revise_draft(draft: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Patch safely, invalidate previous approval, use optimistic revisions."""
    from copy import deepcopy

    if not isinstance(changes, dict) or set(changes) - {"invoice", "message"}:
        raise ValueError("Nur invoice und message sind bearbeitbar")
    updated = deepcopy(draft)
    if "invoice" in changes:
        patch = changes["invoice"]
        if not isinstance(patch, dict) or set(patch) - INVOICE_EDITABLE:
            raise ValueError("Unbekanntes Rechnungsfeld")
        invoice = updated["invoice"]
        for key, val in patch.items():
            if key in ("total_gross", "paid_amount"):
                val = decimal_money(val)
            elif key == "line_items":
                val = normalize_lines(val)
            elif key == "payment_verified":
                if not isinstance(val, bool):
                    raise ValueError("payment_verified muss true oder false sein")
            elif key == "payment_flow":
                if val not in PAYMENT_FLOWS:
                    raise ValueError("Unbekannte Zahlungsart")
            else:
                if not isinstance(val, str) or len(val) > 3000:
                    raise ValueError("Textfeld ungültig oder zu lang")
                if key == "due_date" and val:
                    date.fromisoformat(val)
            invoice[key] = val
        if Decimal(invoice["paid_amount"]) > Decimal(invoice["total_gross"]):
            raise ValueError("Bezahlter Betrag übersteigt Rechnungssumme")
        invoice["status"] = "draft"
    if "message" in changes:
        patch = changes["message"]
        if not isinstance(patch, dict) or set(patch) - MESSAGE_EDITABLE:
            raise ValueError("Unbekanntes Nachrichtenfeld")
        if updated["message"]["status"] in ("sent", "sending", "delivery_unknown"):
            raise ValueError("Versendete/unklare Nachricht ist unveränderlich")
        for key, val in patch.items():
            if not isinstance(val, str) or len(val) > 12000:
                raise ValueError("Nachrichtentext ungültig oder zu lang")
            updated["message"][key] = val
        updated["message"]["status"] = "draft"
        updated["message"]["approved_revision"] = None
    updated["revision"] += 1
    updated["updated_at"] = utc_now()
    updated["audit"].append({"at": updated["updated_at"], "event": "edited"})
    return updated


def invoice_preflight(invoice: dict[str, Any]) -> dict[str, Any]:
    """Read-only invoice consistency report; deliberately NEVER issues an invoice.

    Validating the EN16931 payload and seller taxation is a separate mandatory step.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not str(invoice.get("recipient_name") or "").strip():
        errors.append("Rechnungsempfänger fehlt")
    if not str(invoice.get("recipient_address") or "").strip():
        errors.append("Rechnungsanschrift fehlt")
    try:
        total = Decimal(decimal_money(invoice.get("total_gross")))
        paid = Decimal(decimal_money(invoice.get("paid_amount")))
        if total <= 0:
            errors.append("Rechnungsbetrag muss größer als null sein")
        if paid > total:
            errors.append("Bereits bezahlt übersteigt Rechnungsbetrag")
    except ValueError:
        errors.append("Rechnungsbeträge sind ungültig")
        total, paid = Decimal("0"), Decimal("0")
    try:
        lines = normalize_lines(invoice.get("line_items"))
        if not lines:
            errors.append("Es fehlen Rechnungspositionen")
        sum_lines = sum((Decimal(line["gross"]) for line in lines), Decimal("0"))
        if sum_lines != total:
            errors.append("Summe der Rechnungspositionen stimmt nicht mit Gesamtbetrag überein")
        if any(not line["tax_rate"] for line in lines):
            warnings.append("Steuersätze und Steuerkategorien der Positionen fachlich prüfen")
        if any(Decimal(line["gross"]) < 0 for line in lines):
            warnings.append("Rabattpositionen vor EN16931-Export als korrekte Abschläge modellieren")
    except (ValueError, KeyError, TypeError, InvalidOperation):
        errors.append("Rechnungspositionen sind ungültig")
        sum_lines = Decimal("0")
    flow = invoice.get("payment_flow")
    if flow == "unverified" or flow not in PAYMENT_FLOWS:
        warnings.append("Zahlungsweg nicht verifiziert")
    if flow in ("platform", "already_paid") and not invoice.get("payment_verified"):
        warnings.append("Zahlungsstatus der Plattform nicht bestätigt")
    if flow == "guest_invoice" and not invoice.get("due_date"):
        warnings.append("Zahlungsziel für Überweisungsrechnung fehlt")
    if not invoice.get("payment_verified") and paid > 0:
        warnings.append("Bezahlter Betrag wurde noch nicht bestätigt")
    warnings.append("Absenderdaten, Steuerverfahren, Leistungszeitraum und ZUGFeRD-XML noch nicht validiert")
    return {
        "ready_for_issuance": False,  # no issuance backend or authoritative tax validation in V1
        "errors": errors,
        "warnings": warnings,
        "gross": str(total.quantize(Decimal("0.01"))),
        "paid": str(paid.quantize(Decimal("0.01"))),
        "outstanding": str((total - paid).quantize(Decimal("0.01"))),
        "line_total": str(sum_lines.quantize(Decimal("0.01"))),
    }


def approve_message(draft: dict[str, Any]) -> dict[str, Any]:
    from copy import deepcopy
    updated = deepcopy(draft)
    msg = updated["message"]
    if msg["status"] != "draft" or not msg["body"].strip():
        raise ValueError("Nur ein nichtleerer Nachrichtenentwurf kann freigegeben werden")
    if updated["invoice"]["payment_flow"] == "already_paid" and not updated["invoice"]["payment_verified"]:
        raise ValueError("Zahlung ist nicht verifiziert")
    msg["status"] = "approved"
    msg["approved_revision"] = updated["revision"]
    updated["audit"].append({"at": utc_now(), "event": "message_approved"})
    return updated
