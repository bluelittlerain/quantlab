# 前端架构选择

## 结论

v0.2 使用 FastAPI + React + TypeScript + Vite + Ant Design + Apache ECharts。桌面壳继续使用本地服务与隔离 Edge/Chrome app mode，不引入 Electron。

## 比较

### 继续 Streamlit

优点是 Python 垂直开发快，旧页面可以继续回归。缺点是日期、tooltip、表格、组件 DOM、三态主题和键盘行为受框架控制，历史上已经产生大量脆弱 CSS。它不再适合作为长期产品主界面。

### FastAPI + React

Ant Design 提供正式 `zh_CN` locale、DatePicker、Table、Form、Drawer 和主题算法；ECharts 提供可控的 dataZoom、tooltip、legend 和响应式图表。FastAPI 保持 Python 核心为事实来源并生成 OpenAPI。代价是 Node 构建链和 Windows 静态资源打包，但这些边界可测试且可维护。

### Electron / CEF / 原生 GUI

Electron 会重复打包 Chromium并显著增加磁盘和发布体积；CEF/Qt 引入更重的运行时和新 UI 技术。现有隔离浏览器壳已经解决扩展干扰，因此暂不采用。

## 状态与类型

- React Query 管理 API server state；局部表单与 UI 状态使用 React state。
- 不引入 Redux。
- TypeScript 类型手工与 OpenAPI schema 对齐，并由后端/前端契约测试防漂移。
- ECharts option 只由已序列化 API 数据构造，不做收益或成本计算。

## 主题与 locale

- `ThemeMode = SYSTEM | LIGHT | DARK`。
- SYSTEM 监听 `prefers-color-scheme`；手动模式存入 localStorage。
- Ant Design `ConfigProvider` 使用 `defaultAlgorithm/darkAlgorithm` 与 `zh_CN`。
- dayjs 使用 `zh-cn`。业务文案集中于 locale 模块，组件不散落框架英文。
