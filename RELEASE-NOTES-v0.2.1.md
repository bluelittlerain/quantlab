# QuantLab v0.2.1

QuantLab v0.2.1 是项目首次公开发布版本。它是一款本地运行的量化研究原型，聚焦可信、
可复现的港股日线回测。

## 主要更新

- 使用现金账本驱动回测，并明确采用 T+1 开盘执行规则。
- 支持港交所代码标准化和整数手数（board lot）执行。
- 透明拆分券商佣金、法定费用、交收成本与滑点。
- 策略与可交易基准采用相同的执行纪律进行比较。
- 提供确定性的行情指纹、运行标识与黄金测试。
- 提供 React + FastAPI 研究界面，以及本地历史和研究预设。
- 支持导出 HTML、CSV、Manifest 和统一 ZIP。
- 提供使用隔离浏览器配置的自包含 Windows 桌面包。

## 安装方式

1. 下载 `QuantLab-v0.2.1-windows-x64.zip` 和 `SHA256SUMS.txt`。
2. 校验 ZIP 的 SHA256。
3. 解压压缩包。
4. 打开 `QuantLab` 目录并运行 `QuantLab.exe`。

QuantLab 会启动本地 FastAPI 服务，并在隔离的 Edge 或 Chrome 应用窗口中打开 React 界面。
关闭应用后，本地服务会停止并释放端口。

## 已知限制

- 仅供研究使用，不连接券商，也不支持真实交易。
- Yahoo/yfinance 可能修订历史数据，也可能暂时不可用。
- 部分证券的手数元数据可能需要人工核验。
- 当前公开流程只包含一种 SMA 策略，不支持做空或杠杆。
- Windows 可执行文件尚未进行代码签名，可能触发 SmartScreen。
- 历史回测不代表未来表现，也不构成任何盈利保证。

<details>
<summary>English</summary>

# QuantLab v0.2.1

QuantLab v0.2.1 is the first public release of the project. It is a local quantitative research
prototype focused on trustworthy, reproducible daily backtests with Hong Kong market support.

## Highlights

- Cash-ledger backtesting with explicit T+1 open execution.
- HKEX symbol normalization and board-lot execution.
- Transparent broker commission, statutory fees, settlement costs, and slippage.
- Tradable benchmark comparison under the same execution discipline.
- Deterministic market-data fingerprints, run IDs, and golden tests.
- React and FastAPI research interface with local history and presets.
- HTML, CSV, Manifest, and combined ZIP exports.
- Self-contained Windows desktop package with an isolated browser profile.

## Known Limitations

- Research use only; there is no live trading or brokerage connection.
- Yahoo/yfinance historical data may be revised or temporarily unavailable.
- Board-lot metadata may require manual verification for some securities.
- The public workflow contains one SMA strategy and does not support shorting or leverage.
- The Windows executable is not code-signed and may trigger SmartScreen.
- Historical backtests do not guarantee future profitability.

## Installation

1. Download `QuantLab-v0.2.1-windows-x64.zip` and `SHA256SUMS.txt`.
2. Verify the ZIP SHA256.
3. Extract the archive.
4. Open the `QuantLab` directory and run `QuantLab.exe`.

QuantLab starts a local FastAPI service and opens the React interface in an isolated Edge or
Chrome application window. Closing the application stops the service and releases its port.

</details>
