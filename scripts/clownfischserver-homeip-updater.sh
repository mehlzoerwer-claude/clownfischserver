#!/bin/bash
# =============================================================================
# 🐠 CLOWNFISCHSERVER – HomeIP Auto-Update
# Purpose: Auto-update firewall rule for dynamic home IP (myfritz.net)
# Runs: Every 5 minutes (via cron)
# Author: Mehlzoerwer-Claude
# License: GPL-3.0
# =============================================================================

set -e

# --- Configuration ---
INSTALL_DIR="/opt/clownfischserver"
ENV_FILE="$INSTALL_DIR/config/.env"
STATE_FILE="/var/lib/clownfischserver-homeip-state"
LOG_FILE="/var/log/clownfischserver-homeip-updater.log"
SSH_PORT=22

# --- Helpers ---
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# --- Load .env ---
load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log "ERROR: .env not found at $ENV_FILE"
        exit 1
    fi
    # Load and trim CRLF/LF
    MYFRITZ_DOMAIN=$(grep "^CLOWNFISCHSERVER_HOME_IP_DOMAIN=" "$ENV_FILE" | cut -d= -f2 | tr -d '\r\n')
    if [ -z "$MYFRITZ_DOMAIN" ]; then
        log "ERROR: CLOWNFISCHSERVER_HOME_IP_DOMAIN not set in .env"
        exit 1
    fi
}

# --- Detect Firewall ---
detect_firewall() {
    if systemctl is-active --quiet ufw; then
        echo "ufw"
    elif systemctl is-active --quiet firewalld; then
        echo "firewalld"
    elif command -v iptables &>/dev/null; then
        echo "iptables"
    else
        log "ERROR: No firewall detected (ufw/firewalld/iptables)"
        exit 1
    fi
}

# --- Resolve DNS with fallbacks ---
resolve_ip() {
    local domain="$1"

    # Try dig first
    if command -v dig &>/dev/null; then
        IP=$(dig +short "$domain" A | grep -oE '^[0-9.]+$' | head -1)
        [ -n "$IP" ] && echo "$IP" && return 0
    fi

    # Try nslookup
    if command -v nslookup &>/dev/null; then
        IP=$(nslookup "$domain" 2>/dev/null | grep "Address:" | tail -1 | awk '{print $2}' | grep -oE '^[0-9.]+$')
        [ -n "$IP" ] && echo "$IP" && return 0
    fi

    # Try getent
    if command -v getent &>/dev/null; then
        IP=$(getent hosts "$domain" | awk '{print $1}' | grep -oE '^[0-9.]+$' | head -1)
        [ -n "$IP" ] && echo "$IP" && return 0
    fi

    log "ERROR: Could not resolve $domain"
    return 1
}

# --- Load previous state ---
load_state() {
    if [ -f "$STATE_FILE" ]; then
        PREVIOUS_IP=$(cat "$STATE_FILE" | grep "^IP=" | cut -d= -f2)
        echo "$PREVIOUS_IP"
    else
        echo ""
    fi
}

# --- Save state ---
save_state() {
    local ip="$1"
    echo "IP=$ip" > "$STATE_FILE"
    chmod 600 "$STATE_FILE"
}

# --- UFW Functions ---
ufw_add_rule() {
    local ip="$1"
    ufw allow from "$ip" to any port "$SSH_PORT" comment "clownfisch-homeip" >/dev/null 2>&1
    log "UFW: Added rule for $ip:$SSH_PORT"
}

ufw_remove_rule() {
    local ip="$1"
    echo "y" | ufw delete allow from "$ip" to any port "$SSH_PORT" >/dev/null 2>&1
    log "UFW: Deleted rule for $ip"
}

# --- Firewalld Functions ---
firewalld_add_rule() {
    local ip="$1"
    firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='$ip' port protocol='tcp' port='$SSH_PORT' accept" >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    log "firewalld: Added rule for $ip:$SSH_PORT"
}

firewalld_remove_rule() {
    local ip="$1"
    firewall-cmd --permanent --remove-rich-rule="rule family='ipv4' source address='$ip' port protocol='tcp' port='$SSH_PORT' accept" >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    log "firewalld: Deleted rule for $ip"
}

# --- iptables Functions ---
iptables_add_rule() {
    local ip="$1"
    iptables -I INPUT -s "$ip" -p tcp --dport "$SSH_PORT" -j ACCEPT
    log "iptables: Added rule for $ip:$SSH_PORT"
}

iptables_remove_rule() {
    local ip="$1"
    iptables -D INPUT -s "$ip" -p tcp --dport "$SSH_PORT" -j ACCEPT 2>/dev/null || true
    log "iptables: Deleted rule for $ip"
}

# --- Main ---
main() {
    log "=== HomeIP Auto-Update started ==="

    load_env
    FIREWALL=$(detect_firewall)
    NEW_IP=$(resolve_ip "$MYFRITZ_DOMAIN") || exit 1
    PREVIOUS_IP=$(load_state)

    if [ "$NEW_IP" = "$PREVIOUS_IP" ]; then
        log "No change: $NEW_IP (same as previous)"
        exit 0
    fi

    log "IP change detected: $PREVIOUS_IP → $NEW_IP (firewall: $FIREWALL)"

    # Remove old rule
    if [ -n "$PREVIOUS_IP" ]; then
        case "$FIREWALL" in
            ufw) ufw_remove_rule "$PREVIOUS_IP" ;;
            firewalld) firewalld_remove_rule "$PREVIOUS_IP" ;;
            iptables) iptables_remove_rule "$PREVIOUS_IP" ;;
        esac
    fi

    # Add new rule
    case "$FIREWALL" in
        ufw) ufw_add_rule "$NEW_IP" ;;
        firewalld) firewalld_add_rule "$NEW_IP" ;;
        iptables) iptables_add_rule "$NEW_IP" ;;
    esac

    # Save state
    save_state "$NEW_IP"

    log "=== HomeIP Auto-Update completed successfully ==="
}

main "$@"
