"""Offline safety contracts for Lexware-L-only admin accounting export."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components/smoobu_mittelhof"

class Contracts(unittest.TestCase):
    def test_manifest_and_disabled_guest_default(self):
        m=json.loads((ROOT/"manifest.json").read_text())
        self.assertEqual(m["version"],"0.7.9")
        const=(ROOT/"const.py").read_text()
        self.assertIn("DEFAULT_GUEST_PORTAL_ENABLED = False",const)
        self.assertIn("DEFAULT_GUEST_MESSAGE_SEND_ENABLED = False",const)
        init=(ROOT/"__init__.py").read_text()
        self.assertIn("if runtime.guest_portal_enabled:",init)
        self.assertIn("runtime.accounting = AccountingRepository(hass)",init)

    def test_admin_guard_for_all_accounting_routes(self):
        s=(ROOT/"accounting_portal.py").read_text()
        for name in ("AccountingListView","AccountingBookingView","AccountingPdfView",
                     "AccountingUploadView","AccountingBundleView","AccountingInvoiceReferenceView"):
            chunk=s.split("class "+name+"(",1)[1].split("\nclass ",1)[0]
            self.assertIn("requires_auth = True",chunk,name)
            self.assertIn("_accounting_runtime(request)",chunk,name)
        self.assertIn("_require_admin(request)",s)
        self.assertIn("source_fingerprint",s)
        self.assertIn("confirm_tax_review",s)
        self.assertIn("confirm_manual_upload",s)

    def test_accounting_fetches_booking_only_once_per_request(self):
        import ast
        tree=ast.parse((ROOT/"accounting_portal.py").read_text())
        current=next(node for node in tree.body
                     if isinstance(node,ast.AsyncFunctionDef) and node.name=="_current_source")
        fetches=[node for node in ast.walk(current)
                 if isinstance(node,ast.Call) and
                 isinstance(node.func,ast.Attribute) and node.func.attr=="get_booking"]
        self.assertEqual(fetches, [], "No redundant Smoobu request after _checked_booking")
        checks=[node for node in ast.walk(current)
                if isinstance(node,ast.Call) and
                isinstance(node.func,ast.Name) and node.func.id=="_checked_booking"]
        self.assertEqual(len(checks),1)

    def test_no_automatic_guest_mail_or_lexware_write(self):
        s=(ROOT/"accounting_portal.py").read_text()
        self.assertNotIn("send_message_to_guest(",s)
        self.assertNotIn("lexware.de",s)
        self.assertNotIn("invoice_issued = True",s)
        self.assertIn("lexware_api_enabled",s)
        self.assertIn("False",s)
        core=(ROOT/"accounting_core.py").read_text()
        self.assertIn("internal_booking_record",core)
        self.assertIn("KEINE Rechnung",core)

if __name__=="__main__":
    unittest.main()
