#!/bin/bash
# =============================================================================
# 🐠 Clownfischserver HomeIP Updater
# Version: v0.5.0
# Purpose: Automatisch die Home-IP aktualisieren (alle 5 Min via Cron)
# Multi-Distro: ufw (Ubuntu/Debian), firewalld (Fedora/openSUSE), iptables (Arch)
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

# Erkenne welche Firewall aktiv ist
detect_firewall() {
    if systemctl is-active --quiet ufw 2>/dev/null; then
        echo "ufw"
    elif systemctl is-active --quiet firewalld 2>/dev/null; then
        echo "firewalld"
    elif command -v iptables &>/dev/null; then
        echo "iptables"
    else
        echo "unknown"
    fi
}

FIREWALL=$(detect_firewall)
log "Firewall erkannt: $FIREWALL"

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
log "IP-Änderung erkannt! Aktualisiere Firewall-Regeln..."

# Firewall-spezifische Funktionen
remove_ufw_rule() {
    if ufw status numbered | grep -qE "22.*ALLOW.*FROM\s+$1"; then
        echo "y" | ufw delete allow from "$1" to any port 22 >> "$LOG_FILE" 2>&1
        log "UFW: Alte Regel entfernt: allow from $1 to port 22"
    fi
}

add_ufw_rule() {
    ufw allow from "$1" to any port 22 comment "clownfischserver-homeip-$MYFRITZ_DOMAIN" >> "$LOG_FILE" 2>&1
    log "UFW: Neue Regel hinzugefügt: allow from $1 to port 22"
}

remove_firewalld_rule() {
    firewall-cmd --permanent --remove-rich-rule="rule family='ipv4' source address='$1' port protocol='tcp' port='22' accept" >> "$LOG_FILE" 2>&1
    log "firewalld: Alte Regel entfernt: source address $1 port 22"
}

add_firewalld_rule() {
    firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='$1' port protocol='tcp' port='22' accept" >> "$LOG_FILE" 2>&1
    firewall-cmd --reload >> "$LOG_FILE" 2>&1
    log "firewalld: Neue Regel hinzugefügt: source address $1 port 22"
}

remove_iptables_rule() {
    iptables -D INPUT -s "$1" -p tcp --dport 22 -j ACCEPT 2>> "$LOG_FILE" || true
    log "iptables: Alte Regel entfernt: source $1 port 22"
}

add_iptables_rule() {
    iptables -I INPUT -s "$1" -p tcp --dport 22 -j ACCEPT >> "$LOG_FILE" 2>&1
    log "iptables: Neue Regel hinzugefügt: source $1 port 22"
}

# Entferne alte Regel falls vorhanden
if [[ -n "$OLD_IP" ]]; then
    case "$FIREWALL" in
        ufw)      remove_ufw_rule "$OLD_IP" ;;
        firewalld) remove_firewalld_rule "$OLD_IP" ;;
        iptables) remove_iptables_rule "$OLD_IP" ;;
        *)        log_error "Unbekannte Firewall: $FIREWALL" && exit 1 ;;
    esac
fi

# Füge neue Regel hinzu
case "$FIREWALL" in
    ufw)
        if ! add_ufw_rule "$NEW_IP"; then
            log_error "UFW: Regel konnte nicht hinzugefügt werden"
            exit 1
        fi
        ;;
    firewalld)
        if ! add_firewalld_rule "$NEW_IP"; then
            log_error "firewalld: Regel konnte nicht hinzugefügt werden"
            exit 1
        fi
        ;;
    iptables)
        if ! add_iptables_rule "$NEW_IP"; then
            log_error "iptables: Regel konnte nicht hinzugefügt werden"
            exit 1
        fi
        ;;
    *)
        log_error "Unbekannte Firewall: $FIREWALL"
        exit 1
        ;;
esac

# Speichere neue IP
echo "$NEW_IP" > "$STATE_FILE"
chmod 644 "$STATE_FILE"

log "✓ HomeIP Update erfolgreich: $MYFRITZ_DOMAIN → $NEW_IP ($FIREWALL)"
exit 0
