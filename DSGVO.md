# DSGVO-Konformität – Clownfischserver v0.5.0

> Dieser Stand bezieht sich auf v0.5.0. Frühere Versionen erfüllen nicht den vollen
> Funktionsumfang. v0.6.0 erweitert um Transport-Verschlüsselung und Backup-Konzept.

Clownfischserver ist als **Gateway für lokal gehostete LLMs in Unternehmens­umgebungen**
positioniert. Datenschutz ist kein Add-on, sondern strukturelle Voraussetzung.

Verantwortlich für die DSGVO-konforme Konfiguration im konkreten Einsatz bleibt
**der Betreiber**. Dieses Dokument beschreibt, welche technischen Maßnahmen die
Software dafür bereitstellt.

---

## Art. 5 DSGVO – Grundsätze der Verarbeitung

### Art. 5 (1) (a) – Rechtmäßigkeit, Verarbeitung nach Treu und Glauben, Transparenz

Jeder privilegierte Vorgang wird im Audit-Trail (`audit.jsonl`) protokolliert:

- Wer hat was wann ausgeführt? (`/shell`, `/code`, `/run`, `/ja`, `/ssh`, `/snapshot`, `/rollback`)
- Welches LLM-Modell hat eine Antwort generiert? (Audit-Event `llm.route`)
- Welche Zugriffe wurden abgelehnt? (`result: denied`)

Operatoren können den Trail jederzeit via `/logs` einsehen
(`bot/audit_query.py`, `cmd_logs` in `bot/bot.py`).

### Art. 5 (1) (b) – Zweckbindung

`/shell` und `/code` benötigen eine explizite Bestätigung durch einen Approver
(`/ja`). Dieser Approval-Flow ist nicht umgehbar: jeder Befehl wird *vor* der
Ausführung als Vorschlag im Chat dargestellt, der ausführende Approver
hinterlässt seinerseits einen Audit-Eintrag (`shell.approval`).

### Art. 5 (1) (c) – Datenminimierung

- Audit-Einträge enthalten **nur die numerische Telegram User-ID** – keine
  Klarnamen, keine Telegram-Usernames, keine E-Mail-Adressen.
- Befehlstexte werden auf `AUDIT_MAX_DETAIL_LEN` Zeichen (Default 2000) gekürzt.
  Konfigurierbar via `.env`.
- Es findet **keine Telemetrie nach außen** statt. Sämtliche LLM-Calls können
  konfigurationsabhängig vollständig on-prem gehalten werden
  (`LLM_PRIMARY_PROVIDER=ollama`, `LLM_FALLBACK_PROVIDER=none`).

### Art. 5 (1) (d) – Richtigkeit

Audit-Einträge enthalten Eingaben (`description`, `command`) **und** Ergebnis
(`returncode`, ggf. `stderr`). Falschmeldungen lassen sich gegen den realen
Server­zustand verifizieren.

### Art. 5 (1) (e) – Speicherbegrenzung

`audit_log.prune_old_logs()` läuft beim Bot-Start und entfernt Einträge,
die älter als `AUDIT_RETENTION_DAYS` (Default 90 Tage) sind.

- `AUDIT_RETENTION_DAYS=0` deaktiviert das Pruning bewusst (z. B. für
  forensische Anforderungen mit längerer Aufbewahrungspflicht).
- Das Pruning nutzt einen atomic-rename, sodass auch ein Crash während des
  Bereinigungslaufs keine Audit-Lücken erzeugt.

### Art. 5 (1) (f) – Integrität und Vertraulichkeit

- Audit-Datei wird nach jedem Append auf `0600` gesetzt (nur Eigentümer
  lesbar/schreibbar). Auf Windows-Filesystemen ohne POSIX-Permissions wird
  der Schreibvorgang nicht blockiert, sondern lediglich geloggt – Produktion
  läuft per `install.sh` auf Linux.
- Sämtliche LLM-Kommunikation kann ausschließlich lokal stattfinden
  (Ollama via `127.0.0.1:11434`). OpenRouter-Fallback ist **opt-in**.

---

## Art. 32 DSGVO – Sicherheit der Verarbeitung

### Art. 32 (1) (a) – Pseudonymisierung

Audit-Einträge speichern numerische User-IDs, keine Namen oder Handles.
Die Zuordnung User-ID → Person verbleibt beim Betreiber, außerhalb der Software.

### Art. 32 (1) (a) – Verschlüsselung

- **In v0.5.0 nicht enthalten**: Die Audit-Datei liegt unverschlüsselt im
  Filesystem. Schutz erfolgt ausschließlich über Dateisystem-Permissions
  (`0600`, `MGMT_USER`).
- **Plan für v0.6.0**: HTTPS-only Webhook-Endpoint (Telegram-Bot ist
  derzeit Long-Polling), at-rest-Encryption der Audit-Datei.

### Art. 32 (1) (b) – Vertraulichkeit, Integrität, Verfügbarkeit

- **Rollenbasierter Zugriff** (`bot/auth.py`):
  - `operator` – darf Befehle vorschlagen, ausführen, Code generieren,
    SSH-Firewall steuern, Snapshots verwalten, Rollback fahren.
  - `approver` – darf vorgeschlagene Befehle bestätigen (`/ja`).
  - `viewer` – darf Status und Snapshots einsehen, im Chat lesen.
  - Inheritance: operator ⊃ approver ⊃ viewer.
- Jeder Endpunkt im Bot prüft die Rolle explizit; ein nicht autorisierter
  Zugriff wird abgelehnt **und** als `result: denied` im Audit protokolliert.
- Verfügbarkeit: Bot läuft als `systemd`-Service (`clownfisch`); Boot-Notify-
  Service informiert beim Neustart.

### Art. 32 (1) (c) – Wiederherstellbarkeit

`bot/snapshot.py` erstellt automatisch Snapshots vor potenziell zerstörerischen
Operationen (`/code`, ZIP-Upload, schreibende `/shell`-Befehle). `/rollback`
stellt einen Snapshot wieder her – ebenfalls per Operator-Rolle abgesichert.

### Art. 32 (1) (d) – Verfahren zur Überprüfung

Tests unter `tests/`:

- `test_auth.py` – Rollenmodell + Backwards-Compat
- `test_audit_log.py` – Schreibverhalten, Pruning, Datenminimierung
- `test_audit_query.py` – Filterlogik, Format
- `test_llm_router.py` – Routing-Verhalten, Audit-Hooks

`tests/_smoke.py`, `tests/_smoke_router.py`, `tests/_smoke_query.py` sind
standalone-Skripte für Einsatz ohne pytest.

---

## Was Clownfischserver **nicht** automatisch erledigt

Diese Punkte verbleiben beim Betreiber:

- **Auftragsverarbeitungs-Vertrag** mit OpenRouter (falls Fallback aktiviert).
  OpenRouter-Server stehen außerhalb der EU – aktiviere den Fallback nicht
  für Daten mit Personenbezug.
- **Verzeichnis von Verarbeitungstätigkeiten** (Art. 30 DSGVO).
- **Datenschutz-Folgenabschätzung** bei großvolumiger Personendaten­verarbeitung
  durch das gehostete LLM.
- **Backup-Strategie** für die Audit-Datei (in v0.6.0 geplant).
- **Schulung der Operatoren** im Umgang mit dem `/shell`-Approval-Flow.

---

## Kurz: Welche `.env`-Variablen sind DSGVO-relevant?

| Variable | Effekt |
|---|---|
| `CLOWNFISCH_OPERATORS` / `_APPROVERS` / `_VIEWERS` | Rollenzuweisung, Art. 32 (1) (b) |
| `AUDIT_LOG_PATH` | Pfad zur Audit-Datei (sollte auf verschlüsseltem Volume liegen) |
| `AUDIT_RETENTION_DAYS` | Speicherbegrenzung, Art. 5 (1) (e) |
| `AUDIT_MAX_DETAIL_LEN` | Datenminimierung, Art. 5 (1) (c) |
| `LLM_PRIMARY_PROVIDER=ollama` | On-prem-LLM, keine Cloud-Übertragung |
| `LLM_FALLBACK_PROVIDER=none` | Cloud-Fallback explizit deaktivieren |
| `OPENROUTER_API_KEY` | nur setzen wenn AV-Vertrag mit OpenRouter besteht |

---

**Stand:** Juni 2026 · v0.5.0 · Mehlzoerwer-Claude
