from __future__ import annotations

import math
import unittest
from datetime import date

import pandas as pd
from fixtures import GOLDEN_CASES_BY_ID, GoldenCase

from quant_lab.backtest import (
    run_buy_and_hold_benchmark,
    run_strategy_and_benchmark,
    run_strategy_backtest,
)
from quant_lab.models import BacktestConfig, BacktestResult
from quant_lab.strategies import moving_average_signal

REL_TOL = 1e-12
ABS_TOL = 1e-9
ENGINE_CASE_IDS = tuple(f"G{number:02d}" for number in range(1, 13))


def case_inputs(case: GoldenCase) -> tuple[pd.DataFrame, pd.Series, BacktestConfig]:
    prices = pd.DataFrame(
        [
            {
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in case.bars
        ]
    )
    targets = pd.Series(
        [bar.target_position for bar in case.bars],
        index=prices.index,
        name="target_position",
        dtype=float,
    )
    user_bars = [bar for bar in case.bars if not bar.is_warmup]
    config = BacktestConfig(
        initial_capital=case.initial_capital,
        fee_rate=case.fee_rate,
        slippage_rate=case.slippage_rate,
        start_date=date.fromisoformat(user_bars[0].date),
        end_date=date.fromisoformat(user_bars[-1].date),
    )
    return prices, targets, config


class StrictFloatAssertions(unittest.TestCase):
    def assert_close(
        self,
        actual: float,
        expected: float,
        context: str = "",
    ) -> None:
        self.assertTrue(
            math.isclose(
                float(actual),
                float(expected),
                rel_tol=REL_TOL,
                abs_tol=ABS_TOL,
            ),
            f"{context}: actual={actual!r}, expected={expected!r}, "
            f"rel_tol={REL_TOL}, abs_tol={ABS_TOL}",
        )

    def assert_optional_close(
        self,
        actual: float | None,
        expected: float | None,
        context: str = "",
    ) -> None:
        if expected is None:
            self.assertIsNone(actual, context)
        else:
            self.assertIsNotNone(actual, context)
            self.assert_close(float(actual), expected, context)


class GoldenEngineTests(StrictFloatAssertions):
    def assert_case(self, case_id: str) -> None:
        case = GOLDEN_CASES_BY_ID[case_id]
        prices, targets, config = case_inputs(case)
        comparison = run_strategy_and_benchmark(prices, targets, config)
        self.assert_strategy(case, comparison.strategy)
        self.assert_benchmark(case, comparison.benchmark)

        if case_id == "G10":
            pd.testing.assert_frame_equal(
                comparison.strategy.daily,
                comparison.benchmark.daily,
                check_exact=False,
                rtol=REL_TOL,
                atol=ABS_TOL,
            )

    def assert_strategy(self, case: GoldenCase, result: BacktestResult) -> None:
        daily = result.daily
        self.assertEqual(len(daily), len(case.expected_daily), case.case_id)
        bars_by_date = {bar.date: bar for bar in case.bars}
        expected_columns = {
            "date",
            "target_position",
            "pending_target",
            "action",
            "raw_open",
            "execution_price",
            "trade_quantity",
            "cash",
            "quantity",
            "fee",
            "slippage_cost",
            "close",
            "equity",
        }
        self.assertTrue(expected_columns.issubset(daily.columns), case.case_id)

        for row_index, expected in enumerate(case.expected_daily):
            actual = daily.iloc[row_index]
            bar = bars_by_date[expected.date]
            context = f"{case.case_id} daily {expected.date}"
            self.assertEqual(actual["date"].isoformat(), expected.date, context)
            self.assert_close(actual["target_position"], bar.target_position, f"{context} target")
            self.assert_close(actual["pending_target"], expected.prior_target, f"{context} pending")
            self.assertEqual(actual["action"], expected.action, context)
            self.assert_close(actual["raw_open"], bar.open, f"{context} raw open")
            if expected.fill_price is None:
                self.assertTrue(
                    math.isnan(float(actual["execution_price"])),
                    f"{context} execution price must be NaN",
                )
            else:
                self.assert_close(
                    actual["execution_price"],
                    expected.fill_price,
                    f"{context} execution price",
                )
            self.assert_close(
                actual["trade_quantity"],
                expected.trade_quantity,
                f"{context} trade quantity",
            )
            self.assert_close(actual["cash"], expected.cash, f"{context} cash")
            self.assert_close(actual["quantity"], expected.holdings, f"{context} holdings")
            self.assert_close(actual["fee"], expected.fee, f"{context} fee")
            self.assert_close(actual["slippage_cost"], expected.slippage, f"{context} slippage")
            self.assert_close(actual["close"], bar.close, f"{context} close")
            self.assert_close(actual["equity"], expected.equity, f"{context} equity")

        warmup_dates = {bar.date for bar in case.bars if bar.is_warmup}
        actual_dates = {value.isoformat() for value in daily["date"]}
        self.assertTrue(warmup_dates.isdisjoint(actual_dates), case.case_id)

        self.assertEqual(len(result.trades), len(case.expected_trades), case.case_id)
        for expected_id, (actual, expected) in enumerate(
            zip(result.trades, case.expected_trades), start=1
        ):
            context = f"{case.case_id} trade {expected_id}"
            self.assertEqual(actual.trade_id, expected_id, context)
            self.assertEqual(actual.status, expected.status, context)
            self.assertEqual(actual.entry_date.isoformat(), expected.entry_date, context)
            self.assert_close(
                actual.entry_raw_price,
                expected.entry_reference_open,
                f"{context} entry raw",
            )
            self.assert_close(
                actual.entry_execution_price,
                expected.entry_fill_price,
                f"{context} entry execution",
            )
            self.assert_close(actual.quantity, expected.quantity, f"{context} quantity")
            self.assert_close(actual.entry_fee, expected.entry_fee, f"{context} entry fee")
            self.assert_close(
                actual.entry_slippage_cost,
                expected.entry_slippage,
                f"{context} entry slippage",
            )
            self.assertEqual(
                actual.exit_date.isoformat() if actual.exit_date else None,
                expected.exit_date,
                context,
            )
            self.assert_optional_close(
                actual.exit_raw_price, expected.exit_reference_open, f"{context} exit raw"
            )
            self.assert_optional_close(
                actual.exit_execution_price,
                expected.exit_fill_price,
                f"{context} exit execution",
            )
            self.assert_optional_close(actual.exit_fee, expected.exit_fee, f"{context} exit fee")
            self.assert_optional_close(
                actual.exit_slippage_cost,
                expected.exit_slippage,
                f"{context} exit slippage",
            )
            self.assertEqual(
                actual.mark_date.isoformat() if actual.mark_date else None,
                expected.mark_date,
                context,
            )
            self.assert_optional_close(
                actual.mark_price, expected.mark_price, f"{context} mark price"
            )
            self.assertEqual(actual.holding_days, expected.holding_days, context)
            self.assert_close(actual.gross_pnl, expected.gross_pnl, f"{context} gross PnL")
            self.assert_close(actual.total_fees, expected.total_fees, f"{context} total fees")
            self.assert_close(
                actual.total_slippage_cost,
                expected.total_slippage,
                f"{context} total slippage",
            )
            self.assert_close(actual.net_pnl, expected.net_pnl, f"{context} net PnL")
            self.assert_close(actual.net_return, expected.net_return, f"{context} net return")

        expected = case.expected_summary
        metrics = result.metrics
        self.assert_close(metrics.initial_equity, case.initial_capital, case.case_id)
        self.assert_close(metrics.final_equity, expected.final_equity, case.case_id)
        self.assert_close(metrics.total_return, expected.total_return, case.case_id)
        self.assert_close(metrics.max_drawdown, expected.max_drawdown, case.case_id)
        self.assertEqual(metrics.closed_trade_count, expected.closed_trade_count, case.case_id)
        self.assertEqual(
            metrics.open_trade_count,
            sum(trade.status == "OPEN" for trade in case.expected_trades),
            case.case_id,
        )
        self.assert_optional_close(metrics.win_rate, expected.win_rate, case.case_id)
        self.assert_close(metrics.total_fees, expected.total_fees, case.case_id)
        self.assert_close(metrics.total_slippage_cost, expected.total_slippage, case.case_id)

    def assert_benchmark(self, case: GoldenCase, result: BacktestResult) -> None:
        expected = case.expected_benchmark
        self.assertEqual(len(result.daily), len(expected.daily_equity), case.case_id)
        for row_index, ((expected_date, expected_equity), (_, actual)) in enumerate(
            zip(expected.daily_equity, result.daily.iterrows())
        ):
            context = f"{case.case_id} benchmark {expected_date}"
            self.assertEqual(actual["date"].isoformat(), expected_date, context)
            self.assertEqual(actual["action"], "BUY" if row_index == 0 else "NONE")
            self.assert_close(actual["target_position"], 1.0, context)
            self.assert_close(actual["pending_target"], 1.0, context)
            self.assert_close(actual["cash"], 0.0, context)
            self.assert_close(actual["quantity"], expected.quantity, context)
            self.assert_close(actual["equity"], expected_equity, context)
            if row_index == 0:
                self.assert_close(actual["raw_open"], expected.entry_reference_open, context)
                self.assert_close(actual["execution_price"], expected.entry_fill_price, context)
                self.assert_close(actual["trade_quantity"], expected.quantity, context)
                self.assert_close(actual["fee"], expected.entry_fee, context)
                self.assert_close(actual["slippage_cost"], expected.entry_slippage, context)
            else:
                self.assertTrue(math.isnan(float(actual["execution_price"])), context)
                self.assert_close(actual["trade_quantity"], 0.0, context)
                self.assert_close(actual["fee"], 0.0, context)
                self.assert_close(actual["slippage_cost"], 0.0, context)

        self.assertEqual(len(result.trades), 1, case.case_id)
        trade = result.trades[0]
        self.assertEqual(trade.status, "OPEN", case.case_id)
        self.assertEqual(trade.entry_date.isoformat(), expected.entry_date, case.case_id)
        self.assert_close(trade.entry_raw_price, expected.entry_reference_open, case.case_id)
        self.assert_close(trade.entry_execution_price, expected.entry_fill_price, case.case_id)
        self.assert_close(trade.quantity, expected.quantity, case.case_id)
        self.assert_close(trade.entry_fee, expected.entry_fee, case.case_id)
        self.assert_close(trade.entry_slippage_cost, expected.entry_slippage, case.case_id)
        self.assertIsNone(trade.exit_date, case.case_id)
        self.assertIsNone(trade.exit_execution_price, case.case_id)
        self.assertIsNone(trade.exit_fee, case.case_id)
        self.assertIsNone(trade.exit_slippage_cost, case.case_id)

        metrics = result.metrics
        self.assert_close(metrics.final_equity, expected.final_equity, case.case_id)
        self.assert_close(metrics.total_return, expected.total_return, case.case_id)
        self.assert_close(metrics.max_drawdown, expected.max_drawdown, case.case_id)
        self.assertEqual(metrics.closed_trade_count, 0, case.case_id)
        self.assertEqual(metrics.open_trade_count, 1, case.case_id)
        self.assertIsNone(metrics.win_rate, case.case_id)
        self.assert_close(metrics.total_fees, expected.total_fees, case.case_id)
        self.assert_close(metrics.total_slippage_cost, expected.total_slippage, case.case_id)

    def test_g01_always_flat(self) -> None:
        self.assert_case("G01")

    def test_g02_open_until_end(self) -> None:
        self.assert_case("G02")

    def test_g03_one_profitable_closed_trade(self) -> None:
        self.assert_case("G03")

    def test_g04_one_losing_closed_trade(self) -> None:
        self.assert_case("G04")

    def test_g05_multiple_closed_trades(self) -> None:
        self.assert_case("G05")

    def test_g06_fees_and_slippage(self) -> None:
        self.assert_case("G06")

    def test_g07_peak_to_trough_drawdown(self) -> None:
        self.assert_case("G07")

    def test_g08_open_trade_has_no_exit_costs(self) -> None:
        self.assert_case("G08")

    def test_g09_no_closed_trade_win_rate_is_none(self) -> None:
        self.assert_case("G09")

    def test_g10_strategy_and_benchmark_share_cost_basis(self) -> None:
        self.assert_case("G10")

    def test_g11_equal_moving_averages_stay_flat(self) -> None:
        self.assert_case("G11")

    def test_g12_warmup_signal_executes_on_first_user_open(self) -> None:
        self.assert_case("G12")


class StrategySignalTests(StrictFloatAssertions):
    def test_g11_and_g12_targets_are_unshifted_and_strict(self) -> None:
        for case_id in ("G11", "G12"):
            with self.subTest(case_id=case_id):
                case = GOLDEN_CASES_BY_ID[case_id]
                prices, _, _ = case_inputs(case)
                actual = moving_average_signal(
                    prices,
                    short_window=case.short_window,
                    long_window=case.long_window,
                )
                expected = [bar.target_position for bar in case.bars]
                self.assertEqual(actual.tolist(), expected)
                self.assertTrue(actual.index.equals(prices.index))


class EngineValidationTests(StrictFloatAssertions):
    @staticmethod
    def simple_inputs() -> tuple[pd.DataFrame, pd.Series]:
        prices = pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "open": [100.0, 100.0],
                "close": [100.0, 110.0],
            }
        )
        return prices, pd.Series([0.0, 1.0], index=prices.index)

    def test_dates_must_be_strictly_ascending(self) -> None:
        prices, targets = self.simple_inputs()
        prices = prices.iloc[::-1].reset_index(drop=True)
        targets = targets.reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "strictly ascending"):
            run_strategy_backtest(prices, targets)

    def test_dates_must_be_unique(self) -> None:
        prices, targets = self.simple_inputs()
        prices.loc[1, "date"] = prices.loc[0, "date"]
        with self.assertRaisesRegex(ValueError, "unique"):
            run_strategy_backtest(prices, targets)

    def test_target_must_be_binary(self) -> None:
        prices, targets = self.simple_inputs()
        targets.iloc[1] = 0.5
        with self.assertRaisesRegex(ValueError, "only 0 or 1"):
            run_strategy_backtest(prices, targets)

    def test_target_index_must_exactly_match_prices(self) -> None:
        prices, _ = self.simple_inputs()
        targets = pd.Series([0.0, 1.0], index=[1, 2])
        with self.assertRaisesRegex(ValueError, "index must exactly match"):
            run_strategy_backtest(prices, targets)

    def test_user_interval_must_contain_data(self) -> None:
        prices, targets = self.simple_inputs()
        config = BacktestConfig(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        with self.assertRaisesRegex(ValueError, "contains no price data"):
            run_strategy_backtest(prices, targets, config)

    def test_negative_cost_rates_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "fee_rate"):
            BacktestConfig(fee_rate=-0.001)
        with self.assertRaisesRegex(ValueError, "slippage_rate"):
            BacktestConfig(slippage_rate=-0.001)

    def test_invalid_capital_and_date_range_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "initial_capital"):
            BacktestConfig(initial_capital=0.0)
        with self.assertRaisesRegex(ValueError, "start_date"):
            BacktestConfig(
                start_date=date(2024, 1, 3),
                end_date=date(2024, 1, 2),
            )

    def test_last_day_signal_has_no_future_fill(self) -> None:
        prices, targets = self.simple_inputs()
        result = run_strategy_backtest(
            prices,
            targets,
            BacktestConfig(initial_capital=1000.0, fee_rate=0.0),
        )
        self.assertEqual(result.daily["action"].tolist(), ["NONE", "NONE"])
        self.assertEqual(result.trades, ())
        self.assert_close(result.metrics.final_equity, 1000.0)

    def test_fee_reservation_prevents_materially_negative_cash(self) -> None:
        case = GOLDEN_CASES_BY_ID["G06"]
        prices, targets, config = case_inputs(case)
        result = run_strategy_backtest(prices, targets, config)
        buy_cash = float(result.daily.loc[result.daily["action"] == "BUY", "cash"].iloc[0])
        self.assertGreaterEqual(buy_cash, 0.0)
        self.assert_close(buy_cash, 0.0)

    def test_benchmark_first_bar_buy_is_explicit(self) -> None:
        prices, _ = self.simple_inputs()
        result = run_buy_and_hold_benchmark(
            prices,
            BacktestConfig(initial_capital=1000.0, fee_rate=0.0),
        )
        self.assertEqual(result.daily["action"].tolist(), ["BUY", "NONE"])
        self.assertEqual(result.trades[0].entry_date, date(2024, 1, 2))


if __name__ == "__main__":
    unittest.main()
