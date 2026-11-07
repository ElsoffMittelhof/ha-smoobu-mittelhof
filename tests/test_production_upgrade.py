"""Non-network production-upgrade contract checks (0.6.8 -> 0.7.0).

Guard against accidentally changing local NUKI/laundry/SMTP options or
enabling guest PII syncing and guest-message sending on the first upgrade.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "custom_components" / "smoobu_mittelhof"


class TestProductionUpgradeSafety(unittest.TestCase):
    def test_manifest_release_and_domain_are_stable(self):
        manifest = json.loads((MODULES / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "smoobu_mittelhof")
        self.assertEqual(manifest["version"], "0.7.0")
        self.assertEqual(manifest.get("requirements"), [])

    def test_guest_portal_and_guest_sends_are_opt_in_disabled(self):
        const = (MODULES / "const.py").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_GUEST_PORTAL_ENABLED = False', const)
        self.assertIn('DEFAULT_GUEST_MESSAGE_SEND_ENABLED = False', const)
        init = (MODULES / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('if runtime.guest_portal_enabled:', init)
        self.assertIn('if runtime.guest_portal_enabled:\n        runtime.guest_drafts = GuestDraftRepository(hass)', init)
        self.assertIn('if runtime.guest_portal_enabled:\n        runtime.guest_unsub = coordinator.async_add_listener(', init)
        self.assertIn('runtime.guest_message_send_enabled = bool(\n        runtime.guest_portal_enabled and', init)
        portal = (MODULES / "guest_portal.py").read_text(encoding="utf-8")
        self.assertIn('if not getattr(runtime, "guest_portal_enabled", False)', portal)
        self.assertIn("HTTPServiceUnavailable", portal)

    def test_options_flow_preserves_actual_existing_values(self):
        source = (MODULES / "config_flow.py").read_text(encoding="utf-8")
        flow = source.split("class SmoobuOptionsFlow(", 1)[1]
        all_option_lines = [
            line.strip() for line in flow.splitlines()
            if "vol.Required(CONF_" in line or "vol.Optional(CONF_" in line
        ]
        self.assertGreater(len(all_option_lines), 30)
        exceptions = {'CONF_HOUSES'}  # current_houses is separately recovered from config
        for line in all_option_lines:
            field = re.search(r'vol\.(?:Required|Optional)\((CONF_[A-Z_]+)', line)
            self.assertIsNotNone(field, line)
            if field.group(1) in exceptions:
                self.assertIn("default=current_houses", line)
            else:
                self.assertIn(f"default=options.get({field.group(1)},", line, line)

    def test_local_config_dir_is_never_forcibly_migrated(self):
        init = (MODULES / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('options[CONF_CONFIG_DIRECTORY] = "smoobu_mittelhof"', init)
        self.assertIn('entry.options.get(CONF_CONFIG_DIRECTORY, DEFAULT_CONFIG_DIRECTORY)', init)
        self.assertIn('config_dir / "laundry.yaml"', init)
        self.assertIn('config_dir / "templates"', init)

    def test_never_auto_send_guest_messages_from_new_background_work(self):
        guest = (MODULES / "guest_portal.py").read_text(encoding="utf-8")
        init = (MODULES / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("send_message_to_guest", init)
        self.assertIn("guest_message_send_enabled", guest)
        self.assertIn("claim_send", guest)
        self.assertIn("mark_unknown", guest)
        # Existing operational modules are not imported by the invoice portal.
        invoice_portal = (MODULES / "invoice_portal.py").read_text(encoding="utf-8")
        self.assertNotIn("from .workflow", invoice_portal)
        self.assertNotIn("from .laundry", invoice_portal)

    def test_invoice_service_only_optional_local_config(self):
        portal = (MODULES / "invoice_portal.py").read_text(encoding="utf-8")
        self.assertIn('if not filename.exists():\n        return None', portal)
        self.assertIn("if not isinstance(obj, dict) or obj.get(\"enabled\") is not True", portal)
        self.assertIn('filename.stat().st_mode & 0o077', portal)
        self.assertNotIn("invoice_issued = True", portal)


if __name__ == "__main__":
    unittest.main()
