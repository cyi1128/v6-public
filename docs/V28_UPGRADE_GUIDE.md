# 量化交易作战中台 V2.7 → V2.8 全量升级文档

> 版本：V2.8.0 | 升级日期：2026-09-07 | 架构原则：只新增、不破坏

---

## 一、升级代码包结构

```
D:\QuantMonitorV6\
├── v28/                              # 【新增】V2.8全量升级独立模块包
│   ├── __init__.py                   # 包入口，安全导入+模块可用性标记
│   ├── config.py                     # 统一配置管理（所有开关/参数/阈值）
│   ├── integration.py                # 统一接入接口（原有系统唯一依赖点）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── market_risk.py            # 模块1：大盘系统性风控计算引擎
│   │   ├── stock_radar.py            # 模块2：个股自动排雷三维检测引擎
│   │   ├── signal_lifecycle.py       # 模块3：AI520信号全生命周期跟踪引擎
│   │   ├── news_sentiment.py         # 模块6：新闻情绪分析引擎
│   │   ├── sector_radar.py           # 模块7：板块轮动图谱引擎
│   │   ├── trade_plan.py             # 模块8：交易计划管理引擎
│   │   ├── custom_alert.py           # 模块9：自定义异动提醒引擎
│   │   ├── health_monitor.py         # 模块10：运行状态监控引擎
│   │   ├── push_review.py            # 模块11：推送效果复盘引擎
│   │   └── strategy_params.py        # 模块12：策略参数自定义引擎
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── market_risk_panel.py      # 模块1：大盘风控面板UI组件
│   │   ├── signal_tracking_panel.py  # 模块3：信号跟踪列表UI组件
│   │   ├── stock_link_panel.py       # 模块4：选股列表联动面板UI
│   │   └── quant_diagnosis.py        # 模块5：量化诊断侧边栏UI
│   └── services/
│       └── __init__.py
├── config/
│   └── v28_config.json               # 【新增】V2.8配置文件（所有模块默认关闭）
├── data/
│   └── v28_cache.duckdb              # 【新增】V2.8专用数据库（运行时自动创建）
└── docs/
    └── V28_UPGRADE_GUIDE.md          # 本文档
```

### 模块与文件对应表

| 优先级 | 模块 | 核心文件 | UI文件 | 状态 |
|--------|------|----------|--------|------|
| P0 | 模块1：大盘系统性风控 | core/market_risk.py | ui/market_risk_panel.py | ✅ 完整实现 |
| P0 | 模块2：个股自动排雷 | core/stock_radar.py | — | ✅ 完整实现 |
| P0 | 模块3：信号生命周期跟踪 | core/signal_lifecycle.py | ui/signal_tracking_panel.py | ✅ 完整实现 |
| P1 | 模块4：选股列表联动 | — | ui/stock_link_panel.py | ✅ 完整实现 |
| P1 | 模块5：量化诊断侧边栏 | — | ui/quant_diagnosis.py | ✅ 完整实现 |
| P1 | 模块6：新闻情绪标注 | core/news_sentiment.py | — | ✅ 完整实现 |
| P1 | 模块7：板块轮动图谱 | core/sector_radar.py | — | ✅ 引擎实现 |
| P1 | 模块8：交易计划管理 | core/trade_plan.py | — | ✅ 引擎实现 |
| P2 | 模块9：自定义异动提醒 | core/custom_alert.py | — | ✅ 引擎实现 |
| P2 | 模块10：运行状态监控 | core/health_monitor.py | — | ✅ 引擎实现 |
| P2 | 模块11：推送效果复盘 | core/push_review.py | — | ✅ 引擎实现 |
| P2 | 模块12：策略参数自定义 | core/strategy_params.py | — | ✅ 引擎实现 |

---

## 二、各模块接入位置与修改点说明

### 核心原则
所有V2.8功能通过 `v28/integration.py` 统一接入，原有代码仅需添加**可选调用**，不修改任何原有业务逻辑。配置关闭时，所有接入函数返回空值/None，对原有系统零影响。

---

### 模块1：大盘系统性风控面板

**接入位置**：`ui/battle_console_v2.py` → `BattleConsoleHomeV2._build_ui()`

**修改点**（在市场态势面板 `self.market_panel` 之后添加）：

```python
# === V2.8 新增：大盘系统性风控面板 ===
try:
    from v28.integration import get_market_risk_panel
    self.risk_panel = get_market_risk_panel()
    if self.risk_panel:
        main.addWidget(self.risk_panel)
except Exception as e:
    print(f"[V2.8] 风控面板加载失败: {e}", flush=True)
```

**边界说明**：
- 新增代码独立，用 try/except 包裹，失败不影响原有面板
- 配置 `market_risk.enabled = false` 时 `get_market_risk_panel()` 返回 None
- 不修改原有 `market_panel` 的任何代码

**选股过滤接入**（可选）：`strategy/ai_520_scan_service.py` 扫描结果过滤处：
```python
from v28.integration import should_filter_by_market_risk
if should_filter_by_market_risk(stock['grade']):
    continue  # 高风险期过滤低等级信号
```

---

### 模块2：个股自动排雷体系

**接入位置1**：`ui/battle_console_v2.py` → 选股列表 `StockCard` 渲染处

```python
# === V2.8 新增：排雷标签 ===
try:
    from v28.integration import get_radar_display_tag
    radar_tag = get_radar_display_tag(stock_code, stock_info)
    if radar_tag:
        radar_label = QLabel(radar_tag)
        radar_label.setToolTip(radar_tooltip)
        layout.addWidget(radar_label)
except Exception:
    pass
```

**接入位置2**：`ui/stock_detail_v1.py` → 个股分析页加载时

```python
from v28.integration import scan_stock_radar
radar_result = scan_stock_radar(code, stock_info)
# 在页面中展示排雷详情区域
```

**接入位置3**：`services/wechat_push.py` → 推送内容构建时

```python
from v28.integration import scan_stock_radar
radar = scan_stock_radar(code)
if radar['has_risk']:
    content += f"\n⚠️ 排雷: {radar['tooltip_text']}"
```

**选股结果自动排除**（可选）：扫描结果过滤处：
```python
from v28.integration import should_exclude_by_radar
if should_exclude_by_radar(code):
    continue
```

**边界说明**：排雷计算在后台线程预计算（每日08:30），UI调用仅读取缓存，不阻塞。AkShare公告接口调用包裹10秒超时，失败静默降级。

---

### 模块3：AI520信号全生命周期跟踪

**接入位置1**：`services/wechat_push.py` → 推送成功后

```python
# === V2.8 新增：信号加入跟踪列表 ===
try:
    from v28.integration import add_signal_to_tracking
    add_signal_to_tracking(code, name, {
        'score': score, 'grade': grade, 'price': price,
        'buy_point': buy_point, 'stop_loss': stop_loss,
        'target_price': target, 'industry': industry,
        'push_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })
except Exception:
    pass
```

**接入位置2**：`ui/battle_console_v2.py` → 选股列表下方添加跟踪面板

```python
try:
    from v28.integration import get_signal_tracking_panel
    self.signal_tracking = get_signal_tracking_panel()
    if self.signal_tracking:
        main.addWidget(self.signal_tracking)
except Exception:
    pass
```

**接入位置3**：`ui/stock_detail_v1.py` → 个股分析页新增历史信号统计区域

```python
from v28.integration import get_stock_history_stats
stats = get_stock_history_stats(code)
# 展示：近2年触发次数、持股5日胜率、平均收益、最大回撤
```

**价格提醒定时检查**：在现有行情刷新定时器中添加：
```python
from v28.core.signal_lifecycle import get_signal_lifecycle_engine
engine = get_signal_lifecycle_engine()
for signal in engine.get_all_signals():
    alerts = engine.check_price_alerts(signal, current_price)
    for alert in alerts:
        engine.trigger_wechat_alert(alert)
```

**边界说明**：信号跟踪使用独立数据库 `v28_cache.duckdb`，不影响原有 `ai520_cache.duckdb`。状态流转和评分更新均在后台线程执行。

---

### 模块4：选股列表与个股分析无缝联动

**接入位置**：`ui/battle_console_v2.py` → `BattleConsoleHomeV2._build_ui()`

将选股列表区域改为 `QSplitter`，左侧列表 + 右侧联动面板：
```python
try:
    from v28.integration import get_stock_link_panel
    self.link_panel = get_stock_link_panel()
    if self.link_panel:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.link_panel)
        splitter.setSizes([800, 380])
        main.addWidget(splitter, 1)
        # 列表点击时更新联动面板
        # stock_card.clicked.connect(lambda code: self.link_panel.update_stock(get_stock_data(code)))
except Exception:
    main.addWidget(left, 1)  # 降级：原有布局
```

---

### 模块5：个股分析页量化诊断侧边栏

**接入位置**：`ui/stock_detail_v1.py` → `StockDetailPage` K线图右侧

```python
try:
    from v28.integration import get_quant_diagnosis_sidebar
    self.diagnosis_sidebar = get_quant_diagnosis_sidebar()
    if self.diagnosis_sidebar:
        # 将K线区域和侧边栏放入QHBoxLayout
        kline_layout.addWidget(self.kline_widget, 1)
        kline_layout.addWidget(self.diagnosis_sidebar)
        # 加载个股时更新诊断数据
        # self.diagnosis_sidebar.update_diagnosis(diagnosis_data)
except Exception:
    pass  # 降级：K线占满页面
```

---

### 模块6：新闻模块决策化升级

**接入位置**：`news_center/` 新闻渲染处 + `ui/battle_console_v2.py` 新闻Tab

```python
# 新闻情绪标注
from v28.integration import analyze_news_sentiment
sentiment = analyze_news_sentiment(title, content)
# 在新闻卡片上显示 利好(红)/利空(绿)/中性(灰) 标签 + 强度

# 自选新闻Tab
from v28.integration import get_watchlist_news
watchlist_news = get_watchlist_news(watchlist_codes)
```

---

### 模块7：板块轮动图谱

**接入位置**：`ui/battle_console_v2.py` → 新增「板块雷达」子页面/Tab

```python
from v28.integration import get_sector_radar_panel
# 或直接使用引擎
from v28.core.sector_radar import get_sector_radar_engine
engine = get_sector_radar_engine()
sectors = engine.get_sector_ranking(ai520_results)
```

---

### 模块8：交易计划管理

**接入位置**：`ui/watchlist_panel.py` → 自选评分页新增「交易计划」子列表

```python
from v28.integration import create_trade_plan_from_ai520, get_trade_plan_panel
# AI入选股票一键生成
plan = create_trade_plan_from_ai520(code, name, signal_data)
```

---

### 模块9：自定义异动提醒

**接入位置**：主窗口顶部工具栏新增「异动提醒」按钮

```python
from v28.integration import get_custom_alert_config_dialog
dialog = get_custom_alert_config_dialog()
if dialog:
    dialog.exec()
```

---

### 模块10：运行状态监控面板

**接入位置**：设置菜单 / 顶部标题栏右键菜单新增「运行状态」入口

```python
from v28.integration import get_health_monitor_panel
panel = get_health_monitor_panel()
```

---

### 模块11：推送效果复盘

**接入位置**：新增「策略复盘」页面/Tab

```python
from v28.integration import get_push_review_panel
panel = get_push_review_panel()
```

---

### 模块12：策略参数自定义

**接入位置**：设置菜单 → 新增「AI-520参数设置」

```python
from v28.integration import get_strategy_params_dialog, get_active_strategy_params
dialog = get_strategy_params_dialog()
params = get_active_strategy_params()  # 回测验证后生效的参数
```

---

## 三、配置文件说明

配置文件路径：`config/v28_config.json` + `v28/config.py`（Python默认值）

所有模块**默认关闭**，通过修改 `enabled: true` 逐步开启验证。

### 3.1 模块1：大盘系统性风控 (market_risk)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| enabled | false | 总开关 |
| refresh_interval_sec | 30 | 面板刷新间隔（秒） |
| sentiment.big_gain_ratio | 3.0 | 大赚：涨跌家数比 > 3.0 |
| sentiment.small_gain_ratio | 1.5 | 小赚：涨跌比 1.5~3.0 |
| sentiment.balance_ratio | 0.7 | 平衡：涨跌比 0.7~1.5 |
| sentiment.small_loss_ratio | 0.3 | 小亏：涨跌比 0.3~0.7 |
| systemic_risk.below_ma20_high | 0.70 | 高风险：>70%个股跌破MA20 |
| systemic_risk.below_ma20_mid | 0.50 | 中风险：50%~70%跌破MA20 |
| systemic_risk.volume_shrink_high | 0.40 | 高风险：成交量萎缩>40% |
| systemic_risk.volume_shrink_mid | 0.20 | 中风险：萎缩20%~40% |
| position_suggestion.low | 8成 | 低风险仓位建议 |
| position_suggestion.medium | 6成 | 中风险仓位建议 |
| position_suggestion.high | 2成 | 高风险仓位建议 |
| position_suggestion.extreme | 空仓 | 极端风险仓位建议 |
| high_risk_auto.highlight_panel | true | 高风险面板红色高亮 |
| high_risk_auto.reduce_stock_position | true | 自动下调个股建议仓位 |
| high_risk_auto.reduce_ratio | 0.5 | 仓位下调比例（×0.5） |
| high_risk_auto.filter_low_grade_signal | false | 高风险期自动过滤低等级信号 |
| high_risk_auto.filter_min_grade | A | 过滤阈值：低于A级过滤 |

### 3.2 模块2：个股自动排雷 (stock_radar)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| enabled | false | 总开关 |
| precompute_time | 08:30 | 每日预计算时间 |
| financial_risk.goodwill_ratio_threshold | 0.30 | 商誉占比>30%触发 |
| financial_risk.pledge_ratio_threshold | 0.50 | 股权质押率>50%触发 |
| financial_risk.consecutive_loss_years | 2 | 连续亏损年数>=2触发 |
| financial_risk.negative_cash_flow | true | 现金流为负触发 |
| event_risk.unlock_days_ahead | 15 | 未来N天限售解禁触发 |
| event_risk.check_reduction_plan | true | 检测大股东减持计划 |
| event_risk.check_regulatory_inquiry | true | 检测监管问询 |
| event_risk.check_investigation | true | 检测立案调查 |
| liquidity_risk.min_avg_amount | 50000000 | 日均成交额<5000万触发 |
| liquidity_risk.min_turnover_rate | 0.01 | 换手率<1%触发 |
| liquidity_risk.check_manipulated_stock | true | 检测庄股特征 |
| display.show_single_risk_warning | true | 单风险显示黄色⚠️ |
| display.show_multi_risk_red | true | 多风险显示红色🚫 |
| display.auto_exclude_high_risk | false | 高风险自动排除选股结果 |
| display.high_risk_threshold | 2 | 风险项数>=此值为高风险 |

### 3.3 模块3：信号生命周期跟踪 (signal_lifecycle)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| enabled | false | 总开关 |
| refresh_interval_sec | 60 | 跟踪列表刷新间隔 |
| score_tracking.min_score_for_removal | 60 | 评分跌破此值发出移出提醒 |
| score_tracking.show_score_trend | true | 标注评分上升/下降 |
| price_alert.alert_on_buy_point | true | 到达买点提醒 |
| price_alert.alert_on_stop_loss | true | 到达止损位提醒 |
| price_alert.alert_on_target | true | 到达目标位提醒 |
| price_alert.wechat_push | true | 企业微信推送提醒 |
| history_stats.lookback_years | 2 | 近N年历史统计 |
| history_stats.holding_days | 5 | 持股N日胜率统计 |

### 3.4 模块4-12 关键配置

| 模块 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| 模块4 stock_link_panel | enabled | false | 总开关 |
| 模块4 | panel_width | 380 | 联动面板宽度 |
| 模块5 quant_diagnosis | enabled | false | 总开关 |
| 模块5 | sidebar_width | 320 | 侧边栏宽度 |
| 模块6 news_sentiment | enabled | false | 总开关 |
| 模块7 sector_radar | enabled | false | 总开关 |
| 模块8 trade_plan | enabled | false | 总开关 |
| 模块9 custom_alert | enabled | false | 总开关 |
| 模块9 | check_interval_sec | 10 | 异动检查间隔 |
| 模块10 health_monitor | enabled | false | 总开关 |
| 模块10 | log_retention_days | 30 | 日志保留天数 |
| 模块11 push_review | enabled | false | 总开关 |
| 模块12 strategy_params | enabled | false | 总开关 |
| 模块12 | require_backtest_verify | true | 回测验证后生效 |
| 模块12 | max_profiles | 10 | 最多参数方案数 |

### 配置热加载
```python
from v28.config import reload_config
reload_config()  # 修改JSON后调用，无需重启程序
```

---

## 四、分阶段验证方案

### 第一阶段：P0 核心模块验证（模块1-3）

#### 模块1：大盘系统性风控面板

**测试方法**：
1. **单元测试**：`python -m pytest v28/tests/test_market_risk.py`
   - 市场情绪定级：构造大赚/小赚/平衡/小亏/大亏五种场景，验证定级正确
   - 系统性风险：构造跌破MA20占比/成交量萎缩不同组合，验证风险评级
   - 仓位建议：验证低/中/高风险对应8成/6成/2成
   - 高风险行为：验证仓位下调比例、信号过滤逻辑
   - 异常降级：传入空数据/不存在的DB路径，验证返回安全默认值不崩溃

2. **UI测试**：
   - 配置 `market_risk.enabled = true`，启动程序
   - 验证作战中台顶部出现风控面板，与市场温度/指数/涨停生态并列
   - 验证面板每30秒自动刷新
   - 构造高风险数据，验证面板边框变红高亮
   - 配置 `enabled = false`，验证面板不出现，程序正常运行

3. **性能测试**：
   - 模块启动耗时 < 100ms
   - 单次风控计算 < 500ms（全市场MA20统计）
   - UI刷新不卡顿（后台线程计算）

**验收标准**：
- ✅ 五种情绪定级正确
- ✅ 三级风险评级正确
- ✅ 仓位建议映射正确
- ✅ 高风险面板红色高亮
- ✅ 配置关闭时零影响
- ✅ 异常数据不崩溃

#### 模块2：个股自动排雷体系

**测试方法**：
1. **单元测试**：
   - 财务雷：构造商誉>30%/质押>50%/连续亏损/现金流负的股票数据，验证各检测项触发
   - 事件雷：Mock AkShare返回解禁/减持/问询/调查数据，验证触发
   - 流动性雷：构造日均成交<5000万/换手<1%/庄股特征的K线数据，验证触发
   - 综合排雷：验证无风险/单风险/多风险三种场景的warning_tag和risk_level
   - 缓存读写：验证DuckDB缓存表创建、写入、读取正常
   - 批量扫描：验证100只股票批量扫描<10秒，后台线程不阻塞

2. **集成测试**：
   - 选股列表中验证排雷标签显示（无风险不显示/单风险⚠️/多风险🚫）
   - hover验证风险详情tooltip
   - 企业微信推送验证排雷标签附加
   - 配置 `auto_exclude_high_risk = true`，验证高风险股票不进入选股结果

3. **AkShare降级测试**：
   - 断网/ AkShare接口异常时，验证事件雷返回空列表，其他检测正常
   - 预计算失败时，验证使用缓存或空结果，不崩溃

**验收标准**：
- ✅ 三维排雷各检测项正确触发
- ✅ 无风险时warning_tag为空
- ✅ 单风险显示⚠️，多风险显示🚫
- ✅ DuckDB缓存正常读写
- ✅ 批量扫描后台线程执行
- ✅ AkShare失败自动降级

#### 模块3：AI520信号全生命周期跟踪

**测试方法**：
1. **单元测试**：
   - 信号入选：add_signal验证信号入库，初始状态=待买入
   - 状态流转：验证待买入→持仓中（到达买点）、持仓中→已止盈（到达目标）、持仓中→已止损（跌破止损）
   - 评分更新：验证评分上升/下降趋势标注，跌破60分自动移出
   - 价格提醒：验证买点/止损/目标位三种提醒触发和消息内容
   - 历史统计：验证从push_records表聚合计算触发次数/胜率/收益/回撤
   - 数据库：验证三张表（signal_tracking/signal_score_history/signal_status_log）创建和读写

2. **集成测试**：
   - 企业微信推送后验证信号自动进入跟踪列表
   - 作战中台验证「信号跟踪」子列表显示
   - 个股分析页验证「历史信号统计」区域显示
   - 价格到达关键价位时验证企业微信提醒推送
   - 评分每日更新验证趋势箭头

3. **UI测试**：
   - 状态标签颜色验证（待买入=蓝/持仓中=绿/已止盈=橙/已止损=红/已移出=灰）
   - 状态筛选下拉框验证
   - 点击个股发出stock_clicked信号验证

**验收标准**：
- ✅ 信号入选后自动跟踪
- ✅ 五种状态流转逻辑正确
- ✅ 评分趋势标注正确
- ✅ 跌破60分自动移出提醒
- ✅ 价格提醒企业微信推送
- ✅ 历史统计数据正确
- ✅ UI面板显示正常

---

### 第二阶段：P1 决策深度+交易辅助验证（模块4-8）

**测试方法**：
1. 模块4：点击选股列表个股，验证右侧联动面板展开，显示价格/评分/买卖点/排雷/指标
2. 模块5：个股分析页验证量化诊断侧边栏，筹码/资金/行业/风格四区显示
3. 模块6：新闻列表验证情绪标签（利好红/利空绿/中性灰），自选新闻Tab验证
4. 模块7：板块雷达页面验证涨幅排行/资金流入/AI520信号数，点击板块查看个股
5. 模块8：自选评分页验证交易计划列表，AI入选一键生成计划，价格提醒

**验收标准**：
- 每个模块UI可正常显示，数据填充正确
- 配置关闭时不影响原有页面
- 所有计算后台线程，UI不卡顿

---

### 第三阶段：P2 运维与策略迭代验证（模块9-12）

**测试方法**：
1. 模块9：创建异动提醒条件（涨跌幅/量能/均线），触发时验证弹窗+企业微信双提醒
2. 模块10：运行状态面板验证数据源状态/今日统计/异常日志，一键导出CSV
3. 模块11：策略复盘页面验证历史推送记录/月度胜率/平均收益/最大回撤，筛选功能
4. 模块12：参数设置对话框验证参数调整/多方案保存/一键切换，未回测验证不能激活

**验收标准**：
- 每个模块功能完整可用
- 异常日志记录完整，可导出
- 策略参数修改不直接影响实时选股（回测验证后生效）

---

### 全量回归验证

**测试方法**：
1. 所有模块配置 `enabled = false`，启动程序，验证原有所有功能100%正常
2. 逐个开启模块，每开启一个运行10分钟，验证无崩溃无异常
3. 全部开启后运行30分钟，验证程序稳定性
4. 启动耗时对比：V2.7基线 vs V2.8全量开启，增加不超过10%

**验收标准**：
- ✅ 原有AI520选股、行情、新闻、自选、企业微信推送全部正常
- ✅ 全量开启后程序稳定运行30分钟无崩溃
- ✅ 启动耗时增加 < 10%
- ✅ 单模块启动耗时 < 100ms
- ✅ 任何模块异常自动降级，不影响主程序

---

## 五、数据库设计

### v28_cache.duckdb（V2.8专用数据库，运行时自动创建）

| 表名 | 所属模块 | 说明 |
|------|----------|------|
| stock_radar_cache | 模块2 | 个股排雷结果缓存 |
| signal_tracking | 模块3 | 信号跟踪主表 |
| signal_score_history | 模块3 | 评分历史记录 |
| signal_status_log | 模块3 | 状态变更日志 |
| trade_plans | 模块8 | 交易计划表 |
| custom_alerts | 模块9 | 自定义异动提醒条件 |
| custom_alert_logs | 模块9 | 异动提醒触发日志 |
| health_logs | 模块10 | 异常日志 |
| health_stats | 模块10 | 每日运行统计 |
| strategy_param_profiles | 模块12 | 策略参数方案 |

---

## 六、上线建议

1. **第一周**：仅开启模块1（大盘风控），观察风控面板数据准确性
2. **第二周**：开启模块2（个股排雷），先不开启auto_exclude_high_risk，仅观察标签
3. **第三周**：开启模块3（信号跟踪），验证状态流转和价格提醒
4. **第四周起**：逐步开启P1/P2模块，每个模块观察2-3天
5. **所有模块默认关闭**，确认稳定后再永久开启
