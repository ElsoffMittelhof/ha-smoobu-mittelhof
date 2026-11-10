# Smoobu Workflow v0.7.9 – Lexware-L-Buchhaltungsbeleg mit Einnahme, Belegnummer und Leistungsdatum

**Vollständige stabile Integrationsversion**; vorhandene Home-Assistant-Instanz bleibt unberührt, bis nach vollständiger Sicherung und grüner CI manuell installiert wird. Die bisherige v0.7.8 bleibt als unveränderte Rollback-Version.

## Fachliche Datenquelle

Interner Lexware-L-Einnahmenbeleg pro geeigneter Smoobu-Buchung mit diesen ausdrücklich benannten Feldern:

| PDF-Feld | Quelle | Beispiel |
| --- | --- | --- |
| Belegtyp | Fester Wert für interne Umsatz-Buchungsbelege | Einnahme |
| Belegnummer | `id` der Smoobu-Buchung | 160317906 |
| Buchungsdatum | `created-at` der ursprünglichen Smoobu-Buchung | 09.11.2026 |
| Belegdatum | Derselbe ursprüngliche Buchungstag | 09.11.2026 |
| Fälligkeitsdatum | Derselbe ursprüngliche Buchungstag (Betreiberentscheidung für den internen Lexware-Beleg) | 09.11.2026 |
| Leistungsdatum | `departure`, Checkout/Abreisetag | 27.12.2026 |
| Aufenthaltszeitraum | `arrival` bis `departure` | 22.–27.12.2026 |
| Bruttobetrag / Steuer | Ausschließlich nach Betreiberprüfung ausgewählte Gastpreispositionen | 475,00 EUR, USt zu prüfen |

Belegtyp `Einnahme` ist die **Kategorisierung des internen Einnahmenbelegs**, nicht die Aussage, dass die Zahlung schon erfolgte. Das Leistungsdatum bezeichnet den Checkout-Tag, **nicht** den Zeitpunkt der tatsächlichen Umsatzsteuervereinnahmung bei Istversteuerung. Bei Portalbuchungen darf ein zusätzlicher nachträglich ausgestellter Gastrechnungsbeleg keine zweite Einnahme in Lexware erzeugen.

## Implementierung

- `accounting_core.prepare_booking` liest Buchungs-ID, `created-at` und `departure`, bildet aus diesen das feste `accounting_type="Einnahme"`, `document_number=booking_id` und `service_date=departure`.
- `accounting_core.approve_snapshot` prüft ID-Gleichheit, den festen Belegtyp und ein gültiges Checkoutdatum nach dem Anreisetag; alle drei Felder gehen in den kanonischen `mittelhof.accounting.v4`-Snapshot und den Hash ein.
- `accounting_core.render_pdf` druckt die Felder deutlich als `Belegtyp: Einnahme`, `Belegnummer: <Buchungs-ID>`, `Leistungsdatum: TT.MM.JJJJ`; die bereits vorhandenen Buchungs-, Beleg- und Fälligkeitsdaten bleiben bestehen.
- `accounting_portal` prüft die neue v4-Revision und alle drei Felder bei Einzel-PDF, ZIP-Sammel-PDF und manueller Uploadmarkierung. Bereits hochgeladene Altbelege werden niemals still verändert; ihre Korrektur erfordert manuelle Abstimmung.
- `mittelhof-accounting-card.js` zeigt Belegtyp, Belegnummer und Leistungsdatum schon vor PDF-Freigabe zur Kontrolle an. Die bereits bestehende 7%-Vorbelegung je Gastposition und die explizite Steuerprüfung bleiben erhalten.
- Neue Regression prüft Smoobu-Buchungs-ID als Belegnummer, Checkouttag als Leistungsdatum, ausdrücklich `Belegtyp: Einnahme` und die Sperre bei ungültigem Checkout. Der PDF-Parser kann die Daten in Lexware zur Vorbelegung anbieten, eine **zuverlässige automatische Lexware-OCR-Feldzuordnung ist nicht garantiert**; nach Upload kontrollieren.

## Installation auf dem einzigen Home Assistant

1. Vollständiges Home-Assistant-Backup erstellen und vorher installierte Integrationsversion sowie JS-Ressourcen dokumentieren.
2. Nach grüner Release-CI das vollständige HACS-Release **v0.7.9** installieren. **Home Assistant vollständig neu starten**, da Python-PDF-Backend aktualisiert wird.
3. Den vorhandenen Lovelace-Ressourceneintrag einmalig auf **`/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.9`** ändern (JavaScript-Modul, nicht zusätzlich registrieren). App/Browser vollständig neu laden.
4. Die privaten vollständigen YAML-Dashboards `dashboards/mittelhof.yaml` (fünf Views) und `dashboards/gaste-rechnungen.yaml` (vier Views) bleiben **unverändert**. Tatsächlicher Gäste-Dashboard-URL-Pfad: `gaste-rechnungen-dashboard`.
5. Eine reguläre Portalbuchung kontrollieren: `Belegtyp: Einnahme`, `Belegnummer = Smoobu-ID`, `Leistungsdatum = Abreise/Checkout`. Nach Steuerprüfung PDF herunterladen, dort die expliziten Texte kontrollieren, anschließend manuell in Lexware Office L unter „Belege erfassen“ als **Einnahme** hochladen. Prüfen, ob Lexware Belegtyp, Kunde, Belegnummer, Belegdatum, Fälligkeitsdatum, Leistungsdatum, Kategorie, Brutto und 7%-USt korrekt erkennt. Bei falscher Erkennung vor Verbuchung manuell berichtigen.
6. Bereits geprüfte v3-Belege, die noch nicht in Lexware erfasst sind, erneut prüfen/freigeben, bevor sie als v4-PDF exportiert werden. Bereits manuell als hochgeladen markierte Belege unverändert lassen und gegebenenfalls in Lexware nach gesonderter Prüfung korrigieren.
7. Wäsche, NUKI, IT.NRW, Gastposteingang, Timeline, Provisionsabrechnungen und Uberspace-Wäschebestand unverändert kontrollieren. Keine Gastmails, keine echte Rechnungsausstellung und kein Lexware-API-Schreibzugriff aktivieren.

## Rückfall

Bei Fehlern HACS auf v0.7.8 zurücksetzen, HA neu starten und die Buchhaltungsressource wieder mit `?v=0.7.8` laden. Keine Rechnungs- oder Store-Dateien löschen. Vorhandene v4-Snapshots vor einer erneuten v3-Freigabe prüfen; Rückfall ersetzt keine buchhalterische Korrektur.

**GitHub-Release ≠ Installation oder steuerliche Freigabe im einzigen HA-System.**
