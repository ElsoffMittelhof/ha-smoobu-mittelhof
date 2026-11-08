# Smoobu Workflow for Home Assistant

Custom Home Assistant integration for Smoobu reservations, booking calendars, laundry approval workflows, NUKI guest-code emails, and optional IT.NRW monthly statistics.

Current public version: **0.7.2**. Existing NUKI/laundry/IT.NRW workflows remain unchanged. The guest center and new Lexware-L accounting PDF exports are opt-in, admin-only; guest messages and invoice issuance remain disabled. Read [the v0.7.2 production and rollback guide](docs/release-0.7.2-production.md) before upgrading.

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

A complete set for Mittelhof consists of **one pillowcase, one flat sheet (Laken), one fitted sheet (Bettdeckenbezug), one bath towel and one regular hand towel**. **Bath mats are counted independently** and are not included in the set.

The cleaner records actual use with the Home Assistant action:

```text
smoobu_mittelhof.record_laundry_consumption
```

If no booking ID is supplied, the action uses the oldest open checkout for the selected accommodation. The latest confirmation can be corrected until a replenishment order has been sent.

For stock mode, add an explicit mapping to the local `laundry.yaml` where possible:

```yaml
stock_order:
  item_products:
    pillowcase: pillowcase
    flat_sheet: sheet
    duvet_cover: duvet_cover
    bath_towel: bath_towel
    towel: towel
    bath_mat: bath_mat
  set_products:
    sheet: 1
    duvet_cover: 1
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

**Important for existing local laundry.yaml:** the actual `/config/smoobu_workflow/laundry.yaml` (or existing legacy configuration folder) is *not* updated automatically by HACS. Adjust `stock_order.set_products` to match your local product keys for Laken and Bettdeckenbezug, and verify the actual laundry prices. For Benfer quote 168, `duvet_cover` maps to the supplier product `Systemwäsche Bezug`, while stock article `flat_sheet` maps to supplier product `sheet` (`Systemwäsche Laken`). Do not conflate these two.


The public integration also includes a backwards-compatible name-based product inference for common German and English product names.


## v0.6.0 – individual articles, set shortcut and confirmed deliveries

The six independent item keys are `pillowcase`, `flat_sheet`, `duvet_cover`,
`bath_towel`, `towel` and `bath_mat`. The first five form one complete set; the
bath mat is not included in sets. Existing users who have 24 complete sets and
6 bath mats will migrate without losing previous transactions.

A physical count of **24 sets + 6 bath mats** corresponds to counts of
`24` for each of the five set articles and `6` for `bath_mat`.
Already initialised stock is migrated from its **current** available balances,
not forcibly overwritten with the initial values.

The new HA card is available as a JavaScript module:

```text
/smoobu_mittelhof/frontend/mittelhof-laundry-card.js
```

Add this URL under **Settings → Dashboards → Resources** once, with resource
type **JavaScript module**, and add the card type
`custom:mittelhof-laundry-card` to the Reinigung dashboard (already included
in the Mittelhof dashboard repository).

Cleaning staff use the secure Mittelhof portal to choose **0–8 complete sets**
and/or extra individual article quantities. The underlying service also accepts
the equivalent structured data from local HA:

```yaml
action: smoobu_mittelhof.record_laundry_consumption
data:
  apartment_id: 123456
  sets: 2
  items:
    towel: 1
    bath_mat: 1
```

This would consume two of *each* set component, **one additional hand towel**
and **one bath mat**. Calling the consumption service makes a real stock
change and therefore is NOT suitable as a harmless connection test.

**Order lifecycle:** when any of the first five articles reaches **12 or fewer**
clean pieces or bath mats reach **2 or fewer**, an order suggestion is generated.
The suggested quantity raises only the low article(s) to the desired targets
(24 each, 6 bath mats). An administrator explicitly approves sending an email
using the existing `smoobu_mittelhof.laundry_command` service or HA card.
**Sending does NOT increase available stock.** Open deliveries appear in the HA
card and in the admin portal. Confirm the actual arrival (including partial
deliveries) using:

```yaml
action: smoobu_mittelhof.receive_laundry_delivery
data:
  request_id: laundry_items_REAL_REQUEST_ID
  items:
    towel: 5
    bath_mat: 2
```

Only the actually received quantities are credited. Replaying a fulfilled
delivery is blocked. Service-portal staff cannot send supplier emails or
perform inventory corrections.

**Administrator stocktake** requires all six physical counts:

```yaml
action: smoobu_mittelhof.reconcile_laundry_items
data:
  items:
    pillowcase: 24
    flat_sheet: 24
    duvet_cover: 24
    bath_towel: 24
    towel: 24
    bath_mat: 6
```

This overwrites the **available inventory**, not historical consumption or
supplier order records. Only run it after a physical count; do not use it for
the read-only Node-RED connection test.

The actual local `laundry.yaml` file is **never overwritten by HACS**. Before
sending any supplier order, ensure `stock_order.item_products` maps all six
keys to six **different real supplier products**, including distinct Laken
and Bettdeckenbezug. Confirm the original unit prices and supplier contact
details.

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


### Separate manual checks from v0.6.8

For NUKI-only checks call `smoobu_mittelhof.process_nuki_only` with `force_notify: true` if needed. For laundry-only restock alert checks use `smoobu_mittelhof.process_laundry_only` with `force_notify: true`. Both preserve stock authority in the staff portal and never send a supplier order without the existing approval action. The old combined service remains for compatibility with existing automations, but is intentionally not exposed on the dashboards.


## Lexware Office L – internal booking accounting PDFs (v0.7.2)

The optional administrator guest center offers a fourth **Buchhaltung** view via `custom:mittelhof-accounting-card`. Every active Smoobu booking can be reviewed for gross amount and tax lines, then exported as an internal accounting PDF or as part of a ZIP/CSV batch of up to 25 reviewed bookings. **Tax rates need explicit human review.** Smoobu payment flags are not used as confirmed payments. The document is **not** a guest invoice, does not send emails, and does not post to Lexware. After a manual Lexware L receipt upload an operator may mark the document as manually uploaded; altered source bookings block reused exports. For direct bookings where a guest invoice already documents the income, do not post the internal booking PDF as a second income. The future Lexware API adapter is not enabled on tariff L.

Register exactly one JS module resource `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.2` and use the complete separate private guest-dashboard YAML with its fourth `Buchhaltung` view. See [release 0.7.2 instructions](docs/release-0.7.2-production.md).
