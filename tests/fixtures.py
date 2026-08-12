"""Static Phase 1 golden fixtures.

All expected values are literals derived independently from BACKTEST_SPEC.md.
This module intentionally does not import or call production backtest code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    target_position: float
    is_warmup: bool = False
    short_ma: float | None = None
    long_ma: float | None = None


@dataclass(frozen=True)
class DailyExpectation:
    date: str
    prior_target: float
    action: str
    fill_price: float | None
    trade_quantity: float
    cash: float
    holdings: float
    fee: float
    slippage: float
    equity: float


@dataclass(frozen=True)
class TradeExpectation:
    status: str
    display_status: str
    entry_date: str
    entry_reference_open: float
    entry_fill_price: float
    quantity: float
    entry_fee: float
    entry_slippage: float
    exit_date: str | None
    exit_reference_open: float | None
    exit_fill_price: float | None
    exit_fee: float | None
    exit_slippage: float | None
    mark_date: str | None
    mark_price: float | None
    holding_days: int
    gross_pnl: float
    total_fees: float
    total_slippage: float
    net_pnl: float
    net_return: float


@dataclass(frozen=True)
class SummaryExpectation:
    final_equity: float
    total_return: float
    max_drawdown: float
    closed_trade_count: int
    win_rate: float | None
    total_fees: float
    total_slippage: float


@dataclass(frozen=True)
class BenchmarkExpectation:
    entry_date: str
    entry_reference_open: float
    entry_fill_price: float
    quantity: float
    entry_fee: float
    entry_slippage: float
    daily_equity: tuple[tuple[str, float], ...]
    final_equity: float
    total_return: float
    max_drawdown: float
    total_fees: float
    total_slippage: float


@dataclass(frozen=True)
class CorporateActionExpectation:
    date: str
    raw_open: float
    raw_high: float
    raw_low: float
    raw_close: float
    adjusted_close: float
    adjustment_factor: float
    expected_open: float
    expected_high: float
    expected_low: float
    expected_close: float


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    name: str
    purpose: str
    initial_capital: float
    fee_rate: float
    slippage_rate: float
    short_window: int | None
    long_window: int | None
    bars: tuple[PriceBar, ...]
    expected_daily: tuple[DailyExpectation, ...]
    expected_trades: tuple[TradeExpectation, ...]
    expected_summary: SummaryExpectation
    expected_benchmark: BenchmarkExpectation
    corporate_actions: tuple[CorporateActionExpectation, ...] = ()
    notes: tuple[str, ...] = ()


GOLDEN_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        case_id="G01",
        name="始终空仓",
        purpose="验证目标仓位始终为零时没有交易、成本或策略收益。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-01-02", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0),
            PriceBar("2024-01-03", 110.0, 110.0, 110.0, 110.0, 1000.0, 0.0),
            PriceBar("2024-01-04", 90.0, 90.0, 90.0, 90.0, 1000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-01-02", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-01-03", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-01-04", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
        ),
        expected_trades=(),
        expected_summary=SummaryExpectation(1000.0, 0.0, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-01-02",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-01-02", 1000.0), ("2024-01-03", 1100.0), ("2024-01-04", 900.0)),
            900.0,
            -0.1,
            -0.18181818181818182,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G02",
        name="买入后持仓至期末",
        purpose="验证下一日开盘买入、持仓估值和持仓中账本。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-02-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-02-02", 100.0, 110.0, 100.0, 110.0, 1000.0, 1.0),
            PriceBar("2024-02-05", 110.0, 120.0, 110.0, 120.0, 1000.0, 1.0),
        ),
        expected_daily=(
            DailyExpectation("2024-02-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-02-02", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1100.0),
            DailyExpectation("2024-02-05", 1.0, "NONE", None, 0.0, 0.0, 10.0, 0.0, 0.0, 1200.0),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-02-02",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                None,
                None,
                None,
                None,
                None,
                "2024-02-05",
                120.0,
                1,
                200.0,
                0.0,
                0.0,
                200.0,
                0.2,
            ),
        ),
        expected_summary=SummaryExpectation(1200.0, 0.2, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-02-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-02-01", 1000.0), ("2024-02-02", 1100.0), ("2024-02-05", 1200.0)),
            1200.0,
            0.2,
            0.0,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G03",
        name="一次完整盈利交易",
        purpose="验证一次买入和对应卖出只计为一笔盈利交易。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-03-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-03-04", 100.0, 110.0, 100.0, 110.0, 1000.0, 0.0),
            PriceBar("2024-03-05", 120.0, 120.0, 120.0, 120.0, 1000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-03-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-03-04", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1100.0),
            DailyExpectation("2024-03-05", 0.0, "SELL", 120.0, 10.0, 1200.0, 0.0, 0.0, 0.0, 1200.0),
        ),
        expected_trades=(
            TradeExpectation(
                "CLOSED",
                "已平仓",
                "2024-03-04",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                "2024-03-05",
                120.0,
                120.0,
                0.0,
                0.0,
                None,
                None,
                1,
                200.0,
                0.0,
                0.0,
                200.0,
                0.2,
            ),
        ),
        expected_summary=SummaryExpectation(1200.0, 0.2, 0.0, 1, 1.0, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-03-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-03-01", 1000.0), ("2024-03-04", 1100.0), ("2024-03-05", 1200.0)),
            1200.0,
            0.2,
            0.0,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G04",
        name="一次完整亏损交易",
        purpose="验证净亏损交易、0% 胜率和包含初始净值的回撤。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-04-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-04-02", 100.0, 100.0, 90.0, 90.0, 1000.0, 0.0),
            PriceBar("2024-04-03", 80.0, 80.0, 80.0, 80.0, 1000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-04-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-04-02", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 900.0),
            DailyExpectation("2024-04-03", 0.0, "SELL", 80.0, 10.0, 800.0, 0.0, 0.0, 0.0, 800.0),
        ),
        expected_trades=(
            TradeExpectation(
                "CLOSED",
                "已平仓",
                "2024-04-02",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                "2024-04-03",
                80.0,
                80.0,
                0.0,
                0.0,
                None,
                None,
                1,
                -200.0,
                0.0,
                0.0,
                -200.0,
                -0.2,
            ),
        ),
        expected_summary=SummaryExpectation(800.0, -0.2, -0.2, 1, 0.0, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-04-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-04-01", 1000.0), ("2024-04-02", 900.0), ("2024-04-03", 800.0)),
            800.0,
            -0.2,
            -0.2,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G05",
        name="多次完整交易",
        purpose="验证交易配对、复利后的下一次全仓数量和 50% 胜率。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-05-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-05-02", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0),
            PriceBar("2024-05-03", 110.0, 110.0, 110.0, 110.0, 1000.0, 1.0),
            PriceBar("2024-05-06", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0),
            PriceBar("2024-05-07", 90.0, 90.0, 90.0, 90.0, 1000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-05-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-05-02", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-05-03", 0.0, "SELL", 110.0, 10.0, 1100.0, 0.0, 0.0, 0.0, 1100.0),
            DailyExpectation("2024-05-06", 1.0, "BUY", 100.0, 11.0, 0.0, 11.0, 0.0, 0.0, 1100.0),
            DailyExpectation("2024-05-07", 0.0, "SELL", 90.0, 11.0, 990.0, 0.0, 0.0, 0.0, 990.0),
        ),
        expected_trades=(
            TradeExpectation(
                "CLOSED",
                "已平仓",
                "2024-05-02",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                "2024-05-03",
                110.0,
                110.0,
                0.0,
                0.0,
                None,
                None,
                1,
                100.0,
                0.0,
                0.0,
                100.0,
                0.1,
            ),
            TradeExpectation(
                "CLOSED",
                "已平仓",
                "2024-05-06",
                100.0,
                100.0,
                11.0,
                0.0,
                0.0,
                "2024-05-07",
                90.0,
                90.0,
                0.0,
                0.0,
                None,
                None,
                1,
                -110.0,
                0.0,
                0.0,
                -110.0,
                -0.1,
            ),
        ),
        expected_summary=SummaryExpectation(990.0, -0.01, -0.1, 2, 0.5, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-05-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (
                ("2024-05-01", 1000.0),
                ("2024-05-02", 1000.0),
                ("2024-05-03", 1100.0),
                ("2024-05-06", 1000.0),
                ("2024-05-07", 900.0),
            ),
            900.0,
            -0.1,
            -0.18181818181818182,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G06",
        name="手续费与滑点",
        purpose="验证双边费用、双边滑点、买入预留手续费和成本不重复扣除。",
        initial_capital=1000.0,
        fee_rate=0.01,
        slippage_rate=0.01,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-06-03", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-06-04", 100.0, 110.0, 100.0, 110.0, 1000.0, 0.0),
            PriceBar("2024-06-05", 120.0, 120.0, 120.0, 120.0, 1000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-06-03", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation(
                "2024-06-04",
                1.0,
                "BUY",
                101.0,
                9.802960494069209,
                0.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                1078.325654347613,
            ),
            DailyExpectation(
                "2024-06-05",
                0.0,
                "SELL",
                118.8,
                9.802960494069209,
                1152.9457896284678,
                0.0,
                11.64591706695422,
                11.76355259288305,
                1152.9457896284678,
            ),
        ),
        expected_trades=(
            TradeExpectation(
                "CLOSED",
                "已平仓",
                "2024-06-04",
                100.0,
                101.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                "2024-06-05",
                120.0,
                118.8,
                11.64591706695422,
                11.76355259288305,
                None,
                None,
                1,
                196.05920988138418,
                21.54690716596412,
                21.56651308695226,
                152.9457896284678,
                0.1529457896284678,
            ),
        ),
        expected_summary=SummaryExpectation(
            1152.9457896284678,
            0.1529457896284678,
            0.0,
            1,
            1.0,
            21.54690716596412,
            21.56651308695226,
        ),
        expected_benchmark=BenchmarkExpectation(
            "2024-06-03",
            100.0,
            101.0,
            9.802960494069209,
            9.900990099009901,
            9.802960494069209,
            (
                ("2024-06-03", 980.2960494069209),
                ("2024-06-04", 1078.325654347613),
                ("2024-06-05", 1176.355259288305),
            ),
            1176.355259288305,
            0.17635525928830507,
            -0.01970395059307911,
            9.900990099009901,
            9.802960494069209,
        ),
    ),
    GoldenCase(
        case_id="G07",
        name="明确峰谷最大回撤",
        purpose="验证从 1200 峰值到 900 谷值的最大回撤严格为 -25%。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-07-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-07-02", 100.0, 120.0, 100.0, 120.0, 1000.0, 1.0),
            PriceBar("2024-07-03", 120.0, 120.0, 90.0, 90.0, 1000.0, 1.0),
            PriceBar("2024-07-05", 90.0, 108.0, 90.0, 108.0, 1000.0, 1.0),
        ),
        expected_daily=(
            DailyExpectation("2024-07-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-07-02", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1200.0),
            DailyExpectation("2024-07-03", 1.0, "NONE", None, 0.0, 0.0, 10.0, 0.0, 0.0, 900.0),
            DailyExpectation("2024-07-05", 1.0, "NONE", None, 0.0, 0.0, 10.0, 0.0, 0.0, 1080.0),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-07-02",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                None,
                None,
                None,
                None,
                None,
                "2024-07-05",
                108.0,
                2,
                80.0,
                0.0,
                0.0,
                80.0,
                0.08,
            ),
        ),
        expected_summary=SummaryExpectation(1080.0, 0.08, -0.25, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-07-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (
                ("2024-07-01", 1000.0),
                ("2024-07-02", 1200.0),
                ("2024-07-03", 900.0),
                ("2024-07-05", 1080.0),
            ),
            1080.0,
            0.08,
            -0.25,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G08",
        name="期末持仓不收退出成本",
        purpose="验证持仓中交易只记录已发生的买入手续费和买入滑点。",
        initial_capital=1000.0,
        fee_rate=0.01,
        slippage_rate=0.01,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-08-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-08-02", 100.0, 110.0, 100.0, 110.0, 1000.0, 1.0),
            PriceBar("2024-08-05", 120.0, 120.0, 120.0, 120.0, 1000.0, 1.0),
        ),
        expected_daily=(
            DailyExpectation("2024-08-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation(
                "2024-08-02",
                1.0,
                "BUY",
                101.0,
                9.802960494069209,
                0.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                1078.325654347613,
            ),
            DailyExpectation(
                "2024-08-05",
                1.0,
                "NONE",
                None,
                0.0,
                0.0,
                9.802960494069209,
                0.0,
                0.0,
                1176.355259288305,
            ),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-08-02",
                100.0,
                101.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                None,
                None,
                None,
                None,
                None,
                "2024-08-05",
                120.0,
                1,
                196.05920988138418,
                9.900990099009901,
                9.802960494069209,
                176.35525928830507,
                0.17635525928830507,
            ),
        ),
        expected_summary=SummaryExpectation(
            1176.355259288305,
            0.17635525928830507,
            0.0,
            0,
            None,
            9.900990099009901,
            9.802960494069209,
        ),
        expected_benchmark=BenchmarkExpectation(
            "2024-08-01",
            100.0,
            101.0,
            9.802960494069209,
            9.900990099009901,
            9.802960494069209,
            (
                ("2024-08-01", 980.2960494069209),
                ("2024-08-02", 1078.325654347613),
                ("2024-08-05", 1176.355259288305),
            ),
            1176.355259288305,
            0.17635525928830507,
            -0.01970395059307911,
            9.900990099009901,
            9.802960494069209,
        ),
    ),
    GoldenCase(
        case_id="G09",
        name="零笔已平仓胜率为空",
        purpose="验证存在盈利未平仓交易时胜率仍为 N/A，而不是 100% 或 0%。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-09-02", 100.0, 100.0, 100.0, 100.0, 1000.0, 1.0),
            PriceBar("2024-09-03", 100.0, 120.0, 100.0, 120.0, 1000.0, 1.0),
            PriceBar("2024-09-04", 120.0, 130.0, 120.0, 130.0, 1000.0, 1.0),
        ),
        expected_daily=(
            DailyExpectation("2024-09-02", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-09-03", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1200.0),
            DailyExpectation("2024-09-04", 1.0, "NONE", None, 0.0, 0.0, 10.0, 0.0, 0.0, 1300.0),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-09-03",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                None,
                None,
                None,
                None,
                None,
                "2024-09-04",
                130.0,
                1,
                300.0,
                0.0,
                0.0,
                300.0,
                0.3,
            ),
        ),
        expected_summary=SummaryExpectation(1300.0, 0.3, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-09-02",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-09-02", 1000.0), ("2024-09-03", 1200.0), ("2024-09-04", 1300.0)),
            1300.0,
            0.3,
            0.0,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G10",
        name="策略与基准成本一致",
        purpose="验证预热信号使策略与基准同日买入时，两者结果逐日完全相同。",
        initial_capital=1000.0,
        fee_rate=0.01,
        slippage_rate=0.01,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-09-30", 90.0, 110.0, 90.0, 110.0, 1000.0, 1.0, True),
            PriceBar("2024-10-01", 100.0, 110.0, 100.0, 110.0, 1000.0, 1.0),
            PriceBar("2024-10-02", 120.0, 120.0, 120.0, 120.0, 1000.0, 1.0),
        ),
        expected_daily=(
            DailyExpectation(
                "2024-10-01",
                1.0,
                "BUY",
                101.0,
                9.802960494069209,
                0.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                1078.325654347613,
            ),
            DailyExpectation(
                "2024-10-02",
                1.0,
                "NONE",
                None,
                0.0,
                0.0,
                9.802960494069209,
                0.0,
                0.0,
                1176.355259288305,
            ),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-10-01",
                100.0,
                101.0,
                9.802960494069209,
                9.900990099009901,
                9.802960494069209,
                None,
                None,
                None,
                None,
                None,
                "2024-10-02",
                120.0,
                1,
                196.05920988138418,
                9.900990099009901,
                9.802960494069209,
                176.35525928830507,
                0.17635525928830507,
            ),
        ),
        expected_summary=SummaryExpectation(
            1176.355259288305,
            0.17635525928830507,
            0.0,
            0,
            None,
            9.900990099009901,
            9.802960494069209,
        ),
        expected_benchmark=BenchmarkExpectation(
            "2024-10-01",
            100.0,
            101.0,
            9.802960494069209,
            9.900990099009901,
            9.802960494069209,
            (("2024-10-01", 1078.325654347613), ("2024-10-02", 1176.355259288305)),
            1176.355259288305,
            0.17635525928830507,
            0.0,
            9.900990099009901,
            9.802960494069209,
        ),
        notes=("2024-09-30 是预热行，没有现金、持仓、费用或净值记录。",),
    ),
    GoldenCase(
        case_id="G11",
        name="均线相等保持空仓",
        purpose="验证 short_ma == long_ma 时目标严格为零。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=1,
        long_window=2,
        bars=(
            PriceBar("2024-10-29", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0, True, 100.0, None),
            PriceBar("2024-10-30", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0, True, 100.0, 100.0),
            PriceBar("2024-11-01", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0, False, 100.0, 100.0),
            PriceBar("2024-11-04", 100.0, 100.0, 100.0, 100.0, 1000.0, 0.0, False, 100.0, 100.0),
        ),
        expected_daily=(
            DailyExpectation("2024-11-01", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-11-04", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
        ),
        expected_trades=(),
        expected_summary=SummaryExpectation(1000.0, 0.0, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-11-01",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-11-01", 1000.0), ("2024-11-04", 1000.0)),
            1000.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ),
    ),
    GoldenCase(
        case_id="G12",
        name="预热信号首日执行",
        purpose="验证预热期可形成信号但只能在用户区间第一日开盘成交。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=1,
        long_window=2,
        bars=(
            PriceBar("2024-11-27", 90.0, 90.0, 90.0, 90.0, 1000.0, 0.0, True, 90.0, None),
            PriceBar("2024-11-29", 110.0, 110.0, 110.0, 110.0, 1000.0, 1.0, True, 110.0, 100.0),
            PriceBar("2024-12-02", 100.0, 120.0, 100.0, 120.0, 1000.0, 1.0, False, 120.0, 115.0),
            PriceBar("2024-12-03", 120.0, 130.0, 120.0, 130.0, 1000.0, 1.0, False, 130.0, 125.0),
        ),
        expected_daily=(
            DailyExpectation("2024-12-02", 1.0, "BUY", 100.0, 10.0, 0.0, 10.0, 0.0, 0.0, 1200.0),
            DailyExpectation("2024-12-03", 1.0, "NONE", None, 0.0, 0.0, 10.0, 0.0, 0.0, 1300.0),
        ),
        expected_trades=(
            TradeExpectation(
                "OPEN",
                "持仓中",
                "2024-12-02",
                100.0,
                100.0,
                10.0,
                0.0,
                0.0,
                None,
                None,
                None,
                None,
                None,
                "2024-12-03",
                130.0,
                1,
                300.0,
                0.0,
                0.0,
                300.0,
                0.3,
            ),
        ),
        expected_summary=SummaryExpectation(1300.0, 0.3, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-12-02",
            100.0,
            100.0,
            10.0,
            0.0,
            0.0,
            (("2024-12-02", 1200.0), ("2024-12-03", 1300.0)),
            1300.0,
            0.3,
            0.0,
            0.0,
            0.0,
        ),
        notes=("两根预热行只有均线和目标信号，不出现在 expected_daily 中。",),
    ),
    GoldenCase(
        case_id="G13",
        name="拆股调整后 OHLC 一致",
        purpose="验证同一调整因子作用于 OHLC 后不会产生虚假的拆股价格跳空。",
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_rate=0.0,
        short_window=None,
        long_window=None,
        bars=(
            PriceBar("2024-12-16", 50.0, 52.0, 49.0, 51.0, 1000.0, 0.0),
            PriceBar("2024-12-17", 51.0, 53.0, 50.0, 52.0, 2000.0, 0.0),
        ),
        expected_daily=(
            DailyExpectation("2024-12-16", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
            DailyExpectation("2024-12-17", 0.0, "NONE", None, 0.0, 1000.0, 0.0, 0.0, 0.0, 1000.0),
        ),
        expected_trades=(),
        expected_summary=SummaryExpectation(1000.0, 0.0, 0.0, 0, None, 0.0, 0.0),
        expected_benchmark=BenchmarkExpectation(
            "2024-12-16",
            50.0,
            50.0,
            20.0,
            0.0,
            0.0,
            (("2024-12-16", 1020.0), ("2024-12-17", 1040.0)),
            1040.0,
            0.04,
            0.0,
            0.0,
            0.0,
        ),
        corporate_actions=(
            CorporateActionExpectation(
                "2024-12-16",
                100.0,
                104.0,
                98.0,
                102.0,
                51.0,
                0.5,
                50.0,
                52.0,
                49.0,
                51.0,
            ),
            CorporateActionExpectation(
                "2024-12-17",
                51.0,
                53.0,
                50.0,
                52.0,
                52.0,
                1.0,
                51.0,
                53.0,
                50.0,
                52.0,
            ),
        ),
        notes=(
            "本样例标准化行情文本的 SHA256 为 31875d128ed2a3ca2f9515ed31b4bb561e6f38f002b8cf30d643d9a106102b26。",
        ),
    ),
)


GOLDEN_CASES_BY_ID = {case.case_id: case for case in GOLDEN_CASES}
G13_DATA_SHA256 = "31875d128ed2a3ca2f9515ed31b4bb561e6f38f002b8cf30d643d9a106102b26"


assert len(GOLDEN_CASES) == 13
assert len(GOLDEN_CASES_BY_ID) == len(GOLDEN_CASES)
