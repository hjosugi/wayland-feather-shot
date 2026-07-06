"""Tests for CLI parsing and the pure region parser (no GTK needed).

Run:  python3 tests/test_cli.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import cli  # noqa: E402


class ParseRegionTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(cli.parse_region("10,20,300,200"), (10, 20, 300, 200))

    def test_whitespace_tolerated(self):
        self.assertEqual(cli.parse_region(" 0, 0 , 640 ,480"), (0, 0, 640, 480))

    def test_wrong_count(self):
        with self.assertRaises(ValueError):
            cli.parse_region("1,2,3")
        with self.assertRaises(ValueError):
            cli.parse_region("1,2,3,4,5")

    def test_non_integer(self):
        with self.assertRaises(ValueError):
            cli.parse_region("1,2,3,x")

    def test_non_positive_size(self):
        with self.assertRaises(ValueError):
            cli.parse_region("0,0,0,100")
        with self.assertRaises(ValueError):
            cli.parse_region("0,0,100,-5")

    def test_negative_origin(self):
        with self.assertRaises(ValueError):
            cli.parse_region("-1,0,100,100")


class ArgParsingTests(unittest.TestCase):
    def parse(self, argv):
        parser = cli.build_parser()
        args = parser.parse_args(argv)
        cli._validate(parser, args)
        return args

    def test_defaults(self):
        args = self.parse([])
        self.assertEqual(args.mode, "gui")
        self.assertIsNone(args.region)
        self.assertIsNone(args.output)
        self.assertFalse(args.no_editor)

    def test_region_parsed_into_tuple(self):
        args = self.parse(["full", "--region", "5,5,100,100"])
        self.assertEqual(args.region, (5, 5, 100, 100))

    def test_output_absolute(self):
        args = self.parse(["full", "--output", "shot.png"])
        self.assertTrue(os.path.isabs(args.output))
        self.assertTrue(args.output.endswith("shot.png"))

    def test_scripting_rejected_outside_capture_modes(self):
        for argv in (["scroll", "--no-editor"],
                     ["edit", "x.png", "--region", "0,0,1,1"],
                     ["diagnose", "--output", "a.png"]):
            with self.assertRaises(SystemExit):
                self.parse(argv)

    def test_bad_region_is_usage_error(self):
        with self.assertRaises(SystemExit):
            self.parse(["full", "--region", "nope"])

    def test_no_editor_flag(self):
        args = self.parse(["full", "--no-editor"])
        self.assertTrue(args.no_editor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
