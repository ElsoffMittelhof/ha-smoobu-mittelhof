"""Isolated security/accounting tests for guest draft model (no HA, no network)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "custom_components" / "smoobu_mittelhof" / "guest_finance.py"
spec = importlib.util.spec_from_file_location("guest_finance", source)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


def booking(channel="Airbnb", paid="Yes", price=420):
    return {
        "id": 12345, "type": "reservation",
        "arrival": "2027-01-10", "departure": "2027-01-14",
        "apartment": {"id": 123, "name": "Ferienwohnung"},
        "guest-name": "Test Gast", "email": "test@example.invalid",
        "price": price, "price-paid": paid,
        "channel": {"name": channel},
    }


class TestGuestDrafts(unittest.TestCase):
    def test_channel_never_means_paid(self):
        for channel in ("Airbnb", "Booking.com", "Naturhäuschen", "TOMAS", "Direkt"):
            d = mod.make_draft(booking(channel))
            self.assertEqual(d["invoice"]["paid_amount"], "0.00")
            self.assertEqual(d["invoice"]["payment_flow"], "unverified")
            self.assertFalse(d["invoice"]["payment_verified"])
            self.assertIn("geprüft", d["message"]["body"])

    def test_money_rounding_must_not_be_implicit(self):
        for val in ("1.001", "-2", "NaN", "Infinity", "wat"):
            with self.subTest(value=val), self.assertRaises(ValueError):
                mod.decimal_money(val)
        self.assertEqual(mod.decimal_money("1.2"), "1.20")

    def test_edit_recipient_and_amount(self):
        d = mod.make_draft(booking())
        n = mod.revise_draft(d, {"invoice": {
            "recipient_name": "Testfirma GmbH",
            "recipient_address": "Musterstraße 1",
            "total_gross": "410.00",
            "paid_amount": "300.00",
            "payment_flow": "platform",
            "payment_verified": True,
            "line_items": [{"description": "Aufenthalt", "gross": "410", "tax_rate": ""}],
        }})
        self.assertEqual(n["revision"], 2)
        self.assertEqual(n["invoice"]["paid_amount"], "300.00")
        self.assertEqual(n["invoice"]["recipient_name"], "Testfirma GmbH")
        self.assertEqual(d["invoice"]["total_gross"], "420.00")
        self.assertEqual(d["invoice"]["status"], "draft")

    def test_overpayment_is_blocked(self):
        with self.assertRaises(ValueError):
            mod.revise_draft(mod.make_draft(booking()), {"invoice": {"paid_amount": "421.00"}})

    def test_invalid_due_date(self):
        with self.assertRaises(ValueError):
            mod.revise_draft(mod.make_draft(booking()), {"invoice": {"due_date": "2027-02-30"}})

    def test_unknown_fields_are_blocked(self):
        with self.assertRaises(ValueError):
            mod.revise_draft(mod.make_draft(booking()), {"message": {"status": "sent"}})
        with self.assertRaises(ValueError):
            mod.revise_draft(mod.make_draft(booking()), {"invoice": {"invoice_number": "fake"}})

    def test_message_edits_invalidate_approval(self):
        approved = mod.approve_message(mod.make_draft(booking()))
        revised = mod.revise_draft(approved, {"message": {"body": "Neue Nachricht"}})
        self.assertEqual(revised["message"]["status"], "draft")
        self.assertIsNone(revised["message"]["approved_revision"])
        self.assertEqual(approved["message"]["status"], "approved")

    def test_cannot_edit_sent_message(self):
        d = mod.make_draft(booking())
        d["message"]["status"] = "sent"
        with self.assertRaises(ValueError):
            mod.revise_draft(d, {"message": {"body": "Doppelte Mail"}})

    def test_approval_only_drafts(self):
        d = mod.make_draft(booking())
        approved = mod.approve_message(d)
        self.assertEqual(approved["message"]["approved_revision"], 1)
        with self.assertRaises(ValueError):
            mod.approve_message(approved)

    def test_billing_fingerprint_changes(self):
        original = booking()
        changed = booking(price=421)
        self.assertNotEqual(mod.booking_fingerprint(original), mod.booking_fingerprint(changed))
        changed = booking()
        changed["modifiedAt"] = "unrelated"
        self.assertEqual(mod.booking_fingerprint(original), mod.booking_fingerprint(changed))

    def test_price_elements_not_double_counted(self):
        b = booking()
        b["priceElements"] = [
            {"name": "Unterkunft", "amount": 400, "priceIncludedInId": None},
            {"name": "enthaltene Kosten", "amount": 20, "priceIncludedInId": 9},
            {"name": "Reinigung", "amount": 20, "priceIncludedInId": None},
        ]
        d = mod.make_draft(b)
        self.assertEqual(len(d["invoice"]["line_items"]), 2)

    def test_negative_discount_is_preserved(self):
        b = booking()
        b["priceElements"] = [
            {"name": "Aufenthalt", "amount": 450, "priceIncludedInId": None},
            {"name": "Rabatt", "amount": -30, "priceIncludedInId": None},
        ]
        d = mod.make_draft(b)
        self.assertEqual(d["invoice"]["line_items"][1]["gross"], "-30.00")
        changed = mod.revise_draft(d, {"invoice": {"line_items": [
            {"description": "Rabatt", "gross": "-30.00", "tax_rate": ""}
        ]}})
        self.assertEqual(changed["invoice"]["line_items"][0]["gross"], "-30.00")

    def test_missing_reservation_id_fails(self):
        b = booking()
        b["id"] = None
        with self.assertRaises(ValueError):
            mod.make_draft(b)


if __name__ == "__main__":
    unittest.main()
