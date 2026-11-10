"""Conservative draft preparation for guest communication and future ZUGFeRD invoices.

No invoice is issued here. No channel is assumed to have collected payment.
All money is stored as decimal strings to avoid float rounding.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from typing import Any

from .smoobu_sources import guest_invoice_address, source_price_lines

FINGERPRINT_FIELDS = (
    "id", "arrival", "departure", "channel", "guest-name", "email",
    "price", "price-paid", "prepayment", "prepayment-paid", "deposit",
    "modifiedAt", "price-details", "city-tax", "commission-included",
    "deposit-paid", "type", "is-blocked-booking",
)
PAYMENT_FLOWS = {"unverified", "platform", "guest_invoice", "already_paid"}
INVOICE_EDITABLE = {
    "recipient_name", "recipient_address", "recipient_street",
    "recipient_postal_code", "recipient_city", "recipient_country",
    "description", "total_gross",
    "paid_amount", "due_date", "payment_flow", "payment_note", "tax_note",
    "line_items", "payment_verified",
}
MESSAGE_EDITABLE = {"subject", "body"}
POSITION_NAMES = {
    "rent": "Miete",
    "cleaning": "Reinigung",
    "extra_person": "Zusätzliche Person",
    "dog": "Hund",
    "stay_discount": "Nachlass aufgrund der Mietdauer",
}
POSITION_LIMITS = {"rent": 1, "cleaning": 1, "extra_person": 2, "dog": 2, "stay_discount": 1}
DISCOUNT_MIN_NIGHTS = 8
DISCOUNT_FACTOR = Decimal("0.10")
DISCOUNT_RULE = "10 % Mietdauernachlass ab 8 Übernachtungen auf die gesamte Miete"



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


def source_booking_date(booking: dict[str, Any]) -> str | None:
    """Return Smoobu's ORIGINAL booking date; never substitute modification/today."""
    value = booking.get("created-at")
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", value):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def booking_due_date(booking: dict[str, Any]) -> str | None:
    """Mittelhof operator policy for EXPECTED payment due date, not payment status.

    Airbnb: day after check-in; Booking.com: day after check-out;
    Naturhäuschen: booking date; TOMAS/direct/homepage:
    28 days before arrival if booked >=28 days ahead, otherwise booking date.
    Unknown channels or invalid source dates: no invented fallback.
    """
    booked = source_booking_date(booking)
    if booked is None:
        return None
    channel = channel_name(booking).casefold().strip()
    try:
        arrival = date.fromisoformat(str(booking.get("arrival") or ""))
        departure = date.fromisoformat(str(booking.get("departure") or ""))
    except (TypeError, ValueError):
        return None
    if departure <= arrival:
        return None
    booked_date = date.fromisoformat(booked)
    if "airbnb" in channel:
        due = arrival + timedelta(days=1)
    elif ("booking.com" in channel or channel in ("booking", "booking com")):
        due = departure + timedelta(days=1)
    elif any(value in channel for value in
             ("naturhäuschen", "naturhaeuschen", "naturhauschen", "nature house")):
        due = booked_date
    elif any(value in channel for value in
             ("tomas", "direkt", "direct", "homepage", "website", "webseite")):
        due = arrival - timedelta(days=28) if (arrival - booked_date).days >= 28 else booked_date
    else:
        return None
    return due.isoformat()


def classify_channel(channel: str) -> str:
    lowered = channel.casefold()
    if "airbnb" in lowered or "naturhäuschen" in lowered or "nature house" in lowered or "naturhaeuschen" in lowered:
        return "platform_possible"
    if "booking.com" in lowered or "booking" in lowered:
        return "booking_model_unknown"
    if "tomas" in lowered or "direkt" in lowered or "website" in lowered or "homepage" in lowered:
        return "guest_invoice_possible"
    return "unknown"


def normalize_lines(raw: Any) -> list[dict[str, Any]]:
    """Keep legacy Smoobu positions editable; require explicit type for export."""
    if not isinstance(raw, list) or len(raw) > 50:
        raise ValueError("1 bis 50 Rechnungspositionen als Liste erwartet")
    lines = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Rechnungsposition muss ein Objekt sein")
        label = str(item.get("description") or "").strip()
        if not label or len(label) > 250:
            raise ValueError("Positionsbezeichnung fehlt oder ist zu lang")
        kind = str(item.get("position_type") or "").strip()
        if kind and kind not in POSITION_NAMES:
            raise ValueError("Unbekannte Mittelhof-Leistungsart")
        qty = item.get("quantity", 1)
        if type(qty) is not int or qty < 1 or qty > 2:
            raise ValueError("Menge muss 1 oder 2 sein")
        rule = item.get("discount_rule") or ""
        if not isinstance(rule, str) or len(rule) > 250:
            raise ValueError("Mietdauerrabatt-Regel zu lang")
        discount_nights = item.get("discount_nights")
        if discount_nights is not None and (
            type(discount_nights) is not int or discount_nights < 1 or discount_nights > 365
        ):
            raise ValueError("Rabattnächte ungültig")
        row = {
            "description": label,
            "gross": signed_line_money(item.get("gross", "0.00")),
            "tax_rate": str(item.get("tax_rate") or "").strip(),
            "position_type": kind,
            "quantity": qty,
        }
        if kind == "stay_discount":
            row["discount_rule"] = rule.strip()
            row["discount_nights"] = discount_nights
        lines.append(row)
    return lines


def stay_nights(arrival: str, departure: str) -> int:
    try:
        nights = (date.fromisoformat(departure) - date.fromisoformat(arrival)).days
    except (TypeError, ValueError) as exc:
        raise ValueError("Aufenthaltsdaten für Mietdauerrabatt fehlen") from exc
    if not 1 <= nights <= 365:
        raise ValueError("Aufenthaltsdauer außerhalb von 1 bis 365 Nächten")
    return nights


def expected_discount(rent_gross: Any, nights: int) -> Decimal:
    rent = Decimal(decimal_money(rent_gross))
    if rent <= 0:
        raise ValueError("Mietbetrag muss positiv sein")
    if nights < DISCOUNT_MIN_NIGHTS:
        return Decimal("0.00")
    discount = (rent * DISCOUNT_FACTOR).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if discount <= 0:
        raise ValueError("Mietbetrag für 10-%-Cent-Rabatt zu klein")
    return -discount


def apply_duration_discount(lines: Any, arrival: str, departure: str) -> tuple[list[dict[str, Any]], str | None]:
    """Canonicalize stay discount on saving a manually categorized rent.

    Never infer categories from Smoobu. The operator must first classify exactly
    one rent item. Rebuilds rather than stacks existing discount lines.
    """
    current = normalize_lines(lines)
    rent = [row for row in current if row["position_type"] == "rent"]
    if len(rent) != 1:
        # Keep legacy, unclassified Smoobu positions editable without changing
        # their original booking total; cannot issue until manually categorized.
        return current, None
    nights = stay_nights(arrival, departure)
    discount = expected_discount(rent[0]["gross"], nights)
    clean = [row for row in current if row["position_type"] != "stay_discount"]
    if discount:
        clean.append({
            "position_type": "stay_discount",
            "description": "10 % Mietdauernachlass ab 8 Nächten",
            "quantity": 1,
            "gross": str(discount),
            "tax_rate": "7",
            "discount_nights": nights,
            "discount_rule": DISCOUNT_RULE,
        })
    total = sum((Decimal(row["gross"]) for row in clean), Decimal("0.00"))
    if total <= 0:
        raise ValueError("Rechnungsbrutto nach Nachlass muss positiv sein")
    return clean, str(total.quantize(Decimal("0.01")))


def validate_mittelhof_positions(lines: Any, arrival: str, departure: str) -> None:
    """Only the five operator-defined categories, 7% and confirmed discount."""
    normalized = normalize_lines(lines)
    if not normalized or len(normalized) > 20:
        raise ValueError("Mindestens eine und maximal 20 Mittelhof-Positionen erforderlich")
    nights = stay_nights(arrival, departure)
    seen: dict[str, int] = {}
    for item in normalized:
        kind = item["position_type"]
        if kind not in POSITION_NAMES:
            raise ValueError("Position ohne bestätigte Mittelhof-Leistungsart")
        seen[kind] = seen.get(kind, 0) + item["quantity"]
        if seen[kind] > POSITION_LIMITS[kind]:
            raise ValueError(POSITION_NAMES[kind] + ": maximale Anzahl überschritten")
        try:
            rate = Decimal(item["tax_rate"])
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise ValueError("Steuersatz jeder Position muss 7 % sein") from exc
        if rate != Decimal("7"):
            raise ValueError("Mittelhof-Leistungsarten nur mit 7 % ausgewiesen")
        value = Decimal(item["gross"])
        if kind == "stay_discount":
            if value >= 0:
                raise ValueError("Mietdauernachlass muss negativ sein")
            if item.get("discount_nights") != nights:
                raise ValueError("Mietdauernachlass: Aufenthaltsnächte nicht bestätigt")
            if len(str(item.get("discount_rule") or "").strip()) < 8:
                raise ValueError("Mietdauernachlass: gültige Rabattstaffel/Regel fehlt")
        elif value <= 0:
            raise ValueError("Mittelhof-Leistungsposition muss positiv sein")
    if seen.get("rent") != 1:
        raise ValueError("Eine Mietposition ist zwingend erforderlich")
    gross = next(Decimal(row["gross"]) for row in normalized if row["position_type"] == "rent")
    expected = expected_discount(gross, nights)
    discounts = [row for row in normalized if row["position_type"] == "stay_discount"]
    if nights < DISCOUNT_MIN_NIGHTS:
        if discounts:
            raise ValueError("Vor der 8. Nacht kein Mietdauernachlass zulässig")
    else:
        if len(discounts) != 1:
            raise ValueError("Ab der 8. Nacht sind 10 % Mietdauernachlass Pflicht")
        row = discounts[0]
        if Decimal(row["gross"]) != expected:
            raise ValueError("Mietdauernachlass muss genau 10 % der gesamten Miete betragen")
        if row.get("discount_rule") != DISCOUNT_RULE:
            raise ValueError("Mietdauernachlass muss die bestätigte Regel ausweisen")


def compose_message(context: dict[str, Any], invoice: dict[str, Any]) -> dict[str, str]:
    """Explicitly regenerate a guest message from a reviewed invoice draft.

    Never claim payment based solely on OTA channel or Smoobu's price-paid marker.
    """
    is_english = str(context.get("language") or "").casefold().startswith("en")
    guest = str(context.get("guest") or "").strip()
    house = str(context.get("house") or "").strip()
    arrival = str(context.get("arrival") or "")
    departure = str(context.get("departure") or "")
    gross = decimal_money(invoice["total_gross"])
    paid = decimal_money(invoice["paid_amount"])
    outstanding = decimal_money(Decimal(gross) - Decimal(paid))
    verified = invoice.get("payment_verified") is True
    flow = invoice.get("payment_flow")
    due = str(invoice.get("due_date") or "").strip()
    note = str(invoice.get("payment_note") or "").strip()
    if is_english:
        intro = (f"Dear {guest or 'guest'},\n\nThank you for booking "
                 f"{house or 'our accommodation'} from {arrival} to {departure}.\n\n")
        if verified and Decimal(outstanding) == 0:
            payment = "The accommodation amount has been recorded as paid. No additional transfer is requested."
        elif flow == "guest_invoice" and verified and due and note:
            payment = (f"Invoice amount: {gross} EUR. Amount already paid: {paid} EUR. "
                       f"Remaining amount: {outstanding} EUR. Please pay by {due}.\n{note}")
        elif flow == "platform" and verified:
            payment = ("Your platform payment is recorded as follows: " +
                       f"{paid} EUR paid, {outstanding} EUR outstanding. "
                       "Any further payment arrangement will be communicated separately.")
        else:
            payment = ("Payment handling is being checked. We will contact you separately "
                       "if any amount is still due.")
        closing = "\n\nKind regards,\nYour host team"
        subject = "Your stay – booking information"
    else:
        intro = (f"Guten Tag {guest or 'lieber Gast'},\n\nvielen Dank für Ihre Buchung von "
                 f"{house or 'unserer Unterkunft'} ({arrival} bis {departure}).\n\n")
        if verified and Decimal(outstanding) == 0:
            payment = ("Der Rechnungsbetrag wurde als bezahlt bestätigt. "
                       "Eine zusätzliche Überweisung ist nicht erforderlich.")
        elif flow == "guest_invoice" and verified and due and note:
            payment = (f"Rechnungsbetrag: {gross} €. Bereits bezahlt: {paid} €. "
                       f"Noch zu zahlen: {outstanding} €. Bitte überweisen Sie bis {due}.\n{note}")
        elif flow == "platform" and verified:
            payment = (f"Für die Plattformzahlung wurden {paid} € als bezahlt bestätigt. "
                       f"Offener Betrag: {outstanding} €. Eine etwaige weitere Zahlungsabwicklung "
                       "teilen wir Ihnen gesondert mit.")
        else:
            payment = ("Die Zahlungsabwicklung wird derzeit geprüft. "
                       "Falls noch eine Zahlung erforderlich ist, erhalten Sie "
                       "eine gesonderte Nachricht.")
        closing = "\n\nMit freundlichen Grüßen\nIhr Gastgeberteam"
        subject = "Ihr Aufenthalt – Buchungsinformationen"
    return {"subject": subject, "body": intro + payment + closing}


def make_draft(booking: dict[str, Any]) -> dict[str, Any]:
    booking_id = str(booking.get("id") or "").strip()
    if not booking_id.isdigit() or int(booking_id) < 1:
        raise ValueError("Buchungs-ID fehlt")
    amount = decimal_money(booking.get("price") or 0)
    channel = channel_name(booking)
    guest = str(booking.get("guest-name") or "").strip()
    house = str((booking.get("apartment") or {}).get("name") or "")
    arrival, departure = str(booking.get("arrival") or ""), str(booking.get("departure") or "")
    context = {"guest": guest, "house": house, "arrival": arrival,
               "departure": departure, "language": str(booking.get("language") or "de")}
    lines, source_warnings = source_price_lines(booking)
    suggested_due = booking_due_date(booking)
    if suggested_due is None:
        source_warnings.append(
            "Zahlungsziel nicht ableitbar: Smoobu-Buchungsdatum, Aufenthalt und Buchungskanal prüfen"
        )
    addr = booking.get("_guest_invoice_address")
    if not isinstance(addr, dict):
        addr = guest_invoice_address(booking, None)
    # Never infer payment from Smoobu channel/payment status.

    now = utc_now()
    provisional_invoice = {"total_gross": amount, "paid_amount": "0.00",
                           "payment_verified": False, "payment_flow": "unverified"}
    message = compose_message(context, provisional_invoice)
    return {
        "booking_id": booking_id,
        "booking_context": context,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "source_fingerprint": booking_fingerprint(booking),
        "source_channel": channel,
        "source_channel_class": classify_channel(channel),
        "source_import_warnings": source_warnings,
        "invoice": {
            "status": "draft",
            "recipient_name": addr.get("recipient_name") or guest,
            "recipient_address": ", ".join(x for x in [
                addr.get("recipient_street"), addr.get("recipient_postal_code"),
                addr.get("recipient_city"), addr.get("recipient_country"),
            ] if x),
            "recipient_street": addr.get("recipient_street") or "",
            "recipient_postal_code": addr.get("recipient_postal_code") or "",
            "recipient_city": addr.get("recipient_city") or "",
            "recipient_country": addr.get("recipient_country") or "",
            "description": f"Übernachtung {house}, {arrival}–{departure}",
            "total_gross": amount,
            "paid_amount": "0.00",  # never infer paid from channel
            "payment_verified": False,
            "payment_flow": "unverified",
            "payment_note": "",
            "tax_note": "",
            "due_date": suggested_due or "",
            "line_items": lines,
            "logo_asset": "configured_local_logo",
        },
        "message": {"status": "draft", "subject": message["subject"],
                    "body": message["body"], "approved_revision": None},
        "invoice_review": {"state": "draft", "requested_revision": None, "requested_at": None},
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
                context = updated.get("booking_context") or {}
                val, calculated_total = apply_duration_discount(
                    val, str(context.get("arrival") or ""),
                    str(context.get("departure") or ""),
                )
                if calculated_total is not None:
                    invoice["total_gross"] = calculated_total
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
    updated["invoice_review"] = {"state": "draft", "requested_revision": None, "requested_at": None}
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
    if not str(invoice.get("recipient_street") or "").strip() or not str(invoice.get("recipient_city") or "").strip() or not str(invoice.get("recipient_postal_code") or "").strip():
        errors.append("Strukturierte Rechnungsanschrift fehlt")
    if len(str(invoice.get("recipient_country") or "")) != 2:
        errors.append("ISO-Ländercode für Rechnungsempfänger fehlt")
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
        category_totals: dict[str, int] = {}
        for line in lines:
            kind = line.get("position_type") or ""
            if kind not in POSITION_NAMES:
                errors.append("Leistungsart einer Position nicht ausgewählt")
                continue
            category_totals[kind] = category_totals.get(kind, 0) + line.get("quantity", 1)
            try:
                rate = Decimal(line.get("tax_rate") or "")
            except (InvalidOperation, TypeError):
                errors.append("7-%-Steuersatz einer Position fehlt")
            else:
                if rate != Decimal("7"):
                    errors.append("Nur 7 % für Mittelhof-Leistungsarten zulässig")
            if kind == "stay_discount":
                if Decimal(line["gross"]) >= 0:
                    errors.append("Mietdauernachlass muss negativ sein")
                if len(str(line.get("discount_rule") or "").strip()) < 8:
                    errors.append("Mietdauernachlass: bestätigte Rabattstaffel fehlt")
            elif Decimal(line["gross"]) <= 0:
                errors.append("Mittelhof-Leistung muss einen positiven Bruttobetrag haben")
        if category_totals.get("rent", 0) != 1:
            errors.append("Genau eine Mietposition erforderlich")
        for kind, count in category_totals.items():
            if count > POSITION_LIMITS[kind]:
                errors.append(POSITION_NAMES[kind] + ": Höchstmenge überschritten")

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


def request_invoice_demo_preview(draft: dict[str, Any]) -> dict[str, Any]:
    """Request a DEMO preview, NEVER approve or issue a real invoice."""
    from copy import deepcopy
    updated = deepcopy(draft)
    if updated.get("source_change_pending"):
        raise ValueError("Buchung wurde geändert; Entwurf erneut prüfen")
    invoice = updated["invoice"]
    report = invoice_preflight(invoice)
    if report["errors"]:
        raise ValueError("Rechnungsprüfung: " + "; ".join(report["errors"]))
    if invoice.get("payment_verified") is not True or invoice.get("payment_flow") not in (
        "platform", "guest_invoice", "already_paid"
    ):
        raise ValueError("Zahlungsweg und Zahlungsstatus müssen manuell bestätigt sein")
    if invoice.get("payment_flow") == "guest_invoice" and not invoice.get("due_date"):
        raise ValueError("Überweisungsrechnung benötigt Zahlungsziel")
    context = updated.get("booking_context") or {}
    validate_mittelhof_positions(
        invoice.get("line_items"),
        str(context.get("arrival") or ""),
        str(context.get("departure") or ""),
    )

    previous = updated.get("invoice_review") or {}
    if previous.get("state") == "requested" and previous.get("requested_revision") == updated["revision"]:
        return updated
    stamp = utc_now()
    updated["invoice_review"] = {
        "state": "requested", "requested_revision": updated["revision"],
        "requested_at": stamp,
    }
    updated["audit"].append({"at": stamp, "event": "demo_invoice_preview_requested"})
    return updated


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
