# Smoobu Workflow v0.7.1 – Gästeverwaltung, Produktivpaket

Version 0.7.1 ist ein vollständiger stabiler **Code-Release-Kandidat aus dem geprüften Funktionsstand 0.7.1rc1**. Die Veröffentlichung ist getrennt von der Installation auf dem einzigen Home-Assistant-System. Eine erfolgreiche GitHub CI ersetzt keine reale Smoobu-/HA-Abnahme.

## Funktionen

- **Posteingang**: ausschließlich nach dem initialen Snapshot neue Gastnachrichten (eingehend Typ 1) und Neubuchungen; historische Nachrichten bleiben in der Buchungsansicht verfügbar. HA-lokale Lesemarker, Smoobu-Gelesenstatus unverändert.
- **Buchungen**: frei wählbarer Zeitraum bis 731 Tage je Suche, Filter für Haus/Gast/Booking-ID, selektierbare vollständige Konversation. Timeline-Deep-Link via `guest_dashboard_path: /gaeste-rechnungen/buchungen`.
- **Rechnungen**: unabhängig selektierbare und bearbeitbare **Entwürfe**, keine ausgestellten Belege. DEMO-ZUGFeRD nur mit separat konfiguriertem privatem Dienst; weder endgültige Ausstellung noch Versand oder GoBD-Archiv.
- Detailabruf von Smoobu-Preispositionen mit Fallback `/api/reservations/{id}/price-elements`; Gastland ggf. per `/api/guests/{guestId}`. Unbekannte Positionen/Steuerdaten erfordern Prüfung. Beispiel 355 + 55 + 35 + 30 = 475 EUR.
- Manuelle Entwurfsänderungen bleiben geschützt; Neuimport nur explizit mit Revision; Differenzen zur Smoobu-Quellsumme verhindern DEMO-PDF.

## Auslieferung auf EIN Home Assistant

1. Vollständiges Home-Assistant-Backup anlegen, außerhalb des HA-Hosts erreichbar sichern und Wiederherstellbarkeit prüfen. Konfiguration, Smoobu-Credentials und lokalen Pfad `/config/smoobu_mittelhof/` sichern. Die Wäsche-/Portalreplikation vor dem Upgrade dokumentieren (Bestand, Revision, offene Bestellungen).
2. Sicherstellen, dass die vorherige Version **0.7.0** über GitHub Release/HACS wieder verfügbar ist. Keine Löschung von `.storage` oder lokalen Wäsche-Konfigurationsdateien.
3. Nur das durch CI und Release-Asset-Checksumme verifizierte GitHub-Release v0.7.1 per HACS installieren, Home Assistant neu starten. Die Installation ist eine kontrollierte Produktivänderung, kein automatischer Deployment-Schritt der CI.
4. Gastkarte **genau einmal** als Lovelace-JavaScript-Ressource: `/smoobu_mittelhof/frontend/mittelhof-guest-card.js?v=0.7.1`; Timeline-Ressource entsprechend `/smoobu_mittelhof/frontend/smoobu-timeline-card.js?v=0.7.1`. Browser-/Companion-App-Cache aktualisieren.
5. Privates dreiseitiges Dashboard `dashboards/gaeste-rechnungen.yaml` als YAML-Dashboard mit **URL-Slug `gaeste-rechnungen`** registrieren. Das komplette private `dashboards/mittelhof.yaml` (fünf Views) aus dem zum Release gehörigen Commit einspielen, nicht einzelne Fragmente.
6. **Vor Aktivierung** von `guest_portal_enabled`: Wäsche, NUKI, IT.NRW, bestehende Entity-IDs und Portalreplikation prüfen; keine realen Mails oder Bestellungen auslösen. Danach Gastportal kontrolliert aktivieren, initiales Inbox-Baselineverhalten, Filter, Smoobu-Preispositionen und Konversationslink mit vorhandenen Buchungen verifizieren.
7. `guest_message_send_enabled=false` beibehalten. Rechnungsentwürfe auf Preis, Steuersatz, Land und Rabatt prüfen; kein echter Rechnungsversand oder endgültiger PDF-Ausstellungsprozess.

## Rückfall

Bei kritischem Fehler Gastportal und Gastnachrichtenversand deaktiviert halten, Integration über HACS auf 0.7.0 zurückstellen, Home Assistant neu starten, bisherigen Dashboard-Stand aus GitHub wiederherstellen und Status von Wäsche-/NUKI-/Portalreplikation kontrollieren. Keine pauschalen Workflow-Resets durchführen. Wenn Datenspeicher beschädigt ist, ausschließlich geprüftes HA-Backup verwenden.

## Grenzen

GitHub-Checks testen Code/Frontend/HA-Metadaten, nicht die tatsächlich vorhandene einzige HA-Instanz oder die konkreten Smoobu-Daten. Ein Commit, CI-Erfolg oder HACS-Release ist deshalb keine Behauptung, das Upgrade sei auf der laufenden Installation abgenommen. Gastdaten bleiben admin-geschützt; keine echten Gastmails oder Rechnungen ohne ausdrücklich separate Freigabe.
