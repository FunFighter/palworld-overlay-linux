#!/usr/bin/env bash
# Install the Palworld live map overlay into ~/.local/share/palworld-live-map.
# Idempotent: safe to re-run to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${PALWORLD_MAP_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/palworld-live-map}"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
UNITS="$HOME/.config/systemd/user"
PY="${PALWORLD_MAP_PYTHON:-/usr/bin/python3}"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !! \033[0m%s\n' "$*"; }
die()  { printf '\033[1;31mERROR\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- prerequisites
say "Checking prerequisites"
missing=()
command -v "$PY" >/dev/null      || missing+=("python3")
command -v node >/dev/null       || missing+=("nodejs")
command -v npm  >/dev/null       || missing+=("npm")
command -v curl >/dev/null       || missing+=("curl")
[ ${#missing[@]} -eq 0 ] || die "missing commands: ${missing[*]}"

"$PY" - <<'PYEOF' || die "Python GObject bindings are incomplete (see README prerequisites)"
import sys
try:
    import gi
except ImportError:
    sys.exit("python-gobject (gi) not found")
bad = []
for mod, ver in (("Gtk", "3.0"), ("WebKit2", "4.1"), ("GtkLayerShell", "0.1")):
    try:
        gi.require_version(mod, ver)
    except Exception:
        bad.append(f"{mod} {ver}")
if bad:
    sys.exit("missing typelibs: " + ", ".join(bad))
PYEOF

if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  warn "WAYLAND_DISPLAY is unset - the overlay needs a Wayland session to draw over fullscreen."
fi

# ------------------------------------------------------------------- app files
say "Installing to $PROJ"
mkdir -p "$PROJ/vendor" "$PROJ/tools" "$PROJ/data"
install -m644 "$SRC/server.py" "$SRC/overlay.py" "$SRC/index.html" "$PROJ/"
install -m644 "$SRC/tools/fetch_data.mjs" "$SRC/tools/package.json" "$PROJ/tools/"

if [ ! -f "$PROJ/config.json" ]; then
  install -m600 "$SRC/config.example.json" "$PROJ/config.json"
  NEWCONFIG=1
  say "Created $PROJ/config.json (mode 0600) - you must edit it"
else
  chmod 600 "$PROJ/config.json"
  say "Kept existing config.json"
fi

# --------------------------------------------------------------------- Leaflet
if [ ! -f "$PROJ/vendor/leaflet.js" ]; then
  say "Fetching Leaflet 1.9.4"
  curl -fsSL -o "$PROJ/vendor/leaflet.js"  https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
  curl -fsSL -o "$PROJ/vendor/leaflet.css" https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
  curl -fsSL -o "$PROJ/vendor/marker-shadow.png" \
    https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png
else
  say "Leaflet already present"
fi

# ------------------------------------------------------------------- map data
say "Fetching map data (tile config, 30k+ locations, icon sprite)"
( cd "$PROJ/tools" && npm install --silent && node fetch_data.mjs )

# ----------------------------------------------------------------------- icons
if command -v magick >/dev/null || command -v convert >/dev/null; then
  say "Installing icons"
  CONV=$(command -v magick || command -v convert)
  for s in 16 22 24 32 48 64 128 256; do
    mkdir -p "$ICONS/${s}x${s}/apps"
    "$CONV" -background none "$SRC/assets/icon.svg" -resize ${s}x${s} \
      "$ICONS/${s}x${s}/apps/palworld-overlay.png" 2>/dev/null || true
  done
  gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true
else
  warn "ImageMagick not found - skipping icons (harmless)"
fi

# -------------------------------------------------------- launcher + hotkey
say "Installing launcher"
mkdir -p "$BIN" "$APPS"
install -m755 "$SRC/scripts/palworld-overlay" "$BIN/palworld-overlay"

cat > "$APPS/palworld-overlay.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Palworld Live Map (Overlay)
GenericName=Live Map Overlay
Comment=Live player position from your dedicated server, drawn over the game
Exec=$BIN/palworld-overlay
Icon=palworld-overlay
Terminal=false
Categories=Game;
Keywords=palworld;map;overlay;live;position;
StartupNotify=false
X-KDE-Shortcuts=Meta+P
DESKTOP
update-desktop-database "$APPS" 2>/dev/null || true

# KDE only picks up X-KDE-Shortcuts once kglobalaccel rescans; register directly.
KGS="$HOME/.config/kglobalshortcutsrc"
if [ -f "$KGS" ] && ! grep -q '^\[services\]\[palworld-overlay.desktop\]' "$KGS"; then
  cp "$KGS" "$KGS.bak.palworld.$(date +%s 2>/dev/null || echo bak)" 2>/dev/null || true
  cat >> "$KGS" <<'KGSEOF'

[services][palworld-overlay.desktop]
_k_friendly_name=Palworld Live Map (Overlay)
_launch=Meta+P,none,Palworld Live Map (Overlay)
KGSEOF
  systemctl --user restart plasma-kglobalaccel.service 2>/dev/null || true
  say "Registered Meta+P global shortcut (KDE)"
fi

# --------------------------------------------------------------------- systemd
say "Installing systemd user unit"
mkdir -p "$UNITS"
install -m644 "$SRC/systemd/palworld-live-map.service" "$UNITS/"
systemctl --user daemon-reload

cat <<DONE

$(say "Installed.")

Next steps:

  1. Edit your credentials:
         \$EDITOR $PROJ/config.json
     Set "rest_pass" to your server's AdminPassword and "me" to your in-game
     character name (exactly as it appears in /v1/api/players).

  2. Make sure the REST API is reachable at the "rest_url" in that file.
     If it is bound inside a container or on another host, set up the tunnel:
         cp $SRC/systemd/palworld-rest-tunnel.service.example \\
            $UNITS/palworld-rest-tunnel.service
         \$EDITOR $UNITS/palworld-rest-tunnel.service

  3. Start it:
         systemctl --user enable --now palworld-live-map

  4. Toggle the overlay with Meta+P, or run: palworld-overlay

DONE
