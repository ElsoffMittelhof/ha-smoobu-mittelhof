# Smoobu Workflow v0.7.10 – Einheitliche Fälligkeit für Buchhaltungsbelege und Rechnungsentwürfe

**Vollständige stabile Produktivversion.** Keine automatisch versendeten Gastnachrichten und keine echte Rechnungsausstellung. Der Betreiber bestätigt ausdrücklich: bisher wurden noch **keine produktiven Rechnungen oder Buchhaltungsbelege erstellt**, daher ist keine Bestandsdatenmigration erforderlich. Dennoch gilt: einziges Home-Assistant-System, vor dem Update vollständig sichern.

## Mittelhof-Regel: Fälligkeitsdatum ist der geplante Zahlungstermin

| Smoobu-Buchungskanal | Zahlungsziel / Fälligkeitsdatum |
| --- | --- |
| Airbnb | **Anreisetag + 1 Kalendertag** |
| Booking.com | **Checkout-/Abreisetag + 1 Kalendertag** |
| Naturhäuschen (auch `Naturhaeuschen`, `Nature House`) | **Ursprünglicher Buchungstag** aus `created-at` |
| TOMAS, Direktbuchung, Homepage (einschließlich Website) | Falls zwischen ursprünglichem Buchungstag und Anreise **mindestens 28 volle Kalendertage** liegen: **Anreisetag − 28 Kalendertage**; falls **weniger als 28 Tage**: **ursprünglicher Buchungstag** |

Die Grenze von genau **28 Tagen zählt zur ersten Variante**. Berechnung mit richtigen Kalendertagen, inklusive Monats-/Jahreswechsel und Schalttag; keine Abhängigkeit von aktuellem Datum, UTC-Uhrzeit oder Beleg-/PDF-Exportzeitpunkt.

**Datumsfelder bleiben getrennt:** `Belegdatum` und `Buchungsdatum` stammen weiter aus dem ursprünglichen Smoobu-`created-at`. `Leistungsdatum` bleibt Checkout/Abreisetag; `Belegnummer` bleibt Buchungs-ID; `Belegtyp` bleibt `Einnahme`. **Fälligkeitsdatum ist kein nachgewiesener Zahlungseingang**; Bankabgleich und Istversteuerung erfolgen weiterhin anhand der tatsächlichen Zahlungen in Lexware Office L. Für Plattformbuchungen darf das Datum nicht als erneute Zahlungsaufforderung gegenüber dem Gast verstanden werden.

## Implementierung

- **Gemeinsame Berechnung in `guest_finance.booking_due_date(booking)`**: liest Smoobu-Buchungskanal, `arrival`, `departure` und – wenn für die Regel erforderlich – den ursprünglichen Buchungszeitpunkt `created-at`. Für Airbnb und Booking.com genügt ein valider Aufenthaltszeitraum selbst dann, wenn eine Smoobu-Listenansicht `created-at` nicht mitliefert. Für Naturhäuschen und Direktkanäle ist der ursprüngliche Buchungstag Pflicht. Unbekannte Kanäle oder unplausible An-/Abreisen erhalten kein erfundenes Zahlungsziel.
- **Lexware-L-Buchhaltungsbeleg:** `accounting_core.prepare_booking()` verwendet denselben Algorithmus. `approve_snapshot()` blockiert die Freigabe, wenn die Fälligkeit nicht bestimmbar ist, und schreibt die geprüfte Fälligkeit revisionsgebunden in `mittelhof.accounting.v5` und das PDF. Beleg-/Buchungsdatum bleiben unverändert. Admin-Buchhaltungsansicht erklärt, dass die Fälligkeit ein geplantes Zahlungsziel nach Buchungskanal ist. Einzel-/Sammel-PDF und manuelle Hochgeladen-Markierung prüfen Schema und Fälligkeit.
- **Rechnungsentwürfe und DEMO-ZUGFeRD-Erzeugung:** `guest_finance.make_draft()` trägt die automatisch berechnete `invoice.due_date` als Vorgabe ein. Die bestehende `invoice_portal.EXPORT_FIELDS`-Freigabeliste und `_export_payload()` reichen diese geprüfte Angabe als `due_date` an den privaten DEMO-Rechnungsdienst weiter. Wenn erst die vollständige Smoobu-Buchung das notwendige `created-at` liefert, ergänzt `GuestDraftRepository.enrich_pristine()` die Fälligkeit in **unbearbeiteten** Entwürfen. Bei ausdrücklich bestätigten Quelländerungen wird eine **nicht manuell geänderte** Fälligkeit neu vorgeschlagen. Manuell durch den Betreiber geänderte Fälligkeiten werden nicht still ersetzt.
- Es werden **keine** echten Gastrechnungen erstellt oder versendet. Der private Rechnungs-Companion bleibt DEMO/prüfpflichtig. Buchungsbrutto, getrennte Plattformgebühren, 7%-USt-Vorwahl und strikte Vermeidung doppelter Buchungen bleiben unverändert.
- Neue Python- und Frontend-Regressionsfälle für Airbnb, Booking.com, Naturhäuschen, TOMAS, Direkt und Homepage, die 27-/28-/29-Tage-Grenzen, den Rechnungsvorschlagswert, unbekannte Kanäle und das PDF. Vollständige CI ist vor Veröffentlichung Pflicht.

## Installation auf dem einzigen Home Assistant

1. Vollständiges HA-Backup sichern, auch `.storage` und die bekannten Dashboard-Konfigurationen.
2. **Stabile vollständige Integrationsversion v0.7.10** über HACS installieren, **Home Assistant vollständig neu starten**.
3. Den **bestehenden** Lovelace-Ressourceneintrag für die Buchhaltungskarte (JavaScript-Modul) einmalig auf `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.10` **ändern**, nicht zusätzlich anlegen. Browser/App neu laden.
4. Private vollständige Dashboard-Dateien `dashboards/mittelhof.yaml` (**fünf Views**) und `dashboards/gaste-rechnungen.yaml` (**vier Views**) bleiben unverändert. Tatsächlicher Gäste-Dashboard-Slug: `gaste-rechnungen-dashboard`.
5. Zunächst **nur Testfälle** in Gästeverwaltung/Buchhaltung und im Rechnungsentwurf kontrollieren: Airbnb = Anreise + 1, Booking.com = Abreise + 1, Naturhäuschen = Buchungstag, Direkt/TOMAS/Homepage = 28-Tage-Regel. Prüfen, dass Belegdatum weiterhin Buchungstag und Leistungsdatum Checkout ist.
6. Gastversand AUS, echte Rechnungsausstellung AUS, direkter Lexware-API-Schreibzugriff AUS. Wäsche, NUKI, IT.NRW und Wäscheportal nach Upgrade auf dem einzigen HA kontrollieren.
7. Für Rückfall HACS v0.7.9 installieren, HA neu starten, Ressource wieder auf `?v=0.7.9` ändern. Keine HA-Storage-Daten löschen.

**CI-grüner GitHub-Release bedeutet nicht, dass das Update schon auf dem tatsächlichen HA-System eingespielt oder getestet wurde.**
