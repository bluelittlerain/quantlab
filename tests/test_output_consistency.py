from __future__ import annotations

import csv
import io
import json
import math
import re
import unittest
from dataclasses import replace
from datetime import timedelta
from html import unescape

import pandas as pd
from test_report import (
    FIXED_GENERATED_AT,
    LONG_WINDOW,
    SHORT_WINDOW,
    SOFTWARE_VERSION,
    STRATEGY_NAME,
    build_fixed_report_inputs,
    build_fixed_view,
)

from quant_lab.models import MarketDataResult
from quant_lab.presentation import build_report_view, calculate_run_id
from quant_lab.report import (
    render_html_report,
    render_run_manifest,
    render_trades_csv,
)


def html_meta(document: str, name: str) -> str:
    match = re.search(
        rf'<meta name="{re.escape(name)}" content="([^"]*)">',
        document,
    )
    if match is None:
        raise AssertionError(f"missing HTML meta {name!r}")
    return unescape(match.group(1))


def html_metric_raw(document: str, scope: str, key: str) -> str:
    match = re.search(
        rf'data-scope="{re.escape(scope)}"\s+data-key="{re.escape(key)}"\s+'
        rf'data-raw-value="([^"]*)"',
        document,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing HTML metric {scope}.{key}")
    return unescape(match.group(1))


class OutputConsistencyTests(unittest.TestCase):
    def assert_float_equal(self, actual: str | float, expected: float) -> None:
        self.assertTrue(
            math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-9),
            f"actual={actual!r}, expected={expected!r}",
        )

    def test_01_html_and_csv_share_run_id(self) -> None:
        view = build_fixed_view()
        html = render_html_report(view)
        row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
        self.assertEqual(html_meta(html, "quantlab-run-id"), view.run_metadata.run_id)
        self.assertEqual(row["run_id"], view.run_metadata.run_id)

    def test_02_html_and_csv_share_data_sha256(self) -> None:
        view = build_fixed_view()
        html = render_html_report(view)
        row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
        self.assertEqual(
            html_meta(html, "quantlab-data-sha256"),
            view.market_data.data_sha256,
        )
        self.assertEqual(row["data_sha256"], view.market_data.data_sha256)

    def test_03_version_symbol_and_parameters_match_view(self) -> None:
        view = build_fixed_view()
        html = render_html_report(view)
        row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
        expected = {
            "quantlab-software-version": view.run_metadata.software_version,
            "quantlab-symbol": view.run_metadata.symbol,
            "quantlab-strategy": view.run_metadata.strategy_name,
            "quantlab-short-window": str(view.run_metadata.short_window),
            "quantlab-long-window": str(view.run_metadata.long_window),
            "quantlab-requested-start-date": view.market_data.requested_start_date.isoformat(),
            "quantlab-requested-end-date": view.market_data.requested_end_date.isoformat(),
            "quantlab-actual-start-date": view.market_data.actual_start_date.isoformat(),
            "quantlab-actual-end-date": view.market_data.actual_end_date.isoformat(),
            "quantlab-analysis-start-date": view.market_data.analysis_start_date.isoformat(),
            "quantlab-analysis-end-date": view.market_data.analysis_end_date.isoformat(),
        }
        for key, value in expected.items():
            self.assertEqual(html_meta(html, key), value)
        self.assertEqual(row["software_version"], view.run_metadata.software_version)
        self.assertEqual(row["symbol"], view.run_metadata.symbol)
        self.assertEqual(row["strategy_name"], view.run_metadata.strategy_name)
        self.assertEqual(row["short_window"], str(view.run_metadata.short_window))
        self.assertEqual(row["long_window"], str(view.run_metadata.long_window))
        for prefix in ("requested", "actual", "analysis"):
            for boundary in ("start", "end"):
                field = f"{prefix}_{boundary}_date"
                self.assertEqual(
                    row[field],
                    getattr(view.market_data, field).isoformat(),
                )

    def test_04_every_csv_trade_matches_trade_view_raw_values(self) -> None:
        view = build_fixed_view()
        rows = list(csv.DictReader(io.StringIO(render_trades_csv(view))))
        self.assertEqual(len(rows), len(view.strategy_trades))
        for row, trade in zip(rows, view.strategy_trades):
            self.assertEqual(int(row["trade_id"]), trade.trade_id)
            self.assertEqual(row["entry_date"], trade.entry_date.raw_value.isoformat())
            self.assert_float_equal(row["entry_raw_price"], trade.entry_raw_price.raw_value)
            self.assert_float_equal(
                row["entry_execution_price"], trade.entry_execution_price.raw_value
            )
            self.assert_float_equal(row["quantity"], trade.quantity.raw_value)
            self.assert_float_equal(row["entry_fee"], trade.entry_fee.raw_value)
            self.assert_float_equal(row["entry_slippage_cost"], trade.entry_slippage_cost.raw_value)
            self.assert_float_equal(row["gross_pnl"], trade.gross_pnl.raw_value)
            self.assert_float_equal(row["net_pnl"], trade.net_pnl.raw_value)
            self.assert_float_equal(row["net_return"], trade.net_return.raw_value)

    def test_05_open_and_closed_status_are_identical(self) -> None:
        for case_id in ("G06", "G08"):
            with self.subTest(case_id=case_id):
                view = build_fixed_view(case_id)
                row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
                self.assertEqual(row["status"], view.strategy_trades[0].status)
                self.assertIn(
                    f'data-status="{view.strategy_trades[0].status}"',
                    render_html_report(view),
                )

    def test_06_open_trade_exit_fields_are_empty_not_zero(self) -> None:
        view = build_fixed_view("G08")
        row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
        for key in (
            "exit_date",
            "exit_raw_price",
            "exit_execution_price",
            "exit_fee",
            "exit_slippage_cost",
        ):
            self.assertIsNone(getattr(view.strategy_trades[0], key).raw_value)
            self.assertEqual(row[key], "")

    def test_07_strategy_html_metrics_equal_performance_metrics(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
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
        html = render_html_report(view)
        for key in comparison.strategy.metrics.__dataclass_fields__:
            expected = getattr(comparison.strategy.metrics, key)
            raw = html_metric_raw(html, "strategy", key)
            if expected is None:
                self.assertEqual(raw, "")
            else:
                self.assert_float_equal(raw, expected)

    def test_08_benchmark_html_metrics_equal_performance_metrics(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
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
        html = render_html_report(view)
        for key in comparison.benchmark.metrics.__dataclass_fields__:
            expected = getattr(comparison.benchmark.metrics, key)
            raw = html_metric_raw(html, "benchmark", key)
            if expected is None:
                self.assertEqual(raw, "")
            else:
                self.assert_float_equal(raw, expected)

    def test_09_excess_return_is_constructed_once_in_view(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
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
        expected = (
            comparison.strategy.metrics.total_return - comparison.benchmark.metrics.total_return
        )
        self.assert_float_equal(view.excess_return.raw_value, expected)
        self.assert_float_equal(
            html_metric_raw(render_html_report(view), "comparison", "excess_return"),
            view.excess_return.raw_value,
        )

    def test_10_html_fee_and_slippage_totals_match_metrics(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
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
        html = render_html_report(view)
        for scope, metrics in (
            ("strategy", comparison.strategy.metrics),
            ("benchmark", comparison.benchmark.metrics),
        ):
            self.assert_float_equal(html_metric_raw(html, scope, "total_fees"), metrics.total_fees)
            self.assert_float_equal(
                html_metric_raw(html, scope, "total_slippage_cost"),
                metrics.total_slippage_cost,
            )

    def test_11_html_csv_and_metrics_have_the_same_trade_count(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
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
        html = render_html_report(view)
        csv_rows = list(csv.DictReader(io.StringIO(render_trades_csv(view))))
        expected = (
            comparison.strategy.metrics.closed_trade_count
            + comparison.strategy.metrics.open_trade_count
        )
        self.assertEqual(len(re.findall(r'<tr data-trade-id="', html)), expected)
        self.assertEqual(len(csv_rows), expected)
        self.assertEqual(len(view.strategy_trades), expected)

    def test_12_outputs_do_not_contain_local_absolute_paths(self) -> None:
        view = build_fixed_view()
        for output in (render_html_report(view), render_trades_csv(view)):
            self.assertNotRegex(output, r"[A-Za-z]:[\\/]")
            self.assertNotIn("file://", output.lower())

    def test_13_html_has_no_remote_resource_reference(self) -> None:
        html = render_html_report(build_fixed_view())
        self.assertNotIn("http://", html.lower())
        self.assertNotIn("https://", html.lower())
        self.assertNotRegex(html.lower(), r'(?:src|href)=["\'](?:https?:|//)')

    def test_14_provider_payload_and_dataframe_attrs_are_not_exported(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
        sentinel = "SECRET_PROVIDER_PAYLOAD_9f4c"
        market_data.prices.attrs["raw_provider_response"] = sentinel
        market_data.prices.attrs["api_key"] = sentinel
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
        self.assertNotIn(sentinel, render_html_report(view))
        self.assertNotIn(sentinel, render_trades_csv(view))

    def test_15_same_inputs_and_time_produce_identical_outputs(self) -> None:
        first = build_fixed_view()
        second = build_fixed_view()
        self.assertEqual(render_html_report(first), render_html_report(second))
        self.assertEqual(render_trades_csv(first), render_trades_csv(second))

    def test_16_generation_time_changes_html_but_not_run_id(self) -> None:
        first = build_fixed_view()
        second = build_fixed_view(generated_at_utc=FIXED_GENERATED_AT + timedelta(hours=1))
        self.assertEqual(first.run_metadata.run_id, second.run_metadata.run_id)
        self.assertNotEqual(render_html_report(first), render_html_report(second))
        self.assertIn(second.run_metadata.generated_at_display, render_html_report(second))

    def test_17_run_id_changes_with_hash_cost_or_parameters(self) -> None:
        market_data, _, config = build_fixed_report_inputs()

        def identifier(metadata=market_data.metadata, selected_config=config, short=20):
            return calculate_run_id(
                metadata,
                selected_config,
                strategy_name=STRATEGY_NAME,
                short_window=short,
                long_window=LONG_WINDOW,
                software_version=SOFTWARE_VERSION,
            )

        ids = {
            identifier(),
            identifier(replace(market_data.metadata, data_sha256="c" * 64)),
            identifier(selected_config=replace(config, slippage_rate=0.02)),
            identifier(short=10),
        }
        self.assertEqual(len(ids), 4)

    def test_18_dataframe_column_order_does_not_change_report(self) -> None:
        market_data, comparison, config = build_fixed_report_inputs()
        reordered_market = MarketDataResult(
            prices=market_data.prices.loc[:, list(reversed(market_data.prices.columns))],
            metadata=market_data.metadata,
        )
        reordered_strategy = replace(
            comparison.strategy,
            daily=comparison.strategy.daily.loc[
                :, list(reversed(comparison.strategy.daily.columns))
            ],
        )
        reordered_benchmark = replace(
            comparison.benchmark,
            daily=comparison.benchmark.daily.loc[
                :, list(reversed(comparison.benchmark.daily.columns))
            ],
        )
        original = build_report_view(
            market_data,
            comparison,
            config=config,
            strategy_name=STRATEGY_NAME,
            short_window=SHORT_WINDOW,
            long_window=LONG_WINDOW,
            software_version=SOFTWARE_VERSION,
            generated_at_utc=FIXED_GENERATED_AT,
        )
        reordered = build_report_view(
            reordered_market,
            replace(
                comparison,
                strategy=reordered_strategy,
                benchmark=reordered_benchmark,
            ),
            config=config,
            strategy_name=STRATEGY_NAME,
            short_window=SHORT_WINDOW,
            long_window=LONG_WINDOW,
            software_version=SOFTWARE_VERSION,
            generated_at_utc=FIXED_GENERATED_AT,
        )
        self.assertEqual(render_html_report(original), render_html_report(reordered))
        self.assertEqual(render_trades_csv(original), render_trades_csv(reordered))

    def test_19_none_win_rate_is_na_in_html_and_empty_raw_value(self) -> None:
        view = build_fixed_view("G08")
        html = render_html_report(view)
        self.assertEqual(html_metric_raw(html, "strategy", "win_rate"), "")
        self.assertRegex(
            html,
            r'data-scope="strategy"\s+data-key="win_rate".*?<strong>N/A</strong>',
        )

    def test_20_csv_round_trips_with_standard_library_and_pandas(self) -> None:
        csv_text = render_trades_csv(build_fixed_view())
        standard_rows = list(csv.DictReader(io.StringIO(csv_text)))
        pandas_rows = pd.read_csv(
            io.StringIO(csv_text),
            dtype=str,
            keep_default_na=False,
        )
        self.assertEqual(len(standard_rows), len(pandas_rows))
        self.assertEqual(standard_rows[0]["run_id"], pandas_rows.iloc[0]["run_id"])
        self.assertNotIn("\r", csv_text)
        self.assertEqual(csv_text.encode("utf-8").decode("utf-8"), csv_text)

    def test_21_html_csv_manifest_and_view_share_identity(self) -> None:
        view = build_fixed_view()
        html = render_html_report(view)
        csv_row = next(csv.DictReader(io.StringIO(render_trades_csv(view))))
        manifest = json.loads(render_run_manifest(view))
        expected_run_id = view.run_metadata.run_id
        expected_hash = view.market_data.data_sha256
        self.assertEqual(html_meta(html, "quantlab-run-id"), expected_run_id)
        self.assertEqual(csv_row["run_id"], expected_run_id)
        self.assertEqual(manifest["run_id"], expected_run_id)
        self.assertEqual(html_meta(html, "quantlab-data-sha256"), expected_hash)
        self.assertEqual(csv_row["data_sha256"], expected_hash)
        self.assertEqual(manifest["data_sha256"], expected_hash)

    def test_22_manifest_filenames_match_view_and_report_bundle_contract(self) -> None:
        view = build_fixed_view()
        manifest = json.loads(render_run_manifest(view))
        self.assertEqual(manifest["html_filename"], view.html_filename)
        self.assertEqual(manifest["csv_filename"], view.csv_filename)
        self.assertEqual(manifest["manifest_filename"], view.manifest_filename)


if __name__ == "__main__":
    unittest.main()
