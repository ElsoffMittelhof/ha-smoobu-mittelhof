"""Synthetic screenshot regression for Smoobu detailed price import and ISO address."""
import importlib.util
from pathlib import Path
import unittest

source=Path(__file__).resolve().parents[1]/"custom_components/smoobu_mittelhof/smoobu_sources.py"
spec=importlib.util.spec_from_file_location("smoobu_sources_test",source)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def screenshot_booking():
    return {
        "id":1234,"arrival":"2026-12-22","departure":"2026-12-25",
        "guest-name":"Test Gast","price":475,
        "priceElements":[
            {"id":1,"type":"basePrice","name":"Base Price","amount":355,"currencyCode":"EUR","sortOrder":1},
            {"id":2,"type":"cleaningFee","name":"Reinigungsgebühr","amount":55,"currencyCode":"EUR","sortOrder":2},
            {"id":3,"type":"addon","name":"Haustier-Gebühr","amount":35,"currencyCode":"EUR","sortOrder":3},
            {"id":4,"type":"addon","name":"Gebühr für zusätzliche Gäste","amount":30,"currencyCode":"EUR","sortOrder":4},
        ]
    }

class TestSmoobuSources(unittest.TestCase):
    def test_four_screenshot_positions_and_total(self):
        rows,warnings=module.source_price_lines(screenshot_booking())
        self.assertEqual(len(rows),4)
        self.assertEqual([r["position_type"] for r in rows],["rent","cleaning","dog","extra_person"])
        self.assertEqual([r["gross"] for r in rows],["355.00","55.00","35.00","30.00"])
        self.assertEqual(sum(__import__("decimal").Decimal(r["gross"]) for r in rows),475)
        self.assertEqual([r["tax_rate"] for r in rows],["7"]*4)
        self.assertEqual(warnings,[])

    def test_smoobu_source_mismatch_remains_visible(self):
        b=screenshot_booking()
        b["price"]=470
        rows,warnings=module.source_price_lines(b)
        self.assertEqual(len(rows),4)
        self.assertTrue(any("weicht von Buchungsbetrag" in msg for msg in warnings))

    def test_unknown_addon_never_assumes_seven_percent(self):
        b=screenshot_booking()
        b["price"]=485
        b["priceElements"].append({"id":5,"type":"addon","name":"Parkplatz","amount":10})
        rows,warnings=module.source_price_lines(b)
        unknown=next(row for row in rows if row["description"]=="Parkplatz")
        self.assertEqual(unknown["position_type"],"")
        self.assertEqual(unknown["tax_rate"],"")
        self.assertTrue(any("Unbekannte" in x for x in warnings))

    def test_no_source_details_keeps_total_but_does_not_invent_types(self):
        b=screenshot_booking()
        b.pop("priceElements")
        rows,warnings=module.source_price_lines(b)
        self.assertEqual(rows[0]["gross"],"475.00")
        self.assertEqual(rows[0]["position_type"],"")
        self.assertTrue(warnings)

    def test_guest_address_country_mapping_and_unknown_country(self):
        booking=screenshot_booking()
        guest={"companyName":"","address":{
            "street":"Musterstr. 5","postalCode":"57319","city":"Bad Berleburg","country":"Germany"}}
        address=module.guest_invoice_address(booking,guest)
        self.assertEqual(address["recipient_country"],"DE")
        self.assertEqual(address["recipient_street"],"Musterstr. 5")
        self.assertEqual(address["recipient_postal_code"],"57319")
        self.assertEqual(module.iso_country("Nederland"),"")
        self.assertEqual(module.iso_country("Netherlands"),"NL")
        self.assertEqual(module.iso_country("XX"),"")

    def test_included_price_child_not_double_counted(self):
        b=screenshot_booking()
        b["priceElements"].append({
            "id":5,"type":"addon","name":"Inklusive Extras","amount":15,"priceIncludedInId":1})
        rows,_=module.source_price_lines(b)
        self.assertEqual(len(rows),4)

if __name__=="__main__":
    unittest.main()
