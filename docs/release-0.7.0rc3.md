# Smoobu Workflow 0.7.0rc3 – Release-Kandidat

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

## Änderung 0.7.0rc3 – bestätigter Mittelhof-Leistungskatalog

Der Gast-Rechnungskarteneditor verwendet jetzt einzelne strukturierte Positionen statt JSON:
1. Miete (genau 1).
2. Reinigung der Unterkunft (höchstens 1).
3. Zusätzliche Person (insgesamt höchstens 2).
4. Hund in der Unterkunft (insgesamt höchstens 2).
5. Nachlass abhängig von der Mietdauer (negativ, höchstens 1, mit manuell bestätigter Staffel/Regel und geprüfter Anzahl Übernachtungen).

Für die genannten Beherbergungsleistungen ist die Betreiber-Policy 7 % Umsatzsteuer. Alle anderen/nicht identifizierten Smoobu-Preise müssen manuell klassifiziert werden; kein automatisches Raten. Die HA-Validierung und der private Rechnungsdienst kontrollieren Kategorie, Menge, Steuersatz und Rechnungsbrutto unabhängig. Die Positionssumme wird centgenau berechnet.

Die private Finanzkonfiguration ist ausschließlich im privaten Projekt dokumentiert. Das öffentliche Repository enthält niemals die Namen/Anschriften/Kontonummern des konkreten Betreibers.

Grundlage für 7 % bei Reinigung/Tieren im überlassenen Wohn- und Schlafraum: § 12 Abs. 2 Nr. 11 UStG, UStAE 12.16 Abs. 4. Keine Einstufung fremder Zusatzleistungen ohne eigene steuerliche Prüfung.

Die Höhe und Schwellen der Mietdauernachlässe wurden noch nicht angegeben. Es findet KEINE automatische Rabattberechnung statt. Eine echte Rechnungsstellung, ein Live-Deployment und ein Rechnungsversand sind weiterhin gesperrt.

## RC3: feste Mietdauerrabattstaffel

Ab 8 Übernachtungen beträgt der Nachlass 10 % auf die **gesamte Brutto-Miete** (einschließlich der ersten sieben Nächte), nicht auf separat berechnete Reinigung, zusätzliche Personen oder Hunde. Bei 1–7 Nächten ist kein Mietdauernachlass zulässig. Die HA-Integration erstellt beim Speichern einer manuell als Miete zugeordneten Position die negative Rabattzeile und korrigiert die Bruttosumme mit centgenauer kaufmännischer Rundung automatisch. Bei unklarer Zuordnung aus Smoobu wird weder Miete noch Rabatt geraten. Die private ZUGFeRD-DEMO-Engine validiert die Staffel unabhängig. Regressionstests erfassen 7/8/9 Nächte, Geldrundung und doppelte Speicherung. Keine echte Rechnungsausstellung.
