# 🐠 Clownfischserver

> *Wie der Clownfisch in seiner Anemone lebt – geschützt, autonom, und beißt überraschend hart.*

Ein selbst-hostbarer, KI-gestützter Server-Manager der ausschließlich über Telegram kommuniziert. Kein Dashboard, kein Web-UI, keine Cloud. Nur du und dein Server – über eine Chat-Nachricht.

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Linux](https://img.shields.io/badge/Platform-Linux-red.svg)
![Version](https://img.shields.io/badge/Version-0.4.13-green.svg)
![Status](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)

---

## 🐟 Warum "Clownfisch"?

Der Clownfisch lebt in seiner Anemone – einem der wenigen Orte im Ozean die für andere Fische tödlich sind. Er verlässt sie kaum, schützt sie aktiv, und fühlt sich darin vollkommen sicher.

Genauso lebt der Clownfischserver **in seinem Server** (seiner Anemone):
- Er schirmt alles ab was nicht sein muss
- SSH bleibt standardmäßig zu – nur wer das richtige Klopfmuster kennt kommt rein
- Die KI entscheidet was sicher ist und was nicht
- Und wie der echte Clownfisch: **beißt er überraschend hart wenn nötig** 🐠

---

## Was ist das?

Clownfischserver verwandelt einen Linux-Server in einen vollautonomen, Telegram-gesteuerten Assistenten. Du schreibst ihm in natürlicher Sprache – er versteht, generiert Befehle, erstellt Scripts, und verwaltet deinen Server.

Das Ziel: **Server-Administration so einfach wie eine Chat-Nachricht.** Heute ein Server, morgen eine ganze Farm.

**Kein SCP. Kein Dashboard. Kein Cloud-Zwang. Nur Telegram.**

---

## Features

- 🤖 **Telegram Bot** als primäres Interface – von überall, auch vom Handy
- 🧠 **Dual-Model KI** – Code-Modell (qwen2.5-coder) für Befehle + Chat-Modell (gemma3) für Konversation
- 🔧 **`/shell` + `/ja`** – KI generiert Shell-Befehle, du bestätigst vor der Ausführung
- 🛠️ **`/code` + Aider** – autonome Code- und Script-Generierung direkt auf dem Server
- 💬 **Natürlicher Chat** – Fragen stellen, Erklärungen bekommen, übersetzen lassen
- 📸 **Automatische Snapshots** vor destruktiven Aktionen (tar.gz mit Keep/Unkeep + Paketliste)
- 🔐 **Port-Knocking SSH** als sicherer Backup-Zugang (knockd) mit Telegram-Benachrichtigung
- 🔔 **Benachrichtigungen** – SSH-Zugang, Server-Boot, Knock-Versuche via Telegram
- 📦 **Self-Update via Telegram** – ZIP an den Bot schicken, fertig (inkl. systemd-Services)
- ☁️ **OpenRouter Fallback** – kostenlose Cloud-Modelle als Backup wenn Ollama nicht verfügbar
- 👤 **Eigener User** – beliebiger Name, passwordless sudo, wird überall korrekt eingesetzt
- 🌍 **Mehrsprachig** – antwortet in der Sprache in der du schreibst
- 🐧 **Multi-Distro** – Debian, Ubuntu, Fedora, Arch (Installer)
- 🔒 **DSGVO by design** – lokal ist Standard, Cloud ist Opt-in

---

## Schnellstart

```bash
# Frisches Ubuntu/Debian – als root:
wget https://github.com/mehlzoerwer-claude/clownfischserver/archive/refs/heads/main.zip
unzip main.zip && cd clownfischserver-main
bash install.sh
```

Der Installer führt dich durch alles – Schritt für Schritt, mit Erklärungen.

---

## Installation

### Was du brauchst

- Frischer Ubuntu 22/24 oder Debian 12/13 VPS (min. 8GB RAM empfohlen, 20GB Disk)
- Root SSH-Zugang für die Installation
- Ein Telegram-Account (5 Minuten für Bot-Setup)

### RAM-Empfehlung

| RAM | Coder-Modell | Chat-Modell | Gesamt ca. |
|-----|-------------|-------------|------------|
| 8-12 GB | qwen2.5-coder:3b | gemma3:1b | ~3 GB |
| 16+ GB | qwen2.5-coder:7b | gemma3:4b | ~8 GB |

### Der Installer

```
[1/8] Systemcheck          → RAM, Disk, Distro-Erkennung
[2/8] Pakete               → alles Nötige mit Spinner
[3/8] User einrichten      → eigener User oder vorhandenen nutzen
[4/8] SSH + Firewall       → Port-Knocking, ufw, SSH bleibt offen
[5/8] Ollama               → Dual-Model KI-Setup (Coder + Chat)
[6/8] Python + Aider       → Bot-Umgebung + Code-Agent
[7/8] Telegram             → geführtes Bot-Setup mit BotFather
[8/8] Service starten      → systemd + Boot-Notification
```

### Update (wenn bereits installiert)

```bash
bash install.sh
# → erkennt laufenden Service
# → [1] Update  [2] Neuinstallation  [3] Abbrechen
```

Oder noch einfacher: **ZIP direkt an den Bot schicken** – Self-Update!

---

## Nutzung

### Bot-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/shell <beschreibung>` | KI generiert Shell-Befehl aus natürlicher Sprache |
| `/ja` | Letzten vorgeschlagenen Befehl ausführen |
| `/code <aufgabe>` | Aider erstellt/bearbeitet Code und Scripts |
| `/run <befehl>` | Direkte Shell – kein Ollama, kein Bestätigen |
| `/status` | CPU, RAM, Disk, Top-Prozesse |
| `/snapshots` | Alle Snapshots anzeigen |
| `/snapshot [label]` | Manuell Snapshot erstellen |
| `/snapshot keep <n>` | Snapshot als wichtig markieren |
| `/snapshot delete <n>` | Snapshot löschen |
| `/rollback <n>` | Zu einem Snapshot zurückkehren |
| `/ssh open [ip]` | SSH via ufw öffnen (für alle oder eine IP) |
| `/ssh close [ip]` | SSH wieder sperren |
| `/start` / `/help` | Bot-Info und Befehlsübersicht |

### Freitext-Chat

Einfach schreiben – ohne Befehl. Der Bot antwortet als Chat-Partner:

```
"Was ist ein Reverse Proxy?"
"Übersetze das ins Englische: ..."
"Erkläre mir den Unterschied zwischen apt und snap"
"Welche Services laufen gerade auf meinem Server?"
```

### Workflow: `/shell` + `/ja`

```
Du:   /shell zeig mir die größten Dateien auf dem Server
Bot:  🔧 Vorgeschlagener Befehl:
      du -ah / | sort -rh | head -20
      → Mit /ja ausführen oder einfach ignorieren.
Du:   /ja
Bot:  ✅ Ergebnis: ...
```

### Workflow: `/code`

```
Du:   /code erstelle ein bash script das alte Logs älter als 30 Tage löscht
Bot:  🛠️ Aider Ergebnis:
      ✅ Aider Task abgeschlossen
      Applied edit to cleanup-logs.sh
```

### Self-Update

ZIP-Datei direkt an den Bot schicken → Bot erstellt Snapshot → installiert Update → startet neu.

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
┌──────────┐      ┌──────────────┐
│ Chat-Model│      │ Coder-Model  │
│ (gemma3)  │      │(qwen2.5-coder)│
└──────────┘      └──────────────┘

Weitere Module:
  snapshot.py       – Backup-System (tar.gz, keep/unkeep, auto-cleanup)
  knock_notify.py   – SSH Port-Knocking Alerts
  boot_notify.py    – Server-Neustart Benachrichtigung
```

---

## Sicherheit

### Port-Knocking

SSH ist standardmäßig durch ufw blockiert. Zugang via Klopf-Sequenz:

```bash
# Oeffnen:    7000 -> 8000 -> 9000
knock SERVER_IP 7000 8000 9000

# Schliessen: 9000 -> 8000 -> 7000
knock SERVER_IP 9000 8000 7000
```

Bei jedem Knock kommt eine Telegram-Benachrichtigung mit IP und Zeitstempel.

### KI-gestützte Befehlsgenerierung

```
/shell installiere nginx
  → KI generiert: apt install -y nginx
  → Gefährlich? Nein → Vorschlag anzeigen
  → /ja zum Ausführen, oder ignorieren

/shell lösche alles in /etc
  → KI generiert: rm -rf /etc/*
  → Gefährlich? JA → Verweigert mit Erklärung
```

Kein Befehl wird ohne Bestätigung ausgeführt. Gefährliche Befehle werden immer verweigert.

### Snapshot-System

Vor destruktiven Aktionen automatischer Snapshot (tar.gz). Wichtige Snapshots können mit `/snapshot keep` markiert werden und werden nie automatisch gelöscht.

### Boot-Notification

Nach jedem Server-Neustart bekommst du eine Telegram-Nachricht mit Status aller Dienste (Clownfisch, Ollama, ufw, SSH, Cron) – nach 2 Minuten, wenn alles hochgefahren ist.

---

## Roadmap

### Fertig (v0.1 – v0.4.13)

- [x] Basis-Installer mit geführtem Setup (8 Schritte)
- [x] Telegram Bot mit Auth Guard (Single-User)
- [x] Dual-Model KI: Coder (qwen2.5-coder) + Chat (gemma3/gemma4)
- [x] `/shell` + `/ja` – Befehlsgenerierung mit Bestätigung (non-interaktive Befehle)
- [x] `/code` – Aider Code-Agent für autonome Script-Erstellung (Smart Prompt)
- [x] `/run` – Direkte Shell ohne KI
- [x] `/status` – Systemübersicht (CPU, RAM, Disk, Prozesse)
- [x] `/ssh open/close` – ufw-basierter SSH-Zugang
- [x] Freitext-Chat mit History (letzte 10 Exchanges)
- [x] Snapshot-System (tar.gz, keep/unkeep, auto-cleanup max 20, Paketliste)
- [x] `/snapshot`, `/snapshots`, `/rollback` (inkl. Workspace)
- [x] Port-Knocking SSH (knockd) mit Telegram-Benachrichtigung
- [x] Boot-Notification nach Server-Neustart (Dienste-Status)
- [x] Self-Update via Telegram ZIP (inkl. systemd-Services + User-Patch)
- [x] Update-Modus im Installer (mit MGMT_USER aus .env)
- [x] Multi-Distro Installer (apt/dnf/pacman)
- [x] Ollama Warmup im Hintergrund (Bot sofort bereit)
- [x] **OpenRouter Free Fallback** – kostenlose Cloud-Modelle wenn Ollama nicht verfügbar
- [x] Interaktiver Update-Dialog (OpenRouter Key Eingabe via Telegram)
- [x] `OLLAMA_NUM_CTX` konfigurierbar (4K–32K, RAM-basierte Empfehlung im Installer)
- [x] Safe Telegram Output (Markdown-Fallback bei Parse-Fehlern)
- [x] Lange Antworten werden in Teile gesplittet (kein Abschneiden)
- [x] Mehrsprachig (antwortet in der Sprache des Nutzers)
- [x] MGMT_USER Regex-Patch (beliebiger Username funktioniert überall)
- [x] Security-Analyse dokumentiert (Schwachstellen + Maßnahmen in CLOWNFISCHSERVER.md)
- [x] DSGVO-Regel: `.env` nur per SSH, nie über Telegram lesbar
- [x] Projekt-Kontext-Datei (CLOWNFISCHSERVER.md) für KI-gestütztes Pair-Programming

### v0.5.0 – Geplant

**Sicherheit & DSGVO:**
- [ ] Sensitive Dateien über Telegram blockieren (`.env`, `shadow`, Keys)
- [ ] Output-Sanitizer: API Keys/Tokens in jeder Bot-Antwort maskieren
- [ ] Log-Sanitizer: Keine Secrets im Audit-Log
- [ ] Audit-Log: Jeder Befehl mit Timestamp (DSGVO Art. 5/32)
- [ ] Self-Update Hardening: SHA256-Hash anzeigen, Admin bestätigt
- [ ] `.env` Permissions-Check beim Bot-Start
- [ ] `bot.log`, `.aider.chat.history.md`, `bash_history` aus Snapshots excluden
- [ ] Rate-Limiting: Max 30 Befehle/Minute
- [ ] Session-Timeout: Nach 30 Min Inaktivität → 2FA erneut nötig
- [ ] 2FA bei kritischen Aktionen (TOTP/Mail/zweiter Bot)
- [ ] Persönlicher Code-Offset (SECURITY_OFFSET in `.env`)

**Features:**
- [ ] Snapshot-Scheduling (`/snapshot schedule daily 03:00`)
- [ ] Snapshot-Export als ZIP via Telegram (`/snapshot export <n>`)
- [ ] `/logs` – Systemlogs direkt im Bot
- [ ] `/docker` – Docker Container Management
- [ ] Port-Knocking Sequenz im Installer wählbar
- [ ] Verschlüsselte Snapshots (SNAPSHOT_PASSWORD)
- [ ] Open Interpreter als Aider-Alternative evaluieren

**Quick-Win Security:**
- [ ] Panik-Wort: Admin-definiertes Wort → Bot löscht .env, sperrt alles
- [ ] Honeypot-Befehle: Fake-Commands die Eindringlinge verraten
- [ ] Selbstzerstörende Nachrichten: Bot löscht eigene Outputs nach X Minuten
- [ ] Rollback-Bombe: 3x falscher 2FA → auto-Rollback + SSH sperren
- [ ] Dead Man's Switch: Kein Lebenszeichen in 24h → Bot sperrt sich

### v0.6.0 – Multi-Server

- [ ] Ein Bot steuert mehrere Server
- [ ] Zentrale Snapshot-Verwaltung
- [ ] Serverpark-Übersicht und -Steuerung
- [ ] Mehrere Nutzer mit unterschiedlichen Rechten

### v0.7.0 – DSGVO-bewusster Backup-Manager

- [ ] `/backup configs` → immer erlaubt
- [ ] `/backup app` → eigene Anwendungsdaten
- [ ] `/backup db` → Warnung + Bestätigung bei personenbezogenen Daten
- [ ] Lokale KI bewertet ob Daten DSGVO-relevant sein könnten

### v0.8.0 – Erweiterte Cloud-API Integration

- [ ] Wahl zwischen Free- und Premium-Modellen auf OpenRouter
- [ ] Direkte Anthropic/OpenAI API-Anbindung (neben OpenRouter)
- [ ] Admin steuert pro Befehlstyp: lokal oder Cloud
- [ ] Kosten-Tracking für Cloud-API-Nutzung

### v0.9.0 – Multi-Interface + Advanced Security

- [ ] Matrix/Element Connector (E2E-verschlüsselt, self-hosted)
- [ ] Web-UI mit HTTPS (self-hosted, Let's Encrypt)
- [ ] SSH-CLI als direktes Interface
- [ ] Fake-Modus + Distress-Code (falscher 2FA → stiller Alarm)
- [ ] Geo-Fencing (nur erlaubte Länder/IP-Bereiche)
- [ ] Buddy-System (zwei Admins für kritische Befehle)
- [ ] Verschlüsselter Rückkanal über Telegram

---

## Langzeit-Vision 🚀

### v1.0.0 – Intelligent Disaster Recovery

Server komplett aus Snapshot wiederherstellen – auch auf anderer Hardware oder in einer anderen Umgebung. Die KI analysiert den Snapshot und rekonstruiert die Umgebung.

*"Stelle Server 3 auf Stand von gestern 02:00 Uhr wieder her."*

Ziel: Open Source Alternative zu teuren Enterprise DR-Lösungen.

### v2.0.0 – Cross-Distribution Server Migration

Die eigentliche Revolution: **Ein Snapshot, jedes Zielsystem.**

Der Clownfischserver versteht nicht nur Dateien, sondern die *Logik* eines Servers:
- Welche Pakete sind installiert und wofür?
- Welche Services laufen und wie sind sie konfiguriert?
- Welche Abhängigkeiten bestehen zwischen Komponenten?

Diese Logik ist distro-unabhängig. Ein Debian-Server mit nginx + PostgreSQL + Docker hat die gleiche *Absicht* wie ein Arch-Server mit denselben Diensten – nur andere Paketnamen, Pfade und Init-Systeme.

**Ziel-Plattformen:**
- Debian / Ubuntu (heute)
- Arch Linux
- Red Hat / Fedora / CentOS
- openSUSE
- FreeBSD
- Weitere UNIX-Systeme

**Wie es funktioniert:**
1. KI analysiert Snapshot und erstellt ein distro-neutrales "Server-Profil"
2. Profil beschreibt: Dienste, Konfigurationen, Daten, Netzwerk, Nutzer
3. Auf dem Zielsystem: KI übersetzt das Profil in native Befehle
4. `apt install nginx` → `pacman -S nginx` → `pkg install nginx`
5. Konfigurationen werden angepasst (Pfade, Syntax, Permissions)

*"Migriere meinen Debian-Webserver auf Arch Linux."*

### Weltklasse Integration 🌍

Clownfischserver als Infrastruktur-Layer für die Weltklasse App – natürliche Sprachsteuerung des gesamten Server-Ökosystems. GDPR-konform, vollständig lokal, kein Cloud-Zwang.

---

> *"Angefangen als einfacher Telegram-Bot – gewachsen zu einer Vision."* 🐠

---

## Prinzipien 🛡️

```
1. Local AI first      – Lokal ist Standard. Cloud ist Opt-in.
2. Open Source always   – GPL-3.0, keine Ausnahmen
3. DSGVO by design     – Datenschutz ist kein Feature, es ist Pflicht
4. Security first      – SSH zu, KI prüft, Snapshots sichern
5. Einfachheit         – ein Mensch, ein Bot, ein Server
6. Distro-agnostisch   – Linux ist Linux. Die KI kennt den Unterschied.
```

### Zur Cloud-Frage

Clownfischserver ist und bleibt local-first. Aber wir sind keine Puristen: wenn ein Admin einen OpenRouter-API-Key hat und ihn für komplexe Aufgaben nutzen will, soll er das können. Die Entscheidung liegt beim Admin, nicht beim Tool.

Was wir **nicht** tun:
- Cloud als Voraussetzung
- Daten automatisch an externe APIs senden
- Features hinter Cloud-APIs verstecken

Was wir **ermöglichen** (seit v0.4.12/v0.4.13):
- Optionaler OpenRouter API-Key in `.env` (kostenlos, keine Kreditkarte)
- Automatischer Fallback: Ollama Timeout → OpenRouter übernimmt
- Wenn Cloud ausfällt, funktioniert alles weiterhin lokal
- Setup direkt im Bot: ZIP schicken → Bot fragt nach Key → fertig

> *Als Admin entscheidest du – nicht das Tool.*

---

## Entwicklung

**Entwickler:** [Mehlzoerwer-Claude](https://github.com/mehlzoerwer-claude)

**KI-Assistent:** Dieses Projekt wurde mit [Claude](https://claude.ai) (Anthropic) als Pair-Programming Partner entwickelt. Claude ist der einzige nicht-Open-Source Teil dieser Zusammenarbeit. 😄

**Philosophie:** Open Source ohne Wenn und Aber. Wer's nutzt, muss es offen lassen (GPL-3.0).

---

## Lizenz

GPL-3.0 - Keep it open. Always.

Copyright (C) 2025-2026 Mehlzoerwer-Claude

---

*Danke an alle die Ollama, Aider, python-telegram-bot, knockd und ufw gebaut haben.*
*Und an den echten Clownfisch – für die Inspiration.* 🐠
