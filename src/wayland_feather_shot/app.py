"""GTK application and mode dispatch.

Modes (parsed in cli.py, which imports this module lazily):
  gui     frozen-screen region capture with in-place annotation (default)
  full    capture the whole screen straight into the editor window
  scroll  scrolling capture (record while you scroll, auto-stitch)
  edit    open an existing image file in the editor
  daemon  bind Ctrl+Print etc. via the GlobalShortcuts portal
"""

from __future__ import annotations

import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID
from .i18n import _, tr
from .editor.window import EditorWindow
from .portal import Portal, PortalError, cleanup_portal_file
from .select_overlay import OverlayWindow
from .settings import Settings


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
    def __init__(self, mode: str, delay: float, file: str | None = None,
                 region=None, output: str | None = None,
                 no_editor: bool = False):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.mode = mode
        self.delay = delay
        self.file = file
        self.region = region          # (x, y, w, h) crop, or None
        self.output = output          # explicit save path, or None
        self.no_editor = no_editor    # capture -> save -> print -> exit
        self.settings = Settings()
        self.portal = None
        self.exit_code = 0

    def do_activate(self):
        self.hold()  # stay alive while portal dialogs are up, windows closed
        if self.mode == "edit":
            self._open_existing(self.file)
            return
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
            # Overlay region-select only in interactive gui mode; a scripted
            # capture (--region / --output / --no-editor) is non-interactive.
            overlay = (self.mode == "gui" and not self._scripted())
            self._start_screenshot(overlay=overlay)
        return False  # one-shot timeout

    def _scripted(self) -> bool:
        return bool(self.no_editor or self.output or self.region)

    # -- screenshot modes ---------------------------------------------------

    def _start_screenshot(self, overlay: bool):
        def on_shot(path, error):
            if path is None:
                if error == "cancelled":
                    self._cancel()
                    return
                # Some portals refuse non-interactive shots; ask again with
                # the portal's own dialog before giving up.
                self.portal.screenshot(on_interactive_shot, interactive=True)
                return
            self._open_capture(path, overlay)

        def on_interactive_shot(path, error):
            if path is None:
                if error == "cancelled":
                    self._cancel()
                else:
                    self._fail(tr("Screenshot portal failed: {error}", error=error))
                return
            self._open_capture(path, overlay)

        self.portal.screenshot(on_shot, interactive=False)

    def _crop(self, pixbuf):
        """Crop *pixbuf* to self.region, clamped to the image bounds."""
        if not self.region:
            return pixbuf
        bw, bh = pixbuf.get_width(), pixbuf.get_height()
        x, y, w, h = self.region
        x = max(0, min(x, bw - 1))
        y = max(0, min(y, bh - 1))
        w = max(1, min(w, bw - x))
        h = max(1, min(h, bh - y))
        return pixbuf.new_subpixbuf(x, y, w, h).copy()

    def _open_capture(self, path: str, overlay: bool):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            self._fail(tr("Could not read the captured image: {error}", error=e))
            return
        finally:
            cleanup_portal_file(path)

        pixbuf = self._crop(pixbuf)

        if self._scripted() and self.no_editor:
            self._save_and_exit(pixbuf)
            return

        if overlay:
            win = OverlayWindow(self, pixbuf, self.settings,
                                open_editor=self._open_editor)
        else:
            win = EditorWindow(self, pixbuf, self.settings,
                               save_path=self.output)
        win.connect("destroy", lambda *_: self.release())
        win.present()

    def _save_and_exit(self, pixbuf):
        """Headless --no-editor path: save, print the path, quit."""
        from . import save as save_mod
        path = self.output or save_mod.timestamp_path(self.settings)
        try:
            path = save_mod.save_pixbuf(pixbuf, path)
        except Exception as e:  # GLib.Error or OSError
            self._fail(tr("Save failed: {error}", error=e))
            return
        print(path)
        self.release()

    def _fail(self, message: str):
        """Report an error: dialog when interactive, stderr when scripted."""
        self.exit_code = 1
        if self._scripted():
            print(f"wayland-feather-shot: {message}", file=sys.stderr)
            self.release()
        else:
            _die_dialog(self, message)
            self.release()

    def _cancel(self):
        if self._scripted():
            self.exit_code = 130
        self.release()

    def _open_existing(self, path: str):
        """`edit FILE` mode: no portal involved, straight into the editor."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error as e:
            _die_dialog(self, tr("Could not read the captured image: {error}", error=e))
            self.release()
            return
        win = EditorWindow(self, pixbuf, self.settings)
        win.connect("destroy", lambda *_: self.release())
        win.present()

    def _open_editor(self, pixbuf, shapes=None, startup_toast=None):
        self.hold()
        win = EditorWindow(self, pixbuf, self.settings, shapes=shapes,
                           startup_toast=startup_toast)
        win.connect("destroy", lambda *_: self.release())
        win.present()

    # -- scrolling capture ----------------------------------------------------

    def _start_scroll(self):
        from .scrollcap import recorder as rec
        if not rec.gstreamer_available():
            _die_dialog(self, _("Scrolling capture needs GStreamer (gst-plugins-base + pipewire plugin) with GObject introspection."))
            self.release()
            return

        def on_result(pixbuf, error, warning=None):
            if pixbuf is None:
                if error and error != "cancelled":
                    _die_dialog(self, tr("Scrolling capture failed: {error}", error=error))
                self.release()
                return
            self._open_editor(pixbuf, startup_toast=warning)
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


def run(args) -> int:
    """Run the app for parsed CLI *args* (see cli.build_parser)."""
    Settings().write_default_config_if_missing()

    if args.mode == "daemon":
        return FeatherShotApp(args.mode, 0).run_daemon()

    app = FeatherShotApp(
        args.mode, args.delay,
        file=getattr(args, "file", None),
        region=getattr(args, "region", None),
        output=getattr(args, "output", None),
        no_editor=getattr(args, "no_editor", False))
    status = app.run(None)
    # Prefer our scripting exit code; fall back to GTK's run status.
    return app.exit_code or status
