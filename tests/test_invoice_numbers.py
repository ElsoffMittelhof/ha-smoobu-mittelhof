"""Number proposals are PURE read-only helpers; no invoice allocation in HA."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "custom_components" / "smoobu_mittelhof" / "invoice_numbers.py"
spec = importlib.util.spec_from_file_location("invoice_numbers", source)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class TestInvoiceNumberPreview(unittest.TestCase):
    def test_houses_and_dates(self):
        self.assertEqual(mod.planned_number("Haus 13", "2026-12-10"), "1320261210")
        self.assertEqual(mod.planned_number("Ferienhaus 14", "2027-01-05"), "1420270105")
        self.assertEqual(mod.planned_number("Mittelhof Haus 15", "2027-07-18"), "1520270718")
        self.assertEqual(mod.planned_number("15", "2027-07-18"), "1520270718")

    def test_ambiguous_names_fail_closed(self):
        for name in ("Haus 16", "Haus 13 und 14", "Haus 113", "Apartment", "Straße 13", ""):
            with self.subTest(name=name):
                self.assertIsNone(mod.planned_number(name, "2027-01-01"))
        self.assertIsNone(mod.planned_number("Haus 13", "2027-02-29"))
        self.assertIsNone(mod.planned_number("Haus 13", "27.02.2027"))


if __name__ == "__main__":
    unittest.main()
