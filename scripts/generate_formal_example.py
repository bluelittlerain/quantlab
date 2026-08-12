from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from quant_lab.__about__ import __version__
from quant_lab.models import BacktestReportView, MetricView
from quant_lab.report import render_html_report, render_run_manifest, render_trades_csv
from quant_lab.workflow import SpySmaRunRequest, run_spy_sma_workflow

DEFAULT_OUTPUT_DIRECTORY = Path("examples/spy-sma-20-60")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated time must be timezone-aware UTC")
    if parsed.utcoffset().total_seconds() != 0:
        raise argparse.ArgumentTypeError("generated time must have a zero UTC offset")
    return parsed


def metric_map(metrics: tuple[MetricView, ...]) -> dict[str, MetricView]:
    return {metric.key: metric for metric in metrics}


def render_example_readme(view: BacktestReportView) -> str:
    strategy = metric_map(view.strategy_metrics)
    benchmark = metric_map(view.benchmark_metrics)
    run = view.run_metadata
    market = view.market_data
    return f"""# QuantLab SPY SMA 20/60 正式示例

这是 QuantLab v{run.software_version} 在 `{run.generated_at_display}` 获取并标准化行情后生成的固定展示产物，
用于演示 Phase 1 的真实 SPY 日线回测链路，不构成投资建议，也不代表未来收益。

## 运行身份

- `run_id`: `{run.run_id}`
- 数据 SHA256: `{market.data_sha256}`
- 软件版本: `{run.software_version}`
- 生成时间（UTC）: `{run.generated_at_display}`
- 数据抓取时间（UTC）: `{view.market_fetched_at_display}`
- 数据来源: {market.source} {market.source_version}

## 固定参数

- 标的: SPY
- 请求区间: {view.requested_date_range_display}
- 实际分析区间: {view.analysis_date_range_display}
- 策略: SMA {run.short_window} / {run.long_window}
- 初始资金: {view.initial_capital_display}
- 手续费率: {view.fee_rate_display}
- 滑点率: {view.slippage_rate_display}

## 结果摘要

| 指标 | SMA 双均线 | 买入持有 |
|---|---:|---:|
| 最终权益 | {strategy["final_equity"].display_value} | {benchmark["final_equity"].display_value} |
| 总收益率 | {strategy["total_return"].display_value} | {benchmark["total_return"].display_value} |
| 最大回撤 | {strategy["max_drawdown"].display_value} | {benchmark["max_drawdown"].display_value} |
| 已平仓交易 | {strategy["closed_trade_count"].display_value} | {benchmark["closed_trade_count"].display_value} |
| 累计手续费 | {strategy["total_fees"].display_value} | {benchmark["total_fees"].display_value} |
| 累计滑点成本 | {strategy["total_slippage_cost"].display_value} | {benchmark["total_slippage_cost"].display_value} |

## 文件

- [自包含 HTML 报告](report.html)
- [策略交易 CSV](trades.csv)
- [运行 Manifest](manifest.json)

相同软件版本、相同参数和相同标准化行情 SHA256 可以复现相同计算结果。
Yahoo Finance 等上游提供器可能修订历史调整数据，因此未来重新下载同一日期范围时，
数据 SHA256 与结果可能变化。本目录不包含原始完整行情文件，CI 也不会联网重建这些产物。
"""


def write_example(view: BacktestReportView, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "report.html": render_html_report(view),
        "trades.csv": render_trades_csv(view),
        "manifest.json": render_run_manifest(view),
        "README.md": render_example_readme(view),
    }
    for filename, content in files.items():
        (output_directory / filename).write_text(content, encoding="utf-8", newline="\n")


def generate(output_directory: Path, generated_at_utc: datetime) -> BacktestReportView:
    request = SpySmaRunRequest(
        start_date=date(2015, 1, 1),
        end_date=date(2024, 12, 31),
        short_window=20,
        long_window=60,
        initial_capital=10_000.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
    )
    output = run_spy_sma_workflow(
        request,
        software_version=__version__,
        generated_at_utc=generated_at_utc,
    )
    view = replace(
        output.report_view,
        html_filename="report.html",
        csv_filename="trades.csv",
        manifest_filename="manifest.json",
    )
    write_example(view, output_directory)
    return view


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the fixed real-SPY QuantLab example.")
    parser.add_argument("--generated-at-utc", required=True, type=parse_utc)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    arguments = parser.parse_args()
    view = generate(arguments.output_directory, arguments.generated_at_utc)
    print(f"run_id={view.run_metadata.run_id}")
    print(f"data_sha256={view.market_data.data_sha256}")
    print(f"analysis_range={view.analysis_date_range_display}")


if __name__ == "__main__":
    main()
