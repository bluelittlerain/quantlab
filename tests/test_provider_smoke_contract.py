from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from scripts.run_hk_provider_smoke import (
    BOARD_LOTS,
    END_DATE,
    INITIAL_CAPITAL,
    START_DATE,
    START_DATES,
    SYMBOLS,
    _request,
    _summary,
)


class ProviderSmokeContractTests(unittest.TestCase):
    def test_acceptance_configuration_matches_the_product_workflow(self) -> None:
        checked_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(SYMBOLS, ("0700.HK", "9988.HK", "2800.HK"))
        self.assertEqual((START_DATE, END_DATE), (date(2020, 1, 1), date(2024, 12, 31)))
        self.assertEqual(INITIAL_CAPITAL, 100_000.0)
        self.assertEqual(BOARD_LOTS, {"0700.HK": 100, "9988.HK": 100, "2800.HK": 500})
        self.assertEqual(START_DATES["0700.HK"], date(2020, 1, 1))
        self.assertEqual(START_DATES["9988.HK"], date(2020, 4, 1))

        request = _request("0700.HK", checked_at)
        self.assertEqual((request.short_window, request.long_window), (20, 60))
        self.assertEqual(request.start_date, date(2020, 1, 1))
        self.assertEqual(request.board_lot.lot_size, 100)
        self.assertEqual(request.benchmark_board_lot.lot_size, 500)
        self.assertEqual(request.costs.broker_commission_rate, 0.00025)
        self.assertEqual(request.costs.slippage_rate, 0.0005)
        self.assertEqual(_request("9988.HK", checked_at).start_date, date(2020, 4, 1))

    def test_summary_uses_the_hk_metrics_cost_field(self) -> None:
        checked_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        metadata = SimpleNamespace(
            source="fixture",
            source_version="1",
            fetched_at_utc=checked_at,
            actual_start_date=date(2019, 10, 1),
            actual_end_date=date(2024, 12, 31),
            analysis_row_count=1230,
            warmup_row_count=60,
            total_row_count=1290,
            data_sha256="a" * 64,
        )
        strategy_metrics = SimpleNamespace(
            final_equity=101_000.0,
            cagr=0.01,
            max_drawdown=-0.1,
            total_trading_costs=321.5,
            closed_trade_count=3,
        )
        benchmark_metrics = SimpleNamespace(final_equity=102_000.0, cagr=0.02)
        output = SimpleNamespace(
            market_data=SimpleNamespace(metadata=metadata),
            comparison=SimpleNamespace(
                strategy=SimpleNamespace(metrics=strategy_metrics, trades=(1, 2, 3)),
                benchmark=SimpleNamespace(metrics=benchmark_metrics),
            ),
            request=SimpleNamespace(start_date=date(2020, 1, 1)),
            run_id="fixture-run",
        )

        summary = _summary("0700.HK", output)

        self.assertEqual(summary["total_costs"], 321.5)
        self.assertEqual(summary["trade_records"], 3)
        self.assertEqual(summary["analysis_rows"], 1230)


if __name__ == "__main__":
    unittest.main()
