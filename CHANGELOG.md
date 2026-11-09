# Changelog

## 0.7.8 — 2026-11-09 (Lexware Office L: Belegdatum und Fälligkeitsdatum)

- Der **interne Buchhaltungsbeleg** enthält nun ausdrücklich das ursprüngliche Smoobu-`created-at`-Buchungsdatum sowie `Belegdatum` und `Fälligkeitsdatum`, beide auf den Kalendertag der ursprünglichen Buchung gesetzt, nicht auf Erstellungs-/PDF-Export- oder Anreisedatum.
- Die beiden Lexware-Daten werden im Buchhaltungs-Dashboard vor PDF-Freigabe angezeigt und in jeden PDF-Beleg in deutscher Datumsschreibweise `TT.MM.JJJJ` geschrieben. Dies dient der manuellen Einnahmenbeleg-Erfassung in Lexware Office L, erzeugt **keine** zusätzliche Zahlungsaufforderung und sagt nichts über einen tatsächlichen Zahlungseingang oder dessen USt-Zuordnung aus.
- Smoobu `created-at` muss vollständig vorhanden und kalendergültig sein; bei fehlendem Datum wird **keines erfunden**, sondern die Belegfreigabe gesperrt. Keine Ableitung aus `modifiedAt`, Anreise oder aktuellem Datum.
- Die PDF-Daten stehen im revisionsgebundenen Buchhaltungs-Snapshot `mittelhof.accounting.v3` und unterliegen dem bestehenden Hash-/Dublettenschutz. Ältere, noch nicht verbuchte PDFs müssen vor einem erneuten Download geprüft werden; bereits als in Lexware hochgeladen markierte Belege werden nicht still geändert oder doppelt erfasst. ZIP-Export und manuelle Lexware-Uploadmarkierung prüfen die Datumsrevision.
- Zusätzliche Python-/Frontend-Regressionstests für originale Buchungsdaten, beide Lexware-Datumsfelder, PDF-Datumstext und fehlende/ungültige Buchungsdaten. Bestehende Wäsche-, NUKI-, IT.NRW-, Nachrichten- und Rechnungsabläufe bleiben unverändert.

## 0.7.7 — 2026-11-09 (Reproduzierter HTTP-404 beim Lexware-L-Belegfreigabe-POST)

- **Ursache anhand des echten Browser-Netzwerklogs und GitHub-Code identifiziert:** Die allgemeine Gästenachrichten-POST-Route `/bookings/{booking_id}/{action}` wurde vor dem spezifischen Buchhaltungs-POST `/bookings/{booking_id}/accounting` registriert. Der aiohttp-Router ordnete daher `accounting` irrtümlich als Nachrichtenaktion zu; `GuestMessageActionView.post()` antwortete bei unbekanntem `action` mit `web.HTTPNotFound()`, exakt dem im Browser sichtbaren `404: Not Found`. GET auf denselben Accounting-Pfad war hingegen erreichbar, da der Nachrichten-Handler nur POST anbietet.
- **Definitive Routenentflechtung:** Nachrichtenaktion-URL in `guest_portal.py` auf `{action:regenerate|approve|send}` begrenzt und die Registrierung der spezifischen Accounting-Views vor die Guest-Views verschoben. Damit kann der Nachrichten-Handler weder die Belegfreigabe noch spätere andere POST-API-Aktionen abfangen. Alle drei erlaubten Nachrichtenaktionen bleiben mit identischer URL erreichbar; tatsächlicher Gastversand weiterhin standardmäßig AUS.
- Offline-Regressionsvertrag `tests/test_accounting_router_collision.py` prüft das Muster, GET/POST der Buchhaltungs-View, Registrierung und Abgrenzung der Nachrichtenaktionen. Die bestehende JS-/Python-/HACS-/hassfest-Prüfsuite bleibt vollständige Release-Voraussetzung.
- Keine Änderungen an Buchhaltungspreisen, USt-Prüfung/7%-Vorbelegung, Lexware-Buchung, Gästenachrichten-Logik, Wäsche, NUKI, IT.NRW oder privaten Dashboarddateien. HA-Liveinstallation erfolgt erst nach Backup.

## 0.7.6 — 2026-11-09 (Lexware-L-Buchhaltung: Belegfreigabe HTTP 404)

- Bereinigt: `_current_source()` lud dieselbe Smoobu-Buchung **zweimal nacheinander**, obwohl `_checked_booking()` den vollständig geprüften Smoobu-Detaildatensatz bereits liefert. Die zusätzliche Netzabfrage entfällt, damit das Lesen und Freigeben eines Buchhaltungsbelegs nicht an unterschiedlichen Antworten zweier unmittelbar aufeinanderfolgender Smoobu-Anfragen scheitert.
- Bei HTTP-Fehlern in der Lexware-L-Karte werden nun die betroffene HTTP-Methode, der anonymisierte API-Pfad und die Fehlermeldung angezeigt. Ein HTTP 404 kann aus einem fehlenden Endpunkt **oder** einer Buchungssperre stammen; die Darstellung unterscheidet die Zieloperation, ohne Buchungs-ID oder Gastnamen zu protokollieren.
- Offline-Regression für nur einen Smoobu-Abruf pro Freigabeversuch und für aussagekräftige, anonymisierte POST-404-Diagnostik; in Validate und Release-CI aufgenommen.
- **Keine** Änderungen an Buchungspreisen, Steuersätzen, Gastrechnungsfreigaben, Gastnachrichten, Lexware-API, NUKI, Wäsche, IT.NRW oder den vollständigen privaten Dashboards. Ob der gemeldete 404 ausschließlich von der doppelten Smoobu-Abfrage kam, ist ohne Live-HTTP-Trace nicht abschließend nachgewiesen.

## 0.7.5 — 2026-11-09 (Lexware-L-USt-Vorbelegung und API-Fehlerdiagnose)

- Bei neu geöffneten Buchhaltungsbelegen stehen die Steuersatz-Dropdowns für alle derzeitigen Mittelhof-Gastpositionen auf **7 %** statt auf `USt prüfen`. Manuell andere geprüfte Werte (0/19 %) sowie zuvor gespeicherte Steuerentscheidungen bleiben möglich. Der bestehende ausdrückliche Freigabedialog und die serverseitige Steuer-/Bruttosummenprüfung bleiben erhalten. Die Einstellung ist eine betriebliche Vorbelegung, keine pauschale juristische Anerkennung jeder Sonderleistung.
- Strukturierte Home-Assistant-API-Fehler (`message`/verschachtelte Fehlerobjekte, HTTP-Status) werden in der Buchhaltungskarte als nachvollziehbarer Text ausgegeben statt `[object Object]`. Bei unerwarteten Fehlern wird zur HA-Protokollprüfung aufgefordert; persönliche Daten/Token werden nicht zusätzlich in die Logs geschrieben.
- Offline-Verhaltenstest `tests/test_accounting_vat_error_ui.js` für vier voreingestellte 7%-Positionen, Erhalt einer vorhandenen 19%-Prüfung und verständliche API-Fehlertexte; in Validate und Release-CI eingebunden. Keine Änderung an Smoobu-Zahlstatus, manueller Lexware-L-Uploadlogik, Gästeversand, NUKI, Wäsche oder IT.NRW.

## 0.7.4 — 2026-11-09 (Lexware-L-Buchhaltung: Datumsauswahl)

- Behoben: Datumsfelder **Von/Bis** auf der vierten Gäste-Dashboardseite sprangen bei Klick auf „Buchungen suchen“ auf den vorgegebenen Zeitraum zurück. Ursache: `_run()` renderte die Karte neu, bevor `_refresh()` die aktuell ausgewählten Eingabefelder gelesen hatte.
- Der Suchzeitraum wird nun **vor dem Re-Render** übernommen und bei weiteren UI-Aktionen erhalten. Ungültige Daten, rückwärts gerichtete Zeiträume und Suchfenster größer als 731 Tage werden vor API-Aufrufen abgefangen.
- Neuer Node-JS-Verhaltensregressionstest für die Datumsselektion und DOM-Re-Render; in CI und Release-Pipeline eingebunden.
- Ansonsten unveränderte Gästeverwaltung, Lexware-L-PDF-Erstellung, Rechnungsreferenzen, NUKI, Wäsche und IT.NRW. Keine automatische Gastkommunikation, keine Lexware-API und keine echte Rechnungsausstellung.

## 0.7.3 — 2026-11-08 (Gäste-Buchhaltung: Portalabrechnungen und Rechnungsreferenzen)

- Airbnb-Smoobu-Payload: Settlement-Positionen `Commission`, `Cancellation Host Fee` und `Cancellation Payout` fließen nicht in den Gastbruttobeleg ein. Der separat zu erfassende Provisionsbeleg wird **nicht** künstlich als Gästeumsatz erzeugt. `PASS_THROUGH_PET_FEE` und `Additional Guest Fee` werden als Gastpreispositionen erkannt. Preis-Summe muss nach Trennung exakt dem Smoobu-Buchungsbrutto entsprechen (Regression 355+55+35+30=475, statt falscher 1023,63 EUR).
- Buchhaltungsbelegpositionen vor der Freigabe einzeln auswählen/abwählen und Beschreibung/Brutto anpassen. Jede Steuerklasse explizit wählen; geprüfte Änderungen, ausgeschlossene Zeilen und Quell-Fingerprint in revisionsgebundenem Snapshot. Unausgeglichene Beträge bleiben gesperrt. Bereits hochgeladene Dokumente werden nie still ersetzt.
- Rechnung statt Buchungs-PDF: Direktbuchung/TOMAS werden zunächst als **Rechnung vorgesehen** gekennzeichnet. Bereits tatsächlich ausgestellte Gastrechnungen können mit externer Rechnungsreferenz erfasst werden, ohne eine zweite Lexware-Einnahme zu schaffen. Homepage-Zahlweg bleibt explizite manuelle Wahl; keine automatische Rechnungsausstellung, kein Versand und kein Lexware-API-Schreiben.
- Bewahrt geprüfte Positionen beim erneuten Öffnen der Buchung; neue separate Karte bleibt Admin-only. Dashboard-Link auf tatsächlichen Slug `/gaste-rechnungen/buchungen` korrigiert; das private kanonische Dashboard liegt vollständig unter `dashboards/gaste-rechnungen.yaml`. Hauptdashboard bleibt vollständig erhalten.
- Die bisherige v0.7.2 bleibt unverändert als Rollback-Release bestehen; vor Installation der vollständigen v0.7.3 sind HA-Backup, Ressourcencache-Wechsel und reale Regression vorgeschrieben.

## 0.7.2 — 2026-11-08 (Lexware-L Buchhaltungsbelege)

- Neues admin-geschütztes Buchhaltungsmodul für den **manuellen Lexware-Office-L-Einnahmenbeleg-Upload**: pro aktiver Smoobu-Buchung ein validierter, revisionsgebundener Buchhaltungsfall und ein internes PDF, das ausdrücklich keine Gastrechnung und keine Zahlungsaufforderung ist.
- Smoobu-Brutto und Preispositionssumme werden strikt verglichen; Umsatzsteuer muss für **jede Position manuell bestätigt** werden. Fehlende/abweichende Smoobu-Daten blockieren die Freigabe, unbekannte Hinweise benötigen ausdrückliche Bestätigung. Keine Zahlungsbestätigung aus Smoobu-Feldern ableiten.
- Neue vierte Gäste-Dashboardansicht **Buchhaltung**, separates responsive JS-Frontend, Einzel-PDF sowie ZIP von bis zu 25 bereits freigegebenen PDFs mit CSV-Manifest; revisionsgebundener manueller Marker `in Lexware hochgeladen`.
- Private HA-Storage-Datei für exportbezogene Referenzen, Fingerprints und geprüfte Beleg-Snapshots. Nach Quellbuchungsänderung wird der Download gesperrt; bereits hochgeladene Belege werden niemals stillschweigend verändert.
- Keine Lexware-API-Verbindung in Tarif L; spätere API-Anbindung kann denselben geprüften Snapshot nutzen. Kein automatischer Gastversand, keine Rechnungsausstellung, keine GoBD-/ZUGFeRD-Produktivfreigabe, keine eigene Zahlungsbuchhaltung.
- Smoobu-Workflows für Wäsche, NUKI, IT.NRW sowie die Bestandsreplikation bleiben unverändert. Installation auf dem einzigen HA erst nach Backup und kontrolliertem Test. Details: `docs/release-0.7.2-production.md`.

## 0.7.1 — 2026-11-08 (Produktivversion Gästezentrum)

- Die nach CI und Offline-Regressionen geprüften Funktionen aus 0.7.1rc1 sind in die vollständige reguläre Version 0.7.1 übernommen: getrennter Posteingang, Buchungssuche mit Konversation und Timeline-Deep-Link, selektierbare Rechnungsentwürfe.
- Smoobu-Preispositionen und Gastland mit konservativem Mapping sowie Revision-/Summenprüfung für manuelle Rechnungsänderungen.
- Alle bestehenden Wäsche-, NUKI-, IT.NRW- und Portalabläufe bleiben unverändert; Gastfunktionen sind zunächst deaktiviert und Nachrichtenversand bleibt standardmäßig AUS.
- Rechnungen bleiben ausschließlich Entwürfe beziehungsweise DEMO-Vorschauen; keine rechtsverbindliche Ausstellung, kein GoBD-Archiv und kein automatischer Rechnungsversand.
- Installation auf dem einzigen Home-Assistant-System erst nach Backup und mit dokumentiertem Rollback; eine reale HA-/Smoobu-Abnahme wird nicht durch CI ersetzt. Siehe `docs/release-0.7.1-production.md`.

## 0.7.1rc1 — 2026-11-08 (Staging-Vorabversion)

- Gästeverwaltung in drei Arbeitsbereiche getrennt: **Posteingang** nur für neu erkannte Gastnachrichten/Neubuchungen, **Buchungen** mit manueller Zeitraumsuche und vollständigem Smoobu-Gespräch je Buchung, **Rechnungen** mit gesonderter indexierter Liste der gespeicherten Rechnungsentwürfe.
- Lokale HA-Lesemarkierungen (eigener privater Store) statt Änderungen an Smoobuus globalem Posteingang; erster Abruf legt den historischen Basisbestand fest.
- Smoobu-Preispositionen bei leerer Detailantwort erneut aus `/api/reservations/<id>/price-elements` laden. Zuordnung der vier Betreiberpositionen inkl. Preis und Menge, mit Testfall 355 € Miete + 55 € Reinigung + 35 € Hund + 30 € zusätzliche Person = 475 €. Unbekannte Extras/manuell abweichende Steuern werden nicht geraten.
- Gastanschrift samt ISO-Ländercode zusätzlich aus `/api/guests/<guestId>` übernehmen. Nur unbearbeitete alte Entwürfe automatisch anreichern, bearbeitete Entwürfe ausschließlich nach ausdrücklicher Importbestätigung.
- Unabhängige Sperre von DEMO-PDF-Erstellung bei Abweichung zwischen Smoobu-Buchungsgesamtpreis und Rechnungsentwurf, um versehentliche doppelte Langzeitrabatte zu vermeiden.
- Timeline-Karte mit optionalem `guest_dashboard_path`: bei Auswahl einer Belegung direkt zur betreffenden Gästekonversation wechseln.
- Alle neuen Endpunkte Admin-only; Gastnachrichtenversand weiter deaktiviert, keine echte Rechnungsausstellung. Fünf-Views-Mittelhof-Hauptdashboard, Wäsche, NUKI und IT.NRW unverändert.
- Dokumentation: `docs/release-0.7.1rc1.md`. Erst nach eigenständiger HA-Stagingprüfung als stabilen Produktivstand einsetzen.

## 0.7.0 — 2026-11-07

- Stable, backward-compatible Smoobu Workflow update from v0.6.8 for existing Mittelhof Home Assistant installations. The domain `smoobu_mittelhof`, platform entities and existing NUKI/laundry/IT.NRW workflows remain unchanged.
- New **opt-in** administrator guest inbox, booking-specific Smoobu conversations, manually editable guest-message and invoice drafts. Guest PII syncing/HA Store initialization is DISABLED until `guest_portal_enabled` is explicitly enabled in the integration's options.
- New **guest message sending is OFF by default**, independent of opt-in to the inbox. Sending requires a distinct option and explicit per-message admin approval.
- Fixed options-flow defaults to show the actual saved configuration for existing laundry/NUKI/SMTP settings and the existing custom config directory, preventing accidental reset when enabling the new guest inbox.
- Draft invoice preview: 10-digit planned number `<house><arrival YYYYMMDD>` for houses 13, 14 and 15; 7% on classified accommodation services (rent, cleaning, max. 2 extra persons, max. 2 dogs). From **8 nights**, 10% discount on total gross rent only (not extras), rounded to cents. Unclassified Smoobu items cannot be auto-assigned or discounted.
- Optional admin-only connector to an independently installed PRIVATE ZUGFeRD **DEMO-only** preview service. Not installed with HACS. Final invoice issuance, payment collection, invoice emails and GoBD archiving are NOT provided or activated by this release.
- Separate Lovelace guest card included. Existing `dashboards/mittelhof.yaml` and all five views remain unchanged. New card is not added to existing dashboards automatically.
- New production-upgrade checks plus existing Python/JS, HACS, hassfest, NUKI, laundry, invoice and statistics regression tests.
- Safe migration/backout instructions: `docs/release-0.7.0-production.md`. Take a full HA backup before updating. This release was CI-verified but **has not been installed or runtime-tested on the user's live HA instance**.

## 0.6.8 — 2026-11-02

- Add standalone `smoobu_mittelhof.process_nuki_only` and `smoobu_mittelhof.process_laundry_only` services with optional `force_notify` flag. A manual NUKI request will never process laundry/order status or send a laundry notification, and a laundry request will never process NUKI.
- Update NUKI and laundry resend/reset integration buttons to invoke their respective isolated workflow handlers.
- Retire the combined `Wäsche + NUKI jetzt prüfen` integration button. Keep the legacy `process_workflows` service and periodic combined coordinator maintenance for backward compatibility; no shared operator action or destructive combined reset on dashboards.
- Dashboard Mittelhof now displays separate NUKI-only diagnostics; dedicated `reinigung.yaml` remains read-only and exclusively shows laundry health, stock and Smoobu bookings.


## 0.6.7 — 2026-11-02

- Correct Mittelhof's fifth linen-set article ID: `duvet_cover` (Bettdeckenbezug) replaces the incorrectly assumed `fitted_sheet` (Spannbetttuch); keep `flat_sheet` as Laken.
- One-time, non-destructive migration preserves all six physical counts, monotonic portal revision and HA replication cursor. Existing HA open-order, received-delivery and checkout item records are migrated without additional inventory mutations.
- Recognize Benfer's supplier position `Systemwäsche Bezug` as duvet cover and `Systemwäsche Laken` as the distinct sheet in item-based reorder calculations.
- Requires the coordinated portal deployment, updated Node-RED bidirectional sync and corrected **local** `/config/smoobu_mittelhof/laundry.yaml`. HACS cannot modify this user-managed file.


## 0.6.6 — 2026-11-02

- Uberspace staff portal is the single source of truth for the six available clean-laundry items; HA receives an exact, monotonic versioned snapshot with `smoobu_mittelhof.sync_portal_laundry_stock`.
- HA records portal-confirmed Smoobu checkout and ordered-delivery status without deducting/crediting physical inventory again. Replication event IDs prevent repeated receipt processing.
- Once mirrored, direct legacy HA consumption, receipt and inventory write actions are blocked. Stock thresholds and actionable notification/order-email workflow remain in HA.
- Requires import of the new bidirectional Node-RED status/replica flow and retirement of the old OUTBOUND ONLY agent.


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
