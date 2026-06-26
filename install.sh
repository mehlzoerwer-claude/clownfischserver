#!/bin/bash
# =============================================================================
# 🐠 CLOWNFISCHSERVER
# Version: see banner
# Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
# License: GPL-3.0 – Keep it open. Always.
# Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
# =============================================================================

# GPL-3.0 License - Keep it open. Always.
# https://github.com/mehlzoerwer-claude/clownfischserver

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Defaults ---
INSTALL_DIR="/opt/clownfischserver"
SNAPSHOT_DIR="/opt/clownfisch-snapshots"
WORKSPACE_DIR="/opt/clownfisch-workspace"
LOG_FILE="/var/log/clownfischserver-install.log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MGMT_USER=""
PKG_MANAGER=""
DISTRO=""
OLLAMA_MODEL=""
OLLAMA_MODEL_FAST=""
SNAPSHOT_METHOD="tar"
OLLAMA_NUM_CTX=4096
MYFRITZ_DOMAIN=""
BOT_TOKEN=""
CHAT_ID=""
OPENROUTER_API_KEY=""

# HELPERS

log()  { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; log "OK: $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; log "INFO: $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; log "WARN: $1"; }
fail() {
    echo -e "\n  ${RED}${BOLD}✗ FEHLER: $1${NC}"
    echo -e "  ${YELLOW}Mehr Details: tail -50 $LOG_FILE${NC}\n"
    log "ERROR: $1"
    exit 1
}

step() {
    echo -e "\n${BOLD}${BLUE}[$1/$TOTAL_STEPS] $2${NC}"
    log "=== STEP $1: $2 ==="
}

ask() {
    echo -e "\n  ${YELLOW}?${NC} ${BOLD}$1${NC}"
    if [[ -n "$2" ]]; then
        echo -e "  ${CYAN}  $2${NC}"
    fi
    read -r -p "    → " REPLY
    echo "$REPLY"
}

ask_yn() {
    echo -e "\n  ${YELLOW}?${NC} ${BOLD}$1${NC} ${CYAN}[j/n]${NC}"
    read -r -p "    → " REPLY
    [[ "$REPLY" =~ ^[jJyY] ]]
}

pause() {
    echo -e "\n  ${CYAN}$1${NC}"
    read -r -p "  Enter zum Fortfahren..." _
}

TOTAL_STEPS=8

# PROGRESS + SPINNER

spinner() {
    local pid=$1
    local msg=$2
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    tput civis 2>/dev/null
    while kill -0 "$pid" 2>/dev/null; do
        local c="${spin:$((i % ${#spin})):1}"
        printf "\r  \033[0;36m%s\033[0m %s..." "$c" "$msg"
        sleep 0.1
        ((i++))
    done
    printf "\r\033[K"
    tput cnorm 2>/dev/null
}

run_with_spinner() {
    local msg=$1
    shift
    ("$@" >> "$LOG_FILE" 2>&1) &
    local pid=$!
    spinner "$pid" "$msg"
    wait "$pid"
    return $?
}

print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║          🐠  CLOWNFISCHSERVER  INSTALLER             ║"
    echo "  ║              v0.5.0  |  GPL-3.0                      ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "  Willkommen! Dieses Script richtet deinen"
    echo -e "  Clownfischserver ein – Schritt für Schritt."
    echo -e "  Du wirst durch alles geführt.\n"
    echo -e "  ${YELLOW}Log-Datei: $LOG_FILE${NC}\n"
}

# STEP 1: CHECKS

step_checks() {
    step 1 "Systemcheck"

    # Root check
    [[ $EUID -ne 0 ]] && fail "Bitte als root ausführen:\n  sudo bash install.sh"
    ok "Root-Rechte vorhanden"

    # Distro detection
    if command -v apt &>/dev/null; then
        PKG_MANAGER="apt"
        DISTRO=$(grep -oP '(?<=^ID=).+' /etc/os-release | tr -d '"')
        DISTRO_VERSION=$(grep -oP '(?<=^VERSION_ID=).+' /etc/os-release | tr -d '"')
        ok "Distribution: $DISTRO $DISTRO_VERSION (apt)"
    elif command -v dnf &>/dev/null; then
        PKG_MANAGER="dnf"
        DISTRO="fedora"
        ok "Distribution: Fedora/RHEL (dnf)"
    elif command -v pacman &>/dev/null; then
        PKG_MANAGER="pacman"
        DISTRO="arch"
        ok "Distribution: Arch Linux (pacman)"
    else
        fail "Unbekannte Distribution – apt/dnf/pacman nicht gefunden."
    fi

    # RAM check
    RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
    info "RAM: ${RAM_MB}MB verfügbar"
    if [[ "$RAM_MB" -lt 2000 ]]; then
        warn "Weniger als 2GB RAM – Ollama könnte Probleme haben."
        ask_yn "Trotzdem fortfahren?" || fail "Installation abgebrochen."
    else
        ok "RAM ausreichend"
    fi

    # Disk check
    DISK_FREE=$(df -BG / | awk 'NR==2 {print $4}' | tr -d 'G')
    info "Freier Speicher: ${DISK_FREE}GB"
    [[ "$DISK_FREE" -lt 5 ]] && warn "Weniger als 5GB frei – Ollama-Modell braucht ~2GB."
    ok "Systemcheck abgeschlossen"
}

# STEP 2: PAKETE INSTALLIEREN

step_packages() {
    step 2 "Pakete installieren"

    info "Paketliste wird aktualisiert..."

    case "$PKG_MANAGER" in
        apt)
            run_with_spinner "Paketliste aktualisieren" apt-get update -qq || fail "apt update fehlgeschlagen"
            run_with_spinner "Pakete installieren" apt-get install -y -qq                 curl wget git ufw python3 python3-pip python3-venv                 sudo htop net-tools lsof rsync openssl knockd ||                 warn "Einige Pakete konnten nicht installiert werden – siehe Log"
            ;;
        dnf)
            run_with_spinner "Pakete aktualisieren" dnf update -y -q
            run_with_spinner "Pakete installieren" dnf install -y -q                 curl wget git python3 python3-pip                 sudo htop net-tools rsync openssl
            warn "knockd und ufw nicht verfügbar auf Fedora – firewalld wird genutzt"
            ;;
        pacman)
            run_with_spinner "System aktualisieren" pacman -Syu --noconfirm
            run_with_spinner "Pakete installieren" pacman -S --noconfirm                 curl wget git python python-pip                 sudo htop net-tools rsync openssl
            ;;
    esac

    ok "Pakete installiert"
}

# STEP 3: BENUTZER EINRICHTEN

step_user() {
    step 3 "Benutzer einrichten"

    echo ""
    echo -e "  ${BOLD}Welchen User soll der Clownfischserver nutzen?${NC}"
    echo -e "  ${CYAN}  Dieser User verwaltet den Server und bekommt sudo-Rechte.${NC}"
    echo -e "  ${CYAN}  Du kannst einen neuen anlegen oder einen vorhandenen nutzen.${NC}"
    echo ""

    # List existing non-system users
    EXISTING_USERS=$(awk -F: '$3>=1000 && $3<65534 {print $1}' /etc/passwd | tr '\n' ' ')
    if [[ -n "$EXISTING_USERS" ]]; then
        info "Vorhandene Benutzer: $EXISTING_USERS"
    fi

    echo -e "  ${YELLOW}?${NC} ${BOLD}Username (Enter = 'clownfish'):${NC}"
    echo -e "  ${CYAN}  Neu oder vorhandenen Namen eingeben${NC}"
    read -r -p "    → " MGMT_USER
    [[ -z "$MGMT_USER" ]] && MGMT_USER="clownfish"

    if id "$MGMT_USER" &>/dev/null; then
        warn "User '$MGMT_USER' existiert bereits – wird wiederverwendet."
    else
        useradd -m -s /bin/bash "$MGMT_USER" || fail "User konnte nicht angelegt werden"
        ok "User '$MGMT_USER' angelegt"
    fi

    # Passwordless sudo
    echo "$MGMT_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/clownfisch-$MGMT_USER"
    chmod 0440 "/etc/sudoers.d/clownfisch-$MGMT_USER"
    ok "Sudo-Rechte gesetzt (passwordless)"

    # SSH dir
    mkdir -p "/home/$MGMT_USER/.ssh"
    chmod 700 "/home/$MGMT_USER/.ssh"
    chown -R "$MGMT_USER:$MGMT_USER" "/home/$MGMT_USER"
    ok "SSH-Verzeichnis angelegt"

    # Always set a password as backup
    TEMP_PASS=$(openssl rand -base64 12)
    echo "$MGMT_USER:$TEMP_PASS" | chpasswd
    echo ""
    echo -e "  ${BOLD}${YELLOW}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${BOLD}${YELLOW}║  SSH Passwort für '$MGMT_USER':                    ║${NC}"
    echo -e "  ${BOLD}${YELLOW}║                                                    ║${NC}"
    echo -e "  ${BOLD}${YELLOW}║  ${TEMP_PASS}                          ║${NC}"
    echo -e "  ${BOLD}${YELLOW}║                                                    ║${NC}"
    echo -e "  ${BOLD}${YELLOW}║  Notiere es jetzt! SSH bleibt offen bis du         ║${NC}"
    echo -e "  ${BOLD}${YELLOW}║  im Telegram-Bot /ssh close sendest.               ║${NC}"
    echo -e "  ${BOLD}${YELLOW}╚════════════════════════════════════════════════════╝${NC}"
    pause "Passwort notiert?"
}

# STEP 4: SSH + FIREWALL

step_ssh() {
    step 4 "SSH + Firewall"

    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
    ok "sshd_config gesichert"

    # SSH – nur gezielt aendern, bestehende Config behalten!
    info "Passe sshd_config an (bestehende Einstellungen bleiben erhalten)..."

    _sshd_set() {
        local key="$1" val="$2"
        if grep -qE "^#?\s*${key}" /etc/ssh/sshd_config; then
            sed -i "s|^#\?\s*${key}.*|${key} ${val}|" /etc/ssh/sshd_config
        else
            echo "${key} ${val}" >> /etc/ssh/sshd_config
        fi
    }

    _sshd_set "PasswordAuthentication" "yes"
    _sshd_set "PubkeyAuthentication"   "yes"
    _sshd_set "X11Forwarding"          "no"
    _sshd_set "PermitRootLogin"        "yes"
    ok "sshd_config angepasst (nur relevante Zeilen geaendert)"

    systemctl restart sshd >> "$LOG_FILE" 2>&1
    ok "SSH läuft – Passwort + Key erlaubt"
    info "SSH wird erst gesperrt wenn du im Bot /ssh close sendest"

    # Firewall
    case "$PKG_MANAGER" in
        apt)
            ufw default deny incoming >> "$LOG_FILE" 2>&1
            ufw default allow outgoing >> "$LOG_FILE" 2>&1
            ufw allow 22/tcp >> "$LOG_FILE" 2>&1
            echo "y" | ufw enable >> "$LOG_FILE" 2>&1
            ok "ufw Firewall aktiv – Port 22 offen"

            # knockd
            IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
            NOTIFY_CMD="$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/bot/knock_notify.py"

            # knockd – nur clownfisch-Sektionen schreiben, bestehende Config behalten
            if [ -f /etc/knockd.conf ]; then
                # Entferne nur unsere alten Sektionen falls vorhanden
                sed -i '/^\[openSSH\]/,/^$/d' /etc/knockd.conf 2>/dev/null || true
                sed -i '/^\[closeSSH\]/,/^$/d' /etc/knockd.conf 2>/dev/null || true
                # Interface in [options] setzen falls vorhanden
                if grep -q "^\[options\]" /etc/knockd.conf; then
                    grep -q "Interface" /etc/knockd.conf ||                         sed -i "/^\[options\]/a\    Interface = $IFACE" /etc/knockd.conf
                else
                    echo -e "[options]
    UseSyslog
    Interface = $IFACE
" >> /etc/knockd.conf
                fi
            else
                # Neue Config anlegen
                cat > /etc/knockd.conf << KNOCKEOF
[options]
    UseSyslog
    Interface = $IFACE
KNOCKEOF
            fi

            # Unsere SSH-Sektionen hinzufuegen
            cat >> /etc/knockd.conf << KNOCKEOF

[openSSH]
    sequence    = 7000,8000,9000
    seq_timeout = 10
    command     = /sbin/iptables -I INPUT -s %IP% -p tcp --dport 22 -j ACCEPT && $NOTIFY_CMD open %IP%
    tcpflags    = syn

[closeSSH]
    sequence    = 9000,8000,7000
    seq_timeout = 10
    command     = /sbin/iptables -D INPUT -s %IP% -p tcp --dport 22 -j ACCEPT && $NOTIFY_CMD close %IP%
    tcpflags    = syn
KNOCKEOF
            [ -f /etc/default/knockd ] && sed -i 's/START_KNOCKD=0/START_KNOCKD=1/' /etc/default/knockd
            systemctl enable knockd >> "$LOG_FILE" 2>&1
            systemctl restart knockd >> "$LOG_FILE" 2>&1 && ok "Port-Knocking aktiv (7000→8000→9000)" || warn "knockd konnte nicht starten"
            ;;
        dnf)
            systemctl enable firewalld >> "$LOG_FILE" 2>&1
            systemctl start firewalld >> "$LOG_FILE" 2>&1
            firewall-cmd --permanent --add-service=ssh >> "$LOG_FILE" 2>&1
            firewall-cmd --reload >> "$LOG_FILE" 2>&1
            ok "firewalld aktiv – SSH offen"
            ;;
        pacman)
            warn "Bitte Firewall manuell einrichten (iptables/nftables)"
            ;;
    esac

    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  myfritz – Home-IP Auto-Update (optional)${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Wenn du ein AVM-Gerät (Fritzbox) mit myfritz.net hast,"
    echo -e "  kann der Bot deine Home-IP automatisch ins Firewall-Regelwerk"
    echo -e "  schreiben. Das bedeutet: SSH bleibt immer erreichbar, auch"
    echo -e "  wenn sich deine IP ändert (z.B. ISP, mobil, VPN)."
    echo ""
    echo -e "  ${YELLOW}?${NC} ${BOLD}Hast du ein AVM myfritz.net Gerät?${NC} [j/n]"
    read -r -p "    -> " USE_MYFRITZ

    if [[ "$USE_MYFRITZ" =~ ^[jJ]$ ]]; then
        echo ""
        echo -e "  ${YELLOW}?${NC} ${BOLD}Deine myfritz-Domain:${NC}"
        echo -e "  ${CYAN}  Format: vorname.myfritz.net${NC}"
        read -r -p "    -> " MYFRITZ_DOMAIN
        if [[ -z "$MYFRITZ_DOMAIN" ]]; then
            MYFRITZ_DOMAIN=""
            warn "myfritz übersprungen"
        else
            ok "myfritz Domain: $MYFRITZ_DOMAIN"
        fi
    else
        MYFRITZ_DOMAIN=""
        info "myfritz übersprungen"
    fi
}

# HELPER: Pull an Ollama model with progress bar

_pull_model() {
    local model_name="$1"
    echo ""
    echo -e "  ${CYAN}Lade Modell: ${BOLD}$model_name${NC}"
    echo -e "  ${CYAN}Das kann je nach Internetgeschwindigkeit 2-10 Minuten dauern.${NC}"
    echo ""

    tput civis 2>/dev/null
    ollama pull "$model_name" 2>&1 | while IFS= read -r line; do
        if [[ "$line" =~ ([0-9]+)% ]]; then
            pct="${BASH_REMATCH[1]}"
            filled=$(( pct * 30 / 100 ))
            empty=$(( 30 - filled ))
            bar=""
            for ((i=0; i<filled; i++)); do bar+="="; done
            for ((i=0; i<empty; i++)); do bar+="."; done
            printf "\r  [%-30s] %3s%%  " "$bar" "$pct"
        elif [[ "$line" == *"pulling manifest"* ]]; then
            printf "\r  Manifest wird geladen...                    "
        elif [[ "$line" == *"verifying"* ]]; then
            printf "\r  Verifiziere Modell...                       "
        elif [[ "$line" == *"writing"* ]]; then
            printf "\r  Schreibe Modell...                          "
        elif [[ "$line" == *"success"* ]]; then
            printf "\r  Download abgeschlossen!                     \n"
        fi
    done
    tput cnorm 2>/dev/null
    echo ""

    ollama list 2>/dev/null | grep -q "${model_name%%:*}" || fail "Modell konnte nicht geladen werden: $model_name"
    ok "Modell geladen: $model_name"
}

# STEP 5: OLLAMA

step_ollama() {
    step 5 "Ollama (KI-Engine)"

    echo ""
    info "Ollama ist die KI die deinen Bot intelligent macht."
    info "Es laeuft komplett lokal auf deinem Server – keine Cloud."

    if command -v ollama &>/dev/null; then
        warn "Ollama bereits installiert"
    else
        run_with_spinner "Ollama wird heruntergeladen und installiert" \
            bash -c "curl -fsSL https://ollama.com/install.sh | sh" || fail "Ollama Installation fehlgeschlagen"
        ok "Ollama installiert"
    fi

    run_with_spinner "Ollama Service starten" systemctl enable ollama
    run_with_spinner "Ollama hochfahren" bash -c "systemctl start ollama && sleep 5"

    # ─────────────────────────────────────────────────────────
    # SCHRITT 1: Coder-Modell (Aider + /shell Befehlsgenerierung)
    # ─────────────────────────────────────────────────────────
    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  [1/2] Coder-Modell${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Dieses Modell generiert Code (Aider) und Shell-Befehle (/shell)."
    echo -e "  Es muss gut programmieren koennen – Deutsch ist hier zweitrangig."
    echo ""

    # RAM-basierte Empfehlung fuer Coder
    if [[ "$RAM_MB" -ge 16000 ]]; then
        CODER_DEFAULT="qwen2.5-coder:7b"
        CODER_HINT="16GB+ RAM erkannt – bestes Code-Modell fuer CPU"
    else
        CODER_DEFAULT="qwen2.5-coder:3b"
        CODER_HINT="Kompakt und schnell auf CPU"
    fi

    echo -e "  ${CYAN}  Dein RAM: ${BOLD}${RAM_MB}MB${NC}"
    echo -e "  ${CYAN}  Empfehlung: ${BOLD}${CODER_DEFAULT}${NC}  ${CYAN}(${CODER_HINT})${NC}"
    echo ""
    echo -e "  ${CYAN}  [1] qwen2.5-coder:3b  – schnell, ~2GB RAM (unter 16GB)${NC}"
    echo -e "  ${CYAN}  [2] qwen2.5-coder:7b  – stark, ~4.5GB RAM (16GB+ empfohlen)${NC}"
    echo -e "  ${CYAN}  [3] eigenes Modell eingeben${NC}"
    echo ""
    echo -e "  ${YELLOW}?${NC} ${BOLD}Auswahl [1/2/3]:${NC} (Enter = Empfehlung)"
    read -r -p "    → " CODER_CHOICE
    case "$CODER_CHOICE" in
        1) OLLAMA_MODEL="qwen2.5-coder:3b" ;;
        2) OLLAMA_MODEL="qwen2.5-coder:7b" ;;
        3) echo -e "  ${YELLOW}?${NC} ${BOLD}Modell-Name:${NC} ${CYAN}z.B. codellama:7b${NC}"
           read -r -p "    → " OLLAMA_MODEL ;;
        *) OLLAMA_MODEL="$CODER_DEFAULT" ;;
    esac

    _pull_model "$OLLAMA_MODEL"
    ok "Coder-Modell: $OLLAMA_MODEL"

    # ─────────────────────────────────────────────────────────
    # SCHRITT 2: Chat-Modell (Deutsch, schnelle Antworten)
    # ─────────────────────────────────────────────────────────
    OLLAMA_MODEL_FAST=""

    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  [2/2] Chat-Modell (optional)${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Ein separates Chat-Modell antwortet schneller auf Nachrichten"
    echo -e "  und spricht besser Deutsch. Das Coder-Modell bleibt fuer Code."
    echo ""
    echo -e "  ${CYAN}  Coder-Modell:  ${BOLD}$OLLAMA_MODEL${NC}  ${CYAN}(bereits installiert)${NC}"
    echo ""

    if ask_yn "Separates Chat-Modell installieren? (empfohlen)"; then
        echo ""

        # RAM-basierte Empfehlung fuer Chat
        if [[ "$RAM_MB" -ge 24000 ]]; then
            CHAT_DEFAULT="mistral:7b"
            CHAT_HINT="24GB+ RAM – bestes Deutsch (franzoesische KI, exzellent in EU-Sprachen)"
            echo -e "  ${CYAN}  [1] gemma3:1b    – 800MB RAM, schnell, brauchbares Deutsch${NC}"
            echo -e "  ${CYAN}  [2] gemma3:4b    – 3GB RAM, sehr gutes Deutsch (Google multilingual)${NC}"
            echo -e "  ${BOLD}  [3] mistral:7b   – 4.5GB RAM, exzellentes Deutsch ← empfohlen${NC}"
            echo -e "  ${CYAN}  [4] eigenes Modell eingeben${NC}"
        elif [[ "$RAM_MB" -ge 12000 ]]; then
            CHAT_DEFAULT="gemma3:4b"
            CHAT_HINT="12-20GB RAM – sehr gutes Deutsch bei wenig RAM (Google multilingual)"
            echo -e "  ${CYAN}  [1] gemma3:1b    – 800MB RAM, schnell, brauchbares Deutsch${NC}"
            echo -e "  ${BOLD}  [2] gemma3:4b    – 3GB RAM, sehr gutes Deutsch ← empfohlen${NC}"
            echo -e "  ${CYAN}  [3] mistral:7b   – 4.5GB RAM, exzellentes Deutsch (viel RAM noetig)${NC}"
            echo -e "  ${CYAN}  [4] eigenes Modell eingeben${NC}"
        else
            CHAT_DEFAULT="gemma3:1b"
            CHAT_HINT="<12GB RAM – klein und schnell, spart RAM fuer System"
            echo -e "  ${BOLD}  [1] gemma3:1b    – 800MB RAM, schnell, brauchbar ← empfohlen${NC}"
            echo -e "  ${CYAN}  [2] gemma3:4b    – 3GB RAM, sehr gutes Deutsch (knapp bei <12GB)${NC}"
            echo -e "  ${CYAN}  [3] mistral:7b   – 4.5GB RAM, exzellentes Deutsch (zu gross!)${NC}"
            echo -e "  ${CYAN}  [4] eigenes Modell eingeben${NC}"
        fi

        echo ""
        echo -e "  ${CYAN}  Empfehlung: ${BOLD}${CHAT_DEFAULT}${NC}  ${CYAN}(${CHAT_HINT})${NC}"
        echo ""
        echo -e "  ${YELLOW}?${NC} ${BOLD}Auswahl [1/2/3/4]:${NC} (Enter = Empfehlung)"
        read -r -p "    → " CHAT_CHOICE
        case "$CHAT_CHOICE" in
            1) OLLAMA_MODEL_FAST="gemma3:1b" ;;
            2) OLLAMA_MODEL_FAST="gemma3:4b" ;;
            3) OLLAMA_MODEL_FAST="mistral:7b" ;;
            4) echo -e "  ${YELLOW}?${NC} ${BOLD}Modell-Name:${NC} ${CYAN}z.B. llama3.2:3b${NC}"
               read -r -p "    → " OLLAMA_MODEL_FAST ;;
            *) OLLAMA_MODEL_FAST="$CHAT_DEFAULT" ;;
        esac

        _pull_model "$OLLAMA_MODEL_FAST"
        ok "Chat-Modell: $OLLAMA_MODEL_FAST"
        echo ""
        ok "Dual-Model aktiv:"
        info "  Coder: $OLLAMA_MODEL (Code, /shell, Erklaerungen)"
        info "  Chat:  $OLLAMA_MODEL_FAST (Nachrichten, Deutsch)"
    else
        info "Single-Model: $OLLAMA_MODEL fuer alles"
    fi

    # ─────────────────────────────────────────────────────────
    # Context-Window (wie viel Text das Modell auf einmal sieht)
    # ─────────────────────────────────────────────────────────
    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  Context-Window (KI-Gedaechtnis)${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Je groesser, desto mehr Code/Text kann die KI auf einmal sehen."
    echo -e "  Groesseres Fenster = mehr RAM-Verbrauch + etwas langsamer."
    echo ""

    if [[ "$RAM_MB" -ge 24000 ]]; then
        CTX_DEFAULT=32768
        echo -e "  ${CYAN}  [1]  4096  – minimal, schnell${NC}"
        echo -e "  ${CYAN}  [2]  8192  – gut fuer /shell${NC}"
        echo -e "  ${CYAN}  [3] 16384  – ideal fuer /code${NC}"
        echo -e "  ${BOLD}  [4] 32768  – maximale Code-Qualitaet ← empfohlen${NC}"
    elif [[ "$RAM_MB" -ge 16000 ]]; then
        CTX_DEFAULT=16384
        echo -e "  ${CYAN}  [1]  4096  – minimal, schnell${NC}"
        echo -e "  ${CYAN}  [2]  8192  – gut fuer /shell${NC}"
        echo -e "  ${BOLD}  [3] 16384  – ideal fuer /code ← empfohlen${NC}"
        echo -e "  ${CYAN}  [4] 32768  – maximale Qualitaet (braucht viel RAM)${NC}"
    elif [[ "$RAM_MB" -ge 12000 ]]; then
        CTX_DEFAULT=8192
        echo -e "  ${CYAN}  [1]  4096  – minimal${NC}"
        echo -e "  ${BOLD}  [2]  8192  – guter Kompromiss ← empfohlen${NC}"
        echo -e "  ${CYAN}  [3] 16384  – groessere Scripts${NC}"
        echo -e "  ${CYAN}  [4] 32768  – nur wenn genuegend RAM${NC}"
    else
        CTX_DEFAULT=4096
        echo -e "  ${BOLD}  [1]  4096  – passend fuer wenig RAM ← empfohlen${NC}"
        echo -e "  ${CYAN}  [2]  8192  – wenn es reicht${NC}"
        echo -e "  ${CYAN}  [3] 16384  – wahrscheinlich zu viel${NC}"
        echo -e "  ${CYAN}  [4] 32768  – nicht empfohlen${NC}"
    fi

    echo ""
    echo -e "  ${YELLOW}?${NC} ${BOLD}Auswahl [1/2/3/4]:${NC} (Enter = Empfehlung)"
    read -r -p "    → " CTX_CHOICE
    case "$CTX_CHOICE" in
        1) OLLAMA_NUM_CTX=4096 ;;
        2) OLLAMA_NUM_CTX=8192 ;;
        3) OLLAMA_NUM_CTX=16384 ;;
        4) OLLAMA_NUM_CTX=32768 ;;
        *) OLLAMA_NUM_CTX=$CTX_DEFAULT ;;
    esac
    ok "Context-Window: $OLLAMA_NUM_CTX Token"
}

# STEP 6: PYTHON + PAKETE

step_python() {
    step 6 "Python-Umgebung"

    mkdir -p "$INSTALL_DIR" "$SNAPSHOT_DIR" "$WORKSPACE_DIR"

    run_with_spinner "Python Umgebung erstellen" python3 -m venv "$INSTALL_DIR/venv" || fail "venv konnte nicht erstellt werden"
    ok "Python venv erstellt"

    run_with_spinner "pip aktualisieren" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip

    run_with_spinner "Telegram-Bot Paket installieren"         "$INSTALL_DIR/venv/bin/pip" install "python-telegram-bot==21.0" requests python-dotenv ||         fail "Basis-Pakete fehlgeschlagen"
    ok "Telegram + Basis-Pakete installiert"

    # Aider bekommt ein eigenes venv – seine Dependencies kollidieren mit dem Bot
    info "Installiere aider-chat in separatem venv (2-5 Min)..."
    AIDER_VENV="$INSTALL_DIR/aider-venv"

    if python3 -m venv "$AIDER_VENV" >> "$LOG_FILE" 2>&1; then
        "$AIDER_VENV/bin/pip" install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1
        if "$AIDER_VENV/bin/pip" install aider-chat >> "$LOG_FILE" 2>&1; then
            ok "aider-chat installiert ($AIDER_VENV)"
        elif "$AIDER_VENV/bin/pip" install --no-build-isolation aider-chat >> "$LOG_FILE" 2>&1; then
            ok "aider-chat installiert (no-build-isolation)"
        else
            warn "aider-chat fehlgeschlagen – spaeter manuell:"
            info "  $AIDER_VENV/bin/pip install aider-chat"
            info "Der Bot funktioniert ohne Aider – /code ist dann nicht verfuegbar."
        fi
    else
        warn "Aider venv konnte nicht erstellt werden"
    fi
}

# STEP 7: TELEGRAM

step_telegram() {
    step 7 "Telegram Bot einrichten"

    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  Was ist ein Telegram Bot?${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Ein Bot ist ein automatisches Telegram-Konto das auf"
    echo -e "  Nachrichten reagiert. Du schreibst dem Bot – der Bot"
    echo -e "  fuehrt Befehle auf deinem Server aus."
    echo -e "  ${BOLD}Jeder braucht seinen eigenen Bot – das geht in 2 Minuten.${NC}"
    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  Schritt 1: Bot erstellen${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  1. Oeffne Telegram auf deinem Handy oder PC"
    echo -e "  2. Suche nach: ${BOLD}@BotFather${NC}"
    echo -e "  3. Sende: ${BOLD}/newbot${NC}"
    echo -e "  4. Vergib einen Anzeigenamen  (z.B. 'Mein Server Bot')"
    echo -e "  5. Vergib einen Username      (muss auf 'bot' enden)"
    echo -e "  6. Du bekommst einen ${BOLD}Token${NC} – sieht so aus:"
    echo -e "     ${CYAN}1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ${NC}"
    echo ""
    pause "Bot erstellt? Dann weiter..."

    echo -e "  ${YELLOW}?${NC} ${BOLD}Dein Bot-Token:${NC}"
    echo -e "  ${CYAN}  Den kompletten Token von @BotFather einfuegen${NC}"
    read -r -p "    -> " BOT_TOKEN
    [[ -z "$BOT_TOKEN" ]] && fail "Kein Token eingegeben."
    ok "Token gespeichert"

    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  Schritt 2: Deine Chat-ID herausfinden${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  1. Suche in Telegram nach: ${BOLD}@userinfobot${NC}"
    echo -e "  2. Sende irgendetwas (z.B. 'hi')"
    echo -e "  3. Der Bot antwortet mit deiner ${BOLD}Id${NC} – das ist deine Chat-ID"
    echo ""
    pause "Chat-ID gefunden? Dann weiter..."

    echo -e "  ${YELLOW}?${NC} ${BOLD}Deine Chat-ID:${NC}"
    echo -e "  ${CYAN}  Nur die Zahl, keine anderen Zeichen${NC}"
    read -r -p "    -> " CHAT_ID
    [[ -z "$CHAT_ID" ]] && fail "Keine Chat-ID eingegeben."
    ok "Chat-ID gespeichert"

    # ─────────────────────────────────────────────────────────
    # OpenRouter Fallback (optional, kostenlos)
    # ─────────────────────────────────────────────────────────
    OPENROUTER_API_KEY=""
    
    echo ""
    echo -e "  ${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${BOLD}  OpenRouter Fallback (optional)${NC}"
    echo -e "  ${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Wenn dein Ollama offline ist, kann der Bot auf Cloud-Modelle ausweichen."
    echo -e "  OpenRouter Free Tier: 50 Requests/Tag kostenlos (keine Kreditkarte!)"
    echo ""

    if ask_yn "OpenRouter als Fallback aktivieren?"; then
        echo ""
        echo -e "  ${CYAN}Registrier dich kostenlos: https://openrouter.ai${NC}"
        echo -e "  ${CYAN}Dann kopier deinen API Key von der Dashboard${NC}"
        echo ""
        echo -e "  ${YELLOW}?${NC} ${BOLD}OpenRouter API Key:${NC}"
        echo -e "  ${CYAN}  Format: sk-or-v1-...${NC}"
        read -r -p "    → " OPENROUTER_API_KEY
        
        if [[ -z "$OPENROUTER_API_KEY" ]]; then
            warn "Leerer Key – OpenRouter deaktiviert"
            OPENROUTER_API_KEY=""
        else
            ok "OpenRouter aktiviert"
        fi
    else
        info "OpenRouter deaktiviert – Bot nutzt nur lokal Ollama"
    fi

    mkdir -p "$INSTALL_DIR/config"
    cat > "$INSTALL_DIR/config/.env" << ENVEOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_CHAT_ID=$CHAT_ID
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=$OLLAMA_MODEL
OLLAMA_MODEL_FAST=$OLLAMA_MODEL_FAST
OLLAMA_NUM_CTX=$OLLAMA_NUM_CTX
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
SNAPSHOT_DIR=$SNAPSHOT_DIR
SNAPSHOT_METHOD=$SNAPSHOT_METHOD
INSTALL_DIR=$INSTALL_DIR
MGMT_USER=$MGMT_USER
AIDER_WORKDIR=$WORKSPACE_DIR
CLOWNFISCHSERVER_HOME_IP_DOMAIN=$MYFRITZ_DOMAIN
ENVEOF

    chmod 600 "$INSTALL_DIR/config/.env"
    ok "Konfiguration gespeichert"
}

# STEP 8: BOT STARTEN

step_service() {
    step 8 "Bot installieren + starten"

    mkdir -p "$INSTALL_DIR/bot"
    cp -r "$SCRIPT_DIR/bot/"* "$INSTALL_DIR/bot/" || fail "Bot-Dateien nicht gefunden – ist der bot/ Ordner dabei?"
    ok "Bot-Dateien kopiert"

    mkdir -p "$INSTALL_DIR/scripts"
    if [ -d "$SCRIPT_DIR/scripts" ]; then
        cp -r "$SCRIPT_DIR/scripts/"* "$INSTALL_DIR/scripts/" 2>/dev/null || true
        chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
        ok "Scripts kopiert"
    fi

    chown -R "$MGMT_USER:$MGMT_USER" "$INSTALL_DIR" "$SNAPSHOT_DIR" "$WORKSPACE_DIR"
    chmod -R u+w "$INSTALL_DIR/bot"
    ok "Verzeichnis-Rechte gesetzt"

    cat > /etc/systemd/system/clownfisch.service << SERVICEEOF
[Unit]
Description=🐠 Clownfischserver Telegram Bot
Documentation=https://github.com/mehlzoerwer-claude/clownfischserver
After=network-online.target ollama.service
Wants=network-online.target ollama.service

[Service]
Type=simple
User=$MGMT_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/config/.env
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/bot/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=clownfisch
# Allow sudo and iptables for SSH management
AmbientCapabilities=CAP_NET_ADMIN CAP_SYS_ADMIN
SecureBits=keep-caps
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
SERVICEEOF

    run_with_spinner "Systemd neu laden" systemctl daemon-reload
    run_with_spinner "Bot-Service aktivieren" systemctl enable clownfisch
    run_with_spinner "Bot starten" systemctl start clownfisch
    sleep 3

    if systemctl is-active --quiet clownfisch; then
        ok "Bot laeuft!"
    else
        warn "Bot gestartet – check Logs: journalctl -u clownfisch -n 20 --no-pager"
    fi

    # Boot-Notification Service
    cat > /etc/systemd/system/clownfisch-boot.service << BOOTEOF
[Unit]
Description=🐠 Clownfischserver Boot Notification
Documentation=https://github.com/mehlzoerwer-claude/clownfischserver
After=network-online.target clownfisch.service ollama.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 120
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/bot/boot_notify.py
EnvironmentFile=$INSTALL_DIR/config/.env
WorkingDirectory=$INSTALL_DIR
StandardOutput=journal
StandardError=journal
SyslogIdentifier=clownfisch-boot

[Install]
WantedBy=multi-user.target
BOOTEOF

    run_with_spinner "Boot-Notification aktivieren" bash -c "systemctl daemon-reload && systemctl enable clownfisch-boot"
    ok "Boot-Notification: Telegram-Meldung 2 Min nach Serverstart"

    # HomeIP Updater – falls myfritz konfiguriert
    if [[ -n "$MYFRITZ_DOMAIN" ]]; then
        echo ""
        info "Installiere HomeIP Auto-Updater (5-Min Cron)..."

        # Copy the homeip-updater script if it exists
        if [ -f "$SCRIPT_DIR/scripts/clownfischserver-homeip-updater.sh" ]; then
            mkdir -p /opt/clownfischserver-scripts
            cp "$SCRIPT_DIR/scripts/clownfischserver-homeip-updater.sh" /opt/clownfischserver/scripts/
            chmod +x /opt/clownfischserver/scripts/clownfischserver-homeip-updater.sh

            # Add cron job (every 5 minutes)
            CRON_JOB="*/5 * * * * /opt/clownfischserver/scripts/clownfischserver-homeip-updater.sh >> /var/log/clownfischserver-homeip-updater.log 2>&1"
            (crontab -l 2>/dev/null | grep -v "clownfischserver-homeip-updater" ; echo "$CRON_JOB") | crontab - 2>/dev/null || true

            ok "HomeIP Auto-Updater installiert (myfritz: $MYFRITZ_DOMAIN)"
        else
            warn "homeip-updater Script nicht gefunden – übersprungen"
        fi
    fi
}

# ZUSAMMENFASSUNG

print_summary() {
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "  +======================================================+"
    echo "  |        CLOWNFISCHSERVER BEREIT!  v0.5.0              |"
    echo "  +======================================================+"
    echo -e "${NC}"
    echo -e "  ${BOLD}Server:${NC}      $SERVER_IP"
    echo -e "  ${BOLD}SSH User:${NC}    $MGMT_USER  (Passwort aktiv!)"
    echo -e "  ${BOLD}KI-Modell:${NC}   $OLLAMA_MODEL"
    echo -e "  ${BOLD}Snapshots:${NC}   $SNAPSHOT_DIR ($SNAPSHOT_METHOD)"
    echo -e "  ${BOLD}Logs:${NC}        journalctl -u clownfisch -f"
    echo -e "  ${BOLD}Install-Log:${NC} $LOG_FILE"
    echo ""
    echo -e "  ${CYAN}${BOLD}Erste Schritte:${NC}"
    echo -e "  ${CYAN}  1. Schreibe deinem Bot: /start${NC}"
    echo -e "  ${CYAN}  2. Teste mit:           /status${NC}"
    echo -e "  ${CYAN}  3. Wenn alles laeuft:   /ssh close${NC}"
    echo ""
    echo -e "  ${CYAN}${BOLD}Notfall-Befehle im Bot:${NC}"
    echo -e "  ${CYAN}  /run <befehl>     -> direkte Shell ohne KI${NC}"
    echo -e "  ${CYAN}  /ssh open         -> SSH oeffnen${NC}"
    echo -e "  ${CYAN}  /ssh open 1.2.3.4 -> SSH nur fuer deine IP${NC}"
    echo -e "  ${CYAN}  /ssh close        -> SSH sperren${NC}"
    echo ""
    echo -e "  ${YELLOW}Install-Log (letzte 10 Zeilen):${NC}"
    tail -10 "$LOG_FILE"
    echo ""
}

# MAIN

update_bot() {
    echo -e "
${BOLD}${CYAN}🐠 Clownfischserver Update-Modus${NC}
"
    log "=== Update gestartet ==="

    # Read MGMT_USER from .env if not set
    if [[ -z "$MGMT_USER" ]] && [[ -f "$INSTALL_DIR/config/.env" ]]; then
        MGMT_USER=$(grep "^MGMT_USER=" "$INSTALL_DIR/config/.env" | cut -d= -f2)
    fi
    [[ -z "$MGMT_USER" ]] && MGMT_USER="clownfish"

    # Copy new bot files
    cp -r "$SCRIPT_DIR/bot/"* "$INSTALL_DIR/bot/"
    chown -R "$MGMT_USER:$MGMT_USER" "$INSTALL_DIR/bot"
    ok "Bot-Dateien aktualisiert"

    # Update systemd services – patch hardcoded user with actual MGMT_USER
    for svc in clownfisch.service clownfisch-boot.service; do
        if [ -f "$SCRIPT_DIR/systemd/$svc" ]; then
            sed "s/^User=.*/User=$MGMT_USER/;s/^Group=.*/Group=$MGMT_USER/" \
                "$SCRIPT_DIR/systemd/$svc" > "/etc/systemd/system/$svc"
            [[ "$svc" == "clownfisch-boot.service" ]] && systemctl enable clownfisch-boot >> "$LOG_FILE" 2>&1
        fi
    done
    systemctl daemon-reload >> "$LOG_FILE" 2>&1
    ok "Systemd Services aktualisiert (User=$MGMT_USER)"

    # Restart
    systemctl restart clownfisch >> "$LOG_FILE" 2>&1
    sleep 3
    if systemctl is-active --quiet clownfisch; then
        ok "Bot neu gestartet – Update abgeschlossen!"
    else
        warn "Bot-Status unklar: journalctl -u clownfisch -n 20 --no-pager"
    fi

    echo ""
    echo -e "  ${CYAN}Logs: journalctl -u clownfisch -f${NC}"
    echo ""
    log "=== Update abgeschlossen ==="
}

main() {
    print_banner
    touch "$LOG_FILE"

    # Update mode: service already running
    if systemctl is-active --quiet clownfisch 2>/dev/null; then
        echo -e "  ${YELLOW}⚠${NC} Clownfischserver läuft bereits!"
        echo ""
        echo -e "  ${CYAN}[1]${NC} Update (Bot-Dateien + Restart)"
        echo -e "  ${CYAN}[2]${NC} Neuinstallation (alles neu)"
        echo -e "  ${CYAN}[3]${NC} Abbrechen"
        echo ""
        read -r -p "  → " CHOICE
        case "$CHOICE" in
            1) update_bot; exit 0 ;;
            2) echo "" ;;
            *) echo "Abgebrochen."; exit 0 ;;
        esac
    fi

    log "=== Clownfischserver v0.5.0 Installation gestartet ==="
    step_checks
    step_packages
    step_user
    step_ssh
    step_ollama
    step_python
    step_telegram
    step_service
    print_summary
    log "=== Installation abgeschlossen ==="
}

main "$@"
