# 🐠 Clownfischserver – Projekt-Kontext

> Diese Datei ist der zentrale Wissensspeicher für das Clownfischserver-Projekt.
> Lade sie in jede KI/Chat-Session um sofort produktiv zu sein.
> Letzte Aktualisierung: v0.4.13 (18.04.2026)

---

## Was ist der Clownfischserver?

Ein Open-Source, Telegram-gesteuerter Linux-Server-Manager. Der Admin schreibt dem Bot über Telegram – der Bot versteht, generiert Befehle, erstellt Scripts, verwaltet den Server. Komplett lokal mit Ollama, optional Cloud-Fallback über OpenRouter.

**Repo:** https://github.com/mehlzoerwer-claude/clownfischserver
**Lizenz:** GPL-3.0
**Entwickler:** Mehlzoerwer-Claude (Thorsten Matthes)
**KI-Assistent:** Claude (Anthropic) – Pair-Programming Partner

---

## Architektur

```
                         ┌─────────────────────┐
                         │     Telegram Bot     │
                         │      (bot.py)        │
                         └──────┬──────┬────────┘
                                │      │
              ┌─────────────────┤      ├─────────────────┐
              ▼                 ▼      ▼                 ▼
     ┌────────────────┐ ┌────────────┐ ┌──────────────────┐
     │  ollama_client  │ │  shell.py  │ │  aider_wrapper   │
     │   (Dual-Model)  │ │ (run_shell)│ │  (Code-Agent)    │
     └───────┬────┬────┘ └────────────┘ └──────────────────┘
             │    │
    ┌────────┘    └────────┐
    ▼                      ▼
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│ Chat-Model│      │ Coder-Model  │      │  OpenRouter   │
│ (gemma3)  │      │(qwen2.5-coder)│      │  (Fallback)  │
└──────────┘      └──────────────┘      └──────────────┘
```

**Prinzip:** Freitext = Chat. `/shell` = KI generiert Befehl → Admin bestätigt mit `/ja`. `/code` = Aider erstellt Dateien. `/run` = direkte Shell.

---

## Dateistruktur (19 Dateien, ~3250 Zeilen)

```
clownfischserver/
├── bot/
│   ├── bot.py              # Hauptbot: alle Commands, Auth, Self-Update, Update-Dialog
│   ├── ollama_client.py    # Dual-Model, OpenRouter Fallback, NUM_CTX, Shell-Prompt
│   ├── openrouter_client.py # OpenRouter Free Models Client (openrouter/free)
│   ├── shell.py            # run_shell (shlex.quote), execute_command
│   ├── aider_wrapper.py    # Aider mit --edit-format diff, 600s Timeout
│   ├── snapshot.py         # tar.gz Snapshots, Workspace, Paketliste, sudo rsync
│   ├── boot_notify.py      # Telegram-Nachricht 120s nach Boot
│   ├── knock_notify.py     # Port-Knocking SSH-Benachrichtigungen
│   └── requirements.txt    # python-telegram-bot, requests, python-dotenv
├── config/
│   ├── .env.example        # Vorlage mit allen Variablen
│   └── knockd.conf         # Port-Knocking Sequenz (7000→8000→9000)
├── systemd/
│   ├── clownfisch.service      # Bot-Service (User=clownfish, wird gepatcht)
│   └── clownfisch-boot.service # Boot-Notification (oneshot, 120s delay)
├── install.sh              # 8-Schritt Installer mit Modell/CTX-Auswahl
├── README.md               # Vollständige Dokumentation
├── LICENSE                 # GPL-3.0
├── .gitignore
├── CONTRIBUTING.md
└── GITHUB_PROFILE.md
```

---

## Wichtige Konventionen

### Naming
- **Service:** `clownfisch.service` (Deutsch, mit "ch")
- **Linux-User:** Beliebig (z.B. `clownfisch`, `clownfish`, `admin`) – wird aus `MGMT_USER` in `.env` gelesen
- **Branding:** Immer "Clownfisch" (Deutsch)
- **ZIP-Benennung:** `v0.4.13-clownfischserver-opus.zip`

### Code-Stil
- Python 3, keine Type Hints in Funktionssignaturen (außer Optional)
- Logging über `logging` Modul
- Async für alle Telegram-Handler
- `safe_reply()` für alle Telegram-Nachrichten (Markdown-Fallback)
- Fehler werden dem User angezeigt, nie verschluckt

### Sicherheits-Regeln
- Configs (`sshd_config`, `knockd.conf`) NIE überschreiben – nur gezielte Zeilen ändern
- `.env` Permissions: 0600
- SSH Host-Keys, `/etc/shadow` NIE in Snapshots
- `.env` seit v0.4.12 aus Snapshots excludiert
- Self-Update: systemd-Services werden mit `MGMT_USER` aus `.env` gepatcht (Regex: `User=\S+`)

---

## .env Variablen

```
TELEGRAM_BOT_TOKEN=...         # Bot-Token von @BotFather
TELEGRAM_CHAT_ID=...           # Autorisierte Chat-ID (Single-User)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b  # Coder-Modell für /shell und /code
OLLAMA_MODEL_FAST=gemma3:4b    # Chat-Modell für Freitext
OLLAMA_NUM_CTX=16384           # Context-Window (4096-32768)
OPENROUTER_API_KEY=sk-or-v1-...  # Optional: kostenloser Cloud-Fallback
SNAPSHOT_DIR=/opt/clownfisch-snapshots
SNAPSHOT_METHOD=tar
INSTALL_DIR=/opt/clownfischserver
MGMT_USER=clownfisch           # Linux-User (beliebig wählbar)
AIDER_WORKDIR=/opt/clownfisch-workspace
```

---

## Bot-Befehle

| Befehl | Funktion |
|--------|----------|
| Freitext | Chat mit KI (gemma3 lokal, OpenRouter Fallback) |
| `/shell <beschreibung>` | KI generiert Shell-Befehl, non-interaktiv |
| `/ja` | Letzten `/shell` Befehl ausführen (mit Snapshot davor) |
| `/code <aufgabe>` | Aider erstellt Dateien (Smart Prompt: Dateiname wird ergänzt) |
| `/run <befehl>` | Direkte Shell, kein KI, kein Bestätigen |
| `/status` | CPU, RAM, Disk, Top-Prozesse |
| `/ssh open [ip]` | SSH via ufw öffnen |
| `/ssh close [ip]` | SSH via ufw schließen |
| `/snapshot [label]` | Manuell Snapshot erstellen |
| `/snapshot keep/delete <n>` | Snapshot markieren/löschen |
| `/snapshots` | Alle Snapshots anzeigen |
| `/rollback <name>` | Zu Snapshot zurückkehren (sudo rsync --delete) |
| `/start` / `/help` | Bot-Info und Befehlsübersicht |
| ZIP senden | Self-Update mit optionalem OpenRouter-Setup-Dialog |

---

## Dual-Model Strategie

| Rolle | Modell | RAM | Aufgabe |
|-------|--------|-----|---------|
| Coder | qwen2.5-coder:7b | ~4.7GB | `/shell`, `/code`, Befehlsgenerierung |
| Chat | gemma3:4b | ~3.3GB | Freitext, Erklärungen, Übersetzungen |
| Fallback | openrouter/free | 0 (Cloud) | Wenn Ollama nicht verfügbar |

**Shell-Prompt:** Few-Shot mit non-interaktiven Regeln (kein nano/vim/crontab -e, sudo wenn nötig).
**Chat-Prompt:** Deutsch als Standard, antwortet in Sprache des Nutzers.
**Explain-Prompt:** Erklärt Befehlsergebnisse auf Deutsch.

---

## Snapshot-System

**Gesichert:** `/etc`, `/opt/clownfischserver`, `/home`, `/opt/clownfisch-workspace`
**Excludiert:** SSH Host-Keys, shadow, `.env`, `__pycache__`, `node_modules`
**Paketliste:** `dpkg --get-selections` pro Snapshot als `.packages.txt`
**Rollback:** `sudo rsync -av --delete` pro Verzeichnis
**Auto-Cleanup:** Max 20 Snapshots, `keep`-markierte bleiben immer

---

## OpenRouter Integration

- **Client:** `openrouter_client.py` mit `openrouter/free` Auto-Router
- **Fallback-Trigger:** Ollama Timeout ODER "nicht erreichbar"
- **Betrifft:** Chat + `/shell` (nicht `/code` – Aider braucht Ollama direkt)
- **Setup:** Beim Self-Update fragt Bot "OpenRouter aktivieren?" → Key eingeben → `.env`
- **Kosten:** Free Tier: 50 Requests/Tag, 20/Minute, keine Kreditkarte

---

## Bekannte Bugs / Einschränkungen

- `/code` hat keinen OpenRouter-Fallback (Aider spricht nur Ollama)
- Kleine Modelle (< 8B) halluzinieren bei Erklärungen
- Aider `diff`-Format überfordert kleine Modelle manchmal → Datei wird nicht erstellt
- Shell-Prompt vergisst manchmal `sudo` bei Root-Operationen

---

## Server-Umgebung

- **Hoster:** netcup VPS
- **OS:** Ubuntu 24.04 LTS
- **RAM:** 16GB
- **Disk:** 300GB
- **IP:** 92.60.38.175
- **Ollama:** qwen2.5-coder:7b + gemma3:4b (oder gemma4:e2b)
- **Docker:** installiert
- **SSH:** Port-Knocking via knockd (7000→8000→9000)

---

## Roadmap

### v0.5.0 – Sicherheit + Features
**Security (DSGVO-Pflicht):**
- Sensitive Dateien über Telegram blockieren (`.env`, shadow, Keys)
- Output-Sanitizer: API Keys/Tokens in JEDER Bot-Antwort maskieren
- Log-Sanitizer: Keine Secrets im Audit-Log
- Audit-Log: Jeder Befehl mit Timestamp (DSGVO Art. 5/32)
- SHA256-Hash bei Self-Update + Admin-Bestätigung
- `.env` Permissions-Check beim Bot-Start
- `bot.log`, `.aider.chat.history.md`, `bash_history` aus Snapshots excluden
- Rate-Limiting: Max 30 Befehle/Minute
- Session-Timeout: Nach 30 Min Inaktivität → 2FA erneut
- 2FA bei kritischen Aktionen (TOTP/Mail/zweiter Bot)
- Persönlicher Code-Offset (SECURITY_OFFSET in .env)

**Features:**
- Snapshot-Scheduling + Export via Telegram
- Verschlüsselte Snapshots (SNAPSHOT_PASSWORD)
- `/logs`, `/docker`
- Port-Knocking Sequenz wählbar
- Open Interpreter als Aider-Alternative evaluieren

**Quick-Win Security:**
- Panik-Wort: Admin-definiertes Wort → Bot löscht .env, sperrt alles
- Honeypot-Befehle: Fake-Commands die Eindringlinge verraten
- Selbstzerstörende Nachrichten: Bot löscht eigene Outputs nach X Minuten
- Rollback-Bombe: 3x falscher 2FA → auto-Rollback + SSH sperren + Alert
- Dead Man's Switch: Kein Lebenszeichen in 24h → Bot sperrt sich selbst

### v0.6.0 – Multi-Server + Gedächtnis
- Ein Bot steuert mehrere Server
- Audit-Log / Server-Gedächtnis (server_log.txt)
- Chat kann vergangene Aktionen abfragen

### v0.7.0 – DSGVO-bewusster Backup-Manager
- Verschlüsselte Snapshots (SNAPSHOT_PASSWORD in .env)

### v0.8.0 – Erweiterte Cloud-API
- Premium-Modelle auf OpenRouter
- Anthropic/OpenAI direkt
- Kosten-Tracking

### v0.9.0 – Multi-Interface + Advanced Security
**Alternative Interfaces (E2E-verschlüsselt):**
- Matrix/Element Connector (matrix-nio, self-hosted, E2E)
- Signal Connector (signal-cli, E2E)
- Web-UI (HTTPS, self-hosted, Let's Encrypt)
- SSH-CLI (interaktive Shell-Session, kein Messenger nötig)
- E-Mail mit GPG-Verschlüsselung

**Advanced Security Features (evaluieren bei v0.8.x Abschluss):**
- Fake-Modus: Falscher 2FA-Code → Bot tut so als ob, führt nichts aus, stiller Alarm
- Distress-Code: Umgekehrter Offset = "Ich werde gezwungen" → Fake-Modus
- Geo-Fencing: Bot antwortet nur aus erlaubten Ländern/IP-Bereichen
- Buddy-System: Kritische Befehle brauchen Bestätigung von zweitem Admin
- Canary Token: Unsichtbare Marker-Dateien, Alert bei Zugriff
- Verschlüsselter Rückkanal: Bot-Antworten verschlüsselt über Telegram
- Hardware-Token: USB-Stick als physischer Schlüssel

**Architektur-Ziel:**
```
[Telegram] ─┐
[Matrix]   ─┤
[Web-UI]   ─┼─→ [bot_core.py] → [Ollama/OpenRouter]
[SSH-CLI]  ─┤
[E-Mail]   ─┘
```
Ein Bot, viele Eingänge. Admin wählt was er will.

### v1.0.0 – Disaster Recovery
### v2.0.0 – Cross-Distribution Server Migration

---

## Getestete Modelle

| Modell | Größe | Rolle | Ergebnis |
|--------|-------|-------|----------|
| qwen2.5-coder:7b | 4.7GB | Coder | ✅ Beste Wahl für Code |
| qwen2.5-coder:3b | 1.9GB | Coder | ✅ Funktioniert, schwächer |
| gemma3:4b | 3.3GB | Chat | ✅ Gutes Deutsch, schnell |
| gemma4:e2b | 7.2GB | Beide | ⚠️ Zu groß für Dual-Setup |
| rnj-1:8b | 5.1GB | Coder | ❓ Test ausstehend |
| qwen3.5:4b | – | Coder | ❌ Thinking, zu langsam auf CPU |
| openrouter/free | Cloud | Fallback | ✅ Nemotron-H, stark |

---

## Wichtige Design-Entscheidungen

1. **Local-first:** Cloud ist Opt-in Werkzeug, nicht Abhängigkeit
2. **Kein Classifier:** Freitext = Chat. Befehle explizit per `/shell`, `/run`, `/code`
3. **Bestätigungs-Flow:** `/shell` generiert → Admin prüft → `/ja` führt aus
4. **Beliebiger Username:** MGMT_USER wird überall per Regex eingesetzt
5. **Smart `/code` Prompt:** Bot ergänzt Dateiname wenn User keinen nennt
6. **Snapshot vor destruktiven Aktionen:** Automatisch bei apt install, rm, chmod etc.
7. **DSGVO by design:** Lokal, keine Daten an Cloud, Snapshots ohne Secrets

---

## Security-Analyse (v0.4.13)

### Was wir haben ✅
- Chat-ID Auth (Single-User)
- `.env` mit 0600 Permissions
- SSH Host-Keys + shadow excluded aus Snapshots
- `.env` excluded aus Snapshots (seit v0.4.12)
- Port-Knocking statt offenes SSH
- Lokal-first, Cloud opt-in
- Safe-Reply Markdown-Fallback (kein Crash bei Sonderzeichen)

### Bekannte Schwachstellen ❌

**Telegram als Angriffsfläche:**
- Bot-Token im Klartext in `.env` – wer den Server hackt hat den Bot
- Telegram Chat-History enthält alle Befehle + Outputs – nicht löschbar vom Bot
- Telegram API ist NICHT E2E-verschlüsselt – Telegram Inc. kann mitlesen
- Jemand der das Handy entsperrt hat vollen Zugriff
- `.env` Inhalte können per `/run cat .env` über Telegram geleakt werden

**Bot-Sicherheit:**
- Kein Rate-Limiting – Brute-Force auf Befehle möglich
- Kein Session-Timeout – Bot antwortet 24/7 ohne erneute Auth
- `bot.log` enthält möglicherweise sensible Daten (unverschlüsselt)
- `.aider.chat.history.md` loggt alle Code-Prompts im Klartext
- Ollama API auf localhost:11434 hat keine Auth – jeder lokale Prozess kann anfragen

**Snapshots:**
- Snapshots enthalten `/home` – SSH Keys, bash_history, private Dateien
- Snapshot-Verzeichnis nicht verschlüsselt
- Kein Integrity-Check ob Snapshots manipuliert wurden

**Netzwerk:**
- knockd Sequenz steht im Klartext in `knockd.conf`
- ufw Regeln können über `/run` beliebig geändert werden

**Server:**
- NOPASSWD sudo – kompromittierter Bot = Root
- `install.sh` lädt Pakete aus dem Internet ohne Signatur-Check
- Docker Socket zugänglich → Container-Escape möglich

### Security-Maßnahmen geplant

**v0.5.0 (realistisch umsetzbar):**
1. `.env`/Secrets über Telegram blockieren (Blacklist für sensitive Pfade)
2. Output-Sanitizer: API Keys/Tokens in JEDER Bot-Antwort maskieren
3. Log-Sanitizer: Keine Secrets im Audit-Log
4. `bot.log` + `.aider.chat.history.md` + `bash_history` aus Snapshots excluden
5. Rate-Limiting: Max 30 Befehle/Minute
6. Session-Timeout: Nach 30 Min Inaktivität → 2FA erneut nötig
7. 2FA bei kritischen Aktionen (TOTP/Mail/zweiter Bot)
8. Persönlicher Code-Offset (SECURITY_OFFSET in .env)
9. SHA256-Hash bei Self-Update → Admin bestätigt
10. `.env` Permissions-Check beim Bot-Start (warnen wenn nicht 0600)
11. Audit-Log mit Timestamp für jeden Befehl (DSGVO Art. 5/32)

**v0.6.0+ (langfristig):**
12. Bot-Token Rotation
13. Verschlüsselte Snapshots (SNAPSHOT_PASSWORD)
14. Integrity-Hashes für Snapshots (Manipulation erkennen)
15. Ollama API Auth
16. Audit-Log mit Tamper-Protection (Signierung)

### DSGVO-Regel für Telegram
`.env` wird NUR angelegt/geändert über SSH. Niemals über Telegram lesbar.
Der Bot BLOCKIERT Befehle die sensitive Dateien über Telegram ausgeben würden.

---

## ZIP bauen – exakte Vorgehensweise

### Voraussetzungen
- Alle 20 Dateien müssen im Ordner `clownfischserver/` liegen
- Python-Dateien müssen syntax-geprüft sein
- install.sh muss bash-syntax-geprüft sein

### Schritt 1: Syntax-Check (IMMER vor dem ZIP)
```bash
cd clownfischserver
python3 -m py_compile bot/bot.py
python3 -m py_compile bot/ollama_client.py
python3 -m py_compile bot/openrouter_client.py
python3 -m py_compile bot/shell.py
python3 -m py_compile bot/snapshot.py
python3 -m py_compile bot/aider_wrapper.py
python3 -m py_compile bot/boot_notify.py
python3 -m py_compile bot/knock_notify.py
bash -n install.sh
```

### Schritt 2: ZIP erstellen
```bash
cd ..  # Eine Ebene über clownfischserver/
zip -r v0.4.13-clownfischserver-opus.zip clownfischserver/ -x "*__pycache__*" "*.pyc"
```

**WICHTIG:**
- ZIP-Name: `v<version>-clownfischserver-opus.zip`
- Root-Ordner im ZIP muss `clownfischserver/` heißen (nicht `build/` oder anderer Name)
- Keine `__pycache__` oder `.pyc` Dateien
- Keine `.git/` Ordner
- Keine `.env` mit echten Credentials

### Schritt 3: Verifizieren
```bash
unzip -l v0.4.13-clownfischserver-opus.zip | head -30
# Muss zeigen: clownfischserver/bot/bot.py etc. (20 Dateien)
```

### Schritt 4: Einspielen
**Per Telegram:** ZIP an den ClownfischServer Bot senden → Self-Update Dialog
**Per Server:** `bash install.sh` im entpackten Ordner

### Schritt 5: GitHub Push
```bash
cd clownfischserver
rm -rf .git
git init
git remote add origin https://github.com/mehlzoerwer-claude/clownfischserver.git
git add -A
git commit -m "v0.4.13 – Beschreibung der Änderungen"
git branch -M main
git push -u origin main --force
```

### Dateiliste (20 Dateien, vollständig)
```
clownfischserver/
├── .gitignore
├── CLOWNFISCHSERVER.md          ← diese Datei
├── CONTRIBUTING.md
├── GITHUB_PROFILE.md
├── LICENSE
├── README.md
├── install.sh
├── bot/
│   ├── aider_wrapper.py
│   ├── boot_notify.py
│   ├── bot.py
│   ├── knock_notify.py
│   ├── ollama_client.py
│   ├── openrouter_client.py
│   ├── requirements.txt
│   ├── shell.py
│   └── snapshot.py
├── config/
│   ├── .env.example
│   └── knockd.conf
└── systemd/
    ├── clownfisch-boot.service
    └── clownfisch.service
```

### Versions-Bump Checkliste
Bei neuer Version diese Stellen aktualisieren:
1. `install.sh` – Banner + Log-Meldung (3x `v0.4.13`)
2. `bot/bot.py` – `cmd_start` Begrüßung + `main()` Log-Meldung
3. `README.md` – Badge `Version-0.4.13` + Roadmap "Fertig (v0.1 – v0.4.13)"
4. `CLOWNFISCHSERVER.md` – Header + Dateiliste
5. ZIP-Dateiname

---

> *"Angefangen als einfacher Telegram-Bot – gewachsen zu einer Vision."* 🐠
