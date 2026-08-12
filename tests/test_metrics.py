from __future__ import annotations

import math
import unittest

import pandas as pd
from fixtures import GOLDEN_CASES_BY_ID
from test_engine import ABS_TOL, ENGINE_CASE_IDS, REL_TOL, case_inputs

from quant_lab.backtest import run_strategy_and_benchmark
from quant_lab.metrics import calculate_max_drawdown, calculate_performance_metrics
from quant_lab.models import TradeRecord


class MetricsTests(unittest.TestCase):
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

    def test_g01_to_g12_strategy_metrics_match_static_literals(self) -> None:
        for case_id in ENGINE_CASE_IDS:
            with self.subTest(case_id=case_id):
                case = GOLDEN_CASES_BY_ID[case_id]
                prices, targets, config = case_inputs(case)
                actual = run_strategy_and_benchmark(prices, targets, config).strategy.metrics
                expected = case.expected_summary
                self.assert_close(actual.final_equity, expected.final_equity, case_id)
                self.assert_close(actual.total_return, expected.total_return, case_id)
                self.assert_close(actual.max_drawdown, expected.max_drawdown, case_id)
                self.assertEqual(actual.closed_trade_count, expected.closed_trade_count)
                if expected.win_rate is None:
                    self.assertIsNone(actual.win_rate)
                else:
                    self.assert_close(actual.win_rate, expected.win_rate, case_id)
                self.assert_close(actual.total_fees, expected.total_fees, case_id)
                self.assert_close(actual.total_slippage_cost, expected.total_slippage, case_id)

    def test_g01_to_g12_benchmark_metrics_match_static_literals(self) -> None:
        for case_id in ENGINE_CASE_IDS:
            with self.subTest(case_id=case_id):
                case = GOLDEN_CASES_BY_ID[case_id]
                prices, targets, config = case_inputs(case)
                actual = run_strategy_and_benchmark(prices, targets, config).benchmark.metrics
                expected = case.expected_benchmark
                self.assert_close(actual.final_equity, expected.final_equity, case_id)
                self.assert_close(actual.total_return, expected.total_return, case_id)
                self.assert_close(actual.max_drawdown, expected.max_drawdown, case_id)
                self.assert_close(actual.total_fees, expected.total_fees, case_id)
                self.assert_close(actual.total_slippage_cost, expected.total_slippage, case_id)

    def test_max_drawdown_includes_initial_equity_point(self) -> None:
        actual = calculate_max_drawdown(1000.0, pd.Series([900.0]))
        self.assert_close(actual, -0.1)

    def test_g09_open_profit_does_not_create_a_win_rate(self) -> None:
        case = GOLDEN_CASES_BY_ID["G09"]
        prices, targets, config = case_inputs(case)
        metrics = run_strategy_and_benchmark(prices, targets, config).strategy.metrics
        self.assertEqual(metrics.closed_trade_count, 0)
        self.assertEqual(metrics.open_trade_count, 1)
        self.assertIsNone(metrics.win_rate)

    def test_g06_totals_include_only_actual_fills(self) -> None:
        case = GOLDEN_CASES_BY_ID["G06"]
        prices, targets, config = case_inputs(case)
        result = run_strategy_and_benchmark(prices, targets, config).strategy
        self.assert_close(result.metrics.total_fees, 21.54690716596412)
        self.assert_close(result.metrics.total_slippage_cost, 21.56651308695226)
        self.assertEqual(result.daily["action"].tolist(), ["NONE", "BUY", "SELL"])

    def test_zero_net_profit_is_not_a_winning_trade(self) -> None:
        trade = TradeRecord(
            trade_id=1,
            status="CLOSED",
            entry_date=pd.Timestamp("2024-01-02").date(),
            entry_raw_price=100.0,
            entry_execution_price=100.0,
            quantity=10.0,
            entry_fee=0.0,
            entry_slippage_cost=0.0,
            exit_date=pd.Timestamp("2024-01-03").date(),
            exit_raw_price=100.0,
            exit_execution_price=100.0,
            exit_fee=0.0,
            exit_slippage_cost=0.0,
            mark_date=None,
            mark_price=None,
            holding_days=1,
            gross_pnl=0.0,
            total_fees=0.0,
            total_slippage_cost=0.0,
            net_pnl=0.0,
            net_return=0.0,
        )
        daily = pd.DataFrame({"equity": [1000.0], "fee": [0.0], "slippage_cost": [0.0]})
        metrics = calculate_performance_metrics(1000.0, daily, (trade,))
        self.assertEqual(metrics.closed_trade_count, 1)
        self.assert_close(metrics.win_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
