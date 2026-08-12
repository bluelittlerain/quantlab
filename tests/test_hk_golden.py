from __future__ import annotations

import math
import unittest
from datetime import date, datetime, timezone

import pandas as pd

from quant_lab.market.common.normalized_data import build_adjusted_market_data_result
from quant_lab.market.hk.calendar import hkex_sessions, validate_hk_trading_sessions
from quant_lab.market.hk.costs import calculate_hk_costs
from quant_lab.market.hk.engine import (
    compare_hk_results,
    run_hk_buy_and_hold,
    run_hk_strategy_backtest,
)
from quant_lab.market.hk.models import (
    BoardLotConfig,
    BoardLotSource,
    HKBacktestConfig,
    HKTradingCostConfig,
    TradeSide,
)
from quant_lab.market.hk.symbols import normalize_hk_symbol


def zero_costs(**overrides: float) -> HKTradingCostConfig:
    values = {
        "broker_commission_rate": 0.0,
        "broker_minimum_commission": 0.0,
        "stamp_duty_rate": 0.0,
        "trading_fee_rate": 0.0,
        "transaction_levy_rate": 0.0,
        "afrc_transaction_levy_rate": 0.0,
        "settlement_fee_rate": 0.0,
        "slippage_rate": 0.0,
    }
    values.update(overrides)
    return HKTradingCostConfig(**values)


def board_lot() -> BoardLotConfig:
    return BoardLotConfig(100, BoardLotSource.USER, datetime(2024, 1, 1, tzinfo=timezone.utc))


def simple_prices(*, sell_open: float = 12.0, final_close: float | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "open": [9.0, 10.0, sell_open],
            "close": [9.0, final_close if final_close is not None else 10.0, sell_open],
        }
    )


def config(initial_capital: float = 1_000.0, costs: HKTradingCostConfig | None = None):
    return HKBacktestConfig(
        initial_capital=initial_capital,
        board_lot=board_lot(),
        costs=costs or zero_costs(),
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 4),
    )


class HKGoldenTests(unittest.TestCase):
    def test_hk01_symbol_normalization(self) -> None:
        for raw in ("700", "0700", "0700.HK", "0700.hk"):
            self.assertEqual(normalize_hk_symbol(raw).normalized_symbol, "0700.HK")
        self.assertEqual(normalize_hk_symbol("9988").normalized_symbol, "9988.HK")
        self.assertEqual(normalize_hk_symbol("2800").normalized_symbol, "2800.HK")
        with self.assertRaisesRegex(ValueError, "INVALID_SYMBOL"):
            normalize_hk_symbol("AAPL")

    def test_hk02_board_lot_buy(self) -> None:
        prices = simple_prices()
        targets = pd.Series([1.0, 1.0, 1.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config())
        first = result.daily.iloc[0]
        self.assertEqual(first["action"], "BUY")
        self.assertEqual(first["quantity"], 100)
        self.assertAlmostEqual(first["cash"], 0.0, places=10)
        self.assertEqual(result.trades[0].quantity, 100)

    def test_hk03_insufficient_cash(self) -> None:
        prices = simple_prices()
        targets = pd.Series([1.0, 1.0, 1.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config(999.0))
        self.assertEqual(result.daily.iloc[0]["action"], "INSUFFICIENT_CAPITAL")
        self.assertEqual(result.daily.iloc[0]["quantity"], 0)
        self.assertEqual(result.metrics.final_equity, 999.0)
        self.assertEqual(result.warnings, ("当前资金不足以买入一手。",))

    def test_hk04_commission_rate(self) -> None:
        _, costs = calculate_hk_costs(
            raw_price=10.0,
            quantity=100,
            side=TradeSide.BUY,
            config=zero_costs(broker_commission_rate=0.001),
        )
        self.assertEqual(costs.broker_commission, 1.0)
        self.assertEqual(costs.total_cost, 1.0)

    def test_hk05_minimum_commission(self) -> None:
        _, costs = calculate_hk_costs(
            raw_price=10.0,
            quantity=100,
            side=TradeSide.BUY,
            config=zero_costs(
                broker_commission_rate=0.001,
                broker_minimum_commission=5.0,
            ),
        )
        self.assertEqual(costs.broker_commission, 5.0)

    def test_hk06_stamp_duty_rounds_up_to_hkd(self) -> None:
        _, exact = calculate_hk_costs(
            raw_price=10.0,
            quantity=100,
            side=TradeSide.BUY,
            config=zero_costs(stamp_duty_rate=0.001),
        )
        _, fractional = calculate_hk_costs(
            raw_price=10.01,
            quantity=100,
            side=TradeSide.SELL,
            config=zero_costs(stamp_duty_rate=0.001),
        )
        self.assertEqual(exact.stamp_duty, 1.0)
        self.assertEqual(fractional.stamp_duty, 2.0)

    def test_hk07_statutory_fees_round_each_component(self) -> None:
        _, costs = calculate_hk_costs(
            raw_price=100.0,
            quantity=100,
            side=TradeSide.BUY,
            config=zero_costs(
                trading_fee_rate=0.0000565,
                transaction_levy_rate=0.000027,
                afrc_transaction_levy_rate=0.0000015,
                settlement_fee_rate=0.000042,
            ),
        )
        self.assertEqual(costs.trading_fee, 0.57)
        self.assertEqual(costs.transaction_levy, 0.27)
        self.assertEqual(costs.afrc_transaction_levy, 0.02)
        self.assertEqual(costs.settlement_fee, 0.42)
        self.assertEqual(costs.total_cost, 1.28)

    def test_hk08_slippage(self) -> None:
        execution, costs = calculate_hk_costs(
            raw_price=10.0,
            quantity=100,
            side=TradeSide.BUY,
            config=zero_costs(slippage_rate=0.01),
        )
        self.assertEqual(execution, 10.1)
        self.assertAlmostEqual(costs.slippage_cost, 10.0, places=10)

    def test_hk09_full_profitable_trade(self) -> None:
        prices = simple_prices(sell_open=12.0)
        targets = pd.Series([1.0, 0.0, 0.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config())
        trade = result.trades[0]
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.gross_pnl, 200.0)
        self.assertEqual(trade.net_pnl, 200.0)
        self.assertEqual(result.metrics.final_equity, 1_200.0)
        self.assertAlmostEqual(result.metrics.total_return, 0.2, places=12)
        self.assertEqual(result.metrics.win_rate, 1.0)

    def test_hk10_losing_trade(self) -> None:
        prices = simple_prices(sell_open=8.0)
        targets = pd.Series([1.0, 0.0, 0.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config())
        self.assertEqual(result.trades[0].net_pnl, -200.0)
        self.assertEqual(result.metrics.final_equity, 800.0)
        self.assertEqual(result.metrics.win_rate, 0.0)

    def test_hk11_open_trade_has_no_exit_costs(self) -> None:
        prices = simple_prices(final_close=11.0)
        targets = pd.Series([1.0, 1.0, 1.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config())
        trade = result.trades[0]
        self.assertEqual(trade.status, "OPEN")
        self.assertIsNone(trade.exit_date)
        self.assertIsNone(trade.exit_costs)
        self.assertEqual(trade.net_pnl, 200.0)

    def test_hk12_benchmark_uses_same_initial_capital(self) -> None:
        strategy_prices = simple_prices()
        benchmark_prices = pd.DataFrame(
            {
                "date": strategy_prices["date"],
                "open": [5.0, 5.0, 6.0],
                "close": [5.0, 5.0, 6.0],
            }
        )
        flat = pd.Series([0.0, 0.0, 0.0], index=strategy_prices.index)
        strategy = run_hk_strategy_backtest(strategy_prices, flat, config())
        benchmark = run_hk_buy_and_hold(benchmark_prices, config())
        comparison = compare_hk_results(strategy, benchmark)
        self.assertEqual(strategy.metrics.final_equity, 1_000.0)
        self.assertEqual(benchmark.metrics.final_equity, 1_200.0)
        self.assertAlmostEqual(comparison.benchmark_return, 0.2, places=15)
        self.assertAlmostEqual(comparison.excess_return, -0.2, places=15)

    def test_hk13_adjusted_ohlc_uses_one_split_factor(self) -> None:
        raw = pd.DataFrame(
            {
                "Date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "Open": [100.0, 51.0, 52.0],
                "High": [104.0, 53.0, 54.0],
                "Low": [98.0, 50.0, 51.0],
                "Close": [102.0, 52.0, 53.0],
                "Adj Close": [51.0, 52.0, 53.0],
                "Volume": [1000, 2000, 2100],
            }
        )
        result = build_adjusted_market_data_result(
            symbol="0700.HK",
            raw_history=raw,
            start_date=date(2024, 1, 3),
            end_date=date(2024, 1, 4),
            longest_lookback=1,
            fetched_at_utc=datetime(2024, 1, 5, tzinfo=timezone.utc),
            source="fixture",
            source_version="1",
            adjustment_method="ratio",
        )
        first = result.prices.iloc[0]
        self.assertEqual(first["open"], 50.0)
        self.assertEqual(first["high"], 52.0)
        self.assertEqual(first["low"], 49.0)
        self.assertEqual(first["close"], 51.0)
        self.assertEqual(len(result.metadata.data_sha256), 64)

    def test_hk14_calendar_distinguishes_holidays(self) -> None:
        sessions = hkex_sessions(date(2024, 12, 23), date(2024, 12, 27))
        self.assertEqual(
            sessions,
            (date(2024, 12, 23), date(2024, 12, 24), date(2024, 12, 27)),
        )
        validation = validate_hk_trading_sessions(
            (date(2024, 12, 23), date(2024, 12, 27)),
            start_date=date(2024, 12, 23),
            end_date=date(2024, 12, 27),
        )
        self.assertEqual(validation.missing_expected_sessions, (date(2024, 12, 24),))
        self.assertNotIn(date(2024, 12, 25), validation.missing_expected_sessions)

    def test_hk15_cost_breakdown_conserves_cash(self) -> None:
        costs = zero_costs(broker_commission_rate=0.001)
        prices = simple_prices(sell_open=12.0)
        targets = pd.Series([1.0, 0.0, 0.0], index=prices.index)
        result = run_hk_strategy_backtest(prices, targets, config(1_100.0, costs))
        trade = result.trades[0]
        self.assertAlmostEqual(trade.total_cost, 2.2, places=12)
        self.assertAlmostEqual(trade.net_pnl, 197.8, places=12)
        self.assertAlmostEqual(result.metrics.final_equity, 1_297.8, places=12)
        self.assertAlmostEqual(
            result.metrics.final_equity - result.metrics.initial_equity,
            trade.net_pnl,
            places=12,
        )
        self.assertAlmostEqual(
            trade.gross_pnl - trade.total_cost,
            trade.net_pnl,
            places=12,
        )
        self.assertTrue(math.isfinite(result.metrics.turnover))


if __name__ == "__main__":
    unittest.main()
