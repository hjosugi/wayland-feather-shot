#!/usr/bin/env bash
set -euo pipefail
APP_NAME="wayland-feather-shot"
APP_ID="io.github.hirosugi41.WaylandFeatherShot"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="$HOME/.local/bin"
rm -rf "$DATA_HOME/$APP_NAME"
rm -f "$BIN_HOME/wayland-feather-shot"
rm -f "$DATA_HOME/applications/$APP_ID.desktop"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_ID.Daemon.desktop"
echo "Uninstalled Wayland Feather Shot."
