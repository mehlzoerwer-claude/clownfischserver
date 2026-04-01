#!/bin/bash
# =============================================================================
# 🐠 CLOWNFISCHSERVER
# Version: see banner
# Author:  Mehlzoerwer-Claude (https://github.com/mehlzoerwer-claude)
# License: GPL-3.0 – Keep it open. Always.
# Repo:    https://github.com/mehlzoerwer-claude/clownfischserver
# =============================================================================

# GPL-3.0 License - Keep it open. Always.
# https://github.com/YOUR_USERNAME/clownfischserver

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
SNAPSHOT_METHOD="tar"

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
    "$@" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    spinner "$pid" "$msg"
    wait "$pid"
    return $?
}


progress_bar() {
    local current=$1
    local total=$2
    local msg=$3
    local width=40
    local pct=$(( current * 100 / total ))
    local filled=$(( current * width / total ))
    local empty=$(( width - filled ))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++));  do bar+="░"; done
    echo -ne "  ${CYAN}[${bar}]${NC} ${pct}% ${msg}
"
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
    echo "  ║              v0.4.1  |  GPL-3.0                      ║"
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
}

# STEP 5: OLLAMA

step_ollama() {
    step 5 "Ollama (KI-Engine)"

    echo ""
    info "Ollama ist die KI die deinen Bot intelligent macht."
    info "Es läuft komplett lokal auf deinem Server – keine Cloud."

    if command -v ollama &>/dev/null; then
        warn "Ollama bereits installiert"
    else
        run_with_spinner "Ollama wird heruntergeladen und installiert"             bash -c "curl -fsSL https://ollama.com/install.sh | sh" || fail "Ollama Installation fehlgeschlagen"
        ok "Ollama installiert"
    fi

    run_with_spinner "Ollama Service starten" systemctl enable ollama
    run_with_spinner "Ollama hochfahren" bash -c "systemctl start ollama && sleep 5"

    # Check existing models
    OLLAMA_MODEL=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}' | head -1)

    if [[ -n "$OLLAMA_MODEL" ]]; then
        ok "Vorhandenes Modell erkannt: $OLLAMA_MODEL"
    else
        echo ""
        echo -e "  ${BOLD}Welches KI-Modell soll installiert werden?${NC}"
        echo -e "  ${CYAN}  Empfehlung je nach RAM:${NC}"
        echo -e "  ${CYAN}  [1] qwen2.5:2b  – klein,  schnell, ~2GB RAM  (empfohlen für <8GB)${NC}"
        echo -e "  ${CYAN}  [2] qwen3.5:4b  – größer, schlauer, ~6GB RAM (empfohlen für 8GB+)${NC}"
        echo -e "  ${CYAN}  [3] eigenes Modell eingeben${NC}"
        echo ""
        echo -e "  ${YELLOW}?${NC} ${BOLD}Auswahl [1/2/3]:${NC}"
        read -r -p "    → " MODEL_CHOICE
        case "$MODEL_CHOICE" in
            2) OLLAMA_MODEL="qwen3.5:4b" ;;
            3) echo -e "  ${YELLOW}?${NC} ${BOLD}Modell-Name:${NC} ${CYAN}z.B. llama3:8b${NC}"
               read -r -p "    → " OLLAMA_MODEL ;;
            *) OLLAMA_MODEL="qwen2.5:2b" ;;
        esac

        echo ""
        echo -e "  ${CYAN}Lade Modell: ${BOLD}$OLLAMA_MODEL${NC}"
        echo -e "  ${CYAN}Das kann je nach Internetgeschwindigkeit 2-10 Minuten dauern.${NC}"
        echo ""

        # Live progress from ollama pull
        tput civis 2>/dev/null
        ollama pull "$OLLAMA_MODEL" 2>&1 | while IFS= read -r line; do
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

        # Verify
        ollama list 2>/dev/null | grep -q "${OLLAMA_MODEL%%:*}" || fail "Modell konnte nicht geladen werden"
        ok "Modell geladen: $OLLAMA_MODEL"
    fi
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

    run_with_spinner "setuptools + wheel aktualisieren"         bash -c '"$INSTALL_DIR/venv/bin/pip" install --upgrade setuptools wheel pip >> "$LOG_FILE" 2>&1'

    info "Installiere aider-chat (Coding-Agent, 2-5 Min)..."
    if "$INSTALL_DIR/venv/bin/pip" install aider-chat >> "$LOG_FILE" 2>&1; then
        ok "aider-chat installiert"
    elif "$INSTALL_DIR/venv/bin/pip" install --no-build-isolation aider-chat >> "$LOG_FILE" 2>&1; then
        ok "aider-chat installiert"
    else
        warn "aider-chat fehlgeschlagen – spaeter: $INSTALL_DIR/venv/bin/pip install --no-build-isolation aider-chat"
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

    mkdir -p "$INSTALL_DIR/config"
    cat > "$INSTALL_DIR/config/.env" << ENVEOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_CHAT_ID=$CHAT_ID
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=$OLLAMA_MODEL
SNAPSHOT_DIR=$SNAPSHOT_DIR
SNAPSHOT_METHOD=$SNAPSHOT_METHOD
INSTALL_DIR=$INSTALL_DIR
MGMT_USER=$MGMT_USER
AIDER_WORKDIR=$WORKSPACE_DIR
ENVEOF

    chmod 644 "$INSTALL_DIR/config/.env"
    ok "Konfiguration gespeichert"
}

# STEP 8: BOT STARTEN

step_service() {
    step 8 "Bot installieren + starten"

    mkdir -p "$INSTALL_DIR/bot"
    cp -r "$SCRIPT_DIR/bot/"* "$INSTALL_DIR/bot/" || fail "Bot-Dateien nicht gefunden – ist der bot/ Ordner dabei?"
    ok "Bot-Dateien kopiert"

    chown -R "$MGMT_USER:$MGMT_USER" "$INSTALL_DIR" "$SNAPSHOT_DIR" "$WORKSPACE_DIR"
    chmod -R u+w "$INSTALL_DIR/bot"
    ok "Verzeichnis-Rechte gesetzt"

    cat > /etc/systemd/system/clownfisch.service << SERVICEEOF
[Unit]
Description=Clownfischserver Telegram Bot
After=network.target ollama.service
Wants=ollama.service

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
# Allow sudo and system commands
AmbientCapabilities=CAP_NET_ADMIN CAP_SYS_ADMIN
SecureBits=keep-caps

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
}

# ZUSAMMENFASSUNG

print_summary() {
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "  +======================================================+"
    echo "  |        CLOWNFISCHSERVER BEREIT!  v0.4.1              |"
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

    # Copy new bot files
    cp -r "$SCRIPT_DIR/bot/"* "$INSTALL_DIR/bot/"
    chown -R "$MGMT_USER:$MGMT_USER" "$INSTALL_DIR/bot"
    ok "Bot-Dateien aktualisiert"

    # Update systemd service if changed
    cp "$SCRIPT_DIR/systemd/clownfisch.service" /etc/systemd/system/clownfisch.service
    systemctl daemon-reload >> "$LOG_FILE" 2>&1
    ok "Systemd Service aktualisiert"

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

    log "=== Clownfischserver v0.4.1 Installation gestartet ==="
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
