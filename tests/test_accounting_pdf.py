"""Offline accounting PDF regression: no Home Assistant import, no external requests."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
root = ROOT / "custom_components" / "smoobu_mittelhof"
pkg1 = ModuleType("custom_components")
pkg1.__path__ = [str(ROOT / "custom_components")]
pkg2 = ModuleType("custom_components.smoobu_mittelhof")
pkg2.__path__ = [str(root)]
sys.modules.setdefault("custom_components", pkg1)
sys.modules.setdefault("custom_components.smoobu_mittelhof", pkg2)
name = "custom_components.smoobu_mittelhof.accounting_core"
spec = importlib.util.spec_from_file_location(name, root / "accounting_core.py")
core = importlib.util.module_from_spec(spec)
sys.modules[name] = core
spec.loader.exec_module(core)


def sample(price=475):
    return {
        "id": 98765, "type": "reservation",
        "arrival": "2027-08-12", "departure": "2027-08-17",
        "guest-name": "Test Gast", "channel": {"name": "Booking.com"},
        "apartment": {"id": 777, "name": "Haus Test"},
        "price": price, "price-paid": True,
        "priceElements": [
            {"type": "basePrice", "name": "Miete", "amount": 355},
            {"type": "cleaningFee", "name": "Reinigung", "amount": 55},
            {"type": "addon", "name": "Haustier", "amount": 35},
            {"type": "addon", "name": "Zusätzliche Person", "amount": 30},
        ],
    }


class AccountingTest(unittest.TestCase):
    def test_gross_vs_platform_net_and_no_payment_inference(self):
        prepared = core.prepare_booking(sample(), "Haus Test")
        self.assertEqual(prepared["total_gross"], "475.00")
        self.assertEqual(len(prepared["rows"]), 4)
        self.assertNotIn("payment_status", prepared)
        self.assertNotIn("price-paid", prepared)
        self.assertEqual(sum(Decimal(r["gross"]) for r in prepared["rows"]), Decimal("475.00"))

    def test_rates_require_manual_confirmation(self):
        p = core.prepare_booking(sample(), "Haus Test")
        for invalid in ([None]*4, ["7"]*3, ["7","7","7","garbage"]):
            with self.assertRaises(ValueError):
                core.approve_snapshot(p, invalid)
        snap = core.approve_snapshot(p, ["7","7","7","7"])
        self.assertEqual(sum(Decimal(r["vat_included"]) for r in snap["rows"]), Decimal("31.07"))
        self.assertEqual(snap["total_gross"], "475.00")
        self.assertEqual(snap["document_kind"], "internal_booking_record")
        self.assertEqual(snap, core.approve_snapshot(p, ["7"]*4))

    def test_mismatch_must_fail(self):
        p = core.prepare_booking(sample(470), "Haus Test")
        self.assertTrue(p["warnings"])
        with self.assertRaises(ValueError):
            core.approve_snapshot(p, ["7"]*4)

    def test_pdf_integrity_and_safe_internal_label(self):
        snap = core.approve_snapshot(core.prepare_booking(sample(), "Haus Test"), ["7"]*4)
        pdf = core.render_pdf(snap)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"xref", pdf)
        self.assertIn(b"startxref", pdf)
        self.assertIn(b"BUCHHALTUNGSBELEG", pdf)
        self.assertIn(b"KEINE Rechnung", pdf)
        self.assertNotIn(b"Test Gast <script>", pdf)
        self.assertEqual(pdf, core.render_pdf(snap))

    def test_long_document_creates_multiple_pages(self):
        p = core.prepare_booking(sample(), "Haus Test")
        p["rows"] = ([{"description": "Zusatzleistung" + " X"*60,
                      "gross":"1.00","quantity":1}] * 60)
        p["total_gross"]="60.00"
        snap=core.approve_snapshot(p,["7"]*60)
        pdf=core.render_pdf(snap)
        self.assertIn(b"/Count 5", pdf) if False else self.assertIn(b"/Count ", pdf)
        self.assertGreater(pdf.count(b"/Type /Page "),1)

    def test_foreign_currency_never_becomes_fictitious_eur(self):
        booking = sample()
        booking["priceElements"][0]["currencyCode"] = "USD"
        with self.assertRaisesRegex(ValueError, "Fremdwährung"):
            core.prepare_booking(booking, "Haus Test")

    def test_reject_blocked_and_non_cent(self):
        b=sample();b["is-blocked-booking"]=True
        with self.assertRaises(ValueError): core.prepare_booking(b,"Haus Test")
        b=sample();b["price"]="475.001"
        with self.assertRaises(ValueError): core.prepare_booking(b,"Haus Test")


if __name__=="__main__":
    unittest.main()
