# 🐠 Clownfischserver

> *Wie der Clownfisch in seiner Anemone lebt – geschützt, autonom, und beißt überraschend hart.*

Ein selbst-hostbarer, KI-gestützter Server-Manager der ausschließlich über Telegram kommuniziert. Kein Dashboard, kein Web-UI, keine Cloud. Nur du und dein Server – über eine Chat-Nachricht.

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Linux](https://img.shields.io/badge/Platform-Linux-red.svg)
![Version](https://img.shields.io/badge/Version-0.4.11-green.svg)
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
- 📸 **Automatische Snapshots** vor destruktiven Aktionen (tar.gz mit Keep/Unkeep)
- 🔐 **Port-Knocking SSH** als sicherer Backup-Zugang (knockd)
- 🔔 **Benachrichtigungen** – SSH-Zugang, Server-Boot, Knock-Versuche via Telegram
- 📦 **Self-Update via Telegram** – ZIP an den Bot schicken, fertig
- 👤 **Eigener User** mit passwordless sudo für alle Operationen
- 🌍 **Mehrsprachig** – antwortet in der Sprache in der du schreibst
- 🐧 **Multi-Distro** – Debian, Ubuntu, Fedora, Arch (Installer)
- 🔒 **DSGVO by design** – alles lokal, keine Cloud, keine externen APIs

---

## Schnellstart

```bash
# Frisches Ubuntu/Debian – als root:
wget https://github.com/mehlzoerwer-claude/clownfischserver/releases/latest/download/clownfischserver.zip
unzip clownfischserver.zip && cd clownfischserver
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

### Fertig (v0.1 – v0.4.11)

- [x] Basis-Installer mit geführtem Setup (8 Schritte)
- [x] Telegram Bot mit Auth Guard (Single-User)
- [x] Dual-Model KI: Coder (qwen2.5-coder) + Chat (gemma3)
- [x] `/shell` + `/ja` – Befehlsgenerierung mit Bestätigung
- [x] `/code` – Aider Code-Agent für autonome Script-Erstellung
- [x] `/run` – Direkte Shell ohne KI
- [x] `/status` – Systemübersicht
- [x] `/ssh open/close` – ufw-basierter SSH-Zugang
- [x] Freitext-Chat mit History (letzte 10 Exchanges)
- [x] Snapshot-System (tar.gz, keep/unkeep, auto-cleanup max 20)
- [x] `/snapshot`, `/snapshots`, `/rollback`
- [x] Port-Knocking SSH (knockd) mit Telegram-Notify
- [x] Boot-Notification nach Server-Neustart
- [x] Self-Update via Telegram ZIP
- [x] Update-Modus im Installer
- [x] Multi-Distro Installer (apt/dnf/pacman)
- [x] Ollama Warmup im Hintergrund (Bot sofort bereit)
- [x] Safe Telegram Output (Markdown-Fallback bei Parse-Fehlern)
- [x] Lange Antworten werden in Teile gesplittet (kein Abschneiden)

### v0.5.0 – Geplant

- [ ] Snapshot-Scheduling (`/snapshot schedule daily 03:00`)
- [ ] Snapshot-Export als ZIP via Telegram (`/snapshot export <n>`)
- [ ] `/logs` – Systemlogs direkt im Bot
- [ ] `/docker` – Docker Container Management
- [ ] SSH Key via Telegram hinterlegen
- [ ] Message Queue (parallele Anfragen)
- [ ] Web-Hook statt Polling
- [ ] Automatische Backups zu S3/Backblaze/NAS

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

### v0.8.0 – Cloud-API Integration (optional)

- [ ] Optionale Anbindung externer KI-APIs (OpenRouter, Anthropic, OpenAI)
- [ ] `OLLAMA_MODEL_CLOUD` in `.env` – Opt-in, kein Zwang
- [ ] Fallback-Kette: Cloud → Lokal (wenn Cloud nicht erreichbar)
- [ ] Admin entscheidet welche Anfragen lokal vs. Cloud beantwortet werden
- [ ] **Local-first bleibt Prinzip** – Cloud ist Werkzeug, nicht Abhängigkeit

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

Clownfischserver ist und bleibt local-first. Aber wir sind keine Puristen: wenn ein Admin einen OpenRouter- oder Claude-API-Key hat und ihn für komplexe Aufgaben nutzen will, soll er das können. Die Entscheidung liegt beim Admin, nicht beim Tool.

Was wir **nicht** tun:
- Cloud als Voraussetzung
- Daten automatisch an externe APIs senden
- Features hinter Cloud-APIs verstecken

Was wir **ermöglichen** (ab v0.8.0):
- Optionaler API-Key in `.env`
- Admin wählt welche Aufgaben Cloud nutzen dürfen
- Wenn Cloud ausfällt, funktioniert alles weiterhin lokal

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
