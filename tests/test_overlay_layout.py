"""Headless tests for positioning the region capture controls."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayland_feather_shot.overlay.layout import (  # noqa: E402
    layout_controls, position_bars, position_label,
)


class OverlayLayoutTests(unittest.TestCase):
    TOOLBAR = (900, 52)
    VERTICAL_ACTIONS = (52, 360)

    def assert_bars_fit_without_overlap(self, window, toolbar, actions,
                                        toolbar_size=None, action_size=None):
        tx, ty = toolbar
        sx, sy = actions
        tw, th = toolbar_size or self.TOOLBAR
        sw, sh = action_size or self.VERTICAL_ACTIONS
        self.assertGreaterEqual(tx, 0)
        self.assertGreaterEqual(ty, 0)
        self.assertGreaterEqual(sx, 0)
        self.assertGreaterEqual(sy, 0)
        self.assertLessEqual(tx + tw, window[0])
        self.assertLessEqual(ty + th, window[1])
        self.assertLessEqual(sx + sw, window[0])
        self.assertLessEqual(sy + sh, window[1])
        self.assertTrue(
            tx + tw + 8 <= sx or sx + sw + 8 <= tx
            or ty + th + 8 <= sy or sy + sh + 8 <= ty,
            (toolbar, actions),
        )

    def test_large_selection_keeps_preferred_positions(self):
        toolbar, actions = position_bars(
            (2560, 1440), (700, 300, 1700, 800),
            self.TOOLBAR, self.VERTICAL_ACTIONS,
        )
        # Right-aligned with the selection, where the action bar hangs.
        self.assertEqual(toolbar, (800, 812))
        self.assertEqual(actions, (1712, 300))

    def test_small_selections_do_not_cover_controls_anywhere(self):
        window = (2560, 1440)
        selections = (
            (1200, 600, 1300, 680),  # center
            (1200, 20, 1300, 70),    # top
            (1200, 1340, 1300, 1400),  # bottom
            (10, 600, 110, 680),     # left
            (2450, 600, 2550, 680),  # right
            (2450, 1340, 2550, 1400),  # bottom-right
        )
        for selection in selections:
            with self.subTest(selection=selection):
                toolbar, actions = position_bars(
                    window, selection, self.TOOLBAR, self.VERTICAL_ACTIONS,
                )
                self.assert_bars_fit_without_overlap(
                    window, toolbar, actions,
                )

    def test_compact_viewport_uses_another_arrangement(self):
        window = (1280, 720)
        for selection in (
            (600, 300, 680, 360),
            (10, 10, 90, 50),
            (1170, 630, 1250, 700),
        ):
            with self.subTest(selection=selection):
                toolbar, actions = position_bars(
                    window, selection, self.TOOLBAR, self.VERTICAL_ACTIONS,
                )
                self.assert_bars_fit_without_overlap(
                    window, toolbar, actions,
                )

    def test_narrow_viewport_stacks_bars_when_one_move_is_not_enough(self):
        for window, selection in (
            ((960, 600), (8, 248, 108, 328)),
            ((1000, 500), (448, 8, 548, 88)),
        ):
            with self.subTest(window=window, selection=selection):
                toolbar, actions = position_bars(
                    window, selection, self.TOOLBAR, self.VERTICAL_ACTIONS,
                )
                self.assert_bars_fit_without_overlap(
                    window, toolbar, actions,
                )

    def test_short_viewport_places_bars_side_by_side(self):
        window = (1000, 380)
        toolbar, actions = position_bars(
            window, (450, 150, 550, 230), self.TOOLBAR, self.VERTICAL_ACTIONS,
        )
        self.assert_bars_fit_without_overlap(window, toolbar, actions)

    def test_short_viewport_reorients_actions_before_bars_overlap(self):
        window = (1052, 345)
        toolbar_size = (1002, 52)
        action_row_size = (342, 52)
        layout = layout_controls(
            window, (397, 231, 489, 303), toolbar_size, (54, 328),
            action_row_size,
        )
        self.assertTrue(layout.stacked)
        self.assert_bars_fit_without_overlap(
            window, layout.toolbar, layout.actions,
            toolbar_size, action_row_size,
        )

    def test_action_row_stays_visible_when_selection_blocks_outside_slots(self):
        window = (1663, 195)
        toolbar_size = (1002, 52)
        action_row_size = (342, 52)
        layout = layout_controls(
            window, (1280, 74, 1298, 119), toolbar_size, (54, 328),
            action_row_size,
        )
        self.assertTrue(layout.stacked)
        self.assert_bars_fit_without_overlap(
            window, layout.toolbar, layout.actions,
            toolbar_size, action_row_size,
        )

    def test_wide_toolbar_shifts_left_so_the_actions_hang_from_the_top(self):
        # The toolbar is wider than the selection; centred, it would run under
        # the action bar. Rather than lifting the actions above the selection,
        # the toolbar moves left and the actions keep hanging from the top
        # edge, so the L looks the same as everywhere else.
        window = (2560, 1440)
        toolbar_size, action_size = (1002, 52), (54, 328)
        selection = (983, 717, 1738, 909)
        toolbar, actions = position_bars(
            window, selection, toolbar_size, action_size,
        )
        self.assertEqual(toolbar[1], 921)
        self.assertEqual(actions, (1750, 717))
        self.assertLessEqual(toolbar[0] + toolbar_size[0] + 8, actions[0])
        self.assert_bars_fit_without_overlap(
            window, toolbar, actions, toolbar_size, action_size,
        )

    def test_short_wide_selection_keeps_the_actions_hanging_from_the_top(self):
        window = (2560, 1440)
        toolbar_size, action_size = (1002, 52), (54, 328)
        selection = (400, 600, 2100, 700)
        toolbar, actions = position_bars(
            window, selection, toolbar_size, action_size,
        )
        self.assertEqual(toolbar[1], 712)
        self.assertEqual(actions, (2112, 600))
        self.assert_bars_fit_without_overlap(
            window, toolbar, actions, toolbar_size, action_size,
        )

    def test_tiny_selection_keeps_toolbar_below_when_there_is_room(self):
        window = (2560, 1440)
        toolbar_size, action_size = (1002, 52), (54, 328)
        selection = (1200, 600, 1300, 680)
        toolbar, actions = position_bars(
            window, selection, toolbar_size, action_size,
        )
        self.assertEqual(toolbar[1], 692)
        self.assertEqual(actions[0], 1312)
        self.assertLess(toolbar[0], selection[2])
        self.assertGreater(toolbar[0] + toolbar_size[0], selection[0])
        self.assert_bars_fit_without_overlap(
            window, toolbar, actions, toolbar_size, action_size,
        )

    def test_tiny_selection_near_top_keeps_both_bars_attached(self):
        window = (2560, 1440)
        toolbar_size, action_size = (1002, 52), (54, 328)
        selection = (1200, 40, 1300, 100)
        toolbar, actions = position_bars(
            window, selection, toolbar_size, action_size,
        )
        self.assertEqual(toolbar[1], 112)
        self.assertEqual(actions[0], 1312)
        self.assertLess(toolbar[0], selection[2])
        self.assertGreater(toolbar[0] + toolbar_size[0], selection[0])
        self.assertLess(actions[1], selection[3])
        self.assert_bars_fit_without_overlap(
            window, toolbar, actions, toolbar_size, action_size,
        )

    def test_bottom_left_selection_keeps_both_bars_attached(self):
        window = (2560, 1440)
        toolbar_size, action_size = (1002, 52), (54, 328)
        selection = (120, 1200, 370, 1440)
        toolbar, actions = position_bars(
            window, selection, toolbar_size, action_size,
        )
        # No room below: inside the selection's bottom edge, not above it.
        self.assertEqual(toolbar[1], 1376)
        self.assertEqual(actions[0], 54)
        self.assertLess(toolbar[0], selection[2])
        self.assertGreater(toolbar[0] + toolbar_size[0], selection[0])
        self.assertGreater(actions[1] + action_size[1], selection[1])
        self.assert_bars_fit_without_overlap(
            window, toolbar, actions, toolbar_size, action_size,
        )

    def test_corner_actions_form_second_horizontal_row(self):
        window = (2560, 1440)
        toolbar_size = (1002, 52)
        action_row_size = (342, 52)
        cases = (
            ((0, 0, 486, 157), (8, 169), (8, 233)),
            ((2258, 0, 2559, 71), (1550, 83), (2210, 147)),
            ((0, 1313, 505, 1438), (8, 1304), (8, 1368)),
            ((2297, 1214, 2559, 1438), (1550, 1304), (2210, 1368)),
        )
        for selection, toolbar, actions in cases:
            with self.subTest(selection=selection):
                layout = layout_controls(
                    window, selection, toolbar_size, (54, 328),
                    action_row_size,
                )
                self.assertTrue(layout.stacked)
                self.assertEqual(layout.toolbar, toolbar)
                self.assertEqual(layout.actions, actions)
                self.assert_bars_fit_without_overlap(
                    window, layout.toolbar, layout.actions,
                    toolbar_size, action_row_size,
                )

    def test_toolbar_never_flips_above_the_selection(self):
        # Below when it fits; otherwise inside the selection's bottom edge,
        # including a selection that runs past the window (zoomed in).
        window = (2560, 1440)
        for selection in ((700, 300, 1700, 800), (700, 900, 1700, 1440),
                          (700, 1000, 1700, 2100), (0, 0, 2560, 1440)):
            with self.subTest(selection=selection):
                toolbar, _actions = position_bars(
                    window, selection, (1002, 52), (54, 328))
                self.assertGreaterEqual(toolbar[1], selection[1])
                self.assertLessEqual(toolbar[1] + 52, window[1] - 8)

    def test_ordinary_selections_keep_vertical_action_bar(self):
        for selection in (
            (983, 717, 1738, 909),
            (1200, 600, 1300, 680),
            (120, 1200, 370, 1440),
        ):
            with self.subTest(selection=selection):
                layout = layout_controls(
                    (2560, 1440), selection, (1002, 52), (54, 328),
                    (342, 52),
                )
                self.assertFalse(layout.stacked)

    def test_fullscreen_selection_uses_available_fallback(self):
        layout = layout_controls(
            (2560, 1440), (0, 0, 2560, 1440),
            (1002, 52), (54, 328), (342, 52),
        )
        self.assertFalse(layout.stacked)

    def test_dimension_label_avoids_toolbar_and_actions_at_bottom(self):
        label = position_label(
            (2560, 1440), (120, 1200, 370, 1440), (75, 20),
            ((120, 1136, 1122, 1188), (54, 1104, 108, 1432)),
        )
        self.assertEqual(label, (382, 1200))

    def test_dimension_label_keeps_its_above_selection_position(self):
        label = position_label(
            (2560, 1440), (324, 234, 749, 388), (75, 20),
            ((38, 400, 1040, 452), (761, 60, 815, 388)),
        )
        self.assertEqual(label, (325, 209))

    def test_fullscreen_label_stays_clear_of_corner_resize_handle(self):
        label = position_label(
            (2560, 1440), (0, 0, 2560, 1440), (75, 20),
            ((779, 1380, 1781, 1432), (2498, 8, 2552, 336)),
        )
        self.assertEqual(label, (18, 18))


if __name__ == "__main__":
    unittest.main()
