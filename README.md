# Smoobu Workflow for Home Assistant

Custom Home Assistant integration for Smoobu reservations, booking calendars, laundry approval workflows, NUKI guest-code emails, and optional IT.NRW monthly statistics.

Current public version: **0.5.0**.

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


## Laundry ordering modes

The integration supports two selectable laundry workflows:

- **Per departure** — keeps the established behaviour and creates an approval request for the configured laundry quantities of upcoming checkouts.
- **Stock / sets** — tracks a clean-linen stock and asks for cleaner confirmation of the actual sets used after checkout.

Stock mode defaults to:

```text
Initial stock:       24 complete sets
Initial bath mats:   6 (separate items)
Reorder threshold:   12 consumed sets
Reorder quantity:    12 complete sets
Bath mats per order: 3

Suggested use:
1 guest  = 2 sets
2 guests = 2 sets
3+ guests = 4 sets
```

A complete set for Mittelhof consists of **one pillowcase, one flat sheet (Laken), one fitted sheet (Spannbetttuch), one bath towel and one regular hand towel**. **Bath mats are counted independently** and are not included in the set.

The cleaner records actual use with the Home Assistant action:

```text
smoobu_mittelhof.record_laundry_consumption
```

If no booking ID is supplied, the action uses the oldest open checkout for the selected accommodation. The latest confirmation can be corrected until a replenishment order has been sent.

For stock mode, add an explicit mapping to the local `laundry.yaml` where possible:

```yaml
stock_order:
  set_products:
    flat_sheet: 1
    fitted_sheet: 1
    pillowcase: 1
    towel: 1
    bath_towel: 1
  bath_mat_product: bath_mat
```

**Upgrade 0.4.1 → 0.5.0**: Previous consumption/order histories and available set counts remain unchanged. Six bath mats are initialized once on upgrade if the old state did not track them. In Home Assistant, configure **Wäschebestellmodus: Lagerbestand / Sets**, initial stock 24 sets and 6 bath mats. To set a physically verified current count **without resetting history**, deliberately execute the new action:

```yaml
action: smoobu_mittelhof.reconcile_laundry_stock
data:
  sets: 24
  mats: 6
```

**Do not execute the inventory correction during a read-only integration test**; it is a writing action. It should be run exactly once after verifying the physical count and the current HA stock values.

**New consumption input**: the existing action accepts an additional `mats` field (0–6, default 0), separately from `sets`. The existing booking correction rules remain in force; entering a correction must include the intended complete mat count, otherwise the default 0 is used. Orders still follow the previously configured set threshold and add the separately configured bath mat quantity. The integration currently considers an emailed reorder as already replenished, as in v0.4.1; verify actual deliveries manually.

**Important for existing local laundry.yaml:** the actual `/config/smoobu_workflow/laundry.yaml` (or existing legacy configuration folder) is *not* updated automatically by HACS. Adjust `stock_order.set_products` to match your local product keys for Laken and Spannbetttuch, and verify the actual laundry prices. If the old config contains `duvet_cover`, do not silently substitute that product for `flat_sheet`; add/correct the local product catalog explicitly.


The public integration also includes a backwards-compatible name-based product inference for common German and English product names.


## Timeline card

The integration serves the included card at:

```text
/smoobu_mittelhof/frontend/smoobu-timeline-card.js
```

Add it once as a JavaScript module under **Settings → Dashboards → Resources**. Configure the card with your own accommodation names and calendar entity IDs. Blocked Smoobu periods are displayed separately with a hatched `Geblockt` style. Arrival and departure dates use a midday boundary, so consecutive reservations and blocked periods meet in the middle of their shared calendar date.

## IT.NRW statistics

Monthly reporting uses the actual calendar month by default. Overnight stays are attributed by the night they belong to: for example, a stay from 27 September to 2 October contributes the night from 1 October to 2 October to the October statistics.

The former `node_red_compatible` period remains available as an explicit legacy mode, but dashboard/selected-month generation uses `calendar_month`.

## Security

- NUKI PINs are not stored in the Home Assistant workflow store.
- NUKI PINs are not published as entity attributes.
- Guest email and NUKI PIN are fetched fresh before sending.
- Laundry emails do not include guest names.
- Credentials are never part of the repository examples.

## License

MIT
