# Smoobu Workflow v0.7.0 – produktionssicheres Home-Assistant-Upgrade

Stand: 07.11.2026. **Stabiles HA-Integrationsrelease**, aus geprüftem RC 0.7.0rc3 entwickelt. Es ist KEINE Freigabe zur rechtsverbindlichen Rechnungsausstellung. Ein tatsächlicher Laufzeittest auf der produktiven Mittelhof-Instanz wurde noch nicht durchgeführt.

## Was wird aktualisiert?

Die Installation ersetzt ausschließlich das bisherige Custom-Integration-Verzeichnis `/config/custom_components/smoobu_mittelhof/`. Die HA-Konfiguration, bestehenden Geräte/Entitäten, Smoobu-Anmeldedaten, lokalen Wäschedateien, NUKI-Prozesse, Templates, Uberspace-Portal/Node-RED-Flows und das komplette Fünf-Views-Hauptdashboard bleiben bestehen.

Der interne Integrationsname `smoobu_mittelhof` und die ConfigEntry-Schemaversion `3` bleiben gleich. Es gibt keinen Datenbank-Reset und keine automatische Bestand-/Historienmigration in dieser Version.

### Sichere Defaults

- **Gästeverwaltung aktiviert:** standardmäßig `false`. Keine zusätzliche Gast-Synchronisation, solange sie ausgeschaltet ist. Bestehende Wäsche/NUKI-Workflows laufen weiter.
- **Gastnachrichten senden:** standardmäßig `false`, selbst bei aktivierter Gästeverwaltung. Nur ein explizites zweites Opt-in und individuelle Admin-Freigabe können eine Nachricht versenden.
- **Privater Rechnungsdienst:** keine Konfigurationsdatei = deaktiviert. Erst eine lokale `invoice_service.json` mit `enabled=true` verbindet den eigenständig betriebenen DEMO-Companion. Kein Ausstellen von echten Rechnungen.
- Kein automatisches Anlegen einer Rechnung, Gast-PDF-Versand, Zahlungsaufforderung oder Änderung von Wäsche-/NUKI-Beständen durch die neuen Gästefunktionen.

## Vor dem HA-Update

1. Vollständiges HA-Backup erzeugen und sicherstellen, dass es tatsächlich herunterladbar ist. Lokale Smoobu-Dateien sowie `.storage` müssen im Backup enthalten sein.
2. In den bisherigen Smoobu-Integrationsoptionen vorhandene Hauszuordnungen, `Konfigurationsverzeichnis`, Wäsche-/NUKI-Optionen, SMTP und Bestandswerte notieren. Bei Mittelhof existiert historisch `/config/smoobu_mittelhof/`; dieser Pfad bleibt erhalten.
3. Die produktive Wäsche-Synchronisation/Node-RED-Workflows nicht zurücksetzen und keine Bestandskorrektur ausführen.
4. HACS → Smoobu Workflow → Version `0.7.0` aktualisieren. Alternativ das GitHub-Release-Asset `smoobu-mittelhof-0.7.0.zip` nach Prüfung von `SHA256SUMS.txt` entpacken und `custom_components/smoobu_mittelhof/` komplett ersetzen.
5. Home Assistant vollständig neu starten.

## Nach dem Neustart – Pflichtkontrollen

1. Unter Einstellungen → Geräte & Dienste kontrollieren, dass Smoobu Workflow ohne Fehler geladen wurde.
2. Bestehende Smoobu-Kalender/Hausnummern 13/14/15, die Wäschehistorie und die getrennten NUKI-/Wäsche-Dienste prüfen. **Keine** Bestandsbuchung oder Sendeaktion nur für einen Test auslösen.
3. Das bisherige Mittelhof-Dashboard mit **allen fünf Views** unverändert prüfen, einschließlich Waschküche, Haus 13, Haus 14, Haus 15 und IT.NRW.
4. Über Smoobu Workflow → Konfigurieren/Optionen kontrollieren, dass die bisherigen Einstellungen angezeigt werden, insbesondere der existierende lokale Config-Ordner und NUKI-/Wäschewerte. Beim Öffnen der Optionen dürfen diese Werte nicht durch Standardwerte ersetzt werden.

## Neue Gästeverwaltung bewusst aktivieren

1. Einstellungen → Geräte & Dienste → Smoobu Workflow → Konfigurieren/Optionen.
2. `guest_portal_enabled` (**Gästeverwaltung aktivieren**) auf EIN setzen. `guest_message_send_enabled` (**Gastnachrichtenversand erlauben**) auf AUS lassen.
3. Optionen speichern, Integration wird neu geladen. Es werden daraufhin Gastentwürfe in HA Storage gespeichert; diese enthalten personenbezogene Informationen, also HA-Benutzer- und Backup-Zugriffe angemessen begrenzen.
4. Unter Einstellungen → Dashboards → Ressourcen die JS-Modulressource einbinden:

   `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.0`

5. Ein **separates** Dashboard „Gäste & Rechnungen“ anlegen und folgende manuelle Karte einfügen:

   `type: custom:mittelhof-guest-card`

   Keine bestehende `dashboards/mittelhof.yaml`-View verändern.

6. Eine aktuelle Test-/Beispielbuchung anzeigen. Nach manueller Zuordnung der Positionen Miete, Reinigung, zusätzliche Person (max. 2) und Hund (max. 2) kann die Abrechnungsvorschau geprüft werden: 7 % auf diese Kategorien, ab 8 Übernachtungen 10 % Nachlass auf die gesamte Brutto-Miete. Keine Rechnungen ausstellen oder Gastversand auslösen.

## ZUGFeRD-DEMO-PDF – weiterhin optional

Das HA-Paket enthält keine PDF-Bibliotheken und kein privates Logo. Für PDF/A-3b-/EN16931-ZUGFeRD-MUSTER benötigt man zusätzlich den getrennt eingerichteten privaten Companion `mittelhof-invoice-preview-0.7.0rc3-private.zip` und eine lokale `invoice_service.json` im tatsächlich konfigurierten Smoobu-Ordner (chmod 0600). Bei HA OS läuft dieser Companion typischerweise auf einem separaten Linux-/Container-Host hinter geschütztem HTTPS, nicht direkt im HA-HACS-Container. Die Betriebsanleitung ist im privaten Repo unter `invoice_engine/RELEASE_CANDIDATE.md`.

**ACHTUNG:** Es gibt nur mit `DEMO-` markierte Muster. Keine rechtsverbindliche Ausstellung, finale Rechnungskorrektur, GoBD-/WORM-Archiv oder echten PDF-Versand. Ein erfolgreiches HACS-Upgrade macht daraus noch kein freigegebenes Rechnungswesen.

## Rückkehr zu v0.6.8

Wenn Smoobu, Wäsche oder NUKI nach dem Update unerwartet reagieren:

1. Zuerst `guest_portal_enabled=false` setzen, um die neuen Hintergrundaufgaben zu deaktivieren.
2. Den bisherigen geprüften HA-Backupstand wiederherstellen, **oder** HACS-Version `0.6.8` erneut installieren und HA neu starten. Bei manueller Installation den vor dem Update gesicherten Ordner wiederherstellen.
3. Keinesfalls auf Verdacht Smoobu-Optionen, Wäschebestände, alte Buchungen oder die Node-RED-Flows löschen; das würde Duplikatschutz oder Inventurhistorie gefährden.
4. Nach einem Rollback eventuelle gespeicherte Gästeentwürfe als personenbezogene Daten behandeln; die ältere Version liest diese nicht, sie werden dadurch nicht automatisch gelöscht.

## Test- und Releasebeleg

- Öffentlicher Quellcode: `ElsoffMittelhof/ha-smoobu-mittelhof` auf dem eingefrorenen Branch `release/0.7.0-production`, mit stabilem Manifest `0.7.0`.
- Enthaltene CI: Python/JS, HACS und hassfest, NUKI-/Wäsche-/IT.NRW-Regression, Gästeentwürfe, Steuersatz/Mietdauerrabatt und zusätzlicher Produktivupgrade-Sicherheitstest.
- Kein Zugriff auf die tatsächliche produktive Home-Assistant-Oberfläche, daher noch keine bestätigte HA-Laufzeit-/Datenmigration.

Die beiden ursprünglichen Draft-PRs für Demo-ZUGFeRD und private Archivierung können getrennt bestehen bleiben. Ein stabiles HA-Integrationsrelease ist keine Freigabe für die rechtsverbindliche Rechnungserstellung.
