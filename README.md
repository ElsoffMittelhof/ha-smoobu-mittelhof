# Smoobu Workflow for Home Assistant

Custom Home Assistant integration for Smoobu reservations, booking calendars, laundry approval workflows, NUKI guest-code emails, and optional IT.NRW monthly statistics.

Current public version: **0.3.0**.

> Technical note: the integration domain remains `smoobu_mittelhof` for compatibility with installations from the private pre-release phase. The public integration contains no property-specific apartment IDs, email addresses, Home Assistant entity IDs, API credentials, or SMTP credentials.

## Privacy model

Installation-specific values are stored only in Home Assistant:

- Smoobu API key and secret
- Smoobu apartment IDs and accommodation names
- mobile notify service
- laundry recipient
- SMTP server, username, sender, and password
- local laundry configuration and editable email templates

The repository contains only generic examples.

## Installation with HACS

Add this repository as a custom HACS integration repository:

`https://github.com/ElsoffMittelhof/ha-smoobu-mittelhof`

Then install **Smoobu Workflow**, restart Home Assistant, and add the integration under **Settings → Devices & services**.

## Initial setup

1. Enter the Smoobu API key and secret.
2. The integration searches reservations and pre-fills discovered accommodations.
3. Confirm the accommodation list in the form `apartment_id=Name`, one line per accommodation.
4. Configure notifications, laundry, NUKI and SMTP under the integration options.

Example mapping:

```text
123456=Apartment A
234567=Apartment B
```

## Upgrade from private v0.2.x

v0.3.0 migrates existing installations without embedding private IDs in the public source code. It first recovers apartment IDs/names from the existing Home Assistant workflow store and, if needed, from Smoobu reservations. The legacy external configuration directory `/config/smoobu_mittelhof/` is preserved during migration.

After the first successful start, open the integration options and verify the accommodation mapping.

## External files

For new installations the default path is:

```text
/config/smoobu_workflow/
├── laundry.yaml
└── templates/
    ├── laundry_order.yaml
    ├── laundry_change.yaml
    ├── nuki_de.yaml
    └── nuki_en.yaml
```

Copy and customize the generic examples from `examples/`. These local files are intentionally not managed by HACS updates.

## Timeline card

The integration serves the included card at:

```text
/smoobu_mittelhof/frontend/smoobu-timeline-card.js
```

Add it once as a JavaScript module under **Settings → Dashboards → Resources**. Configure the card with your own accommodation names and calendar entity IDs.

## Security

- NUKI PINs are not stored in the Home Assistant workflow store.
- NUKI PINs are not published as entity attributes.
- Guest email and NUKI PIN are fetched fresh before sending.
- Laundry emails do not include guest names.
- Credentials are never part of the repository examples.

## License

MIT
