"""Runtime diagnostics (`wayland-feather-shot diagnose`).

Import-light on purpose: this must work when GTK/PyGObject is missing or
broken, so users can find out *why* the app does not start.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _gtk4() -> tuple[bool, str]:
    if not _module_exists("gi"):
        return False, "PyGObject (python3-gi) is not installed"
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        return True, f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}"
    except Exception as exc:
        return False, str(exc)


def _gst_pipewire() -> tuple[bool, str]:
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        if Gst.ElementFactory.find("pipewiresrc") is not None:
            return True, "pipewiresrc element available"
        return False, "GStreamer works but the pipewire plugin is missing"
    except Exception as exc:
        return False, str(exc)


def _portal_interfaces() -> list[Check]:
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return [Check("portal introspection", False,
                      "gdbus not found (install libglib2.0-bin / glib2)",
                      required=False)]
    try:
        proc = subprocess.run(
            [gdbus, "introspect", "--session",
             "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop"],
            text=True, capture_output=True, timeout=5)
        stdout, stderr = proc.stdout, proc.stderr.strip()
    except Exception as exc:
        stdout, stderr = "", str(exc)
    checks = []
    for iface, required in [
            ("org.freedesktop.portal.Screenshot", True),
            ("org.freedesktop.portal.ScreenCast", False),
            ("org.freedesktop.portal.GlobalShortcuts", False),
            ("org.freedesktop.portal.RemoteDesktop", False)]:
        found = iface in stdout
        detail = "available" if found else \
            (stderr or "not found in portal introspection")
        checks.append(Check(iface, found, detail, required=required))
    return checks


def run_checks() -> list[Check]:
    session = os.environ.get("XDG_SESSION_TYPE", "<unset>")
    checks = [
        Check("Wayland session", session == "wayland",
              f"XDG_SESSION_TYPE={session}", required=False),
        Check("GTK 4 via PyGObject", *_gtk4()),
        Check("pycairo", _module_exists("cairo"), "cairo module import"),
        Check("wl-clipboard", shutil.which("wl-copy") is not None,
              "copy survives after the app closes", required=False),
        Check("GStreamer + PipeWire", *_gst_pipewire(), required=False),
        Check("numpy", _module_exists("numpy"),
              "optional, makes scroll stitching fast", required=False),
    ]
    checks.extend(_portal_interfaces())
    return checks


def print_diagnostics() -> int:
    checks = run_checks()
    failed_required = False
    ok_by_name = {}
    for check in checks:
        ok_by_name[check.name] = check.ok
        if check.ok:
            mark = "OK  "
        elif check.required:
            mark = "MISS"
            failed_required = True
        else:
            mark = "warn"
        print(f"[{mark}] {check.name}: {check.detail}")

    # Optional auto-scroll (scroll --auto) needs both the RemoteDesktop portal
    # and the GStreamer/PipeWire recorder — spell it out so users know whether
    # the flag will do anything before they try it (#3).
    from .scrollcap.autoscroll import auto_scroll_availability
    usable, reason = auto_scroll_availability(
        ok_by_name.get("org.freedesktop.portal.RemoteDesktop", False),
        ok_by_name.get("GStreamer + PipeWire", False))
    print(f"[{'OK  ' if usable else 'warn'}] scroll --auto: {reason}")

    # Hotkey setup guidance for this desktop (the "nothing happens when I press
    # the key" case is almost always the wrong binding mechanism).
    from . import hotkey
    desktop = hotkey.detect_desktop()
    support = hotkey.portal_support(desktop)
    print(f"\n[info] desktop: {desktop} "
          f"(GlobalShortcuts portal daemon: {support})")
    print("Hotkey setup (Ctrl+PrtSc → region capture):")
    for line in hotkey.setup_hint(desktop).splitlines():
        print("  " + line)

    if failed_required:
        print("\nRequired components are missing — see README.md "
              "'Install' for your distro's package names.")
    return 1 if failed_required else 0
