# Smoobu Workflow 0.7.2 – Lexware Office L, manuelle PDF-Buchhaltungsbelege

**Vollständige Integrationsversion** (keine RC-Version). Auslieferung als HACS-Release nach grüner CI; keine automatische Installation in das einzige Home-Assistant-System. Bestehende Wäsche-, NUKI-, IT.NRW- und Portal-Wäschefunktionen bleiben unverändert.

## Zweck und Abgrenzung

Neue Buchhaltungsansicht für die im separaten privaten Gäste-Dashboard vorhandenen Smoobu-Buchungen aller Häuser. Pro aktiver, nicht geblockter Buchung wird aus aktuellen Smoobu-Details ein interner Buchhaltungsfall vorbereitet. Aus diesem können nach Prüfung **PDF-Buchungsnachweise für den manuellen Upload als Einnahmenbeleg in Lexware Office L** erstellt werden.

**Wichtig:** PDF-Buchungsnachweise sind ausdrücklich **keine steuerlichen Gastrechnungen**, keine Zahlungsaufforderungen, kein vom Portal erstellter Originalbeleg und kein Nachweis, dass die Zahlung tatsächlich geflossen ist. Sie ersetzen auch nicht ohne weitere steuerliche Prüfung die Original-Buchungsbestätigung, Portal-Abrechnung und den Provisionsbeleg. Bei Direktbuchungen/TOMAS, für die bereits eine rechtlich ausgestellte Gastrechnung existiert, darf der interne Buchungsnachweis in Lexware **nicht zusätzlich als weiterer Umsatz** erfasst werden: die bestehende Gastrechnung ist der maßgebliche Einnahmenbeleg.

Die Lexware-Public-API ist im Tarif L nicht vorgesehen und wird von 0.7.2 weder kontaktiert noch simuliert. Ein zukünftiger API-Adapter kann den kanonischen geprüften Snapshot, Dokument-Hash und Smoobu-ID verwenden. Lexware ist führend für Bank-/Zahlungsabgleich, tatsächliche Umsatzsteuerbuchung und Portalprovisionen.

## Prüfung und PDF

1. Zeitraum auf der vierten Gäste-Dashboardseite **Buchhaltung** wählen (max. 731 Tage je Abfrage), eine Buchung auswählen.
2. Smoobu liefert Booking-ID, Haus, Gast, Kanal, Aufenthalt, Gesamtbrutto und Preispositionen einschließlich offiziellem Fallback für Preis-Details. Die Positionen müssen exakt den Gesamtbetrag ergeben. Fehlende Preisdetails werden als Warnung ausgewiesen.
3. Für **jede Position** den steuerlich überprüften Satz 0, 7 oder 19 % auswählen. Smoobu-Werte sind höchstens **Vorschläge**, keine automatischen steuerlichen Freigaben. Nur nach eindeutiger fachlicher Prüfung freigeben; Sonderfälle mit unbekannter oder gemischter Besteuerung sind vorab zu klären. Einzelne Warnungen und die Steuerprüfung sind explizit zu bestätigen.
4. Das System erstellt aus dem freigegebenen Snapshot einen unveränderlichen Hash und ein PDF mit Bruttoumsatz, Einzelpositionen, USt-Ausweis und Smoobu-Provenienz. PDF zeigt **keinen** bezahlten/offenen Status, da Smoobu nach der Buchung nicht zuverlässig aktualisiert wird.
5. Einzel-PDF oder ZIP mit bis zu 25 **bereits geprüften** Buchungsbelegen und CSV-Manifest herunterladen. ZIP-Export verändert keinen Buchungs- oder Zahlungsstatus.
6. PDF unter Lexware `Belege erfassen` als **Einnahmenbeleg** hochladen. Erst **danach** Schaltfläche `In Lexware hochgeladen` nutzen. Der Marker ist nur eine manuelle Bestätigung, keine Lexware-API-Quittung.
7. Weicht ein späterer Smoobu-Datensatz ab, ist ein alter Beleg für neue Downloads gesperrt. Bereits als hochgeladen markierte Belege werden nicht still überschrieben. Änderungen nach Lexware-Erfassung müssen im manuellen Korrekturprozess in Lexware geklärt werden.

**Brutto-/Netto-Beispiel:** 355 + 55 + 35 + 30 = 475 EUR Gastbrutto. Bei 71,25 EUR Provision überweist das Portal 403,75 EUR. Die 403,75 EUR sind **nicht** die Bemessungsgrundlage der Gastumsatz-USt. Vermittlungsgebühren/Reverse-Charge separat in Lexware behandeln. Die im Beispiel angenommenen 7 % pro Position sind ohne steuerliche Bestätigung kein allgemein gültiger Default.

## Technische Architektur und Datenschutz

- Integrationsdomain und bestehende Integrationskonfiguration bleiben `smoobu_mittelhof`; aktuelle Gastportal-Option `guest_portal_enabled` bleibt default OFF. Gastnachrichtenversand default OFF.
- `accounting_core.py`: reine Preis-/Steuerprüfung und Standardbibliothek-PDF 1.4 (keine neue Abhängigkeit, kein privater PDF-Companion erforderlich).
- `accounting_portal.py`: HA-Authentifizierung + explizite Administratorprüfung für Quellenabruf, Freigabe, PDF, ZIP und manuellen Marker. API unter `/api/smoobu_mittelhof/guest/v1/accounting` und `/bookings/{id}/accounting[...]`.
- `frontend/mittelhof-accounting-card.js`: eigenständige, responsive Buchhaltungsansicht. Steuerprüfung nur durch HA-Admin. Zur PDF-Ausgabe Base64 über authentifiziertes HA-API; keine öffentlichen, langzeitgültigen Download-URLs.
- Private HA Store-Datei: `/config/.storage/smoobu_mittelhof.accounting_records`. Enthält geprüfte Buchhaltungs-Snapshots samt Gastname und Buchungsbeträgen; **nicht in GitHub** und nur in geschützten HA-Backups verwahren. Keine NUKI-PINs, Smoobu-Tokens, Gastkommunikation oder Bankdaten speichern.
- PDF-Hashes und Quellfingerprints machen eine spätere API-Integration und das Erkennen von Änderungen möglich, sind aber **kein GoBD-konformes Archiv**.
- Keine automatischen E-Mails, keine endgültigen Rechnungsnummern, keine endgültige ZUGFeRD-Rechnung und keine automatische Verbuchung.

## Einrichtung auf EINER HA-Instanz

1. Aktive Integrationsversion und Dashboard-Ressourcen dokumentieren. **Vollständiges HA-Backup** und offline erreichbare Kopie samt Wiederherstellungsprüfung vor dem HACS-Update anlegen. Lokale Verzeichnisse `/config/smoobu_mittelhof/` sowie Wäsche-Portalreplikation unverändert bewahren.
2. Nur das geprüfte v0.7.2 GitHub-Release per HACS installieren; HA neu starten. Bestehende Smoobu-Einstellungen und `guest_portal_enabled` nicht ungefragt ändern.
3. Lovelace-Ressourcen als **JavaScript-Modul**, jeweils nur einmal: `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.2`, `/smoobu_mittelhof/frontend/smoobu-timeline-card.js?v=0.7.2`, und neu `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.2`.
4. Private vollständige Datei `dashboards/gaeste-rechnungen.yaml` aus dem zugehörigen privaten `main` installieren: vier Views **Posteingang, Buchungen, Rechnungen, Buchhaltung**. Der URL-Pfad bleibt `gaeste-rechnungen`. Die kanonische `dashboards/mittelhof.yaml` mit allen **fünf** Views wird bei diesem Release nicht verändert.
5. Auf dem einzigen HA-System zunächst ohne Gastkommunikation testen: Wäsche/NUKI/IT.NRW-Regression und Portal-Wäsche-Synchronisation; danach Smoobu-Buchungssuche, Warnungsfälle, Steuerfreigabe, PDF, ZIP und manuelle Uploadmarkierung.
6. Erst wenn Belegart, USt-Zuordnung und Lexware-Upload buchhalterisch abgenommen sind, echte Einnahmenbelege aus diesem Workflow verwenden. Kein automatischer Gastversand; alle Rechnungsausstellungsfunktionen bleiben außerhalb dieser Freigabe.

## Rollback

Bei Laufzeitproblem Gastportal gegebenenfalls wieder deaktivieren, Integration über HACS auf das zuletzt installierte stabile Release zurückstellen und Home Assistant neu starten. Bisheriges vier-/dreiseitiges Gäste-Dashboard passend zur Version zurückspielen. Die alte `.storage` nicht ungezielt verändern, Workflow-Duplikatschutz nicht resetten. Für echte Daten nach Freigabe Datenmigration/Restore gesondert prüfen; aktuell ist noch kein schützenswerter Gäste-Datenbestand gemeldet.

## Grenzen

CI prüft Offline-Tests, Python-/JS-Syntax, HACS und hassfest. Die korrekte steuerliche Einordnung einer Leistung sowie die Anerkennung des internen PDFs als geeigneter Einnahmenbeleg können nicht allein durch Softwaretests bestätigt werden. Ebenso ist eine echte HACS-/HA-Installation in der einzigen Betreiberinstanz nicht automatisiert. Nach einem erfolgreichen Release ist daher noch eine kontrollierte reale Abnahme nötig.
