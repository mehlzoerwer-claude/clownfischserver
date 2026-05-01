# 🐠 Clownfischserver HomeIP Auto-Update

Automatische SSH-Freigabe für deine Home-IP – ohne Port-Knocking.

## Wie es funktioniert

1. **Installation:** `install.sh` fragt nach deiner myfritz-Adresse
2. **Cron-Job:** Läuft alle 5 Minuten (root crontab)
3. **DNS-Auflösung:** Löst `vorname.myfritz.net` auf
4. **UFW-Update:** Aktualisiert die Firewall-Regel wenn IP sich ändert

## Setup während Installation

```bash
[4/8] SSH + Firewall

? myfritz Home-IP permanent erlauben? [j/n]
→ j

? Deine myfritz Adresse:
  Format: vorname.myfritz.net
→ mehlzoerwer.myfritz.net
```

Das Script wird dann automatisch:
- In `/opt/clownfischserver/scripts/` installiert
- Executable gemacht
- In `root`-Crontab als 5-Minuten-Job eingetragen

## Manuelle Verwaltung

### Script manuell ausführen
```bash
sudo /opt/clownfischserver/scripts/clownfischserver-homeip-updater.sh
```

### Cron-Job prüfen
```bash
sudo crontab -l | grep clownfischserver-homeip
```

### Logs anschauen
```bash
tail -f /var/log/clownfischserver-homeip.log
```

### Manuell aktivieren/deaktivieren

**Aktivieren** (wenn nicht aktiviert während Installation):
```bash
# myfritz-Adresse in .env eintragen
sudo nano /opt/clownfischserver/config/.env
# CLOWNFISCHSERVER_HOME_IP_DOMAIN=vorname.myfritz.net

# Cron-Job hinzufügen
(sudo crontab -l 2>/dev/null; echo "*/5 * * * * /opt/clownfischserver/scripts/clownfischserver-homeip-updater.sh >> /var/log/clownfischserver-homeip.log 2>&1") | sudo crontab -
```

**Deaktivieren:**
```bash
# Aus .env entfernen
sudo nano /opt/clownfischserver/config/.env
# CLOWNFISCHSERVER_HOME_IP_DOMAIN= (leer lassen)

# Cron-Job entfernen
sudo crontab -l 2>/dev/null | grep -v clownfischserver-homeip | sudo crontab -

# UFW-Regeln cleanup (optional)
sudo ufw status | grep "clownfischserver-homeip"
sudo ufw delete allow from [IP] to any port 22
```

## Was die myfritz-Adresse ist

**myfritz** ist ein DynDNS-Service der AVM (Fritz.Box Hersteller):
- `https://myfritz.net/`
- Deine Home-IP bekommst darin immer einen stabilen Hostnamen
- Auch wenn deine DSL-IP sich ändert, bleibt `vorname.myfritz.net` gleich
- ✅ Das Script prüft alle 5 Min und aktualisiert die UFW-Regel automatisch

## Sicherheit

- **UFW-Kommentar:** `clownfischserver-homeip-vorname.myfritz.net`
  - Zeigt in `ufw status` an woher die Regel kommt
  
- **Logging:**
  - `/var/log/clownfischserver-homeip.log` – vollständiger Audit-Trail
  - Timestamp + alte IP + neue IP + Aktion

- **State-File:**
  - `/var/lib/clownfischserver-homeip-state` – speichert die letzte bekannte IP
  - Verhindert unnötige UFW-Updates bei gleicher IP

## Troubleshooting

### Cron-Job läuft nicht
```bash
# Status prüfen
sudo crontab -l | grep clownfischserver-homeip

# Logs prüfen
sudo tail -20 /var/log/clownfischserver-homeip.log

# Manuell testen
sudo /opt/clownfischserver/scripts/clownfischserver-homeip-updater.sh
```

### DNS-Auflösung schlägt fehl
```bash
# myfritz-Adresse testen
dig vorname.myfritz.net

# Oder mit nslookup
nslookup vorname.myfritz.net

# In .env prüfen
grep CLOWNFISCHSERVER_HOME_IP /opt/clownfischserver/config/.env
```

### UFW-Regel wird nicht hinzugefügt
```bash
# UFW Status prüfen
sudo ufw status

# Manuelle Regel hinzufügen (Debugging)
sudo ufw allow from 1.2.3.4 to any port 22 comment "clownfischserver-homeip-test"

# Logs prüfen
sudo journalctl -u ufw -n 20
```

---

**Script-Info:** Clownfischserver v0.5.0+ | GPL-3.0
