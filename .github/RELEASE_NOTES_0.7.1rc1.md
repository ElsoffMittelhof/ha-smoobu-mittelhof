# Smoobu Workflow 0.7.1rc1 – Gästezentrum mit drei Ansichten

**Technisch geprüftes VORAB-Release**, nicht automatisch auf dem produktiven Home Assistant installiert. Das stabile HA-Release 0.7.0 bleibt bis zur Freigabe unverändert. Echte Rechnungsstellung und Gast-PDF-Versand sind nicht implementiert.

## Neue Bedienung

- **Posteingang:** Nur neu eingegangene Gastnachrichten (Eingangs-Typ 1) und nach Initial-Snapshot neu erkannte Buchungen. Neue Gastgeberantworten löschen keine ungelesenen Gasteingänge. Lokale HA-Gelesen-Marker, keine Smoobu-globalen Änderungen.
- **Buchungen:** Datumsbereich (bis zu 731 Tage je Suche), Filter für Gast, Haus, Buchungs-ID; öffnet jederzeit den vollständigen Gesprächsverlauf. Direkter Buchungssprung aus dem Smoobu-Belegungsplan über `guest_dashboard_path`.
- **Rechnungen:** Separate gefilterte Liste der vorhandenen **Rechnungsentwürfe** mit Auswahl, Bearbeitung und optionaler DEMO-PDF-Vorschau. Es existiert noch **kein Verzeichnis rechtsverbindlich ausgestellter Rechnungen**, denn die Funktion für deren Ausstellung fehlt.
- Erstes Laden der Ansicht ist sequenziell, damit keine Buchungs-/Rechnungslisten oder direkten Buchungslinks verloren gehen.
- Alle Ansichten ausschließlich für HA-Administratoren.

## Smoobu-Datenübernahme

- Buchungsdetail `GET /api/reservations/{id}?includePriceElements=true`; falls dort keine Positionen vorhanden sind, zusätzlich offizielles `GET /api/reservations/{id}/price-elements`.
- Beispiel aus der Betreiberbeobachtung: Miete 355 €, Reinigung 55 €, Hund 35 €, zusätzliche Person 30 € = **475 €**; eigene Regressionstests.
- Die Adress- und Landesdaten werden auch über `GET /api/guests/{guestId}` nachgeladen; zweistellige ISO-Ländercodes werden nur aus bekannten, eindeutigen Angaben übernommen.
- Vorhandene **unbearbeitete** Entwürfe können ergänzende Smoobu-Daten erhalten; bereits manuell bearbeitete Entwürfe werden nicht ungefragt überschrieben und besitzen einen separaten Neuimport mit expliziter Bestätigung.
- Warnungen bei unbekannten Extras, Nicht-EUR-Beträgen, abweichenden Steuerangaben und Gesamtbetrag-Differenzen. Ein nicht belegbarer zweiter 10-%-Nachlass wird vor dem DEMO-Beleg blockiert.

## Installation in einer HA-Testumgebung

1. Vollständiges HA-Backup, bestehende `0.7.0`-Integration und lokale Smoobu-Dateien sichern.
2. HACS-Vorabversion `0.7.1rc1` auswählen oder `smoobu-mittelhof-0.7.1rc1.zip` aus den Release-Assets entpacken.
3. HA neu starten, Wäsche/NUKI/IT.NRW und Smoobu-Zuordnung kontrollieren.
4. JS-Modulressourcen auf `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.1rc1` sowie `/smoobu_mittelhof/frontend/smoobu-timeline-card.js?v=0.7.1rc1` aktualisieren.
5. Separates Dashboard mit drei Views aus dem **privaten** Repository-Branch `release/0.7.1rc1-private`, Datei `dashboards/gaeste-rechnungen.yaml`, installieren. Dashboard URL-Pfad `gaeste-rechnungen`, oder im Timeline-Link den tatsächlichen Pfad eintragen.
6. Beim vorhandenen Smoobu-Timeline-Card-Eintrag zusätzlich `guest_dashboard_path: /gaeste-rechnungen/buchungen` setzen, übrige Haus-/Kalenderparameter nicht ändern. Nicht das fünffache Hauptdashboard durch ein Fragment ersetzen.
7. Nach Datenabgleich vorhandene Entwürfe nur bewusst neu importieren; der importierte Betrag muss weiterhin zum Smoobu-Quellbetrag passen.

**Unverändert:** Gastnachrichtenversand standardmäßig AUS; keine Produktiv-Rechnungsausstellung, kein GoBD-/WORM-Archiv, keine automatische PDF-Zustellung. Privater ZUGFeRD-Companion `0.7.0rc3` bleibt ein separates DEMO-System.

Eingefrorener, geprüfter Quellcommit: `1bce3bc456cea8e225ace520c152d5634a0d91e7`.
