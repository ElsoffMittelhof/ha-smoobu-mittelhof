"""Contract smoke checks for separate admin guest inbox/bookings/invoices views.

Works without Home Assistant runtime and without touching real guest data.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components/smoobu_mittelhof"


class TestGuestCenterContract(unittest.TestCase):
    def test_only_admin_views_for_bookings_invoices_import_and_messages(self):
        txt=(ROOT/"guest_portal.py").read_text()
        for url in ('/guest/v1/threads','/guest/v1/search-bookings',
                    '/guest/v1/invoice-drafts','/guest/v1/bookings/{booking_id}/import-smoobu'):
            self.assertIn(url,txt)
        for name in ('GuestBookingSearchView','GuestInvoiceDraftsView','GuestImportSmoobuView'):
            fragment=txt.split('class '+name+'(',1)[1].split('\n\nclass ',1)[0]
            self.assertIn('requires_auth = True',fragment)
            self.assertIn('_require_admin(request)',fragment)
        self.assertIn('await runtime.guest_inbox.mark_opened',txt)
        self.assertIn('class GuestInboxState:',txt)
        self.assertIn('message_scan_limit_reached',txt)

    def test_date_filter_is_limited_and_existing_drafts_read_only(self):
        txt=(ROOT/"guest_portal.py").read_text()
        self.assertIn('date.fromisoformat(start)',txt)
        self.assertIn('730:',txt)
        self.assertIn('issued_invoices_supported": False',txt)
        self.assertIn('source_fingerprint',txt)
        self.assertIn('confirm_replace',txt)
        self.assertIn('_invoice_source_preflight',txt)

    def test_frontend_has_separate_views_and_timeline_deep_link(self):
        text=(ROOT/"frontend/mittelhof-guest-card.js").read_text()
        for val in ('"inbox"','"bookings"','"invoices"','search-bookings',
                    'invoice-drafts','import-smoobu','URLSearchParams(window.location.search)'):
            self.assertIn(val,text)
        timeline=(ROOT/"frontend/smoobu-timeline-card.js").read_text()
        self.assertIn('guest_dashboard_path',timeline)
        self.assertIn('Gespräch / Rechnungsentwurf öffnen',timeline)
        self.assertIn('encodeURIComponent(id)',timeline)

    def test_cold_dashboard_start_serializes_view_fetch_and_deep_link(self):
        text=(ROOT/"frontend/mittelhof-guest-card.js").read_text()
        setter=text.split("  set hass(value) {",1)[1].split("  getCardSize()",1)[0]
        self.assertIn("void this._initialize(bid);",setter)
        self.assertIn("await this._loadInbox();",setter)
        self.assertIn('if (this._tab === "bookings") await this._loadBookings();',setter)
        self.assertIn('else if (this._tab === "invoices") await this._loadInvoiceDrafts();',setter)
        self.assertIn("if (/^\\d{1,18}$/.test(bid)) await this._open(bid);",setter)
        self.assertNotIn("this._loadInbox();\n      if (this._tab",setter)

    def test_guest_portal_still_opt_in_with_guest_send_off(self):
        init=(ROOT/"__init__.py").read_text()
        self.assertIn('if runtime.guest_portal_enabled:',init)
        const=(ROOT/"const.py").read_text()
        self.assertIn('DEFAULT_GUEST_MESSAGE_SEND_ENABLED = False',const)


if __name__=="__main__":
    unittest.main()
