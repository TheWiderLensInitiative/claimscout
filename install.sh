#!/usr/bin/env bash
# ClaimScout installer and updater (Linux).
#
#   From anywhere:   curl -fsSL https://raw.githubusercontent.com/TheWiderLensInitiative/claimscout/main/install.sh | bash
#   From the repo:   ./install.sh            (run it again any time to update)
#   Remove it:       ./install.sh --uninstall
#
# It gets Python if needed (via uv, no sudo), installs the server, starts it at login, offers to open the firewall
# for your home network, then shows two QR codes: one to download the phone app and one to pair it.
set -euo pipefail
trap 'printf "\n\033[31mThe installer stopped at line %s (%s).\033[0m Run it again; if it keeps failing, open an issue at\nhttps://github.com/TheWiderLensInitiative/claimscout/issues with this output.\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

REPO="${CLAIMSCOUT_REPO:-https://github.com/TheWiderLensInitiative/claimscout}"
APK_URL="https://github.com/TheWiderLensInitiative/claimscout/releases/latest"
PORT="${CLAIMSCOUT_PORT:-8787}"
WEB_PORT="${CLAIMSCOUT_WEB_PORT:-8788}"

say()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
ask()  {   # ask "Question?" -> 0 for yes. Reads the terminal even when piped from curl; no terminal = no.
    local a=""
    [ -r /dev/tty ] || return 1
    printf '    %s [Y/n] ' "$1" > /dev/tty
    read -r a < /dev/tty || return 1
    [[ -z "$a" || "$a" =~ ^[Yy] ]]
}

# --- where the code lives: this repo, or a fresh clone in ~/claimscout ------------------------------------------
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$(dirname "$SELF")/server/claimscout/__main__.py" ]; then
    ROOT="$(cd "$(dirname "$SELF")" && pwd)"
else
    ROOT="${CLAIMSCOUT_DIR:-$HOME/claimscout}"
    if [ -d "$ROOT/.git" ]; then
        exec bash "$ROOT/install.sh" "$@"   # already cloned: let that copy update itself
    fi
    say "Downloading ClaimScout to $ROOT"
    if command -v git >/dev/null 2>&1; then
        git clone -q "$REPO" "$ROOT"
    else
        mkdir -p "$ROOT"
        curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar xz -C "$ROOT" --strip-components=1
        warn "git isn't installed, so updates will need a fresh download (or: sudo apt install git)"
    fi
    exec bash "$ROOT/install.sh" "$@"
fi
SERVER="$ROOT/server"
UNIT="$HOME/.config/systemd/user/claimscout.service"
BIN="$HOME/.local/bin"
HAS_SYSTEMD=0
command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1 && HAS_SYSTEMD=1

# --- uninstall ---------------------------------------------------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
    say "Removing ClaimScout"
    if [ "$HAS_SYSTEMD" = 1 ]; then
        systemctl --user disable --now claimscout 2>/dev/null || true
        rm -f "$UNIT"; systemctl --user daemon-reload
        ok "stopped and removed the service"
    fi
    rm -f "$BIN/claimscout" && ok "removed the claimscout command"
    rm -rf "$SERVER/.venv" && ok "removed the Python environment"
    echo
    echo "    Your data (profile, matches, claims) is still in ~/.local/share/claimscout."
    echo "    Delete it too with:  rm -rf ~/.local/share/claimscout"
    echo "    The code is in $ROOT. Uninstall the phone app from the phone."
    exit 0
fi

# --- 1. Python ---------------------------------------------------------------------------------------------------
say "1/4  Python"
cd "$SERVER"
export PATH="$BIN:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        :
    else
        echo "    Installing uv (a small tool that downloads the right Python into your home folder; no sudo)"
        curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
            || die "Couldn't install uv. Check your internet connection, or install Python 3.10+ yourself."
    fi
fi
if command -v uv >/dev/null 2>&1; then
    [ -x .venv/bin/python ] || uv venv -q --python 3.12 .venv
    uv pip install --python .venv/bin/python -q -r requirements.txt
else
    [ -x .venv/bin/python ] || python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
fi
ok "Python $(.venv/bin/python -c 'import platform; print(platform.python_version())') with everything ClaimScout needs"

mkdir -p "$BIN"
cat > "$BIN/claimscout" <<EOF
#!/bin/sh
# ClaimScout command (made by install.sh)
cd "$SERVER" && exec "$SERVER/.venv/bin/python" -m claimscout "\$@"
EOF
chmod +x "$BIN/claimscout"
ok "the 'claimscout' command (try: claimscout doctor)"
command -v claimscout >/dev/null 2>&1 || warn "$BIN isn't on your PATH yet; open a new terminal or log out and back in"

# --- 2. Run at login ---------------------------------------------------------------------------------------------
say "2/4  Starting ClaimScout"
if [ "$HAS_SYSTEMD" = 1 ]; then
    mkdir -p "$(dirname "$UNIT")"
    sed -e "s#%h/claimscout/server#$SERVER#g" systemd/claimscout.service > "$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable claimscout >/dev/null 2>&1
    systemctl --user restart claimscout
    # keep running when you're logged out (may ask for your password once)
    loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes || loginctl enable-linger "$USER" 2>/dev/null || true
    ok "runs in the background and starts at login (logs: journalctl --user -u claimscout -f)"
else
    nohup "$SERVER/.venv/bin/python" -m claimscout serve --port "$PORT" --web-port "$WEB_PORT" > "$HOME/.local/share/claimscout-server.log" 2>&1 &
    warn "no systemd here, so it's running now but won't start at login. Start it later with: claimscout serve"
fi
for _ in $(seq 40); do
    curl -fs -o /dev/null "http://127.0.0.1:$WEB_PORT/" && break
    sleep 0.5
done
curl -fs -o /dev/null "http://127.0.0.1:$WEB_PORT/" || die "ClaimScout didn't start. See: journalctl --user -u claimscout -n 50"
ok "server is up"

# --- 3. Firewall -------------------------------------------------------------------------------------------------
say "3/4  Firewall"
LAN_NET="$(ip -o -f inet route show scope link 2>/dev/null | awk '$1 !~ /^(169\.254|172\.17)/ && $3 !~ /^(docker|br-|virbr|tailscale)/ {print $1; exit}')"
FW=""
if command -v ufw >/dev/null 2>&1 && grep -qs '^ENABLED=yes' /etc/ufw/ufw.conf; then FW=ufw
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active -q firewalld 2>/dev/null; then FW=firewalld
fi
if [ -z "$FW" ]; then
    ok "no firewall is on, so the phone can reach port $PORT"
elif [ -f "$ROOT/.firewall-done" ]; then
    ok "port $PORT is already open for your home network"
else
    echo "    Your firewall ($FW) is on. The phone needs port $PORT, from your home network${LAN_NET:+ ($LAN_NET)} and Tailscale only."
    if ask "Open it now? (asks for your password)"; then
        if [ "$FW" = ufw ]; then
            [ -n "$LAN_NET" ] && sudo ufw allow from "$LAN_NET" to any port "$PORT" proto tcp comment ClaimScout >/dev/null
            ip link show tailscale0 >/dev/null 2>&1 && sudo ufw allow in on tailscale0 to any port "$PORT" proto tcp comment ClaimScout >/dev/null
        else
            sudo firewall-cmd -q --permanent --zone=home --add-port="$PORT/tcp"
            [ -n "$LAN_NET" ] && sudo firewall-cmd -q --permanent --zone=home --add-source="$LAN_NET"
            sudo firewall-cmd -q --reload
        fi
        touch "$ROOT/.firewall-done"
        ok "opened"
    else
        warn "skipped. Later: sudo ufw allow from ${LAN_NET:-192.168.1.0/24} to any port $PORT proto tcp"
    fi
fi
command -v tailscale >/dev/null 2>&1 && ok "Tailscale found: the phone can reach this PC away from home too" \
    || echo "    Tip: install Tailscale (free) on this PC and the phone to use ClaimScout away from home: https://tailscale.com/download"

# --- 4. Phone ----------------------------------------------------------------------------------------------------
say "4/4  Your phone"
cd "$SERVER"
echo "    a) Scan this with your phone's camera to download the app (Android 9+):"
.venv/bin/python - "$APK_URL" <<'EOF'
import sys, qrcode
q = qrcode.QRCode(border=1); q.add_data(sys.argv[1]); q.print_ascii(invert=True)
print("   ", sys.argv[1])
EOF
echo
echo "    b) Open the app, then scan this to pair it with this PC:"
.venv/bin/python -m claimscout pair --qr-only
echo
echo "    Lost this screen? Run: claimscout pair    Something not working? Run: claimscout doctor"
echo "    Dashboard (profile, AI, sources) on this PC: claimscout open"
echo
printf '\033[1;32mClaimScout is installed.\033[0m It\x27s checking the settlement sites now; your matches appear in the app after the questionnaire.\n'
