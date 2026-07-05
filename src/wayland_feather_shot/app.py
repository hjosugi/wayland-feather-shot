"""Application entry point and mode dispatch.

Modes:
  gui     frozen-screen region capture with in-place annotation (default)
  full    capture the whole screen straight into the editor window
  scroll  scrolling capture (record while you scroll, auto-stitch)
  daemon  bind Ctrl+Print etc. via the GlobalShortcuts portal
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import __version__
from .i18n import _, tr
from .editor.window import EditorWindow
from .portal import Portal, PortalError, cleanup_portal_file
from .select_overlay import OverlayWindow
from .settings import Settings

APP_ID = "io.github.wayland_feather_shot"


def _die_dialog(app, message: str):
    win = Gtk.ApplicationWindow(application=app, title="Feather Shot")
    alert = Gtk.AlertDialog()
    alert.set_message(_("Feather Shot could not capture the screen"))
    hint = _("portal-hint") if _("portal-hint") != "portal-hint" else (
        "Make sure xdg-desktop-portal and a backend for your desktop "
        "(gtk / gnome / kde / wlr / hyprland) are installed and running, "
        "then try again.")
    alert.set_detail(message + "\n\n" + hint)
    alert.set_buttons([_("Quit")])

    def done(dlg, result):
        try:
            dlg.choose_finish(result)
        except GLib.Error:
            pass
        win.destroy()

    alert.choose(win, None, done)


class FeatherShotApp(Gtk.Application):
    def __init__(self, mode: str, delay: float):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.mode = mode
        self.delay = delay
        self.settings = Settings()
        self.portal = None

    def do_activate(self):
        self.hold()  # stay alive while portal dialogs are up, windows closed
        try:
            self.portal = Portal()
        except PortalError as e:
            _die_dialog(self, str(e))
            self.release()
            return
        delay_ms = int(self.delay * 1000)
        if delay_ms > 0:
            GLib.timeout_add(delay_ms, self._dispatch)
        else:
            GLib.idle_add(self._dispatch)

    def _dispatch(self):
        if self.mode == "scroll":
            self._start_scroll()
        else:
            self._start_screenshot(region=(self.mode == "gui"))
        return False  # one-shot timeout

    # -- screenshot modes ---------------------------------------------------

    def _start_screenshot(self, region: bool):
        def on_shot(path, error):
            if path is None:
                if error == "cancelled":
                    self.release()
                    return
                # Some portals refuse non-interactive shots; ask again with
                # the portal's own dialog before giving up.
                self.portal.screenshot(on_interactive_shot, interactive=True)
                return
            self._open_capture(path, region)

        def on_interactive_shot(path, error):
            if path is None:
                if error == "cancelled":
                    self.release()
                else:
                    _die_dialog(self, tr("Screenshot portal failed: {error}", error=error))
                    self.release()
                return
            self._open_capture(path, region)

        self.portal.screenshot(on_shot, interactive=False)

    def _open_capture(self, path: str, region: bool):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            _die_dialog(self, tr("Could not read the captured image: {error}", error=e))
            self.release()
            return
        finally:
            cleanup_portal_file(path)

        if region:
            win = OverlayWindow(self, pixbuf, self.settings,
                                open_editor=self._open_editor)
        else:
            win = EditorWindow(self, pixbuf, self.settings)
        win.connect("destroy", lambda *_: self.release())
        win.present()

    def _open_editor(self, pixbuf, shapes=None):
        self.hold()
        win = EditorWindow(self, pixbuf, self.settings, shapes=shapes)
        win.connect("destroy", lambda *_: self.release())
        win.present()

    # -- scrolling capture ----------------------------------------------------

    def _start_scroll(self):
        from .scrollcap import recorder as rec
        if not rec.gstreamer_available():
            _die_dialog(self, _("Scrolling capture needs GStreamer (gst-plugins-base + pipewire plugin) with GObject introspection."))
            self.release()
            return

        def on_result(pixbuf, error):
            if pixbuf is None:
                if error and error != "cancelled":
                    _die_dialog(self, tr("Scrolling capture failed: {error}", error=error))
                self.release()
                return
            self._open_editor(pixbuf)
            self.release()

        win = rec.ScrollCaptureWindow(self, self.settings, on_result)
        win.present()
        win.begin(self.portal)

    # -- global shortcut daemon --------------------------------------------------

    def run_daemon(self) -> int:
        """Blocking daemon using the GlobalShortcuts portal (no GTK window)."""
        from .portal import GlobalShortcuts
        try:
            portal = Portal()
        except PortalError as e:
            print(f"feather-shot daemon: {e}", file=sys.stderr)
            return 1
        loop = GLib.MainLoop()
        mode_by_id = {"capture-region": "gui", "capture-full": "full",
                      "capture-scroll": "scroll"}

        def activated(shortcut_id):
            mode = mode_by_id.get(shortcut_id)
            if mode:
                spawn_capture(mode)

        shortcuts = GlobalShortcuts(portal, activated)

        def bound(ok, error):
            if ok:
                print("feather-shot daemon: shortcuts bound via the "
                      "GlobalShortcuts portal (default: Ctrl+Print).")
            else:
                print(f"feather-shot daemon: {error}\n"
                      "Your desktop probably does not implement the "
                      "GlobalShortcuts portal. Register a keyboard shortcut "
                      "for 'wayland-feather-shot gui' in your desktop "
                      "settings instead (see scripts/setup-hotkey.sh).",
                      file=sys.stderr)
                loop.quit()

        shortcuts.bind(bound)
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        return 0


def spawn_capture(mode: str):
    """Re-exec ourselves in a fresh process for one capture."""
    argv0 = os.path.realpath(sys.argv[0])
    if os.access(argv0, os.X_OK) and not argv0.endswith((".py",)):
        cmd = [argv0, mode]
    else:
        cmd = [sys.executable, "-m", "wayland_feather_shot", mode]
    subprocess.Popen(cmd, start_new_session=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="wayland-feather-shot",
        description="Flameshot-style screenshot tool built Wayland-first: "
                    "portal capture, in-place annotation (pen, arrow, blur, "
                    "…), scrolling capture. 100%% local — no upload, no "
                    "network code.")
    parser.add_argument("mode", nargs="?", default="gui",
                        choices=["gui", "full", "scroll", "daemon"],
                        help="gui: region capture (default) / full: whole "
                             "screen / scroll: scrolling capture / daemon: "
                             "GlobalShortcuts-portal hotkey daemon")
    parser.add_argument("-d", "--delay", type=float, default=0.0,
                        metavar="SEC", help="delay before capturing")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    Settings().write_default_config_if_missing()

    if args.mode == "daemon":
        return FeatherShotApp(args.mode, 0).run_daemon()

    app = FeatherShotApp(args.mode, args.delay)
    return app.run(None)
