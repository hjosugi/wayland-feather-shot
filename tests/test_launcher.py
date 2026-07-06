"""Tests for the source/install launcher."""

import os
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..")


class LauncherTests(unittest.TestCase):
    def test_launcher_uses_distro_python(self):
        path = os.path.join(ROOT, "bin", "wayland-feather-shot")
        with open(path, encoding="utf-8") as f:
            shebang = f.readline().strip()
        self.assertEqual(shebang, "#!/usr/bin/python3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
