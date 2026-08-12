from __future__ import annotations

import unittest

from scripts.run_dark_theme_acceptance import contrast_ratio, validate_runtime_snapshot


def valid_snapshot() -> dict[str, object]:
    return {
        "viewportWidth": 1366,
        "viewportHeight": 768,
        "viewportOverflow": 0,
        "sidebarRestoreVisible": True,
        "disabledButton": {
            "disabled": True,
            "background": "rgb(23, 32, 51)",
            "color": "rgb(203, 213, 225)",
        },
        "tooltip": {
            "background": "rgb(30, 41, 59)",
            "color": "rgb(241, 245, 249)",
            "x": 220,
            "y": 322,
            "width": 320,
            "height": 44,
            "right": 540,
            "bottom": 366,
        },
        "icons": [
            {
                "inside": True,
                "aria": "Increment",
            }
        ],
        "segments": {
            "activeBackground": "rgb(29, 58, 95)",
            "normalBackground": "rgba(0, 0, 0, 0)",
            "activeBorder": "rgb(96, 165, 250)",
            "normalBorder": "rgba(0, 0, 0, 0)",
        },
    }


class DarkThemeAcceptanceContractTests(unittest.TestCase):
    def test_reference_colors_meet_runtime_contrast_contract(self) -> None:
        self.assertGreaterEqual(
            contrast_ratio("rgb(203, 213, 225)", "rgb(23, 32, 51)"),
            3.0,
        )
        self.assertGreaterEqual(
            contrast_ratio("rgb(241, 245, 249)", "rgb(30, 41, 59)"),
            4.5,
        )

    def test_valid_computed_style_and_bounding_box_snapshot_passes(self) -> None:
        validate_runtime_snapshot(valid_snapshot())

    def test_white_disabled_button_is_rejected(self) -> None:
        snapshot = valid_snapshot()
        snapshot["disabledButton"]["background"] = "rgb(255, 255, 255)"

        with self.assertRaisesRegex(AssertionError, "white background"):
            validate_runtime_snapshot(snapshot)

    def test_tooltip_viewport_overflow_is_rejected(self) -> None:
        snapshot = valid_snapshot()
        snapshot["tooltip"]["right"] = 1400

        with self.assertRaisesRegex(AssertionError, "horizontal viewport"):
            validate_runtime_snapshot(snapshot)

    def test_icon_outside_parent_button_is_rejected(self) -> None:
        snapshot = valid_snapshot()
        snapshot["icons"][0]["inside"] = False

        with self.assertRaisesRegex(AssertionError, "SVG exceeds"):
            validate_runtime_snapshot(snapshot)

    def test_indistinguishable_segmented_states_are_rejected(self) -> None:
        snapshot = valid_snapshot()
        snapshot["segments"]["activeBackground"] = snapshot["segments"]["normalBackground"]

        with self.assertRaisesRegex(AssertionError, "backgrounds are identical"):
            validate_runtime_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
