from __future__ import annotations

import logging
import re
import unittest
from hashlib import sha256
from pathlib import Path

from test_app_integration import (
    build_app,
    prepare_exports_button,
    result_navigation,
    run_button,
)
from workflow_fixtures import RecordingMarketDataLoader

from app.components import (
    CHART_EXCESS_RETURN_COLUMN,
    CHART_VIEW_EXCESS,
    DARK_THEME,
    DEFAULT_CHART_MAX_ROWS,
    LIGHT_THEME,
    PreparedExportData,
)

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app" / "streamlit_app.py"
WINDOWS_LAUNCHER_PATH = ROOT / "packaging" / "windows" / "desktop_launcher.py"
WINDOWS_README_PATH = ROOT / "packaging" / "windows" / "README-WINDOWS.txt"


def keyed_toggle(app, key: str):
    return next(toggle for toggle in app.toggle if toggle.key == key)


def chart_view_control(app):
    return next(
        control
        for control in app.segmented_control
        if str(control.key).startswith("phase1_chart_view_")
    )


def relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2])


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def output_hashes(output) -> tuple[str, str, str]:
    return tuple(
        sha256(payload.encode("utf-8")).hexdigest()
        for payload in (output.html_report, output.trades_csv, output.manifest_json)
    )


class StreamlitUiQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(
            logging.ERROR
        )

    def test_long_run_details_are_complete_and_copyable_without_metric_cards(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        view = output.report_view
        code_values = [item.value for item in app.code]
        markdown = "\n".join(str(item.value) for item in app.markdown)

        self.assertIn(view.analysis_date_range_display, markdown)
        self.assertIn(view.run_metadata.run_id, code_values)
        self.assertIn(view.run_metadata.run_id[:12], markdown)
        self.assertIn(view.market_data.data_sha256, code_values)
        self.assertIn(view.market_data.data_sha256[:16], markdown)
        self.assertNotIn("run_id（完整）", markdown)
        self.assertNotIn("run_id", [metric.label for metric in app.metric])
        self.assertNotIn("实际分析日期", [metric.label for metric in app.metric])

    def test_dark_palette_and_major_component_overrides_meet_readability_contract(
        self,
    ) -> None:
        for background in (
            DARK_THEME.page,
            DARK_THEME.surface,
            DARK_THEME.surface_muted,
            DARK_THEME.surface_elevated,
        ):
            self.assertGreaterEqual(contrast_ratio(DARK_THEME.text, background), 7.0)
            self.assertGreaterEqual(contrast_ratio(DARK_THEME.text_secondary, background), 7.0)
            self.assertGreaterEqual(contrast_ratio(DARK_THEME.text_muted, background), 4.5)
        self.assertGreaterEqual(
            contrast_ratio(DARK_THEME.on_accent, DARK_THEME.accent),
            4.5,
        )
        self.assertEqual(LIGHT_THEME.page, "#f5f7fb")
        self.assertEqual(LIGHT_THEME.surface, "#ffffff")
        self.assertEqual(LIGHT_THEME.text, "#14213d")
        self.assertEqual(LIGHT_THEME.dataframe_filter, "none")
        self.assertEqual(DARK_THEME.dataframe_filter, "invert(1) hue-rotate(180deg)")

        source = APP_PATH.read_text(encoding="utf-8")
        for selector in (
            '[data-testid="stSegmentedControl"]',
            '[data-testid="stButtonGroup"]',
            '[data-testid="stTabs"]',
            '[data-testid="stAlert"]',
            '[data-testid="stToast"]',
            '[data-testid="stNumberInputContainer"]',
            '[data-testid="stTextInputRootElement"]',
            '[data-baseweb="popover"]',
            '[data-testid="stDataFrameGlideDataEditor"]',
            "--ql-dataframe-filter",
            "#vg-tooltip-element.vg-tooltip",
        ):
            self.assertIn(selector, source)
        self.assertNotIn(
            "仅改变当前页面配色，不改变回测结果或导出文件。",
            source,
        )

    def test_result_navigation_has_a_visible_section_label_and_collapsed_widget_label(
        self,
    ) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        navigation_markup = [
            str(item.value) for item in app.markdown if "ql-result-nav-label" in str(item.value)
        ]

        self.assertEqual(result_navigation(app).label, "结果导航")
        self.assertTrue(any(">结果导航<" in item for item in navigation_markup))
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('label_visibility="collapsed"', source)
        self.assertIn("margin: 1.55rem 0 0.45rem", source)

    def test_dark_disclaimer_remains_readable_without_caption_opacity(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        keyed_toggle(app, "phase1_dark_mode").set_value(True).run(timeout=30)
        sidebar_markup = "\n".join(str(item.value) for item in app.sidebar.markdown)

        self.assertIn("仅用于研究与工程验证，不构成投资建议。", sidebar_markup)
        self.assertIn('class="ql-disclaimer"', sidebar_markup)
        self.assertGreaterEqual(
            contrast_ratio(DARK_THEME.text_muted, DARK_THEME.surface),
            4.5,
        )
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"\.ql-disclaimer\s*\{[^}]*"
            r"color:\s*var\(--ql-text-muted\)\s*!important;[^}]*"
            r"opacity:\s*1;",
        )

    def test_disabled_buttons_keep_a_visible_boundary_and_label(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        for selector in (
            '.stButton > button[aria-disabled="true"]',
            ".stButton > button:disabled p",
            '.stDownloadButton > button[aria-disabled="true"] span',
        ):
            self.assertIn(selector, source)
        self.assertRegex(
            source,
            r"\.stButton > button:disabled,[^{]*\{[^}]*"
            r"border-color:\s*var\(--ql-border-strong\)\s*!important;[^}]*"
            r"color:\s*var\(--ql-text-secondary\)\s*!important;[^}]*"
            r"cursor:\s*not-allowed\s*!important;",
        )
        self.assertIn('[data-testid="stTooltipContent"]', source)
        self.assertIn("max-width: min(20rem, calc(100vw - 1rem))", source)
        self.assertIn('[data-testid="stNumberInputStepDown"] svg', source)
        self.assertIn(
            '.st-key-phase1_chart_shell [data-testid="stElementToolbar"]',
            source,
        )
        self.assertIn("display: none !important", source)

    def test_assumptions_expander_header_uses_theme_surface(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        run_button(app).click().run(timeout=30)
        result_navigation(app).set_value("数据与假设").run(timeout=30)

        self.assertIn("数据与回测假设", [item.label for item in app.expander])
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('[data-testid="stExpander"] details > summary', source)
        self.assertIn('[data-testid="stExpanderDetails"]', source)
        self.assertRegex(
            source,
            r'\[data-testid="stExpander"\] details,[^{]*\{[^}]*'
            r"background:\s*var\(--ql-surface\)\s*!important;[^}]*"
            r"border-color:\s*var\(--ql-border\)\s*!important;",
        )

    def test_theme_switch_toast_appears_only_for_first_change(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        self.assertEqual(len(app.toast), 0)

        keyed_toggle(app, "phase1_dark_mode").set_value(True).run(timeout=30)
        self.assertEqual([item.value for item in app.toast], ["已切换为深色模式。"])

        keyed_toggle(app, "phase1_dark_mode").set_value(False).run(timeout=30)
        self.assertEqual(len(app.toast), 0)
        self.assertTrue(app.session_state["phase1_theme_toast_shown"])

    def test_dark_theme_is_ui_only_and_reuses_the_completed_run(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]

        keyed_toggle(app, "phase1_dark_mode").set_value(True).run(timeout=30)

        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)
        styles = "\n".join(str(item.value) for item in app.markdown)
        self.assertIn("--ql-page-background: #0b1220", styles)
        self.assertTrue(app.session_state["phase1_dark_mode"])

    def test_theme_switch_preserves_chart_data_and_export_hashes(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]
        equity_before = page_data.equity_chart.copy(deep=True)
        excess_before = page_data.excess_return_chart.copy(deep=True)
        hashes_before = output_hashes(output)

        keyed_toggle(app, "phase1_dark_mode").set_value(True).run(timeout=30)

        themed_output = app.session_state["phase1_run_output"]
        themed_page_data = app.session_state["phase1_page_data"]
        self.assertIs(themed_output, output)
        self.assertIs(themed_page_data, page_data)
        self.assertEqual(len(loader.calls), 1)
        self.assertTrue(themed_page_data.equity_chart.equals(equity_before))
        self.assertTrue(themed_page_data.excess_return_chart.equals(excess_before))
        self.assertEqual(output_hashes(themed_output), hashes_before)

    def test_sidebar_parameters_are_grouped_without_duplicate_controls(self) -> None:
        app = build_app(RecordingMarketDataLoader())
        sidebar_markdown = "\n".join(str(item.value) for item in app.sidebar.markdown)

        for heading in ("数据与区间", "策略参数", "资金与成本"):
            self.assertIn(heading, sidebar_markdown)
        self.assertEqual(len(app.sidebar.text_input), 3)
        self.assertEqual(len(app.sidebar.date_input), 0)
        self.assertEqual(len(app.sidebar.number_input), 5)

    def test_session_cache_layers_are_distinct_and_do_not_duplicate_workflow(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]
        run_id = output.report_view.run_metadata.run_id

        self.assertEqual(len(app.session_state["phase1_market_data_cache"]), 1)
        self.assertIs(app.session_state["phase1_presentation_cache"][run_id], page_data)
        self.assertNotIn("phase1_export_cache", app.session_state)

        app.run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)

        run_button(app).click().run(timeout=30)
        self.assertEqual(len(loader.calls), 1)
        self.assertTrue(app.session_state["phase1_run_timings"]["cache_hit"])
        self.assertTrue(app.session_state["phase1_run_timings"]["presentation_cache_hit"])
        self.assertLess(app.session_state["phase1_run_timings"]["total_seconds"], 1.0)
        self.assertIs(app.session_state["phase1_page_data"], page_data)

    def test_chart_views_reuse_bounded_display_data_and_preserve_full_equity(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        page_data = app.session_state["phase1_page_data"]
        original_equity = page_data.equity_chart.copy(deep=True)

        result_navigation(app).set_value("净值对比").run(timeout=30)
        control = chart_view_control(app)
        self.assertIn(CHART_VIEW_EXCESS, control.options)
        control.set_value(CHART_VIEW_EXCESS).run(timeout=30)

        self.assertEqual(len(loader.calls), 1)
        self.assertIs(app.session_state["phase1_run_output"], output)
        self.assertIs(app.session_state["phase1_page_data"], page_data)
        self.assertEqual(len(app.get("vega_lite_chart")), 1)
        self.assertIn(CHART_EXCESS_RETURN_COLUMN, page_data.excess_return_chart.columns)
        self.assertLessEqual(len(page_data.equity_chart_fast), DEFAULT_CHART_MAX_ROWS)
        self.assertLessEqual(len(page_data.excess_return_chart_fast), DEFAULT_CHART_MAX_ROWS)
        self.assertTrue(page_data.equity_chart.equals(original_equity))

    def test_exports_are_materialized_once_after_explicit_intent(self) -> None:
        loader = RecordingMarketDataLoader()
        app = build_app(loader)
        run_button(app).click().run(timeout=30)
        output = app.session_state["phase1_run_output"]
        run_id = output.report_view.run_metadata.run_id

        result_navigation(app).set_value("导出").run(timeout=30)
        self.assertEqual(app.session_state["phase1_export_cache"], {})
        self.assertEqual(len(app.get("download_button")), 0)

        prepare_exports_button(app).click().run(timeout=30)
        prepared = app.session_state["phase1_export_cache"][run_id]
        self.assertIsInstance(prepared, PreparedExportData)
        self.assertEqual(prepared.run_id, run_id)
        self.assertGreater(prepared.zip_size, 0)
        self.assertEqual(len(app.get("download_button")), 4)

        result_navigation(app).set_value("摘要").run(timeout=30)
        result_navigation(app).set_value("导出").run(timeout=30)
        self.assertIs(app.session_state["phase1_export_cache"][run_id], prepared)
        self.assertEqual(len(loader.calls), 1)

    def test_responsive_css_keeps_native_sidebar_recovery_controls(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 1366px)", source)
        self.assertIn("@media (min-width: 1600px)", source)
        self.assertIn('[data-testid="collapsedControl"]', source)
        self.assertIn("overflow-x: hidden", source)
        self.assertIsNone(
            re.search(
                r'\[data-testid="stStatusWidget"\][^{]*\{[^}]*display\s*:\s*none',
                source,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )
        self.assertIsNone(
            re.search(
                r'header\[data-testid="stHeader"\]\s*\{[^}]*'
                r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0)",
                source,
                flags=re.IGNORECASE | re.DOTALL,
            )
        )

    def test_keyboard_focus_is_visible_on_primary_interactive_components(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")

        for selector in (
            '[data-testid="stSegmentedControl"] button:focus-visible',
            '[data-testid="stTabs"] [role="tab"]:focus-visible',
            '[data-testid="stExpander"] summary:focus-visible',
            '[data-testid="stSidebarCollapseButton"] button:focus-visible',
            '[data-baseweb="input"] input:focus-visible',
        ):
            self.assertIn(selector, source)
        self.assertIn("outline: 2px solid var(--ql-accent) !important", source)
        self.assertNotRegex(source, r"outline\s*:\s*none")

    def test_windows_lifecycle_keeps_browser_isolation_and_defers_tray_dependency(self) -> None:
        launcher = WINDOWS_LAUNCHER_PATH.read_text(encoding="utf-8")
        guide = WINDOWS_README_PATH.read_text(encoding="utf-8")

        self.assertIn("run_desktop_session", launcher)
        self.assertIn("isolated_browser_is_active", launcher)
        self.assertIn("terminate_browser_process_tree", launcher)
        self.assertIn("--disable-extensions", launcher)
        self.assertNotIn("import pystray", launcher)
        self.assertIn("Windows 任务栏", guide)
        self.assertIn("当前不引入 pystray", guide)
        self.assertIn("释放本地端口", guide)


if __name__ == "__main__":
    unittest.main()
