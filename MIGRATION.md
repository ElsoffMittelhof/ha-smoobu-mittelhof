# Migration from v0.2.x

v0.3.0 removes private installation mapping from the integration source.

During upgrade, Home Assistant attempts to recover the accommodation list from the existing workflow store and from Smoobu reservations. It also keeps the old external configuration directory so existing laundry/templates continue to work.

After restarting Home Assistant:

1. Open **Settings → Devices & services → Smoobu Workflow → Configure**.
2. Verify the `apartment_id=Name` mapping.
3. Verify notify, laundry, NUKI and SMTP settings.
4. Run a test notification before relying on the workflows.

No API keys, SMTP passwords or NUKI PINs are migrated to GitHub.
