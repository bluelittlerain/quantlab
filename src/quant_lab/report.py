from __future__ import annotations

import csv
import io
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path

from quant_lab.models import BacktestReportView, MetricView, ReportArtifacts, ScalarView

CSV_FLOAT_PLACES = 10
RUN_MANIFEST_SCHEMA_VERSION = "1.0"
TRADES_CSV_COLUMNS = (
    "run_id",
    "software_version",
    "generated_at_utc",
    "symbol",
    "strategy_name",
    "short_window",
    "long_window",
    "requested_start_date",
    "requested_end_date",
    "actual_start_date",
    "actual_end_date",
    "analysis_start_date",
    "analysis_end_date",
    "source",
    "source_version",
    "data_sha256",
    "adjustment_method",
    "initial_capital",
    "fee_rate",
    "slippage_rate",
    "trade_id",
    "status",
    "entry_date",
    "entry_raw_price",
    "entry_execution_price",
    "quantity",
    "entry_fee",
    "entry_slippage_cost",
    "exit_date",
    "exit_raw_price",
    "exit_execution_price",
    "exit_fee",
    "exit_slippage_cost",
    "mark_date",
    "mark_price",
    "holding_days",
    "gross_pnl",
    "total_fees",
    "total_slippage_cost",
    "net_pnl",
    "net_return",
)


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _raw_number(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("report raw numeric values must be finite.")
    return str(value) if isinstance(value, int) else format(number, ".17g")


def _csv_number(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("CSV numeric values must be finite.")
    quantum = Decimal(1).scaleb(-CSV_FLOAT_PLACES)
    rounded = Decimal(str(number)).quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.{CSV_FLOAT_PLACES}f}"


def _metric_cards(scope: str, metrics: tuple[MetricView, ...]) -> str:
    return "\n".join(
        (
            f'<article class="metric" data-scope="{_html(scope)}" '
            f'data-key="{_html(metric.key)}" '
            f'data-raw-value="{_html(_raw_number(metric.raw_value))}">'
            f'<span class="metric-label">{_html(metric.label)}</span>'
            f"<strong>{_html(metric.display_value)}</strong>"
            "</article>"
        )
        for metric in metrics
    )


def _chart_svg(view: BacktestReportView) -> str:
    rows = view.equity_rows
    if not rows:
        return '<p class="empty-state">分析区间内没有可绘制的净值数据。</p>'

    width = 920.0
    height = 320.0
    left = 42.0
    right = 18.0
    top = 32.0
    bottom = 42.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    all_values = [view.config.initial_capital]
    all_values.extend(row.strategy_equity for row in rows)
    all_values.extend(row.benchmark_equity for row in rows)
    low = min(all_values)
    high = max(all_values)
    spread = high - low
    padding = spread * 0.08 if spread else max(abs(high) * 0.05, 1.0)
    y_min = max(0.0, low - padding)
    y_max = high + padding

    def x_position(index: int) -> float:
        if len(rows) == 1:
            return left + plot_width / 2.0
        return left + plot_width * index / (len(rows) - 1)

    def y_position(value: float) -> float:
        return top + (y_max - value) * plot_height / (y_max - y_min)

    strategy_points = " ".join(
        f"{x_position(index):.2f},{y_position(row.strategy_equity):.2f}"
        for index, row in enumerate(rows)
    )
    benchmark_points = " ".join(
        f"{x_position(index):.2f},{y_position(row.benchmark_equity):.2f}"
        for index, row in enumerate(rows)
    )
    grid_lines = "\n".join(
        f'<line x1="{left:.2f}" y1="{(top + plot_height * step / 4):.2f}" '
        f'x2="{(width - right):.2f}" y2="{(top + plot_height * step / 4):.2f}" />'
        for step in range(5)
    )
    start = rows[0]
    end = rows[-1]
    return f"""
<svg class="equity-chart" viewBox="0 0 {width:.0f} {height:.0f}" role="img"
     aria-labelledby="equity-chart-title equity-chart-description"
     data-point-count="{len(rows)}"
     data-start-date="{_html(start.date_display)}"
     data-end-date="{_html(end.date_display)}"
     data-initial-equity="{_html(_raw_number(view.config.initial_capital))}">
  <title id="equity-chart-title">策略与买入持有净值对比</title>
  <desc id="equity-chart-description">两条曲线使用同一日期轴，且不包含预热期。</desc>
  <g class="grid">{grid_lines}</g>
  <polyline class="strategy-line" data-series="strategy"
            data-point-count="{len(rows)}" points="{strategy_points}" />
  <polyline class="benchmark-line" data-series="benchmark"
            data-point-count="{len(rows)}" points="{benchmark_points}" />
  <circle class="strategy-dot" cx="{x_position(len(rows) - 1):.2f}"
          cy="{y_position(end.strategy_equity):.2f}" r="4" />
  <circle class="benchmark-dot" cx="{x_position(len(rows) - 1):.2f}"
          cy="{y_position(end.benchmark_equity):.2f}" r="4" />
  <text class="axis-label" x="{left:.2f}" y="{height - 14:.2f}">{_html(start.date_display)}</text>
  <text class="axis-label axis-label-end" x="{width - right:.2f}" y="{height - 14:.2f}">{_html(end.date_display)}</text>
</svg>
""".strip()


def _trade_cell(field: ScalarView) -> str:
    raw = field.raw_value
    raw_text = raw.isoformat() if hasattr(raw, "isoformat") else _raw_number(raw)
    return f'<td data-raw-value="{_html(raw_text)}">{_html(field.display_value)}</td>'


def _trade_rows(view: BacktestReportView) -> str:
    if not view.strategy_trades:
        return '<tr><td colspan="21" class="empty-state">本次策略没有交易记录。</td></tr>'
    rows: list[str] = []
    for trade in view.strategy_trades:
        cells = [
            f'<td data-raw-value="{trade.trade_id}">{trade.trade_id}</td>',
            f'<td data-raw-value="{_html(trade.status)}">{_html(trade.status_display)}</td>',
            _trade_cell(trade.entry_date),
            _trade_cell(trade.entry_raw_price),
            _trade_cell(trade.entry_execution_price),
            _trade_cell(trade.quantity),
            _trade_cell(trade.entry_fee),
            _trade_cell(trade.entry_slippage_cost),
            _trade_cell(trade.exit_date),
            _trade_cell(trade.exit_raw_price),
            _trade_cell(trade.exit_execution_price),
            _trade_cell(trade.exit_fee),
            _trade_cell(trade.exit_slippage_cost),
            _trade_cell(trade.mark_date),
            _trade_cell(trade.mark_price),
            _trade_cell(trade.holding_days),
            _trade_cell(trade.gross_pnl),
            _trade_cell(trade.total_fees),
            _trade_cell(trade.total_slippage_cost),
            _trade_cell(trade.net_pnl),
            _trade_cell(trade.net_return),
        ]
        rows.append(
            f'<tr data-trade-id="{trade.trade_id}" data-status="{_html(trade.status)}">'
            + "".join(cells)
            + "</tr>"
        )
    return "\n".join(rows)


def render_html_report(view: BacktestReportView) -> str:
    """Render a deterministic, self-contained and script-free HTML report."""
    run = view.run_metadata
    market = view.market_data
    style = """
:root { color-scheme: light; --ink: #111827; --muted: #5b6472; --line: #d9dee7;
  --surface: #ffffff; --soft: #f4f6f9; --blue: #2563eb; --green: #0f9f6e; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--soft); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  line-height: 1.55; }
.page { width: min(1180px, calc(100% - 32px)); margin: 32px auto 56px; }
.report-header { padding: 28px 30px; background: #101827; color: #fff; border-radius: 8px; }
.eyebrow { margin: 0 0 6px; color: #a9c4ff; font-size: 13px; font-weight: 700; }
h1 { margin: 0; font-size: 30px; letter-spacing: 0; }
.subtitle { margin: 8px 0 0; color: #d7dfec; }
.run-id { display: inline-block; margin-top: 16px; padding: 5px 9px; border: 1px solid #526077;
  border-radius: 6px; color: #e9eef7; font-family: Consolas, monospace; font-size: 13px; }
section { margin-top: 30px; }
h2 { margin: 0 0 14px; font-size: 22px; }
h3 { margin: 24px 0 10px; font-size: 17px; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 20px; }
.facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px;
  background: var(--line); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.fact { min-width: 0; padding: 14px 16px; background: var(--surface); }
.fact span, .metric-label { display: block; color: var(--muted); font-size: 13px; }
.fact strong { display: block; margin-top: 3px; overflow-wrap: anywhere; }
.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.metric { padding: 14px 15px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.metric strong { display: block; margin-top: 5px; font-size: 21px; }
.comparison-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
.excess { border-left: 4px solid var(--blue); }
.legend { display: flex; flex-wrap: wrap; gap: 18px; margin-bottom: 8px; color: var(--muted); }
.legend i { display: inline-block; width: 20px; height: 3px; margin: 0 7px 3px 0; }
.legend .strategy { background: var(--blue); }
.legend .benchmark { background: var(--green); }
.equity-chart { display: block; width: 100%; min-height: 240px; }
.grid line { stroke: #e2e7ef; stroke-width: 1; }
.strategy-line, .benchmark-line { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.strategy-line { stroke: var(--blue); } .benchmark-line { stroke: var(--green); }
.strategy-dot { fill: var(--blue); } .benchmark-dot { fill: var(--green); }
.axis-label { fill: var(--muted); font-size: 12px; } .axis-label-end { text-anchor: end; }
.chart-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 8px; }
.chart-summary div { padding: 10px 12px; background: var(--soft); border-radius: 6px; }
.chart-summary span { display: block; color: var(--muted); font-size: 12px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; background: var(--surface); font-size: 13px; }
th, td { padding: 10px 11px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { position: sticky; top: 0; background: #edf1f6; color: #364152; font-weight: 700; }
th:nth-child(1), th:nth-child(2), td:nth-child(1), td:nth-child(2) { text-align: left; }
tbody tr:last-child td { border-bottom: 0; }
.hash { font-family: Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }
.notice { padding: 14px 16px; border-left: 4px solid #d97706; background: #fff8e8; border-radius: 6px; }
ul { margin: 10px 0 0; padding-left: 22px; } li + li { margin-top: 6px; }
.empty-state { color: var(--muted); text-align: center; }
footer { margin-top: 30px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 840px) { .facts, .metrics { grid-template-columns: 1fr 1fr; }
  .comparison-columns { grid-template-columns: 1fr; } .chart-summary { grid-template-columns: 1fr 1fr; } }
@media (max-width: 520px) { .page { width: min(100% - 20px, 1180px); margin-top: 10px; }
  .report-header { padding: 22px 18px; } .facts, .metrics { grid-template-columns: 1fr; } }
""".strip()

    assumptions = "\n".join(f"<li>{_html(item)}</li>" for item in view.assumptions)
    warnings = "\n".join(f"<li>{_html(item)}</li>" for item in view.warnings)
    chart = _chart_svg(view)
    strategy_cards = _metric_cards("strategy", view.strategy_metrics)
    benchmark_cards = _metric_cards("benchmark", view.benchmark_metrics)
    trade_rows = _trade_rows(view)
    first = view.equity_rows[0]
    last = view.equity_rows[-1]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="quantlab-run-id" content="{_html(run.run_id)}">
  <meta name="quantlab-software-version" content="{_html(run.software_version)}">
  <meta name="quantlab-symbol" content="{_html(run.symbol)}">
  <meta name="quantlab-strategy" content="{_html(run.strategy_name)}">
  <meta name="quantlab-short-window" content="{run.short_window}">
  <meta name="quantlab-long-window" content="{run.long_window}">
  <meta name="quantlab-data-sha256" content="{_html(market.data_sha256)}">
  <meta name="quantlab-requested-start-date" content="{market.requested_start_date.isoformat()}">
  <meta name="quantlab-requested-end-date" content="{market.requested_end_date.isoformat()}">
  <meta name="quantlab-actual-start-date" content="{market.actual_start_date.isoformat()}">
  <meta name="quantlab-actual-end-date" content="{market.actual_end_date.isoformat()}">
  <meta name="quantlab-analysis-start-date" content="{market.analysis_start_date.isoformat()}">
  <meta name="quantlab-analysis-end-date" content="{market.analysis_end_date.isoformat()}">
  <meta name="quantlab-initial-capital" content="{_html(_raw_number(view.config.initial_capital))}">
  <meta name="quantlab-fee-rate" content="{_html(_raw_number(view.config.fee_rate))}">
  <meta name="quantlab-slippage-rate" content="{_html(_raw_number(view.config.slippage_rate))}">
  <title>{_html(run.symbol)} {_html(run.strategy_name)} 回测报告</title>
  <style>{style}</style>
</head>
<body>
<main class="page">
  <header class="report-header">
    <p class="eyebrow">QuantLab / 可复现日线回测</p>
    <h1>{_html(run.symbol)} {_html(run.strategy_name)} 回测报告</h1>
    <p class="subtitle">双均线参数 {run.short_window} / {run.long_window}，与买入持有使用一致成本口径。</p>
    <span class="run-id">run_id: {_html(run.run_id)}</span>
  </header>

  <section aria-labelledby="run-information">
    <h2 id="run-information">运行与数据</h2>
    <div class="facts">
      <div class="fact"><span>软件版本</span><strong>{_html(run.software_version)}</strong></div>
      <div class="fact"><span>生成时间（UTC）</span><strong>{_html(run.generated_at_display)}</strong></div>
      <div class="fact"><span>标的</span><strong>{_html(run.symbol)}</strong></div>
      <div class="fact"><span>请求日期范围</span><strong>{_html(view.requested_date_range_display)}</strong></div>
      <div class="fact"><span>实际数据范围</span><strong>{_html(view.actual_data_range_display)}</strong></div>
      <div class="fact"><span>正式分析范围</span><strong>{_html(view.analysis_date_range_display)}</strong></div>
      <div class="fact"><span>数据来源</span><strong>{_html(market.source)} {_html(market.source_version)}</strong></div>
      <div class="fact"><span>抓取时间（UTC）</span><strong>{_html(view.market_fetched_at_display)}</strong></div>
      <div class="fact"><span>预热 / 分析行数</span><strong>{market.warmup_row_count} / {market.analysis_row_count}</strong></div>
      <div class="fact"><span>调整口径</span><strong>{_html(market.adjustment_method)}</strong></div>
      <div class="fact"><span>初始资金</span><strong>{_html(view.initial_capital_display)}</strong></div>
      <div class="fact"><span>手续费 / 滑点</span><strong>{_html(view.fee_rate_display)} / {_html(view.slippage_rate_display)}</strong></div>
      <div class="fact"><span>数据 SHA256</span><strong class="hash">{_html(market.data_sha256)}</strong></div>
    </div>
  </section>

  <section aria-labelledby="performance">
    <h2 id="performance">核心指标</h2>
    <div class="comparison-columns">
      <div><h3>双均线策略</h3><div class="metrics">{strategy_cards}</div></div>
      <div><h3>买入持有基准</h3><div class="metrics">{benchmark_cards}</div></div>
    </div>
    <div class="metric excess" data-scope="comparison" data-key="excess_return"
         data-raw-value="{_html(_raw_number(view.excess_return.raw_value))}">
      <span class="metric-label">{_html(view.excess_return.label)}</span>
      <strong>{_html(view.excess_return.display_value)}</strong>
    </div>
  </section>

  <section aria-labelledby="equity-curve">
    <h2 id="equity-curve">净值对比</h2>
    <div class="panel">
      <div class="legend"><span><i class="strategy"></i>双均线策略</span><span><i class="benchmark"></i>买入持有</span></div>
      {chart}
      <div class="chart-summary">
        <div><span>初始权益</span><strong>{_html(view.initial_capital_display)}</strong></div>
        <div><span>策略首日 / 末日</span><strong>{_html(first.strategy_equity_display)} / {_html(last.strategy_equity_display)}</strong></div>
        <div><span>基准首日 / 末日</span><strong>{_html(first.benchmark_equity_display)} / {_html(last.benchmark_equity_display)}</strong></div>
        <div><span>正式日期轴</span><strong>{_html(view.analysis_date_range_display)}</strong></div>
      </div>
    </div>
  </section>

  <section aria-labelledby="trade-ledger">
    <h2 id="trade-ledger">策略交易账本</h2>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>ID</th><th>状态</th><th>入场日期</th><th>入场参考价</th><th>入场成交价</th>
          <th>数量</th><th>入场手续费</th><th>入场滑点</th><th>退出日期</th><th>退出参考价</th>
          <th>退出成交价</th><th>退出手续费</th><th>退出滑点</th><th>估值日期</th><th>估值价格</th>
          <th>持有交易日</th><th>毛损益</th><th>总手续费</th><th>总滑点</th><th>净损益</th><th>净收益率</th>
        </tr></thead>
        <tbody>{trade_rows}</tbody>
      </table>
    </div>
  </section>

  <section aria-labelledby="methodology">
    <h2 id="methodology">回测规则摘要</h2>
    <div class="panel"><ul>{assumptions}</ul></div>
  </section>

  <section aria-labelledby="limitations">
    <h2 id="limitations">已知限制与免责声明</h2>
    <div class="notice"><ul>{warnings}</ul></div>
  </section>

  <footer>QuantLab deterministic report · {_html(run.run_id)}</footer>
</main>
</body>
</html>
"""


def _scalar_csv(field: ScalarView) -> str:
    value = field.raw_value
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _csv_number(value)


def render_trades_csv(view: BacktestReportView) -> str:
    """Render only the strategy trade ledger with fixed UTF-8/LF semantics."""
    run = view.run_metadata
    market = view.market_data
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=TRADES_CSV_COLUMNS,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    common = {
        "run_id": run.run_id,
        "software_version": run.software_version,
        "generated_at_utc": run.generated_at_display,
        "symbol": run.symbol,
        "strategy_name": run.strategy_name,
        "short_window": str(run.short_window),
        "long_window": str(run.long_window),
        "requested_start_date": market.requested_start_date.isoformat(),
        "requested_end_date": market.requested_end_date.isoformat(),
        "actual_start_date": market.actual_start_date.isoformat(),
        "actual_end_date": market.actual_end_date.isoformat(),
        "analysis_start_date": market.analysis_start_date.isoformat(),
        "analysis_end_date": market.analysis_end_date.isoformat(),
        "source": market.source,
        "source_version": market.source_version,
        "data_sha256": market.data_sha256,
        "adjustment_method": market.adjustment_method,
        "initial_capital": _csv_number(view.config.initial_capital),
        "fee_rate": _csv_number(view.config.fee_rate),
        "slippage_rate": _csv_number(view.config.slippage_rate),
    }
    for trade in view.strategy_trades:
        writer.writerow(
            {
                **common,
                "trade_id": str(trade.trade_id),
                "status": trade.status,
                "entry_date": _scalar_csv(trade.entry_date),
                "entry_raw_price": _scalar_csv(trade.entry_raw_price),
                "entry_execution_price": _scalar_csv(trade.entry_execution_price),
                "quantity": _scalar_csv(trade.quantity),
                "entry_fee": _scalar_csv(trade.entry_fee),
                "entry_slippage_cost": _scalar_csv(trade.entry_slippage_cost),
                "exit_date": _scalar_csv(trade.exit_date),
                "exit_raw_price": _scalar_csv(trade.exit_raw_price),
                "exit_execution_price": _scalar_csv(trade.exit_execution_price),
                "exit_fee": _scalar_csv(trade.exit_fee),
                "exit_slippage_cost": _scalar_csv(trade.exit_slippage_cost),
                "mark_date": _scalar_csv(trade.mark_date),
                "mark_price": _scalar_csv(trade.mark_price),
                "holding_days": str(trade.holding_days.raw_value),
                "gross_pnl": _scalar_csv(trade.gross_pnl),
                "total_fees": _scalar_csv(trade.total_fees),
                "total_slippage_cost": _scalar_csv(trade.total_slippage_cost),
                "net_pnl": _scalar_csv(trade.net_pnl),
                "net_return": _scalar_csv(trade.net_return),
            }
        )
    return stream.getvalue()


def render_run_manifest(view: BacktestReportView) -> str:
    """Render deterministic file-level run metadata, including zero-trade runs."""
    run = view.run_metadata
    market = view.market_data
    payload = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": run.run_id,
        "software_version": run.software_version,
        "generated_at_utc": run.generated_at_display,
        "symbol": run.symbol,
        "strategy_name": run.strategy_name,
        "short_window": run.short_window,
        "long_window": run.long_window,
        "requested_start_date": market.requested_start_date.isoformat(),
        "requested_end_date": market.requested_end_date.isoformat(),
        "actual_start_date": market.actual_start_date.isoformat(),
        "actual_end_date": market.actual_end_date.isoformat(),
        "analysis_start_date": market.analysis_start_date.isoformat(),
        "analysis_end_date": market.analysis_end_date.isoformat(),
        "initial_capital": view.config.initial_capital,
        "fee_rate": view.config.fee_rate,
        "slippage_rate": view.config.slippage_rate,
        "data_source": market.source,
        "data_source_version": market.source_version,
        "fetched_at_utc": view.market_fetched_at_display,
        "warmup_row_count": market.warmup_row_count,
        "analysis_row_count": market.analysis_row_count,
        "adjustment_method": market.adjustment_method,
        "data_sha256": market.data_sha256,
        "strategy_trade_count": view.strategy_trade_count,
        "strategy_open_trade_count": view.strategy_open_trade_count,
        "html_filename": view.html_filename,
        "csv_filename": view.csv_filename,
        "manifest_filename": view.manifest_filename,
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    )


def write_report_bundle(
    view: BacktestReportView,
    output_directory: Path,
) -> ReportArtifacts:
    """Write already-renderable view content; no strategy or metric work occurs here."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    html_path = directory / view.html_filename
    csv_path = directory / view.csv_filename
    manifest_path = directory / view.manifest_filename
    html_path.write_text(render_html_report(view), encoding="utf-8", newline="\n")
    csv_path.write_text(render_trades_csv(view), encoding="utf-8", newline="\n")
    manifest_path.write_text(
        render_run_manifest(view),
        encoding="utf-8",
        newline="\n",
    )
    return ReportArtifacts(
        html_path=html_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        html_filename=html_path.name,
        csv_filename=csv_path.name,
        manifest_filename=manifest_path.name,
        run_id=view.run_metadata.run_id,
    )
