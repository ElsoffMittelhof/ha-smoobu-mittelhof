# Smoobu Workflow 0.7.1rc1 – getrennter Gäste-Arbeitsbereich

**Vorab-Release für eine HA-Testinstanz, kein automatisches Upgrade der installierten v0.7.0.** Das stabile v0.7.0 und die vorhandenen Wäsche-/NUKI-/IT.NRW-Funktionen bleiben unverändert.

## Neue Ansichten

Das Gäste-Dashboard besteht aus drei Ansichten, alle nur für HA-Administratoren:

1. **Posteingang:** Nur seit dem erstmaligen Aktivieren/Öffnen neu eingegangene Gastnachrichten und erkannte Neubuchungen. Es werden lokale gelesen-Markierungen ausschließlich in der privaten HA-Storage-Datei `smoobu_mittelhof.guest_inbox_state` verwaltet; dies verändert NICHT Smoobuus zentrale Ungelesen-Markierung. Beim ersten Start wird der vorhandene Verlauf als Basis genommen; deshalb erscheinen historische Gespräche nicht als neu. Neue Nachrichten werden anhand des tatsächlichen Smoobu-Nachrichtentyps 1 (Eingang), nicht nur anhand irgendeiner neuen Aktivität, erkannt. Ältere Gespräche finden sich über **Buchungen**.
2. **Buchungen:** Frei wählbarer Reisezeitraum (bis 731 Tage pro Abfrage) mit Suche nach Gastname, Haus und Buchungs-ID. Die Auswahl öffnet jederzeit den vollständigen Smoobu-Gesprächsverlauf zur Buchung.
3. **Rechnungen:** Separate, durchsuchbare Liste der in HA gespeicherten **Rechnungsentwürfe**, unabhängig vom Nachrichtenposteingang. Jeder Entwurf kann ausgewählt, überarbeitet und der eigene DEMO-ZUGFeRD-Vorschauprozess aufgerufen werden. **Rechtsverbindlich ausgestellte Rechnungen gibt es in der aktuellen Integration noch nicht.** Deshalb wird nichts als „ausgestellt/archiviert“ ausgegeben, was nur ein Entwurf ist.

Die beiden Editoren sind getrennt: Im Gespräch werden nur Nachrichten angezeigt/bearbeitet; im Rechnungsbereich nur Rechnungsdaten. Nachrichten werden weiterhin nur nach einer ausdrücklichen HA-Option und manueller Freigabe versendet.

### Separates Lovelace-Dashboard

Drei vollständige Views finden sich im **privaten** Projektbranch `feature/guest-center-0.7.1-private`, Datei `dashboards/gaeste-rechnungen.yaml` (Posteingang, Buchungen, Rechnungen). Das vorhandene fünfseitige Hauptdashboard `dashboards/mittelhof.yaml` wird nicht verändert. Alternativ einzelne Karten:

```yaml
type: custom:mittelhof-guest-card
view: invoices
```

Die JS-Ressource für dieses RC ist `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.1rc1`.

### Smoobu-Belegungsplan → Gespräch

Die vorhandene Timeline Card erhält den optionalen Konfigurationsparameter `guest_dashboard_path` mit dem **tatsächlichen** HA-Dashboardpfad, z. B.:

```yaml
type: custom:smoobu-timeline-card
guest_dashboard_path: /gaeste-rechnungen/buchungen
```

Die übrigen Timeline-Parameter (einschließlich `houses:`) bleiben wie bisher. Wenn die URL des Gästedashboards abweicht, diese reale URL verwenden, nicht einen geratenen Pfad. Nach Klick auf einen Belegungsbalken erscheint „Gespräch / Rechnungsentwurf öffnen“. Die Zielkarte übernimmt die Buchungs-ID aus `?booking_id=123...`, öffnet sie admin-geschützt und zeigt den Smoobu-Verlauf.

Timeline-JavaScript auf `/smoobu_mittelhof/frontend/smoobu-timeline-card.js?v=0.7.1rc1` ändern. Es wird kein zusätzlicher öffentlich zugänglicher Port geöffnet.

## Preispositionen und Anschrift

Der bisherige Code hat Smoobu-Preispositionen ausschließlich aus `GET /api/reservations/<id>?includePriceElements=true` importiert. Falls die Antwort keine `priceElements` enthält, fragt v0.7.1rc1 nun zusätzlich den dokumentierten Endpunkt `GET /api/reservations/<id>/price-elements` ab. Die Zeilen werden inkl. Betrag, Mengenangabe und Namen übernommen; bekannte Beherbergungsarten werden zu `rent`, `cleaning`, `dog` oder `extra_person` und der bestätigten Mittelhof-Policy mit 7 % zugeordnet. **Unbekannte Extras und abweichende Smoobu-Steuerangaben werden nicht erraten** und benötigen manuelle Kontrolle.

Das konkrete anonymisierte Betreiberbeispiel wird mit Regressionstests abgesichert:

| Smoobu-Quelle | Import | Brutto |
|---|---|---:|
| Base Price | Miete | 355 € |
| Reinigungsgebühr | Reinigung | 55 € |
| Haustier-Gebühr | Hund | 35 € |
| Gebühr für zusätzliche Gäste | zusätzliche Person | 30 € |
| **Gesamt** | | **475 €** |

Die Gastanschrift wird zusätzlich aus `GET /api/guests/<guestId>` gelesen. Länder werden nur bei eindeutigem Ländername/ISO-Code zu einem zweistelligen ISO-Code umgewandelt, andernfalls bleibt der Wert zur Prüfung offen.

**Vorhandene Entwürfe:** Ein unbearbeiteter automatischer Altentwurf kann aus vollständigen Smoobu-Details ergänzt werden. Bearbeitete Rechnungsentwürfe werden nicht automatisch überschrieben; hierfür steht ein gesondert zu bestätigender Import-Button zur Verfügung. Nach einem Import prüfen wir die Einzelpositionssumme gegen den Smoobu-Buchungsbetrag. Eine abweichende Quellsumme blockiert selbst die DEMO-Erzeugung: So wird bei einer bereits in Smoobu rabattierten Buchung nicht unbemerkt nochmals 10 % abgezogen. Die Nachlassregel selbst bleibt 10 % auf Gesamt-Miete ab 8 Nächten, Zusatzleistungen bleiben ungekürzt.

## Sicherheits- und Upgradegrenzen

- Alle neuen Smoobu-/HA-Listen-APIs `requires_auth` plus Admin-Prüfung; es werden keine Smoobu-Zugangsdaten, NUKI-PINs oder Gasttoken an den Browser weitergegeben.
- Posteingangs-Lesestatus ist HA-intern, nicht Smoobu-global.
- Historische Buchungen sind über Datum verfügbar; die Liste „Rechnungen“ enthält Entwürfe und keine erfundenen echten Rechnungen.
- Gastsenden ist weiterhin default OFF. Keine Änderung an den lokalen Wäsche- und Node-RED-Portaldaten oder dem fünffachen Hauptdashboard.
- Der separate private PDF-Dienst v0.7.0rc3 erzeugt weiterhin **nur DEMO**-Muster; es gibt keine rechtsverbindliche Rechnungsausstellung, keinen finalen GoBD-/WORM-Nachweis und keinen Gast-PDF-Versand.
- Ein echter HA-Laufzeittest an der Betreiberinstallation steht noch aus. Vor dem Installieren: HA-Backup und Rollback auf v0.7.0 sichern.
