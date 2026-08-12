from __future__ import annotations

import unittest
from datetime import date
from time import perf_counter

import numpy as np
import pandas as pd

from app.components import (
    CHART_BENCHMARK_COLUMN,
    CHART_EXCESS_RETURN_COLUMN,
    CHART_STRATEGY_COLUMN,
    DARK_THEME,
    DEFAULT_CHART_MAX_ROWS,
    build_equity_chart_spec,
    build_excess_return_chart_spec,
    downsample_equity_chart,
)

FORMAL_DOMAIN = (date(2015, 1, 2), date(2024, 12, 31))


def formal_scale_chart() -> pd.DataFrame:
    positions = np.arange(2_516, dtype=float)
    return pd.DataFrame(
        {
            CHART_STRATEGY_COLUMN: (
                10_000.0 * np.exp(positions * 0.00020) * (1.0 + 0.035 * np.sin(positions / 33.0))
            ),
            CHART_BENCHMARK_COLUMN: (
                10_000.0
                * np.exp(positions * 0.00024)
                * (1.0 + 0.025 * np.sin((positions / 41.0) + 0.4))
            ),
        },
        index=pd.Index(pd.bdate_range("2015-01-02", periods=2_516), name="日期"),
    )


class ChartPerformanceRegressionTests(unittest.TestCase):
    def test_formal_scale_fast_chart_has_bounded_deterministic_payload(self) -> None:
        complete = formal_scale_chart()
        original = complete.copy(deep=True)

        first = downsample_equity_chart(complete)
        second = downsample_equity_chart(complete)
        complete_payload = (
            complete.reset_index()
            .to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
            .encode("utf-8")
        )
        fast_payload = (
            first.reset_index()
            .to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
            .encode("utf-8")
        )

        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(complete, original)
        self.assertLessEqual(len(first), DEFAULT_CHART_MAX_ROWS)
        self.assertLess(len(fast_payload), len(complete_payload) * 0.4)
        self.assertEqual(first.index[0], complete.index[0])
        self.assertEqual(first.index[-1], complete.index[-1])

    def test_chart_spec_does_not_reintroduce_hover_point_layers(self) -> None:
        spec = build_equity_chart_spec(FORMAL_DOMAIN)

        self.assertEqual(spec["mark"]["type"], "line")
        self.assertNotIn("layer", spec)
        self.assertEqual(len(spec["params"]), 2)
        self.assertEqual(spec["params"][0]["bind"], "scales")
        self.assertEqual(spec["params"][1]["bind"], "legend")
        self.assertNotIn("customdata", str(spec).lower())

    def test_dark_chart_theme_changes_only_visual_configuration(self) -> None:
        light = build_equity_chart_spec(FORMAL_DOMAIN)
        dark = build_equity_chart_spec(FORMAL_DOMAIN, dark_mode=True)
        light_excess = build_excess_return_chart_spec(FORMAL_DOMAIN)
        dark_excess = build_excess_return_chart_spec(FORMAL_DOMAIN, dark_mode=True)

        self.assertEqual(light["transform"], dark["transform"])
        self.assertEqual(light["encoding"]["x"]["field"], dark["encoding"]["x"]["field"])
        self.assertEqual(light["encoding"]["y"]["field"], dark["encoding"]["y"]["field"])
        self.assertEqual(light["encoding"]["tooltip"], dark["encoding"]["tooltip"])
        self.assertEqual(light_excess["encoding"], dark_excess["encoding"])
        self.assertEqual(dark["background"], DARK_THEME.surface)
        self.assertEqual(dark["config"]["view"]["fill"], DARK_THEME.surface)
        self.assertEqual(dark_excess["background"], DARK_THEME.surface)
        self.assertEqual(dark["encoding"]["x"]["axis"]["tickCount"], 6)
        self.assertEqual(dark["encoding"]["x"]["axis"]["format"], "%Y")
        self.assertEqual(dark["encoding"]["x"]["axis"]["tickMinStep"], 86_400_000)
        self.assertEqual(
            dark["encoding"]["x"]["scale"],
            {"domain": ["2015-01-02", "2024-12-31"], "nice": False},
        )
        self.assertFalse(dark["encoding"]["x"]["axis"]["grid"])
        self.assertEqual(dark["encoding"]["y"]["axis"]["tickCount"], 5)
        self.assertEqual(
            dark["encoding"]["color"]["scale"]["range"],
            [DARK_THEME.chart_strategy, DARK_THEME.chart_benchmark],
        )
        self.assertEqual(dark_excess["mark"]["color"], DARK_THEME.chart_excess)
        self.assertEqual(
            len(
                {
                    DARK_THEME.chart_strategy,
                    DARK_THEME.chart_benchmark,
                    DARK_THEME.chart_excess,
                }
            ),
            3,
        )

    def test_excess_chart_has_bounded_payload_and_browser_local_zoom(self) -> None:
        complete_equity = formal_scale_chart()
        complete = pd.DataFrame(
            {
                CHART_EXCESS_RETURN_COLUMN: (
                    complete_equity[CHART_STRATEGY_COLUMN] - complete_equity[CHART_BENCHMARK_COLUMN]
                )
                / 10_000.0
            },
            index=complete_equity.index,
        )

        fast = downsample_equity_chart(complete)
        complete_payload = complete.reset_index().to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
        fast_payload = fast.reset_index().to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
        spec = build_excess_return_chart_spec(FORMAL_DOMAIN)

        self.assertLessEqual(len(fast), DEFAULT_CHART_MAX_ROWS)
        self.assertLess(
            len(fast_payload.encode("utf-8")), len(complete_payload.encode("utf-8")) * 0.4
        )
        self.assertEqual(fast.index[0], complete.index[0])
        self.assertEqual(fast.index[-1], complete.index[-1])
        self.assertEqual(spec["params"][0]["bind"], "scales")
        self.assertNotIn("layer", spec)

    def test_fast_chart_preserves_datetime_value_pairs_and_exact_domain(self) -> None:
        complete = formal_scale_chart().reset_index()
        fast = downsample_equity_chart(complete)
        complete_rows = {
            (
                row["日期"],
                row[CHART_STRATEGY_COLUMN],
                row[CHART_BENCHMARK_COLUMN],
            )
            for _, row in complete.iterrows()
        }

        self.assertEqual(fast.iloc[0].to_dict(), complete.iloc[0].to_dict())
        self.assertEqual(fast.iloc[-1].to_dict(), complete.iloc[-1].to_dict())
        for _, row in fast.iterrows():
            self.assertIn(
                (
                    row["日期"],
                    row[CHART_STRATEGY_COLUMN],
                    row[CHART_BENCHMARK_COLUMN],
                ),
                complete_rows,
            )

    def test_tooltip_fields_have_fixed_order_and_number_format(self) -> None:
        tooltip = build_equity_chart_spec(FORMAL_DOMAIN)["encoding"]["tooltip"]

        self.assertEqual([field["title"] for field in tooltip], ["日期", "系列", "账户净值"])
        self.assertEqual(tooltip[0]["format"], "%Y-%m-%d")
        self.assertEqual(tooltip[2]["format"], ",.2f")

    def test_formal_scale_downsampling_and_serialization_has_a_bounded_runtime(self) -> None:
        complete = formal_scale_chart()

        started = perf_counter()
        fast = downsample_equity_chart(complete)
        payload = fast.reset_index().to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
        elapsed = perf_counter() - started

        self.assertLess(elapsed, 1.0)
        self.assertLessEqual(len(fast), DEFAULT_CHART_MAX_ROWS)
        self.assertLess(len(payload.encode("utf-8")), 100_000)


if __name__ == "__main__":
    unittest.main()
