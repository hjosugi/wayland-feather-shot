"""Global-shortcut helpers: desktop detection, per-desktop setup hints, and
the command used to launch a capture.

Import-light on purpose (no gi): the daemon, `diagnose` and the unit tests all
use it, and it must work even where GTK is missing.

Why this exists: on Wayland there is no portable way for a client to grab a
global key — it is the compositor's decision. Two mechanisms cover the field:

* the ``org.freedesktop.portal.GlobalShortcuts`` portal (KDE Plasma, GNOME
  46+), driven by ``wayland-feather-shot daemon``; and
* a native desktop keybinding (GNOME gsettings, Hyprland/Sway config, KDE
  custom shortcut), set up by ``scripts/setup-hotkey.sh``.

The failure people actually hit is "I pressed the key and nothing launched".
Usually that is either the wrong mechanism for the desktop, or a capture
command that cannot be found/imported when spawned — :func:`capture_command`
makes the launch robust across install layouts.
"""

from __future__ import annotations

import os

DEFAULT_SHORTCUT = "CTRL+Print"

# id -> (default trigger, human description) for the daemon's portal session.
DAEMON_SHORTCUTS = [
    ("capture-region", "CTRL+Print", "Capture a screen region (Feather Shot)"),
    ("capture-full", "SHIFT+CTRL+F12", "Capture the full screen (Feather Shot)"),
    ("capture-scroll", "CTRL+SHIFT+Print", "Scrolling capture (Feather Shot)"),
]


def detect_desktop(env=None) -> str:
    """Return a normalized desktop id: gnome/kde/hyprland/sway/wlroots/other.

    Uses the most reliable signals first (compositor-specific env vars set by
    the running session), then falls back to XDG_CURRENT_DESKTOP.
    """
    env = os.environ if env is None else env
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if env.get("SWAYSOCK"):
        return "sway"
    fields = ":".join(
        (env.get("XDG_CURRENT_DESKTOP", ""),
         env.get("XDG_SESSION_DESKTOP", ""),
         env.get("DESKTOP_SESSION", ""))).lower()
    if "gnome" in fields:
        return "gnome"
    if "kde" in fields or "plasma" in fields:
        return "kde"
    if "hyprland" in fields:
        return "hyprland"
    if "sway" in fields or "wlroots" in fields:
        return "sway"
    return "other"


# Whether the GlobalShortcuts portal daemon is expected to work, per desktop.
# "yes" it implements it, "no" it does not, "maybe" version-dependent.
PORTAL_SUPPORT = {
    "gnome": "maybe",     # GNOME 46+ only
    "kde": "yes",
    "hyprland": "maybe",  # needs XDPH with GlobalShortcuts support
    "sway": "no",
    "wlroots": "no",
    "other": "maybe",
}


def portal_support(desktop: str) -> str:
    return PORTAL_SUPPORT.get(desktop, "maybe")


def setup_hint(desktop: str, cmd: str = "wayland-feather-shot") -> str:
    """Exact, copy-pasteable instructions to bind Ctrl+PrtSc on *desktop*."""
    if desktop == "gnome":
        return (
            "GNOME: run the helper to bind it via gsettings —\n"
            "    ./scripts/setup-hotkey.sh\n"
            "  (Ctrl+PrtSc → region, Ctrl+Shift+PrtSc → scroll). GNOME 46+ can\n"
            f"  also use the portal daemon:  {cmd} daemon")
    if desktop == "kde":
        return (
            "KDE Plasma: the portal daemon works —\n"
            f"    {cmd} daemon\n"
            "  (the installed autostart entry runs it at login; approve the\n"
            "  shortcut dialog once). Or System Settings → Shortcuts → Custom:\n"
            f"    command:  {cmd} gui      key: Ctrl+PrtSc")
    if desktop == "hyprland":
        return (
            "Hyprland: add to ~/.config/hypr/hyprland.conf —\n"
            f"    bind = CTRL, Print, exec, {cmd} gui\n"
            f"    bind = CTRL SHIFT, Print, exec, {cmd} scroll")
    if desktop == "sway":
        return (
            "Sway: add to ~/.config/sway/config —\n"
            f"    bindsym Ctrl+Print exec {cmd} gui\n"
            f"    bindsym Ctrl+Shift+Print exec {cmd} scroll")
    return (
        "Register these in your desktop's keyboard-shortcut settings:\n"
        f"    Ctrl+PrtSc        ->  {cmd} gui\n"
        f"    Ctrl+Shift+PrtSc  ->  {cmd} scroll\n"
        "  If your desktop implements the GlobalShortcuts portal you can\n"
        f"  instead run:  {cmd} daemon")


def valid_trigger(trigger: str) -> bool:
    """Loosely validate an XDG shortcut trigger like ``CTRL+Print`` or
    ``SHIFT+CTRL+F12`` (one or more ``+``-joined, non-empty tokens)."""
    if not trigger or trigger.startswith("+") or trigger.endswith("+"):
        return False
    parts = trigger.split("+")
    return all(p.strip() for p in parts)


def capture_command(mode: str, *, argv0: str, executable: str, src_dir: str,
                    is_executable=None):
    """Build the argv (and any extra env) to launch one capture in *mode*.

    Returns ``(argv, extra_env)``.  Prefers re-executing the launcher script
    directly when it is an executable (installed console script or
    ``bin/wayland-feather-shot``); otherwise falls back to ``python -m`` with
    PYTHONPATH pointed at the package source so the import always resolves.
    """
    if is_executable is None:
        is_executable = lambda p: os.access(p, os.X_OK)  # noqa: E731
    real = os.path.realpath(argv0)
    if real and is_executable(real) and not real.endswith(".py"):
        return [real, mode], {}
    return [executable, "-m", "wayland_feather_shot", mode], {"PYTHONPATH": src_dir}
