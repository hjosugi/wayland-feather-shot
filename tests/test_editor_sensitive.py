"""Unit tests for sensitive-text detection (GTK-free, no OCR engine needed).

Run:  python3 tests/test_editor_sensitive.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot import recognize  # noqa: E402
from wayland_feather_shot.editor import sensitive as S  # noqa: E402


def rules(text):
    return sorted({m.rule for m in S.sensitive_matches(text)})


def redacted(text):
    """What the rules would cover, as substrings."""
    return [text[m.start:m.end] for m in S.sensitive_matches(text)]


class LuhnTests(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertTrue(S.luhn([int(c) for c in "4242424242424242"]))

    def test_a_transposed_digit_fails(self):
        self.assertFalse(S.luhn([int(c) for c in "4242424242424243"]))

    def test_an_arbitrary_run_of_digits_usually_fails(self):
        self.assertFalse(S.luhn([int(c) for c in "1234567890123456"]))


class RuleTests(unittest.TestCase):
    def test_email(self):
        self.assertIn("email", rules("write to user@example.com today"))
        self.assertEqual(redacted("write to user@example.com today"),
                         ["user@example.com"])

    def test_urls_and_hosts(self):
        self.assertIn("url", rules("see https://internal.corp/admin"))
        self.assertIn("host", rules("see www.internal.corp/admin"))

    def test_ipv4_is_validated(self):
        self.assertIn("ipv4", rules("host 192.168.11.42"))
        self.assertNotIn("ipv4", rules("host 999.1.1.1"))

    def test_a_payment_card_needs_a_valid_check_digit(self):
        self.assertIn("card", rules("card 4242 4242 4242 4242"))
        self.assertEqual(rules("order 1234 5678 9012 3456"), [])

    def test_phone_numbers_by_digit_count(self):
        self.assertIn("phone", rules("call +81 90 1234 5678"))
        self.assertEqual(rules("only 123 here"), [])

    def test_jwt(self):
        self.assertIn("jwt", rules("eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSM"))

    def test_known_token_prefixes(self):
        for token in ("AKIAIOSFODNN7EXAMPLE", "AIzaSyD-ExampleKey123456",
                      "ya29.ExampleAccessToken1234"):
            self.assertTrue(rules(f"key {token}"), token)

    def test_a_labelled_secret_redacts_the_value_not_the_label(self):
        text = "password: hunter2secret"
        self.assertEqual(redacted(text), ["hunter2secret"])

    def test_labels_are_matched_case_insensitively(self):
        self.assertIn("secret", rules("API Key = abcdef123456"))

    def test_a_long_opaque_token(self):
        self.assertIn("token", rules("k7Hs93kdMs0aQ2ldPz84mXq1"))

    def test_ordinary_prose_is_left_alone(self):
        for text in ("just some ordinary words here",
                     "click the Settings button",
                     "見出しのテキストです",
                     "/usr/share/applications/foo.desktop",
                     "version 1.2 released"):
            self.assertEqual(rules(text), [], text)

    def test_a_hyphenated_word_is_not_a_token(self):
        self.assertEqual(rules("a-very-long-hyphenated-description-here"), [])


class MergeTests(unittest.TestCase):
    def test_overlapping_matches_merge(self):
        # An AWS key is also a long opaque token; one region, not two.
        matches = S.sensitive_matches("key AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(len(matches), 1)

    def test_the_merged_span_keeps_the_first_rule(self):
        self.assertEqual(S.sensitive_matches("key AKIAIOSFODNN7EXAMPLE")[0].rule,
                         "api-key")

    def test_separate_matches_stay_separate(self):
        text = "user@example.com and 192.168.1.1"
        self.assertEqual(len(S.sensitive_matches(text)), 2)

    def test_merge_spans_handles_touching_ranges(self):
        self.assertEqual(S.merge_spans([(0, 5), (5, 9), (20, 22)]),
                         [(0, 9), (20, 22)])

    def test_merge_spans_of_nothing(self):
        self.assertEqual(S.merge_spans([]), [])


class LineTests(unittest.TestCase):
    def _words(self):
        return [
            S.Word("password:", 10, 20, 40, 12, (1, 1, 1)),
            S.Word("hunter2secret", 55, 20, 70, 12, (1, 1, 1)),
            S.Word("user@example.com", 10, 40, 120, 12, (1, 1, 2)),
        ]

    def test_words_are_reassembled_into_lines(self):
        lines = S.build_lines(self._words())
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].text, "password: hunter2secret")

    def test_words_are_ordered_left_to_right(self):
        scrambled = [S.Word("second", 100, 0, 30, 10, (1, 1, 1)),
                     S.Word("first", 10, 0, 30, 10, (1, 1, 1))]
        self.assertEqual(S.build_lines(scrambled)[0].text, "first second")

    def test_blank_words_are_dropped(self):
        words = self._words() + [S.Word("  ", 0, 0, 5, 5, (1, 1, 1))]
        self.assertEqual(len(S.build_lines(words)[0].words), 2)

    def test_no_words_means_no_lines(self):
        self.assertEqual(S.build_lines([]), [])


class RegionTests(unittest.TestCase):
    IMAGE = (200.0, 100.0)

    def _words(self):
        return [
            S.Word("password:", 10, 20, 40, 12, (1, 1, 1)),
            S.Word("hunter2secret", 55, 20, 70, 12, (1, 1, 1)),
            S.Word("harmless", 10, 40, 60, 12, (1, 1, 2)),
        ]

    def test_only_the_sensitive_words_get_a_region(self):
        regions = S.regions_from_words(self._words(), self.IMAGE)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].text, "hunter2secret")
        self.assertEqual(regions[0].rule, "secret")

    def test_the_region_covers_the_word_it_came_from(self):
        region = S.regions_from_words(self._words(), self.IMAGE)[0]
        x, y, w, h = region.rect
        # The value starts at x=55 of 200, so the box starts near 0.275 and is
        # padded a little outwards.
        self.assertLess(x, 55 / 200)
        self.assertGreater(x + w, 125 / 200)

    def test_regions_stay_inside_the_image(self):
        words = [S.Word("user@example.com", 0, 0, 200, 100, (1, 1, 1))]
        x, y, w, h = S.regions_from_words(words, self.IMAGE)[0].rect
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, 1.0)
        self.assertLessEqual(y + h, 1.0)

    def test_padding_scales_with_the_image(self):
        small = S.normalized_padding((100.0, 100.0))
        large = S.normalized_padding((4000.0, 4000.0))
        self.assertGreater(small[0], large[0])
        for value in small + large:
            self.assertGreaterEqual(value, 0.002)
            self.assertLessEqual(value, 0.012)

    def test_no_words_means_no_regions(self):
        self.assertEqual(S.regions_from_words([], self.IMAGE), [])

    def test_a_degenerate_image_is_refused(self):
        self.assertEqual(S.regions_from_words(self._words(), (0.0, 0.0)), [])


class DedupeTests(unittest.TestCase):
    def _region(self, rect):
        return S.Region(rect=rect, text="x", rule="test")

    def test_a_box_inside_another_is_dropped(self):
        kept = S.dedupe([self._region((0.0, 0.0, 0.5, 0.5)),
                         self._region((0.1, 0.1, 0.2, 0.2))])
        self.assertEqual(len(kept), 1)

    def test_separate_boxes_are_both_kept(self):
        kept = S.dedupe([self._region((0.0, 0.0, 0.2, 0.2)),
                         self._region((0.7, 0.7, 0.2, 0.2))])
        self.assertEqual(len(kept), 2)

    def test_a_partial_overlap_is_kept(self):
        kept = S.dedupe([self._region((0.0, 0.0, 0.4, 0.4)),
                         self._region((0.3, 0.3, 0.4, 0.4))])
        self.assertEqual(len(kept), 2)

    def test_the_first_one_wins(self):
        first = self._region((0.0, 0.0, 0.5, 0.5))
        kept = S.dedupe([first, self._region((0.0, 0.0, 0.5, 0.5))])
        self.assertEqual(kept, [first])


class TsvTests(unittest.TestCase):
    """Parsing tesseract's word boxes, without tesseract."""

    HEADER = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
              "left\ttop\twidth\theight\tconf\ttext")

    def _tsv(self, *rows):
        return "\n".join([self.HEADER] + list(rows))

    def test_a_word_row_is_parsed(self):
        rows = recognize.parse_tsv_words(
            self._tsv("5\t1\t1\t1\t1\t1\t10\t20\t40\t12\t96.1\thello"))
        self.assertEqual(rows, [("hello", 10.0, 20.0, 40.0, 12.0, (1, 1, 1))])

    def test_non_word_levels_are_skipped(self):
        rows = recognize.parse_tsv_words(
            self._tsv("4\t1\t1\t1\t1\t0\t0\t0\t50\t50\t-1\t",
                      "5\t1\t1\t1\t1\t1\t10\t20\t40\t12\t96.1\thello"))
        self.assertEqual(len(rows), 1)

    def test_blank_text_is_skipped(self):
        rows = recognize.parse_tsv_words(
            self._tsv("5\t1\t1\t1\t1\t1\t10\t20\t40\t12\t96.1\t   "))
        self.assertEqual(rows, [])

    def test_rows_tesseract_has_no_confidence_in_are_skipped(self):
        rows = recognize.parse_tsv_words(
            self._tsv("5\t1\t1\t1\t1\t1\t10\t20\t40\t12\t-1\tnoise"))
        self.assertEqual(rows, [])

    def test_a_zero_sized_box_is_skipped(self):
        rows = recognize.parse_tsv_words(
            self._tsv("5\t1\t1\t1\t1\t1\t10\t20\t0\t0\t90\thello"))
        self.assertEqual(rows, [])

    def test_empty_output_is_not_an_error(self):
        self.assertEqual(recognize.parse_tsv_words(""), [])

    def test_output_without_a_usable_header_is_not_an_error(self):
        self.assertEqual(recognize.parse_tsv_words("garbage\nmore garbage"), [])

    def test_a_short_row_is_skipped(self):
        self.assertEqual(recognize.parse_tsv_words(self._tsv("5\t1\t1")), [])

    def test_the_command_uses_sparse_text_mode(self):
        command = recognize.tesseract_tsv_command("/tmp/a.png")
        self.assertIn("--psm", command)
        self.assertIn("tsv", command)


if __name__ == "__main__":
    unittest.main()
