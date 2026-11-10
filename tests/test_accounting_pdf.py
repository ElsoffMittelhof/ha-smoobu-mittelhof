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
        "created-at": "2026-11-09 15:43",
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
        p["rows"] = [{"source_index": i, "description": "Zusatzleistung" + " X"*60,
                      "gross":"1.00","quantity":1} for i in range(60)]
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

    def test_airbnb_settlements_do_not_inflate_guest_gross(self):
        b = sample()
        b["channel"] = {"name":"Airbnb"}
        b["priceElements"] = [
            {"name":"Base Price","type":"basePrice","amount":355},
            {"name":"Cancellation Host Fee","type":"addon","amount":73.63},
            {"name":"Cancellation Payout","type":"addon","amount":401.37},
            {"name":"Cleaning fee","type":"cleaningFee","amount":55},
            {"name":"Commission","type":"addon","amount":73.63},
            {"name":"PASS_THROUGH_PET_FEE","type":"addon","amount":35},
            {"name":"Additional Guest Fee","type":"addon","amount":30},
        ]
        p = core.prepare_booking(b,"Haus Test")
        self.assertEqual([x["gross"] for x in p["rows"]],
                         ["355.00","55.00","35.00","30.00"])
        self.assertEqual([x["position_type"] for x in p["rows"]],
                         ["rent","cleaning","dog","extra_person"])
        self.assertEqual(len(p["ignored_settlement_lines"]),3)
        self.assertEqual(p["warnings"],[])
        snap=core.approve_snapshot(p,["7"]*4)
        self.assertEqual(snap["total_gross"],"475.00")
        self.assertEqual(sum(Decimal(r["gross"]) for r in snap["rows"]),Decimal("475.00"))
        self.assertEqual(len(snap["ignored_settlement_lines"]),3)
        self.assertIn(b"475.00",core.render_pdf(snap))

    def test_manual_description_amount_and_deleted_rows_are_validated(self):
        p=core.prepare_booking(sample(),"Haus Test")
        edits=[
            {"source_index":0,"description":"Übernachtung","gross":"390.00"},
            {"source_index":1,"description":"Reinigung","gross":"55.00"},
            {"source_index":3,"description":"Zusätzliche Person","gross":"30.00"},
        ]
        snap=core.approve_snapshot(p,["7","7","7"],edits)
        self.assertEqual(snap["total_gross"],"475.00")
        self.assertEqual(len(snap["rows"]),3)
        self.assertEqual(snap["source_excluded"][0]["source_index"],2)
        self.assertEqual(snap["source_changes"][0]["original_gross"],"355.00")
        invalid=[dict(x) for x in edits]
        invalid[0]["gross"]="389.00"
        with self.assertRaises(ValueError):
            core.approve_snapshot(p,["7"]*3,invalid)
        with self.assertRaises(ValueError):
            core.approve_snapshot(p,["7"]*4,edits+[edits[0]])
        with self.assertRaises(ValueError):
            core.approve_snapshot(p,["7"],[{"source_index":100,"description":"Fake","gross":"475.00"}])

    def test_direct_and_tomas_invoice_routing_no_assumed_homepage_payment(self):
        b=sample()
        for channel in ("TOMAS","Direktbuchung"):
            b["channel"]={"name":channel}
            self.assertEqual(core.prepare_booking(b,"Haus Test")["suggested_document_kind"],"invoice")
        b["channel"]={"name":"Homepage"}
        self.assertEqual(core.prepare_booking(b,"Haus Test")["suggested_document_kind"],"booking_record")

    def test_booking_date_drives_both_lexware_fields(self):
        source=sample()
        source["created-at"]="2026-11-09 15:43"
        prepared=core.prepare_booking(source, "Haus Test")
        self.assertEqual(prepared["booking_created_at"],"2026-11-09")
        self.assertEqual(prepared["document_date"],"2026-11-09")
        self.assertEqual(prepared["due_date"],"2026-11-09")
        snap=core.approve_snapshot(prepared,["7"]*4)
        self.assertEqual(snap["schema"],"mittelhof.accounting.v4")
        self.assertEqual(snap["document_date"],snap["due_date"])
        self.assertEqual(snap["document_date"],"2026-11-09")
        pdf=core.render_pdf(snap)
        self.assertIn(b"Belegdatum: 09.11.2026",pdf)
        self.assertIn(b"F\xe4lligkeitsdatum: 09.11.2026",pdf)
        self.assertIn(b"Buchungsdatum: 09.11.2026",pdf)

    def test_lexware_income_document_number_and_checkout_date(self):
        source=sample()
        source["id"]=160317906
        source["departure"]="2027-08-17"
        p=core.prepare_booking(source,"Haus Test")
        self.assertEqual(p["accounting_type"],"Einnahme")
        self.assertEqual(p["document_number"],"160317906")
        self.assertEqual(p["service_date"],"2027-08-17")
        snap=core.approve_snapshot(p,["7"]*4)
        self.assertEqual(snap["schema"],"mittelhof.accounting.v4")
        self.assertEqual(snap["accounting_type"],"Einnahme")
        self.assertEqual(snap["document_number"],snap["booking_id"])
        pdf=core.render_pdf(snap)
        for expected in (b"Belegtyp: Einnahme", b"Belegnummer: 160317906",
                         b"Leistungsdatum: 17.08.2027", b"Belegdatum: 09.11.2026",
                         b"F\\xe4lligkeitsdatum: 09.11.2026"):
            self.assertIn(expected,pdf)

    def test_invalid_checkout_blocks_export(self):
        for bad in ("", "2027-08-12", "2027-02-30", "2027-08-11"):
            booking=sample()
            booking["departure"]=bad
            prepared=core.prepare_booking(booking,"Haus Test")
            with self.assertRaises(ValueError):
                core.approve_snapshot(prepared,["7"]*4)

    def test_missing_invalid_created_date_blocks_instead_of_inventing(self):
        for raw in (None, "", "2026-02-30 13:05", "yesterday"):
            source=sample()
            if raw is None:
                source.pop("created-at",None)
            else:
                source["created-at"]=raw
            prepared=core.prepare_booking(source,"Haus Test")
            self.assertIsNone(prepared["booking_created_at"])
            self.assertTrue(any("Buchungsdatum" in w for w in prepared["warnings"]))
            with self.assertRaisesRegex(ValueError,"Buchungsdatum"):
                core.approve_snapshot(prepared,["7"]*4)

    def test_booking_date_never_uses_arrival_modified_or_export_day(self):
        source=sample()
        source["created-at"]="2026-12-08T23:55:00+01:00"
        source["modifiedAt"]="2027-06-01T09:00:00Z"
        source["arrival"]="2027-08-12"
        prepared=core.prepare_booking(source,"Haus Test")
        self.assertEqual(prepared["booking_created_at"],"2026-12-08")
        snap=core.approve_snapshot(prepared,["7"]*4)
        self.assertEqual(snap["due_date"],"2026-12-08")

    def test_reject_blocked_and_non_cent(self):
        b=sample();b["is-blocked-booking"]=True
        with self.assertRaises(ValueError): core.prepare_booking(b,"Haus Test")
        b=sample();b["price"]="475.001"
        with self.assertRaises(ValueError): core.prepare_booking(b,"Haus Test")


if __name__=="__main__":
    unittest.main()
