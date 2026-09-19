# Changelog

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
