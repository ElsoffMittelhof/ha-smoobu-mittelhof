# Smoobu Workflow v0.7.6 – Lexware-L-Buchhaltung: stabiler Buchungsabruf und 404-Diagnose

**Vollständige stabile Integrationsversion; kein RC.** Die bisherige Version v0.7.5 bleibt als unverändertes Rollback-Release erhalten.

## Fehlerbild und Diagnose

Der Betreiber kann in `/gaste-rechnungen-dashboard/buchhaltung` einen Buchhaltungsfall mit Gastbrutto und Umsatzsteuerpositionen öffnen. Bei `Steuern prüfen und PDF freigeben` meldete v0.7.5 jedoch `response error 404`. Die POST-Route `/api/smoobu_mittelhof/guest/v1/bookings/{booking_id}/accounting` ist im Quellcode definiert und wird beim HA-Integrationsstart registriert. HTTP 404 allein beweist **nicht**, dass genau diese Route fehlt: auch ein fehlender/außerhalb der konfigurierten Häuser liegender Buchungsdatensatz kann 404 bewirken.

Im vorigen Backend rief `_current_source` die Smoobu-Detail-API **zweimal nacheinander** auf: einmal bereits über `_checked_booking` (inklusive Haus-/Reservierungsprüfung und Preisdetail-Fallback), danach nochmals direkt. v0.7.6 entfernt diesen unnötigen Zweitabruf. Dadurch erfolgt pro GET/POST genau ein validierter Smoobu-Detailabruf und nicht zwei möglicherweise unterschiedliche Netzantworten.

Die Karten-Fehlerdiagnose zeigt bei einem erneuten Fehlschlag **Methode + anonymisierten API-Endpunkt**, z. B. `HTTP 404 bei POST /api/smoobu_mittelhof/guest/v1/bookings/{id}/accounting`. Sie enthält **keine reale Buchungs-ID, keinen Gastnamen und keinen API-Key**. Weitere Ursachen wie fehlende/alte HA-Route, veralteter Backendstand oder Smoobu-Hauskonfiguration lassen sich damit sicher eingrenzen. **Eine endgültige Behebung des konkreten Live-404 kann ohne erneuten Test am einzigen HA nicht zugesagt werden.**

## Offline-Schutz und Tests

- `tests/test_accounting_contract.py` prüft anhand der Python-Implementierung, dass `_current_source` den validierten Smoobu-Abruf exakt einmal verwendet und danach keinen zweiten `get_booking` ausführt.
- `tests/test_accounting_404_ui.js` prüft Methode, anonymisierten Pfad, aussagekräftige 404-Meldung, erfolgreiche POST-Antwort und den weitergegebenen 409-Konflikt.
- Alle bisherigen Python-/JS-Tests, hassfest und HACS müssen vor Release grün sein. Keine automatische Lexware-Buchung, keine Gastmail und keine Gastrechnung.

## Sichere Installation auf dem einzigen Home Assistant

1. **Vollständiges HA-Backup** und aktiven Integrations-/Dashboardstand dokumentieren.
2. Die komplette stabile Integration v0.7.6 in HACS installieren, HA neu starten, Version v0.7.6 unter Smoobu Workflow prüfen. Ein reines Frontend-Reload ersetzt keinen HA-Neustart, weil hier auch der Python-Backend-Code geändert wurde.
3. In Lovelace-Ressourcen die bestehende JavaScript-Modul-Ressource **ersetzen**, nicht doppelt hinzufügen:
   `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.6`. Browser/App neu öffnen.
4. Hauptdashboard `dashboards/mittelhof.yaml` mit fünf Views und Gäste-Dashboard `dashboards/gaste-rechnungen.yaml` mit vier Views bleiben unverändert. Der tatsächliche URL-Slug lautet `gaste-rechnungen-dashboard`.
5. Zuerst Buchungen suchen und eine aktive Buchung mit eindeutigem Preis aufrufen, danach **einmal** freigeben. Bei Erfolg erst den PDF-Download prüfen, keinerlei Beleg doppelt in Lexware buchen.
6. Bei erneutem 404 die nun sichtbare **HTTP-Methode plus anonymisierten Endpunkt** mitteilen und in HA unter Einstellungen → System → Protokolle nach Fehlern der `smoobu_mittelhof`-Integration suchen. Ohne personenbezogene Daten oder Tokens teilen; nur dann entscheidet man über weitere Routen-/Datenkorrekturen.
7. Anschließend Wäsche, NUKI, IT.NRW, Gastkommunikation und Portalbestände unverändert kontrollieren. Gastversand, echte Gastrechnungsausstellung und Lexware-API-Schreibzugriff bleiben AUS.

## Rückfall

Bei Problemen HACS auf v0.7.5 zurücksetzen, HA neu starten und JS-Ressource wieder `?v=0.7.5` setzen. Keine HA-`.storage`-Dateien oder Rechnungsreferenzen zur Fehlerbehandlung löschen. Keine automatische produktive Installation durch GitHub-Release.
