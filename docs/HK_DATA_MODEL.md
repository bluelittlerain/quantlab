# 港股数据模型

## 领域对象

- `HKSymbol`：规范代码、交易所、货币、可选 provider 名称和本地别名。
- `BoardLotConfig`：每手股数、`AUTO/USER` 来源、核验时间和确认状态。
- `HKTradingCostConfig`：佣金、最低佣金、印花税、交易费、交易征费、会财局征费、交收费和滑点。
- `CostBreakdown`：每次成交的七项成本与守恒合计。
- `HKTradeRecord`：整股数量、入场/退出成本分解、持有交易日、毛损益、净损益和净收益率。
- `HKPerformanceMetrics`：基础指标与 CAGR、波动率、Sharpe、Calmar、敞口、换手、Profit Factor、平均交易和成本指标。
- `HKRunOutput`：行情事实、基准行情、目标信号、交易日验证和比较结果。

## 指标定义

- CAGR：按第一和最后分析日期之间的实际日历天数年化。
- 年化波动率：包含初始权益到首日权益的日收益，样本标准差乘 `sqrt(252)`。
- Sharpe：无风险利率暂取 0；日收益均值除样本标准差后乘 `sqrt(252)`。
- Calmar：CAGR 除以最大回撤绝对值；零回撤时为 N/A。
- Market Exposure：分析日收盘后持仓数量大于零的天数占比。
- Turnover：成交名义金额合计除以分析期平均权益。
- Profit Factor：已平仓净盈利总额除以已平仓净亏损绝对值；无亏损时为 N/A。
- Average Trade Return / Holding Period：只统计已平仓交易。
- Total Trading Costs：所有实际成交的分项费用与滑点合计。
- Cost / Gross Profit：总成本除以已平仓正毛利润；无正毛利润时为 N/A。

## SQLite v1

数据库位于 `%LOCALAPPDATA%\QuantLab\quantlab.db`，包含 `schema_meta`、`runs`、`presets`、`settings`、`recent_symbols`。连接逐操作创建并显式关闭。未知 schema version 或损坏会返回可恢复错误，不会静默删除数据库。

## API 事实边界

React 只读取 API 中的 metrics、series、trades 和 cost summary。日期使用 ISO `YYYY-MM-DD`，时间使用带偏移 ISO 8601，金额保留原始数值并在前端按 HKD 格式化。
