from __future__ import annotations

import csv
import html
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HKExportBundle:
    report_html: bytes
    trades_csv: bytes
    manifest_json: bytes
    bundle_zip: bytes


def _fmt_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _fmt_hkd(value: float) -> str:
    return f"HK$ {value:,.2f}"


def render_hk_report_html(result: dict[str, Any]) -> bytes:
    symbol = html.escape(result["symbol"]["normalized_symbol"])
    benchmark = html.escape(result["benchmark"]["normalized_symbol"])
    metrics = result["strategy_metrics"]
    rows = "".join(
        "<tr>"
        f"<td>{trade['trade_id']}</td><td>{html.escape(trade['status'])}</td>"
        f"<td>{html.escape(trade['entry_date'])}</td>"
        f"<td>{html.escape(trade['exit_date'] or '持仓中')}</td>"
        f"<td>{trade['quantity']}</td><td>{_fmt_hkd(trade['net_pnl'])}</td>"
        f"<td>{_fmt_percent(trade['net_return'])}</td><td>{_fmt_hkd(trade['total_cost'])}</td>"
        "</tr>"
        for trade in result["trades"]
    )
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>QuantLab {symbol} 港股回测报告</title>
<style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#162338}}h1{{margin-bottom:4px}}.muted{{color:#607086}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:28px 0}}.metric{{border:1px solid #dbe4ef;border-radius:8px;padding:16px}}.metric strong{{display:block;font-size:22px;margin-top:8px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid #dbe4ef;padding:10px;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4){{text-align:left}}code{{overflow-wrap:anywhere}}footer{{margin-top:36px;color:#607086;font-size:13px}}</style></head>
<body><header><h1>{symbol} 港股日线回测</h1><div class="muted">SMA {result["strategy"]["short_window"]} / {result["strategy"]["long_window"]} · 比较基准 {benchmark}</div></header>
<section class="metrics"><div class="metric">最终权益<strong>{_fmt_hkd(metrics["final_equity"])}</strong></div><div class="metric">总收益率<strong>{_fmt_percent(metrics["total_return"])}</strong></div><div class="metric">最大回撤<strong>{_fmt_percent(metrics["max_drawdown"])}</strong></div><div class="metric">总交易成本<strong>{_fmt_hkd(metrics["total_trading_costs"])}</strong></div></section>
<h2>交易记录</h2><table><thead><tr><th>ID</th><th>状态</th><th>买入日期</th><th>卖出日期</th><th>数量</th><th>净损益</th><th>净收益率</th><th>总成本</th></tr></thead><tbody>{rows}</tbody></table>
<h2>数据与复现</h2><p>数据来源：{html.escape(result["market_data"]["source"])}<br>数据指纹：<code>{html.escape(result["market_data"]["data_sha256"])}</code><br>运行标识：<code>{html.escape(result["run_id"])}</code></p>
<footer>仅用于研究与工程验证，不构成投资建议。费用和整手股数以本次配置为准。</footer></body></html>"""
    return document.encode("utf-8")


def render_hk_trades_csv(result: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "run_id",
        "trade_id",
        "status",
        "entry_date",
        "entry_raw_price",
        "entry_execution_price",
        "quantity",
        "entry_total_cost",
        "exit_date",
        "exit_raw_price",
        "exit_execution_price",
        "exit_total_cost",
        "holding_days",
        "gross_pnl",
        "net_pnl",
        "net_return",
        "total_cost",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for trade in result["trades"]:
        writer.writerow(
            {
                "run_id": result["run_id"],
                "trade_id": trade["trade_id"],
                "status": trade["status"],
                "entry_date": trade["entry_date"],
                "entry_raw_price": format(trade["entry_raw_price"], ".12g"),
                "entry_execution_price": format(trade["entry_execution_price"], ".12g"),
                "quantity": trade["quantity"],
                "entry_total_cost": format(trade["entry_costs"]["total_cost"], ".12g"),
                "exit_date": trade["exit_date"] or "",
                "exit_raw_price": ""
                if trade["exit_raw_price"] is None
                else format(trade["exit_raw_price"], ".12g"),
                "exit_execution_price": ""
                if trade["exit_execution_price"] is None
                else format(trade["exit_execution_price"], ".12g"),
                "exit_total_cost": ""
                if trade["exit_costs"] is None
                else format(trade["exit_costs"]["total_cost"], ".12g"),
                "holding_days": trade["holding_days"],
                "gross_pnl": format(trade["gross_pnl"], ".12g"),
                "net_pnl": format(trade["net_pnl"], ".12g"),
                "net_return": format(trade["net_return"], ".12g"),
                "total_cost": format(trade["total_cost"], ".12g"),
            }
        )
    return output.getvalue().encode("utf-8-sig")


def render_hk_manifest_json(result: dict[str, Any]) -> bytes:
    manifest = {
        "schema_version": 1,
        "run_id": result["run_id"],
        "symbol": result["symbol"]["normalized_symbol"],
        "benchmark": result["benchmark"]["normalized_symbol"],
        "date_range": result["date_range"],
        "strategy": result["strategy"],
        "initial_capital": result["initial_capital"],
        "board_lot": result["board_lot"],
        "benchmark_board_lot": result["benchmark_board_lot"],
        "cost_config": result["cost_config"],
        "benchmark_cost_config": result["benchmark_cost_config"],
        "market_data": result["market_data"],
        "strategy_metrics": result["strategy_metrics"],
        "benchmark_metrics": result["benchmark_metrics"],
        "trade_count": len(result["trades"]),
    }
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def build_hk_export_bundle(result: dict[str, Any]) -> HKExportBundle:
    report = render_hk_report_html(result)
    trades = render_hk_trades_csv(result)
    manifest = render_hk_manifest_json(result)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in (
            ("report.html", report),
            ("trades.csv", trades),
            ("manifest.json", manifest),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return HKExportBundle(report, trades, manifest, buffer.getvalue())
