# Smoobu Workflow 0.7.8 – Lexware L: Belegdatum und Fälligkeitsdatum

**Vollständige stabile Integrationsversion**, Veröffentlichung erst nach grüner CI. Die private Haupt-Dashboard-YAML mit fünf Views und die Gäste-Dashboard-YAML mit vier Views bleiben unverändert.

## Betreiberanforderung und Smoobu-Quelle

Beim manuellen Erfassen eines aus Smoobu erzeugten PDF-Buchhaltungsbelegs in Lexware Office L werden insbesondere **Belegdatum** und **Fälligkeitsdatum** verlangt. Nach Entscheidung des Betreibers sollen **beide dem ursprünglichen Buchungsdatum** entsprechen. Smoobu liefert es im Detail- und Listenendpunkt als `created-at` (beispielsweise `2026-11-09 15:43`). Nicht das spätere Anreise-/Abreisedatum, `modifiedAt` oder das aktuelle Exportdatum einsetzen.

**Interner Buchhaltungsbeleg, keine Gastrechnung:** Diese Datumsbelegung ist für die **Lexware-Einnahmenbeleg-Erfassung** bestimmt und bedeutet bei privaten Portalbuchungen **keine offene Zahlungsforderung**. Sie bestimmt bei Istversteuerung auch **nicht** den Zeitpunkt der Umsatzsteuerentstehung; der Bank-/Zahlungsabgleich bleibt in Lexware. Bei Direkt/TOMAS mit bereits ausgestellter Gastrechnung wird weiterhin die echte Rechnung referenziert, um Doppelumsätze zu vermeiden.

## Neue PDF- und Frontendfelder

Das PDF enthält neben Buchungsreferenz, Gast, Haus, Aufenthalt und Bruttobetrag drei explizite Datumszeilen:

```text
Buchungsdatum: 09.11.2026
Belegdatum: 09.11.2026
Fälligkeitsdatum: 09.11.2026
```

Die Buchhaltungsansicht zeigt Beleg-/Fälligkeitsdatum bereits vor der Freigabe. Die Beträge und die 7%-USt-Vorbelegung bleiben unverändert. Lexware-PDF-Texterkennung kann die Werte als Vorschlag übernehmen, deren tatsächliche automatische Feldzuordnung ist jedoch **nicht garantiert**; bitte bei jedem Upload kontrollieren.

Technisch: `accounting_core.py` übernimmt ausschließlich `created-at` mit Kalenderprüfung, `approve_snapshot()` sichert `booking_created_at`, `document_date` und `due_date` im unveränderlichen `mittelhof.accounting.v3`-Snapshot und aktualisiert den PDF-Inhalt. Fehlendes/ungültiges Smoobu-Datum führt zu einem ausdrücklichen Prüfhinweis und einer gesperrten Freigabe. `accounting_portal.py` erkennt ältere v2-Snapshots; vor **neuem** Einzel-PDF-, ZIP-Export oder nachträglicher manueller Lexware-Uploadmarkierung sind v3-Datumsfelder notwendig. Historische in Lexware verbuchte/hochgeladene Belege dürfen nicht still überschrieben werden; eventuelle Korrekturen manuell abstimmen. Kein Datenbank-Reset und keine automatische Datenmigration.

## Sichere Installation auf dem einzigen Home Assistant

1. Vollständiges HA-Backup und aktuelle Integrations-/Ressourcenstände sichern.
2. Nach vollständiger GitHub-CI-Prüfung das stabile Release v0.7.8 über HACS installieren. **Home Assistant vollständig neu starten**, da Python-Backend und PDF-Erstellung geändert wurden.
3. In Einstellungen → Dashboards → Ressourcen die bestehende `JavaScript-Modul`-Ressource **ändern**, nicht duplizieren:
   `/smoobu_mittelhof/frontend/mittelhof-accounting-card.js?v=0.7.8`.
   App/Browser neu laden. Die Timeline- und Gäste-JS-Karte sind in diesem Release unverändert.
4. Gästeverwaltung unter `/gaste-rechnungen-dashboard/buchhaltung` öffnen, Smoobu-Buchung auswählen. Prüfen, ob **Belegdatum = Fälligkeitsdatum = ursprünglicher Buchungstag**. Gastpreis, Haustier, Reinigung und Zusatzgast weiterhin getrennt von Provisionen/Abrechnungen behandeln.
5. Nach Steuer-/Belegprüfung PDF herunterladen, dort beide Datumsfelder überprüfen und in Lexware-L-`Belege erfassen` als Einnahmenbeleg hochladen. Die manuelle Zuordnung von Kunde, Kategorie und Steuer sowie die Datenerkennung in Lexware prüfen; die tatsächliche Bankzuordnung liegt weiterhin in Lexware.
6. Bei noch offenen v2-Altbelegen neue geprüfte Revision erstellen. Ein bereits in Lexware hochgeladener Beleg ist gesperrt; zur Änderung gilt der manuelle Korrekturprozess.
7. Wäsche, NUKI, IT.NRW, Gastnachrichten und die Uberspace-Wäsche-Bestandsführung nach Update kontrollieren. Gastversand, echte Gastrechnungs-Ausstellung und Lexware-API-Schreibzugriff bleiben AUS.

## Rückfall

Bei Laufzeitproblemen HACS auf **v0.7.7** zurückstellen, HA neu starten, Buchhaltungskarte wieder `?v=0.7.7` referenzieren. Die private HA-Storage-Datei und gespeicherte Belegrevisionen **nicht löschen**. Keine automatische Installation der Software durch GitHub-Veröffentlichung.
