#!/usr/bin/env bash
# Register the default hotkeys for wayland-feather-shot:
#   Ctrl+Print        -> region capture (gui)
#   Ctrl+Shift+Print  -> scrolling capture
#
# GNOME is configured automatically (gsettings). Other desktops get either
# the GlobalShortcuts-portal daemon or a config snippet printed for you.
set -u

CMD="wayland-feather-shot"
command -v "$CMD" >/dev/null 2>&1 || CMD="$(cd "$(dirname "$0")/.." && pwd)/bin/wayland-feather-shot"

desktop="${XDG_CURRENT_DESKTOP:-unknown}"
echo "Detected desktop: $desktop"

setup_gnome() {
    local base="org.gnome.settings-daemon.plugins.media-keys"
    local dir="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    local list slot0 slot1
    list=$(gsettings get $base custom-keybindings 2>/dev/null) || return 1

    add_binding() {  # $1 name  $2 command  $3 binding
        local i=0 slot
        while :; do
            slot="$dir/custom$i/"
            case "$list" in *"$slot"*) i=$((i+1)); continue;; esac
            break
        done
        if [ "$list" = "@as []" ] || [ "$list" = "[]" ]; then
            list="['$slot']"
        else
            list="${list%]*}, '$slot']"
        fi
        gsettings set $base custom-keybindings "$list"
        local schema="$base.custom-keybinding:$slot"
        gsettings set "$schema" name "$1"
        gsettings set "$schema" command "$2"
        gsettings set "$schema" binding "$3"
        echo "  bound: $3 -> $2"
    }

    add_binding "Feather Shot (region)" "$CMD gui" "<Control>Print"
    add_binding "Feather Shot (scroll)" "$CMD scroll" "<Control><Shift>Print"
}

case "$desktop" in
    *GNOME*)
        if setup_gnome; then
            echo "GNOME shortcuts installed: Ctrl+Print / Ctrl+Shift+Print"
        else
            echo "Could not configure gsettings automatically." >&2
        fi
        ;;
    *KDE*)
        echo "KDE Plasma implements the GlobalShortcuts portal — start the daemon:"
        echo "    $CMD daemon"
        echo "(installed autostart entry does this at login), then approve the"
        echo "shortcut dialog. Default trigger requested: Ctrl+Print."
        echo "Or add it manually: System Settings → Shortcuts → Custom:"
        echo "    command:  $CMD gui      key: Ctrl+Print"
        ;;
    *Hyprland*)
        echo "Add to ~/.config/hypr/hyprland.conf:"
        echo "    bind = CTRL, Print, exec, $CMD gui"
        echo "    bind = CTRL SHIFT, Print, exec, $CMD scroll"
        ;;
    *sway*|*Sway*)
        echo "Add to ~/.config/sway/config:"
        echo "    bindsym Ctrl+Print exec $CMD gui"
        echo "    bindsym Ctrl+Shift+Print exec $CMD scroll"
        ;;
    *)
        echo "Register these in your desktop's keyboard-shortcut settings:"
        echo "    Ctrl+Print        ->  $CMD gui"
        echo "    Ctrl+Shift+Print  ->  $CMD scroll"
        echo "If your desktop implements the GlobalShortcuts portal you can"
        echo "instead run:  $CMD daemon"
        ;;
esac
