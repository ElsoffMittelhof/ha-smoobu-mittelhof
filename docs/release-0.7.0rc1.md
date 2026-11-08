# Smoobu Workflow 0.7.0rc1 – Release-Kandidat

Der Branch feature/guest-invoice-v1-drafts enthält den ausführbaren HA-Workflow für Gäste und DEMO-ZUGFeRD-Musterrechnungen.
Er ist noch NICHT der freigegebene Produktiv-Release für echte Rechnungen. Die bisherige produktive HACS-Version 0.6.8 bleibt unangetastet.

## Neu gegenüber 0.6.8

- Admin-only Gäste-Posteingang mit Smoobu-Nachrichten und manuell bearbeitbaren Rechnungs-/Nachrichtenentwürfen.
- Manuelle Anforderung einer ZUGFeRD-Musterprüfung, geschützt durch aktuelle Smoobu-Buchungsdaten und Entwurfsrevision.
- Rechnungsnummernvorschau: Hausnummer 13, 14 oder 15 gefolgt vom Anreisedatum YYYYMMDD ohne Trennzeichen.
- Steuer-/Zahlungskontrollen, strukturierte Rechnungsempfängeranschrift, Smoobu-HMAC-API-Konversationen.
- Lokale Verbindung zum PRIVATEN Mittelhof-Musterrechnungsdienst: DEMO-PDF erstellen, PDF/A unabhängig prüfen, Mustervorschau freigeben, archivieren und nach begründetem Korrekturwunsch neu erstellen.
- DEMO-PDF per authentifiziertem HA-Admin-Endpunkt laden. Das Token des privaten Rechnungsdienstes wird dem Browser nie mitgeteilt.
- Echter Smoobu-Gastnachrichtenversand ist in den Integrationsoptionen standardmäßig serverseitig AUS und verlangt auch bei Opt-in manuelle Freigabe.

## Installationsvoraussetzungen

Die HACS-Integration enthält aus Gründen der Privatsphäre weder das Original-Logo noch WeasyPrint, Factur-X oder Steuerschlüssel. Für die DEMO-PDF-Funktion wird der separat installierte private Dienst aus ElsoffMittelhof/mittelhof-homeassistant benötigt.
Anleitung im privaten Repository: invoice_engine/RELEASE_CANDIDATE.md.
Die lokale Datei invoice_service.json im konfigurierten HA-Smoobu-Ordner enthält enabled, url und ein geheimes Token, mit Dateirechten 0600. Nur HTTPS oder localhost-HTTP ist erlaubt.
Ressource für die separate Lovelace-Gästekarte: /smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=rc1, Kartentyp: custom:mittelhof-guest-card.
Kein Export von Gästedaten in Entity-Attribute, Recorder, Logbücher oder GitHub.

## Staging-Abnahme und Grenze

Nach Installation in einer isolierten HA-Testinstanz: alle fünf Hauptdashboard-Seiten, Wäsche/NUKI/IT.NRW prüfen; Testbuchung vorbereiten, Beträge korrigieren, DEMO-PDF mit Logo erstellen und veraPDF-Prüfung sowie Archiv/Korrektur abnehmen.
NOCH KEINE echte Rechnungsnummernzuteilung, GoBD-Aufbewahrung, steuerliche Freigabe, finaler PDF-Versand oder echte Rechnungskorrekturen. Diese Grenzen sind serverseitig erzwungen.

Die PRs bleiben bis zu einem echten HA-Stagingtest, formaler Steuerrichtlinie und Freigabe der entsprechenden Sicherheitsfunktionen zunächst im Entwicklungsstand.
