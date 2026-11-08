# Smoobu Workflow v0.7.3 – korrigierte Buchhaltungsverwaltung für Lexware Office L

## Release-Charakter

Vollständiges stabiles Integrationsrelease, keine Testversion; Installationsstand aus HACS erst nach Backup im einzigen produktiven Home Assistant kontrolliert aktivieren. Das bisherige v0.7.2 bleibt als unverändertes Rollback-Release erhalten.

## Gastumsatz versus Portalabrechnung

Bei Airbnb werden die Smoobu-Positionen `Commission`, `Cancellation Host Fee` und `Cancellation Payout` aus dem **Gastumsatzbeleg** herausgehalten. Sie werden als separat zu behandelnde Provider- bzw. Stornopositionen angezeigt. Die Provision gehört zu einem eigenen Airbnb-Abrechnungs-/Provisionsbeleg und wird **nicht** als neue Gastumsatzposition in Lexware erzeugt. Die Stornopositionen sind ebenfalls nicht Bestandteil der regulären Gastpreisrechnung; die gesonderte Behandlung von realen Storno-/Ausgleichsfällen ist buchhalterisch zu prüfen. Die bekannten Gastpositionen `Base Price`, `Cleaning Fee`, `PASS_THROUGH_PET_FEE` und `Additional Guest Fee` bilden in der Nutzerprobe 355+55+35+30=475 EUR. Kein Abzug des 73,63-EUR-Provisionsbetrags vom Gastumsatz.

Der Export prüft das **verbindliche Smoobu-Gastbrutto gegen die ausgewählten Gastpositionen**; uneindeutige oder abweichende Daten sind zunächst gesperrt. Jede einzelne Umsatzsteuerklasse ist **fachlich manuell zu prüfen**; der angezeigte Smoobu-Satz ist nur ein Vorschlag, keine Steuerfreigabe.

## Bearbeitbarer Gastbeleg

In der vierten Gäste-Dashboardseite `Buchhaltung` kann der HA-Administrator vor PDF-Freigabe einzelne Preispositionen abwählen, Texte und Beträge bearbeiten sowie je Position 0%, 7% oder 19% auswählen. Auch nach manuellen Korrekturen **muss die Summe exakt dem Gastbrutto der Smoobu-Buchung entsprechen**. Sonst bleibt das PDF gesperrt. Änderungen und ausgeschlossene Zeilen werden im geprüften Snapshot samt Hash gespeichert und beim Wiederöffnen angezeigt. Ein bereits als in Lexware hochgeladen markierter Beleg kann nicht still verändert werden. PDF/ZIP bleiben interne Buchungsnachweise, keine Gastrechnungen und keine Steuer-/Zahlungseinträge.

## Gastrechnung statt zweitem Buchhaltungsbeleg

Bei eindeutig als `Direkt` bzw. `TOMAS` identifizierten Buchungen schlägt die Ansicht **Gastrechnung vorgesehen** vor. Bei Homepage-Buchungen entscheidet der Betreiber anhand der tatsächlichen Zahlungsart; diese lässt sich aus dem Smoobu-Kanal nicht sicher ableiten. Eine **bereits tatsächlich ausgestellte und in Lexware erfasste** Gastrechnung kann mit ihrer externen Nummer/Referenz verbunden werden. Dann wird **kein zweiter Umsatzbeleg** erzeugt oder in den Sammel-PDF-Export aufgenommen. Bestehende Rechnungsreferenzen und manuell als hochgeladen markierte PDFs können nicht ohne Korrekturverfahren überschrieben werden. Diese Referenzierung **erstellt keine Rechnung**, vergibt keine Rechnungsnummer und sendet keine Nachricht. Noch nicht ausgestellte Rechnungen bleiben nur *vorgesehen*.

## Dashboard-Korrektur

Die reale Home-Assistant-URL lautet laut Betreiber `gaste-rechnungen` (nicht `gaeste-rechnungen`). Die private Projektdatei wurde zentral **umbenannt** in `dashboards/gaste-rechnungen.yaml` und wird nicht separat vom Repository gepflegt; die alte `dashboards/gaeste-rechnungen.yaml` wurde entfernt. Die komplette private `dashboards/mittelhof.yaml` enthält weiter sämtliche bisherigen fünf Ansichten und die **vier** reparierten Timeline-Links `guest_dashboard_path: /gaste-rechnungen/buchungen`. Kein direktes Bearbeiten von HA-`.storage`.

## Kontrollierte Installation auf dem einzigen HA

1. Vollständiges HA-Backup erstellen und den bestehenden HACS-/Dashboard-/Wäsche-/NUKI-/IT.NRW-Status dokumentieren.
2. Vollständige HACS-Integration v0.7.3 installieren, HA neu starten. Gast-Nachrichtenversand AUS lassen; echte Rechnungsausstellung bleibt ausgeschaltet.
3. Lovelace-JavaScript-Ressourcen nur einmal als **JavaScript-Modul** registrieren bzw. Cache-Parameter aktualisieren:
   - `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.3`
   - `/smoobu_mittelhof/frontend/smoobu-timeline-card.js?v=0.7.3`
   - `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.3`
4. Beide **vollständigen** privaten Dashboards übernehmen: `dashboards/mittelhof.yaml` mit fünf Views sowie `dashboards/gaste-rechnungen.yaml` mit vier Views. Vorhandenes Gäste-Dashboard URL-Slug `gaste-rechnungen` beibehalten; keine doppelte Dashboard-Registrierung.
5. Gäste-Buchungen und Timelinelinks testen. Nutzerprobe mit 475 EUR nachprüfen; nur 4 Preispositionen sind relevante Gastkosten, 3 separat behandelte Positionen dürfen kein PDF-Brutto aufblasen. PDF-Änderungen und Sperren sowie Gastrechnungsreferenz testen. Nur steuerlich geprüfte echte Belege in Lexware hochladen.
6. Wäsche-/NUKI-/IT.NRW-Workflows sowie Uberspace-Portalbestand unverändert prüfen. Bei Fehlern HACS-Integration auf v0.7.2 und Dashboards auf bisherigen GitHub-Stand zurückstellen; bei beschädigten HA-Daten geprüftes Backup nutzen.

## Daten und fachliche Grenzen

Die private HA-Store-Datei `smoobu_mittelhof.accounting_records` kann auf v0.7.2 erzeugte Einträge enthalten. Diese werden **nicht** automatisch verändert oder gelöscht. Bereits als hochgeladen markierte alte Belege bleiben gesperrt, bis eine manuelle buchhalterische Korrektur durchgeführt ist. Die Abbildung der Portalprovision als separater Beleg und die Steuerklassifikation sind weiterhin vom Steuerberater/Betreiber zu prüfen. Kein Lexware-API-Schreibzugriff im L-Tarif, kein automatischer Bankabgleich, keine endgültige Gastrechnung und kein GoBD-Archiv.
