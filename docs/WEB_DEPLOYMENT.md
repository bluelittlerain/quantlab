# Web 部署边界

QuantLab 当前提供可自托管的单实例 Web 架构准备，不代表已经具备公开、多用户投资服务的安全能力。本轮没有部署任何服务器，也没有创建在线 Demo。

## 运行模型

`QUANTLAB_MODE` 支持：

- `DESKTOP`：loopback、SQLite、本地缓存和隔离浏览器。
- `LAN`：复用同一后端和核心，显式监听内网并要求启动周期配对。
- `WEB`：服务器运行方式；FastAPI 同源提供 Vite 静态资源与 API。

三种模式共用 `BacktestApplicationService`、行情标准化、回测会计、指标、序列化和导出实现，不存在 Web 专用回测分支。React 默认同源请求；只有前后端分开部署时才通过 `VITE_API_BASE_URL` 与明确的 `QUANTLAB_CORS_ORIGINS` 配置。

## 本地容器验证

```bash
docker compose -f docker-compose.example.yml up --build
```

默认访问 `http://127.0.0.1:8000`，数据卷为 `/data`。`.env.example` 只包含非敏感示例，真实 `.env` 被 Git 忽略。镜像使用多阶段构建，最终运行层不包含 Node 开发依赖，也不推送到任何 registry。

## 存储边界

`RunHistoryRepository`、`PresetRepository` 和 `SettingsRepository` 将应用层与 SQLite 解耦。桌面和单实例自托管仍使用 SQLite。正式公网多用户服务推荐 PostgreSQL，因为需要并发写入、事务、备份、迁移、逐用户隔离和可观测性；本版本未实现 PostgreSQL 适配器。

当前 SQLite 历史不能被误认为多用户数据系统。正式公网版本至少还必须增加：

- 身份验证、用户模型与逐用户授权；
- 逐用户历史、预设和数据隔离；
- HTTPS、可信代理配置与安全响应头；
- 速率限制、CSRF/会话策略和 secret 管理；
- provider 配额、超时、重试和服务条款审查；
- PostgreSQL、迁移、加密备份与恢复演练；
- 结构化日志、监控、告警、审计和隐私政策。

## 网络与代理

FastAPI 只监听内部应用端口，不直接负责公网 TLS。生产应由平台 ingress 或反向代理负责 HTTPS、TLS termination、可信代理头和请求体限制。CORS 默认关闭；启用 credentials 时只接受显式 `http`/`https` origin，配置 `*` 会在启动时失败。

`/api/health/live` 只证明进程可响应；`/api/health/ready` 检查 API 与数据库，不访问 Yahoo。Vite hashed assets 使用长期 immutable cache，`index.html` 与 SPA fallback 使用 `no-cache`。

## GitHub 的职责

GitHub 只作为源码、文档、CI/CD 配置和 Windows Release 中心。GitHub Pages 不能运行 FastAPI、SQLite、provider 和配对逻辑，因此不是 QuantLab 完整产品的部署方案。本仓库不提供静态假数据 Pages Demo，也不提供虚假的在线链接。
