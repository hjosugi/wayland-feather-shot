#!/usr/bin/env bash
# Install this git checkout's desktop entries for the current user, so the
# launcher shows up in the app grid and, more importantly, the GlobalShortcuts
# portal accepts our app id: it only registers an app id that has a matching
# <app id>.desktop in an applications directory it can see.  A package install
# (AUR, deb/rpm, AppImage integration) provides that file; a source tree needs
# this script before `wayland-feather-shot daemon` can bind Ctrl+PrtSc.
#
#   scripts/install-desktop-entry.sh              app entry only
#   scripts/install-desktop-entry.sh --autostart  also start the hotkey daemon at login
#   scripts/install-desktop-entry.sh --remove     remove both
#
# Exec= is rewritten to this checkout's bin/wayland-feather-shot, so the entries
# follow the source tree; rerun after moving the checkout.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
launcher="$here/bin/wayland-feather-shot"
appid="io.github.hjosugi.WaylandFeatherShot"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
with_autostart=0

case "${1:-}" in
    "") ;;
    --autostart) with_autostart=1 ;;
    --remove)
        rm -f "$apps/$appid.desktop" "$autostart/$appid.Daemon.desktop"
        echo "removed $apps/$appid.desktop and $autostart/$appid.Daemon.desktop"
        exit 0 ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

[ -x "$launcher" ] || { echo "launcher not executable: $launcher" >&2; exit 1; }

mkdir -p "$apps"
sed -e "s|^Exec=wayland-feather-shot|Exec=$launcher|" \
    -e "s|^Icon=.*|&\nTryExec=$launcher|" \
    "$here/data/$appid.desktop" > "$apps/$appid.desktop"
echo "installed $apps/$appid.desktop"

if [ "$with_autostart" = 1 ]; then
    mkdir -p "$autostart"
    sed -e "s|^Exec=wayland-feather-shot|Exec=$launcher|" \
        "$here/data/$appid.Daemon.desktop" > "$autostart/$appid.Daemon.desktop"
    echo "installed $autostart/$appid.Daemon.desktop (daemon starts at next login)"
fi

command -v update-desktop-database >/dev/null && update-desktop-database "$apps" 2>/dev/null || true
echo "test the binding now:  $launcher daemon --bind-once"
