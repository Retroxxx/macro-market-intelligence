# Architecture Audit

## 1. 官方当前架构

NiuOne 是 Vue 3/Vite 前端、FastAPI 单监听端口 Dashboard、独立 scheduler 和 NewsNow sidecar。`app/dashboard/fastapi_app.py` 是 HTTP 组合层，市场接口集中在 `app/dashboard/routers/market.py`，数据源及采样编排仍由 Dashboard 组合层提供。官方 Compose 使用 `dashboard`、`scheduler`、`newsnow` 三个服务；官方运行数据统一位于 `/data` 对应的 `niuone-data` volume。

## 2. 选定扩展位置

本地宏观层采用独立 `macro` sidecar，而不是修改官方 FastAPI 或 Vue 业务代码：

```text
browser :8790
    ↓
local_ext.api.app
    ↓ HTTP read-only
 dashboard:8787/api/*
    ↓
NiuOne official services
```

`local_ext/adapters/niuone` 是唯一官方边界；宏观规则只接收规范化的 `NiuOneSnapshot`。`local_web` 由 macro sidecar 自己提供，官方 `/`、Dashboard 路由和静态样式不变。

## 3. 复用的官方 API

- `/api/indices`：指数代理和风格基准。
- `/api/market_breadth`：红绿盘、涨跌停、市场宽度、成交额和日内采样。
- `/api/sectors`：行业行及行业涨跌字段。
- `/api/money_flow`：资金流读模型。

这些 API 通过 HTTP 调用，不直接依赖 `app` 内部实现、数据库或运行文件。

## 4. 高冲突风险文件

| 文件 | 风险 | 本轮处理 |
|---|---|---|
| `app/dashboard/fastapi_app.py` | 上游路由/生命周期频繁变更 | 不修改 |
| `app/dashboard/routers/market.py` | 官方 API 合同变化 | 不修改，adapter 测试隔离 |
| `web/src/router.js`、`DashboardPage.vue` | 页面路由和组件结构变化 | 不修改，sidecar 独立页面 |
| `compose.yaml` | 官方服务编排变更 | 不修改，使用 `-f deploy/compose.prod.yaml` overlay |
| `Dockerfile`、`.dockerignore` | 官方构建上下文变更 | 仅 `.dockerignore` 增加本地构建白名单 |

## 5. 不建议修改的文件

不要把宏观规则、数据库 schema、前端卡片或新定时任务加入官方 `app/`、`web/`、`frontend/`。不要把本地数据写入 `niuone-data`，不要修改模拟交易、策略、候选、回测或严格前向逻辑。

## 6. 数据与 schema 风险

官方接口字段可能变化；adapter 对缺失字段采用 `None`/空集合，记录非敏感错误类型。宏观计算对缺失数据输出 `UNKNOWN`，不使用本地推导覆盖官方交易事实。`MarketContext` 固定 `market-context-v1`，每个规则输出自己的 `rules_version`。

## 7. Frontend integration 风险

sidecar 页面使用原生 ES modules，无 npm 依赖、无官方组件修改、无官方 CSS 修改。删除 `local_web` 和 macro 服务即可恢复官方页面。

## 8. Docker integration 风险

生产通过 Compose overlay 新增 `macro` 服务、独立 `local-macro-data` volume、健康检查、日志轮转和固定镜像标签。官方 Compose 文件仍是基础事实来源。宏观服务默认仅绑定 `127.0.0.1:8790`，若需要公网访问应由反向代理或明确安全组配置暴露。

## 9. Upstream merge 风险

风险集中在：`.dockerignore` 的本地白名单、官方 API 字段合同和 overlay 与官方服务名的兼容性。代码本身位于 `local_ext/`、`local_web/`、`deploy/`、`tests_local/`、`docs_local/`，upstream 更新一般不会触碰。每次同步后先跑 `tests_local` 和 Compose 配置检查，再部署。

## 10. 当前边界

第一版 Sector Rotation 只有在官方行业数据提供持续性字段时才输出确定状态；没有持续性证据时输出 `UNKNOWN`，不会把单日涨幅排名伪装成轮动状态。Style Matrix 使用可识别的官方指数代理，缺少代理时输出 `UNKNOWN`。Narrative、Global Tape、Event Radar、Level1 聚合和自动交易本轮不实现。
