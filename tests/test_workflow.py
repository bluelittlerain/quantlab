from __future__ import annotations

import csv
import io
import json
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from workflow_fixtures import (
    G06_EXPECTED_FINAL_EQUITY,
    G06_EXPECTED_TOTAL_FEES,
    G06_EXPECTED_TOTAL_RETURN,
    G06_EXPECTED_TOTAL_SLIPPAGE,
    RecordingMarketDataLoader,
)

from quant_lab import __version__
from quant_lab.backtest import run_strategy_and_benchmark
from quant_lab.presentation import build_report_view
from quant_lab.workflow import (
    SPY_SMA_STRATEGY_NAME,
    SpySmaRunRequest,
    run_spy_sma_workflow,
)

FIXED_GENERATED_AT = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
SOFTWARE_VERSION = "0.1.0-test"


def build_request(**changes: object) -> SpySmaRunRequest:
    values: dict[str, object] = {
        "start_date": date(2024, 6, 3),
        "end_date": date(2024, 6, 5),
        "short_window": 20,
        "long_window": 60,
        "initial_capital": 1000.0,
        "fee_rate": 0.01,
        "slippage_rate": 0.01,
    }
    values.update(changes)
    return SpySmaRunRequest(**values)  # type: ignore[arg-type]


def run_fixed_workflow(
    request: SpySmaRunRequest | None = None,
    *,
    loader: RecordingMarketDataLoader | None = None,
    generated_at_utc: datetime = FIXED_GENERATED_AT,
):
    selected_loader = loader or RecordingMarketDataLoader()
    output = run_spy_sma_workflow(
        request or build_request(),
        software_version=SOFTWARE_VERSION,
        generated_at_utc=generated_at_utc,
        market_data_loader=selected_loader,
    )
    return output, selected_loader


class WorkflowRequestTests(unittest.TestCase):
    def test_valid_request_is_immutable_and_typed(self) -> None:
        request = build_request()
        self.assertEqual(request.short_window, 20)
        with self.assertRaisesRegex(Exception, "cannot assign"):
            request.short_window = 10  # type: ignore[misc]

    def test_invalid_dates_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "start_date"):
            build_request(start_date=date(2024, 6, 6))
        with self.assertRaisesRegex(TypeError, "must be a date"):
            build_request(start_date=datetime(2024, 6, 3))

    def test_invalid_windows_are_rejected(self) -> None:
        for changes in (
            {"short_window": 0},
            {"long_window": 1},
            {"short_window": 60},
            {"short_window": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_request(**changes)

    def test_invalid_capital_costs_and_slippage_are_rejected(self) -> None:
        for changes in (
            {"initial_capital": 0.0},
            {"initial_capital": math.nan},
            {"fee_rate": -0.001},
            {"fee_rate": 1.0},
            {"slippage_rate": -0.001},
            {"slippage_rate": math.inf},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_request(**changes)


class WorkflowIntegrationTests(unittest.TestCase):
    def assert_close(self, actual: float, expected: float) -> None:
        self.assertTrue(
            math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9),
            f"actual={actual!r}, expected={expected!r}",
        )

    def test_provider_is_called_once_with_request_and_long_window(self) -> None:
        output, loader = run_fixed_workflow()
        self.assertEqual(
            loader.calls,
            [
                (
                    output.request.start_date,
                    output.request.end_date,
                    output.request.long_window,
                    FIXED_GENERATED_AT,
                )
            ],
        )

    def test_strategy_engine_and_view_are_each_built_once(self) -> None:
        loader = RecordingMarketDataLoader()
        with (
            patch(
                "quant_lab.workflow.run_strategy_and_benchmark",
                wraps=run_strategy_and_benchmark,
            ) as engine,
            patch(
                "quant_lab.workflow.build_report_view",
                wraps=build_report_view,
            ) as view_builder,
        ):
            output, _ = run_fixed_workflow(loader=loader)
        engine.assert_called_once()
        view_builder.assert_called_once()
        self.assertIs(output.report_view.market_data, output.market_data.metadata)

    def test_stage_callback_reports_deterministic_workflow_boundaries(self) -> None:
        stages: list[str] = []
        output = run_spy_sma_workflow(
            build_request(),
            software_version=SOFTWARE_VERSION,
            generated_at_utc=FIXED_GENERATED_AT,
            market_data_loader=RecordingMarketDataLoader(),
            stage_callback=stages.append,
        )
        self.assertEqual(
            stages,
            [
                "market_data_fetch",
                "market_data_standardize",
                "sma_signal",
                "cash_ledger",
                "presentation",
                "html_report",
                "trades_csv",
                "manifest",
            ],
        )
        self.assertNotIn("market_data_fetch", output.html_report)
        self.assertNotIn("market_data_fetch", output.manifest_json)

    def test_real_sma_and_cash_ledger_reproduce_g06_literals(self) -> None:
        output, _ = run_fixed_workflow()
        metrics = output.comparison.strategy.metrics
        self.assert_close(metrics.final_equity, G06_EXPECTED_FINAL_EQUITY)
        self.assert_close(metrics.total_return, G06_EXPECTED_TOTAL_RETURN)
        self.assert_close(metrics.total_fees, G06_EXPECTED_TOTAL_FEES)
        self.assert_close(
            metrics.total_slippage_cost,
            G06_EXPECTED_TOTAL_SLIPPAGE,
        )
        self.assertEqual(
            output.comparison.strategy.daily["target_position"].tolist(),
            [1.0, 0.0, 0.0],
        )
        self.assertEqual(
            output.comparison.strategy.daily["action"].tolist(),
            ["NONE", "BUY", "SELL"],
        )

    def test_html_csv_and_manifest_share_one_run_identity(self) -> None:
        output, _ = run_fixed_workflow()
        view = output.report_view
        manifest = json.loads(output.manifest_json)
        csv_row = next(csv.DictReader(io.StringIO(output.trades_csv)))
        self.assertIn(view.run_metadata.run_id, output.html_report)
        self.assertEqual(csv_row["run_id"], view.run_metadata.run_id)
        self.assertEqual(manifest["run_id"], view.run_metadata.run_id)
        self.assertEqual(csv_row["data_sha256"], view.market_data.data_sha256)
        self.assertEqual(manifest["data_sha256"], view.market_data.data_sha256)

    def test_current_runtime_version_flows_to_new_outputs(self) -> None:
        output = run_spy_sma_workflow(
            build_request(),
            software_version=__version__,
            generated_at_utc=FIXED_GENERATED_AT,
            market_data_loader=RecordingMarketDataLoader(),
        )
        manifest = json.loads(output.manifest_json)
        csv_row = next(csv.DictReader(io.StringIO(output.trades_csv)))

        self.assertEqual(__version__, "0.2.1")
        self.assertEqual(output.report_view.run_metadata.software_version, "0.2.1")
        self.assertEqual(manifest["software_version"], "0.2.1")
        self.assertEqual(csv_row["software_version"], "0.2.1")
        self.assertIn('content="0.2.1"', output.html_report)
        self.assertNotIn("0.2.1-preview", output.html_report)

    def test_view_and_outputs_retain_the_same_result_facts(self) -> None:
        output, _ = run_fixed_workflow()
        strategy_metrics = {
            metric.key: metric.raw_value for metric in output.report_view.strategy_metrics
        }
        self.assertEqual(
            strategy_metrics["final_equity"],
            output.comparison.strategy.metrics.final_equity,
        )
        self.assertEqual(
            strategy_metrics["total_fees"],
            output.comparison.strategy.metrics.total_fees,
        )
        self.assertEqual(
            len(output.report_view.strategy_trades),
            len(output.comparison.strategy.trades),
        )

    def test_generation_time_is_injected_and_forwarded(self) -> None:
        output, loader = run_fixed_workflow()
        manifest = json.loads(output.manifest_json)
        self.assertEqual(output.market_data.metadata.fetched_at_utc, FIXED_GENERATED_AT)
        self.assertEqual(loader.calls[0][3], FIXED_GENERATED_AT)
        self.assertEqual(manifest["generated_at_utc"], "2025-02-03T04:05:06Z")

    def test_same_inputs_and_time_are_byte_deterministic(self) -> None:
        first, _ = run_fixed_workflow()
        second, _ = run_fixed_workflow()
        self.assertEqual(
            first.report_view.run_metadata.run_id, second.report_view.run_metadata.run_id
        )
        self.assertEqual(first.html_report, second.html_report)
        self.assertEqual(first.trades_csv, second.trades_csv)
        self.assertEqual(first.manifest_json, second.manifest_json)

    def test_generated_time_changes_outputs_but_not_run_id(self) -> None:
        first, _ = run_fixed_workflow()
        second, _ = run_fixed_workflow(generated_at_utc=FIXED_GENERATED_AT + timedelta(hours=1))
        self.assertEqual(
            first.report_view.run_metadata.run_id, second.report_view.run_metadata.run_id
        )
        self.assertNotEqual(first.html_report, second.html_report)
        self.assertNotEqual(first.manifest_json, second.manifest_json)

    def test_cost_or_parameter_changes_run_id(self) -> None:
        base, _ = run_fixed_workflow()
        changed_fee, _ = run_fixed_workflow(build_request(fee_rate=0.02))
        changed_short, _ = run_fixed_workflow(build_request(short_window=10))
        self.assertEqual(
            len(
                {
                    base.report_view.run_metadata.run_id,
                    changed_fee.report_view.run_metadata.run_id,
                    changed_short.report_view.run_metadata.run_id,
                }
            ),
            3,
        )

    def test_zero_trade_run_has_header_only_csv_and_complete_manifest(self) -> None:
        output, _ = run_fixed_workflow(loader=RecordingMarketDataLoader(flat=True))
        lines = output.trades_csv.splitlines()
        manifest = json.loads(output.manifest_json)
        self.assertEqual(len(lines), 1)
        self.assertIn("trade_id", lines[0])
        self.assertEqual(output.report_view.strategy_trade_count, 0)
        self.assertEqual(manifest["strategy_trade_count"], 0)
        self.assertEqual(manifest["strategy_open_trade_count"], 0)
        win_rate = next(
            metric for metric in output.report_view.strategy_metrics if metric.key == "win_rate"
        )
        self.assertIsNone(win_rate.raw_value)
        self.assertEqual(win_rate.display_value, "N/A")

    def test_non_spy_provider_result_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "SPY"):
            run_fixed_workflow(loader=RecordingMarketDataLoader(symbol="QQQ"))

    def test_provider_failure_is_not_masked_by_fallback(self) -> None:
        def failing_loader(*args, **kwargs):
            raise ConnectionError("fixed provider outage")

        with self.assertRaisesRegex(ConnectionError, "fixed provider outage"):
            run_spy_sma_workflow(
                build_request(),
                software_version=SOFTWARE_VERSION,
                generated_at_utc=FIXED_GENERATED_AT,
                market_data_loader=failing_loader,
            )

    def test_workflow_metadata_is_phase_one_only(self) -> None:
        output, _ = run_fixed_workflow()
        self.assertEqual(output.report_view.run_metadata.symbol, "SPY")
        self.assertEqual(
            output.report_view.run_metadata.strategy_name,
            SPY_SMA_STRATEGY_NAME,
        )
        self.assertNotIn("crypto", output.html_report.lower())

    def test_workflow_rejects_non_utc_generation_time(self) -> None:
        for invalid_time in (
            datetime(2025, 2, 3, 4, 5, 6),
            datetime(2025, 2, 3, 12, 5, 6, tzinfo=timezone(timedelta(hours=8))),
        ):
            with self.subTest(invalid_time=invalid_time), self.assertRaises(ValueError):
                run_spy_sma_workflow(
                    build_request(),
                    software_version=SOFTWARE_VERSION,
                    generated_at_utc=invalid_time,
                    market_data_loader=RecordingMarketDataLoader(),
                )


if __name__ == "__main__":
    unittest.main()
