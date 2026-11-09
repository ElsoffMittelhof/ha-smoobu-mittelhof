# Smoobu Workflow v0.7.5 – 7%-USt-Vorbelegung und verständliche Fehler im Lexware-L-Bereich

**Vollständiges stabiles Integrationsrelease**, das v0.7.4 ersetzt, ohne bestehende Daten automatisch zu migrieren oder fremde Produktivabläufe anzupassen. Das bisherige v0.7.4-Release bleibt Rollback.

## Betreiberfeedback

Beim Erstellen eines internen Buchungsbelegs in der vierten Gästeansicht `Buchhaltung · Lexware L` wurde nur `[object Object]` angezeigt. Das war ein Darstellungsfehler: Die JavaScript-Karte verwendete `String(error.message)`, während Home Assistant dort manchmal ein geschachteltes JSON-Fehlerobjekt liefert. Der tatsächliche Backend-Ablehnungsgrund war aus der Anzeige **nicht rekonstruierbar**; er wird nicht als bereits definitiv behoben behauptet. Die neue Anzeige extrahiert verständliche `message`, `error`, `detail` und HTTP-Code, sodass eine fachliche Ablehnung, ungültige Smoobu-Quelle oder technische Störung sichtbar wird, ohne Tokens/PII zu protokollieren.

Der Betreiber hat aktuell keine Gast-Buchungsposition mit abweichendem Umsatzsteuersatz: **7 % wird deshalb als lokale Standard-Vorauswahl auf allen neuen Gastpositionen aktiviert.** Weiterhin bleiben 0%, 7%, 19% auswählbar und bereits zuvor explizit geprüfte andere Steuersätze erhalten. **Die bestehende bestätigende Freigabeaufforderung und die serverseitige Steuerprüfung bleiben unverändert.** Eine Vorbelegung ist weder eine automatisch ausgestellte Rechnung noch eine steuerliche Allgemeinfreigabe sämtlicher späterer Zusatzleistungen.

Neue Offline-UI-Regression `tests/test_accounting_vat_error_ui.js`: vier Gastpositionen, vorausgewählte 7%, Übernahme geprüfter 19%-Abweichung, geschachtelte HA-API-Fehler mit verständlichem Text, kein `[object Object]`. Vollständige Python-/JS-/HACS-/hassfest-Regression vor Veröffentlichung.

## Installation auf dem einzigen Home-Assistant-System

1. Vor dem HACS-Update **vollständiges HA-Backup** erstellen, vorherige Integration-/Dashboard-/Ressourcenstände notieren. Die aktuelle HA-Gästeverwaltung muss gesichert werden.
2. Stabiles veröffentlichtes v0.7.5-Release in HACS installieren, Home Assistant neu starten.
3. In Lovelace-Ressourcen den bestehenden JavaScript-Modul-Eintrag **ersetzen**, nicht duplizieren: `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.5`. Andere Smoobu-Lovelace-Ressourcen können mit ihrer vorherigen v0.7.4-Cachekennung unverändert bleiben, da sie nicht geändert wurden. Browser/App neu laden.
4. Gäste-Dashboard `/gaste-rechnungen-dashboard/buchhaltung` öffnen. Buchung auswählen: jede neue Gastposition zeigt **7 %** als Vorgabewert; eine andere Besteuerung kann ausdrücklich ausgewählt und vor PDF-Freigabe geprüft werden.
5. `Steuern prüfen und PDF freigeben` betätigen und die Freigabebestätigung beachten. Bei fachlichem oder technischem Fehler wird nun die konkrete Meldung sichtbar. Sollte es weiterhin nicht funktionieren, **nur Fehlermeldung und HTTP-Code** melden, nicht komplette Smoobu-Buchungs-/Gastdaten oder API-Tokens.
6. Nach erfolgreicher Freigabe PDF nur entsprechend der fachlich freigegebenen Belegregeln für Lexware L verwenden. Rechnungen, Gastkommunikation, Bankabgleich und Portalabrechnungen bleiben strikt getrennt; kein Lexware-API-Schreibzugriff.
7. Wäsche, NUKI, IT.NRW, Gasttimeline und Bestandsabgleich nach dem HACS-Update kontrollieren; es gibt keine Änderungen an diesen Modulen oder den privaten YAML-Dashboards.

## Rückfall

Bei einer HA-Laufzeitstörung die Integration auf v0.7.4 und die Buchhaltungsressource auf `?v=0.7.4` zurückstellen, HA neu starten. Nicht eigenmächtig HA-`.storage`-Belegdaten löschen. Eine dokumentierte Korrektur in Lexware ist vom reinen UI-Rollback unabhängig.

**Release-Bereitstellung und Github-CI sind keine automatische Installation auf dem einzigen HA.**
