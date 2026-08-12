from __future__ import annotations

import unittest

from scripts.run_chart_dark_acceptance import parse_args, validate_snapshot


def valid_snapshot() -> dict[str, object]:
    return {
        "viewportWidth": 1366,
        "viewportHeight": 768,
        "viewportOverflow": 0,
        "bannedVisibleText": "QuantLab 运行回测 交互图 查看数据 重置视图",
        "nativeToolbarVisible": False,
        "chartFacts": {
            "startDate": "2015-01-01",
            "endDate": "2024-12-31",
            "startStrategy": 10_000.0,
            "endStrategy": 18_500.0,
            "startBenchmark": 9_990.0,
            "endBenchmark": 25_000.0,
        },
        "axisYears": ["2015", "2017", "2019", "2021", "2023"],
        "icons": [{"inside": True}],
        "tooltip": {
            "rows": [
                ["日期", "2021-11-18"],
                ["系列", "买入持有"],
                ["账户净值", "8,078.76"],
            ],
            "x": 400,
            "y": 220,
            "right": 610,
            "bottom": 320,
            "width": 210,
            "height": 100,
        },
    }


class ChartDarkAcceptanceContractTests(unittest.TestCase):
    def test_valid_runtime_snapshot_passes(self) -> None:
        validate_snapshot(valid_snapshot())

    def test_future_axis_and_implausible_equity_are_rejected(self) -> None:
        future = valid_snapshot()
        future["axisYears"] = ["2015", "2030"]
        with self.assertRaisesRegex(AssertionError, "future year"):
            validate_snapshot(future)

        near_zero = valid_snapshot()
        near_zero["chartFacts"]["startStrategy"] = 0.2
        with self.assertRaisesRegex(AssertionError, "close to zero"):
            validate_snapshot(near_zero)

    def test_native_toolbar_and_english_controls_are_rejected(self) -> None:
        toolbar = valid_snapshot()
        toolbar["nativeToolbarVisible"] = True
        with self.assertRaisesRegex(AssertionError, "toolbar"):
            validate_snapshot(toolbar)

        english = valid_snapshot()
        english["bannedVisibleText"] = "Show data"
        with self.assertRaisesRegex(AssertionError, "English control"):
            validate_snapshot(english)

    def test_tooltip_order_and_viewport_bounds_are_enforced(self) -> None:
        wrong_order = valid_snapshot()
        wrong_order["tooltip"]["rows"] = [
            ["系列", "买入持有"],
            ["日期", "2021-11-18"],
            ["账户净值", "8,078.76"],
        ]
        with self.assertRaisesRegex(AssertionError, "row order"):
            validate_snapshot(wrong_order)

        overflow = valid_snapshot()
        overflow["tooltip"]["right"] = 1400
        with self.assertRaisesRegex(AssertionError, "horizontal viewport"):
            validate_snapshot(overflow)

    def test_icon_bounds_and_timeout_limit_are_enforced(self) -> None:
        outside = valid_snapshot()
        outside["icons"] = [{"inside": False}]
        with self.assertRaisesRegex(AssertionError, "icon exceeds"):
            validate_snapshot(outside)

        self.assertEqual(parse_args(["--timeout", "300"]).timeout, 300)
        with self.assertRaises(SystemExit):
            parse_args(["--timeout", "301"])


if __name__ == "__main__":
    unittest.main()
