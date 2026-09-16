#!/usr/bin/env bash
set -euo pipefail

APP="devnet-wayvr-watch-manager"
DEST="${HOME}/.local/share/${APP}"

echo "Uninstalling Devnet WayVR Watch Manager"

if [[ -f "$DEST/watchlib.py" ]]; then
    python3 "$DEST/watchlib.py" restore-watch >/dev/null 2>&1 || true
fi

systemctl --user disable --now devnet-wayvr-watch-metrics.service >/dev/null 2>&1 || true
rm -f \
    "$HOME/.local/bin/devnet-wayvr-watch-manager" \
    "$HOME/.local/bin/devnet-wayvr-watch-metrics" \
    "$HOME/.local/bin/devnet-wayvr-watch-toggle" \
    "$HOME/.local/bin/devnet-wayvr-watch-doctor" \
    "$HOME/.local/share/applications/devnet-wayvr-watch-manager.desktop" \
    "$HOME/.config/systemd/user/devnet-wayvr-watch-metrics.service"

systemctl --user daemon-reload >/dev/null 2>&1 || true
rm -rf "$DEST"

echo "Removed application files."
echo "Your settings/backups were left in ~/.config/devnet-wayvr-watch-manager/"
echo "The Devnet watch override was removed/restored. Restart the VR stack if it was running."
