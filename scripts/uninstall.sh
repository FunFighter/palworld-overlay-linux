#!/usr/bin/env bash
# Remove the Palworld live map overlay. Keeps config.json unless --purge.
set -euo pipefail
PROJ="${PALWORLD_MAP_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/palworld-live-map}"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

systemctl --user disable --now palworld-live-map.service 2>/dev/null || true
systemctl --user disable --now palworld-rest-tunnel.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/palworld-live-map.service"
rm -f "$HOME/.config/systemd/user/palworld-rest-tunnel.service"
systemctl --user daemon-reload 2>/dev/null || true

rm -f "$HOME/.local/bin/palworld-overlay"
rm -f "$HOME/.local/share/applications/palworld-overlay.desktop"
rm -f "$HOME/.local/share/icons/hicolor/"*/apps/palworld-overlay.png
rm -f "${XDG_RUNTIME_DIR:-/tmp}/palworld-overlay.pid"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if [ "$PURGE" = 1 ]; then
  rm -rf "$PROJ"
  echo "Removed everything including $PROJ"
else
  rm -rf "$PROJ/data" "$PROJ/vendor" "$PROJ/tools/node_modules"
  rm -f  "$PROJ/server.py" "$PROJ/overlay.py" "$PROJ/index.html" "$PROJ/window.json"
  echo "Removed app files. Kept $PROJ/config.json - delete it or re-run with --purge."
fi
echo "Note: the Meta+P entry in ~/.config/kglobalshortcutsrc is left in place."
