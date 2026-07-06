#!/usr/bin/env bash
# Installer for wayland-feather-shot.
#   ./install.sh              user install (~/.local)
#   sudo ./install.sh         system install (/usr/local)
#   ./install.sh --with-hotkey   also register Ctrl+PrtSc (GNOME: automatic)
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
WITH_HOTKEY=0
[ "${1:-}" = "--with-hotkey" ] && WITH_HOTKEY=1

if [ "$(id -u)" = 0 ]; then
    PREFIX="/usr/local"
    APPDIR="$PREFIX/share/wayland-feather-shot"
    BINDIR="$PREFIX/bin"
    DESKDIR="/usr/local/share/applications"
    ICONDIR="/usr/local/share/icons/hicolor/scalable/apps"
    AUTOSTART=""   # per-user; skip for system installs
else
    PREFIX="$HOME/.local"
    APPDIR="$PREFIX/share/wayland-feather-shot"
    BINDIR="$PREFIX/bin"
    DESKDIR="$PREFIX/share/applications"
    ICONDIR="$PREFIX/share/icons/hicolor/scalable/apps"
    AUTOSTART="$HOME/.config/autostart"
fi

echo "== wayland-feather-shot installer =="

# --- dependency check ---------------------------------------------------
PYTHON=/usr/bin/python3
if ! [ -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 || true)"
fi
missing=""
"$PYTHON" - <<'EOF' || missing=1
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa
import cairo  # noqa
EOF
if [ -n "$missing" ]; then
    echo ""
    echo "Missing dependencies: Python GObject bindings + GTK 4 + pycairo."
    echo "Install them first:"
    echo "  Arch/CachyOS : sudo pacman -S --needed python-gobject gtk4 python-cairo"
    echo "  Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0"
    echo "  Fedora       : sudo dnf install python3-gobject gtk4 python3-cairo"
    echo ""
    echo "Recommended extras:"
    echo "  wl-clipboard  (copy survives after the app closes)"
    echo "  GStreamer + pipewire plugin, python numpy  (scrolling capture)"
    echo "  Arch/CachyOS : sudo pacman -S --needed wl-clipboard gst-plugins-base gst-plugin-pipewire python-numpy"
    echo "  Debian/Ubuntu: sudo apt install wl-clipboard gstreamer1.0-pipewire gir1.2-gst-plugins-base-1.0 python3-numpy"
    echo "  Fedora       : sudo dnf install wl-clipboard pipewire-gstreamer python3-numpy"
    exit 1
fi
echo "Dependencies: OK"

# --- copy files ------------------------------------------------------------
mkdir -p "$APPDIR" "$BINDIR" "$DESKDIR" "$ICONDIR"
rm -rf "$APPDIR/src" "$APPDIR/bin"
cp -r "$HERE/src" "$HERE/bin" "$APPDIR/"
chmod +x "$APPDIR/bin/wayland-feather-shot"
ln -sf "$APPDIR/bin/wayland-feather-shot" "$BINDIR/wayland-feather-shot"

APP_ID="io.github.hjosugi.WaylandFeatherShot"
cp "$HERE/data/$APP_ID.desktop" "$DESKDIR/"
cp "$HERE/data/icons/$APP_ID.svg" "$ICONDIR/"
METAINFODIR="$(dirname "$DESKDIR")/metainfo"
mkdir -p "$METAINFODIR"
cp "$HERE/data/$APP_ID.metainfo.xml" "$METAINFODIR/"
# Clean up files installed under the pre-0.2.0 names.
rm -f "$DESKDIR/wayland-feather-shot.desktop" \
      "$ICONDIR/wayland-feather-shot.svg"
if [ -n "$AUTOSTART" ]; then
    mkdir -p "$AUTOSTART"
    cp "$HERE/data/$APP_ID.Daemon.desktop" "$AUTOSTART/"
    rm -f "$AUTOSTART/wayland-feather-shot-daemon.desktop"
fi
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$DESKDIR" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q "${ICONDIR%/scalable/apps}" 2>/dev/null || true

echo "Installed to: $APPDIR"
echo "Command:      $BINDIR/wayland-feather-shot"
case ":$PATH:" in
    *":$BINDIR:"*) ;;
    *) echo "NOTE: $BINDIR is not in your PATH." ;;
esac

# --- hotkey -------------------------------------------------------------------
if [ "$WITH_HOTKEY" = 1 ]; then
    bash "$HERE/scripts/setup-hotkey.sh"
else
    echo ""
    echo "Default hotkey (Ctrl+PrtSc): run  ./scripts/setup-hotkey.sh"
    echo "(On KDE/GNOME 46+ the autostarted portal daemon also offers it.)"
fi

echo ""
echo "Try it:  wayland-feather-shot gui"
