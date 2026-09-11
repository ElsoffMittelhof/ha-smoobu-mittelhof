# Changelog

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
