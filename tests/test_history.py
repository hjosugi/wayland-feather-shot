"""Tests for the recent-screenshots listing (no GTK needed).

Run:  python3 tests/test_history.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import history  # noqa: E402


class RecentScreenshotsTests(unittest.TestCase):
    def test_lists_newest_first_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            for i, name in enumerate(["a.png", "b.jpg", "c.txt", "d.webp"]):
                p = os.path.join(d, name)
                with open(p, "w") as f:
                    f.write("x")
                os.utime(p, (1000 + i, 1000 + i))  # increasing mtime
            got = history.recent_screenshots(d, limit=10)
            names = [os.path.basename(p) for p in got]
            self.assertEqual(names, ["d.webp", "b.jpg", "a.png"])  # .txt gone

    def test_limit(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                p = os.path.join(d, f"s{i}.png")
                open(p, "w").close()
                os.utime(p, (2000 + i, 2000 + i))
            got = history.recent_screenshots(d, limit=2)
            self.assertEqual([os.path.basename(p) for p in got],
                             ["s4.png", "s3.png"])

    def test_missing_dir_is_empty(self):
        self.assertEqual(history.recent_screenshots("/no/such/dir"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
