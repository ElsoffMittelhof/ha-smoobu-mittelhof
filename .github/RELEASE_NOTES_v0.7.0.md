# Smoobu Workflow 0.7.0 – stabiles Home-Assistant-Integrationsrelease

**Dieses Release ist für ein kontrolliertes Upgrade einer bestehenden 0.6.8-Installation vorgesehen.** Es ist eine stabile HA-Integration, aber keine Freigabe zur rechtsverbindlichen Rechnungsstellung und kein Deployment auf dem Home Assistant des Betreibers.

## Neu

- Optionale **Admin-Gästeverwaltung** mit Smoobu-Nachrichten, buchungsgebundenen Entwürfen, sicherem Rechnungs-Entwurfsexport und separater Lovelace-Karte.
- **Gästeverwaltung beim Update AUS**, um zusätzliche Smoobu-Abfragen und Speicherung personenbezogener Gästedaten nicht unbeabsichtigt zu aktivieren.
- **Gastnachrichtenversand separat AUS**. Auch nach Aktivierung der Gästeverwaltung werden keine Nachrichten automatisch versendet.
- Aufbewahrung der vorherigen Integrations-Domain `smoobu_mittelhof`, der vorhandenen Hauszuordnungen, lokalen Konfigurationsdateien, Wäsche-/NUKI-/IT.NRW-Abläufe und des Bestands.
- Behobener Optionsdialog: bereits gespeicherte lokale Pfade, NUKI-, Wäsche-, SMTP- und Bestandsparameter werden beim Ändern der Optionen übernommen, statt mit Defaults überschrieben zu werden. Kein stilles Verschieben des Wäsche-Erfassungsbeginns durch Öffnen des Dialogs.
- Entwürfe für Haus 13/14/15 nach `<Haus><JJJJMMTT-Anreise>`; 7 % für die definierten Unterkunftspositionen; 10 % auf den **gesamten Brutto-Mietbetrag ab acht Übernachtungen**, nicht auf Reinigung/Hunde/zusätzliche Personen.
- **Optional**: privater, separat betriebener ZUGFeRD-**DEMO**-Rechnungsdienst. Ohne Konfiguration bleibt die PDF-Vorschau aus; keine echte Rechnungsausstellung, kein Zahlungs- oder Rechnungsversand, kein GoBD-Archiv.

## Produktive Installation (mit Sicherung)

1. **Vollständiges HA-Backup** anfertigen und dessen Verfügbarkeit prüfen.
2. HACS → Smoobu Workflow → Version **0.7.0** installieren. Für manuelle Installation das Asset `smoobu-mittelhof-0.7.0.zip` und die Prüfsummendatei `SHA256SUMS.txt` herunterladen.
3. ZIP unter `/config/custom_components/smoobu_mittelhof/` installieren, bestehende Integration vorher sichern; HA vollständig neu starten.
4. Smoobu-Kalender, Wäsche, NUKI, IT.NRW, die fünf Mittelhof-Dashboardseiten sowie die bisherigen Integrationsoptionen überprüfen.
5. Erst dann unter Smoobu Workflow → Optionen **Gästeverwaltung aktivieren** einschalten, **Gastnachrichtenversand** ausgeschaltet lassen.
6. Separates Dashboard verwenden, Ressource `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.0` als JavaScript-Modul registrieren und Karte `type: custom:mittelhof-guest-card` hinzufügen. Das bisherige Hauptdashboard nicht ersetzen.

Vollständige Upgrade-/Prüf-/Rollback-Anleitung: `docs/release-0.7.0-production.md` im Release-Quellstand.

## Rollback

Gästeverwaltung deaktivieren und bei Problemen den vorherigen 0.6.8-Integrationsstand oder das vollständige HA-Backup wiederherstellen. Wäschebestände, NUKI-/Portal-Duplikatsperren und Node-RED-Workflows **niemals** als Schnellreparatur zurücksetzen.

## Prüfung und Grenze

Auf festem Quellcommit `853acc9ac20e4f6a34717624e6eecb7441e098c5` basierend, mit Python-/JS-Tests, HACS, hassfest und spezifischen Regressionstests für bestehende Wäsche-/NUKI-Konfiguration und opt-in Gästezugriff.

**Nicht geschehen:** Installation auf produktivem HA, echte PDF-Rechnungsausstellung, GoBD-konforme Endarchivierung, Rechnungskorrekturen oder automatischer Gastversand. Deshalb zuerst reale Laufzeit-/Backup-Abnahme durchführen.

