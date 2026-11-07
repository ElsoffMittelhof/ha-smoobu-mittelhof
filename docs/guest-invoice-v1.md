# Guest communication and invoice drafts — experimental V1

Status: **feature branch / review only**. Do not release or enable against real guests until manually tested. No ZUGFeRD PDF generation, invoice issuance or PDF upload is included in this increment.

## Implemented

- Use the already configured HMAC client for:
  - \`GET /api/threads\` (first inbox page, up to 100)
  - \`GET /api/reservations/{id}?includePriceElements=true\`
  - \`GET /api/reservations/{id}/messages\` (all pages, max 100)
  - \`POST /api/reservations/{id}/messages/send-message-to-guest\` ONLY after two explicit admin actions.
- Prepare an editable message and invoice **draft** for nonblocked bookings belonging to configured houses, up to 730 days in the future and 30 days in the past, at startup, on coordinator refresh, and independently every 30 minutes.
- Drafts persist in an independent Home Assistant Store; message conversations themselves are read live and never copied to state attributes.
- Edit billing name/address, line items (including discounts), total, amount already paid, payment confirmation, due date, payment method, explanatory/steering text and message subject/body.
- Show a branded **non-issued** invoice preview with itemized gross totals and invoice preflight consistency checks (missing address, gross/line mismatch, pending tax review, payment uncertainty).
- Compose booking messages in German or English; admin can explicitly regenerate from edited payment flow and verified amounts (never auto-send).
- Keep guest sending **disabled server-side by default**. Explicitly enable it via integration options `guest_message_send_enabled` only in the controlled test environment. A message still requires individual approval and a separate Send click.
- Require an admin account to view, edit, approve or send. Editing invalidates previous message approval.
- Check a source booking fingerprint before edits, approval and send; stale data requires review again.
- Before a send, persist \`sending\`. If Smoobu does not clearly confirm acceptance, record \`delivery_unknown\`, do not retry automatically, and manually check Smoobu to avoid duplicates.
- Keep existing NUKI and laundry behavior unchanged.

## Not yet implemented / intentionally blocked

- Final ZUGFeRD/EN 16931 XML, PDF/A-3 rendering, validator, final tax calculations, invoice number allocation, immutable invoice ledger, correction/credit notes, archival policy and actual invoice send.
- Template import from Smoobu and advanced per-channel message variants.
- Multi-page inbox navigation beyond 100 conversations.
- Smoobu invoice upload, invoice PDF attachments over Smoobu's messaging API, guaranteed guest delivery.
- Full automated reconciliation of Booking.com/Airbnb/Naturhäuschen/TOMAS payments; channel name is NOT proof of guest payment.
- Admin-only action does not constitute role-based audit/authentication for a separate multi-user invoicing system; plan audit/retention and tax verification before issuing.
- Guest conversations are currently retrieved synchronously when opening a booking.
- In production, keep `guest_message_send_enabled: false` until portal-specific sending behavior has been verified with safe test bookings.
- Smoobu source changes remain flagged as stale during automatic synchronization, and only an explicit admin acknowledgement accepts the new source fingerprint. **The original invoice line edits are NOT overwritten**; compare them with the latest Smoobu figures afterwards.
- Only the first page of the Smoobu inbox is displayed; the message history of each selected booking is paged in full (max 100 pages).
- The seller profile and VAT regime are NOT read automatically from the homepage imprint. The private project contains a commented draft `invoice/issuer.example.yaml`, which requires manual legal and tax confirmation.

## Installation on a disposable test Home Assistant only

1. Install the **feature branch** into an isolated development Home Assistant, not a production upgrade; keep a full backup.
2. In HA dashboard resources add exactly one JS-module resource:
   \`/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=guest-v1-test\`
3. Add a Lovelace card:
   \`\`\`yaml
   type: custom:mittelhof-guest-card
   \`\`\`
4. For logo preview, copy your private brand image to:
   \`/config/www/smoobu_mittelhof/invoice-logo.png\`
   It is served at \`/local/smoobu_mittelhof/invoice-logo.png\`. The public integration intentionally does not ship your private logo.
5. As a Home Assistant administrator, read a real thread, prepare and **edit** a draft, save, and check that source changes invalidate approvals.
6. Keep the new integration option `guest_message_send_enabled` **false** for all normal installations. Only enable it for a designated safe test booking/guest, and disable it after test. Validate sending using a designated safe test booking/guest only. The Send button sends a plain text message through Smoobu, **not a PDF**. No automatic send is enabled.
7. Keep Smoobu's existing automatic guest templates enabled until replacements have been verified. Before activating overlapping HA templates, disable the corresponding Smoobu automation to prevent duplicate sends.

## Privacy and operations

\`/config/.storage/smoobu_mittelhof.guest_drafts\` contains personal data in invoice/message drafts and MUST NOT be committed, logged, exported as sensor attributes or put in InfluxDB. HA backups containing it need appropriate access and retention policies. Keep NUKI PINs out of drafts and invoices. Never use \`reset_all_workflow_state\` as a way to clean guest draft data.

## Testing

\`python tests/test_guest_finance.py\`, compile checks, \`node --check\` and existing hassfest/HACS CI. A real Smoobu sandbox test, browser visual test and accountant verification are required before deployment.

## Invoice release gates

A PDF that merely *looks* like an invoice is NOT a ZUGFeRD e-invoice. No final invoice is issued from this draft-only module.

The next invoice engine will use ZUGFeRD 2.5.2/EN16931 in PDF/A-3, including consistent XML and visual totals, logo, seller identity, tax categories, discounts, payment accounting and validation. Issuance must be blocked until all of the following are present:
- Confirmed legally correct seller identity and tax status (homepage imprint is a starting point only).
- Explicit recipient address, separate tax categories/line bases, and line/total reconciliation.
- Trustworthy payment evidence, no automatic paid status based on booking channel alone.
- Unique collision-safe invoice number and immutable ledger with corrective documents, never overwriting an issued invoice.
- PDF/A-3 and embedded XML extraction/EN16931 Schematron validation with a known-good validator such as Mustangproject, test vectors including mixed tax rates and cancellations.
- Full privacy/backup, retention, concurrency, availability, and real HA/UI testing before release.


- The 30-minute synchronization is serialized and runs outside startup-critical Wäsche/NUKI setup. Smoobu source-difference acknowledgement is explicit; pending edits remain preserved.
