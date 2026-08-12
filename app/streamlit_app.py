from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter

import streamlit as st

from app.components import (
    CHART_BENCHMARK_COLUMN,
    CHART_DATE_COLUMN,
    CHART_STRATEGY_COLUMN,
    CHART_VIEW_EQUITY,
    CHART_VIEW_EXCESS,
    DEFAULT_TRADE_PREVIEW_ROWS,
    MarketDataCacheKey,
    PreparedExportData,
    PreparedPageData,
    control_signature,
    export_zip_filename,
    format_file_size,
    friendly_error_message,
    friendly_export_error_message,
    market_data_cache_key,
    metrics_by_key,
    prepare_export_data,
    prepare_page_data,
    request_signature,
    theme_palette,
    validate_date_inputs,
    visible_trades_table,
)
from quant_lab.models import MarketDataResult
from quant_lab.workflow import (
    SpySmaRunOutput,
    SpySmaRunRequest,
    WorkflowStage,
    installed_software_version,
    run_spy_sma_workflow,
)

MARKET_DATA_CACHE_LIMIT = 4
PRESENTATION_CACHE_LIMIT = 4
EXPORT_CACHE_LIMIT = 4
RESULT_SUMMARY = "摘要"
RESULT_CHART = "净值对比"
RESULT_TRADES = "交易记录"
RESULT_DATA = "数据与假设"
RESULT_EXPORT = "导出"
CHART_DISPLAY_INTERACTIVE = "交互图"
CHART_DISPLAY_DATA = "查看数据"
LOGGER = logging.getLogger(__name__)

st.set_page_config(
    page_title="QuantLab",
    page_icon="QL",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles(*, dark_mode: bool) -> None:
    palette = theme_palette(dark_mode=dark_mode)
    st.markdown(
        f"""
        <style>
        :root {{
          color-scheme: {palette.color_scheme};
          --ql-page-background: {palette.page};
          --ql-surface: {palette.surface};
          --ql-surface-muted: {palette.surface_muted};
          --ql-surface-elevated: {palette.surface_elevated};
          --ql-surface-hover: {palette.surface_hover};
          --ql-border: {palette.border};
          --ql-border-strong: {palette.border_strong};
          --ql-text-primary: {palette.text};
          --ql-text-secondary: {palette.text_secondary};
          --ql-text-muted: {palette.text_muted};
          --ql-accent: {palette.accent};
          --ql-accent-hover: {palette.accent_hover};
          --ql-accent-soft: {palette.accent_soft};
          --ql-on-accent: {palette.on_accent};
          --ql-success: {palette.success};
          --ql-warning: {palette.warning};
          --ql-danger: {palette.danger};
          --ql-code-background: {palette.code};
          --ql-dataframe-filter: {palette.dataframe_filter};
          --ql-shadow: {palette.shadow};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        html, body {
          background: var(--ql-page-background);
          color: var(--ql-text-primary);
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
          background: var(--ql-page-background);
          color: var(--ql-text-primary);
        }
        .stApp { overflow-x: hidden; }
        .block-container {
          max-width: 1480px;
          min-width: 0;
          padding-top: 2.2rem;
          padding-bottom: 4rem;
        }
        header[data-testid="stHeader"] { background: transparent; }
        [data-testid="stDecoration"],
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenu"] { display: none; }
        [data-testid="collapsedControl"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
          align-items: center !important;
          box-sizing: border-box !important;
          display: flex !important;
          height: 2.5rem !important;
          justify-content: center !important;
          min-height: 2.5rem !important;
          min-width: 2.5rem !important;
          overflow: hidden !important;
          padding: 0 !important;
          transform: none !important;
          visibility: visible !important;
          width: 2.5rem !important;
          opacity: 1 !important;
          pointer-events: auto !important;
        }
        [data-testid="stSidebar"] {
          background: var(--ql-surface);
          border-right: 1px solid var(--ql-border);
          color: var(--ql-text-primary);
        }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.25rem; }
        [data-baseweb="input"],
        [data-baseweb="input"] > div,
        [data-baseweb="base-input"],
        [data-baseweb="select"] > div,
        [data-testid="stNumberInputContainer"],
        [data-testid="stTextInputRootElement"] {
          background: var(--ql-surface-muted) !important;
          border-color: var(--ql-border) !important;
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] label p {
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stWidgetLabel"] small,
        [data-testid="InputInstructions"],
        [data-testid="stTooltipIcon"] {
          color: var(--ql-text-muted) !important;
        }
        [data-baseweb="input"] input,
        [data-baseweb="base-input"] input,
        [data-baseweb="select"] input,
        [data-testid="stNumberInputField"],
        [data-testid="stTextInputRootElement"] input {
          background: transparent !important;
          color: var(--ql-text-primary) !important;
          -webkit-text-fill-color: var(--ql-text-primary) !important;
        }
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="base-input"] input::placeholder {
          color: var(--ql-text-muted) !important;
          opacity: 1;
        }
        input:disabled {
          color: var(--ql-text-secondary) !important;
          -webkit-text-fill-color: var(--ql-text-secondary) !important;
          opacity: 1 !important;
        }
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepDown"],
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepUp"] {
          align-items: center !important;
          background: var(--ql-surface-muted) !important;
          border-color: var(--ql-border) !important;
          color: var(--ql-text-primary) !important;
          display: inline-flex !important;
          flex: 0 0 2rem;
          height: 100% !important;
          justify-content: center !important;
          line-height: 1 !important;
          min-width: 2rem !important;
          overflow: hidden !important;
          padding: 0 !important;
          transform: none !important;
          width: 2rem !important;
        }
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepDown"] svg,
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepUp"] svg {
          display: block;
          fill: currentColor !important;
          flex: 0 0 auto;
          height: 0.625rem !important;
          max-height: 0.625rem;
          max-width: 0.625rem;
          transform: none !important;
          width: 0.625rem !important;
        }
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepDown"]:hover,
        [data-testid="stNumberInput"] [data-testid="stNumberInputStepUp"]:hover {
          background: var(--ql-surface-hover) !important;
          border-color: var(--ql-border-strong) !important;
        }
        [data-testid="stTooltipIcon"] button {
          align-items: center;
          color: var(--ql-text-muted) !important;
          display: inline-flex;
          height: 1rem;
          justify-content: center;
          line-height: 0;
          overflow: hidden;
          padding: 0;
          transform: none !important;
          width: 1rem;
        }
        [data-testid="stTooltipIcon"] button svg {
          color: inherit !important;
          height: 1rem !important;
          max-height: 1rem;
          max-width: 1rem;
          stroke: currentColor !important;
          transform: none !important;
          width: 1rem !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stExpandSidebarButton"] button,
        [data-testid="collapsedControl"] button {
          align-items: center !important;
          background: var(--ql-surface-muted) !important;
          border: 1px solid var(--ql-border) !important;
          box-sizing: border-box !important;
          color: var(--ql-text-primary) !important;
          border-radius: 8px;
          display: flex !important;
          height: 2.5rem !important;
          justify-content: center !important;
          line-height: 1 !important;
          margin: 0 !important;
          min-height: 2.5rem !important;
          min-width: 2.5rem !important;
          overflow: hidden !important;
          padding: 0.625rem !important;
          position: static !important;
          transform: none !important;
          width: 2.5rem !important;
        }
        [data-testid="stSidebarCollapseButton"] button span,
        [data-testid="stExpandSidebarButton"] button span,
        [data-testid="collapsedControl"] button span {
          align-items: center !important;
          color: var(--ql-text-primary) !important;
          display: flex !important;
          height: 1rem !important;
          justify-content: center !important;
          line-height: 1 !important;
          margin: 0 !important;
          overflow: hidden !important;
          padding: 0 !important;
          position: static !important;
          transform: none !important;
          width: 1rem !important;
        }
        [data-testid="stSidebarCollapseButton"] button svg,
        [data-testid="stExpandSidebarButton"] button svg,
        [data-testid="collapsedControl"] button svg {
          display: block !important;
          fill: currentColor !important;
          height: 1rem !important;
          margin: 0 !important;
          max-height: 1rem !important;
          max-width: 1rem !important;
          position: static !important;
          stroke: currentColor !important;
          transform: none !important;
          width: 1rem !important;
        }
        h1, h2, h3, h4 { color: var(--ql-text-primary); letter-spacing: 0; }
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] strong,
        [data-testid="stText"],
        [data-testid="stWidgetLabel"] p {
          color: var(--ql-text-primary);
        }
        p, span, label {
          overflow-wrap: anywhere;
        }
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {
          color: var(--ql-text-secondary) !important;
        }
        h1 { font-size: 2.25rem; font-weight: 720; }
        h3 { margin-top: 1.5rem; }
        [data-testid="stMetric"] {
          background: var(--ql-surface);
          border: 1px solid var(--ql-border);
          border-radius: 8px;
          padding: 0.85rem 1rem;
          min-height: 96px;
        }
        [data-testid="stMetricLabel"] { color: var(--ql-text-secondary); }
        [data-testid="stMetricValue"] { color: var(--ql-text-primary); }
        div[data-testid="stDataFrame"], div[data-testid="stVegaLiteChart"] {
          background: var(--ql-surface);
          border: 1px solid var(--ql-border);
          border-radius: 8px;
          padding: 0.55rem;
        }
        .st-key-phase1_chart_shell [data-testid="stElementToolbar"] {
          display: none !important;
          pointer-events: none !important;
          visibility: hidden !important;
        }
        .st-key-phase1_chart_controls [data-testid="stVerticalBlockBorderWrapper"] {
          background: var(--ql-surface);
          border-color: var(--ql-border-strong) !important;
          border-radius: 8px;
        }
        .ql-chart-domain {
          color: var(--ql-text-secondary);
          font-size: 0.78rem;
          line-height: 1.45;
          margin: 0.15rem 0 0;
          overflow-wrap: anywhere;
        }
        [data-testid="stStatusWidget"],
        [data-testid="stExpander"],
        [data-testid="stAlert"] {
          background: var(--ql-surface) !important;
          border-color: var(--ql-border) !important;
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] details > summary,
        [data-testid="stExpanderDetails"] {
          background: var(--ql-surface) !important;
          border-color: var(--ql-border) !important;
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stStatusWidget"] p,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary p,
        [data-testid="stAlert"] p {
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stExpander"] details[open] > summary {
          border-bottom: 1px solid var(--ql-border) !important;
        }
        [data-testid="stExpander"] summary svg {
          color: var(--ql-text-secondary) !important;
          fill: var(--ql-text-secondary) !important;
        }
        [data-testid="stExpander"] summary:hover {
          background: var(--ql-surface-hover) !important;
        }
        [data-testid="stSegmentedControl"] [role="radiogroup"],
        [data-testid="stButtonGroup"] {
          background: var(--ql-surface-muted);
          border: 1px solid var(--ql-border-strong);
          border-radius: 8px;
        }
        [data-testid="stSegmentedControl"] button,
        [data-testid="stButtonGroup"] button {
          background: transparent !important;
          border-color: transparent !important;
          color: var(--ql-text-secondary) !important;
          transition:
            background-color 120ms ease,
            border-color 120ms ease,
            color 120ms ease;
        }
        [data-testid="stSegmentedControl"] button p,
        [data-testid="stButtonGroup"] button p {
          color: inherit !important;
        }
        [data-testid="stSegmentedControl"] button:hover,
        [data-testid="stButtonGroup"] button:hover {
          background: var(--ql-surface-hover) !important;
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        [data-testid="stSegmentedControl"] button[aria-checked="true"],
        [data-testid="stButtonGroup"] button[aria-checked="true"] {
          background: var(--ql-accent-soft) !important;
          border-color: var(--ql-accent) !important;
          color: var(--ql-accent-hover) !important;
          box-shadow: inset 0 0 0 1px var(--ql-accent);
        }
        [data-testid="stSegmentedControl"] button:disabled,
        [data-testid="stSegmentedControl"] button[aria-disabled="true"],
        [data-testid="stButtonGroup"] button:disabled,
        [data-testid="stButtonGroup"] button[aria-disabled="true"] {
          background: var(--ql-surface-muted) !important;
          border-color: transparent !important;
          color: var(--ql-text-muted) !important;
          cursor: not-allowed !important;
          opacity: 1 !important;
        }
        [data-testid="stTabs"] [role="tablist"] {
          border-bottom: 1px solid var(--ql-border-strong) !important;
        }
        [data-testid="stTabs"] [role="tab"] {
          color: var(--ql-text-secondary) !important;
          border-color: transparent !important;
        }
        [data-testid="stTabs"] [role="tab"]:hover {
          background: var(--ql-surface-hover) !important;
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
          border-bottom-color: var(--ql-accent) !important;
          color: var(--ql-text-primary) !important;
        }
        .stButton > button,
        .stDownloadButton > button {
          background: var(--ql-surface) !important;
          border-color: var(--ql-border) !important;
          color: var(--ql-text-primary) !important;
          border-radius: 8px;
          min-height: 2.75rem;
          font-weight: 650;
        }
        .stButton > button:not(:disabled):not([aria-disabled="true"]):hover,
        .stDownloadButton > button:not(:disabled):not([aria-disabled="true"]):hover {
          background: var(--ql-surface-hover) !important;
          border-color: var(--ql-border-strong) !important;
          color: var(--ql-text-primary) !important;
        }
        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible,
        [data-testid="stSegmentedControl"] button:focus-visible,
        [data-testid="stButtonGroup"] button:focus-visible,
        [data-testid="stTabs"] [role="tab"]:focus-visible,
        [data-testid="stExpander"] summary:focus-visible,
        [data-testid="stSidebarCollapseButton"] button:focus-visible,
        [data-testid="stExpandSidebarButton"] button:focus-visible,
        [data-testid="collapsedControl"] button:focus-visible,
        [data-baseweb="input"] input:focus-visible,
        [data-testid="stNumberInputField"]:focus-visible {
          outline: 2px solid var(--ql-accent) !important;
          outline-offset: 2px;
        }
        .stButton > button:active,
        .stDownloadButton > button:active {
          background: var(--ql-surface-elevated) !important;
        }
        .stButton > button[kind="primary"] {
          background: var(--ql-accent) !important;
          border-color: var(--ql-accent) !important;
          color: var(--ql-on-accent) !important;
        }
        .stButton > button[kind="primary"] p {
          color: var(--ql-on-accent) !important;
        }
        .stButton > button[kind="primary"]:hover {
          background: var(--ql-accent-hover) !important;
          border-color: var(--ql-accent-hover) !important;
          color: var(--ql-on-accent) !important;
        }
        .stButton > button:disabled,
        .stButton > button[aria-disabled="true"],
        .stDownloadButton > button:disabled,
        .stDownloadButton > button[aria-disabled="true"] {
          background: var(--ql-surface-muted) !important;
          border-color: var(--ql-border-strong) !important;
          color: var(--ql-text-secondary) !important;
          cursor: not-allowed !important;
          opacity: 1 !important;
        }
        .stButton > button:disabled p,
        .stButton > button:disabled span,
        .stButton > button[aria-disabled="true"] p,
        .stButton > button[aria-disabled="true"] span,
        .stDownloadButton > button:disabled p,
        .stDownloadButton > button:disabled span,
        .stDownloadButton > button[aria-disabled="true"] p,
        .stDownloadButton > button[aria-disabled="true"] span {
          color: var(--ql-text-secondary) !important;
          -webkit-text-fill-color: var(--ql-text-secondary) !important;
          opacity: 1 !important;
        }
        .stButton > button:disabled svg,
        .stButton > button[aria-disabled="true"] svg,
        .stDownloadButton > button:disabled svg,
        .stDownloadButton > button[aria-disabled="true"] svg {
          fill: currentColor !important;
          stroke: currentColor !important;
        }
        [data-testid="stAlert"] { border-radius: 8px; }
        [data-testid="stCode"] {
          background: var(--ql-code-background);
          border: 1px solid var(--ql-border);
          border-radius: 8px;
          overflow-wrap: anywhere;
        }
        [data-testid="stCode"] code,
        [data-testid="stCode"] pre,
        [data-testid="stCode"] button {
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stMarkdownContainer"] code {
          background: var(--ql-code-background);
          color: var(--ql-accent-hover);
          border: 1px solid var(--ql-border);
          border-radius: 5px;
          padding: 0.08rem 0.28rem;
        }
        [data-testid="stToast"] {
          background: var(--ql-surface-elevated) !important;
          border: 1px solid var(--ql-border-strong) !important;
          color: var(--ql-text-primary) !important;
          box-shadow: 0 10px 30px var(--ql-shadow);
        }
        [data-testid="stToast"] p { color: var(--ql-text-primary) !important; }
        [data-baseweb="popover"] > div,
        [data-baseweb="menu"],
        [role="listbox"] {
          background: var(--ql-surface-elevated) !important;
          border-color: var(--ql-border-strong) !important;
          color: var(--ql-text-primary) !important;
        }
        [role="option"] {
          color: var(--ql-text-primary) !important;
        }
        [role="option"]:hover {
          background: var(--ql-surface-hover) !important;
        }
        [role="option"][aria-selected="true"] {
          background: var(--ql-accent-soft) !important;
          color: var(--ql-accent-hover) !important;
        }
        [data-baseweb="tooltip"],
        [role="tooltip"],
        [data-testid="stTooltipContent"] {
          background: var(--ql-surface-elevated) !important;
          color: var(--ql-text-primary) !important;
        }
        [role="tooltip"] {
          max-width: min(20rem, calc(100vw - 1rem)) !important;
          z-index: 1000060 !important;
        }
        [data-testid="stTooltipContent"] {
          border: 1px solid var(--ql-border-strong) !important;
          box-shadow: 0 10px 28px var(--ql-shadow) !important;
          box-sizing: border-box;
          max-height: min(18rem, calc(100vh - 1rem)) !important;
          max-width: min(20rem, calc(100vw - 1rem)) !important;
          opacity: 1 !important;
          overflow: auto !important;
          overflow-wrap: anywhere !important;
          padding: 0.55rem 0.7rem !important;
          white-space: normal !important;
        }
        [data-testid="stTooltipContent"] *,
        [data-testid="stTooltipContent"] p {
          color: inherit !important;
          opacity: 1 !important;
          overflow-wrap: anywhere !important;
          white-space: normal !important;
        }
        [data-testid="stTooltipContent"] p {
          line-height: 1.45;
          margin: 0;
        }
        #vg-tooltip-element.vg-tooltip,
        .vg-tooltip {
          background: var(--ql-surface-elevated) !important;
          border: 1px solid var(--ql-border-strong) !important;
          border-radius: 8px !important;
          box-sizing: border-box !important;
          color: var(--ql-text-primary) !important;
          box-shadow: 0 10px 28px var(--ql-shadow) !important;
          font-size: 0.82rem !important;
          line-height: 1.4 !important;
          max-width: min(18rem, calc(100vw - 1rem)) !important;
          opacity: 1 !important;
          overflow-wrap: anywhere !important;
          padding: 0.5rem 0.65rem !important;
          pointer-events: none !important;
          white-space: normal !important;
          z-index: 1000050 !important;
        }
        #vg-tooltip-element.vg-tooltip table,
        .vg-tooltip table {
          border-collapse: collapse !important;
          table-layout: auto !important;
          width: 100% !important;
        }
        #vg-tooltip-element.vg-tooltip tr,
        #vg-tooltip-element.vg-tooltip tr:last-child,
        .vg-tooltip tr,
        .vg-tooltip tr:last-child {
          background: transparent !important;
          border: 0 !important;
          font-weight: 400 !important;
        }
        #vg-tooltip-element.vg-tooltip td,
        #vg-tooltip-element.vg-tooltip th,
        .vg-tooltip td,
        .vg-tooltip th {
          background: transparent !important;
          border: 0 !important;
          color: var(--ql-text-primary) !important;
          font-weight: 400 !important;
          line-height: 1.4 !important;
          padding: 0.16rem 0 !important;
          vertical-align: baseline !important;
        }
        #vg-tooltip-element.vg-tooltip td.key,
        .vg-tooltip td.key {
          color: var(--ql-text-secondary) !important;
          padding-right: 0.9rem !important;
          text-align: left !important;
          white-space: nowrap !important;
          width: 5.5rem !important;
        }
        #vg-tooltip-element.vg-tooltip td.value,
        .vg-tooltip td.value {
          color: var(--ql-text-primary) !important;
          font-variant-numeric: tabular-nums;
          text-align: right !important;
          white-space: nowrap !important;
        }
        [data-testid="stDataFrameGlideDataEditor"] {
          --gdg-accent-color: var(--ql-accent) !important;
          --gdg-text-dark: var(--ql-text-primary) !important;
          --gdg-text-medium: var(--ql-text-secondary) !important;
          --gdg-text-light: var(--ql-text-muted) !important;
          --gdg-text-header: var(--ql-text-primary) !important;
          --gdg-bg-cell: var(--ql-surface) !important;
          --gdg-bg-cell-medium: var(--ql-surface-muted) !important;
          --gdg-bg-header: var(--ql-surface-muted) !important;
          --gdg-bg-header-hovered: var(--ql-surface-hover) !important;
          --gdg-border-color: var(--ql-border) !important;
        }
        [data-testid="stDataFrame"] canvas {
          filter: var(--ql-dataframe-filter);
        }
        [data-testid="stDataFrame"] button {
          color: var(--ql-text-primary) !important;
        }
        [data-testid="stDataFrame"] button:hover {
          background: var(--ql-surface-hover) !important;
        }
        .ql-kicker { color: var(--ql-accent); font-size: 0.82rem; font-weight: 750; }
        .ql-intro {
          color: var(--ql-text-secondary);
          font-size: 1.02rem;
          margin-top: -0.7rem;
        }
        .ql-run-strip {
          background: var(--ql-surface);
          border: 1px solid var(--ql-border);
          border-radius: 8px;
          box-shadow: 0 8px 24px var(--ql-shadow);
          color: var(--ql-text-secondary);
          margin: 0.35rem 0 1rem;
          padding: 0.75rem 0.9rem;
        }
        .ql-run-strip strong { color: var(--ql-text-primary); }
        [data-testid="stVerticalBlockBorderWrapper"] {
          background: var(--ql-surface);
          border-color: var(--ql-border) !important;
        }
        .ql-result-nav-label {
          color: var(--ql-text-secondary);
          font-size: 0.78rem;
          font-weight: 720;
          line-height: 1.25;
          margin: 1.55rem 0 0.45rem;
        }
        .ql-identity-row {
          color: var(--ql-text-secondary);
          margin: 0.95rem 0 0.45rem;
        }
        .ql-identity-label {
          color: var(--ql-text-secondary);
          display: block;
          font-size: 0.84rem;
          font-weight: 700;
          margin-bottom: 0.3rem;
        }
        .ql-identity-row code {
          background: var(--ql-code-background);
          border: 1px solid var(--ql-border);
          border-radius: 5px;
          color: var(--ql-accent-hover);
          padding: 0.08rem 0.28rem;
        }
        .ql-disclaimer {
          color: var(--ql-text-muted) !important;
          font-size: 0.8rem;
          font-weight: 500;
          line-height: 1.5;
          margin: 1rem 0 0.35rem;
          opacity: 1;
        }
        .ql-sidebar-section {
          color: var(--ql-text-secondary);
          font-size: 0.72rem;
          font-weight: 760;
          letter-spacing: 0.08em;
          margin: 1.15rem 0 0.45rem;
          text-transform: uppercase;
        }
        div[data-testid="stHorizontalBlock"] { min-width: 0; }
        div[data-testid="column"] { min-width: 0; }
        [data-testid="stDataFrame"] { max-width: 100%; overflow: auto; }
        [data-testid="stCode"] pre { white-space: pre-wrap; overflow-wrap: anywhere; }
        @media (max-width: 1366px) {
          .block-container { padding: 1.7rem 1.35rem 3.5rem; }
          h1 { font-size: 2rem; }
          [data-testid="stMetricValue"] { font-size: 1.55rem; }
        }
        @media (max-width: 900px) {
          .block-container { padding: 1.4rem 1rem 3rem; }
          h1 { font-size: 1.85rem; }
          [data-testid="stMetric"] { min-height: 88px; padding: 0.7rem 0.8rem; }
        }
        @media (min-width: 1600px) {
          .block-container { max-width: 1520px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _show_theme_toast_once(*, dark_mode: bool) -> None:
    previous_mode = st.session_state.get("phase1_previous_dark_mode")
    st.session_state["phase1_previous_dark_mode"] = dark_mode
    if previous_mode is None or previous_mode == dark_mode:
        return
    if st.session_state.get("phase1_theme_toast_shown", False):
        return
    label = "深色" if dark_mode else "浅色"
    st.toast(f"已切换为{label}模式。")
    st.session_state["phase1_theme_toast_shown"] = True


def _render_summary(
    output: SpySmaRunOutput,
    run_timings: dict[str, object] | None,
) -> None:
    view = output.report_view
    run = view.run_metadata
    market = view.market_data
    st.subheader("运行详情")
    timings = run_timings if isinstance(run_timings, dict) else {}
    total_seconds = timings.get("total_seconds")
    elapsed_display = (
        f"{float(total_seconds):.2f} 秒" if isinstance(total_seconds, (int, float)) else "未记录"
    )
    cache_display = "命中，会话内复用" if timings.get("cache_hit") else "未命中，本次获取"
    st.markdown(
        (
            '<div class="ql-run-strip">'
            f"<strong>运行完成</strong> · 耗时 {elapsed_display} · 行情缓存{cache_display}"
            f" · 数据日期 {view.analysis_date_range_display}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        left, right = st.columns(2, gap="large")
        with left:
            st.markdown(
                f"**标的与策略**  \n{run.symbol} · SMA {run.short_window} / {run.long_window}"
            )
            st.markdown(f"**实际分析日期**  \n{view.analysis_date_range_display}")
            st.markdown(f"**数据来源**  \n{market.source} {market.source_version}")
        with right:
            st.markdown(f"**软件版本**  \n{run.software_version}")
            st.markdown(f"**预热行数**  \n{market.warmup_row_count}")
            st.markdown(f"**交易状态**  \n{view.strategy_trade_count} 笔记录")

        st.markdown(
            (
                '<div class="ql-identity-row">'
                '<span class="ql-identity-label">run_id（短）</span>'
                f"<code>{run.run_id[:12]}</code>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        with st.expander("查看并复制完整 run_id"):
            st.code(run.run_id, language=None, wrap_lines=True)
            st.caption("使用代码框右上角的复制按钮获取完整原值。")
        st.markdown(
            (
                '<div class="ql-identity-row">'
                '<span class="ql-identity-label">数据 SHA256（短）</span>'
                f"<code>{market.data_sha256[:16]}</code>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        with st.expander("展开并复制完整数据 SHA256"):
            st.code(market.data_sha256, language=None, wrap_lines=True)
            st.caption("使用代码框右上角的复制按钮获取完整原值。")


def _render_metrics(output: SpySmaRunOutput) -> None:
    view = output.report_view
    strategy = metrics_by_key(view, "strategy")
    benchmark = metrics_by_key(view, "benchmark")

    st.subheader("核心指标")
    cards = (
        (strategy["final_equity"].label, strategy["final_equity"].display_value),
        (strategy["total_return"].label, strategy["total_return"].display_value),
        (strategy["max_drawdown"].label, strategy["max_drawdown"].display_value),
        (
            strategy["closed_trade_count"].label,
            strategy["closed_trade_count"].display_value,
        ),
        (strategy["win_rate"].label, strategy["win_rate"].display_value),
        (strategy["total_fees"].label, strategy["total_fees"].display_value),
        (
            strategy["total_slippage_cost"].label,
            strategy["total_slippage_cost"].display_value,
        ),
        ("买入持有收益", benchmark["total_return"].display_value),
        (view.excess_return.label, view.excess_return.display_value),
    )
    for offset in range(0, len(cards), 3):
        columns = st.columns(3)
        for column, (label, display_value) in zip(
            columns,
            cards[offset : offset + 3],
            strict=True,
        ):
            column.metric(label, display_value)


@st.fragment
def _render_chart(page_data: PreparedPageData, *, dark_mode: bool) -> None:
    st.subheader("交互图表")
    first_equity = page_data.equity_chart.iloc[0]
    last_equity = page_data.equity_chart.iloc[-1]
    first_date = first_equity[CHART_DATE_COLUMN].date().isoformat()
    last_date = last_equity[CHART_DATE_COLUMN].date().isoformat()
    with st.container(key="phase1_chart_controls", border=True):
        content_column, display_column = st.columns(2)
        with content_column:
            chart_view = st.segmented_control(
                "图表内容",
                options=(CHART_VIEW_EQUITY, CHART_VIEW_EXCESS),
                default=CHART_VIEW_EQUITY,
                key=f"phase1_chart_view_{page_data.run_id}",
            )
        with display_column:
            display_mode = st.segmented_control(
                "显示方式",
                options=(CHART_DISPLAY_INTERACTIVE, CHART_DISPLAY_DATA),
                default=CHART_DISPLAY_INTERACTIVE,
                key=f"phase1_chart_display_{page_data.run_id}",
            )
        reset_column, resolution_column = st.columns(2)
        with reset_column:
            reset_view = st.button(
                "重置视图",
                key=f"phase1_chart_reset_{page_data.run_id}",
                disabled=display_mode != CHART_DISPLAY_INTERACTIVE,
                width="stretch",
            )
        with resolution_column:
            full_resolution = st.toggle(
                "显示完整分辨率",
                value=False,
                key=f"phase1_full_equity_{page_data.run_id}",
                help="只改变交互图和数据视图的显示点数，不改变回测、指标或导出文件。",
            )
        st.markdown(
            (
                '<div class="ql-chart-domain" '
                f'data-start-date="{first_date}" data-end-date="{last_date}" '
                f'data-start-strategy="{first_equity[CHART_STRATEGY_COLUMN]:.10f}" '
                f'data-end-strategy="{last_equity[CHART_STRATEGY_COLUMN]:.10f}" '
                f'data-start-benchmark="{first_equity[CHART_BENCHMARK_COLUMN]:.10f}" '
                f'data-end-benchmark="{last_equity[CHART_BENCHMARK_COLUMN]:.10f}">'
                f"完整日期范围 {first_date} 至 {last_date} · "
                f"完整权益序列 {len(page_data.equity_chart):,} 个交易日"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    if chart_view == CHART_VIEW_EXCESS:
        complete_chart = page_data.excess_return_chart
        chart_frame = (
            page_data.excess_return_chart if full_resolution else page_data.excess_return_chart_fast
        )
        chart_spec = (
            page_data.excess_return_chart_spec_dark
            if dark_mode
            else page_data.excess_return_chart_spec
        )
        chart_key = "excess"
    else:
        complete_chart = page_data.equity_chart
        chart_frame = page_data.equity_chart if full_resolution else page_data.equity_chart_fast
        chart_spec = page_data.equity_chart_spec_dark if dark_mode else page_data.equity_chart_spec
        chart_key = "equity"
    reset_state_key = f"phase1_chart_reset_state_{page_data.run_id}"
    reset_state = int(st.session_state.get(reset_state_key, 0))
    if reset_view:
        reset_state += 1
        st.session_state[reset_state_key] = reset_state

    if display_mode == CHART_DISPLAY_DATA:
        st.dataframe(
            chart_frame,
            hide_index=True,
            width="stretch",
            height=min(560, 34 * (len(chart_frame) + 1)),
            column_config={
                "日期": st.column_config.DatetimeColumn("日期", format="YYYY-MM-DD"),
            },
        )
        st.caption(
            f"图表数据共显示 {len(chart_frame):,} / {len(complete_chart):,} 个交易日；"
            "切换显示方式不会重新运行回测。"
        )
        return

    with st.container(key="phase1_chart_shell"):
        st.vega_lite_chart(
            chart_frame,
            spec=chart_spec,
            width="stretch",
            height=360,
            theme=None,
            key=(
                f"phase1_chart_{page_data.run_id}_{chart_key}_"
                f"{'dark' if dark_mode else 'light'}_"
                f"{'full' if full_resolution else 'fast'}_{reset_state}"
            ),
            on_select="ignore",
        )
    if chart_view == CHART_VIEW_EQUITY:
        st.caption(
            "悬停查看精确日期与净值；拖拽或滚轮可缩放日期轴；点击图例可聚焦单条曲线或恢复全部。"
        )
    else:
        st.caption(
            "悬停查看精确日期与超额收益；累计超额收益率 ="
            "（策略净值 - 买入持有净值）/ 初始资金，仅用于页面比较。"
        )
    if len(chart_frame) < len(complete_chart):
        st.caption(
            f"交互图采用确定性极值保留抽样：显示 {len(chart_frame):,} / "
            f"{len(complete_chart):,} 个交易日。"
            "指标、交易账本与导出报告始终基于完整权益序列。"
        )
    else:
        st.caption("当前显示完整正式分析日期序列；页面交互不会重新执行回测。")


@st.fragment
def _render_trades(page_data: PreparedPageData) -> None:
    st.subheader("交易记录")
    table = page_data.trades_table
    if table.empty:
        st.info("本次策略没有交易记录。")
        return
    total_rows = len(table)
    show_all = total_rows <= DEFAULT_TRADE_PREVIEW_ROWS
    if not show_all:
        show_all = st.toggle(
            f"显示全部 {total_rows} 笔交易",
            value=False,
            key=f"phase1_show_all_trades_{page_data.run_id}",
        )
    visible = visible_trades_table(table, show_all=show_all)
    st.caption(f"共 {total_rows} 笔，当前显示 {len(visible)} 笔；下载的交易 CSV 始终包含完整账本。")
    st.dataframe(
        visible,
        hide_index=True,
        width="stretch",
        height=min(560, 42 * (len(visible) + 1)),
    )


def _render_research_workspace(
    output: SpySmaRunOutput,
    page_data: PreparedPageData,
    *,
    run_timings: dict[str, object] | None,
    dark_mode: bool,
) -> None:
    st.markdown(
        '<div class="ql-result-nav-label">结果导航</div>',
        unsafe_allow_html=True,
    )
    selection = st.segmented_control(
        "结果导航",
        options=(RESULT_SUMMARY, RESULT_CHART, RESULT_TRADES, RESULT_DATA, RESULT_EXPORT),
        default=RESULT_SUMMARY,
        selection_mode="single",
        key="phase1_result_section",
        label_visibility="collapsed",
    )
    if selection == RESULT_CHART:
        _render_chart(page_data, dark_mode=dark_mode)
    elif selection == RESULT_TRADES:
        _render_trades(page_data)
    elif selection == RESULT_DATA:
        _render_assumptions(output)
    elif selection == RESULT_EXPORT:
        _render_downloads(output)
    else:
        _render_summary(output, run_timings)
        _render_metrics(output)


def _render_assumptions(output: SpySmaRunOutput) -> None:
    view = output.report_view
    market = view.market_data
    with st.expander("数据与回测假设"):
        st.markdown(
            "\n".join(
                (
                    f"- 数据来源：{market.source} {market.source_version}",
                    f"- 抓取时间（UTC）：{view.market_fetched_at_display}",
                    f"- 实际数据日期：{view.actual_data_range_display}",
                    f"- 正式分析日期：{view.analysis_date_range_display}",
                    f"- 预热行数：{market.warmup_row_count}",
                    f"- 调整方式：{market.adjustment_method}",
                    f"- 数据 SHA256：`{market.data_sha256}`",
                )
            )
        )
        for assumption in view.assumptions:
            st.markdown(f"- {assumption}")
        for warning in view.warnings:
            st.warning(warning)
        st.info(
            "相同软件版本、标准化数据、参数和数据指纹能够复现相同计算结果；"
            "上游数据提供器可能修订历史数据，抓取时间本身不代表永久可复现。"
        )


@st.fragment
def _render_downloads(output: SpySmaRunOutput) -> None:
    view = output.report_view
    run_id = view.run_metadata.run_id
    st.subheader("导出结果")
    st.caption("运行完成时不会注册下载资源。请明确准备后，再选择需要的文件。")
    export_cache = st.session_state.get("phase1_export_cache")
    if not isinstance(export_cache, dict):
        export_cache = {}
        st.session_state["phase1_export_cache"] = export_cache
    prepared = export_cache.get(run_id)
    if not isinstance(prepared, PreparedExportData):
        if not st.button(
            "准备导出文件",
            type="primary",
            width="stretch",
            key=f"phase1_prepare_exports_{run_id}",
        ):
            return
        try:
            prepared = prepare_export_data(output)
        except Exception as error:
            LOGGER.warning("Export preparation failed (%s).", type(error).__name__)
            st.error(friendly_export_error_message(error))
            return
        _remember_bounded_cache(
            export_cache,
            run_id,
            prepared,
            limit=EXPORT_CACHE_LIMIT,
        )
        st.session_state["phase1_export_cache"] = export_cache

    st.success("导出文件已就绪。下载不会重新获取行情或执行回测。")
    st.markdown(
        "\n".join(
            (
                f"**生成时间（UTC）**：{prepared.generated_at_display}",
                f"**run_id**：`{prepared.run_id}`",
                (
                    "**文件大小**："
                    f"HTML {format_file_size(prepared.html_size)} · "
                    f"CSV {format_file_size(prepared.csv_size)} · "
                    f"Manifest {format_file_size(prepared.manifest_size)} · "
                    f"ZIP {format_file_size(prepared.zip_size)}"
                ),
            )
        )
    )
    columns = st.columns(2)
    columns[0].download_button(
        "下载 HTML 报告",
        data=lambda: output.html_report,
        file_name=view.html_filename,
        mime="text/html",
        on_click="ignore",
        width="stretch",
        key=f"phase1_download_html_{run_id}",
    )
    columns[1].download_button(
        "下载交易 CSV",
        data=lambda: output.trades_csv,
        file_name=view.csv_filename,
        mime="text/csv",
        on_click="ignore",
        width="stretch",
        key=f"phase1_download_csv_{run_id}",
    )
    columns = st.columns(2)
    columns[0].download_button(
        "下载 Manifest JSON",
        data=lambda: output.manifest_json,
        file_name=view.manifest_filename,
        mime="application/json",
        on_click="ignore",
        width="stretch",
        key=f"phase1_download_manifest_{run_id}",
    )
    columns[1].download_button(
        "下载全部结果 ZIP",
        data=lambda: prepared.zip_bytes,
        file_name=export_zip_filename(output),
        mime="application/zip",
        on_click="ignore",
        width="stretch",
        key=f"phase1_download_zip_{run_id}",
    )


def _remember_bounded_cache(
    cache: dict[object, object],
    key: object,
    value: object,
    *,
    limit: int,
) -> None:
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > limit:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key)


def _remember_market_data(
    cache: dict[MarketDataCacheKey, MarketDataResult],
    key: MarketDataCacheKey,
    market_data: MarketDataResult,
) -> None:
    _remember_bounded_cache(
        cache,
        key,
        market_data,
        limit=MARKET_DATA_CACHE_LIMIT,
    )


def _cached_market_data_loader(market_data: MarketDataResult):
    def load_cached_market_data(*args, **kwargs) -> MarketDataResult:
        return market_data

    return load_cached_market_data


def _workflow_stage_label(stage: WorkflowStage, *, cache_hit: bool) -> str:
    if stage == "market_data_fetch":
        return "1/6 准备数据（会话缓存命中）" if cache_hit else "1/6 准备数据"
    labels = {
        "market_data_standardize": "2/6 标准化行情",
        "sma_signal": "3/6 生成信号",
        "cash_ledger": "4/6 执行回测",
        "presentation": "5/6 生成展示模型与导出结果",
        "html_report": "5/6 生成展示模型与导出结果",
        "trades_csv": "5/6 生成展示模型与导出结果",
        "manifest": "5/6 生成展示模型与导出结果",
    }
    return labels[stage]


def _run_submitted_workflow(
    request: SpySmaRunRequest,
    *,
    software_version: str,
    force_refresh: bool,
) -> None:
    st.session_state.pop("phase1_run_output", None)
    st.session_state.pop("phase1_page_data", None)
    st.session_state.pop("phase1_run_timings", None)
    st.session_state.pop("phase1_result_section", None)

    cache = st.session_state.get("phase1_market_data_cache")
    if not isinstance(cache, dict):
        cache = {}
        st.session_state["phase1_market_data_cache"] = cache
    cache_key = market_data_cache_key(request)
    cached_market_data = None if force_refresh else cache.get(cache_key)
    cache_hit = isinstance(cached_market_data, MarketDataResult)

    generated_at_utc = st.session_state.get("_quantlab_generated_at_utc")
    if generated_at_utc is None:
        generated_at_utc = datetime.now(timezone.utc)

    injected_loader = st.session_state.get("_quantlab_market_data_loader")
    workflow_kwargs: dict[str, object] = {}
    if cache_hit:
        workflow_kwargs["market_data_loader"] = _cached_market_data_loader(cached_market_data)
    elif injected_loader is not None:
        workflow_kwargs["market_data_loader"] = injected_loader

    total_started = perf_counter()
    stage_started = total_started
    active_stage: WorkflowStage | None = None
    previous_label: str | None = None
    stage_timings: dict[str, float] = {}

    with st.status("正在启动回测工作流", expanded=True) as run_status:

        def observe_stage(stage: WorkflowStage) -> None:
            nonlocal active_stage, previous_label, stage_started
            now = perf_counter()
            if active_stage is not None:
                stage_timings[active_stage] = now - stage_started
            active_stage = stage
            stage_started = now
            label = _workflow_stage_label(stage, cache_hit=cache_hit)
            if label != previous_label:
                run_status.write(label)
                previous_label = label

        try:
            output = run_spy_sma_workflow(
                request,
                software_version=software_version,
                generated_at_utc=generated_at_utc,
                stage_callback=observe_stage,
                **workflow_kwargs,
            )
            now = perf_counter()
            if active_stage is not None:
                stage_timings[active_stage] = now - stage_started

            run_status.write("正在准备页面图表与交易记录")
            page_started = perf_counter()
            page_cache = st.session_state.get("phase1_presentation_cache")
            if not isinstance(page_cache, dict):
                page_cache = {}
                st.session_state["phase1_presentation_cache"] = page_cache
            run_id = output.report_view.run_metadata.run_id
            page_data = page_cache.get(run_id)
            presentation_cache_hit = isinstance(page_data, PreparedPageData)
            if not presentation_cache_hit:
                page_data = prepare_page_data(output)
                _remember_bounded_cache(
                    page_cache,
                    run_id,
                    page_data,
                    limit=PRESENTATION_CACHE_LIMIT,
                )
                st.session_state["phase1_presentation_cache"] = page_cache
            stage_timings["streamlit_page_prepare"] = perf_counter() - page_started

            if not cache_hit:
                _remember_market_data(cache, cache_key, output.market_data)
                st.session_state["phase1_market_data_cache"] = cache
            st.session_state["phase1_run_output"] = output
            st.session_state["phase1_page_data"] = page_data
            st.session_state["phase1_last_run_signature"] = request_signature(request)
            total_seconds = perf_counter() - total_started
            st.session_state["phase1_run_timings"] = {
                "cache_hit": cache_hit,
                "presentation_cache_hit": presentation_cache_hit,
                "total_seconds": total_seconds,
                "stages": stage_timings,
            }
            run_status.update(
                label=f"6/6 完成，用时 {total_seconds:.2f} 秒",
                state="complete",
                expanded=False,
            )
            source_note = "，已复用本次会话行情缓存" if cache_hit else ""
            st.success(
                f"回测完成，总耗时 {total_seconds:.2f} 秒{source_note}。"
                "页面与导出文件来自同一运行结果。"
            )
        except Exception as error:
            LOGGER.warning(
                "Backtest workflow failed at %s (%s).",
                active_stage or "startup",
                type(error).__name__,
            )
            failed_label = (
                _workflow_stage_label(active_stage, cache_hit=cache_hit)
                if active_stage is not None
                else "启动回测工作流"
            )
            run_status.update(
                label=f"{failed_label}失败",
                state="error",
                expanded=True,
            )
            st.error(f"{failed_label}失败。{friendly_error_message(error)}")


def render_app() -> None:
    dark_mode = bool(st.session_state.get("phase1_dark_mode", False))
    inject_styles(dark_mode=dark_mode)
    version = installed_software_version()

    st.markdown(
        '<div class="ql-kicker">QUANTLAB · TRUSTWORTHY BACKTESTING</div>', unsafe_allow_html=True
    )
    st.title("QuantLab SPY 日线回测")
    st.markdown(
        '<div class="ql-intro">验证 SMA 双均线策略在统一成本口径下是否优于买入持有。</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("回测设置")
        st.caption(f"QuantLab v{version}")
        dark_mode = st.toggle(
            "深色模式",
            key="phase1_dark_mode",
        )
        _show_theme_toast_once(dark_mode=dark_mode)
        st.markdown(
            '<div class="ql-sidebar-section">数据与区间</div>',
            unsafe_allow_html=True,
        )
        st.text_input("标的", value="SPY", disabled=True, key="phase1_symbol")
        start_date_text = st.text_input(
            "开始日期",
            value="2015-01-01",
            placeholder="YYYY-MM-DD",
            key="phase1_start_date_text",
        )
        end_date_text = st.text_input(
            "结束日期",
            value="2024-12-31",
            placeholder="YYYY-MM-DD",
            key="phase1_end_date_text",
        )
        date_validation = validate_date_inputs(start_date_text, end_date_text)
        for validation_error in date_validation.errors:
            st.error(validation_error)

        st.markdown(
            '<div class="ql-sidebar-section">策略参数</div>',
            unsafe_allow_html=True,
        )
        short_window = int(
            st.number_input(
                "短均线窗口",
                min_value=1,
                value=20,
                step=1,
                key="phase1_short_window",
            )
        )
        long_window = int(
            st.number_input(
                "长均线窗口",
                min_value=2,
                value=60,
                step=1,
                key="phase1_long_window",
            )
        )
        st.markdown(
            '<div class="ql-sidebar-section">资金与成本</div>',
            unsafe_allow_html=True,
        )
        initial_capital = float(
            st.number_input(
                "初始资金",
                min_value=0.01,
                value=10_000.0,
                step=1_000.0,
                format="%.2f",
                key="phase1_initial_capital",
            )
        )
        fee_rate = float(
            st.number_input(
                "手续费率",
                min_value=0.0,
                max_value=0.9999,
                value=0.0005,
                step=0.0001,
                format="%.4f",
                key="phase1_fee_rate",
            )
        )
        slippage_rate = float(
            st.number_input(
                "滑点率",
                min_value=0.0,
                max_value=0.9999,
                value=0.0005,
                step=0.0001,
                format="%.4f",
                key="phase1_slippage_rate",
            )
        )
        run_clicked = st.button(
            "运行回测",
            type="primary",
            width="stretch",
            key="phase1_run",
            disabled=not date_validation.is_valid,
        )
        refresh_clicked = st.button(
            "重新获取行情并运行",
            width="stretch",
            key="phase1_refresh_and_run",
            disabled=not date_validation.is_valid,
        )
        st.caption("“重新获取”会忽略当前会话缓存，并向数据源发起新请求。")
        st.markdown(
            '<div class="ql-disclaimer">仅用于研究与工程验证，不构成投资建议。</div>',
            unsafe_allow_html=True,
        )

    signature = None
    if date_validation.is_valid:
        assert date_validation.start_date is not None
        assert date_validation.end_date is not None
        signature = control_signature(
            start_date=date_validation.start_date,
            end_date=date_validation.end_date,
            short_window=short_window,
            long_window=long_window,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )

    if (run_clicked or refresh_clicked) and date_validation.is_valid:
        try:
            assert date_validation.start_date is not None
            assert date_validation.end_date is not None
            request = SpySmaRunRequest(
                start_date=date_validation.start_date,
                end_date=date_validation.end_date,
                short_window=short_window,
                long_window=long_window,
                initial_capital=initial_capital,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
            )
            _run_submitted_workflow(
                request,
                software_version=version,
                force_refresh=refresh_clicked,
            )
        except Exception as error:
            LOGGER.warning("Backtest request validation failed (%s).", type(error).__name__)
            st.error(friendly_error_message(error))

    output = st.session_state.get("phase1_run_output")
    if output is None:
        st.info("设置参数后点击“运行回测”。修改控件不会自动下载行情或执行回测。")
        return

    if signature != request_signature(output.request):
        st.warning("参数已修改，请重新运行回测以更新结果。以下仍是上一次运行结果。")

    page_data = st.session_state.get("phase1_page_data")
    if not isinstance(page_data, PreparedPageData) or (
        page_data.run_id != output.report_view.run_metadata.run_id
    ):
        page_cache = st.session_state.get("phase1_presentation_cache")
        if not isinstance(page_cache, dict):
            page_cache = {}
            st.session_state["phase1_presentation_cache"] = page_cache
        page_data = page_cache.get(output.report_view.run_metadata.run_id)
        if not isinstance(page_data, PreparedPageData):
            page_data = prepare_page_data(output)
            _remember_bounded_cache(
                page_cache,
                page_data.run_id,
                page_data,
                limit=PRESENTATION_CACHE_LIMIT,
            )
            st.session_state["phase1_presentation_cache"] = page_cache
        st.session_state["phase1_page_data"] = page_data

    run_timings = st.session_state.get("phase1_run_timings")
    _render_research_workspace(
        output,
        page_data,
        run_timings=run_timings if isinstance(run_timings, dict) else None,
        dark_mode=dark_mode,
    )
    st.caption("历史回测不代表未来表现；本工具不构成投资建议。")


render_app()
