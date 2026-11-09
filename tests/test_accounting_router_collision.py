"""Regression against the HA POST router shadowing accounting with guest action."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]/"custom_components/smoobu_mittelhof"


class RoutesTest(unittest.TestCase):
    def test_accounting_post_is_not_a_guest_message_action(self):
        guest=(ROOT/"guest_portal.py").read_text()
        accounting=(ROOT/"accounting_portal.py").read_text()
        init=(ROOT/"__init__.py").read_text()

        action=re.search(r'class GuestMessageActionView\(HomeAssistantView\):\s+url\s*=\s*"([^"]+)"',guest)
        self.assertIsNotNone(action)
        self.assertIn("{action:regenerate|approve|send}",action.group(1))
        self.assertNotIn('"{action}"',action.group(1))
        self.assertEqual(
            accounting.count('url = "/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting"'),
            1,
        )
        view=re.search(r'class AccountingBookingView\(HomeAssistantView\):(.+?)(?=\nclass |\Z)',accounting,re.S)
        self.assertIsNotNone(view)
        self.assertIn("async def get(",view.group(1))
        self.assertIn("async def post(",view.group(1))
        self.assertLess(init.index("register_accounting_views(hass)"),
                        init.index("register_guest_views(hass)"))
        self.assertIn('raise web.HTTPNotFound()',guest)

    def test_regex_only_catches_authorized_message_actions(self):
        pattern=r"^/api/smoobu_mittelhof/guest/v1/bookings/[^/]+/(regenerate|approve|send)$"
        for suffix in ("regenerate","approve","send"):
            self.assertRegex(f"/api/smoobu_mittelhof/guest/v1/bookings/123/{suffix}",pattern)
        for suffix in ("accounting","draft","invoice-export","preview-request"):
            self.assertIsNone(re.match(pattern,f"/api/smoobu_mittelhof/guest/v1/bookings/123/{suffix}"))


if __name__=="__main__":
    unittest.main()
