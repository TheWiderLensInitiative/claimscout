#!/usr/bin/env bash
# ClaimScout server installer (Linux). Run from the repo:  ./install.sh
# Makes server/.venv, installs the requirements, and starts ClaimScout as a systemd user service at login.
# macOS / Windows (WSL without systemd): see README.md for the manual steps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
cd "$SERVER"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

say "Python environment"
if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 .venv >/dev/null
    uv pip install --python .venv/bin/python -q -r requirements.txt
else
    PY="$(command -v python3 || true)"
    [ -n "$PY" ] || { echo "Install Python 3.10 or newer first (or uv: https://docs.astral.sh/uv/)."; exit 1; }
    "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10 or newer is needed."; exit 1; }
    "$PY" -m venv .venv || { echo "Couldn't make a venv. On Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
fi

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    say "Starting ClaimScout at login (systemd user service)"
    mkdir -p "$HOME/.config/systemd/user"
    sed -e "s#%h/claimscout/server#$SERVER#g" systemd/claimscout.service > "$HOME/.config/systemd/user/claimscout.service"
    systemctl --user daemon-reload
    systemctl --user enable --now claimscout >/dev/null
    systemctl --user restart claimscout
    # keep running after logout (asks for your password only if it isn't already on)
    loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes || loginctl enable-linger "$USER" 2>/dev/null || true
    STARTED=1
else
    STARTED=0
fi

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    echo
    echo "Your firewall (ufw) is on. Let the phone reach port 8787 from your home network or Tailscale, e.g.:"
    echo "  sudo ufw allow from 192.168.0.0/16 to any port 8787 proto tcp"
    echo "  sudo ufw allow in on tailscale0 to any port 8787 proto tcp"
fi

echo
say "Done"
if [ "$STARTED" = 1 ]; then
    echo "ClaimScout is running. Open the dashboard:  $SERVER/.venv/bin/python -m claimscout open"
    echo "Logs:  journalctl --user -u claimscout -f"
else
    echo "Start it with:  cd $SERVER && .venv/bin/python -m claimscout serve"
fi
echo "Then fill in your profile (or let the phone's questionnaire do it) and pair the phone from the Phone tab."
echo "Phone app: https://github.com/TheWiderLensInitiative/claimscout/releases/latest"
