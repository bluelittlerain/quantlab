from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pandas as pd
from workflow_fixtures import RecordingMarketDataLoader

from app.components import (
    CHART_BENCHMARK_COLUMN,
    CHART_DATE_COLUMN,
    CHART_EXCESS_RETURN_COLUMN,
    CHART_STRATEGY_COLUMN,
    DATE_INPUT_FORMAT_ERROR,
    DATE_RANGE_ORDER_ERROR,
    DEFAULT_CHART_MAX_ROWS,
    DEFAULT_TRADE_PREVIEW_ROWS,
    build_equity_chart_spec,
    chart_date_domain,
    downsample_equity_chart,
    export_zip_filename,
    format_file_size,
    friendly_error_message,
    friendly_export_error_message,
    market_data_cache_key,
    prepare_export_data,
    prepare_page_data,
    render_export_zip,
    validate_date_inputs,
    visible_trades_table,
)
from quant_lab.workflow import SpySmaRunRequest, run_spy_sma_workflow

FIXED_GENERATED_AT = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)


def build_request(*, short_window: int = 20, long_window: int = 60) -> SpySmaRunRequest:
    return SpySmaRunRequest(
        start_date=date(2024, 6, 3),
        end_date=date(2024, 6, 5),
        short_window=short_window,
        long_window=long_window,
        initial_capital=1000.0,
        fee_rate=0.01,
        slippage_rate=0.01,
    )


def build_output():
    return run_spy_sma_workflow(
        build_request(),
        software_version="0.1.0-test",
        generated_at_utc=FIXED_GENERATED_AT,
        market_data_loader=RecordingMarketDataLoader(),
    )


class StreamlitComponentTests(unittest.TestCase):
    def test_market_cache_key_uses_market_dates_and_longest_lookback(self) -> None:
        base = market_data_cache_key(build_request())
        changed_short = market_data_cache_key(build_request(short_window=10))
        changed_long = market_data_cache_key(build_request(long_window=80))

        self.assertEqual(base, changed_short)
        self.assertNotEqual(base, changed_long)
        self.assertEqual(base.symbol, "SPY")
        self.assertEqual(base.start_date, date(2024, 6, 3))
        self.assertEqual(base.end_date, date(2024, 6, 5))
        self.assertEqual(base.longest_lookback, 60)

    def test_page_data_maps_existing_equity_and_trade_facts_once(self) -> None:
        output = build_output()
        prepared = prepare_page_data(output)

        self.assertEqual(prepared.run_id, output.report_view.run_metadata.run_id)
        self.assertEqual(len(prepared.equity_chart), len(output.report_view.equity_rows))
        self.assertEqual(
            prepared.equity_chart[CHART_STRATEGY_COLUMN].tolist(),
            [row.strategy_equity for row in output.report_view.equity_rows],
        )
        self.assertEqual(
            prepared.equity_chart[CHART_BENCHMARK_COLUMN].tolist(),
            [row.benchmark_equity for row in output.report_view.equity_rows],
        )
        self.assertEqual(
            prepared.equity_chart[CHART_DATE_COLUMN].tolist(),
            [pd.Timestamp(row.date) for row in output.report_view.equity_rows],
        )
        pd.testing.assert_frame_equal(prepared.equity_chart_fast, prepared.equity_chart)
        expected_domain = (
            output.report_view.equity_rows[0].date,
            output.report_view.equity_rows[-1].date,
        )
        self.assertEqual(
            prepared.equity_chart_spec,
            build_equity_chart_spec(expected_domain),
        )
        self.assertEqual(
            prepared.excess_return_chart[CHART_EXCESS_RETURN_COLUMN].tolist(),
            [
                (row.strategy_equity - row.benchmark_equity)
                / output.report_view.config.initial_capital
                for row in output.report_view.equity_rows
            ],
        )
        self.assertEqual(len(prepared.trades_table), len(output.report_view.strategy_trades))

        first = output.report_view.equity_rows[0]
        last = output.report_view.equity_rows[-1]
        strategy_metrics = {
            metric.key: metric.raw_value for metric in output.report_view.strategy_metrics
        }
        benchmark_metrics = {
            metric.key: metric.raw_value for metric in output.report_view.benchmark_metrics
        }
        self.assertEqual(
            prepared.equity_chart.iloc[0][CHART_STRATEGY_COLUMN], first.strategy_equity
        )
        self.assertEqual(
            prepared.equity_chart.iloc[-1][CHART_STRATEGY_COLUMN], last.strategy_equity
        )
        self.assertEqual(
            prepared.equity_chart.iloc[0][CHART_BENCHMARK_COLUMN], first.benchmark_equity
        )
        self.assertEqual(
            prepared.equity_chart.iloc[-1][CHART_BENCHMARK_COLUMN], last.benchmark_equity
        )
        self.assertEqual(last.strategy_equity, strategy_metrics["final_equity"])
        self.assertEqual(last.benchmark_equity, benchmark_metrics["final_equity"])
        self.assertIn(f'data-start-date="{first.date.isoformat()}"', output.html_report)
        self.assertIn(f'data-end-date="{last.date.isoformat()}"', output.html_report)
        self.assertEqual(chart_date_domain(prepared.equity_chart), expected_domain)

    def test_trade_preview_does_not_change_complete_table(self) -> None:
        complete = pd.DataFrame({"trade_id": range(25), "status": ["CLOSED"] * 25})
        preview = visible_trades_table(complete, show_all=False)
        all_rows = visible_trades_table(complete, show_all=True)

        self.assertEqual(len(preview), DEFAULT_TRADE_PREVIEW_ROWS)
        self.assertEqual(len(all_rows), 25)
        self.assertEqual(len(complete), 25)
        self.assertEqual(all_rows["trade_id"].tolist(), list(range(25)))

    def test_trade_preview_uses_common_columns_without_changing_full_table(self) -> None:
        complete = pd.DataFrame(
            {
                "ID": range(25),
                "状态": ["已平仓"] * 25,
                "入场日期": ["2024-01-01"] * 25,
                "入场参考价": ["100.00"] * 25,
                "入场成交价": ["100.10"] * 25,
                "退出日期": ["2024-01-02"] * 25,
                "退出成交价": ["101.00"] * 25,
                "持有交易日": ["1"] * 25,
                "净损益": ["1.00"] * 25,
                "净收益率": ["1.00%"] * 25,
            }
        )

        preview = visible_trades_table(complete, show_all=False)
        all_rows = visible_trades_table(complete, show_all=True)

        self.assertEqual(len(preview), DEFAULT_TRADE_PREVIEW_ROWS)
        self.assertNotIn("入场参考价", preview.columns)
        self.assertIn("净收益率", preview.columns)
        self.assertIs(all_rows, complete)

    def test_trade_preview_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            visible_trades_table(pd.DataFrame({"trade_id": [1]}), show_all=False, limit=0)

    def test_equity_downsampling_is_deterministic_and_preserves_extrema(self) -> None:
        chart = pd.DataFrame(
            {
                CHART_STRATEGY_COLUMN: [10, 100, 20, 1, 30, 90, 40, 2, 50, 60],
                CHART_BENCHMARK_COLUMN: [10, 20, 95, 3, 40, 30, 85, 4, 50, 60],
            },
            index=pd.date_range("2024-01-01", periods=10),
        )
        original = chart.copy(deep=True)

        first = downsample_equity_chart(chart, max_rows=10)
        second = downsample_equity_chart(chart, max_rows=10)

        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(chart, original)
        self.assertEqual(first.index[0], chart.index[0])
        self.assertEqual(first.index[-1], chart.index[-1])
        for position in (1, 2, 3, 5, 6, 7):
            self.assertIn(chart.index[position], first.index)
        self.assertLessEqual(len(first), 10)

    def test_formal_scale_downsampling_controls_rows_and_keeps_full_data(self) -> None:
        dates = pd.bdate_range("2015-01-02", periods=2_516)
        chart = pd.DataFrame(
            {
                CHART_STRATEGY_COLUMN: [10_000 + (index % 97) for index in range(2_516)],
                CHART_BENCHMARK_COLUMN: [10_000 + (index % 71) for index in range(2_516)],
            },
            index=dates,
        )

        display = downsample_equity_chart(chart)

        self.assertLessEqual(len(display), DEFAULT_CHART_MAX_ROWS)
        self.assertEqual(len(chart), 2_516)
        self.assertEqual(display.index[0], chart.index[0])
        self.assertEqual(display.index[-1], chart.index[-1])

    def test_equity_chart_spec_has_one_mark_and_browser_local_interaction(self) -> None:
        date_domain = (date(2015, 1, 2), date(2024, 12, 31))
        spec = build_equity_chart_spec(date_domain)

        self.assertEqual(spec["mark"]["type"], "line")
        self.assertNotIn("layer", spec)
        self.assertEqual(spec["params"][0]["bind"], "scales")
        self.assertEqual(spec["params"][0]["select"]["encodings"], ["x"])
        self.assertEqual(
            spec["encoding"]["x"]["scale"],
            {"domain": ["2015-01-02", "2024-12-31"], "nice": False},
        )

    def test_iso_date_inputs_are_locale_independent_and_report_chinese_errors(self) -> None:
        valid = validate_date_inputs("2015-01-01", "2024-12-31")
        bad_format = validate_date_inputs("01/01/2015", "2024-12-31")
        bad_order = validate_date_inputs("2024-12-31", "2024-12-31")

        self.assertTrue(valid.is_valid)
        self.assertEqual(valid.start_date, date(2015, 1, 1))
        self.assertEqual(valid.end_date, date(2024, 12, 31))
        self.assertEqual(bad_format.errors, (f"开始日期：{DATE_INPUT_FORMAT_ERROR}",))
        self.assertEqual(bad_order.errors, (DATE_RANGE_ORDER_ERROR,))

    def test_export_zip_contains_exact_existing_outputs(self) -> None:
        output = build_output()
        archive_bytes = render_export_zip(output)

        self.assertTrue(export_zip_filename(output).endswith("-results.zip"))
        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    output.report_view.html_filename,
                    output.report_view.csv_filename,
                    output.report_view.manifest_filename,
                },
            )
            self.assertEqual(
                archive.read(output.report_view.html_filename).decode("utf-8"),
                output.html_report,
            )
            self.assertEqual(
                archive.read(output.report_view.csv_filename).decode("utf-8"),
                output.trades_csv,
            )
            manifest = json.loads(
                archive.read(output.report_view.manifest_filename).decode("utf-8")
            )
        self.assertEqual(manifest["run_id"], output.report_view.run_metadata.run_id)

    def test_prepared_export_metadata_uses_exact_utf8_payload_sizes(self) -> None:
        output = build_output()

        prepared = prepare_export_data(output)

        self.assertEqual(prepared.run_id, output.report_view.run_metadata.run_id)
        self.assertEqual(prepared.generated_at_display, "2025-02-03T04:05:06Z")
        self.assertEqual(prepared.html_size, len(output.html_report.encode("utf-8")))
        self.assertEqual(prepared.csv_size, len(output.trades_csv.encode("utf-8")))
        self.assertEqual(prepared.manifest_size, len(output.manifest_json.encode("utf-8")))
        self.assertEqual(prepared.zip_size, len(prepared.zip_bytes))
        self.assertEqual(format_file_size(0), "0 B")
        self.assertEqual(format_file_size(1536), "1.5 KB")
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            format_file_size(-1)

    def test_user_facing_errors_are_specific_and_remove_provider_details(self) -> None:
        cases = (
            (ValueError("returned no SPY history"), "数据提供器没有返回 SPY 日线数据"),
            (ValueError("warmup rows are insufficient"), "预热行情不足"),
            (ValueError("contains no price data"), "所选日期范围内没有可用交易日"),
            (TimeoutError("provider timeout"), "网络请求超时，请稍后重试"),
            (ConnectionError("provider refused"), "网络连接失败，请检查网络后重试"),
        )
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                message = friendly_error_message(error)
                self.assertIn(expected, message)
                self.assertNotIn(str(error), message)

        sanitized = friendly_error_message(
            RuntimeError(
                r"provider failed at C:\Users\ExampleUser\response.json "
                "https://example.invalid/private-response"
            )
        )
        self.assertIn("[本地路径已隐藏]", sanitized)
        self.assertIn("[远程地址已隐藏]", sanitized)
        self.assertNotIn("ExampleUser", sanitized)
        self.assertNotIn("example.invalid", sanitized)
        self.assertEqual(
            friendly_export_error_message(OSError("private detail")),
            "导出文件准备失败，请稍后重试；当前回测结果仍然保留。",
        )


if __name__ == "__main__":
    unittest.main()
