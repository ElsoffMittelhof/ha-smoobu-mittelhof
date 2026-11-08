"""Pure Smoobu invoice/address import contract, never issues or sends invoices.

Smoobu's reservation API may omit priceElements even when the booking UI
displays separate rows; GET /api/reservations/<id>/price-elements is authoritative.
Conservative classification of addons, source total reconciliation and operator
review prevent silently invented positions or wrong taxes.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any


_COUNTRIES = {
    "deutschland": "DE", "germany": "DE", "de": "DE", "deu": "DE",
    "osterreich": "AT", "austria": "AT", "at": "AT",
    "schweiz": "CH", "switzerland": "CH", "suisse": "CH", "ch": "CH",
    "niederlande": "NL", "netherlands": "NL", "holland": "NL", "nl": "NL",
    "belgien": "BE", "belgium": "BE", "be": "BE",
    "frankreich": "FR", "france": "FR", "fr": "FR",
    "polen": "PL", "poland": "PL", "pl": "PL",
    "danemark": "DK", "denmark": "DK", "dk": "DK",
    "italien": "IT", "italy": "IT", "it": "IT",
    "spanien": "ES", "spain": "ES", "es": "ES",
    "portugal": "PT", "pt": "PT", "tschechien": "CZ", "czech republic": "CZ",
    "vereinigtes konigreich": "GB", "united kingdom": "GB", "uk": "GB",
    "grossbritannien": "GB", "great britain": "GB", "gb": "GB",
    "usa": "US", "united states": "US", "united states of america": "US", "us": "US",
    "schweden": "SE", "sweden": "SE", "se": "SE",
    "norwegen": "NO", "norway": "NO", "no": "NO",
    "luxemburg": "LU", "luxembourg": "LU", "lu": "LU",
}

_COUNTRY_ISO = frozenset({
    "AD","AE","AL","AR","AT","AU","BA","BE","BG","BR","CA","CH","CN","CY",
    "CZ","DE","DK","EE","EG","ES","FI","FR","GB","GR","HR","HU","ID",
    "IE","IL","IN","IS","IT","JP","KR","LI","LT","LU","LV","MA","MC",
    "ME","MK","MT","MX","NL","NO","NZ","PL","PT","RO","RS","RU",
    "SA","SE","SG","SI","SK","TH","TR","UA","US","ZA",
})


def _fold(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value)


def iso_country(value: Any) -> str:
    raw = str(value or "").strip()
    if len(raw) == 2 and raw.upper() in _COUNTRY_ISO:
        return raw.upper()
    return _COUNTRIES.get(_fold(raw), "")


def guest_invoice_address(booking: dict, guest: dict | None) -> dict[str, str]:
    guest = guest if isinstance(guest, dict) else {}
    ba = booking.get("address")
    ga = guest.get("address")
    ba = ba if isinstance(ba, dict) else {}
    ga = ga if isinstance(ga, dict) else {}
    def one(*values):
        return next((str(x).strip() for x in values if x is not None and str(x).strip()), "")
    country_raw = one(ga.get("country"),ba.get("country"),guest.get("country"),booking.get("country"))
    return {
        "recipient_name": one(guest.get("companyName"),booking.get("guest-name"),
                              " ".join([str(guest.get("firstName") or ""), str(guest.get("lastName") or "")]).strip()),
        "recipient_street": one(ga.get("street"),ba.get("street")),
        "recipient_postal_code": one(ga.get("postalCode"),ga.get("zipCode"),ba.get("postalCode")),
        "recipient_city": one(ga.get("city"),ga.get("location"),ba.get("city"),ba.get("location")),
        "recipient_country": iso_country(country_raw),
    }


def classification(element: dict) -> str:
    kind = _fold(element.get("type")).replace(" ", "")
    label = _fold(element.get("name"))
    if kind == "baseprice":
        return "rent"
    if kind == "cleaningfee":
        return "cleaning"
    if kind in ("longstaydiscount", "coupon"):
        # Smoobu coupons are NOT necessarily rent-only discounts.
        return "stay_discount" if kind == "longstaydiscount" else ""
    if kind == "addon" or not kind:
        if any(word in label for word in ("haustier", "pet fee", "dog", "hund", "tiergebuhr", "pet charge")):
            return "dog"
        if any(word in label for word in ("zusatzliche gast", "zusatzliche person",
                                          "extra guest", "extra person", "additional guest",
                                          "additional person", "mehrperson")):
            return "extra_person"
    return ""


def _money(amount: Any) -> str:
    try:
        x = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("Smoobu-Preisposition ist kein gültiger Geldbetrag") from err
    if not x.is_finite() or x.as_tuple().exponent < -2:
        raise ValueError("Smoobu-Preisposition nicht centgenau")
    return f"{x:.2f}"


def source_price_lines(booking: dict) -> tuple[list[dict], list[str]]:
    """Import original Smoobu amount, type, quantity and source IDs; no tax guess.

    Unknown addons are kept but unclassified, never made eligible for an
    automatic 7% invoice. Numeric total comparison excludes included children.
    """
    elements = booking.get("priceElements") or []
    if not isinstance(elements, list):
        elements = []
    warnings: list[str] = []
    rows = []
    def order(item):
        try:
            n = int(item.get("sortOrder") or 0)
        except (ValueError, TypeError):
            n = 0
        return n, str(item.get("id") or "")
    for el in sorted((x for x in elements if isinstance(x, dict)), key=order):
        if el.get("priceIncludedInId") is not None:
            continue
        kind = classification(el)
        desc = str(el.get("name") or el.get("type") or "Unbekannte Smoobu-Position").strip()[:250]
        currency = str(el.get("currencyCode") or "EUR").upper()
        if currency != "EUR":
            warnings.append(f"Nicht-EUR-Position {desc} ({currency}) – prüfen")
        raw_qty = el.get("quantity")
        qty = raw_qty if type(raw_qty) is int and 1 <= raw_qty <= 2 else 1
        if raw_qty is not None and raw_qty != qty:
            warnings.append(f"Unplausible Menge bei {desc}; manuell prüfen")
        gross = _money(el.get("amount"))
        # Never unilaterally promote a provider tax to 7%. Let user review.
        vat = "7" if kind in ("rent", "cleaning", "dog", "extra_person", "stay_discount") and currency == "EUR" else ""
        if el.get("tax") is not None and str(el.get("tax")) not in ("0", "0.0", "7", "7.0", "7.00"):
            vat = ""
            warnings.append(f"Smoobu-Steuerangabe bei {desc} weicht von 7 % ab – prüfen")
        if not kind:
            warnings.append(f"Unbekannte Leistungsart: {desc} – manuell zuordnen")
        row = {"description": desc,"gross": gross,"tax_rate": vat,
               "position_type": kind,"quantity": qty}
        rows.append(row)
    if not rows:
        rows = [{
            "description": f"Aufenthalt {booking.get('arrival') or ''}–{booking.get('departure') or ''}",
            "gross": _money(booking.get("price") or 0),
            "tax_rate": "", "position_type": "", "quantity": 1,
        }]
        warnings.append("Keine Smoobu-Einzelpositionen geliefert; nur Gesamtbetrag vorhanden")
    try:
        source = Decimal(_money(booking.get("price") or 0))
        row_total = sum((Decimal(x["gross"]) for x in rows), Decimal("0.00"))
        if row_total != source:
            warnings.append(
                f"Smoobu-Positionssumme {row_total:.2f} EUR weicht von Buchungsbetrag "
                f"{source:.2f} EUR ab; vor Rechnung manuell abgleichen"
            )
    except ValueError as err:
        warnings.append(str(err))
    return rows,warnings
