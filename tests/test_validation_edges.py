from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date

import pandas as pd
from test_report import (
    FIXED_GENERATED_AT,
    LONG_WINDOW,
    SHORT_WINDOW,
    SOFTWARE_VERSION,
    STRATEGY_NAME,
    build_fixed_report_inputs,
)

from quant_lab.fingerprint import canonical_market_data_bytes
from quant_lab.models import BacktestConfig, MarketDataResult
from quant_lab.presentation import build_report_view
from quant_lab.strategies import moving_average_signal


def valid_fingerprint_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": date(2024, 1, 2),
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1_000.0,
            }
        ]
    )


class StrategyValidationEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prices = pd.DataFrame({"close": [100.0, 101.0, 102.0]})

    def test_boolean_and_fractional_windows_are_rejected(self) -> None:
        for short_window, long_window in ((True, 2), (1, False), (1.5, 2)):
            with self.subTest(short=short_window, long=long_window):
                with self.assertRaisesRegex(TypeError, "integers"):
                    moving_average_signal(self.prices, short_window, long_window)

    def test_nonpositive_windows_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            moving_average_signal(self.prices, 0, 2)

    def test_short_window_must_be_smaller(self) -> None:
        with self.assertRaisesRegex(ValueError, "smaller"):
            moving_average_signal(self.prices, 2, 2)

    def test_close_column_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "close column"):
            moving_average_signal(pd.DataFrame({"open": [100.0]}), 1, 2)

    def test_nonfinite_close_is_rejected(self) -> None:
        prices = pd.DataFrame({"close": [100.0, float("inf"), 102.0]})
        with self.assertRaisesRegex(ValueError, "finite"):
            moving_average_signal(prices, 1, 2)


class FingerprintValidationEdgeTests(unittest.TestCase):
    def test_all_canonical_columns_are_required(self) -> None:
        frame = valid_fingerprint_frame().drop(columns="volume")
        with self.assertRaisesRegex(ValueError, "volume.*required fingerprint column"):
            canonical_market_data_bytes(frame)

    def test_unparseable_date_reports_the_source_row(self) -> None:
        frame = valid_fingerprint_frame()
        frame.loc[0, "date"] = "not-a-date"
        with self.assertRaisesRegex(ValueError, r"date=row\[0\].*cannot map"):
            canonical_market_data_bytes(frame)

    def test_boolean_price_is_not_treated_as_numeric(self) -> None:
        frame = valid_fingerprint_frame()
        frame["open"] = frame["open"].astype(object)
        frame.loc[0, "open"] = True
        with self.assertRaisesRegex(ValueError, "open.*numeric type"):
            canonical_market_data_bytes(frame)

    def test_negative_volume_is_rejected(self) -> None:
        frame = valid_fingerprint_frame()
        frame.loc[0, "volume"] = -1.0
        with self.assertRaisesRegex(ValueError, "volume.*non-negative"):
            canonical_market_data_bytes(frame)

    def test_nonpositive_price_is_rejected(self) -> None:
        frame = valid_fingerprint_frame()
        frame.loc[0, "close"] = 0.0
        with self.assertRaisesRegex(ValueError, "close.*greater than zero"):
            canonical_market_data_bytes(frame)


class ModelValidationEdgeTests(unittest.TestCase):
    def test_config_dates_must_have_date_types(self) -> None:
        with self.assertRaisesRegex(TypeError, "start_date"):
            BacktestConfig(start_date="2024-01-01")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "end_date"):
            BacktestConfig(end_date="2024-01-02")  # type: ignore[arg-type]

    def test_market_metadata_invariants_are_enforced(self) -> None:
        market_data, _, _ = build_fixed_report_inputs()
        metadata = market_data.metadata
        invalid_changes = (
            ({"source": ""}, "non-empty"),
            ({"longest_lookback": 0}, "greater than zero"),
            ({"warmup_row_count": metadata.longest_lookback - 1}, "cover"),
            ({"analysis_row_count": 0}, "greater than zero"),
            ({"total_row_count": metadata.total_row_count + 1}, "warmup plus analysis"),
            ({"data_sha256": "ABC"}, "64 lowercase"),
        )
        for changes, message in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    replace(metadata, **changes)

    def test_market_data_result_checks_type_and_row_count(self) -> None:
        market_data, _, _ = build_fixed_report_inputs()
        with self.assertRaisesRegex(TypeError, "pandas DataFrame"):
            MarketDataResult(prices=[], metadata=market_data.metadata)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "row count"):
            MarketDataResult(prices=market_data.prices.iloc[:-1], metadata=market_data.metadata)


class PresentationValidationEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.market_data, self.comparison, self.config = build_fixed_report_inputs()

    def build(self, **overrides: object) -> object:
        arguments: dict[str, object] = {
            "config": self.config,
            "strategy_name": STRATEGY_NAME,
            "short_window": SHORT_WINDOW,
            "long_window": LONG_WINDOW,
            "software_version": SOFTWARE_VERSION,
            "generated_at_utc": FIXED_GENERATED_AT,
        }
        arguments.update(overrides)
        return build_report_view(self.market_data, self.comparison, **arguments)  # type: ignore[arg-type]

    def test_names_and_windows_are_validated_before_rendering(self) -> None:
        cases = (
            ({"strategy_name": " "}, "strategy_name"),
            ({"software_version": " "}, "software_version"),
            ({"short_window": True}, "short_window"),
            ({"long_window": 0}, "long_window"),
            ({"short_window": 60, "long_window": 20}, "smaller"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, message):
                    self.build(**overrides)

    def test_config_dates_must_match_market_metadata(self) -> None:
        bad_config = replace(self.config, start_date=date(2024, 1, 1))
        with self.assertRaisesRegex(ValueError, "start_date must match"):
            self.build(config=bad_config)

    def test_daily_schema_and_ledger_counts_must_match(self) -> None:
        missing_equity = self.comparison.strategy.daily.drop(columns="equity")
        bad_strategy = replace(self.comparison.strategy, daily=missing_equity)
        with self.assertRaisesRegex(ValueError, "missing columns"):
            build_report_view(
                self.market_data,
                replace(self.comparison, strategy=bad_strategy),
                config=self.config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )

        bad_metrics = replace(
            self.comparison.strategy.metrics,
            open_trade_count=self.comparison.strategy.metrics.open_trade_count + 1,
        )
        bad_strategy = replace(self.comparison.strategy, metrics=bad_metrics)
        with self.assertRaisesRegex(ValueError, "open trade count"):
            build_report_view(
                self.market_data,
                replace(self.comparison, strategy=bad_strategy),
                config=self.config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )

    def test_negative_equity_is_rejected(self) -> None:
        daily = self.comparison.strategy.daily.copy(deep=True)
        daily.loc[daily.index[0], "equity"] = -0.01
        bad_strategy = replace(self.comparison.strategy, daily=daily)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            build_report_view(
                self.market_data,
                replace(self.comparison, strategy=bad_strategy),
                config=self.config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )


if __name__ == "__main__":
    unittest.main()
