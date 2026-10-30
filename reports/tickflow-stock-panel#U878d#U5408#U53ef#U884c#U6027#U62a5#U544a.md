# tickflow-stock-panel 融合可行性报告

> **审计性质**：只读源码级审计，未修改任何用户代码
> **审计目标**：https://github.com/shy3130/tickflow-stock-panel
> **审计日期**：2026-08-22
> **项目 Star**：3405 | **Fork**：795 | **主语言**：Python
> **最终评级**：**B 级（需改造）**

---

## 一、项目整体架构分析

### 1.1 使用语言与框架

| 层级 | 技术选型 | 代码依据 |
|------|---------|---------|
| **后端语言** | Python ≥ 3.11 | README.md 技术栈表；`.env.example` 无版本锁定 |
| **后端框架** | FastAPI + Pydantic v2 + APScheduler + sse-starlette | README.md 技术栈表；`backend/app/main.py` |
| **数据计算** | Polars（毫秒级全A股扫描） | README.md；`backend/app/indicators/pipeline.py`（82KB） |
| **数据查询** | DuckDB | README.md topics 标签；`backend/app/db_safe.py` |
| **数据存储** | Parquet（分区存储） | `backend/app/parquet.py`；depth_service.py 落盘 `data/depth5/date=xxx/part.parquet` |
| **回测引擎** | vectorbt（全项目唯一 pandas 边界） | README.md 技术栈表 |
| **前端** | React 18 + Vite + TypeScript + Tailwind + Tanstack Query + Lightweight Charts + ECharts | README.md 技术栈表 |
| **部署** | Docker 两阶段构建，前端 dist 拷入后端镜像，**单容器** | README.md；`Dockerfile` |

### 1.2 数据层结构

项目采用**多数据源提供者架构**，核心位于 `backend/app/data_providers/`：

```
backend/app/data_providers/
├── base.py              # MarketDataProvider Protocol 协议定义（接口契约）
├── registry.py          # 提供者注册器（当前仅注册 tickflow）
├── normalizer.py        # 数据标准化（统一 Polars Schema）
├── schemas.py           # 数据模式定义
├── tickflow_provider.py # TickFlow 官方 SDK 提供者实现
└── custom/              # 自定义数据源框架
    ├── config.py        # YAML 配置解析
    ├── loader.py        # 提供者加载器（22KB）
    ├── mapper.py        # 字段映射器
    └── provider.py      # 通用 HTTP 提供者基类（13KB）
```

此外，`backend/app/plugins/stocksdk/` 是一个**内置免费数据源插件**，通过 Node.js 子进程调用东方财富数据。

### 1.3 核心模块目录

| 目录 | 大小/关键文件 | 功能 |
|------|-------------|------|
| `backend/app/api/` | 25+ 路由文件，`kline.py`(48KB), `backtest.py`(39KB), `screener.py`(34KB) | API 路由层 |
| `backend/app/services/` | `quote_service.py`(75KB), `kline_sync.py`(44KB), `depth_service.py`(26KB) | 核心业务服务 |
| `backend/app/tickflow/` | `client.py`, `capabilities.py`, `policy.py`(628行), `rate_limits.py` | TickFlow SDK 封装与能力探测 |
| `backend/app/backtest/` | `engine.py`(139KB), `matrix.py`(135KB), `strategy.py`(85KB) | 回测引擎 |
| `backend/app/strategy/` | 18 个内置策略 + `ai_generator.py` + `monitor.py` | 选股策略引擎 |
| `backend/app/indicators/` | `pipeline.py`(82KB), `levels.py`(26KB) | 技术指标流水线 |
| `backend/app/jobs/` | `daily_pipeline.py`(49KB) | 盘后定时任务 |
| `backend/app/plugins/stocksdk/` | `bridge.mjs`, `provider.py`, `bridge.py` | 免费东方财富数据源插件 |

### 1.4 数据流向

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据来源层                                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ TickFlow SDK │  │ stock-sdk(东财免费)│  │ 自定义HTTP/CSV/JSON│  │
│  │ (付费/免费)   │  │ (Node子进程)       │  │ (custom框架)       │  │
│  └──────┬───────┘  └────────┬─────────┘  └────────┬──────────┘  │
└─────────┼─────────────────────┼───────────────────────┼────────────┘
          │                     │                       │
          ▼                     ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                   data_providers 适配层                           │
│  base.py(Protocol) → normalizer.py(统一Polars Schema)           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌────────────┐ ┌────────────────┐
    │ kline_sync.py   │ │quote_service│ │ depth_service  │
    │ (日K/分钟K同步)  │ │(实时行情轮询)│ │ (五档盘口轮询)  │
    └────────┬────────┘ └─────┬──────┘ └───────┬────────┘
             │                 │                  │
             ▼                 ▼                  ▼
    ┌──────────────────────────────────────────────────────┐
    │           Parquet 存储 + 内存缓存                      │
    │  kline_daily / kline_minute / enriched / depth5 /    │
    │  instruments / financial / indices                    │
    └──────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ 选股引擎    │ │ 回测引擎    │ │ 监控中心    │
    │ (screener) │ │ (vectorbt) │ │ (SSE推送)  │
    └────────────┘ └────────────┘ └────────────┘
```

**关键数据流特征**：
- 实时行情通过 `quote_service.py` 后台线程轮询（间隔按档位 1-60 秒），写入 `kline_daily` parquet 并增量计算 `enriched` 技术指标表
- 五档盘口通过 `depth_service.py` 独立线程轮询（Pro: 10-120s, Expert: 3-120s），仅针对涨跌停股，结果存 `data/depth5/` parquet
- 盘后通过 `daily_pipeline.py` 批量拉取日K + 计算 enriched 全量指标
- 所有实时更新通过 SSE（Server-Sent Events）推送到前端

---

## 二、真实数据能力分析（重点）

### 2.1 行情数据来源

#### 2.1.1 主数据源：TickFlow 官方 SDK

| 项目 | 详情 | 代码依据 |
|------|------|---------|
| **数据服务商** | TickFlow（tickflow.org） | README.md；`client.py:33-35` |
| **免费端点** | `https://free-api.tickflow.org` | `client.py:33` |
| **付费端点** | `https://api.tickflow.org` | `client.py:35` |
| **认证方式** | API Key（`TICKFLOW_API_KEY`） | `.env.example`；`client.py:56-68` |
| **调用方式** | Python SDK（`tickflow` 包），非直接 HTTP | `client.py:16` `from tickflow import AsyncTickFlow, TickFlow` |
| **是否免费** | 部分免费（none/free 档仅历史日K） | `tiers.yaml:27-36` |
| **是否需要Token** | 是（付费功能必须；无Key走none档） | `client.py:44-48` |

**TickFlow 五档能力体系**（`tiers.yaml` + `capabilities.py` 确认）：

| 能力 | none(无Key) | free(免费Key) | starter | pro | expert |
|------|:-----------:|:-------------:|:-------:|:---:|:------:|
| 历史日K(单只) | ✅ 60rpm | ✅ 60rpm | ✅ 60rpm | ✅ 120rpm | ✅ 300rpm |
| 历史日K(批量) | ✅ 60rpm/100只 | ✅ 60rpm/100只 | ✅ 30rpm/100只 | ✅ 60rpm/100只 | ✅ 120rpm/200只 |
| 复权因子 | ❌ | ❌ | ✅ 30rpm/50只 | ✅ 60rpm/100只 | ✅ 120rpm/200只 |
| 实时行情(按标的) | ❌ | ✅ 10rpm/5只 | ✅ 60rpm/50只 | ✅ 120rpm/100只 | ✅ 300rpm/500只 |
| 实时行情(批量) | ❌ | ❌ | ✅ 60rpm/50只 | ✅ 120rpm/100只 | ✅ 300rpm/500只 |
| 实时行情(标的池) | ❌ | ❌ | ✅ 20rpm | ✅ 60rpm | ✅ 120rpm |
| 分钟K | ❌ | ❌ | ❌ | ✅ 30rpm/100只 | ✅ 60rpm/200只 |
| 分时(intraday) | ❌ | ❌ | ❌ | ✅ 30rpm/1只 | ✅ 120rpm/1只 |
| 五档盘口(单只) | ❌ | ❌ | ❌ | ✅ 60rpm/1只 | ✅ 120rpm/1只 |
| 五档盘口(批量) | ❌ | ❌ | ❌ | ✅ 30rpm/100只 | ✅ 60rpm/200只 |
| 批量分时 | ❌ | ❌ | ❌ | ❌ | ✅ 60rpm/200只 |
| WebSocket推送 | ❌ | ❌ | ❌ | ❌ | ✅ 100订阅 |
| 财务数据 | ❌ | ❌ | ❌ | ❌ | ✅ 120rpm/100只 |

> **代码依据**：`tiers.yaml:27-73` 定义各档位限速；`capabilities.py:11-27` 定义全部 Cap 枚举；`policy.py:186-264` 逐能力探测调用真实 SDK 接口。

#### 2.1.2 免费插件数据源：stock-sdk（东方财富）

| 项目 | 详情 | 代码依据 |
|------|------|---------|
| **数据来源** | 东方财富（东财） | `bridge.mjs` 注释第77行："上游(东财)偶发冷启动/限流" |
| **调用方式** | Node.js 子进程 + `stock-sdk` npm 包 | `bridge.mjs:1-10`；`stocksdk/provider.py` |
| **是否免费** | **完全免费**，无需 Token | `stocksdk/provider.py` 注释；`plugin.yaml` |
| **支持数据** | 日K、除权因子、分钟K、全市场实时快照、标的维表 | `stocksdk/provider.py:24 _DATASETS` |
| **不支持** | 盘口、Tick、财务 | `stocksdk/provider.py:24` 注释 "financial 不支持" |

**stock-sdk 实际调用的 SDK 方法**（`bridge.mjs` 确认）：
- `sdk.kline.cn(sym, opts)` — 日K（`bridge.mjs:155`）
- `sdk.kline.cnMinute(sym, opts)` — 分钟K（`bridge.mjs:182`）
- `sdk.batch.cn({ concurrency })` — 全A股实时快照（`bridge.mjs:196`），同时用于提取标的维表元数据

### 2.2 数据类型支持判断

| 数据类型 | 是否支持 | 档位要求 | 代码依据 |
|---------|:--------:|---------|---------|
| **实时行情** | ✅ | free+(自选)/starter+(全市场) | `tickflow_provider.py:105-117`；`quote_service.py` |
| **历史日K** | ✅ | 全部档位（含none） | `tickflow_provider.py:48-75`；`tiers.yaml:29-30` |
| **分时数据** | ✅ | pro+ | `capabilities.py:21-22` INTRADAY/INTRADAY_BATCH；`policy.py:227-235` |
| **分钟K** | ✅ | pro+（TickFlow）/ 全档位（stock-sdk免费） | `tickflow_provider.py:96-103`（返回空，实际在kline_sync）；`stocksdk/provider.py:131-163` |
| **Tick逐笔成交** | **❌ 不支持** | — | 全局搜索"逐笔/tick_data/trade_detail/transaction"无行情Tick能力；`capabilities.py` 无Tick枚举 |
| **五档盘口** | ✅ | pro+ | `depth_service.py`；`capabilities.py:23-24` DEPTH5/DEPTH5_BATCH |
| **十档盘口** | ❌ 不支持 | — | 仅有 depth5，无 depth10 定义 |
| **Level2数据** | ❌ 不支持 | — | 无 Level2 相关能力定义 |
| **主力资金流** | ❌ 不支持 | — | 实时行情字段无主力资金净流入/流出；搜索无 money_flow 相关 |
| **财务数据** | ✅ | expert | `capabilities.py:26` FINANCIAL；`policy.py:247-251` 调用 `tf.financials.metrics()` |
| **WebSocket实时推送** | ✅ | expert | `capabilities.py:25` WEBSOCKET；`policy.py:258-264`（推断式启用） |

> **重要发现**：项目名称为 "tickflow-stock-panel"，但**实际不提供逐笔 Tick 成交数据**。"TickFlow" 是数据服务商的品牌名，而非 Tick 级数据。全局搜索确认无任何逐笔成交/trade_detail/transaction 相关的行情数据接口。

### 2.3 数据字段分析（从代码提取，非臆测）

#### 2.3.1 股票基础信息

**来源**：`normalizer.py:15` INSTRUMENT_COLS + `stocksdk/bridge.mjs:215-233` opInstruments

| 字段 | 类型 | 说明 | 代码依据 |
|------|------|------|---------|
| `symbol` | str | 股票代码（如 `600519.SH`） | `normalizer.py:15` |
| `name` | str | 股票名称 | `normalizer.py:15` |
| `code` | str | 纯数字代码（如 `600519`） | `normalizer.py:15` |
| `exchange` | str | 交易所（SH/SZ/BJ） | `normalizer.py:15` |
| `asset_type` | str | 资产类型（stock/index/etf） | `base.py:13` AssetType |
| `source` | str | 数据来源标记 | `normalizer.py:15` |
| `total_shares` | int | 总股本（stock-sdk ext） | `bridge.mjs:227` |
| `float_shares` | int | 流通股本（stock-sdk ext） | `bridge.mjs:228` |
| `limit_up` | float | 涨停价（stock-sdk ext） | `bridge.mjs:229` |
| `limit_down` | float | 跌停价（stock-sdk ext） | `bridge.mjs:230` |

**行业/概念字段**：项目**不直接提供**行业/概念分类。行业概念数据来自 `ext_presets.py` / `concept_rotation_analyzer.py`，通过第三方扩展数据或同花顺概念（`ths`）接口获取，非 TickFlow 核心字段。

#### 2.3.2 行情数据（实时快照）

**来源**：`quote_service.py` 记录解析 + `stocksdk/bridge.mjs:196-213` opRealtime + `tickflow_provider.py:105-117`

| 字段 | 类型 | 说明 | 代码依据 |
|------|------|------|---------|
| `symbol` | str | 股票代码 | `quote_service.py` 记录构建 |
| `name` | str | 股票名称 | 同上 |
| `last_price` | float | 最新价 | `tickflow_provider.py` q.get("last_price") |
| `prev_close` | float | 昨收 | 同上 |
| `open` | float | 开盘价 | 同上 |
| `high` | float | 最高价 | 同上 |
| `low` | float | 最低价 | 同上 |
| `volume` | int | 成交量 | 同上 |
| `amount` | float | 成交额 | 同上 |
| `change_pct` | float | 涨跌幅（小数制，0.0366=3.66%） | `quote_service.py` 注释："enriched 全项目约定小数" |
| `change_amount` | float | 涨跌额 | ext.get("change_amount") |
| `amplitude` | float | 振幅 | `quote_service.py` get_quotes_compat 保留列 |
| `turnover_rate` | float | 换手率 | 同上 |

**买卖盘口**：实时行情快照**不包含**五档买卖盘口。盘口数据由独立的 `depth_service.py` 通过 `tf.depth.batch()` 获取，仅包含**买卖盘量**（ask_volumes/bid_volumes 数组），**不包含买卖盘价**（因为涨跌停股盘口价格已知为涨跌停价）。

#### 2.3.3 K线数据

**来源**：`normalizer.py:13` DAILY_COLS + `stocksdk/provider.py:27 _MINUTE_CANONICAL`

| 字段 | 类型 | 说明 | 代码依据 |
|------|------|------|---------|
| `symbol` | str | 股票代码 | `normalizer.py:13` |
| `date` / `datetime` | date/datetime | 日期/时间 | 日K用date，分钟K用datetime |
| `open` | float | 开盘价 | `normalizer.py:13` |
| `high` | float | 最高价 | 同上 |
| `low` | float | 最低价 | 同上 |
| `close` | float | 收盘价 | 同上 |
| `volume` | float | 成交量 | 同上 |
| `amount` | float | 成交额 | 同上 |
| `quote_ts` | int | 毫秒级行情时间戳（用于量比折算） | `normalizer.py:13`；注释"用于盘后校验/量比折算" |

#### 2.3.4 五档盘口数据

**来源**：`depth_service.py` `_call_depth_batch` + `_fetch_and_seal_locked`

| 字段 | 类型 | 说明 | 代码依据 |
|------|------|------|---------|
| `ask_volumes` | list[int] | 卖一至卖五挂单量数组 | `depth_service.py` d.get("ask_volumes") |
| `bid_volumes` | list[int] | 买一至买五挂单量数组 | `depth_service.py` d.get("bid_volumes") |
| `timestamp` | int | 盘口时间戳（毫秒epoch） | `depth_service.py` d.get("timestamp") |
| `ask1_vol` | int | 卖一挂单量（派生） | `depth_service.py` ask_vols[0] |
| `bid1_vol` | int | 买一挂单量（派生） | `depth_service.py` bid_vols[0] |
| `sealed_up` | bool | 是否真涨停（卖一量==0） | `depth_service.py` "涨停价上卖一(主动卖压)为 0" |
| `sealed_down` | bool | 是否真跌停（买一量==0） | `depth_service.py` |

> **注意**：五档盘口**仅返回挂单量，不返回挂单价**。这是因为 `depth_service.py` 设计上只针对涨跌停股查询盘口，涨跌停价已知，因此只需判断封单量是否为0来判定真假涨停/跌停。通用五档盘口查询（`tf.depth.get()` 单只）可能返回价格，但项目中未使用该路径。

---

## 三、可复用模块分析

### 3.1 高价值可复用模块

#### 3.1.1 `plugins/stocksdk/` — 免费东方财富数据源插件 ⭐⭐⭐⭐⭐

**价值评级**：最高。完全免费，无需 API Key，直接调用东方财富数据。

| 文件 | 行数/大小 | 功能 | 可独立使用 |
|------|----------|------|-----------|
| `bridge.mjs` | ~250行 | Node.js 桥接脚本，调用 stock-sdk npm 包抓东财数据 | ✅ 可独立运行（stdin JSON → stdout JSON） |
| `provider.py` | ~250行 | Python 提供者实现，对齐 MarketDataProvider 协议 | ⚠️ 依赖 normalizer.py 和 tickflow.rate_limits |
| `bridge.py` | ~100行 | Python subprocess 调用 bridge.mjs 的封装 | ✅ 可独立 |
| `plugin.yaml` | ~30行 | 插件元数据配置 | ✅ |

**支持的数据集**（`stocksdk/provider.py:24`）：
- `daily` — 日K（`sdk.kline.cn`）
- `adj_factor` — 除权因子（通过 hfq/none 收盘价比值计算）
- `minute` — 分钟K（`sdk.kline.cnMinute`）
- `realtime` — 全A股实时快照（`sdk.batch.cn`）
- `instruments` — 全A股标的维表（从 batch.cn 提取元数据）

**与 QuantTrader DataManager 兼容性**：
- 数据格式为标准 OHLCV + 行情字段，可通过适配层转换为 DataManager 统一格式
- `bridge.mjs` 是无状态的 JSON 协议，可被任何 Python 程序通过 subprocess 调用
- 唯一依赖是 Node.js 环境 + `stock-sdk` npm 包

#### 3.1.2 `data_providers/base.py` — 数据提供者协议定义 ⭐⭐⭐⭐

**价值**：接口设计清晰，可作为 QuantTrader 统一数据接口的参考范式。

**核心协议**（`base.py:24-56`）：
```python
class MarketDataProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities  # instruments/daily/adj_factor/minute/realtime/financial
    def get_instruments(self, asset_type) -> pl.DataFrame
    def get_daily(self, symbols, start_time, end_time, asset_type) -> pl.DataFrame
    def get_adj_factors(self, symbols, start_time, end_time, asset_type) -> pl.DataFrame
    def get_minute(self, symbols, start_time, end_time, asset_type, freq) -> pl.DataFrame
    def get_realtime(self, universes, symbols) -> pl.DataFrame
```

**设计亮点**：
- 使用 `Protocol` 而非抽象基类，鸭子类型，低耦合
- `ProviderCapabilities` 数据类声明能力边界，运行时可探测
- 统一返回 Polars DataFrame，存储/指标/回测与数据源无关

#### 3.1.3 `services/depth_service.py` — 五档盘口真假涨停判定 ⭐⭐⭐⭐

**价值**：独立的五档盘口轮询服务，真假涨停/跌停判定逻辑可直接参考。

**架构特征**（`depth_service.py` 文档字符串）：
- **完全解耦**：只读 enriched 表拿涨跌停名单，不写回 enriched
- sealed 数据存独立 parquet（`data/depth5/date=xxx/part.parquet`）
- 盘中轮询线程（独立 sleep，不绑行情轮询）→ 内存缓存 → SSE 通知
- 盘后定版 job（默认 15:02）落盘
- 三层防护节流：套餐范围 clamp + 限速安全 clamp + 系统接管通知

**核心算法**：
- 真涨停（sealed_up）：涨停股的卖一挂单量 == 0（`depth_service.py` "涨停价上卖一(主动卖压)为 0"）
- 真跌停（sealed_down）：跌停股的买一挂单量 == 0
- 封单量：涨停=买一量（涨停价买单堆积），跌停=卖一量

#### 3.1.4 `services/quote_service.py` — 实时行情 SSE 推送架构 ⭐⭐⭐

**价值**：75KB 的完整实时行情服务，SSE 多客户端广播架构可参考。

**核心特征**：
- 后台线程轮询 TickFlow `get_by_universes(["CN_Equity_A", "CN_Index"])`
- 每轮 ~15s（按档位 1-60s 可调）：拉取行情 → 写 kline_daily → 增量计算 enriched → 写盘 + 更新缓存 → SSE 通知
- 每个 SSE 连接对应独立 `QuoteSubscriber`（独立事件+独立队列），避免多客户端告警被先醒来的连接消费
- 档位感知：none 档拒绝开启实时，free 档自选股实时（10rpm/5只），starter+ 全市场实时
- 交易时段感知：精确区分集合竞价/连续竞价/午休/收盘，仅连续竞价时段评估监控告警

#### 3.1.5 `tickflow/capabilities.py` + `policy.py` — 能力探测框架 ⭐⭐⭐

**价值**：运行时能力探测 + 档位判定 + 持久化缓存的完整框架，设计模式可参考。

**核心机制**：
- `Cap` 枚举定义所有能力（`capabilities.py:11-27`）
- `_probe_real()` 逐 capability 用最小代价请求试探（`policy.py:109-266`），用 600000.SH 浦发银行作为探测标的
- 分水岭判定档位（`policy.py:408-436`）：
  - 无单只日K → 无效Key（none）
  - 有日K无复权因子 → 免费Key（free）
  - 有复权因子 → 付费档（按 signature 判定 starter/pro/expert）
- 瞬时失败保护：网络抖动不降级，保留上次缓存档位

### 3.2 中等价值可参考模块

| 模块 | 文件 | 价值 | 说明 |
|------|------|------|------|
| 数据标准化 | `data_providers/normalizer.py` | ⭐⭐⭐ | 字段映射逻辑可复用（ts_code→symbol, vol→volume等），但强依赖Polars |
| 限速控制 | `tickflow/rate_limits.py` | ⭐⭐⭐ | chunked分批 + sleep_between_batches + apply_safety_rpm，API限速通用逻辑 |
| 指标流水线 | `indicators/pipeline.py`(82KB) | ⭐⭐ | MA/EMA/MACD/RSI/KDJ/布林/量比等，Polars实现，与QuantTrader现有指标重叠 |
| 选股策略 | `strategy/builtin/`(18个) | ⭐⭐ | 18个内置策略（金叉/突破/连板/回踩等），逻辑可参考但需重写为Backtrader框架 |
| 回测引擎 | `backtest/`(engine.py 139KB) | ⭐ | vectorbt向量化回测，与QuantTrader的Backtrader框架技术栈不同，仅架构参考 |

### 3.3 与 DataManager 兼容性评估

| 模块 | 直接接入 | 需适配层 | 不可用 | 原因 |
|------|:--------:|:--------:|:------:|------|
| stocksdk bridge.mjs | — | ✅ | — | JSON协议，subprocess调用，需写Python适配转换为DataManager格式 |
| stocksdk provider.py | — | ✅ | — | 依赖项目内 normalizer 和 rate_limits，需剥离依赖 |
| data_providers/base.py | — | ✅ | — | Protocol定义可参考，但返回Polars DataFrame，需转换为DataManager格式 |
| depth_service.py | — | ✅ | — | 依赖 tickflow SDK + 项目 repository，需重写盘口获取逻辑 |
| quote_service.py | — | ⚠️ | — | 75KB强耦合，SSE架构可参考但代码不可直接移植 |
| tickflow_provider.py | — | — | ❌ | 强依赖 tickflow SDK 包，需付费Key，且数据可被通达信/AKShare替代 |
| normalizer.py | — | ✅ | — | 字段映射逻辑可抽取，但Polars依赖需替换 |
| 回测/策略/指标 | — | — | ❌ | 技术栈（vectorbt/Polars）与QuantTrader（Backtrader/pandas）不兼容 |

---

## 四、与 QuantTrader 融合方案

### 4.1 融合架构设计

```
┌──────────────────────────────────────────────────────────────────┐
│                    QuantTrader 现有系统（不动）                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ 通达信    │ │ AKShare  │ │  聚宽     │ │ 现有缓存系统       │  │
│  │ (日K/分时)│ │(免费补充) │ │(数据补充) │ │(DuckDB/Parquet)   │  │
│  └─────┬────┘ └────┬─────┘ └────┬─────┘ └────────┬──────────┘  │
└────────┼─────────────┼─────────────┼────────────────┼────────────┘
         │             │             │                │
         ▼             ▼             ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│              【新增】统一数据接口适配层（Adapter Layer）            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  DataSourceRouter（数据源路由 + 优先级 + 冲突处理）          │  │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐ │  │
│  │  │ TickFlow适配器│  │ stock-sdk适配器   │  │ 通用HTTP适配器│ │  │
│  │  │ (付费:实时/   │  │ (免费:东财日K/   │  │ (自定义扩展)  │ │  │
│  │  │  五档/分钟K)  │  │  分钟K/实时快照) │  │              │ │  │
│  │  └──────┬───────┘  └────────┬─────────┘  └──────┬───────┘ │  │
│  └─────────┼─────────────────────┼─────────────────────┼────────┘  │
└────────────┼─────────────────────┼─────────────────────┼───────────┘
             │                     │                     │
             ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                   QuantTrader 数据中心（DataManager）               │
│         统一数据格式 → 缓存 → 策略引擎 → AI评分 → 实时监控          │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 数据源优先级与冲突处理

#### 4.2.1 数据优先级矩阵

| 数据类型 | 优先级1（最高） | 优先级2 | 优先级3 | 优先级4（最低） |
|---------|----------------|---------|---------|----------------|
| **日K** | 通达信（现有） | TickFlow | stock-sdk(东财) | AKShare |
| **分时** | 通达信（现有） | TickFlow(pro+) | stock-sdk(分钟K) | — |
| **实时行情** | TickFlow(starter+付费) | stock-sdk(东财免费) | 通达信 | AKShare |
| **分钟K** | TickFlow(pro+付费) | stock-sdk(东财免费) | 通达信 | — |
| **五档盘口** | TickFlow(pro+付费) | — | — | — |
| **财务数据** | 聚宽/AKShare（现有） | TickFlow(expert) | — | — |
| **标的维表** | 通达信（现有） | stock-sdk(东财免费) | TickFlow | — |

#### 4.2.2 冲突处理规则

1. **新鲜度优先**：实时行情场景下，选择 `quote_ts` 最新的数据源
2. **质量优先**：日K/历史数据场景下，优先通达信（稳定性验证过），TickFlow/stock-sdk 作为交叉校验
3. **字段补全**：当主数据源缺少某字段（如换手率），从次优先级数据源补全
4. **降级机制**：高优先级数据源失败/超时时，自动降级到下一级，记录日志
5. **缓存隔离**：新增数据源的数据写入独立缓存命名空间（如 `tickflow_` / `stocksdk_` 前缀），不污染现有缓存

### 4.3 分阶段融合路径

#### 阶段1：stock-sdk 免费数据源接入（推荐优先，零成本）

**目标**：接入东方财富免费数据，作为通达信/AKShare 的免费备选

**工作内容**：
1. 部署 Node.js 环境 + `npm install stock-sdk`
2. 编写 `StockSDKAdapter` 类，通过 subprocess 调用 `bridge.mjs`
3. 转换 JSON 输出为 QuantTrader DataManager 统一格式
4. 接入日K、分钟K、实时快照、标的列表四个数据集
5. 写入独立缓存，设置为优先级3（日K）/优先级2（实时行情）

**预期收益**：
- 免费获取全A股实时快照（stock-sdk `batch.cn`）
- 免费获取分钟K数据（stock-sdk `kline.cnMinute`）
- 作为通达信数据的免费交叉校验源

#### 阶段2：五档盘口能力接入（需 TickFlow Pro 账号）

**目标**：接入五档盘口，增强真假涨停判定和封单监控

**工作内容**：
1. 注册 TickFlow 账号并升级 Pro 档位
2. 参考 `depth_service.py` 编写 `DepthAdapter`
3. 实现涨跌停股筛选 → 批量五档查询 → 真假涨停判定 → 封单量统计
4. 接入实时监控中心，新增"真假涨停预警"规则
5. 数据写入独立缓存 `depth5_` 命名空间

**预期收益**：
- 真假涨停/跌停判定（卖一量/买一量是否为0）
- 封单量监控（涨停封单/跌停封单）
- 连板梯队封单强度分析

#### 阶段3：实时行情增强（需 TickFlow Starter+ 账号）

**目标**：增强实时监控中心的全市场实时行情能力

**工作内容**：
1. 参考 `quote_service.py` 的 SSE 推送架构
2. 实现全市场实时行情轮询（TickFlow `get_by_universes`）
3. 增量计算技术指标（enriched 表思路）
4. 接入 AI 实时监控中心，提升行情刷新频率和覆盖范围

**预期收益**：
- 全市场实时行情（非仅自选股）
- 更高频的行情刷新（Starter 60rpm/50只，Pro 120rpm/100只）
- 标的池模式（universe）批量获取

### 4.4 不替换原则确认

| 现有组件 | 是否替换 | 说明 |
|---------|:--------:|------|
| 通达信行情数据 | ❌ 不替换 | 作为日K/分时最高优先级数据源 |
| AKShare | ❌ 不替换 | 保留作为免费补充数据源 |
| 聚宽 | ❌ 不替换 | 保留财务/基本面数据来源 |
| 现有缓存系统 | ❌ 不替换 | 新增数据写入独立命名空间，不修改现有缓存结构 |
| DataManager 数据中心 | ❌ 不替换 | 仅通过适配层新增数据源入口，不修改核心架构 |
| 策略引擎（九重选股/缠论） | ❌ 不替换 | 新增数据仅作为输入增强，不修改策略逻辑 |
| AI评分系统 | ❌ 不替换 | 新增数据字段可作为评分输入因子，但不修改评分架构 |
| K线回测训练系统 | ❌ 不替换 | Backtrader 框架不变，新增数据可作为回测数据源选项 |

---

## 五、重点判断

### 5.1 这个项目是否有真实行情数据能力？

**是，但分档位且有明确边界。**

| 维度 | 判断 | 说明 |
|------|------|------|
| **真实A股行情** | ✅ 是 | TickFlow 官方 SDK + stock-sdk 东方财富，均为真实行情数据 |
| **实时行情** | ✅ 是 | free档(自选股10rpm/5只) / starter+(全市场) / stock-sdk(全市场免费) |
| **历史日K** | ✅ 是 | 全部档位支持，含 none（无Key） |
| **分时数据** | ✅ 是 | pro+ 档位（TickFlow intraday） |
| **分钟K** | ✅ 是 | pro+（TickFlow）/ 全档位（stock-sdk 免费） |
| **五档盘口** | ✅ 是 | pro+ 档位，仅挂单量（无挂单价，因设计上只查涨跌停股） |
| **Tick逐笔成交** | **❌ 否** | 项目名称误导，实际无逐笔数据能力 |
| **十档盘口/Level2** | ❌ 否 | 仅五档，无Level2 |
| **主力资金流** | ❌ 否 | 无主力净流入/流出字段 |

**代码依据**：
- `capabilities.py:11-27` 定义全部14种能力，无 Tick/逐笔相关枚举
- `tiers.yaml:27-73` 五档能力对照表，无 Tick 数据
- 全局搜索"逐笔/tick_data/trade_detail/transaction"仅命中回测引擎中的"每笔交易"（指回测交易，非行情Tick）

### 5.2 是否值得融合？

**部分值得，需选择性融合。**

| 方面 | 是否值得 | 理由 |
|------|:--------:|------|
| **stock-sdk 免费插件** | ✅ 值得 | 完全免费，东方财富数据，支持日K/分钟K/全市场实时快照，零成本接入 |
| **五档盘口能力** | ✅ 有条件值得 | 需 TickFlow Pro 付费账号，但真假涨停判定逻辑有实际价值 |
| **实时行情架构** | ⚠️ 参考价值 | SSE 推送 + 多客户端广播 + 档位感知架构可参考，但通达信已有实时能力 |
| **数据提供者协议** | ⚠️ 参考价值 | Protocol 设计模式可参考，但 QuantTrader 已有 DataManager 架构 |
| **TickFlow 付费数据** | ❌ 不值得直接接入 | 付费 API，核心数据（日K/实时）通达信已覆盖，性价比低 |
| **回测/策略/指标** | ❌ 不值得 | 技术栈（vectorbt/Polars）与 QuantTrader（Backtrader/pandas）不兼容，且功能重叠 |
| **前端UI** | ❌ 不值得 | React 技术栈与 QuantTrader（PyQt/PySide）不同，仅视觉参考 |

### 5.3 最大价值是什么？

**第一名：stock-sdk 免费东方财富数据源插件**（`backend/app/plugins/stocksdk/`）

- 完全免费，无需 API Key，无调用限制（stock-sdk 包本身）
- 支持日K、分钟K、全市场实时快照、标的维表
- 通过 Node.js subprocess 调用，与 Python 解耦，可独立部署
- `bridge.mjs` 是无状态 JSON 协议，极易适配到任何系统

**第二名：五档盘口真假涨停判定逻辑**（`backend/app/services/depth_service.py`）

- 独立的五档盘口轮询 + 真假涨停/跌停判定 + 封单量统计
- 三层防护节流设计（套餐范围 + 限速安全 + 系统接管通知）
- 可直接参考算法逻辑，接入 QuantTrader 实时监控中心

**第三名：实时行情 SSE 多客户端广播架构**（`backend/app/services/quote_service.py`）

- 每连接独立订阅者（独立事件+独立队列），解决多客户端告警竞争问题
- 精确的交易时段感知（集合竞价/连续竞价/午休/收盘区分）
- 档位感知的实时行情权限控制

### 5.4 是否可以增强现有能力？

| 能力 | 判断 | 说明 | 代码依据 |
|------|:----:|------|---------|
| **主力资金分析** | **部分** | 实时行情有成交额/成交量/换手率，但**无主力资金净流入/流出字段**，无大单/中单/小单拆分。可通过量价数据间接推算主力行为，但非直接数据 | `quote_service.py` 行情字段无 money_flow；全局搜索无主力资金相关接口 |
| **盘口分析** | **是** | 五档盘口（pro+），支持买卖盘量查询，可判定真假涨停/跌停、封单量、封单强度。但仅返回挂单量，不返回挂单价（设计上只查涨跌停股） | `depth_service.py` 完整实现；`capabilities.py:23-24` DEPTH5 |
| **实时监控** | **是** | 全市场实时行情轮询（starter+）+ SSE 推送 + 四类监控规则（策略/个股信号/价格/异动）+ 语音播报 + 飞书推送。stock-sdk 可免费提供全市场实时快照 | `quote_service.py`(75KB)；`monitor_rules.py`(27KB)；`stocksdk/provider.py` realtime |
| **买点判断** | **部分** | 有分钟K（pro+/stock-sdk免费）、分时（pro+）、技术指标流水线（MA/EMA/MACD/RSI/KDJ/布林/量比等82KB），可增强分时级买点判断。但**无 Tick 级数据**，无法做逐笔成交级精确买点 | `indicators/pipeline.py`(82KB)；`kline_sync.py` 分钟K同步；无Tick能力 |

---

## 六、最终评级

### 评级：**B 级（需改造）**

#### 评级理由

**支持 B 级的因素（有实际价值，但需改造）：**

1. **stock-sdk 免费插件有真实价值**：东方财富免费数据源，支持日K/分钟K/全市场实时快照，零成本可接入，是本项目最大的可复用资产。

2. **五档盘口能力可增强现有系统**：`depth_service.py` 的真假涨停判定 + 封单量监控逻辑，可直接参考接入实时监控中心，需 TickFlow Pro 付费账号。

3. **数据提供者架构设计良好**：`base.py` 的 Protocol 模式 + `capabilities.py` 能力探测框架，设计模式可作为 QuantTrader 统一数据接口的参考。

4. **实时行情 SSE 架构可参考**：`quote_service.py` 的多客户端广播 + 交易时段感知 + 档位权限控制，架构设计成熟。

**限制 B 级（不能到 A 级）的因素：**

1. **核心数据依赖付费 API**：TickFlow 主数据源的实时行情（starter+）、分钟K/分时/五档盘口（pro+）、WebSocket/财务（expert）均需付费。免费档位（none/free）仅历史日K + 自选股实时（10rpm/5只），能力非常有限。

2. **不支持逐笔 Tick 数据**：项目名称 "tickflow" 有误导性，实际无 Tick/逐笔成交/Level2 数据能力，无法满足"开盘30分钟资金模型"等需要 Tick 级数据的场景。

3. **技术栈不一致**：后端使用 Polars + DuckDB + vectorbt，与 QuantTrader 现有技术栈（pandas + Backtrader + 通达信）不兼容，代码无法直接复用，需重写适配层。

4. **强依赖 tickflow SDK 包**：`tickflow_provider.py` 等核心模块强依赖 `tickflow` Python 包，无法脱离 TickFlow 服务独立运行。

5. **五档盘口仅返回挂单量**：`depth_service.py` 设计上只针对涨跌停股查询盘口，返回 ask_volumes/bid_volumes 数组但不返回挂单价，通用盘口分析能力受限。

**排除 C 级的因素（不止 UI 参考价值）：**

- stock-sdk 免费插件提供真实可用的东方财富数据，非 UI 空壳
- 五档盘口、实时行情、数据提供者协议均有实际代码逻辑和数据能力
- 项目有 3405 Star，社区活跃，代码质量较高（有完整测试、类型注解、文档）

#### 融合建议总结

| 融合项 | 优先级 | 成本 | 预期收益 |
|--------|:------:|------|---------|
| stock-sdk 免费数据源接入 | **P0 最高** | 低（Node.js环境+适配层） | 免费全市场实时快照+分钟K+日K |
| 五档盘口真假涨停判定 | P1 | 中（需TickFlow Pro账号+适配） | 真假涨停/跌停预警+封单监控 |
| 实时行情SSE架构参考 | P2 | 中（架构参考+部分重写） | 增强AI实时监控中心推送能力 |
| 数据提供者Protocol参考 | P3 | 低（设计参考） | 优化DataManager统一接口设计 |
| TickFlow付费数据直接接入 | **不推荐** | 高（付费+强依赖） | 核心数据通达信已覆盖，性价比低 |
| 回测/策略/指标代码复用 | **不推荐** | 极高（技术栈不兼容） | 功能重叠，需完全重写 |
| 前端UI复用 | **不推荐** | 高（React vs PyQt） | 仅视觉参考，无代码复用价值 |

---

## 附录：关键代码索引

| 结论 | 文件 | 行号 |
|------|------|------|
| TickFlow 免费/付费端点 | `backend/app/tickflow/client.py` | 33-35 |
| 五档能力定义 | `backend/app/tickflow/capabilities.py` | 23-24 |
| 无Tick能力确认 | `backend/app/tickflow/capabilities.py` | 11-27（全部枚举，无Tick） |
| 五档档位限速 | `tiers.yaml` | 55-56(pro), 69-70(expert) |
| 免费档仅历史日K | `tiers.yaml` | 27-36(none/free) |
| stock-sdk 数据源为东财 | `backend/app/plugins/stocksdk/bridge.mjs` | 77（注释） |
| stock-sdk 支持数据集 | `backend/app/plugins/stocksdk/provider.py` | 24 |
| stock-sdk 实时全市场快照 | `backend/app/plugins/stocksdk/bridge.mjs` | 196-213 |
| 五档盘口真假涨停算法 | `backend/app/services/depth_service.py` | _fetch_and_seal_locked 方法 |
| 实时行情字段 | `backend/app/services/quote_service.py` | 记录构建处（last_price/prev_close/volume/amount等） |
| 日K标准字段 | `backend/app/data_providers/normalizer.py` | 13（DAILY_COLS） |
| 数据提供者协议 | `backend/app/data_providers/base.py` | 24-56（MarketDataProvider Protocol） |
| 能力探测分水岭算法 | `backend/app/tickflow/policy.py` | 408-436（_classify_tier） |

---

> **审计结论**：tickflow-stock-panel 是一个架构设计良好、有真实数据能力的量化工作台项目，但核心数据依赖付费 TickFlow API，且不支持逐笔 Tick 数据。**最大价值在于 stock-sdk 免费东方财富数据源插件**，建议优先接入作为免费数据备选。五档盘口能力可在有 TickFlow Pro 账号时选择性融合。整体评级 **B 级（需改造）**，不建议直接复用代码，应通过适配层选择性融合。
