# Mittelhof Smoobu Workflow 0.7.0rc3 – Vorab-Release (DEMO)

**Kein Produktiv-Release für rechtsverbindliche Rechnungen.** Dies ist eine technisch geprüfte Vorabversion für einen isolierten Home-Assistant-Testbetrieb.

## Enthalten

- Bestehende NUKI-, Wäsche- und IT.NRW-Workflows bleiben enthalten.
- Separate admin-only Gäste-/Nachrichten-/Rechnungsentwurfsansicht mit geschützter Smoobu-Anbindung.
- 7-%-Leistungskatalog: Miete, Reinigung, maximal zwei zusätzliche Personen, maximal zwei Hunde und Mietdauernachlass.
- **Ab 8 Übernachtungen 10 % Nachlass auf die gesamte Brutto-Miete**, keine Rabattierung von Reinigung, Personen oder Hunden. 7 Nächte: kein Rabatt. Centgenaue Rundung und serverseitige erneute Kontrolle im privaten Dienst.
- Rechnungsnummernvorschau: Haus 13/14/15 + JJJJMMTT des Anreisetags.
- Admin-only DEMO-ZUGFeRD-Muster-PDF, PDF/A-Prüfung, Musterfreigabe, Korrekturhistorie und Testarchiv über einen **separat zu installierenden privaten Rechnungsdienst**.
- Gast-Nachrichtenversand standardmäßig **AUS**. Es gibt **keine** Funktion zur echten Rechnungsausstellung oder zum Rechnungsversand.

## Manuell installieren – erst auf Test-HA

1. GitHub-Release-Asset `smoobu-mittelhof-0.7.0rc3.zip` beziehen.
2. Vorher Home-Assistant-Backup und Rückweg zur bisherigen v0.6.8 anlegen.
3. ZIP so entpacken, dass `custom_components/smoobu_mittelhof/` im HA-Konfigurationsverzeichnis liegt; HA im Testsystem neu starten.
4. Die **separate** Gäste-Lovelace-Karte aus `custom_components/smoobu_mittelhof/frontend/mittelhof-guest-card.js` laden.
5. Den privaten Companion ausschließlich nach der Anleitung im privaten Repo `mittelhof-homeassistant`, Datei `invoice_engine/RELEASE_CANDIDATE.md`, konfigurieren. Ohne private Konfiguration gibt es keine PDF-Erzeugung.
6. Smoobu-Buchung, Zahlungsfluss, Übernachtungszahl, Rabatt und PDF/A-Muster manuell testen, bevor ein produktives Upgrade erwogen wird.

Das ZIP ist das **manuelle HA-Installationspaket**. HACS kann alternativ die Version aus dem GitHub-Prerelease-Tag lesen; es muss ausdrücklich die Vorabversion gewählt werden. Die Prüfsumme steht in `SHA256SUMS.txt`.

## Noch nicht freigegeben

Keine Produktivinstallation, keine finale Steuergenehmigung, keine externe/revisionssichere GoBD-Archivierung, keine finalen Korrekturbelege, kein Versand von Rechnungs-PDFs. Das private Archiv ist ein testbares Musterarchiv, keine WORM-Ablage. Die Produktivversion bleibt unverändert.

Versionsquelle (eingefrorener Commit): `63c96b4ceda8f5f2c0b632f411bb17eeec581e13`.
