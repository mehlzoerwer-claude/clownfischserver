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

# Erstelle Log-File wenn nicht existiert
touch "$LOG_FILE" 2>/dev/null || true

# Lade myfritz-Adresse aus .env (Zeilenumbrüche entfernen)
MYFRITZ_DOMAIN=$(grep "^CLOWNFISCHSERVER_HOME_IP_DOMAIN=" "$ENV_FILE" | cut -d= -f2 | tr -d '\r\n')

if [[ -z "$MYFRITZ_DOMAIN" ]]; then
    log "Clownfischserver HomeIP: Deaktiviert (keine myfritz-Adresse)"
    exit 0
fi

# Versuche IP aufzulösen (mit Fallback)
if command -v dig &>/dev/null; then
    NEW_IP=$(dig +short "$MYFRITZ_DOMAIN" A 2>/dev/null | tail -1 | grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b')
elif command -v nslookup &>/dev/null; then
    NEW_IP=$(nslookup "$MYFRITZ_DOMAIN" 2>/dev/null | grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' | tail -1)
elif command -v getent &>/dev/null; then
    NEW_IP=$(getent hosts "$MYFRITZ_DOMAIN" 2>/dev/null | awk '{print $1}')
else
    log_error "Kein DNS-Tool verfügbar (dig/nslookup/getent)"
    exit 1
fi

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

# Entferne alte Regel falls vorhanden (mit y bestätigen für Cron)
if [[ -n "$OLD_IP" ]]; then
    # Prüfe ob Regel existiert
    if ufw status numbered | grep -qE "22.*ALLOW.*FROM\s+$OLD_IP"; then
        # Löschen mit 'y' autom. bestätigen
        echo "y" | ufw delete allow from "$OLD_IP" to any port 22 >> "$LOG_FILE" 2>&1
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
