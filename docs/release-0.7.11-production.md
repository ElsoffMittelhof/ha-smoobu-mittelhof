# Smoobu Workflow v0.7.11 – Buchungsbelege mit echten Smoobu-Rabatten

**Vollständige stabile HACS-Version.** Fehlerkorrektur bei der manuellen Freigabe von Lexware-L-Buchhaltungsbelegen. Die bestehende Integration bleibt funktional vollständig; Gastnachrichten werden nicht automatisch versendet und es werden keine Gastrechnungen ausgestellt.

## Behebung des HTTP-409-Fehlers

Bei einer Website-Buchung von Haus 13 wurde der Beleg durch die negative Gastpreisposition `Long stay discount` bisher fälschlich abgelehnt:

| Gastpreisposition | Gastbrutto |
|---|---:|
| Base price | 840,00 EUR |
| Long stay discount | −70,06 EUR |
| Cleaning fee | 55,00 EUR |
| Hund | 84,00 EUR |
| **Summe** | **908,94 EUR** |

Die vorige Validierung `accounting_core._edited_rows()` verbot jeden Betrag kleiner/gleich Null, obwohl `prepare_booking()` die echte Smoobu-Rabattzeile korrekt übernahm und das Frontend alle Zeilen zur steuerlichen Prüfung übermittelte. Der Backend-Fehler wurde als HTTP 409 Conflict angezeigt.

**v0.7.11 akzeptiert echte negative Gastpreispositionen** und liefert diese signiert in die interne PDF-Buchhaltungsfreigabe. Normale Gastleistungen bleiben positiv. Nullbeträge und Vorzeichenwechsel relativ zur originalen Smoobu-Position sind gesperrt. Unverändert bleiben:
- Centgenauigkeit und **exakte Übereinstimmung** mit dem autoritativen Smoobu-Gastbrutto.
- Explizite USt-Prüfung je Position; negative Rabattzeilen haben ein entsprechendes negatives Steueranteil.
- Getrennte Behandlung von Plattformprovision und Storno-Abrechnungen (keine Gastumsätze).
- Source-Fingerprint-Prüfung, Bearbeitungs-/Änderungsprüfung, schreibgeschützte revisionsgebundene Snapshots, Hash und Dublettenschutz.
- Buchhaltungsbeleg ist **keine Gastrechnung**. Kein automatischer Lexware-Upload und kein Zahlungsnachweis.

## Bestehenden produktiven Datenbestand unbedingt erhalten

Auf dem einzigen produktiven Home Assistant zeigt das Buchhaltungsportal inzwischen unter anderem **2 geprüfte PDFs und 3 als hochgeladen markierte Belege**. Diese Daten dürfen nicht gelöscht oder überschrieben werden.

Das Update verändert **keine** Datenbank-Schemas oder `.storage`-Schlüssel. Das bestehende `mittelhof.accounting.v5`-Belegformat bleibt erhalten. Bereits hochgeladene Belege dürfen nicht durch neue Versionen „erneut“ in Lexware erfasst werden. Für einen schon in Lexware gebuchten Beleg erfolgt eine notwendige Korrektur getrennt und manuell nach Buchhaltungsprüfung.

**Installationsschritte:**
1. **Vor dem Update ein vollständiges HA-Backup** mit Konfiguration, `.storage`, `/config/smoobu_workflow/`, allen Gästen/Buchhaltungsdaten, vorhandenen Dashboard-Dateien und ESPHome-Backup erstellen. Backup extern aufbewahren. Nicht mit einem leeren Datenverzeichnis neu installieren.
2. HACS → Smoobu Workflow → Version **v0.7.11** installieren. Kein Patch von einzelnen Dateien.
3. Home Assistant **vollständig neu starten**.
4. Den **bereits vorhandenen** Lovelace-Ressourceneintrag für die Buchhaltungskarte **ersetzen**, nicht duplizieren: `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.11`. Cache/Browser/App neu laden.
5. Einstellungen → Geräte & Dienste → Smoobu Workflow: Funktionsfähigkeit der HMAC-signierten API und Buchungs-/Hausdaten prüfen.
6. In Gästeverwaltung/Buchhaltung zuerst die bereits vorhandenen **geprüft/hochgeladen**-Status kontrollieren; keine Änderungen an diesen Belegen vornehmen.
7. Bei einer **noch nicht freigegebenen** Buchung mit negativem Smoobu-Rabatt die Position und die Gesamtbruttosumme kontrollieren. Alle Gastpositionen und Steuersätze manuell bestätigen, „Steuern prüfen und PDF freigeben“, PDF prüfen und erst dann **manuell** in Lexware übertragen. Bei der Musterbuchung exakt 908,94 EUR Gesamtbrutto.
8. Nuki-Gastcode-Abläufe, Wäsche, IT.NRW und bestehende Gast-/Haus-Dashboards nach dem Neustart kontrollieren. Gastversand und Rechnungsausstellung bleiben deaktiviert.

**Rollback:** HACS-Version v0.7.10 installieren, Home Assistant neu starten und die bestehende Dashboard-Ressource wieder auf `?v=0.7.10` setzen. **Keine** `.storage`-Buchhaltungsdaten, Gäste-/Wäschehistorie oder Beleg-Snapshots löschen. Falls mit v0.7.11 neue Belege mit Negativpositionen geprüft wurden, sollten diese nicht unter v0.7.10 erneut freigegeben oder verändert werden: die alte Version würde den früheren Fehler wieder auslösen.

## Qualitätssicherung

- Python-Paket-Kompilation und alle bestehenden Regressionsprüfungen (Gastverwaltung, Wäsche, Nuki, Smoobu, Buchhaltung, IT.NRW).
- Neue Python-Regression für 840 − 70,06 + 55 + 84 = 908,94 EUR mit PDF-Ausgabe, Vorzeichenverbot, Nullbetrag und Summenabweichung.
- JavaScript-Syntax- und Eingaberegression für positive und negative Preise, bestehende Home-Assistant-UI-Tests.
- HACS und hassfest Validierung im automatischen Release-Workflow.

**Wichtig:** Ein erfolgreicher GitHub-Release bedeutet noch nicht, dass v0.7.11 in Home Assistant installiert oder dort getestet ist.
