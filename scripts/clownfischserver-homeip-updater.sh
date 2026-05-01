#!/bin/bash
# =============================================================================
# 🐠 Clownfischserver HomeIP Updater
# Version: v0.5.0
# Purpose: Automatisch die Home-IP aktualisieren (alle 5 Min via Cron)
# Author:  Mehlzoerwer-Claude
# License: GPL-3.0
# =============================================================================

# Konfiguration
INSTALL_DIR="/opt/clownfischserver"
ENV_FILE="$INSTALL_DIR/config/.env"
STATE_FILE="/var/lib/clownfischserver-homeip-state"
LOG_FILE="/var/log/clownfischserver-homeip.log"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >> "$LOG_FILE"
}

# Prüfe ob .env existiert
if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env nicht gefunden: $ENV_FILE"
    exit 1
fi

# Lade myfritz-Adresse aus .env
MYFRITZ_DOMAIN=$(grep "^CLOWNFISCHSERVER_HOME_IP_DOMAIN=" "$ENV_FILE" | cut -d= -f2)

if [[ -z "$MYFRITZ_DOMAIN" ]]; then
    log "Clownfischserver HomeIP: Deaktiviert (keine myfritz-Adresse)"
    exit 0
fi

# Versuche IP aufzulösen
NEW_IP=$(dig +short "$MYFRITZ_DOMAIN" A 2>/dev/null | tail -1 | grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b')

if [[ -z "$NEW_IP" ]]; then
    log_error "DNS-Auflösung fehlgeschlagen: $MYFRITZ_DOMAIN"
    exit 1
fi

# Lese alte IP aus State-File
OLD_IP=""
if [[ -f "$STATE_FILE" ]]; then
    OLD_IP=$(cat "$STATE_FILE")
fi

log "Domain: $MYFRITZ_DOMAIN | Neue IP: $NEW_IP | Alte IP: ${OLD_IP:-keine}"

# Wenn IP sich nicht geändert hat → nichts tun
if [[ "$NEW_IP" == "$OLD_IP" ]] && [[ -n "$OLD_IP" ]]; then
    log "IP unverändert – keine Aktion nötig"
    exit 0
fi

# IP hat sich geändert oder ist neue Installation
log "IP-Änderung erkannt! Updating ufw rules..."

# Entferne alte Regel falls vorhanden
if [[ -n "$OLD_IP" ]]; then
    if ufw status | grep -q "22/tcp.*ALLOW.*$OLD_IP"; then
        ufw delete allow from "$OLD_IP" to any port 22 >> "$LOG_FILE" 2>&1
        log "Alte Regel entfernt: allow from $OLD_IP to port 22"
    fi
fi

# Füge neue Regel hinzu
if ufw allow from "$NEW_IP" to any port 22 comment "clownfischserver-homeip-$MYFRITZ_DOMAIN" >> "$LOG_FILE" 2>&1; then
    log "Neue Regel hinzugefügt: allow from $NEW_IP to port 22"
else
    log_error "ufw Regel konnte nicht hinzugefügt werden"
    exit 1
fi

# Speichere neue IP
echo "$NEW_IP" > "$STATE_FILE"
chmod 644 "$STATE_FILE"

log "✓ HomeIP Update erfolgreich: $MYFRITZ_DOMAIN → $NEW_IP"
exit 0
