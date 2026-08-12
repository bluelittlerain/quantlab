from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from quant_lab.application.hk_workflow import HKRunOutput, HKRunRequest, run_hk_sma_workflow
from quant_lab.market.hk.models import BoardLotConfig, BoardLotSource, HKTradingCostConfig
from quant_lab.providers.cache import CachedMarketDataProvider
from quant_lab.providers.yahoo_hk import YahooHKProvider

SYMBOLS = ("0700.HK", "9988.HK", "2800.HK")
START_DATE = date(2020, 1, 1)
END_DATE = date(2024, 12, 31)
INITIAL_CAPITAL = 100_000.0
BOARD_LOTS = {"0700.HK": 100, "9988.HK": 100, "2800.HK": 500}
START_DATES = {**dict.fromkeys(SYMBOLS, START_DATE), "9988.HK": date(2020, 4, 1)}


def _request(symbol: str, checked_at: datetime) -> HKRunRequest:
    board_lot = BoardLotConfig(
        lot_size=BOARD_LOTS[symbol],
        source=BoardLotSource.USER,
        verified_at=checked_at,
        confirmed=True,
    )
    benchmark_board_lot = BoardLotConfig(
        lot_size=BOARD_LOTS["2800.HK"],
        source=BoardLotSource.USER,
        verified_at=checked_at,
        confirmed=True,
    )
    costs = HKTradingCostConfig()
    return HKRunRequest(
        symbol=symbol,
        benchmark_symbol="2800.HK",
        start_date=START_DATES[symbol],
        end_date=END_DATE,
        short_window=20,
        long_window=60,
        initial_capital=INITIAL_CAPITAL,
        board_lot=board_lot,
        benchmark_board_lot=benchmark_board_lot,
        costs=costs,
        benchmark_costs=costs,
    )


def _summary(symbol: str, output: HKRunOutput) -> dict[str, object]:
    metadata = output.market_data.metadata
    strategy = output.comparison.strategy
    benchmark = output.comparison.benchmark
    return {
        "symbol": symbol,
        "provider": metadata.source,
        "provider_version": metadata.source_version,
        "fetched_at_utc": metadata.fetched_at_utc.isoformat(),
        "actual_start_date": metadata.actual_start_date.isoformat(),
        "actual_end_date": metadata.actual_end_date.isoformat(),
        "analysis_rows": metadata.analysis_row_count,
        "warmup_rows": metadata.warmup_row_count,
        "total_rows": metadata.total_row_count,
        "data_sha256": metadata.data_sha256,
        "run_id": output.run_id,
        "requested_start_date": output.request.start_date.isoformat(),
        "board_lot": BOARD_LOTS[symbol],
        "final_equity": strategy.metrics.final_equity,
        "cagr": strategy.metrics.cagr,
        "max_drawdown": strategy.metrics.max_drawdown,
        "benchmark_final_equity": benchmark.metrics.final_equity,
        "benchmark_cagr": benchmark.metrics.cagr,
        "total_costs": strategy.metrics.total_trading_costs,
        "closed_trades": strategy.metrics.closed_trade_count,
        "trade_records": len(strategy.trades),
    }


def run_real_provider_smoke(cache_directory: Path) -> dict[str, object]:
    """Exercise real Yahoo HK data without promoting live values to golden expectations."""
    checked_at = datetime.now(timezone.utc)
    provider = CachedMarketDataProvider(YahooHKProvider(), cache_directory=cache_directory)
    results: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        output = run_hk_sma_workflow(
            _request(symbol, checked_at),
            provider=provider,
            created_at_utc=checked_at,
            force_refresh=True,
        )
        results.append(_summary(symbol, output))
    return {
        "status": "ok",
        "golden_expectation": False,
        "analysis_period": {
            symbol: [START_DATES[symbol].isoformat(), END_DATE.isoformat()] for symbol in SYMBOLS
        },
        "initial_capital": INITIAL_CAPITAL,
        "board_lots": BOARD_LOTS,
        "lot_size_note": "explicit acceptance values; not inferred from Yahoo metadata",
        "cost_note": "default HK statutory, broker commission, minimum commission, and slippage",
        "listing_note": "9988.HK starts on 2020-04-01 so its post-IPO history supplies 60 warmup rows",
        "results": results,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="quantlab-hk-provider-smoke-") as temporary:
        result = run_real_provider_smoke(Path(temporary))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
