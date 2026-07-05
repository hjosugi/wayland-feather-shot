#!/usr/bin/env bash
set -euo pipefail

APP_NAME="wayland-feather-shot"
APP_ID="io.github.hirosugi41.WaylandFeatherShot"
SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="$HOME/.local/bin"
APP_HOME="$DATA_HOME/$APP_NAME"
APPS_DIR="$DATA_HOME/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

mkdir -p "$APP_HOME" "$BIN_HOME" "$APPS_DIR" "$AUTOSTART_DIR"
rm -rf "$APP_HOME"
mkdir -p "$APP_HOME"
cp -a "$SRC_DIR/." "$APP_HOME/"
find "$APP_HOME" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$APP_HOME" -type f -name '*.pyc' -delete

cat > "$BIN_HOME/wayland-feather-shot" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$APP_HOME/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m wayland_feather_shot "\$@"
WRAP
chmod +x "$BIN_HOME/wayland-feather-shot"

cat > "$APPS_DIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Wayland Feather Shot
Comment=Local-only Wayland screenshot editor
Exec=$BIN_HOME/wayland-feather-shot capture --target area
Icon=accessories-screenshot
Terminal=false
Categories=Graphics;Utility;
StartupNotify=true
DESKTOP

cat > "$AUTOSTART_DIR/$APP_ID.Daemon.desktop" <<AUTOSTART
[Desktop Entry]
Type=Application
Name=Wayland Feather Shot Shortcut Daemon
Comment=Bind CTRL+Print for Wayland Feather Shot when the desktop portal supports it
Exec=$BIN_HOME/wayland-feather-shot daemon --shortcut CTRL+Print
Icon=accessories-screenshot
Terminal=false
X-GNOME-Autostart-enabled=true
AUTOSTART

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

cat <<MSG
Installed Wayland Feather Shot to:
  $APP_HOME

Launcher:
  $BIN_HOME/wayland-feather-shot

Default capture command:
  wayland-feather-shot capture --target area

Default shortcut target:
  CTRL+Print

A portal-based shortcut daemon autostart file was installed. If your compositor
rejects GlobalShortcuts, bind this command manually in desktop settings:
  $BIN_HOME/wayland-feather-shot capture --target area

Run diagnostics:
  wayland-feather-shot diagnose
MSG
