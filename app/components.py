from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np
import pandas as pd

from quant_lab.models import BacktestReportView, MetricView
from quant_lab.workflow import SpySmaRunOutput, SpySmaRunRequest

CHART_DATE_COLUMN = "日期"
CHART_STRATEGY_COLUMN = "SMA 双均线"
CHART_BENCHMARK_COLUMN = "买入持有"
CHART_EQUITY_COLUMN = "账户净值"
CHART_EXCESS_RETURN_COLUMN = "累计超额收益率"
CHART_SERIES_COLUMN = "系列"
CHART_VIEW_EQUITY = "策略与基准"
CHART_VIEW_EXCESS = "超额收益"
DEFAULT_CHART_MAX_ROWS = 800
DEFAULT_TRADE_PREVIEW_ROWS = 20
DATE_INPUT_FORMAT_ERROR = "请输入 YYYY-MM-DD 格式"
DATE_RANGE_ORDER_ERROR = "结束日期必须晚于开始日期"
TRADE_PREVIEW_COLUMNS = (
    "ID",
    "状态",
    "入场日期",
    "入场成交价",
    "退出日期",
    "退出成交价",
    "持有交易日",
    "净损益",
    "净收益率",
)


@dataclass(frozen=True)
class ThemePalette:
    name: str
    color_scheme: str
    page: str
    surface: str
    surface_muted: str
    surface_elevated: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    success: str
    warning: str
    danger: str
    code: str
    shadow: str
    chart_strategy: str
    chart_benchmark: str
    chart_excess: str
    dataframe_filter: str


LIGHT_THEME = ThemePalette(
    name="light",
    color_scheme="light",
    page="#f5f7fb",
    surface="#ffffff",
    surface_muted="#eef3f9",
    surface_elevated="#ffffff",
    surface_hover="#f8fafc",
    border="#dce3ed",
    border_strong="#cbd5e1",
    text="#14213d",
    text_secondary="#5b6578",
    text_muted="#64748b",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    accent_soft="#dbeafe",
    on_accent="#ffffff",
    success="#0f8a5f",
    warning="#b45309",
    danger="#b42318",
    code="#eef3f9",
    shadow="rgba(15, 23, 42, 0.08)",
    chart_strategy="#2563eb",
    chart_benchmark="#16a085",
    chart_excess="#b45309",
    dataframe_filter="none",
)

DARK_THEME = ThemePalette(
    name="dark",
    color_scheme="dark",
    page="#0b1220",
    surface="#111827",
    surface_muted="#172033",
    surface_elevated="#1e293b",
    surface_hover="#233049",
    border="#334155",
    border_strong="#475569",
    text="#f1f5f9",
    text_secondary="#cbd5e1",
    text_muted="#a7b4c7",
    accent="#60a5fa",
    accent_hover="#93c5fd",
    accent_soft="#1d3a5f",
    on_accent="#07111f",
    success="#34d399",
    warning="#fbbf24",
    danger="#f87171",
    code="#172033",
    shadow="rgba(0, 0, 0, 0.28)",
    chart_strategy="#60a5fa",
    chart_benchmark="#34d399",
    chart_excess="#fbbf24",
    dataframe_filter="invert(1) hue-rotate(180deg)",
)


def theme_palette(*, dark_mode: bool) -> ThemePalette:
    return DARK_THEME if dark_mode else LIGHT_THEME


@dataclass(frozen=True)
class MarketDataCacheKey:
    symbol: str
    start_date: date
    end_date: date
    longest_lookback: int


@dataclass(frozen=True)
class PreparedPageData:
    run_id: str
    equity_chart: pd.DataFrame
    equity_chart_fast: pd.DataFrame
    equity_chart_spec: dict[str, object]
    equity_chart_spec_dark: dict[str, object]
    excess_return_chart: pd.DataFrame
    excess_return_chart_fast: pd.DataFrame
    excess_return_chart_spec: dict[str, object]
    excess_return_chart_spec_dark: dict[str, object]
    trades_table: pd.DataFrame


@dataclass(frozen=True)
class PreparedExportData:
    run_id: str
    generated_at_display: str
    html_size: int
    csv_size: int
    manifest_size: int
    zip_size: int
    zip_bytes: bytes


@dataclass(frozen=True)
class DateInputValidation:
    start_date: date | None
    end_date: date | None
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.start_date is not None and self.end_date is not None


def validate_date_inputs(start_text: str, end_text: str) -> DateInputValidation:
    """Parse strict ISO dates without relying on the browser's locale."""

    errors: list[str] = []

    def parse(value: str, label: str) -> date | None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
            errors.append(f"{label}：{DATE_INPUT_FORMAT_ERROR}")
            return None
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            errors.append(f"{label}：{DATE_INPUT_FORMAT_ERROR}")
            return None

    start_date = parse(start_text, "开始日期")
    end_date = parse(end_text, "结束日期")
    if start_date is not None and end_date is not None and end_date <= start_date:
        errors.append(DATE_RANGE_ORDER_ERROR)
    return DateInputValidation(
        start_date=start_date,
        end_date=end_date,
        errors=tuple(errors),
    )


def control_signature(
    *,
    start_date: date,
    end_date: date,
    short_window: int,
    long_window: int,
    initial_capital: float,
    fee_rate: float,
    slippage_rate: float,
) -> tuple[object, ...]:
    return (
        start_date,
        end_date,
        int(short_window),
        int(long_window),
        float(initial_capital),
        float(fee_rate),
        float(slippage_rate),
    )


def request_signature(request: SpySmaRunRequest) -> tuple[object, ...]:
    return control_signature(
        start_date=request.start_date,
        end_date=request.end_date,
        short_window=request.short_window,
        long_window=request.long_window,
        initial_capital=request.initial_capital,
        fee_rate=request.fee_rate,
        slippage_rate=request.slippage_rate,
    )


def market_data_cache_key(request: SpySmaRunRequest) -> MarketDataCacheKey:
    """Key session-local standardized data by every input that changes its rows."""
    return MarketDataCacheKey(
        symbol="SPY",
        start_date=request.start_date,
        end_date=request.end_date,
        longest_lookback=request.long_window,
    )


def metrics_by_key(
    view: BacktestReportView,
    scope: str,
) -> dict[str, MetricView]:
    if scope == "strategy":
        metrics = view.strategy_metrics
    elif scope == "benchmark":
        metrics = view.benchmark_metrics
    else:
        raise ValueError("scope must be 'strategy' or 'benchmark'.")
    return {metric.key: metric for metric in metrics}


def equity_chart_frame(view: BacktestReportView) -> pd.DataFrame:
    """Map existing equity facts to chart columns without deriving returns."""
    return pd.DataFrame(
        {
            CHART_DATE_COLUMN: pd.to_datetime([row.date for row in view.equity_rows]),
            CHART_STRATEGY_COLUMN: [row.strategy_equity for row in view.equity_rows],
            CHART_BENCHMARK_COLUMN: [row.benchmark_equity for row in view.equity_rows],
        }
    )


def excess_return_chart_frame(view: BacktestReportView) -> pd.DataFrame:
    """Build a display-only cumulative excess-return series from existing equities."""
    initial_equity = float(view.config.initial_capital)
    return pd.DataFrame(
        {
            CHART_DATE_COLUMN: pd.to_datetime([row.date for row in view.equity_rows]),
            CHART_EXCESS_RETURN_COLUMN: [
                (row.strategy_equity - row.benchmark_equity) / initial_equity
                for row in view.equity_rows
            ],
        }
    )


def downsample_equity_chart(
    chart: pd.DataFrame,
    *,
    max_rows: int = DEFAULT_CHART_MAX_ROWS,
) -> pd.DataFrame:
    """Retain endpoints and each series' min/max in deterministic time buckets."""
    numeric_columns = list(chart.select_dtypes(include="number").columns)
    minimum_rows = 2 + (2 * len(numeric_columns))
    if not numeric_columns:
        raise ValueError("equity chart must contain at least one numeric series.")
    if max_rows < minimum_rows:
        raise ValueError(f"max_rows must be at least {minimum_rows}.")
    if len(chart) <= max_rows:
        return chart.copy()

    bucket_count = max(1, (max_rows - 2) // (2 * len(numeric_columns)))
    interior_positions = np.arange(1, len(chart) - 1)
    selected_positions = {0, len(chart) - 1}
    for positions in np.array_split(interior_positions, bucket_count):
        if positions.size == 0:
            continue
        bucket = chart.iloc[positions]
        for column in numeric_columns:
            values = bucket[column].to_numpy(dtype=float)
            selected_positions.add(int(positions[int(np.argmin(values))]))
            selected_positions.add(int(positions[int(np.argmax(values))]))

    return chart.iloc[sorted(selected_positions)].copy()


def chart_date_domain(chart: pd.DataFrame) -> tuple[date, date]:
    """Return the exact ordered chart domain after validating the date/value pairing."""
    if CHART_DATE_COLUMN not in chart.columns:
        raise ValueError(f"chart is missing the {CHART_DATE_COLUMN!r} column.")
    if chart.empty:
        raise ValueError("chart must contain at least one row.")
    dates = pd.to_datetime(chart[CHART_DATE_COLUMN], errors="coerce")
    if dates.isna().any():
        raise ValueError("chart dates must all be valid datetimes.")
    if not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError("chart dates must be strictly increasing and unique.")
    return dates.iloc[0].date(), dates.iloc[-1].date()


def _chart_theme_colors(*, dark_mode: bool) -> dict[str, str]:
    palette = theme_palette(dark_mode=dark_mode)
    return {
        "canvas": palette.surface,
        "label": palette.text_secondary,
        "title": palette.text,
        "grid": palette.border,
        "domain": palette.border_strong,
        "strategy": palette.chart_strategy,
        "benchmark": palette.chart_benchmark,
        "excess": palette.chart_excess,
    }


def _chart_x_encoding(date_domain: tuple[date, date]) -> dict[str, object]:
    start_date, end_date = date_domain
    if start_date > end_date:
        raise ValueError("chart date domain start must not be after its end.")
    span_days = (end_date - start_date).days
    if span_days <= 31:
        label_format = "%m-%d"
        tick_count = min(7, span_days + 1)
    elif span_days <= 730:
        label_format = "%Y-%m"
        tick_count = 6
    else:
        label_format = "%Y"
        tick_count = 6
    return {
        "field": CHART_DATE_COLUMN,
        "type": "temporal",
        "title": "日期",
        "scale": {
            "domain": [start_date.isoformat(), end_date.isoformat()],
            "nice": False,
        },
        "axis": {
            "format": label_format,
            "grid": False,
            "labelFlush": True,
            "labelOverlap": "greedy",
            "labelPadding": 8,
            "tickCount": tick_count,
            "tickMinStep": 86_400_000,
        },
    }


def build_equity_chart_spec(
    date_domain: tuple[date, date],
    *,
    dark_mode: bool = False,
) -> dict[str, object]:
    """Return a single-mark Vega-Lite spec with browser-local x-axis interaction."""
    colors = _chart_theme_colors(dark_mode=dark_mode)
    return {
        "transform": [
            {
                "fold": [CHART_STRATEGY_COLUMN, CHART_BENCHMARK_COLUMN],
                "as": [CHART_SERIES_COLUMN, CHART_EQUITY_COLUMN],
            }
        ],
        "mark": {
            "type": "line",
            "clip": True,
            "strokeWidth": 2,
        },
        "encoding": {
            "x": _chart_x_encoding(date_domain),
            "y": {
                "field": CHART_EQUITY_COLUMN,
                "type": "quantitative",
                "title": "账户净值",
                "axis": {
                    "grid": True,
                    "labelPadding": 8,
                    "tickCount": 5,
                },
                "scale": {"zero": False},
            },
            "color": {
                "field": CHART_SERIES_COLUMN,
                "type": "nominal",
                "title": None,
                "scale": {
                    "domain": [CHART_STRATEGY_COLUMN, CHART_BENCHMARK_COLUMN],
                    "range": [colors["strategy"], colors["benchmark"]],
                },
                "legend": {"orient": "top", "direction": "horizontal"},
            },
            "opacity": {
                "condition": {"param": "equity_series", "value": 1.0},
                "value": 0.16,
            },
            "tooltip": [
                {
                    "field": CHART_DATE_COLUMN,
                    "type": "temporal",
                    "title": "日期",
                    "format": "%Y-%m-%d",
                },
                {
                    "field": CHART_SERIES_COLUMN,
                    "type": "nominal",
                    "title": "系列",
                },
                {
                    "field": CHART_EQUITY_COLUMN,
                    "type": "quantitative",
                    "title": "账户净值",
                    "format": ",.2f",
                },
            ],
        },
        "params": [
            {
                "name": "equity_x_scale",
                "select": {"type": "interval", "encodings": ["x"]},
                "bind": "scales",
            },
            {
                "name": "equity_series",
                "select": {
                    "type": "point",
                    "fields": [CHART_SERIES_COLUMN],
                    "toggle": True,
                },
                "bind": "legend",
            },
        ],
        "background": colors["canvas"],
        "config": {
            "view": {"fill": colors["canvas"], "stroke": None},
            "axis": {
                "domainColor": colors["domain"],
                "gridOpacity": 0.62,
                "labelColor": colors["label"],
                "labelFontSize": 12,
                "tickColor": colors["domain"],
                "titleColor": colors["title"],
                "titleFontSize": 13,
                "titleFontWeight": 600,
                "gridColor": colors["grid"],
            },
            "legend": {
                "labelColor": colors["label"],
                "labelFontSize": 12,
                "symbolStrokeWidth": 3,
                "titleColor": colors["title"],
            },
        },
    }


def build_excess_return_chart_spec(
    date_domain: tuple[date, date],
    *,
    dark_mode: bool = False,
) -> dict[str, object]:
    """Return an interactive chart for cumulative strategy-minus-benchmark return."""
    colors = _chart_theme_colors(dark_mode=dark_mode)
    return {
        "mark": {
            "type": "line",
            "clip": True,
            "strokeWidth": 2,
            "color": colors["excess"],
        },
        "encoding": {
            "x": _chart_x_encoding(date_domain),
            "y": {
                "field": CHART_EXCESS_RETURN_COLUMN,
                "type": "quantitative",
                "title": "累计超额收益率",
                "axis": {
                    "format": ".1%",
                    "grid": True,
                    "labelPadding": 8,
                    "tickCount": 5,
                },
                "scale": {"zero": True},
            },
            "tooltip": [
                {
                    "field": CHART_DATE_COLUMN,
                    "type": "temporal",
                    "title": "日期",
                    "format": "%Y-%m-%d",
                },
                {
                    "field": CHART_EXCESS_RETURN_COLUMN,
                    "type": "quantitative",
                    "title": "累计超额收益率",
                    "format": ".2%",
                },
            ],
        },
        "params": [
            {
                "name": "excess_x_scale",
                "select": {"type": "interval", "encodings": ["x"]},
                "bind": "scales",
            }
        ],
        "background": colors["canvas"],
        "config": {
            "view": {"fill": colors["canvas"], "stroke": None},
            "axis": {
                "domainColor": colors["domain"],
                "gridOpacity": 0.62,
                "labelColor": colors["label"],
                "labelFontSize": 12,
                "tickColor": colors["domain"],
                "titleColor": colors["title"],
                "titleFontSize": 13,
                "titleFontWeight": 600,
                "gridColor": colors["grid"],
            },
        },
    }


def trades_table_frame(view: BacktestReportView) -> pd.DataFrame:
    """Map the complete strategy TradeView ledger to localized display text."""
    rows = []
    for trade in view.strategy_trades:
        rows.append(
            {
                "ID": trade.trade_id,
                "状态": trade.status_display,
                "入场日期": trade.entry_date.display_value,
                "入场参考价": trade.entry_raw_price.display_value,
                "入场成交价": trade.entry_execution_price.display_value,
                "数量": trade.quantity.display_value,
                "入场手续费": trade.entry_fee.display_value,
                "入场滑点": trade.entry_slippage_cost.display_value,
                "退出日期": trade.exit_date.display_value,
                "退出参考价": trade.exit_raw_price.display_value,
                "退出成交价": trade.exit_execution_price.display_value,
                "退出手续费": trade.exit_fee.display_value,
                "退出滑点": trade.exit_slippage_cost.display_value,
                "估值日期": trade.mark_date.display_value,
                "估值价格": trade.mark_price.display_value,
                "持有交易日": trade.holding_days.display_value,
                "毛损益": trade.gross_pnl.display_value,
                "总手续费": trade.total_fees.display_value,
                "总滑点": trade.total_slippage_cost.display_value,
                "净损益": trade.net_pnl.display_value,
                "净收益率": trade.net_return.display_value,
            }
        )
    return pd.DataFrame(rows)


def prepare_page_data(output: SpySmaRunOutput) -> PreparedPageData:
    """Build browser-facing tables once per completed workflow result."""
    chart = equity_chart_frame(output.report_view)
    excess = excess_return_chart_frame(output.report_view)
    date_domain = chart_date_domain(chart)
    return PreparedPageData(
        run_id=output.report_view.run_metadata.run_id,
        equity_chart=chart,
        equity_chart_fast=downsample_equity_chart(chart),
        equity_chart_spec=build_equity_chart_spec(date_domain),
        equity_chart_spec_dark=build_equity_chart_spec(date_domain, dark_mode=True),
        excess_return_chart=excess,
        excess_return_chart_fast=downsample_equity_chart(excess),
        excess_return_chart_spec=build_excess_return_chart_spec(date_domain),
        excess_return_chart_spec_dark=build_excess_return_chart_spec(
            date_domain,
            dark_mode=True,
        ),
        trades_table=trades_table_frame(output.report_view),
    )


def visible_trades_table(
    trades: pd.DataFrame,
    *,
    show_all: bool,
    limit: int = DEFAULT_TRADE_PREVIEW_ROWS,
) -> pd.DataFrame:
    if limit <= 0:
        raise ValueError("limit must be greater than zero.")
    if show_all:
        return trades
    preview = trades.head(limit)
    common_columns = [column for column in TRADE_PREVIEW_COLUMNS if column in preview.columns]
    return preview.loc[:, common_columns] if common_columns else preview


def export_zip_filename(output: SpySmaRunOutput) -> str:
    stem = output.report_view.html_filename.removesuffix(".html")
    return f"{stem}-results.zip"


def render_export_zip(output: SpySmaRunOutput) -> bytes:
    """Build a deterministic bundle from the workflow's already-rendered outputs."""
    members = (
        (output.report_view.html_filename, output.html_report),
        (output.report_view.csv_filename, output.trades_csv),
        (output.report_view.manifest_filename, output.manifest_json),
    )
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for filename, text in members:
            info = ZipInfo(filename=filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def prepare_export_data(output: SpySmaRunOutput) -> PreparedExportData:
    """Materialize export bytes only after explicit user intent."""
    zip_bytes = render_export_zip(output)
    return PreparedExportData(
        run_id=output.report_view.run_metadata.run_id,
        generated_at_display=output.report_view.run_metadata.generated_at_display,
        html_size=len(output.html_report.encode("utf-8")),
        csv_size=len(output.trades_csv.encode("utf-8")),
        manifest_size=len(output.manifest_json.encode("utf-8")),
        zip_size=len(zip_bytes),
        zip_bytes=zip_bytes,
    )


def format_file_size(size: int) -> str:
    if size < 0:
        raise ValueError("size must not be negative.")
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def friendly_error_message(error: Exception) -> str:
    raw = str(error).strip() or error.__class__.__name__
    replacements = (
        ("start_date must not be later than end_date", "开始日期不能晚于结束日期"),
        ("short_window must be smaller than long_window", "短均线窗口必须小于长均线窗口"),
        ("initial_capital must be finite and greater than zero", "初始资金必须大于零"),
        ("fee_rate must be finite", "手续费率必须是有效的非负数"),
        ("slippage_rate must be finite", "滑点率必须是有效的非负数"),
        ("contains no price data", "所选日期范围内没有可用交易日"),
        ("returned no SPY history", "数据提供器没有返回 SPY 日线数据"),
        ("warmup", "预热行情不足"),
    )
    for source, target in replacements:
        if source in raw:
            raw = target
            break
    if isinstance(error, TimeoutError):
        raw = "网络请求超时，请稍后重试"
    elif isinstance(error, (ConnectionError, OSError)):
        raw = "网络连接失败，请检查网络后重试"
    elif "yfinance" in raw.lower() or "connection" in raw.lower():
        raw = "数据提供器连接失败，请稍后重试"

    raw = re.sub(r"https?://\S+", "[远程地址已隐藏]", raw, flags=re.IGNORECASE)
    raw = re.sub(r"file://\S+", "[本地路径已隐藏]", raw, flags=re.IGNORECASE)
    raw = re.sub(r"[A-Za-z]:[\\/][^\r\n'\"\[]+", "[本地路径已隐藏]", raw)
    if len(raw) > 500:
        raw = raw[:497] + "..."
    return f"回测未完成：{raw}"


def friendly_export_error_message(error: Exception) -> str:
    del error
    return "导出文件准备失败，请稍后重试；当前回测结果仍然保留。"
