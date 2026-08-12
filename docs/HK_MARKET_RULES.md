# 港股市场规则

最后核验：2026-08-10。以下默认值用于研究，可在每次运行中覆盖。经纪佣金是商业条款，不是交易所固定收费。

## 执行

- 市场：HKEX 股票与 ETF 日线；货币：HKD。
- 只做多；目标仓位为全仓或空仓。
- T 日调整后收盘形成信号，最早 T+1 调整后开盘执行。
- 港股默认 `BOARD_LOT`；成交数量必须为已确认 `lot_size` 的整数倍。
- 买入数量先预留全部现金费用，现金不得为负。买不起一手时不成交并返回“当前资金不足以买入一手。”
- 未平仓交易按最后一个分析交易日调整后收盘估值，不虚构退出费用。
- 旧 SPY 黄金测试继续使用独立的 fractional 执行器。

## 默认成本

| 项目 | 默认 | 取整 | 方向 |
|---|---:|---|---|
| 经纪佣金 | 0.025%，最低 HK$100 | 分项四舍五入至仙 | 双边，可覆盖 |
| 股票印花税 | 0.1% | 不足 HK$1 向上取整 | 买卖双方 |
| 交易费 | 0.00565% | 四舍五入至仙 | 双边 |
| 证监会交易征费 | 0.0027% | 四舍五入至仙 | 双边 |
| 会财局交易征费 | 0.00015% | 四舍五入至仙 | 双边 |
| 股票交收费 | 0.0042% | 四舍五入至仙 | 双边 |
| 滑点 | 0.05% | 不逐笔舍入 | 买价上调、卖价下调 |

官方依据：

- 香港政府印花税率表：<https://www.gov.hk/en/residents/taxes/stamp/stamp_duty_rates.htm>
- HKEX 证券交易费用：<https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Trading/Transaction>
- HKEX 交收服务费用：<https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Clearing-and-Settlement/Operational>

## ETF 与印花税

印花税豁免必须按证券确认，不能只凭代码猜测。成本模型支持买卖方向覆盖。产品将 `2800.HK` 作为“盈富基金（可交易 ETF）”而不是恒生指数；其默认模板可以把印花税设为 0，但 UI 必须显示并要求用户确认该费用口径。

## 调整后价格

同一日使用 `Adjusted Close / raw Close` 因子统一调整 Open、High、Low、Close。拆股和提供器纳入 Adjusted Close 的现金分派会反映在历史价格中；回测不单独模拟现金股息入账。该模型适合总回报近似研究，但不能解释每次分派的现金时间点。

## 交易日

使用 `exchange-calendars` 的 `XHKG` 日历识别 HKEX session、节假日和半日市。缺失的预期 session 会被报告，不会 forward-fill。个股停牌与 provider 缺行在没有额外停牌数据时无法自动区分，这是当前已知限制。
