from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fixtures import GOLDEN_CASES_BY_ID

from quant_lab.backtest import run_strategy_and_benchmark
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.models import (
    BacktestConfig,
    BacktestReportView,
    MarketDataMetadata,
    MarketDataResult,
)
from quant_lab.presentation import build_report_view, calculate_run_id
from quant_lab.report import (
    TRADES_CSV_COLUMNS,
    render_html_report,
    render_run_manifest,
    render_trades_csv,
    write_report_bundle,
)

FIXED_GENERATED_AT = datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc)
FIXED_FETCHED_AT = datetime(2025, 1, 14, 20, 0, tzinfo=timezone.utc)
SOFTWARE_VERSION = "0.1.0-dev"
STRATEGY_NAME = "SMA crossover"
SHORT_WINDOW = 20
LONG_WINDOW = 60


def build_fixed_report_inputs(
    case_id: str = "G06",
    *,
    analysis_limit: int | None = None,
) -> tuple[MarketDataResult, object, BacktestConfig]:
    """Build an offline report input while preserving each golden case's analysis bars."""
    case = GOLDEN_CASES_BY_ID[case_id]
    user_bars = [bar for bar in case.bars if not bar.is_warmup]
    if analysis_limit is not None:
        user_bars = user_bars[:analysis_limit]
    if not user_bars:
        raise ValueError("report fixture requires at least one analysis bar")
    analysis_start = date.fromisoformat(user_bars[0].date)
    analysis_end = date.fromisoformat(user_bars[-1].date)
    warmup_dates = [
        value.date()
        for value in pd.bdate_range(
            end=pd.Timestamp(analysis_start) - pd.offsets.BDay(1),
            periods=LONG_WINDOW,
        )
    ]
    anchor = user_bars[0]
    warmup_rows = [
        {
            "date": warmup_date,
            "open": anchor.open,
            "high": anchor.open,
            "low": anchor.open,
            "close": anchor.open,
            "volume": 1000.0,
        }
        for warmup_date in warmup_dates
    ]
    analysis_rows = [
        {
            "date": date.fromisoformat(bar.date),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in user_bars
    ]
    prices = pd.DataFrame(warmup_rows + analysis_rows)
    targets = pd.Series(
        [0.0] * LONG_WINDOW + [bar.target_position for bar in user_bars],
        index=prices.index,
        name="target_position",
        dtype=float,
    )
    config = BacktestConfig(
        initial_capital=case.initial_capital,
        fee_rate=case.fee_rate,
        slippage_rate=case.slippage_rate,
        start_date=analysis_start,
        end_date=analysis_end,
    )
    comparison = run_strategy_and_benchmark(prices, targets, config)
    metadata = MarketDataMetadata(
        symbol="SPY",
        source="fixed-offline-fixture",
        source_version="fixture-v1",
        fetched_at_utc=FIXED_FETCHED_AT,
        requested_start_date=analysis_start,
        requested_end_date=analysis_end,
        actual_start_date=warmup_dates[0],
        actual_end_date=analysis_end,
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        longest_lookback=LONG_WINDOW,
        warmup_row_count=LONG_WINDOW,
        analysis_row_count=len(analysis_rows),
        total_row_count=len(prices),
        adjustment_method="same-day adjusted OHLC factor; dividends not booked separately",
        data_sha256=calculate_market_data_sha256(prices),
    )
    return MarketDataResult(prices=prices, metadata=metadata), comparison, config


def build_fixed_view(
    case_id: str = "G06",
    *,
    analysis_limit: int | None = None,
    generated_at_utc: datetime = FIXED_GENERATED_AT,
    strategy_name: str = STRATEGY_NAME,
    short_window: int = SHORT_WINDOW,
    long_window: int = LONG_WINDOW,
    software_version: str = SOFTWARE_VERSION,
) -> BacktestReportView:
    market_data, comparison, config = build_fixed_report_inputs(
        case_id,
        analysis_limit=analysis_limit,
    )
    return build_report_view(
        market_data,
        comparison,
        config=config,
        strategy_name=strategy_name,
        short_window=short_window,
        long_window=long_window,
        software_version=software_version,
        generated_at_utc=generated_at_utc,
    )


def metrics_by_key(view: BacktestReportView, scope: str) -> dict[str, object]:
    metrics = view.strategy_metrics if scope == "strategy" else view.benchmark_metrics
    return {metric.key: metric for metric in metrics}


class PresentationModelTests(unittest.TestCase):
    def test_g06_exact_results_enter_the_view_without_recalculation(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs("G06")
        view = build_report_view(
            market_data,
            comparison,
            config=config,
            strategy_name=STRATEGY_NAME,
            short_window=SHORT_WINDOW,
            long_window=LONG_WINDOW,
            software_version=SOFTWARE_VERSION,
            generated_at_utc=FIXED_GENERATED_AT,
        )
        strategy = metrics_by_key(view, "strategy")
        self.assertAlmostEqual(strategy["final_equity"].raw_value, 1152.9457896285, places=9)
        self.assertAlmostEqual(strategy["total_return"].raw_value, 0.152945789628, places=12)
        self.assertAlmostEqual(strategy["total_fees"].raw_value, 21.5469071660, places=9)
        self.assertAlmostEqual(
            strategy["total_slippage_cost"].raw_value,
            21.5665130870,
            places=9,
        )
        self.assertEqual(
            [row.strategy_equity for row in view.equity_rows],
            comparison.strategy.daily["equity"].tolist(),
        )
        self.assertEqual(len(view.strategy_trades), len(comparison.strategy.trades))

    def test_view_builder_does_not_call_backtest_entrypoints(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
        with patch(
            "quant_lab.backtest.run_strategy_and_benchmark",
            side_effect=AssertionError("report layer reran the engine"),
        ):
            view = build_report_view(
                market_data,
                comparison,
                config=config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )
        self.assertEqual(view.run_metadata.symbol, "SPY")

    def test_run_id_is_deterministic_and_excludes_generation_time(self) -> None:
        first = build_fixed_view()
        second = build_fixed_view(generated_at_utc=FIXED_GENERATED_AT + timedelta(days=30))
        self.assertEqual(first.run_metadata.run_id, second.run_metadata.run_id)
        self.assertNotEqual(
            first.run_metadata.generated_at_display,
            second.run_metadata.generated_at_display,
        )

    def test_run_id_changes_for_hash_cost_and_strategy_parameter(self) -> None:
        market_data, _, config = build_fixed_report_inputs()
        base = calculate_run_id(
            market_data.metadata,
            config,
            strategy_name=STRATEGY_NAME,
            short_window=SHORT_WINDOW,
            long_window=LONG_WINDOW,
            software_version=SOFTWARE_VERSION,
        )
        variants = (
            calculate_run_id(
                replace(market_data.metadata, data_sha256="b" * 64),
                config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
            ),
            calculate_run_id(
                market_data.metadata,
                replace(config, fee_rate=0.02),
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
            ),
            calculate_run_id(
                market_data.metadata,
                config,
                strategy_name=STRATEGY_NAME,
                short_window=10,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
            ),
        )
        self.assertEqual(len(set((base, *variants))), 4)
        self.assertRegex(base, r"^[0-9a-f]{16}$")

    def test_none_win_rate_keeps_raw_none_and_displays_na(self) -> None:
        view = build_fixed_view("G08")
        win_rate = metrics_by_key(view, "strategy")["win_rate"]
        self.assertIsNone(win_rate.raw_value)
        self.assertEqual(win_rate.display_value, "N/A")

    def test_input_consistency_checks_reject_date_and_equity_mismatch(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
        with self.assertRaisesRegex(ValueError, "start_date"):
            build_report_view(
                market_data,
                comparison,
                config=replace(config, start_date=config.start_date - timedelta(days=1)),
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )
        invalid_strategy = replace(
            comparison.strategy,
            daily=comparison.strategy.daily.iloc[:-1].copy(),
        )
        with self.assertRaisesRegex(ValueError, "row count"):
            build_report_view(
                market_data,
                replace(comparison, strategy=invalid_strategy),
                config=config,
                strategy_name=STRATEGY_NAME,
                short_window=SHORT_WINDOW,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
            )


class ReportRendererTests(unittest.TestCase):
    def test_html_contains_every_required_section_and_no_remote_resource(self) -> None:
        html = render_html_report(build_fixed_view())
        for heading in (
            "运行与数据",
            "核心指标",
            "净值对比",
            "策略交易账本",
            "回测规则摘要",
            "已知限制与免责声明",
        ):
            self.assertIn(heading, html)
        self.assertNotIn("http://", html.lower())
        self.assertNotIn("https://", html.lower())
        self.assertNotIn("<script", html.lower())
        self.assertNotRegex(html, r"[A-Za-z]:\\")
        self.assertIn("<style>", html)
        self.assertIn("<svg", html)

    def test_html_escapes_strategy_name(self) -> None:
        html = render_html_report(build_fixed_view(strategy_name='<script>alert("x")</script>'))
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", html)

    def test_chart_has_aligned_series_and_analysis_only_dates(self) -> None:
        view = build_fixed_view()
        html = render_html_report(view)
        self.assertIn(f'data-point-count="{len(view.equity_rows)}"', html)
        self.assertEqual(len(re.findall(r'data-series="(?:strategy|benchmark)"', html)), 2)
        self.assertIn(
            f'data-start-date="{view.market_data.analysis_start_date.isoformat()}"',
            html,
        )
        self.assertIn(
            f'data-end-date="{view.market_data.analysis_end_date.isoformat()}"',
            html,
        )
        svg = re.search(r"<svg class=\"equity-chart\".*?</svg>", html, re.DOTALL)
        self.assertIsNotNone(svg)
        self.assertNotIn(
            view.market_data.actual_start_date.isoformat(),
            svg.group(0),
        )

    def test_single_analysis_day_chart_is_explicit_and_deterministic(self) -> None:
        view = build_fixed_view("G01", analysis_limit=1)
        html = render_html_report(view)
        self.assertEqual(len(view.equity_rows), 1)
        self.assertIn('data-point-count="1"', html)
        self.assertIn('data-start-date="2024-01-02"', html)
        self.assertIn('data-end-date="2024-01-02"', html)

    def test_csv_has_fixed_schema_and_exact_strategy_trade_values(self) -> None:
        view = build_fixed_view()
        rows = list(csv.DictReader(io.StringIO(render_trades_csv(view))))
        self.assertEqual(tuple(rows[0]), TRADES_CSV_COLUMNS)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["run_id"], view.run_metadata.run_id)
        self.assertEqual(row["status"], "CLOSED")
        self.assertEqual(row["entry_date"], "2024-06-04")
        self.assertEqual(row["entry_raw_price"], "100.0000000000")
        self.assertEqual(row["entry_execution_price"], "101.0000000000")
        self.assertEqual(row["quantity"], "9.8029604941")
        self.assertEqual(row["net_return"], "0.1529457896")
        self.assertNotIn("%", row["net_return"])
        self.assertNotIn(",", row["entry_raw_price"])

    def test_open_trade_csv_leaves_all_exit_fields_empty(self) -> None:
        row = next(csv.DictReader(io.StringIO(render_trades_csv(build_fixed_view("G08")))))
        self.assertEqual(row["status"], "OPEN")
        for field in (
            "exit_date",
            "exit_raw_price",
            "exit_execution_price",
            "exit_fee",
            "exit_slippage_cost",
        ):
            self.assertEqual(row[field], "", field)
        self.assertEqual(row["mark_date"], "2024-08-05")

    def test_zero_trade_csv_is_header_only_without_synthetic_row(self) -> None:
        csv_text = render_trades_csv(build_fixed_view("G01"))
        self.assertEqual(list(csv.DictReader(io.StringIO(csv_text))), [])
        self.assertEqual(tuple(csv_text.splitlines()[0].split(",")), TRADES_CSV_COLUMNS)

    def test_write_bundle_writes_exact_renderer_output(self) -> None:
        view = build_fixed_view()
        with tempfile.TemporaryDirectory() as directory:
            artifacts = write_report_bundle(view, Path(directory))
            self.assertEqual(artifacts.run_id, view.run_metadata.run_id)
            self.assertEqual(
                artifacts.html_path.read_text(encoding="utf-8"),
                render_html_report(view),
            )
            self.assertEqual(
                artifacts.csv_path.read_text(encoding="utf-8"),
                render_trades_csv(view),
            )
            self.assertEqual(
                artifacts.manifest_path.read_text(encoding="utf-8"),
                render_run_manifest(view),
            )
            self.assertIn(view.run_metadata.run_id, artifacts.html_path.name)
            self.assertIn(view.run_metadata.run_id, artifacts.csv_path.name)
            self.assertIn(view.run_metadata.run_id, artifacts.manifest_path.name)
            self.assertEqual(artifacts.html_filename, artifacts.html_path.name)
            self.assertEqual(artifacts.csv_filename, artifacts.csv_path.name)
            self.assertEqual(
                artifacts.manifest_filename,
                artifacts.manifest_path.name,
            )


class RunManifestTests(unittest.TestCase):
    def test_manifest_contains_fixed_required_metadata(self) -> None:
        view = build_fixed_view()
        manifest = json.loads(render_run_manifest(view))
        expected = {
            "schema_version": "1.0",
            "run_id": view.run_metadata.run_id,
            "software_version": view.run_metadata.software_version,
            "generated_at_utc": view.run_metadata.generated_at_display,
            "symbol": view.run_metadata.symbol,
            "strategy_name": view.run_metadata.strategy_name,
            "short_window": view.run_metadata.short_window,
            "long_window": view.run_metadata.long_window,
            "requested_start_date": view.market_data.requested_start_date.isoformat(),
            "requested_end_date": view.market_data.requested_end_date.isoformat(),
            "actual_start_date": view.market_data.actual_start_date.isoformat(),
            "actual_end_date": view.market_data.actual_end_date.isoformat(),
            "analysis_start_date": view.market_data.analysis_start_date.isoformat(),
            "analysis_end_date": view.market_data.analysis_end_date.isoformat(),
            "initial_capital": view.config.initial_capital,
            "fee_rate": view.config.fee_rate,
            "slippage_rate": view.config.slippage_rate,
            "data_source": view.market_data.source,
            "adjustment_method": view.market_data.adjustment_method,
            "data_sha256": view.market_data.data_sha256,
            "strategy_trade_count": view.strategy_trade_count,
            "strategy_open_trade_count": view.strategy_open_trade_count,
            "html_filename": view.html_filename,
            "csv_filename": view.csv_filename,
        }
        for key, value in expected.items():
            self.assertEqual(manifest[key], value, key)

    def test_zero_trade_manifest_is_complete_while_csv_is_header_only(self) -> None:
        view = build_fixed_view("G01")
        csv_text = render_trades_csv(view)
        manifest = json.loads(render_run_manifest(view))
        self.assertEqual(len(csv_text.splitlines()), 1)
        self.assertEqual(manifest["run_id"], view.run_metadata.run_id)
        self.assertEqual(manifest["strategy_trade_count"], 0)
        self.assertEqual(manifest["strategy_open_trade_count"], 0)
        self.assertEqual(manifest["html_filename"], view.html_filename)
        self.assertEqual(manifest["csv_filename"], view.csv_filename)
        self.assertEqual(manifest["manifest_filename"], view.manifest_filename)

    def test_manifest_is_utf8_lf_terminated_and_deterministic(self) -> None:
        view = build_fixed_view()
        first = render_run_manifest(view)
        second = render_run_manifest(view)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn("\r", first)
        self.assertEqual(first.encode("utf-8").decode("utf-8"), first)

    def test_manifest_has_no_paths_nonfinite_values_or_private_payloads(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
        sentinel = "SECRET_PROVIDER_PAYLOAD_f592"
        market_data.prices.attrs["provider_response"] = sentinel
        view = build_report_view(
            market_data,
            comparison,
            config=config,
            strategy_name=STRATEGY_NAME,
            short_window=SHORT_WINDOW,
            long_window=LONG_WINDOW,
            software_version=SOFTWARE_VERSION,
            generated_at_utc=FIXED_GENERATED_AT,
        )
        rendered = render_run_manifest(view)
        json.loads(rendered, parse_constant=lambda value: self.fail(value))
        self.assertNotRegex(rendered, r"[A-Za-z]:[\\/]")
        self.assertNotIn("file://", rendered.lower())
        self.assertNotIn("NaN", rendered)
        self.assertNotIn("Infinity", rendered)
        self.assertNotIn(sentinel, rendered)

    def test_generation_time_changes_manifest_not_run_id(self) -> None:
        first = build_fixed_view()
        second = build_fixed_view(generated_at_utc=FIXED_GENERATED_AT + timedelta(hours=1))
        self.assertEqual(first.run_metadata.run_id, second.run_metadata.run_id)
        self.assertNotEqual(render_run_manifest(first), render_run_manifest(second))

    def test_manifest_records_exact_output_filenames(self) -> None:
        view = build_fixed_view()
        manifest = json.loads(render_run_manifest(view))
        self.assertEqual(
            (
                manifest["html_filename"],
                manifest["csv_filename"],
                manifest["manifest_filename"],
            ),
            (view.html_filename, view.csv_filename, view.manifest_filename),
        )
        for filename in (
            view.html_filename,
            view.csv_filename,
            view.manifest_filename,
        ):
            self.assertTrue(filename.startswith("quantlab-spy-"))
            self.assertIn(view.run_metadata.run_id, filename)


if __name__ == "__main__":
    unittest.main()
