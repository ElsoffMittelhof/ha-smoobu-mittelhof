# Smoobu Workflow v0.7.4 – Lexware-L-Buchhaltung Datumsauswahl

**Vollständige stabile Integrationsversion** mit gezielter UI-Korrektur; kein unfertiger RC-Stand. Der bisherige v0.7.3-Zustand bleibt unverändert als Rückfalloption.

## Ursache und Korrektur

In `frontend/mittelhof-accounting-card.js` rendert `_run()` die ganze Karte vor dem API-Aufruf. Bis einschließlich v0.7.3 wurden **erst im Callback** der Suchfunktion `_refresh()` die Datumswerte aus den Eingabefeldern gelesen. Da das erste Re-Render die Felder bereits durch vorbelegte Daten ersetzte, gingen die gerade ausgewählten Werte verloren.

v0.7.4 liest beide Daten vor dem ersten Re-Render, speichert sie im Card-Zustand und verwendet exakt diese Werte für `search-bookings?from=...&to=...`. Änderungen der Datumsfelder werden auch über DOM-`change` übernommen. Fehlerhafte Datumsangaben, Enddatum vor Startdatum und Zeiträume über 731 Kalendertage werden abgefangen. Regressionstest `tests/test_accounting_date_ui.js` simuliert die Neurenderung und prüft gültige, ungültige und vertauschte Werte.

## Aktualisierung auf dem einzigen Home-Assistant-System

1. Vorher vollständig sichern; aktuelle HACS-Integration v0.7.3, `dashboards/mittelhof.yaml` und `dashboards/gaste-rechnungen.yaml` dokumentieren. In v0.7.4 ist **keine Dashboard-YAML-Änderung** notwendig.
2. Die vollständige stabile Integration **v0.7.4** über HACS aktualisieren und Home Assistant neu starten.
3. Unter Lovelace → Ressourcen die bestehende JavaScript-Modulressource der Lexware-Karte von `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.3` auf **`/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.4`** ändern (nur ein Ressourceneintrag, keinen zweiten hinzufügen). Danach Browser-App neu öffnen, um die JS-Datei neu zu laden.
4. Gästeverwaltung unter `/gaste-rechnungen-dashboard/buchhaltung` öffnen. Einen eigenen Zeitraum wählen und „Buchungen suchen“ anklicken; Von/Bis und Suchergebnis müssen zum gewählten Zeitraum passen. Buchung auswählen, dann erneut suchen; Daten dürfen nicht unerwartet zurückspringen. Ungültige/reverse/zu lange Zeiträume müssen eine Fehlermeldung liefern, ohne den API-Import zu verändern.
5. Wäsche, NUKI, IT.NRW, Gäste-Gespräche und Belegungsplan-Deep-Links weiterhin kontrollieren; keine automatische Gastmail oder Gastrechnung aktivieren. Lexware Office L bleibt manueller Belegimport ohne direkte API. Buchhaltungsbelege und Steuerklassifikationen benötigen die bereits festgelegte fachliche Abnahme.

## Rückfall

Bei Problemen HACS auf v0.7.3 zurücksetzen und die JS-Ressource wieder auf `?v=0.7.3` stellen. Vollständiges HA-Backup für unerwartete Bestandsdatenprobleme verwenden. Keine externen Kunden-/Rechnungsaktionen werden in v0.7.4 selbst ausgelöst.

**Release bedeutet nicht, dass diese Korrektur bereits im produktiven HA installiert wurde.**
