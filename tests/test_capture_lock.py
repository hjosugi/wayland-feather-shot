"""Only one capture at a time: the second one finds the lock taken.

Run:  python3 tests/test_capture_lock.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402,F401
    from wayland_feather_shot.lifecycle import acquire_capture_lock
    HAVE_GI = True
    HAVE_GTK_DISPLAY = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    HAVE_GI = HAVE_GTK_DISPLAY = False
if HAVE_GTK_DISPLAY:
    from wayland_feather_shot.app import FeatherShotApp  # noqa: E402


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class CaptureLockTests(unittest.TestCase):
    def test_second_acquire_fails_until_the_first_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            first = acquire_capture_lock(directory)
            self.assertIsNotNone(first)
            self.assertIsNone(acquire_capture_lock(directory))
            first.close()
            third = acquire_capture_lock(directory)
            self.assertIsNotNone(third)
            third.close()

    def test_the_lock_file_lives_in_the_given_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            handle = acquire_capture_lock(os.path.join(directory, "new"))
            self.assertIsNotNone(handle)
            self.assertTrue(os.path.exists(
                os.path.join(directory, "new", "wayland-feather-shot.capture.lock")))
            handle.close()

    def test_an_unusable_directory_does_not_block_capturing(self):
        # A lock file that cannot be created must not read as "a capture is
        # already open", or no capture could ever start.
        with tempfile.NamedTemporaryFile() as not_a_directory:
            handle = acquire_capture_lock(not_a_directory.name)
            self.assertIsNotNone(handle)
            handle.close()

    def test_a_filesystem_without_locks_does_not_block_capturing(self):
        import errno
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch("fcntl.flock",
                           side_effect=OSError(errno.ENOLCK, "No locks")):
            handle = acquire_capture_lock(directory)
            self.assertIsNotNone(handle)
            handle.close()


@unittest.skipUnless(HAVE_GTK_DISPLAY, "GTK display unavailable")
class CaptureLockScopeTests(unittest.TestCase):
    """A capture holds the lock until its overlay closes, whatever the
    mode; a picture opened from a file is not a capture and holds none."""

    def picture(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 64, 48)
        pixbuf.fill(0xffffffff)
        pixbuf.savev(path, "png", [], [])
        return path

    def app(self, mode):
        directory = tempfile.mkdtemp()
        app = FeatherShotApp(mode=mode, delay=0)
        app.set_application_id("io.github.hjosugi.WaylandFeatherShot."
                               + mode.capitalize() + "LockTest")
        app.register(None)
        return app, directory

    def window_of(self, app):
        window = app.get_active_window() or app.get_windows()[0]
        self.addCleanup(window.destroy)
        return window

    def test_a_capture_holds_the_lock_until_its_overlay_closes(self):
        for mode in ("gui", "window"):
            with self.subTest(mode=mode):
                app, directory = self.app(mode)
                app._capture_lock = acquire_capture_lock(directory)
                app._open_capture(self.picture())
                window = self.window_of(app)
                self.assertIsNone(acquire_capture_lock(directory))
                window.destroy()
                self.assertIsNone(app._capture_lock)
                again = acquire_capture_lock(directory)
                self.assertIsNotNone(again)
                again.close()

    def test_a_picture_from_a_file_holds_no_lock(self):
        app, directory = self.app("edit")
        app._open_existing(self.picture())
        self.window_of(app)
        again = acquire_capture_lock(directory)
        self.assertIsNotNone(again)
        again.close()


if __name__ == "__main__":
    unittest.main()
