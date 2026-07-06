#!/usr/bin/env bash
# Remove wayland-feather-shot installed by install.sh.
set -eu

if [ "$(id -u)" = 0 ]; then
    PREFIX="/usr/local"
    AUTOSTART=""
else
    PREFIX="$HOME/.local"
    AUTOSTART="$HOME/.config/autostart"
fi

APP_ID="io.github.hjosugi.WaylandFeatherShot"
rm -rf "$PREFIX/share/wayland-feather-shot"
rm -f  "$PREFIX/bin/wayland-feather-shot"
rm -f  "$PREFIX/share/applications/$APP_ID.desktop" \
       "$PREFIX/share/applications/wayland-feather-shot.desktop"
rm -f  "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
       "$PREFIX/share/icons/hicolor/scalable/apps/wayland-feather-shot.svg"
rm -f  "$PREFIX/share/metainfo/$APP_ID.metainfo.xml"
[ -n "$AUTOSTART" ] && rm -f "$AUTOSTART/$APP_ID.Daemon.desktop" \
                             "$AUTOSTART/wayland-feather-shot-daemon.desktop"

echo "Removed. Config (~/.config/wayland-feather-shot) was kept;"
echo "delete it manually if you want a clean slate."
