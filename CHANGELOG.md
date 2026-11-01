# Changelog

## 0.6.5 — 2026-11-01

- Add idempotent service `smoobu_mittelhof.record_clean_laundry_receipt` for physical access of clean linen without a linked purchase order. An identical portal receipt ID can never increase stock twice; a conflicting reuse is rejected.
- Keep dirty linen separate from available clean inventory. Preserve existing order-linked delivery and physical stocktaking actions.
- Re-evaluate the existing article-stock notification workflow after receipts; per-item threshold remains 12 for linen articles and 2 for bath mats (targets 24 / 6).
- Requires updated service portal and Node-RED import for staff inventory/receipts.


## 0.6.4 — 2026-11-01

- Provide the Smoobu guest display name (no contact or access details) for the authenticated housekeeping portal via the HA status sensor; names are read live and not persisted in laundry history.
- Expose `no_laundry_change` for confirmed checkouts whose actual use is 0 sets and 0 individual articles.
- Add regression coverage confirming a zero-article checkout is marked complete without changing any stock quantities.
- Node-RED and portal require their corresponding updates for end-to-end behaviour; do not enable the outbound processing flow before reviewing the existing queued Haus 15 job.


## 0.6.3 — 2026-11-01

- Homepage / Uberspace is the primary interface for staff laundry operations. Home Assistant stays the authoritative store for Smoobu-linked bookings, six physical stock items, reorder proposals, deliveries, and inventory counts.
- Restores current Smoobu checkouts from November 1, 2026, instead of the previous December-only pilot gate. Migrates the previously stored December cutoff to the active November setting. Older checkouts before the configured date remain archived, not deleted; currently valid bookings are reactivated.
- Adds sanitized `laundry_portal_bookings` sensor attribute with booking ID, house, arrival/departure, guest count and workflow state. Guest names and contact details are never sent to the staff portal.
- HA laundry card becomes read-only dashboard plus local simulation; actual work is performed using the authenticated portal and an outbound-only Node-RED agent.
- Adds privacy-preserving status sync, booking-specific consumption and administrator inventory commands on the homepage.


## 0.6.2 — 2026-11-01

- Mittelhof: Start der tatsächlichen Wäscheerfassung ist als Optionswert **2026-12-01** eingestellt und kann in den Integrationsoptionen verändert werden.
- Noch offene oder geplante Reinigungen **vor dem Erfassungsbeginn** werden als `excluded_before_start` archiviert, nicht gelöscht. Historische bestätigte Buchungen und bestehende Artikelbestände bleiben unverändert.
- HA blockiert echte Verbrauchsbuchungen bis zum Startdatum, einschließlich direkter Service-Aufrufe. Bis dahin ist ausschließlich die Simulation erlaubt.
- Neue lokale Wäschesimulation in der HA-Reinigungskarte: Sets und sechs Einzelartikel, hypothetischer Bestand und Nachbestellvorschlag ohne Dienstaufruf und ohne Speichern.
- Rein berechnende Funktionen und Regressionstests für den Dezember-Stichtag und die Simulation ergänzt.
- Das Mitarbeiterportal bietet denselben Trockenlauf ohne Netzwerkaktion und sperrt produktive Verbrauchserfassungen serverseitig bis zum 1. Dezember 2026.


## 0.6.1 — 2026-11-01

- Sicherheitskorrektur: Ohne explizite Buchungs-ID wird ausschließlich eine offene Reinigung bestätigt; bereits bestätigte Verbräuche werden nicht unbemerkt überschrieben.
- Gezielte Korrekturen benötigen die Buchungs-ID.
- Regressionstests für wiederholte Erfassungen und Buchungszuordnung ergänzt.


## 0.6.0 — 2026-10-31

- Six separate article inventories for pillowcases, flat sheets, fitted sheets, bath towels, hand towels, and bath mats, migrated from the existing 24/6 stock without clearing histories.
- Cleaner booking combines optional complete sets and extra item quantities, with corrections and negative-stock prevention.
- Low-stock article-specific reorder proposals (12 per set item, 2 mats); administrator approves the existing email workflow.
- Supplier email creates an outstanding delivery, never credits stock immediately. Partial/full physical receipts update balances exactly once.
- New HA actions for individual physical stocktake and confirmed delivery; dedicated local Lovelace card and secure service portal integration.


## 0.5.0 — 2026-10-31

- Defines a complete linen set as pillowcase, flat sheet (Laken), fitted sheet, bath towel and hand towel; bath mats are explicitly separate.
- Adds initial tracked stock of 6 bath mats alongside the existing 24 sets without deleting existing consumption/order history.
- Adds optional `mats` consumption (0–6) and independent stock/correction/replenishment accounting.
- Adds Home Assistant action `smoobu_mittelhof.reconcile_laundry_stock` for deliberate physical stocktake corrections of both balances.
- Updates the laundry product example and stock-order product-name inference; local `laundry.yaml` must be reviewed separately (not overwritten by HACS).
- The usual reorder threshold remains based on consumed sets. Bath mats per order remain independently configurable.


## 0.4.1 — 2026-10-03

- IT.NRW statistics now use the real calendar month by default instead of the legacy Node-RED-compatible shifted period.
- A stay from 27.09. to 02.10. now correctly counts the night 01.10.→02.10. in October.
- Selected-month generation and the dashboard statistics button now use `calendar_month`.
- The legacy `node_red_compatible` mode remains available only when explicitly requested.
- Adds a regression test for stays crossing a month boundary.

## 0.4.0 — 2026-09-19

- Adds selectable laundry ordering modes: the existing per-departure workflow remains available, and the new stock/set mode tracks an initial clean-linen stock.
- Stock mode defaults to 24 complete sets, triggers replenishment after 12 consumed sets, and orders 12 complete sets plus 3 bath mats.
- Cleaner-confirmed consumption is stored per checkout; suggested values are 2 sets for 1–2 guests and 4 sets for 3+ guests.
- Cleaner confirmations can be corrected until the next replenishment order is sent.
- Adds the Home Assistant action `smoobu_mittelhof.record_laundry_consumption`.
- Stock mode reuses the existing laundry mail template and supports an explicit `stock_order` product mapping in `laundry.yaml`.
- Adds persistent stock diagnostics and stock-accounting CI coverage.

## 0.3.2 — 2026-09-11

- Timeline bars now use half-day geometry: arrival and departure boundaries are rendered at the centre of their calendar date.
- Consecutive reservations and blocked periods therefore meet at the same midday boundary instead of occupying whole-day columns.
- Example: a reservation ending on 03.10. ends at the middle of 03.10.; a block from 03.10. to 04.10. runs from midday 03.10. to midday 04.10.

## 0.3.1 — 2026-09-11

- Smoobu blocked periods are included in the timeline data without changing laundry/NUKI workflow processing.
- Blocked periods are rendered as clearly labelled hatched bars with a dedicated legend entry and detail status.
- Timeline status now separates regular bookings and blocked periods.

## 0.3.0

First public release.

- Removed installation-specific Smoobu apartment IDs, email addresses, notify services, SMTP defaults and Home Assistant entity IDs from the public codebase.
- Accommodation mapping is now dynamic and editable in the config/options flow.
- Existing v0.2.x installations can recover their accommodation mapping from Home Assistant state and Smoobu during migration.
- Entity IDs are derived from configured accommodation names.
- Booking and statistics processing is restricted to configured accommodations.
- Generic examples replace installation-specific laundry and email templates.
