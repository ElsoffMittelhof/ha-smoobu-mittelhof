# Changelog

## 0.3.1

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
