# Contributing to Clownfischserver 🐠

Danke dass du mitmachen willst! Hier sind die Regeln:

## Grundprinzipien

- **Open Source bleibt Open Source** – GPL-3.0, keine Ausnahmen
- **Lokal first** – keine Cloud-Dependencies, keine externen APIs
- **Einfach bleiben** – ein Nutzer, ein Bot, ein Server
- **Sicherheit** – Safety-Check vor jeder Aktion

## Pull Requests

1. Fork das Repo
2. Branch erstellen: `git checkout -b feature/dein-feature`
3. Änderungen committen
4. PR öffnen mit Beschreibung was und warum

## Code Style

- Python: PEP8, async/await
- Bash: shellcheck-kompatibel
- Kommentare auf Deutsch oder Englisch
- Header in jeder Datei (siehe bestehende Dateien)

## Code-Hygiene (wichtig!)

- **Kein toter Code** – keine Funktionen/Module die definiert aber nie aufgerufen werden
- **Keine versteckten Cloud-Calls** – jeder externe Request muss klar ersichtlich und opt-in sein
- **Niemals `verify=False`** bei HTTPS-Requests
- **Keine User-Eingaben an Dritte** ohne explizites Opt-in (DSGVO by design)
- **Klare Conditions** – verschachtelte Ternaries (`A if B else C` innerhalb von `and`-Ketten) vermeiden
- Selbst-Review vor jedem Release: macht jede Zeile noch das was sie soll?

## Issues

- Bug? → Issue mit Log-Output
- Feature-Idee? → Issue mit Use-Case Beschreibung
- Frage? → Issue oder Discussions

## Was wir suchen

- Distro-Support (getestete Fedora/Arch Fixes)
- Neue Bot-Commands
- Bessere Safety-Prompts
- Dokumentation
- Tests

## Was wir NICHT wollen

- Cloud-Dependencies
- Closed-Source Komponenten
- Komplexität die Einsteiger abschreckt
