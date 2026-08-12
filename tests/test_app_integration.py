from __future__ import annotations

import logging
import re
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest
from workflow_fixtures import RecordingMarketDataLoader

APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
FIXED_GENERATED_AT = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

# AppTest intentionally runs without a live Streamlit request context. Silence only
# that documented bare-mode diagnostic; page exceptions remain asserted below.
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)


class FailingMarketDataLoader:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise ConnectionError(r"C:\private\provider-response.json connection refused")


class ExportFailureText(str):
    def encode(self, *args, **kwargs):
        raise OSError(r"C:\private\export-buffer.tmp is unavailable")


def build_app(loader) -> AppTest:
    app = AppTest.from_file(str(APP_PATH))
    app.session_state["_quantlab_market_data_loader"] = loader
    app.session_state["_quantlab_generated_at_utc"] = FIXED_GENERATED_AT
    return app.run(timeout=30)


def run_button(app: AppTest):
    return next(button for button in app.button if button.key == "phase1_run")


def refresh_button(app: AppTest):
    return next(button for button in app.button if button.key == "phase1_refresh_and_run")


def result_navigation(app: AppTest):
    return app.segmented_control(key="phase1_result_section")


def prepare_exports_button(app: AppTest):
    return next(
        button for button in app.button if str(button.key).startswith("phase1_prepare_exports_")
    )


def metric_value(app: AppTest, label: str) -> str:
    return next(metric.value for metric in app.metric if metric.label == label)


def visible_text(app: AppTest) -> str:
    values: list[str] = []
    for collection in (
        app.title,
        app.header,
        app.subheader,
        app.caption,
        app.info,
        app.warning,
        app.error,
    ):
        values.extend(str(element.value) for element in collection)
    values.extend(str(element.label) for element in app.button)
    values.extend(str(element.label) for element in app.date_input)
    values.extend(str(element.label) for element in app.number_input)
    values.extend(str(element.label) for element in app.text_input)
    values.extend(str(element.label) for element in app.get("download_button"))
    values.extend(f"{element.label} {element.value}" for element in app.metric)
    return "\n".join(values)


class StreamlitPhaseOneIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(
            logging.ERROR
        )

    def test_page_starts_with_only_phase_one_controls_and_no_network_call(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(loader.calls, [])
        self.assertEqual([title.value for title in app.title], ["QuantLab SPY 日线回测"])
        self.assertIn("QuantLab v0.2.1", [item.value for item in app.sidebar.caption])
        self.assertEqual(list(app.date_input), [])
        self.assertEqual(
            [item.key for item in app.number_input],
            [
                "phase1_short_window",
                "phase1_long_window",
                "phase1_initial_capital",
                "phase1_fee_rate",
                "phase1_slippage_rate",
            ],
        )
        symbol = next(item for item in app.text_input if item.key == "phase1_symbol")
        self.assertEqual(symbol.value, "SPY")
        self.assertTrue(symbol.proto.disabled)
        self.assertEqual(
            [(item.label, item.key, item.value) for item in app.sidebar.text_input],
            [
                ("标的", "phase1_symbol", "SPY"),
                ("开始日期", "phase1_start_date_text", "2015-01-01"),
                ("结束日期", "phase1_end_date_text", "2024-12-31"),
            ],
        )
        self.assertEqual(
            [item.key for item in app.sidebar.number_input],
            [
                "phase1_short_window",
                "phase1_long_window",
                "phase1_initial_capital",
                "phase1_fee_rate",
                "phase1_slippage_rate",
            ],
        )
        self.assertEqual(
            [item.key for item in app.sidebar.button],
            ["phase1_run", "phase1_refresh_and_run"],
        )
        self.assertEqual(list(app.main.button), [])
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("st.form(", source)
        self.assertNotIn("st.form_submit_button(", source)
        self.assertNotIn("Press Enter to submit form", source)
        self.assertNotIn("st.date_input(", source)

    def test_sidebar_is_expanded_and_native_recovery_controls_are_not_hidden(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('initial_sidebar_state="expanded"', source)
        self.assertIn('[data-testid="collapsedControl"]', source)
        self.assertIn('[data-testid="stExpandSidebarButton"]', source)
        self.assertIn('[data-testid="stSidebarCollapseButton"]', source)
        for declaration in (
            "display: flex !important",
            "visibility: visible !important",
            "opacity: 1 !important",
            "pointer-events: auto !important",
        ):
            self.assertIn(declaration, source)
        self.assertIsNone(
            re.search(
                r'header\[data-testid="stHeader"\]\s*\{[^}]*'
                r"(?:height\s*:\s*0|display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0)",
                source,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )
        self.assertIsNone(
            re.search(
                r'\[data-testid="stToolbar"\]\s*\{[^}]*display\s*:\s*none',
                source,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )

    def test_page_has_no_desktop_control_surface(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        source = APP_PATH.read_text(encoding="utf-8")
        page_text = "\n".join(str(item.value) for item in app.markdown)
        self.assertNotIn("桌面控制", page_text)
        self.assertNotIn("打开控制窗口", [button.label for button in app.button])
        self.assertNotIn("desktop_control", source)

    def test_legacy_markets_strategies_and_upload_controls_are_not_visible(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        text = visible_text(app)
        for excluded in (
            "Crypto",
            "Demo",
            "CSV",
            "Stooq",
            "自适应策略",
            "参数排名",
            "纸上交易",
            "AI 预测",
        ):
            self.assertNotIn(excluded, text)
        self.assertEqual(len(app.selectbox), 0)
        self.assertEqual(len(app.radio), 0)
        self.assertEqual(len(app.file_uploader), 0)

    def test_click_runs_once_and_renders_view_outputs_in_required_order(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(
            [heading.value for heading in app.subheader],
            ["运行详情", "核心指标"],
        )
        self.assertEqual(len(app.metric), 9)
        self.assertNotIn("标的", [metric.label for metric in app.metric])
        self.assertNotIn("实际分析日期", [metric.label for metric in app.metric])
        self.assertNotIn("run_id", [metric.label for metric in app.metric])
        self.assertNotIn("数据指纹", [metric.label for metric in app.metric])
        self.assertEqual(metric_value(app, "胜率"), "100.0000%")
        self.assertEqual(len(app.get("vega_lite_chart")), 0)
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.segmented_control), 1)
        self.assertEqual(len(app.get("download_button")), 0)

        output = app.session_state["phase1_run_output"]
        details = "\n".join(str(item.value) for item in app.markdown)
        self.assertIn(output.report_view.analysis_date_range_display, details)
        self.assertIn(output.report_view.run_metadata.run_id, [item.value for item in app.code])
        self.assertIn(output.report_view.market_data.data_sha256, [item.value for item in app.code])

        result_navigation(app).set_value("净值对比").run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)
        self.assertEqual(len(app.get("download_button")), 0)
        chart_domain = next(
            str(item.value)
            for item in app.markdown
            if '<div class="ql-chart-domain"' in str(item.value)
        )
        first_equity = output.report_view.equity_rows[0]
        last_equity = output.report_view.equity_rows[-1]
        self.assertIn(f'data-start-date="{first_equity.date.isoformat()}"', chart_domain)
        self.assertIn(f'data-end-date="{last_equity.date.isoformat()}"', chart_domain)
        self.assertIn(f'data-start-strategy="{first_equity.strategy_equity:.10f}"', chart_domain)
        self.assertIn(f'data-end-strategy="{last_equity.strategy_equity:.10f}"', chart_domain)

        result_navigation(app).set_value("交易记录").run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(len(app.get("vega_lite_chart")), 0)
        self.assertEqual(len(app.dataframe), 1)

    def test_exports_require_explicit_preparation_and_do_not_rerun_workflow(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(len(app.get("download_button")), 0)

        result_navigation(app).set_value("导出").run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertIn("准备导出文件", [button.label for button in app.button])

        prepare_exports_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(
            [button.label for button in app.get("download_button")],
            [
                "下载 HTML 报告",
                "下载交易 CSV",
                "下载 Manifest JSON",
                "下载全部结果 ZIP",
            ],
        )
        for download in app.get("download_button"):
            self.assertTrue(download.proto.ignore_rerun)
            download.click().run(timeout=30)
            self.assertEqual(len(loader.calls), 1)
            self.assertEqual(list(app.exception), [])

    def test_zero_trade_run_shows_na_and_empty_state_with_all_downloads(self) -> None:
        loader = RecordingMarketDataLoader(flat=True)
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(metric_value(app, "胜率"), "N/A")
        result_navigation(app).set_value("交易记录").run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertIn("本次策略没有交易记录。", [item.value for item in app.info])
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.get("download_button")), 0)
        result_navigation(app).set_value("导出").run(timeout=30)
        prepare_exports_button(app).click().run(timeout=30)
        self.assertEqual(len(app.get("download_button")), 4)
        output = app.session_state["phase1_run_output"]
        self.assertEqual(len(output.trades_csv.splitlines()), 1)

    def test_provider_error_is_friendly_and_does_not_expose_local_path(self) -> None:
        loader = FailingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(loader.calls, 1)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.error), 1)
        message = app.error[0].value
        self.assertIn("网络连接失败", message)
        self.assertNotRegex(message, r"[A-Za-z]:[\\/]")
        self.assertNotIn("provider-response", message)
        self.assertNotIn("Traceback", message)
        self.assertEqual(len(app.subheader), 0)

    def test_export_failure_is_safe_and_keeps_the_completed_result(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        run_id = output.report_view.run_metadata.run_id
        app.session_state["phase1_run_output"] = replace(
            output,
            html_report=ExportFailureText(output.html_report),
        )

        result_navigation(app).set_value("导出").run(timeout=30)
        prepare_exports_button(app).click().run(timeout=30)

        self.assertEqual(list(app.exception), [])
        self.assertIn(
            "导出文件准备失败，请稍后重试；当前回测结果仍然保留。",
            [item.value for item in app.error],
        )
        self.assertEqual(
            app.session_state["phase1_run_output"].report_view.run_metadata.run_id,
            run_id,
        )
        self.assertNotIn(run_id, app.session_state["phase1_export_cache"])
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertNotRegex(app.error[-1].value, r"[A-Za-z]:[\\/]")
        self.assertNotIn("Traceback", app.error[-1].value)

    def test_control_change_keeps_old_result_and_requires_explicit_rerun(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        original_output = app.session_state["phase1_run_output"]
        original_run_id = original_output.report_view.run_metadata.run_id
        short_window = next(item for item in app.number_input if item.key == "phase1_short_window")
        short_window.set_value(10).run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertIn(
            "参数已修改，请重新运行回测以更新结果。以下仍是上一次运行结果。",
            [item.value for item in app.warning],
        )
        self.assertEqual(
            app.session_state["phase1_run_output"].report_view.run_metadata.run_id,
            original_run_id,
        )
        details = "\n".join(str(item.value) for item in app.markdown)
        self.assertIn("SPY · SMA 20 / 60", details)

    def test_date_draft_validation_is_chinese_and_never_runs_workflow(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        start_input = next(item for item in app.text_input if item.key == "phase1_start_date_text")
        start_input.set_value("2015/01/01").run(timeout=30)

        self.assertEqual(loader.calls, [])
        self.assertIn("开始日期：请输入 YYYY-MM-DD 格式", [item.value for item in app.error])
        self.assertTrue(run_button(app).proto.disabled)
        self.assertTrue(refresh_button(app).proto.disabled)

        start_input = next(item for item in app.text_input if item.key == "phase1_start_date_text")
        end_input = next(item for item in app.text_input if item.key == "phase1_end_date_text")
        start_input.set_value("2024-12-31")
        end_input.set_value("2024-12-31").run(timeout=30)
        self.assertEqual(loader.calls, [])
        self.assertIn("结束日期必须晚于开始日期", [item.value for item in app.error])

    def test_same_market_request_reuses_session_cache_and_refresh_bypasses_it(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        first_market_data = app.session_state["phase1_run_output"].market_data

        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertTrue(app.session_state["phase1_run_timings"]["cache_hit"])
        self.assertIs(app.session_state["phase1_run_output"].market_data, first_market_data)

        refresh_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 2)
        self.assertFalse(app.session_state["phase1_run_timings"]["cache_hit"])

    def test_cache_key_uses_dates_and_longest_lookback_but_not_short_window(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)

        short_window = next(item for item in app.number_input if item.key == "phase1_short_window")
        short_window.set_value(10)
        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(app.session_state["phase1_run_output"].request.short_window, 10)

        long_window = next(item for item in app.number_input if item.key == "phase1_long_window")
        long_window.set_value(80)
        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 2)
        self.assertIn("fixed to a 60-day lookback", app.error[0].value)

    def test_corrupt_session_cache_is_replaced_without_faking_a_cache_hit(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        app.session_state["phase1_market_data_cache"] = "corrupt"
        app.session_state["phase1_presentation_cache"] = ["corrupt"]
        app.session_state["phase1_export_cache"] = object()

        run_button(app).click().run(timeout=30)
        result_navigation(app).set_value("导出").run(timeout=30)

        self.assertEqual(len(loader.calls), 1)
        self.assertFalse(app.session_state["phase1_run_timings"]["cache_hit"])
        self.assertFalse(app.session_state["phase1_run_timings"]["presentation_cache_hit"])
        self.assertIsInstance(app.session_state["phase1_market_data_cache"], dict)
        self.assertIsInstance(app.session_state["phase1_presentation_cache"], dict)
        self.assertIsInstance(app.session_state["phase1_export_cache"], dict)
        self.assertEqual(list(app.exception), [])

    def test_cached_fetch_time_is_preserved_while_generation_time_changes(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        first = app.session_state["phase1_run_output"]

        later = FIXED_GENERATED_AT.replace(hour=FIXED_GENERATED_AT.hour + 1)
        app.session_state["_quantlab_generated_at_utc"] = later
        run_button(app).click().run(timeout=30)
        second = app.session_state["phase1_run_output"]

        self.assertEqual(len(loader.calls), 1)
        self.assertEqual(second.market_data.metadata.fetched_at_utc, FIXED_GENERATED_AT)
        self.assertEqual(second.report_view.run_metadata.generated_at_utc, later)
        self.assertEqual(
            first.report_view.run_metadata.run_id,
            second.report_view.run_metadata.run_id,
        )

    def test_page_rerun_and_result_selection_reuse_workflow_output(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]

        app.run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)

        result_navigation(app).set_value("交易记录").run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)

    def test_chart_resolution_is_ui_only_and_reuses_workflow_objects(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]

        result_navigation(app).set_value("净值对比").run(timeout=30)
        full_toggle = next(
            toggle for toggle in app.toggle if str(toggle.key).startswith("phase1_full_equity_")
        )
        full_toggle.set_value(True).run(timeout=30)

        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)

    def test_external_chart_data_and_reset_controls_do_not_rerun_workflow(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]
        run_id = output.report_view.run_metadata.run_id

        result_navigation(app).set_value("净值对比").run(timeout=30)
        display_control = next(
            control
            for control in app.segmented_control
            if str(control.key).startswith("phase1_chart_display_")
        )
        display_control.set_value("查看数据").run(timeout=30)
        self.assertEqual(len(app.get("vega_lite_chart")), 0)
        self.assertEqual(len(app.dataframe), 1)
        self.assertEqual(len(loader.calls), 1)

        display_control = next(
            control
            for control in app.segmented_control
            if str(control.key).startswith("phase1_chart_display_")
        )
        display_control.set_value("交互图").run(timeout=30)
        reset_button = next(
            button for button in app.button if str(button.key).startswith("phase1_chart_reset_")
        )
        reset_button.click().run(timeout=30)

        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)
        self.assertEqual(app.session_state[f"phase1_chart_reset_state_{run_id}"], 1)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)

    def test_chart_and_export_source_have_no_business_rerun_or_auto_download_hook(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertNotIn("st.line_chart(", source)
        self.assertIn('on_select="ignore"', source)
        self.assertIn("@st.fragment", source)
        self.assertIn('key="phase1_chart_shell"', source)
        self.assertIn('[data-testid="stElementToolbar"]', source)
        self.assertIn("准备导出文件", source)
        self.assertNotIn("window.location", source)
        self.assertNotIn(".click()", source)
        self.assertNotIn("data:text/csv", source)
        self.assertNotIn("blob:", source)
        for mime_type in ("text/html", "text/csv", "application/json", "application/zip"):
            self.assertIn(f'mime="{mime_type}"', source)

    def test_success_status_records_each_stage_without_exposing_timings_in_outputs(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        stage_text = "\n".join(str(item.value) for item in app.markdown)
        for label in (
            "1/6 准备数据",
            "2/6 标准化行情",
            "3/6 生成信号",
            "4/6 执行回测",
            "5/6 生成展示模型与导出结果",
            "正在准备页面图表与交易记录",
        ):
            self.assertIn(label, stage_text)
        timings = app.session_state["phase1_run_timings"]
        self.assertGreaterEqual(timings["total_seconds"], 0.0)
        self.assertNotIn("total_seconds", app.session_state["phase1_run_output"].manifest_json)

    def test_success_page_contains_reproducibility_limit_and_no_local_path(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        result_navigation(app).set_value("数据与假设").run(timeout=30)
        text = visible_text(app)
        self.assertIn("上游数据提供器可能修订历史数据", text)
        self.assertNotRegex(text, r"[A-Za-z]:[\\/]")
        self.assertNotIn("Traceback", text)

    def test_theme_variables_are_semantic_and_native_sidebar_controls_remain_visible(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        for variable in (
            "--ql-page-background",
            "--ql-surface",
            "--ql-surface-muted",
            "--ql-border",
            "--ql-text-primary",
            "--ql-text-secondary",
            "--ql-accent",
            "--ql-success",
            "--ql-warning",
            "--ql-code-background",
        ):
            self.assertIn(variable, source)
        self.assertIn('[data-testid="collapsedControl"]', source)
        self.assertIn("display: flex !important", source)


if __name__ == "__main__":
    unittest.main()
