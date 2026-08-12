from __future__ import annotations

import math
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd
from fixtures import G13_DATA_SHA256, GOLDEN_CASES_BY_ID

from quant_lab.backtest import run_strategy_backtest
from quant_lab.data import (
    SPY_ADJUSTMENT_METHOD,
    SPY_SOURCE,
    STANDARD_PRICE_COLUMNS,
    adapt_yfinance_history,
    build_spy_market_data_result,
    fetch_spy_raw_yfinance,
    load_spy_adjusted_daily,
    standardize_adjusted_ohlcv,
    validate_standardized_prices,
)
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.models import BacktestConfig
from quant_lab.strategies import moving_average_signal

REL_TOL = 1e-12
ABS_TOL = 1e-9
FIXED_FETCHED_AT = datetime(2025, 1, 10, 12, 30, tzinfo=timezone.utc)


def g13_raw_frame() -> pd.DataFrame:
    case = GOLDEN_CASES_BY_ID["G13"]
    volumes = {bar.date: bar.volume for bar in case.bars}
    return pd.DataFrame(
        [
            {
                "date": expected.date,
                "raw_open": expected.raw_open,
                "raw_high": expected.raw_high,
                "raw_low": expected.raw_low,
                "raw_close": expected.raw_close,
                "adjusted_close": expected.adjusted_close,
                "volume": volumes[expected.date],
            }
            for expected in case.corporate_actions
        ]
    )


def sample_yfinance_history() -> pd.DataFrame:
    dates = pd.to_datetime(
        [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-08",
            "2024-01-09",
        ]
    )
    closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    return pd.DataFrame(
        {
            "Open": closes - 0.5,
            "High": closes + 1.0,
            "Low": closes - 1.0,
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0, 1500.0],
        },
        index=pd.DatetimeIndex(dates, name="Date"),
    )


class StrictFloatAssertions(unittest.TestCase):
    def assert_close(self, actual: float, expected: float, context: str = "") -> None:
        self.assertTrue(
            math.isclose(
                float(actual),
                float(expected),
                rel_tol=REL_TOL,
                abs_tol=ABS_TOL,
            ),
            f"{context}: actual={actual!r}, expected={expected!r}",
        )


class G13AdjustmentTests(StrictFloatAssertions):
    def test_g13_adjustment_factor_and_all_ohlc_are_exact(self) -> None:
        case = GOLDEN_CASES_BY_ID["G13"]
        raw = g13_raw_frame()
        actual = standardize_adjusted_ohlcv(raw)

        self.assertEqual(tuple(actual.columns), STANDARD_PRICE_COLUMNS)
        self.assertEqual(len(actual), 2)
        for row_index, expected in enumerate(case.corporate_actions):
            row = actual.iloc[row_index]
            self.assertEqual(row["date"].isoformat(), expected.date)
            actual_factor = float(row["open"]) / expected.raw_open
            self.assert_close(actual_factor, expected.adjustment_factor, expected.date)
            self.assert_close(row["open"], expected.expected_open, expected.date)
            self.assert_close(row["high"], expected.expected_high, expected.date)
            self.assert_close(row["low"], expected.expected_low, expected.date)
            self.assert_close(row["close"], expected.expected_close, expected.date)

        self.assert_close(actual.loc[0, "close"], actual.loc[1, "open"])
        validate_standardized_prices(actual)
        self.assertEqual(calculate_market_data_sha256(actual), G13_DATA_SHA256)

    def test_reversed_provider_rows_are_normalized_to_ascending(self) -> None:
        actual = standardize_adjusted_ohlcv(g13_raw_frame().iloc[::-1].reset_index(drop=True))
        self.assertEqual(
            [value.isoformat() for value in actual["date"]],
            ["2024-12-16", "2024-12-17"],
        )

    def test_duplicate_trading_date_is_rejected(self) -> None:
        raw = pd.concat([g13_raw_frame(), g13_raw_frame().iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(
            ValueError,
            "field='date'.*date=2024-12-16.*actual=2 rows",
        ):
            standardize_adjusted_ohlcv(raw)

    def test_missing_raw_ohlc_column_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "field='raw_open'.*actual=<missing>",
        ):
            standardize_adjusted_ohlcv(g13_raw_frame().drop(columns="raw_open"))

    def test_zero_and_negative_prices_report_field_date_and_value(self) -> None:
        for field, value in (("raw_open", 0.0), ("adjusted_close", -1.0)):
            with self.subTest(field=field, value=value):
                raw = g13_raw_frame()
                raw.loc[0, field] = value
                with self.assertRaisesRegex(
                    ValueError,
                    f"field='{field}'.*date=2024-12-16.*actual={value!r}",
                ):
                    standardize_adjusted_ohlcv(raw)

    def test_nan_and_infinite_prices_are_rejected(self) -> None:
        for field, value in (("raw_high", math.nan), ("raw_low", math.inf)):
            with self.subTest(field=field):
                raw = g13_raw_frame()
                raw.loc[0, field] = value
                with self.assertRaisesRegex(
                    ValueError,
                    f"field='{field}'.*date=2024-12-16.*must be finite",
                ):
                    standardize_adjusted_ohlcv(raw)

    def test_numeric_strings_are_not_silently_coerced(self) -> None:
        raw = g13_raw_frame()
        raw["raw_open"] = raw["raw_open"].astype(object)
        raw.at[0, "raw_open"] = "100.0"
        with self.assertRaisesRegex(
            ValueError,
            "field='raw_open'.*date=2024-12-16.*numeric type",
        ):
            standardize_adjusted_ohlcv(raw)

    def test_invalid_high_low_relationship_is_rejected(self) -> None:
        raw = g13_raw_frame()
        raw.loc[0, "raw_high"] = 99.0
        with self.assertRaisesRegex(
            ValueError,
            "field='raw_high'.*date=2024-12-16.*actual=99.0",
        ):
            standardize_adjusted_ohlcv(raw)

    def test_raw_close_zero_cannot_form_adjustment_factor(self) -> None:
        raw = g13_raw_frame()
        raw.loc[0, "raw_close"] = 0.0
        with self.assertRaisesRegex(
            ValueError,
            "field='raw_close'.*date=2024-12-16.*actual=0.0",
        ):
            standardize_adjusted_ohlcv(raw)

    def test_non_finite_adjustment_factor_is_rejected(self) -> None:
        raw = pd.DataFrame(
            [
                {
                    "date": "2024-12-16",
                    "raw_open": 5e-324,
                    "raw_high": 5e-324,
                    "raw_low": 5e-324,
                    "raw_close": 5e-324,
                    "adjusted_close": 1.0,
                    "volume": 1.0,
                }
            ]
        )
        with self.assertRaisesRegex(
            ValueError,
            "field='adjustment_factor'.*date=2024-12-16.*actual=inf",
        ):
            standardize_adjusted_ohlcv(raw)

    def test_utc_timestamp_maps_to_prior_new_york_trading_date(self) -> None:
        raw = g13_raw_frame().iloc[[0]].copy()
        raw["date"] = raw["date"].astype(object)
        raw.at[0, "date"] = pd.Timestamp("2024-01-03T01:00:00Z")
        actual = standardize_adjusted_ohlcv(raw)
        self.assertEqual(actual.loc[0, "date"], date(2024, 1, 2))


class StandardizedValidationTests(unittest.TestCase):
    def test_standardized_missing_ohlc_is_rejected(self) -> None:
        standardized = standardize_adjusted_ohlcv(g13_raw_frame())
        with self.assertRaisesRegex(ValueError, "field='close'.*actual=<missing>"):
            validate_standardized_prices(standardized.drop(columns="close"))

    def test_standardized_dates_must_be_ascending_and_unique(self) -> None:
        standardized = standardize_adjusted_ohlcv(g13_raw_frame())
        reversed_prices = standardized.iloc[::-1].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "strictly ascending"):
            validate_standardized_prices(reversed_prices)

        duplicate = pd.concat([standardized, standardized.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "date=2024-12-16.*duplicate"):
            validate_standardized_prices(duplicate)

    def test_standardized_relationship_error_is_specific(self) -> None:
        standardized = standardize_adjusted_ohlcv(g13_raw_frame())
        standardized.loc[0, "low"] = 60.0
        with self.assertRaisesRegex(
            ValueError,
            "field='low'.*date=2024-12-16.*actual=60.0",
        ):
            validate_standardized_prices(standardized)

    def test_invalid_date_reports_original_value(self) -> None:
        standardized = standardize_adjusted_ohlcv(g13_raw_frame())
        standardized.loc[0, "date"] = "not-a-date"
        with self.assertRaisesRegex(
            ValueError,
            "field='date'.*actual='not-a-date'",
        ):
            validate_standardized_prices(standardized)


class MarketDataResultTests(StrictFloatAssertions):
    def test_ci_offline_guard_blocks_provider_before_importing_yfinance(self) -> None:
        with patch.dict(os.environ, {"QUANTLAB_OFFLINE": "1"}):
            with self.assertRaisesRegex(RuntimeError, "disabled by QUANTLAB_OFFLINE"):
                fetch_spy_raw_yfinance(date(2024, 1, 1), date(2024, 1, 31))

    def test_metadata_dates_counts_hash_and_warmup_rows(self) -> None:
        result = build_spy_market_data_result(
            sample_yfinance_history(),
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=FIXED_FETCHED_AT,
            source=SPY_SOURCE,
            source_version="test-provider-1.0",
        )
        metadata = result.metadata
        self.assertEqual(metadata.symbol, "SPY")
        self.assertEqual(metadata.source, SPY_SOURCE)
        self.assertEqual(metadata.source_version, "test-provider-1.0")
        self.assertEqual(metadata.fetched_at_utc, FIXED_FETCHED_AT)
        self.assertEqual(metadata.requested_start_date, date(2024, 1, 8))
        self.assertEqual(metadata.requested_end_date, date(2024, 1, 9))
        self.assertEqual(metadata.actual_start_date, date(2024, 1, 3))
        self.assertEqual(metadata.actual_end_date, date(2024, 1, 9))
        self.assertEqual(metadata.analysis_start_date, date(2024, 1, 8))
        self.assertEqual(metadata.analysis_end_date, date(2024, 1, 9))
        self.assertEqual(metadata.longest_lookback, 3)
        self.assertEqual(metadata.warmup_row_count, 3)
        self.assertEqual(metadata.analysis_row_count, 2)
        self.assertEqual(metadata.total_row_count, 5)
        self.assertEqual(metadata.adjustment_method, SPY_ADJUSTMENT_METHOD)
        self.assertEqual(
            metadata.data_sha256,
            calculate_market_data_sha256(result.prices),
        )
        self.assertEqual(
            [value.isoformat() for value in result.prices["date"]],
            ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"],
        )
        self.assertFalse(result.prices.attrs)

    def test_fetched_at_is_normalized_to_utc(self) -> None:
        local_time = datetime(
            2025,
            1,
            10,
            20,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
        result = build_spy_market_data_result(
            sample_yfinance_history(),
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=local_time,
            source=SPY_SOURCE,
            source_version="test-provider-1.0",
        )
        self.assertEqual(result.metadata.fetched_at_utc, FIXED_FETCHED_AT)

    def test_fetched_at_change_does_not_change_data_sha256(self) -> None:
        first = build_spy_market_data_result(
            sample_yfinance_history(),
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=FIXED_FETCHED_AT,
            source=SPY_SOURCE,
            source_version="test-provider-1.0",
        )
        second = build_spy_market_data_result(
            sample_yfinance_history(),
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=FIXED_FETCHED_AT + timedelta(days=30),
            source=SPY_SOURCE,
            source_version="test-provider-2.0",
        )
        self.assertEqual(first.metadata.data_sha256, second.metadata.data_sha256)

    def test_standardized_result_is_directly_consumable_by_engine(self) -> None:
        market_data = build_spy_market_data_result(
            sample_yfinance_history(),
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=FIXED_FETCHED_AT,
            source=SPY_SOURCE,
            source_version="test-provider-1.0",
        )
        targets = moving_average_signal(market_data.prices, 1, 3)
        result = run_strategy_backtest(
            market_data.prices,
            targets,
            BacktestConfig(
                initial_capital=1000.0,
                fee_rate=0.0,
                slippage_rate=0.0,
                start_date=date(2024, 1, 8),
                end_date=date(2024, 1, 9),
            ),
        )
        self.assertEqual(
            [value.isoformat() for value in result.daily["date"]],
            ["2024-01-08", "2024-01-09"],
        )

    def test_user_interval_without_trading_rows_fails(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "field='analysis_date_range'.*actual=0 rows",
        ):
            build_spy_market_data_result(
                sample_yfinance_history(),
                date(2024, 2, 1),
                date(2024, 2, 2),
                3,
                fetched_at_utc=FIXED_FETCHED_AT,
                source=SPY_SOURCE,
                source_version="test-provider-1.0",
            )

    def test_insufficient_warmup_rows_fail(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "field='warmup_row_count'.*actual=1.*requires at least 2",
        ):
            build_spy_market_data_result(
                sample_yfinance_history().iloc[3:],
                date(2024, 1, 8),
                date(2024, 1, 9),
                2,
                fetched_at_utc=FIXED_FETCHED_AT,
                source=SPY_SOURCE,
                source_version="test-provider-1.0",
            )

    def test_yfinance_adapter_requires_unadjusted_and_adjusted_columns(self) -> None:
        history = sample_yfinance_history().drop(columns="Adj Close")
        with self.assertRaisesRegex(ValueError, "field='adj_close'.*actual=<missing>"):
            adapt_yfinance_history(history)

    @patch("quant_lab.data.fetch_spy_raw_yfinance")
    def test_production_entry_uses_only_injected_yfinance_boundary(self, fetch_mock) -> None:
        fetch_mock.return_value = (sample_yfinance_history(), "mock-yfinance-1.0")
        stages: list[str] = []
        result = load_spy_adjusted_daily(
            date(2024, 1, 8),
            date(2024, 1, 9),
            3,
            fetched_at_utc=FIXED_FETCHED_AT,
            stage_callback=stages.append,
        )
        fetch_mock.assert_called_once_with(date(2023, 12, 9), date(2024, 1, 9))
        self.assertEqual(stages, ["market_data_fetch", "market_data_standardize"])
        self.assertEqual(result.metadata.source, SPY_SOURCE)
        self.assertEqual(result.metadata.source_version, "mock-yfinance-1.0")


if __name__ == "__main__":
    unittest.main()
