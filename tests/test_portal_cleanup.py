"""cleanup_portal_file removes the portal's capture file, and nothing else.

Run:  python3 tests/test_portal_cleanup.py
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from wayland_feather_shot.portal import cleanup_portal_file
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class CleanupPortalFileTests(unittest.TestCase):
    def setUp(self):
        # Not under /tmp: this stands in for a real user directory.
        self.home = tempfile.mkdtemp(prefix="wfs-home-",
                                     dir=os.path.dirname(os.path.abspath(__file__)))
        self.addCleanup(lambda: os.path.exists(self.home) and __import__("shutil").rmtree(self.home))

    def touch(self, directory, name, age=0.0):
        path = os.path.join(directory, name)
        with open(path, "wb") as fh:
            fh.write(b"png")
        if age:
            old = time.time() - age
            os.utime(path, (old, old))
        return path

    def test_a_file_in_a_temp_directory_is_always_removed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            path = self.touch(tmp, "shot.png", age=3600)
            cleanup_portal_file(path)
            self.assertFalse(os.path.exists(path))

    def test_a_file_elsewhere_is_kept_when_the_request_time_is_unknown(self):
        path = self.touch(self.home, "Screenshot.png")
        cleanup_portal_file(path)
        self.assertTrue(os.path.exists(path))

    def test_a_file_elsewhere_written_for_this_request_is_removed(self):
        since = time.time()
        path = self.touch(self.home, "Screenshot.png")
        cleanup_portal_file(path, since=since)
        self.assertFalse(os.path.exists(path))

    def test_an_older_file_elsewhere_is_never_touched(self):
        path = self.touch(self.home, "holiday.png", age=120)
        cleanup_portal_file(path, since=time.time())
        self.assertTrue(os.path.exists(path))

    def test_a_missing_file_is_not_an_error(self):
        cleanup_portal_file(os.path.join(self.home, "gone.png"), since=time.time())


if __name__ == "__main__":
    unittest.main()
