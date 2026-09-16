#!/usr/bin/env bash
set -euo pipefail

APP="devnet-wayvr-watch-manager"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.local/share/${APP}"
BIN="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Installing Devnet WayVR Watch Manager v0.1.14"

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required."; exit 1; }

if ! python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
PY
then
    echo "ERROR: GTK4 Python bindings are missing."
    echo "Install them with:"
    echo "  sudo pacman -S --needed python-gobject gtk4"
    exit 1
fi

if ! command -v wayvrctl >/dev/null 2>&1; then
    echo "WARNING: wayvrctl was not found. The GUI will install, but live VR updates need wayvrctl."
fi

if ! command -v adb >/dev/null 2>&1; then
    echo "WARNING: adb was not found. Quest controller batteries need android-tools (adb)."
    echo "         CachyOS/Arch: sudo pacman -S --needed android-tools"
fi

mkdir -p "$DEST" "$BIN" "$DESKTOP_DIR" "$SYSTEMD_DIR"

# Atomic-ish app update: stage then replace only our application files.
STAGE="${DEST}.new.$$"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$HERE/app/." "$STAGE/"
rm -rf "$DEST"
mv "$STAGE" "$DEST"

install -m755 "$HERE/bin/devnet-wayvr-watch-manager" "$BIN/devnet-wayvr-watch-manager"
install -m755 "$HERE/bin/devnet-wayvr-watch-metrics" "$BIN/devnet-wayvr-watch-metrics"
install -m755 "$HERE/bin/devnet-wayvr-watch-toggle" "$BIN/devnet-wayvr-watch-toggle"
install -m755 "$HERE/bin/devnet-wayvr-watch-doctor" "$BIN/devnet-wayvr-watch-doctor"
install -m644 "$HERE/desktop/devnet-wayvr-watch-manager.desktop" "$DESKTOP_DIR/devnet-wayvr-watch-manager.desktop"
install -m644 "$HERE/systemd/devnet-wayvr-watch-metrics.service" "$SYSTEMD_DIR/devnet-wayvr-watch-metrics.service"

systemctl --user daemon-reload >/dev/null 2>&1 || true
python3 "$DEST/watchlib.py" init-config >/dev/null

echo
echo "Installed."
echo "Nothing has been changed in your WayVR watch yet."
echo "Open 'Devnet WayVR Watch Manager' and press 'Save & Apply to VR' when ready."
