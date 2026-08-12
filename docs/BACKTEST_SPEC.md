# QuantLab Phase 1 回测规范

状态：Phase 1 第三质量门  
规范版本：1.1  
适用范围：SPY、美国市场调整后日线、双均线、只做多

本文档是 Phase 1 回测行为的唯一规范。实现、页面、HTML 报告、交易 CSV 和测试若与本文档冲突，以本文档为准。

## 1. 明确范围

- 只支持日线数据，不解释分钟线、盘中成交顺序或隔夜挂单。
- 只做多，不做空，不使用杠杆，不借入现金或证券。
- 目标仓位只有 `0%`（空仓）和 `100%`（全仓）两种状态。
- 使用小数股，不做整股取整。
- “全仓”表示在从空仓切换为持仓时，用当时全部可用现金买入，并预留本次买入手续费。持仓期间不因价格变化再平衡。
- Phase 1 只有双简单移动平均线策略和买入持有基准。
- 初始资金必须大于零，用户区间必须至少包含一个有效交易日。

## 2. 行情数据与公司行为调整

### 2.1 标准化列

引擎接收以下固定列，列名全部使用小写：

`date, open, high, low, close, volume`

其中 `open/high/low/close` 必须是同一公司行为调整口径下的日线价格。回测不允许混用原始 Open 与调整后 Close。

### 2.2 调整规则

当数据源同时提供原始 OHLC、原始 Close 和 Adjusted Close 时，每行使用同一个调整因子：

```text
adjustment_factor = adjusted_close / raw_close
adjusted_open  = raw_open  * adjustment_factor
adjusted_high  = raw_high  * adjustment_factor
adjusted_low   = raw_low   * adjustment_factor
adjusted_close = raw_close * adjustment_factor
```

选择这一方案的原因是拆股和现金分红必须同时、等比例地作用于同一交易日的 OHLC，才能保证信号价格、成交价格和期末估值处于同一尺度。不得只调整 Close。

- 不在回测引擎内再次调整已经由提供器统一调整过的 OHLC。
- Phase 1 唯一生产提供器为 Yahoo Finance，经 yfinance 获取 `auto_adjust=False` 的原始 OHLC、Adjusted Close 和原始成交量；不做多提供器回退。
- 提供器调用固定使用 `repair=False` 和 `rounding=False`：不让 yfinance 静默重建或两位舍入行情；原始返回值必须通过本项目验证后才能进入回测。
- Yahoo 对 Adjusted Close 的定义包含适用的拆股和股息分配调整。本项目使用该序列的调整因子，因此当前口径同时反映拆股和现金分红对历史价格序列的影响。
- 这是“调整后价格回测”：现金分红通过历史价格调整体现，不另外模拟现金到账或分红再投资交易。因此结果用于同口径策略比较，不应解释为逐笔复原券商现金流水。
- 本项目能验证数值、OHLC 关系、日期、预热数量和数据指纹，但不能证明 Yahoo 上游每次公司行为调整都无误；上游历史修订会改变 SHA256，属于必须在报告中披露的数据版本风险。
- `volume` 不参与策略、成交或估值；保留数据源的非负原始数值，不乘价格调整因子，也不发明成交量调整规则。
- `date` 表示美国交易所的交易日。若输入含时区时间戳，先转换为 `America/New_York`，再取交易日日期并移除时区。
- 日期必须唯一并严格升序；重复日期直接报错，不自动保留任意一行。
- OHLCV 必须是有限数值，不接受空值、NaN 或正负无穷。
- OHLC 必须大于零，`volume` 必须大于等于零。
- 每行必须满足 `high >= max(open, close)` 且 `low <= min(open, close)`。

## 3. 双均线信号

在交易日 T 的调整后收盘价产生简单移动平均线：

```text
short_ma[T] = 最近 short_window 个调整后 Close 的算术平均
long_ma[T]  = 最近 long_window 个调整后 Close 的算术平均
```

目标仓位定义为：

```text
short_ma[T] > long_ma[T]  -> target[T] = 1.0
short_ma[T] <= long_ma[T] -> target[T] = 0.0
```

- “严格高于”是有意选择；均线相等时保持空仓。
- `short_window` 和 `long_window` 必须是正整数，且 `short_window < long_window`，否则在回测开始前报错。
- 长均线尚未形成时，目标仓位固定为 `0.0`，不使用部分窗口均值。
- 信号只表达目标状态，不负责位移、成交、费用或估值。

## 4. 时间顺序与成交条件

每个用户区间内交易日按以下顺序处理：

1. 开盘前读取前一个交易日收盘后已经确定的目标仓位。
2. 仅当该目标仓位与当前实际持仓状态不同，才在当天调整后 Open 成交。
3. 成交后更新现金和持仓数量。
4. 当天收盘按调整后 Close 计算日终净值。
5. 使用当天调整后 Close 更新均线，并产生供下一个交易日使用的目标仓位。

因此，T 日收盘后产生的信号最早只能在 T+1 日开盘成交。不得用 T 日信号赚取 T-1 收盘至 T 收盘的收益，也不得在 T 日收盘价上回填成交。

- `0 -> 1`：买入。
- `1 -> 0`：卖出全部持仓。
- `0 -> 0` 或 `1 -> 1`：不成交，不收取费用和滑点。
- 最后一个交易日收盘后即使产生新目标，也没有下一根 K 线可执行，不创建虚构成交。

## 5. 预热数据

- 用户开始日期之前的行情仅用于形成均线。
- 预热期没有初始资金曲线、现金、持仓、交易、收益、费用、滑点或统计指标。
- 预热期内即使目标仓位多次变化，也不成交。
- 最后一个预热交易日收盘后得到的有效目标仓位，可以在用户区间第一根 K 线开盘执行。
- Phase 1 生产数据入口必须在用户开始日期之前保留至少 `longest_lookback` 根有效交易日；数量按实际行情行统计，不按自然日估算。
- 标准化后若预热交易行不足，数据层必须明确报错，不能以大量 NaN 或强制空仓继续生产回测。引擎对手工输入的防御性行为不替代生产数据层校验。

选择允许“预热信号在首个区间交易日开盘执行”，是为了避免人为强制策略在每次回测开始时空仓若干天，同时仍保证所有成交都发生在用户选择区间内。

## 6. 成交、手续费与滑点

设开盘参考价格为 `O`、滑点率为 `s`、手续费率为 `f`，二者均为非负小数。

Phase 1 要求 `0 <= f < 1` 且 `0 <= s < 1`；超出范围直接报错。选择严格小于 1 是为了保证卖出成交价保持为正，并排除明显不合理的成本输入。

### 6.1 买入

```text
buy_fill_price = O * (1 + s)
quantity = cash_before / (buy_fill_price * (1 + f))
trade_notional = quantity * buy_fill_price
buy_fee = trade_notional * f
cash_after = cash_before - trade_notional - buy_fee
buy_slippage_amount = quantity * (buy_fill_price - O)
```

买入数量必须使用上述公式预留手续费。数学上 `cash_after` 应为零；浮点运算后绝对值不超过 `1e-9` 的残差归零。若现金小于 `-1e-9`，实现必须报错，不能静默透支。

### 6.2 卖出

```text
sell_fill_price = O * (1 - s)
quantity_sold = all_current_holdings
trade_notional = quantity_sold * sell_fill_price
sell_fee = trade_notional * f
cash_after = cash_before + trade_notional - sell_fee
sell_slippage_amount = quantity_sold * (O - sell_fill_price)
holdings_after = 0
```

- 手续费按包含滑点后的实际成交金额双边收取。
- 滑点金额已经通过成交价影响现金，不能再从现金中重复扣除。
- 每次成交的手续费和滑点金额都必须单独记录，并可汇总到报告。

### 6.3 逐日账本的无成交字段

逐日账本使用一套固定空值规则，避免 `None`、空字符串和数值零混用：

- 无成交日的 `action` 为 `NONE`，`execution_price` 为 IEEE-754 `NaN`。
- 无成交日的 `trade_quantity`、`fee` 和 `slippage_cost` 均为数值 `0.0`。
- `raw_open`、`cash`、`quantity`、`close` 和 `equity` 每日都必须有有限数值，不得留空。
- `NaN` 只用于表达逐日账本中的“无成交价格”，不得进入现金、持仓、费用、滑点、净值或指标计算。
- 未来导出 CSV 时可以把该 `NaN` 显示为空字符串，但不得把展示值写回引擎。

## 7. 净值、收益和最大回撤

每个用户区间交易日收盘后的净值为：

```text
equity[T] = cash_after_open_trades[T] + holdings[T] * adjusted_close[T]
```

总收益率为：

```text
total_return = final_equity / initial_capital - 1
```

最大回撤计算序列必须在第一日日终净值之前显式包含初始净值：

```text
drawdown_series = [initial_capital] + daily_equity
running_peak[T] = max(drawdown_series[0:T+1])
drawdown[T] = drawdown_series[T] / running_peak[T] - 1
max_drawdown = min(drawdown)
```

这样可以捕捉首日买入手续费和滑点相对初始资金造成的立即回撤。

## 8. 交易账本

一次买入及其对应的全部卖出构成一笔完整交易。Phase 1 不允许加仓、减仓或部分卖出，因此交易配对必须是一对一。

每笔账本至少包含：

- 状态：内部值 `OPEN` / `CLOSED`，中文显示“持仓中” / “已平仓”。
- 入场日期、参考 Open、实际成交价、数量、名义金额、手续费、滑点金额。
- 平仓交易还包含退出日期、参考 Open、实际成交价、名义金额、手续费、滑点金额。
- 未平仓交易包含期末估值日期和最后调整后 Close，退出字段为空。
- 持有交易日数：从入场交易日到退出交易日的交易日索引差；未平仓则计算到期末估值日。

已平仓交易的损益定义：

```text
gross_pnl_before_costs = quantity * (exit_reference_open - entry_reference_open)
total_slippage = entry_slippage_amount + exit_slippage_amount
total_fees = entry_fee + exit_fee
net_pnl = gross_pnl_before_costs - total_slippage - total_fees
net_return = net_pnl / (entry_notional + entry_fee)
```

未平仓交易的期末未实现损益定义：

```text
gross_unrealized_pnl = quantity * (last_adjusted_close - entry_reference_open)
net_unrealized_pnl = gross_unrealized_pnl - entry_slippage_amount - entry_fee
```

未平仓交易不得虚构卖出日期、卖出成交价、卖出手续费或卖出滑点。

## 9. 交易次数与胜率

- 完整交易次数只统计状态为 `CLOSED` 的账本行。
- 一次买入加对应卖出算一笔，不把买入和卖出分别计为两次。
- 胜率只统计已平仓交易：`net_pnl > 0` 的笔数除以完整交易次数。
- `net_pnl == 0` 不是盈利交易。
- 未平仓交易不进入分子或分母。
- 零笔已平仓交易时，内部胜率为 `None`，页面和报告显示 `N/A`，不得显示 `0%`。

## 10. 买入持有基准

- 基准在用户区间第一根 K 线的调整后 Open 买入，不等待策略信号。
- 基准使用与策略完全相同的初始资金、手续费率、滑点率、小数股和买入数量公式。
- 基准持有到用户区间最后一个交易日，并按最后调整后 Close 估值。
- 基准期末不虚构卖出，因此没有卖出手续费或卖出滑点。
- 基准最大回撤同样显式包含初始净值。
- 基准和策略必须读取同一份标准化行情数据、相同用户区间和相同成本配置。

## 11. 内部精度、测试容差与展示舍入

### 11.1 内部计算

- 行情、现金、数量、费用、滑点、净值和收益率统一使用 IEEE-754 `float64`。
- 除绝对值不超过 `1e-9` 的现金残差归零外，任何中间步骤都不得舍入。
- 不得把页面格式化后的金额或数量写回引擎继续计算。
- 黄金测试数值断言使用 `abs_tol=1e-9`、`rel_tol=1e-12`。字符串、日期、状态和交易次数必须精确相等。

选择 `float64` 而不是在 Phase 1 全面引入 `Decimal`，是因为行情和 Pandas 计算本身使用浮点数；通过禁止中间舍入、固定容差和黄金样例可以保持可复核性，同时避免两套数值类型造成额外复杂度。

### 11.2 人类可读展示

UI 和 HTML 报告只在最后一步使用十进制 `ROUND_HALF_UP`：

- 货币金额：2 位小数。
- 成交价和估值价：4 位小数。
- 持仓数量：8 位小数。
- 百分比：先乘 100，再保留 4 位小数，并附 `%`。
- 交易次数：整数。
- 空胜率、空退出字段：`N/A`。

交易 CSV 是机器可读输出，不使用千位分隔符；数值字段保留 10 位小数，空字段为空字符串。CSV 的格式化值同样不得参与后续计算。

## 12. 标准化行情数据 SHA256

数据指纹覆盖本次运行实际使用的全部标准化行情行，包括预热行和用户区间行。指纹只描述行情内容，不描述运行环境。

规范化步骤必须严格按以下顺序执行：

1. 固定列顺序为 `date,open,high,low,close,volume`。
2. 日期先转换为美国市场交易日，再序列化为 `YYYY-MM-DD`，不带时间和时区后缀。
3. 按 `date` 严格升序排序；重复日期直接报错。
4. 六个字段均不允许缺失、NaN 或无穷；不使用空字符串、`null` 或零值替代缺失数据。
5. `open/high/low/close/volume` 全部使用十进制定点格式 `%.10f`，不使用科学计数法。
6. 使用 CSV 逗号分隔；包含固定表头；字段不含额外空格。
7. 文本编码为 UTF-8、无 BOM。
8. 换行符固定为 LF（`\n`），包括最后一行后的一个终止换行。
9. 对上述完整字节序列计算 SHA-256，保存为 64 位小写十六进制字符串。

以下 G13 标准化文本：

```text
date,open,high,low,close,volume
2024-12-16,50.0000000000,52.0000000000,49.0000000000,51.0000000000,1000.0000000000
2024-12-17,51.0000000000,53.0000000000,50.0000000000,52.0000000000,2000.0000000000
```

对应 SHA256：

```text
31875d128ed2a3ca2f9515ed31b4bb561e6f38f002b8cf30d643d9a106102b26
```

请求区间使用闭区间 `[requested_start_date, requested_end_date]`。yfinance 的 `end` 参数是开区间，因此提供器适配层请求到 `requested_end_date + 1` 个自然日，再按纽约交易日期闭区间过滤。标准化结果按日期升序，保留恰好 `longest_lookback` 根预热交易行和区间内全部有效交易行。若请求边界是周末或休市日，元数据分别记录请求日期和区间内实际首末交易日，不制造不存在的交易日。

以下内容作为独立元数据保存，不参与行情数据 SHA256：

- 数据源名称和提供器版本。
- 抓取时间。
- QuantLab 软件版本。
- 标的代码。
- 用户开始和结束日期。
- 预热行数、策略参数、初始资金、手续费率和滑点率。

`fetched_at_utc` 必须是带 UTC 时区的独立元数据；它以及上述元数据变化均不得改变行情 SHA256。

## 13. 展示模型与报告输出

### 13.1 唯一事实来源

- `MarketDataResult` 是标准化行情及数据元数据的事实来源。
- `ComparisonResult` 是策略与买入持有的逐日账本、交易账本和绩效指标事实来源。
- `BacktestConfig` 是初始资金、成本率和请求日期的事实来源；这些值不能从成交结果反推。
- `BacktestReportView` 只能由上述对象构造一次。它保存原始值和最终展示文本，HTML、交易 CSV 和未来 UI 只能消费该对象。
- 展示模型不得运行策略、位移信号、执行成交或重新计算手续费、滑点、回撤、胜率及交易次数。唯一允许新增的比较值是 `策略总收益率 - 基准总收益率`，并且只在构造展示模型时计算一次。
- 构造展示模型时必须校验策略和基准日期轴一致、只包含正式分析区间、初始权益与配置一致，以及账本状态数与指标交易数一致。校验失败时停止输出，不能静默修补。

### 13.2 确定性运行标识

`run_id` 是以下固定顺序字段的规范化 SHA256 前 16 位小写十六进制：

```text
software_version
symbol
requested_start_date
requested_end_date
actual_start_date
actual_end_date
analysis_start_date
analysis_end_date
data_sha256
initial_capital
fee_rate
slippage_rate
strategy_name
short_window
long_window
```

- 日期使用 `YYYY-MM-DD`。
- 三个浮点配置值使用 Python `float64` 的 locale 无关 `.17g` 文本。
- 字段以固定顺序的二元素数组序列编码为紧凑 JSON，`ensure_ascii=True`、`allow_nan=False`、UTF-8，无额外空白。
- `generated_at_utc` 和 `fetched_at_utc` 不参与 `run_id`。相同输入在不同时间重新导出仍是同一次可复现运行，但报告中的生成时间会变化。

### 13.3 HTML

- HTML 使用 UTF-8，CSS 和净值图全部内嵌，不引用 CDN、远程脚本、字体、图片或样式。
- 报告不含脚本，不含本地绝对路径、提供器原始响应或敏感配置；所有外部文本先进行 HTML 转义。
- 净值图是确定性内嵌 SVG。两条曲线直接读取策略和基准 `daily.equity`，使用相同正式分析日期轴；预热行不进入曲线。
- HTML 指标及交易表使用展示模型中已经格式化的文本；模板不得根据逐日数据或账本重新汇总指标。

### 13.4 策略交易 CSV

CSV 只包含策略 `TradeRecord`，一笔交易对应一行，不添加基准交易或合计行。字段顺序固定为：

```text
run_id,software_version,generated_at_utc,symbol,strategy_name,short_window,long_window,
requested_start_date,requested_end_date,actual_start_date,actual_end_date,
analysis_start_date,analysis_end_date,source,source_version,data_sha256,adjustment_method,
initial_capital,fee_rate,slippage_rate,trade_id,status,entry_date,entry_raw_price,
entry_execution_price,quantity,entry_fee,entry_slippage_cost,exit_date,exit_raw_price,
exit_execution_price,exit_fee,exit_slippage_cost,mark_date,mark_price,holding_days,
gross_pnl,total_fees,total_slippage_cost,net_pnl,net_return
```

- 编码为 UTF-8、无 BOM；换行固定为 LF，末行包含 LF。
- 日期固定为 `YYYY-MM-DD`，UTC 时间固定为 `YYYY-MM-DDTHH:MM:SSZ`。
- 金额、价格、数量、成本率和收益率原始数值均使用十进制定点 10 位小数、`ROUND_HALF_UP`，不使用科学计数法、千位分隔符或百分号。
- `trade_id`、均线窗口和持有日数使用十进制整数。
- `None` 写为空字符串。`OPEN` 交易的全部退出字段必须为空，估值日期和价格使用独立 `mark_*` 字段。
- 字符串字段按标准 CSV 引号规则转义。输出必须可由 Python 标准库 `csv` 和 Pandas 重新读取。
- 零笔策略交易时仅写固定表头，不制造虚假交易行。

### 13.5 运行清单 Manifest

每次运行同时生成一个 UTF-8 JSON Manifest，作为交易 CSV 在零交易时仍可独立追溯运行元数据的文件级载体。Manifest 只能序列化 `BacktestReportView` 中已有事实，不得重新计算回测指标。

字段结构和顺序固定，至少包含：

```text
schema_version,run_id,software_version,generated_at_utc,symbol,strategy_name,
short_window,long_window,requested_start_date,requested_end_date,
actual_start_date,actual_end_date,analysis_start_date,analysis_end_date,
initial_capital,fee_rate,slippage_rate,data_source,data_source_version,
fetched_at_utc,warmup_row_count,analysis_row_count,adjustment_method,data_sha256,
strategy_trade_count,strategy_open_trade_count,html_filename,csv_filename,
manifest_filename
```

- JSON 使用 UTF-8、LF，末尾固定保留一个换行。
- 禁止 `NaN`、`Infinity`、本地绝对路径、提供器原始响应、密钥和调试信息。
- 相同 `BacktestReportView` 必须产生字节一致的 Manifest。
- `generated_at_utc` 可以改变 Manifest 文本，但不得改变 `run_id`。
- HTML、CSV 和 Manifest 文件名都必须包含 `quantlab`、`spy` 和同一个 `run_id`。
- 零交易时 CSV 仍只有标准表头；HTML 与 Manifest 承载完整运行元数据，不创建虚假交易。

### 13.6 Streamlit 执行语义

- Phase 1 默认页面仅允许固定 SPY、日线和一套 SMA 双均线策略。
- 页面控件表示“待运行参数”；修改控件不得下载数据或执行回测。
- 只有点击“运行回测”后，页面才构造一次请求并调用一次统一工作流。
- 成功结果以完整不可变输出对象保存到 `st.session_state`。普通页面重绘和下载操作不得重新抓取行情或重复回测。
- 控件与已保存请求不一致时，页面必须明确提示当前仍展示上一次结果，且摘要继续显示上一次实际参数和 `run_id`。
- 页面指标、净值曲线、交易记录、假设和警告只能消费 `BacktestReportView`；不得直接从 prices、daily、trades、`PerformanceMetrics` 或 `ComparisonResult` 重算任何财务结果。
- 页面错误不得暴露本地绝对路径、长堆栈、密钥或提供器原始响应，也不得自动回退到 Demo、CSV、Crypto 或其他提供器。
- 可复现性的准确表述是：相同软件版本、标准化行情、参数和数据指纹可复现相同计算结果；上游数据提供器可能修订或在不同会话返回不同历史数据，抓取时间本身不是永久复现保证。

## 14. 明确排除项

Phase 1 不定义税费、分红现金流拆分、借贷利息、做空、杠杆、限价单、停牌成交、盘中止损、整股约束、成交量冲击、参数优化、纸上交易或真实下单。遇到这些情况不能自行推断，应在后续规范版本中显式加入。
