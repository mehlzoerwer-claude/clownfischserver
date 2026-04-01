# 🐠 Clownfischserver

> *Wie der Clownfisch in seiner Anemone lebt – geschützt, autonom, und beißt überraschend hart.*

Ein selbst-hostbarer, KI-gestützter Server-Manager der ausschließlich über Telegram kommuniziert. Kein Dashboard, kein Web-UI, keine Cloud. Nur du und dein Server – über eine Chat-Nachricht.

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Debian](https://img.shields.io/badge/Platform-Debian%2FUbuntu-red.svg)
![Version](https://img.shields.io/badge/Version-0.3.8-green.svg)
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

Clownfischserver verwandelt einen frischen Debian/Ubuntu VPS in einen vollautonomen, Telegram-gesteuerten Server. Du schreibst ihm – er denkt nach (via Ollama + lokaler KI) und handelt.

**Kein SCP. Kein Dashboard. Kein Cloud-Zwang. Nur Telegram.**

---

## Features

- 🤖 **Telegram Bot** als primäres Interface – von überall, auch vom Handy
- 🧠 **Lokale KI** (Ollama + qwen) für Safety-Checks und natürliche Sprache
- 🛠️ **Aider** für autonome Code-Generierung und -Bearbeitung
- 📸 **Automatische Snapshots** vor jeder Aktion (btrfs oder tar.gz)
- 🔐 **Port-Knocking SSH** als sicherer Backup-Zugang (knockd)
- 🔔 **Knock-Knock Notify** – Telegram-Benachrichtigung bei SSH-Zugang
- 📦 **Self-Update via Telegram** – ZIP an den Bot schicken, fertig
- 👤 **Eigener User** mit passwordless sudo für alle Operationen
- 🌍 **Mehrsprachig** – antwortet in der Sprache in der du schreibst
- 🐧 **Multi-Distro** – Debian, Ubuntu, Fedora, Arch

---

## Schnellstart

```bash
# Frisches Debian/Ubuntu – als root:
wget https://github.com/mehlzoerwer/clownfischserver/releases/latest/download/clownfischserver.zip
unzip clownfischserver.zip && cd clownfischserver
bash install.sh
```

Der Installer führt dich durch alles – Schritt für Schritt, mit Erklärungen.

---

## Installation

### Was du brauchst

- Frischer Debian 12/13 oder Ubuntu 22/24 VPS (min. 4GB RAM, 20GB Disk)
- Root SSH-Zugang für die Installation
- Ein Telegram-Account (5 Minuten für Bot-Setup)

### Der Installer

```
[1/8] Systemcheck          → RAM, Disk, Distro-Erkennung
[2/8] Pakete               → alles Nötige mit Spinner
[3/8] User einrichten      → eigener User oder vorhandenen nutzen
[4/8] SSH + Firewall       → Port-Knocking, ufw, SSH bleibt offen
[5/8] Ollama               → KI-Engine, Modell-Auswahl
[6/8] Python + Aider       → Bot-Umgebung
[7/8] Telegram             → geführtes Bot-Setup mit BotFather
[8/8] Service starten      → systemd, läuft beim Boot
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
| `/start` | Bot-Status prüfen |
| `/status` | CPU, RAM, Disk |
| `/snapshots` | Alle Snapshots anzeigen |
| `/rollback <n>` | Zu Snapshot zurück |
| `/run <befehl>` | Direkte Shell – kein Ollama nötig |
| `/ssh open` | SSH für alle öffnen |
| `/ssh open 1.2.3.4` | SSH nur für deine IP |
| `/ssh close` | SSH wieder sperren |
| `/help` | Diese Hilfe |

### Natürliche Sprache

```
"Wie viel RAM ist noch frei?"
"Installiere nginx"
"Zeig mir alle laufenden Docker Container"
"Erstelle eine einfache Node.js API"
"Was frisst gerade die CPU?"
```

### Self-Update

ZIP-Datei direkt an den Bot schicken, Bot erstellt Snapshot, installiert Update, startet neu.

---

## Sicherheit

### Port-Knocking

SSH ist standardmäßig durch iptables blockiert. Zugang via Klopf-Sequenz:

```bash
# Oeffnen:    7000 -> 8000 -> 9000
knock SERVER_IP 7000 8000 9000

# Schliessen: 9000 -> 8000 -> 7000
knock SERVER_IP 9000 8000 7000
```

Bei jedem Knock kommt eine Telegram-Benachrichtigung mit IP und Zeitstempel.

### KI Safety-Check

Vor jeder Aktion bewertet die lokale KI die Anfrage:

```
Nutzer schreibt  ->  KI prueft:
  "Chat/Frage?"      -> direkte Antwort
  "Shell-Befehl?"    -> Snapshot -> ausfuehren -> Ergebnis
  "Code-Aufgabe?"    -> Aider -> ausfuehren -> Ergebnis
  "Gefaehrlich?"     -> verweigern + Erklaerung
```

Gefaehrliche Befehle (rm -rf /, Disk wipen, Fork Bombs) werden immer verweigert.

### Snapshot-System

Vor jeder Aktion automatischer Snapshot (btrfs nativ oder tar.gz Fallback).

---

## Architektur

```
[Telegram] <-> [bot.py] <-> [ollama_client.py]  <- Safety + Chat
                  |
            [shell.py]  [aider_wrapper.py]       <- Ausfuehrung
                  |
            [snapshot.py]                        <- Sicherung
                  |
            [knock_notify.py]                    <- SSH Alerts
```

---

## Roadmap

### Fertig (v0.1 - v0.3.8)

- [x] Basis-Installer mit gefuehrtem Setup
- [x] Telegram Bot mit Auth Guard
- [x] Ollama Integration (Safety-Check + Chat)
- [x] Shell-Executor mit Output-Rueckgabe
- [x] Snapshot-System (btrfs + tar.gz)
- [x] Port-Knocking SSH (knockd)
- [x] Knock-Knock Telegram Notify mit Timestamp
- [x] /run Direkt-Shell ohne Ollama
- [x] /ssh open/close Notfall-Zugang
- [x] Self-Update via Telegram ZIP
- [x] Update-Modus im Installer
- [x] Multi-Distro Support (apt/dnf/pacman)
- [x] Spinner + Ladebalken im Installer
- [x] Ollama Retry-Loop beim Start
- [x] Mehrsprachig (DE/EN/FR/ES/IT/PT)

### Geplant (v0.4+)

- [ ] SSH Key via Telegram hinterlegen
- [ ] Datei-Upload via Telegram (Scripte direkt ausfuehren)
- [ ] Message Queue (parallele Anfragen ohne Timeout)
- [ ] Aider vollstaendig integriert und getestet
- [ ] /logs - Systemlogs direkt im Bot
- [ ] /docker - Docker Container Management
- [ ] Mehrere Nutzer mit unterschiedlichen Rechten
- [ ] Web-Hook statt Polling

### Ideen (v0.5+)

- [ ] Automatische Backups zu S3/Backblaze
- [ ] Cron-Jobs via Telegram verwalten
- [ ] VPN-Setup Assistent
- [ ] Weltklasse OS Layer Integration

---

## Entwicklung

**Entwickler:** [Mehlzoerwer](https://github.com/mehlzoerwer)

**KI-Assistent:** Dieses Projekt wurde mit [Claude](https://claude.ai) (Anthropic) als Pair-Programming Partner entwickelt. Claude ist der einzige nicht-Open-Source Teil dieser Zusammenarbeit. 😄

**Philosophie:** Open Source ohne Wenn und Aber. Wer's nutzt, muss es offen lassen (GPL-3.0).

---

## Lizenz

GPL-3.0 - Keep it open. Always.

Copyright (C) 2026 Mehlzoerwer

---

*Danke an alle die Port-Knocking, knockd, Ollama, Aider und python-telegram-bot gebaut haben.*
*Und an den echten Clownfisch – fuer die Inspiration.* 🐠
