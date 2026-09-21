#!/usr/bin/env bash
# Open the dev site to other devices on your Wi-Fi (e.g. to scan a table QR code with a phone).
#
#   scripts/lan-dev.sh on [restaurant-slug]    # default restaurant: luigis
#   scripts/lan-dev.sh off                     # back to localhost-only
#
# Why it is needed: "<slug>.localhost" and "localhost" only exist on this computer. Over the network the site is
# reached by IP address, so (1) the browser must call the API at that IP, (2) the API must allow that origin, and
# (3) the restaurant is the default one, because an IP address has no subdomain to name it.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=.env
BACKUP=.env.lan-backup

set_var() { # set_var NAME VALUE  (replaces the line, or appends it)
  if grep -q "^$1=" "$ENV_FILE"; then sed -i.tmp "s|^$1=.*|$1=$2|" "$ENV_FILE" && rm -f "$ENV_FILE.tmp"; else echo "$1=$2" >> "$ENV_FILE"; fi
}

case "${1:-}" in
  on)
    IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
    [ -n "$IP" ] || { echo "Could not find this computer's Wi-Fi address. Are you connected?"; exit 1; }
    [ -f "$BACKUP" ] || cp "$ENV_FILE" "$BACKUP"
    set_var NUXT_PUBLIC_API_URL "http://$IP:8000"
    set_var CORS_ORIGINS "http://localhost:3000,http://127.0.0.1:3000,http://$IP:3000"
    set_var DEFAULT_TENANT_SLUG "${2:-luigis}"
    docker compose up -d backend frontend
    echo
    echo "Ready. On this computer AND on your phone (same Wi-Fi) open:  http://$IP:3000"
    echo "To get QR codes that work on a phone, open the admin from  http://$IP:3000/admin/qr  (not from localhost)."
    echo "If the phone cannot connect, allow incoming connections for Docker in macOS: System Settings > Network > Firewall."
    echo "Undo with: scripts/lan-dev.sh off"
    ;;
  off)
    [ -f "$BACKUP" ] || { echo "Nothing to undo."; exit 0; }
    mv "$BACKUP" "$ENV_FILE"
    docker compose up -d backend frontend
    echo "Back to localhost-only."
    ;;
  *) echo "Usage: $0 on [restaurant-slug] | off"; exit 2 ;;
esac
