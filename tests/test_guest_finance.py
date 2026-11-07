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
        changed["modifiedAt"] = "2026-11-07 10:00:00"
        self.assertNotEqual(mod.booking_fingerprint(original), mod.booking_fingerprint(changed))
        changed = booking()
        changed["unrelatedApiAttribute"] = "unrelated"
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

    def test_invoice_preflight_blocks_unvalidated_issuance(self):
        invoice = mod.make_draft(booking())["invoice"]
        report = mod.invoice_preflight(invoice)
        self.assertFalse(report["ready_for_issuance"])
        self.assertIn("Strukturierte Rechnungsanschrift fehlt", report["errors"])
        self.assertEqual(report["outstanding"], "420.00")

    def test_invoice_preflight_detects_wrong_line_sum(self):
        invoice = mod.make_draft(booking())["invoice"]
        invoice["recipient_address"] = "Musterstraße 1"
        invoice["line_items"][0]["gross"] = "300.00"
        report = mod.invoice_preflight(invoice)
        self.assertTrue(any("Summe" in x for x in report["errors"]))
        self.assertEqual(report["line_total"], "300.00")

    def test_invoice_preflight_partial_payment(self):
        invoice = mod.make_draft(booking())["invoice"]
        invoice["recipient_address"] = "Musterstraße 1"
        invoice["paid_amount"] = "200.00"
        invoice["payment_flow"] = "guest_invoice"
        invoice["payment_verified"] = True
        invoice["due_date"] = "2027-01-01"
        report = mod.invoice_preflight(invoice)
        self.assertEqual(report["outstanding"], "220.00")
        self.assertFalse(report["ready_for_issuance"])

    def test_payment_context_message_never_assumes_portal_is_paid(self):
        ctx = {"guest": "Muster Gast", "house": "Haus 13", "arrival": "2027-06-01",
               "departure": "2027-06-05", "language": "de"}
        inv = mod.make_draft(booking())["invoice"]
        inv["payment_flow"] = "platform"
        msg = mod.compose_message(ctx, inv)
        self.assertIn("wird derzeit geprüft", msg["body"])
        self.assertNotIn("als bezahlt bestätigt", msg["body"])

    def test_context_message_after_verified_platform_payment(self):
        inv = mod.make_draft(booking())["invoice"]
        inv["payment_flow"] = "platform"
        inv["paid_amount"] = "420.00"
        inv["payment_verified"] = True
        msg = mod.compose_message({"guest": "Test", "house": "House",
                                   "language": "en"}, inv)
        self.assertIn("No additional transfer", msg["body"])
        self.assertNotIn("Please pay by", msg["body"])

    def test_context_message_for_invoice_requires_verified_bank_details(self):
        inv = mod.make_draft(booking())["invoice"]
        inv["payment_flow"] = "guest_invoice"
        inv["payment_verified"] = True
        inv["due_date"] = "2027-01-01"
        text = mod.compose_message({"guest": "Test", "language": "de"}, inv)
        self.assertNotIn("Bitte überweisen Sie", text["body"])
        inv["payment_note"] = "Banküberweisung an das Geschäftskonto"
        text = mod.compose_message({"guest": "Test", "language": "de"}, inv)
        self.assertIn("Bitte überweisen Sie", text["body"])

    def test_demo_preview_request_requires_complete_manual_review(self):
        d = mod.make_draft(booking())
        with self.assertRaises(ValueError):
            mod.request_invoice_demo_preview(d)
        ready = mod.revise_draft(d, {"invoice": {
            "recipient_street": "Musterweg 1", "recipient_postal_code": "12345",
            "recipient_city": "Musterstadt", "recipient_country": "DE",
            "payment_verified": True, "payment_flow": "guest_invoice",
            "due_date": "2027-01-01", "line_items": [
                {"description": "Miete", "gross": "420.00", "tax_rate": "7", "position_type": "rent", "quantity": 1}
            ],
        }})
        queued = mod.request_invoice_demo_preview(ready)
        self.assertEqual(queued["invoice_review"]["state"], "requested")
        self.assertEqual(queued["invoice_review"]["requested_revision"], ready["revision"])
        self.assertNotEqual(queued["invoice_review"]["state"], "approved_preview")
        again = mod.request_invoice_demo_preview(queued)
        self.assertEqual(len(again["audit"]), len(queued["audit"]))
        edited = mod.revise_draft(queued, {"message": {"subject": "Neuer Betreff"}})
        self.assertEqual(edited["invoice_review"]["state"], "draft")
        with self.assertRaises(ValueError):
            mod.request_invoice_demo_preview(dict(ready, source_change_pending=True))

    def test_demo_preview_request_refuses_unresolved_tax_and_payment(self):
        d = mod.make_draft(booking())
        ready = mod.revise_draft(d, {"invoice": {
            "recipient_street": "Musterweg 1", "recipient_postal_code": "12345",
            "recipient_city": "Musterstadt", "recipient_country": "DE",
            "payment_flow": "platform", "payment_verified": True,
        }})
        with self.assertRaisesRegex(ValueError, "Leistungsart"):
            mod.request_invoice_demo_preview(ready)
        changed = mod.revise_draft(ready, {"invoice": {
            "line_items": [{"description": "Aufenthalt", "gross": "420.00", "tax_rate": "19"}],
            "payment_verified": False,
        }})
        with self.assertRaisesRegex(ValueError, "Zahlungs"):
            mod.request_invoice_demo_preview(changed)

    def test_mittelhof_5_positions_and_two_person_dog_limits(self):
        lines = [
            {"position_type": "rent", "description": "Miete", "gross": "500.00", "vat_rate": "7"},
            {"position_type": "cleaning", "description": "Reinigung", "gross": "50.00", "vat_rate": "7"},
            {"position_type": "extra_person", "description": "Zusätzliche Person", "gross": "40.00", "vat_rate": "7", "quantity": 2},
            {"position_type": "dog", "description": "Hund", "gross": "20.00", "vat_rate": "7", "quantity": 2},
            {"position_type": "stay_discount", "description": "Nachlass", "gross": "-30.00", "vat_rate": "7",
             "discount_nights": 4, "discount_rule": "4 Nächte, Betreiber-Rabatt schriftlich geprüft"},
        ]
        mod.validate_mittelhof_positions(lines, "2027-01-10", "2027-01-14")
        for index in (2, 3):
            bad = [dict(item) for item in lines]
            bad[index]["quantity"] = 3
            with self.assertRaises(ValueError):
                mod.validate_mittelhof_positions(bad, "2027-01-10", "2027-01-14")
        wrong = [dict(item) for item in lines]
        wrong[0]["vat_rate"] = "19"
        with self.assertRaisesRegex(ValueError, "7"):
            mod.validate_mittelhof_positions(wrong, "2027-01-10", "2027-01-14")

    def test_discount_requires_explicit_duration_rule_not_fictional_threshold(self):
        data = [
            {"position_type": "rent", "description": "Miete", "gross": "500.00", "tax_rate": "7"},
            {"position_type": "stay_discount", "description": "Nachlass", "gross": "-10.00", "tax_rate": "7",
             "discount_nights": 4, "discount_rule": ""},
        ]
        with self.assertRaisesRegex(ValueError, "Rabattstaffel"):
            mod.validate_mittelhof_positions(data, "2027-01-10", "2027-01-14")
        data[1]["discount_rule"] = "manuell bestätigte 4-Nächte-Regel"
        data[1]["discount_nights"] = 5
        with self.assertRaisesRegex(ValueError, "Aufenthaltsnächte"):
            mod.validate_mittelhof_positions(data, "2027-01-10", "2027-01-14")
        data[1]["discount_nights"] = 4
        mod.validate_mittelhof_positions(data, "2027-01-10", "2027-01-14")

    def test_sent_message_stays_immutable_while_invoice_changes(self):
        draft = mod.make_draft(booking())
        draft["message"]["status"] = "sent"
        sent_subject = draft["message"]["subject"]
        revised = mod.revise_draft(draft, {"invoice": {"recipient_city": "Neue Stadt"}})
        self.assertEqual(revised["message"]["status"], "sent")
        self.assertEqual(revised["message"]["subject"], sent_subject)
        self.assertEqual(revised["invoice"]["recipient_city"], "Neue Stadt")
        with self.assertRaises(ValueError):
            mod.revise_draft(revised, {"message": {"body": "Darf nicht geändert werden"}})

    def test_missing_reservation_id_fails(self):
        b = booking()
        b["id"] = None
        with self.assertRaises(ValueError):
            mod.make_draft(b)


if __name__ == "__main__":
    unittest.main()
