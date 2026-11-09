# Smoobu Workflow v0.7.7 – Belegfreigabe HTTP 404: Ursache und korrigierte API-Routen

**Vollständige stabile Produktivversion, keine RC.** Nur veröffentlichen, wenn vollständige GitHub-Prüfungen grün sind. Einzige HA-Produktivinstallation bleibt bis zur gesicherten manuellen Aktualisierung unverändert.

## Nachgewiesene Fehlerursache

Browser-Netzwerkaufzeichnung: `POST /api/smoobu_mittelhof/guest/v1/bookings/{id}/accounting` antwortet wörtlich mit `404: Not Found`, während dieselbe Buchung über GET erfolgreich geladen wird. Im bestehenden Quellcode wird die allgemeine Route `/bookings/{booking_id}/{action}` für **POST** von `GuestMessageActionView` vor der spezifischen Accounting-Route registriert. Bei der Aktion `accounting` gibt der Nachrichtenhandler `web.HTTPNotFound()` zurück. Das erklärt exakt, warum GET funktioniert und POST 404 liefert. Der Umsatzsteuersatz, die Smoobu-Preispositionen und die doppelte Smoobu-Abfrage aus v0.7.6 waren **nicht die Ursache** dieses 404.

## Definitive Korrektur

1. In `guest_portal.py` darf `GuestMessageActionView` nur `/bookings/{id}/{action:regenerate|approve|send}` bedienen. Unzulässige Aktionsnamen einschließlich `accounting` dürfen die Nachrichtenroute gar nicht mehr matchen.
2. In `__init__.py` werden die spezifischen Accounting-Views vor allgemeinen Gäste-Views registriert, als zweite Schutzschicht.
3. Die echten Buchhaltungs-Endpunkte und die Administratorprüfung/Quell-, Brutto-, Steuer- und Revisionsvalidierung bleiben unverändert. Nur die Route wird zuverlässig erreicht.
4. Offline-Regressionsprüfung `tests/test_accounting_router_collision.py` gegen das Verwechseln von Accounting-POST und Nachrichtenaktions-POST. Python-/JS-/hassfest-/HACS-Volltests bleiben Release-Pflicht.

## Kontrollierte Installation auf EINEM Home Assistant

1. Vollständiges Home-Assistant-Backup erstellen und bisher installierte HACS-Version und Dashboard-Ressourcen sichern.
2. Stabiles vollständiges HACS-Release v0.7.7 installieren und **Home Assistant vollständig neu starten**, damit die neue Python-API-Routenregistrierung aktiviert wird. Ein Cache-Reload ohne Neustart reicht nicht.
3. Die Buchhaltungs-JavaScript-Karte selbst ist funktional gegenüber v0.7.6 unverändert. Eine bestehende Ressource `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.6` kann bestehen bleiben; optional die Cacheversionskennung einmalig auf `?v=0.7.7` aktualisieren. Keine Ressourcen duplizieren.
4. Das volle private Hauptdashboard `dashboards/mittelhof.yaml` mit fünf Views und das Gäste-Dashboard `dashboards/gaste-rechnungen.yaml` mit vier Views bleiben unverändert. Tatsächlicher HA-Dashboard-Pfad: `/gaste-rechnungen-dashboard/buchhaltung`.
5. Bestehenden Airbnb-Testfall 475 EUR aufrufen, vier Gastpreispositionen mit 7%-Vorbelegung prüfen, dann einmal `Steuern prüfen und PDF freigeben`. Nach der Freigabe sollte `PDF herunterladen` aktiv werden. Bei fachlich bedingten 409-Meldungen nur die fachliche Validierung prüfen, nicht die Routen umstellen.
6. Gast-Nachrichtenentwürfe und Aktionen (regenerate, approve), Wäsche, NUKI, IT.NRW und Portal-Wäsche-Bestandsabgleich kontrollieren. Gastnachrichtenversand bleibt AUS; echte Rechnungsausstellung und direkter Lexware-API-Import bleiben AUS. Keine doppelte Einnahme bei bereits bestehender Gastrechnung nach Lexware übernehmen.

## Rückfall

Bei einer Störung HACS auf v0.7.6 zurückstellen und Home Assistant neu starten. Keine HA-`.storage`- oder Buchhaltungsdaten löschen. Die neuen Routenänderungen erzeugen keine Migrationen und keine Gastnachrichten. Für unerwartete HA-Probleme gesichertes Backup nutzen.

**Der veröffentlichte GitHub-Quellstand allein bedeutet keine automatische Installation im HA.**
