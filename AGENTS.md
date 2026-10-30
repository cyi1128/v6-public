# QuantMonitorV6 — 项目说明（给 AI 助手看）

A 股盘中监控程序。Python 3.14 + PyQt6 + DuckDB + SQLite。入口 `main.py`。

- Python 解释器：`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
- 系统：Windows，shell 是 PowerShell（读写文本必须显式 UTF-8）

---

## 备份与恢复（重要）

项目有三层备份，详见 `备份与回滚说明.md`。

### 当前稳定版还原点

| 项 | 值 |
|---|---|
| 标签 | **1010n 稳定版（五阶段观察标签铺到 UI；A+B 落地）** |
| 快照目录 | `backups\backup_20261011_175355`（1338 文件 / 77.0 MB） |
| Git 提交 | 未提交（工作区状态） |
| 时间 | 2026-10-11 17:53 |

> 上一版 1010m 快照 `backups\backup_20261011_112723` 仍在盘上；`scripts\backup.py` 只保留最近 10 份，再打几次备份它会被自动清掉。

这一份快照**已核实真的含 1010m 的 pos45 改动**（快照内 `strategy\base.py` 1712 行、含 `MARKUP_POS_MAX = 0.45` 与前置门槛；`services\band_pattern_engine.py` 2074 行、`_MARKUP_FUNNEL` 带 `'pos'` 键；快照内 `AGENTS.md` 已含 1010m 记录）。

这一份含**截止 2026-10-11 11:27 的全部代码改动**：控盘度三件套（控盘分 / 洗盘-出货 / 建仓因子）+ C1~C6 观察规则 + 试盘识别 + 出货形态确认 + 试盘位置门槛 0.35 + 洗盘文案降级（`_WASH_NOTE_MODE='off'`）+ **拉升阶段识别（`_MARKUP_NOTE_MODE='watch'`，第五类观察规则）** + **拉升位置门槛（`MARKUP_POS_MAX=0.45`，1010m）** + 创业板放行 + 四批判涨停修复 + 门槛收紧 + MA20 硬门槛。
备份**不含** duckdb（数据类），所以快照里没有扫描后的 `band_pattern.db` 与回填后的 `picks_tracking.duckdb`；要重建就关掉主程序后跑 `python tools\run_scan_quiet.py` / `python services\picks_tracking_service.py --backfill`。

> ⚠️ **只剩 10 份快照，且早期基线已被清空**：`scripts\backup.py` 只保留最近 10 份。截至 2026-10-11 10:10，`150427`、`145546`、`134550`、`005808`、`20261009_172437`、`20260926_203651`、`20260924_170012`、1010 旧基线 `20261010_153652`，**以及 1010a `backup_20261010_193113` 都已自动清理，磁盘上没有了**。
> 也就是说「回到没有控盘/试盘/出货形态的版本」现在**已无快照可回**，只能走 Git `git reset --hard f2d3bcd`（0924 版）。
> 恢复编号以 `python scripts\restore.py --list` 与 `backups\` 目录为准（下表 2026-10-11 10:10 已核对一遍）。

这个版本包含：

- **「🎯 今日决策」新页（2026-10-17 新增；清一盘首页第一屏升级为今日市场决策页）+ 控盘选股「仅看今日主线」开关**：
  - **新文件 `services/decision_page_service.py`（纯 LF，约 12KB）**：`compute_decision()` 主入口，全部复用现有模块——`market_rhythm_engine.get_rhythm()`（题材/状态/龙头/梯队/轮动）、`market_dashboard_service.compute_dashboard()`（广度/情绪分/封板率）、holding 表（`data/cache/atr_t_tracking.duckdb`）、`control_screen_service.compute_stock()`（持仓弱化）。
  - **顶部状态条**：市场状态四级（主升浪/震荡上行/震荡分化/退潮期）+ 建议最大仓位（重仓/中等/轻仓/空仓·极轻仓）+ 情绪分 + 轮动方向 + 全部刷新。
  - **四重共振**：板块卡（+30 家数增/+25 状态持续或首日/+25 均涨跑赢大盘；成交额20分跳过）、龙头卡（+40 率先涨停或连板/+30 连板/+30 当日未炸板，查 zbc）、资金卡（+30 涨停数增/+35 跟风梯队≥3/+35 连板高度未降）、情绪卡（基础=情绪分，封板率≥70且炸板≤20 +10，炸板≥30 −15）；总分=四卡均分，≥75 强/55-74 中/<55 弱。
  - **两处安全修正（不照搬配置原文）**：① 退潮期闸门——情绪分 26 时四卡总分仍 76.5（创新药卡强），原结论会喊「主线明确进攻」，与顶部「空仓」矛盾；现退潮期一律输出「不新开仓」。② 持仓预警只保留 cost 非空的真实持仓（holding 表混入约 28 只 cost=None 的做T自选池，含 000678 等触发天量的噪音）。
  - **主线快照**：`data/cache/today_main_themes.json`（最强1~2题材+同簇cluster，由 compute_decision 写入）。
  - **新文件 `ui/battle_widgets/decision_page_widget.py`（纯 LF，约 10KB）**：顶部状态条 + 4 共振卡 + 总分条 + 方向结论 + 持仓预警表（吃剩余高度）；`jump_to_control` 信号。
  - **挂最前页签**：`ui/battle_console_v2.py`（纯 CRLF）在「🤖 清一盘」前注册「🎯 今日决策」；新增 `_jump_to_control_filtered()`：切到控盘页并自动勾主线开关。
  - **控盘页开关**：`control_screen_widget.py`（纯 LF）筛选区「剔除ST」后加「仅看今日主线」复选框（默认关），在 `apply_filters` 结果之上用 `filter_rows_by_themes()` 按行内 `theme`（最近一次涨停原因）匹配主线名/同簇题材；原有默认筛选全保留；`enable_mainline_filter()` 供跳转调用。**注意：stock_keywords.json 对多数股票只有名字无题材，不能用于全市场过滤**，已改用行 theme。
  - **验证**：`tools/_verify_decision_page.py`（可重跑）：服务断言、闸门、cost 过滤、开关往返（默认1118 → 主线42 → 关闭1118）、离屏渲染两页截图（`tools/_shot_decision.png`、`tools/_shot_control_mainline.png`）。
  - 需重启主程序才能看到新页签。
  - **同日二次重写为七行高密度白版**（用户指上一版空壳）：第1行状态条（状态/情绪/仓位/涨停炸板/最高连板/成交额+真刷新）、第2行四大指数（`_index_snapshot()` 腾讯 qt.gtimg.cn sh000001/sz399001/sz399006/sh000688 点位+涨跌幅）、第3行核心横条（涨平跌/强弱±3%/MA20站上率/新高新低）、第4行四卡压缩+总分+**情绪一票否决**（sentiment≤35 或退潮期→共振封顶「中」+显示「⚠情绪拖累，不可进攻」，result 增 veto/allow_open 字段）、第5行左涨跌分布8桶+连板梯队、右主线+轮动+概念TOP5、第6行结论+真跳转按钮、第7行持仓表（stage unknown 显示 '-'）。按钮全部真绑定：刷新=run_async 重算 compute_decision，跳转=jump_to_control 信号。
  - **复盘日报自动推微信（同日）**：此前 `services/daily_close_summary_service.py`（11节复盘报告）与 15:05 定时器在 `ui/main_window.py`，但 `main.py` 实际启动的是 `BattleConsoleWindowV2` → 定时器从不运行。已把同款 30s 定时器 + `_check_close_summary()` 搬进 `BattleConsoleWindowV2`（battle_console_v2.py）：交易日 15:05 后后台线程跑 `generate_and_push()`，经 `wechat_bus` → 企业微信群机器人（webhook 已配在 data/wechat_config.json，实测 test_push 成功），用 `data/daily_close_summary_state.json` 一日一次去重。**程序需在 15:05 后保持开着才会推**；纯定时器接线，无引擎改动，重启主程序生效。

- **「📈 策略看板」新页（2026-10-17 新增；对标 TickFlow Stock Panel 的选股/扫描部分）**：
  - **定位**：用户转发 TickFlow Stock Panel 安利贴，要求「在我程序单开一页做这个项目」。v1 只做其**选股/扫描**部分（回测引擎 / AI 复盘留后续迭代），全部吃本地 kline_cache，不引外部栈、不装重型依赖。
  - **新文件 `services\strategy_scan_service.py`（纯 LF）**：`STRATEGIES` 7 个策略（`ma_gold` MA5上穿MA20 / `ma_long` 均线多头排列 / `macd_gold` DIF上穿DEA / `rsi_oversold` RSI14≤25 / `kdj_gold` K上穿D / `brk_vol` 收盘创20日新高且量比≥1.5 / `pull_ma20` 缩量回踩MA20）。纯 Python 指标（`_ma_series`/`_ema_series`/`_kdj_series`），全市场 4416 只实测 **3 秒**。复用 `control_screen_service.load_all_bars()` / `code_name_map()` / `is_st_name()`；结果落 `data/cache/strategy_panel.json`。**RSI 阈值定 25 而非 30**：实测普跌日 RSI≤30 会命中全市场 1/4（689→1100+），等于没筛。
  - **新文件 `ui\battle_widgets\strategy_panel_widget.py`（纯 LF）**：`StrategyPanelWidget(BattleModuleBase)`，7 列（股票名称/代码/现价/涨跌幅/命中策略/位置/数据日，命中策略列 Stretch）；工具栏 7 个策略复选框（默认全选）+ 开始扫描/停止 + 进度条；双击行发 `stock_clicked(code,name)`。
  - **挂 Tab**：`ui\battle_console_v2.py`（纯 CRLF）在控盘选股块后插 try/except 注册 `📈 策略看板`，并在信号连接区把 `stock_clicked` 接到 `_show_stock_detail`（由 `tools\_apply_strategy_tab.py` 一次性完成，勿重跑）。
  - **验证**：`tools\_verify_strategy_panel.py` **13 PASS / 0 FAIL**（造数：多头排列/金叉/放量突破命中、不足60根不命中；实扫 1733/4416、数据日新鲜、每只至少命中一个；离屏渲染 1733 行）。命中分布：多头排列 891 / RSI超卖 689 / 缩量回踩MA20 139 / MA金叉 72 / KDJ金叉 59 / 放量突破 30 / MACD金叉 28。
  - **刻意没做（下一步候选）**：TickFlow 的回测（vectorbt 式 T+1/手续费/滑点/止损；用户已明确「不做回测」）、AI 复盘（DeepSeek/通义/Ollama，待用户给 Key 与配置位置）。
  - **盘后复盘子页（同日追加，用户「盘后还能看连板梯队、概念轮动、炸板翘板」）**：策略看板页外层加 QTabWidget = 「策略扫描」（原有内容）+「盘后复盘」；盘后复盘内层直接**复用现有成熟控件**（不自造数据引擎）：连板梯队=`LeaderLadderWidget`、概念轮动=`MarketRhythmWidget`、涨停·炸板=`LimitUpWidget`（涨停控件「炸板也不删」，故炸板股可见）。子控件 `stock_clicked` 转发到本页信号。`strategy_scan_service.py` 另加了 `signal_series()`（全历史信号序列，原计划给回测用；回测已取消，函数保留无害）。
  - **市场看板仪表盘（同日追加，用户给 TickFlow 首页截图要求「按图片排序生成」）**：外层第一个页签「市场看板」= `ui\battle_widgets\market_dashboard_widget.py`（新），数据服务 `services\market_dashboard_service.py`（新，纯 LF）。布局照截图：指数条(占位未接行情) → 6 统计卡(涨/平/跌、强/弱≥3%、涨停/炸板·封板率、最高连板、成交额、均涨/中位) → 涨跌分布8桶+情绪分+趋势强度(MA站上率/新高新低)+涨停梯队 → 概念/行业热度TOP5 → 四张榜(涨/跌/额/振幅)。数据全本地：广度/榜走 `load_all_bars()`，涨停梯队走 `data\limit_up_reason.db`(连板数lbc/炸板zbc)，概念行业走 `board_anomaly_engine.get_board_anomaly()`。**QProgressBar.setValue 必须传 int**（MA站上率是 float，踩过一次 TypeError）。
  - **AI 复盘页（同日追加，用户「启用本地部署的 o 开头模型」=Ollama）**：`services\ai_review_service.py`（新）+ `ui\battle_widgets\ai_review_widget.py`（新），外层第 4 个页签「AI 复盘」。本机 Ollama 装在 `D:\Ollama\`（默认 `http://localhost:11434`），已装 4 个模型：`qwen2.5:7b`(默认)/`deepseek-r1:7b`/`qwen3:14b`/`qwen2.5-coder:7b`。Service 把 `market_dashboard_service.compute_dashboard()` 拼成文本快照，POST `/api/chat`（stream=False, temperature=0.6, num_predict=900），UI 下拉切模型 + 按钮生成，后台 `run_async` 不卡界面。实测 qwen2.5:7b 约 18 秒出 400 字复盘。Ollama 没启动时 UI 状态栏会提示。

- **控盘选股「数据日停在昨天」→ 取数源顺序修复 + 当日 bar 补齐 + 接到页面扫描前（2026-10-12；用户「控盘选股没有更新实际数据」→ 选「要」自动补）**：
  - **根因**：`utils\kline_fetcher.py` 的 `fetch_kline()` 旧顺序 `pytdx → 新浪 → 腾讯 → 东财`，判据是「根数够就 return」。盘中实测：pytdx 服务器可连但**无数据**；**新浪日线不含当天未收盘 bar（末根=上一交易日）**；腾讯**有**当天 bar 却排在新浪之后永远用不上；东财连接被断 → K线缓存与控盘选股的数据日停在上一交易日（当时是 10-09）。
  - **修复 1（取数源）**：`fetch_kline` 改**新鲜度优先** —— 逐源尝试，优先返回「末根=今天」的那一份，都不新才退回第一份能用的；新增 `_kline_last_date()` / `_today_bar_expected()`（工作日 + 非节假日 + 已过 09:30，按分钟缓存）。380 → **431 行**，仍**纯 CRLF + BOM**，编译 OK。实测 8 只不同板块代码全部拿到当天 bar（0.26~0.75s/只）。
  - **修复 2（当日 bar 补齐器）**：`services\kline_cache_service.py`（**纯 LF，11664 → 16079 B**）新增 `seed_today_bar(codes=None, progress_cb=None, only_in_session=True, sleep_per_batch=0.0)` —— 走腾讯**批量实时行情**（`qt.gtimg.cn`，80 只/请求、全市场 56 请求、约 55 秒），用当日快照拼今天这根**未收盘** bar（open/high/low=快照、close=最新价、volume=手×100、amount=volume×close、`ON CONFLICT(code,date)` 更新、同步 `kline_cache_meta` 记 `source='realtime_seed'`），停牌/无成交跳过不写假 bar，DB 被占用退避重试 6×2s。`tools\seed_today_bar.py` 改为它的**薄 CLI 封装**（`--codes` / `--force-anytime`）。
  - **为什么不用逐个代码抓日线**：实测 4427 只里 **3242 只腾讯日线被 WAF 限流**（`[KLINE TX] 解析异常`），退回新浪旧数据 → 命中不了当天 bar。
  - **修复 3（接到页面扫描前）**：`ui\battle_widgets\control_screen_widget.py`（**纯 LF，717 → 758 行**）工具栏新增复选框 `_ck_seed = QCheckBox('补当日K线')`（默认勾选 + 说明 tooltip），`_start_scan` 的 `_job()` 在 `SS.load_all_bars()` **之前**调 `seed_today_bar(progress_cb=_p)`，状态栏依次显示「补当日K线 n/N」→「当日K线已补 N 只（覆盖 a→b），开始扫描…」/「当日K线未补：<原因>」/「当日K线补齐异常：…」；只在交易日 09:15~15:05 生效（`utils.trade_calendar.is_market_open`），失败不打断扫描。
  - **顺手修掉的真实缺陷**：`_on_scan_ok` 原来**无条件** `save_snapshot` —— 点一次「停止扫描」就把残缺结果（实测 0 行 / **122 B 空壳**）覆盖掉上一次完整快照，下次打开本页是空表。现在 `_cancelled or not rows` 时不覆盖快照，列表与快照保持上一次结果，状态栏提示「扫描已中止：本次 N 只…」（提示必须放在 `_apply_and_render()` **之后**，否则会被 `_update_count` 重写的统计条盖掉）。
  - **验证**：`tools\_verify_seed_bar.py` **22 PASS / 0 FAIL**（服务层：写库成功、库里真有今天行、volume 是**股**、meta 同步、非交易时段被打回且不写行、无行情代码不写假 bar；页面层：开关存在/默认勾选/挂在 bar1、源码顺序「先补数后读K线」、真跑扫描 91s（补数≈58s + 扫描 31s）vs 关掉开关 **33s**、结果 `data_date`=今天）；`tools\_verify_seed_msg.py` **4 PASS / 0 FAIL**（成功/跳过/异常三条状态文案）；`tools\_verify_cancel_snapshot.py`（中止不覆盖快照 + 正常扫描照旧覆盖）。
  - 实测数据：当日 bar 覆盖 **1835 → 4418 / 4427 只**（9 只当日无有效行情，多为停牌）；快照 `data\cache\control_screen.json` 数据日 **2026-10-09 → 2026-10-12**（4404 行）；页面渲染统计条「符合条件 1083 只 ｜ 全量 4404 只 ｜ 扫描 4416 只 ｜ 数据日 2026-10-12」。
  - 回退：`copy /Y "utils\kline_fetcher.py.bak_before_fresh" "utils\kline_fetcher.py"`、`copy /Y "services\kline_cache_service.py.bak_before_seed" "services\kline_cache_service.py"`、`copy /Y "ui\battle_widgets\control_screen_widget.py.bak_before_seed" "ui\battle_widgets\control_screen_widget.py"`、`copy /Y "tools\seed_today_bar.py.bak_before_seed" "tools\seed_today_bar.py"`。**纯取数 + UI 改动，不需要重跑全市场扫描，但必须重启主程序**（运行中的实例内存里是旧取数代码）。
  - 一次性补丁勿重跑：`tools\_fix_kline_source_order.py`、`tools\_refill_today_kline.py`、`tools\_apply_agents_seed.py`；可重跑：`tools\seed_today_bar.py`、`tools\_rescan_ctrl_today.py`、`tools\_verify_seed_bar.py`、`tools\_verify_seed_msg.py`、`tools\_verify_cancel_snapshot.py`、`tools\_shot_ctrl_screen.py`。
- **日K线图修复 + 板性阈值/周期切换真正生效（2026-10-11 深夜；用户一句「修复日k线图」；纯 UI，不碰引擎与扫描）**：
  - **① 图全空白（致命）**：`ui\echarts_kline.py` 里 `_lu_pct = ...` 那两行被误粘进了 `js_code = f"""…"""` 的 **JS 模板内部**，求值 f-string 时 `{_lu_pct}` 直接抛 `NameError` → 被外层 `except` 吞掉 → `runJavaScript` **从未执行** → **所有周期、所有入口的日K线图都是空白**。修法：注释与赋值移到 f-string **之外**，JS 串内只留 `window.__limitPct = {_lu_pct};`。
  - **② 伴生 bug（板性判定一直失效）**：`set_kline_data()` 循环内部有一行 `code = kline_data.get('code', '')`，**把入参 code 覆盖成空串**（`get_kline_by_period()` 返回的 dict 根本没有 `code` 键）→ 逐根「涨停K线标紫」永远走主板分支（创业板 10% 就被误标紫、真 20cm 反而用错阈值）；`window.__limitPct` 恒 9.8；`current_code` 回填不了 → 组件内「日/周/月/15/30/60分」按钮点了没反应。修法：循环前算一次 `_kline_code`（入参 → 数据字典 → `current_code`），循环内与末尾共用，**删掉覆盖入参那句**。
  - **③ code 贯通到控件**：`EChartsKlineWidget.set_kline_data(kline_data, code='')` 与 `KlineContainer.set_kline_data(kline_data, code='')` 均为**新增可选参数**（旧调用不受影响）；容器新增 `pending_code`，`_check_echarts_status` / `_fallback_to_qpainter` / `_on_timeout` **三处 pending 重放**都带上；调用方补传各自手上的 code：`battle_console_v2._load_kline`+`_retry_kline_render`、`stock_detail_v1._set_kline_data`、`professional_kline_dialog`、`pro_stock_pool`（`self._kline_code`）；`watchlist_panel` 本来就传了。
  - 改动量（对着备份逐行 diff）：`echarts_kline.py` +10/−9、`kline_container.py` +12/−6、`battle_console_v2.py` +2/−2、`stock_detail_v1.py` +1/−1、`professional_kline_dialog.py` +1/−1、`pro_stock_pool.py` +2/−2，**合计 49 行**；六个文件仍**纯 CRLF（裸 LF=0）**、`py_compile` 全 OK。
  - 验证（全部实跑）：`tools\_verify_kline_lupct_logic.py` **5 PASS/0 FAIL**（300750→19.8 / 600519→9.8 / 688981→19.8 / code 放数据字典→19.8 / 都不给→9.8 兼容，且 current_code 三种来源都能回填）；`tools\_verify_kline_limitup_purple.py` **3 PASS/0 FAIL**（造 +10% 与 +20% 两根：创业板只标紫 1 根、主板标紫 2 根）；`tools\_verify_kline_container_code.py` **9 PASS/0 FAIL**（三处重放带 code、QPainter 路径透传、无参调用兼容）；真实 WebEngine：`300750/day` 300 根 + luPct **19.8**、`600519/day` 269 根 + 9.8、`600519/week` 500 根、`600519/5分` 500 根（后两例走**单参数**调用，证明向后兼容）。
  - 回退：`copy /Y "ui\echarts_kline.py.bak_before_kline_code2" "ui\echarts_kline.py"`（含①②；要连①一起退到修复前用 `.bak_before_kline_fix`）+ 同后缀 `.bak_before_kline_code` 的 `ui\kline_container.py` / `battle_console_v2.py` / `stock_detail_v1.py` / `professional_kline_dialog.py` / `pro_stock_pool.py`。**纯 UI 改动，不需要重跑全市场扫描，重启主程序即可。**
  - 一次性补丁勿重跑：`tools\_fix_kline_lupct.py`、`_fix_kline_code_plumb.py` / `_plumb2.py` / `_plumb3.py` / `_plumb4.py`。可重跑：`_verify_kline_code.py`（`KL_CODE` / `KL_MODE` / `KL_OUT`）、`_kline_case.py`、`_verify_kline_lupct_logic.py`、`_verify_kline_limitup_purple.py`、`_verify_kline_container_code.py`、`_diff_kline_code_plumb.py`。
  - ⚠️ 本机多用例版 `tools\_verify_kline_fix.py` 与 `_diag_kline_ui.py` / `_diag_kline_win.py` 仍会**非确定性崩 0xC0000409**，别拿它们判成败；单用例 `_kline_case.py` / `_verify_kline_code.py` 稳定 exit 0。
- **五阶段「观察」标签铺到界面（1010n 新增；用户选 A+B；纯 UI + 页面服务层，不碰引擎、不重扫选股）**：背景是对照「机构/庄家/主力操盘控盘手法拆解」逐条核查后，发现 17 条手法里 **6 条界面直接可见、6 条只在 DB 字段或 tooltip、5 条界面完全看不到**（A/B 批次的破位收复 / 量能分位在全部 `ui\**` 里零引用；建仓因子只有数字没标签）。用户选 **A**（控盘选股页把 A/B 与建仓因子纳入「观察」列 + 加「阶段」筛选）与 **B**（日K建仓表把只写在 `note` 里的文案拆成可见的独立列）。
  - **词表唯一来源**：`services\control_profile.py`（**纯 CRLF，193 → 279 行**）末尾新增 `_OBS_TAG_ORDER` / `OBS_TAG_LEVEL` / `TAG_STAGE` / `STAGE_PICK` + `obs_tag_pairs()` / `obs_stages()` / `obs_tag_text()` / `obs_tag_color()`。标签固定顺序 **建仓(堆量/红肥绿瘦) → 试盘 → C4/C6 → 洗盘(洗盘收复/地量) → 拉升(拉升:形态/缩量上涨) → 出货(破位警示/天量/出货形态)**；level：`risk` 红 / `warn` 橙 / `gold` 金（试盘）/ `info` 蓝。**日K建仓表与控盘选股页共用这一份**，不要再各写一套。
  - `services\control_screen_service.py`（**纯 LF，886 → 946 行**）：`compute_stock` 增算 `detect_breakdown_recover` / `detect_volume_regime`，并把 `brk.get('type'), vreg.get('tags')` 传给 `_ctrl_note`（**此前只传 10 个参数，note 里没有 A/B 文案**）；`rec` 增 `stack_ok/redfat_ok/brk_type/vreg_tags/vreg_pct` 与 `obs_pairs`（JSON 友好 list）/`observe`/`stages`；`observe_tags()` 改为薄封装（旧调用方不受影响）+ 新增 `obs_tag_pairs(rec)` / `stages_of(rec)`（**老快照缺 `stages` 时从 observe 文本回推**）；`apply_filters(..., stage=None)` 支持按阶段筛。
  - `ui\battle_widgets\control_screen_widget.py`（**纯 LF，668 → 716 行**）：新增「阶段」下拉（`SS.STAGE_OPTIONS`，宽 88，紧跟「观察」下拉）；`_obs_color` 改为按 level 判；`_obs_tip` 补 A/B 因子与阶段；「观察」列宽 190 → 250、上限 330 → 430。**踩到的坑**：选具体阶段时会与「排除出货」互斥（勾着它再选「阶段=出货」会得到接近空表）→ `_on_stage_changed()` 在切到非「全部」时**自动松开「排除出货」**（只取消勾选、不隐藏控件），tooltip 里写明。
  - `ui\battle_widgets\atr_t_widget.py`（**纯 CRLF，2216 → 2260 行**）：日K建仓表 **12 列 → 13 列**，新列「观察」插在「控盘」与「环境分」之间（宽度 200）。**5 处同步齐全**：`COL_D_CTRL, COL_D_OBS, COL_D_ENV, COL_D_BASE_DATE = range(13)` / `HEADER_DAILY` / `DAILY_WIDTHS` / `make_table(13, ...)` / `_daily_render_table` 的 `setItem(i, COL_D_OBS, ...)`。行数据补 `probe_ok/c4_ok/c6_ok/brk_type/vreg_tags/dist_type/markup_type`，**并补上原来漏带的 `ctrl_tag`**（此前控盘列只能退回 note 白名单比对）。该列一格一个颜色（取该格最高 level），悬停显示手法阶段 + 逐条标签 + 完整 note。
  - 实测量级（`tools\_verify_obstags.py` → `tools\obstags_verify.txt`，**43 PASS / 0 FAIL**，离屏 Qt 真实渲染）：DB 230 条里 145 条有标签、默认可见（建仓触发+等待确认）203 条里 **122 条**带标签；120 只真股票抽查 78% 有标签、五类阶段全出现（出货 46 / 建仓 39 / 洗盘 13 / 拉升 4 / 试盘 3）。**建仓因子 ok 率不是「几乎全中」**（500 只实测：堆量 16.0% / 红肥绿瘦 26.6% / 两者都中 6.6% / 都不中 64.0%），所以放进标签列有区分度、不是噪音。
  - 控盘选股页快照已按新字段重扫（`tools\_rescan_obstags.py` → `data\cache\control_screen.json`，4404 只 / 28s / 失败 0 / 数据日 2026-10-09）：标签命中 C6 1378、红肥绿瘦 1144、天量 1039、堆量 629、破位警示 415、地量 351、拉升 175、出货形态 156、洗盘收复 138、C4 136、缩量上涨 81、试盘 47；**默认筛选后仍是 993 行**（选股口径一行没动），其中 823 行带标签；阶段筛选：建仓 260 / 试盘 10 / 洗盘 162 / 拉升 25 / 出货 256。
  - 回归：`tools\_ctrltag_unit.py`（**35 PASS / 0 FAIL**）、`tools\_c6_ui.py`（**8 PASS / 0 FAIL**）、`tools\_verify_ctrl_col.py`（真实渲染里已能看到「观察=天量」）。旧验证脚本大多用 `len(M.HEADER_DAILY)` 动态取列数，**列数改动不破坏它们**（只有 `tools\_add_ctrl_col.py` 这类一次性补丁写死了 12，勿重跑）。
  - 回退（改完无需重扫引擎，只需重启主程序）：`copy /Y "services\control_profile.py.bak_before_obstags" "services\control_profile.py"`、`copy /Y "services\control_screen_service.py.bak_before_obstags" "services\control_screen_service.py"`、`copy /Y "ui\battle_widgets\control_screen_widget.py.bak_before_obstags" "ui\battle_widgets\control_screen_widget.py"`、`copy /Y "ui\battle_widgets\atr_t_widget.py.bak_before_obstags" "ui\battle_widgets\atr_t_widget.py"`；控盘选股页快照要回到旧字段就重扫一次（页面打开时自动扫）。一次性补丁 `tools\_apply_obstags_profile.py` / `_apply_obstags_service.py` / `_apply_obstags_widget.py` / `_apply_obstags_atrt.py` **勿重跑**。
  - **刻意没做**：C 项（把洗盘收复/地量做成强提示）——标定里这两类没有正向价值，这里只作为「状态存在」的中性事实标注（蓝/灰），不当买入提示；建仓因子的 note 文案开关 `_BUILD_NOTE_MODE` 仍是 `'off'`（动它等于改引擎）。

- **⚠ 快照之后又改了 1 个文件（已含在 1010n 快照里）**：`ui\battle_widgets\market_rhythm_widget.py` —— 「市场节奏」Tab1 / Tab2 接入控盘度（见下面「控盘度已铺到全部列表模块」一节）。纯 UI 列/文案改动，不涉及扫描与 DB，**不需要重跑全市场扫描**；回退 `copy /Y "ui\battle_widgets\market_rhythm_widget.py.bak_before_rhythm_ctrl" "ui\battle_widgets\market_rhythm_widget.py"` 后重启主程序即可。

- **拉升位置门槛（1010m 新增，方案 C；纯筛选口径改动，不新增文案规则）**：`detect_markup` 命中整体相对基准只有 **+0.06pp** 增量（=噪音），分档看只有 **pos120 < 0.45** 是正期望（+1.10% / 胜率 54.3% / **t=+3.31**），pos∈[0.45,0.60) −2.79%、[0.60,0.75) −4.25%、≥0.75 −3.32% **三档全部显著为负** → 在因子层加前置门槛，只保留低位子集。用户在 (A) 维持 watch /(B) 改 off /(C) 加门槛里**选 C**。
  - `strategy\base.py`（**纯 CRLF**，1688 → **1712 行**）：新增 `MARKUP_POS_MAX = 0.45`（紧跟 `MARKUP_MIN_BARS = 60` 之后，含依据与边界注释）+ `detect_markup` 函数体内的前置门槛（`pos` 算完、`hi60` 之前：回填 `r['pos120']` → `if pos >= MARKUP_POS_MAX: r['reason'] = 'pos>=%.2f' % MARKUP_POS_MAX; return r`）+ docstring「前置」段。
  - **边界口径（别改成 `>`）**：`pos` 分母带 `+1e-8`，0.45 归入负期望档，所以判定必须写 `>=`。真实临界样本：`000668 2026-09-30 pos=0.4470`（放行）/ `300214 2026-10-09 pos=0.4601`（拦下）。
  - `services\band_pattern_engine.py`（**纯 LF**，2065 → **2074 行**）：`_MARKUP_FUNNEL` 加 `'pos'` 计数键；`scan_stock` 计数分支改成 `_mrr.startswith('pos>') → ['pos']`、其他有 reason → `['insuf']`（与试盘那套写法一致）；`scan_all` 打印改为「可算（已过位置门槛）…」+「位置超限跳过(pos>=0.45) N 只」，阈值用 `from strategy.base import MARKUP_POS_MAX` 现取，不写死。
  - **⚠ 连带后果（已写进两处注释，别当 bug）**：形态②`缩量强势`自带 `MARKUP_LOCK_POS_MIN=0.55`，被 0.45 门槛完全覆盖后**不可达** —— 现参数下②不会再产生命中。常量保留，把 `MARKUP_POS_MAX` 改回 `1.01` 即可恢复。**命中数 276（237/29/10）→ 81（80/0/1）。**
  - 全市场扫描（`tools\run_scan_quiet.py` → `tools\_scan_after_markup_pos45.log`）：**5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**，与 1010l **逐项 0 变化**（只新增字段与文案，不参与任何筛选）；漏斗 `[拉升观察] 可算（已过位置门槛）2675 只 ｜ 阶梯式上行 80 ｜ 缩量强势 0 ｜ 加速迹象 1 ｜ 命中合计 81` + `位置超限跳过(pos>=0.45) 906 只`（2675+906 = 3581 = 全项目控盘/观察因子的可算只数）。库内 `markup_ok=1` 由 **50 条 → 14 条**（全是阶梯式上行），界面 203 行里可见 **14** 行。**唯一非 markup 的连带变化**：`[控盘度] … 触发提醒 1750 → 1604 只`（`_CTRL_FUNNEL['tip']` = 至少有 1 条文案的个股数，少了 146 只「只靠拉升文案才有提示」的票）。
  - 重跑标定（`tools\_calib_markup.py` → `tools\markup_calib.txt`；门槛前那份另存 `tools\markup_calib_before_pos45.txt` / `.csv`）：命中 **1250/17516（7.14%）**、均 **+1.10%** / 中位 +0.82% / 胜率 **54.3%** / **t=+3.31**；pos 分档只剩 `[0.00,0.45)` 一档（其余三档 n=0，证明门槛生效）；score 分档 `[70,80) +2.26%/62.4%`、`[80,90) +1.55%/55.3%`、`[90,101) −2.88%/37.2%`（**低位子集里仍然是分数越高越差**）；逐锚点 k20 −4.28%（增量 −2.45pp）/ k40 +3.57%（+0.60pp）/ k60 −1.71%（−2.74pp）/ k80 −17.10%（−11.80pp）→ **仍是「有结构但锚点依赖」**，门槛只删掉了明确为负的高位段，没有改变这个因子的脆弱性；与出货形态重叠由 85 条降到 **0 条**。
  - 验证：`tools\_verify_markup_pos45.py`（可重跑，`$env:MP45_SAMPLE` 控抽样只数）→ `tools\markup_pos45_verify.txt`（**32 PASS / 0 FAIL**：[A] 常量/源码**构造式**比对 —— 新函数 == 备份 + 恰好两处插入、`if pos >= MARKUP_POS_MAX:` 只出现 1 次且备份里没有；[B] 边界 0.4499 放行 / 0.4501 拦下 / **恰好等于门槛**（把门槛设成用同一公式算出的浮点值）拦下；[C] 真实 398 只：拦下 103 只、未拦的最高 0.4470、拦下的最低 0.4601、把常量临时改 1.01 后同一只不再被拦、常量已改回；[D] DB 229 条逐只独立重算：`markup_ok=1` 的 pos120 全部 < 0.45、`pos>=0.45` 的记录 `markup_ok` 全为 0）。
  - 同步复跑（门槛改了语义，这两套必须一起跑）：`tools\_markup_unit.py` → **39 PASS / 0 FAIL**（[A] 造数用例已按门槛语义改造：新增助手 `lower_pos()` 把 ①/③ 形态搬到低位再验；② 视为「门槛下不可达」，改成两步 —— 先断言被门槛拦下、再把 `MARKUP_POS_MAX` 临时改 1.01 证明②自身形态逻辑仍完好；[B] 真实 294 只命中 5 只且 pos120 全部 < 0.45、被门槛拦下 68 只（最低 0.4504）、中间值逐只一致 226 只、可复现 60/60；[C] 旧 9 参数 14580 组 + 旧 7 参数 64 组仍与 `.bak_before_markup` 逐字一致）；`tools\_markup_dbui.py` → **26 PASS / 0 FAIL**（DB 59 列同序、3 列 230/230 全填、`markup_ok=1` ⟺ note 含「拉升观察」、离屏渲染 203 行中 14 行可见拉升文案、控盘列 31 条标签未被污染）。
  - 回退：`copy /Y "strategy\base.py.bak_before_markup_pos45" "strategy\base.py"` + `copy /Y "services\band_pattern_engine.py.bak_before_markup_pos45" "services\band_pattern_engine.py"`（**回退后必须重跑扫描**）。
  - `tools\_apply_markup_pos45.py` / `tools\_fix_markup_docstring_esc.py` 都是**一次性补丁，勿重跑**。
  - **本批踩过的两个小坑**：① docstring 里写 `tools\markup_calib.txt`（单反斜杠）会触发 `SyntaxWarning: "\m" is an invalid escape sequence`，必须写双反斜杠；② 用 Python 读 CRLF 文件做**多行锚点比对**时必须先 `.replace('\r\n', '\n')` 归一化，否则锚点命中 0 次、比对会假失败。
- **拉升阶段识别（1010l 新增；第五类观察规则，不参与 signal_level / 建仓价 / 排序 / 等级）**：
  - 因子本体 `strategy\base.py`（**纯 CRLF**）新增常量块 `MARKUP_*`（紧跟 `DIST_MIN_BARS = 60` 之后）+ `TechnicalIndicators.detect_markup()`（插在 `detect_distribution_pattern` 之后、`# K线数据解析` 之前）。文件 1449 → **1688 行**。
  - **三种形态**（命中多个取分数最高者）：
    - `阶梯式上行`：A1 MA5 > MA10 > MA20；A2 近 `MARKUP_TREND_WIN=10` 根累计涨幅 ≥ `MARKUP_TREND_GAIN(6%)`；A3 近窗口上涨日均量 / 下跌日均量 ≥ `MARKUP_UP_DN_VOL(1.00)`（**必须有下跌日**，否则该条不成立 —— 纯上涨不算「回调缩量」）；A4 最近 `MARKUP_HOLD_WIN(5)` 根最低价 ≥ MA20 × (1 − `MARKUP_PULLBACK_TOL(3%)`)。
    - `缩量强势`：B1 近 8 根阳线占比 ≥ 60%；B2 近窗口均量 / 前窗口均量 ≤ 1.00；B3 pos120 ≥ 0.55；B4 后半窗口最低价 ≥ 前半窗口最低价。
    - `加速迹象`：C1 近 5 根累计涨幅 ≥ 12%；C2 近窗口均量 / 前窗口均量 ≥ 1.30；C3 收盘 ≥ 近 60 日最高 × 0.98。
    - 返回契约与 `detect_probe` / `detect_distribution_pattern` 对齐；**分数两段不重叠**（`ok=True` 必 ≥ `MARKUP_SCORE_OK(70)`，未通过必 ≤ 60）。
    - **A4 的口径坑（本批踩过，别改回去）**：最初写成「近 10 根最低价 ≥ MA20×(1−3%)」，结果**所有快速发动的票都必然不通过** —— 发动那根的低点本来就在均线附近。改成只看最近 `MARKUP_HOLD_WIN=5` 根后单测才过。
  - `services\band_pattern_engine.py`（**纯 LF**，2010 → **2065 行**）接入：`_MARKUP_NOTE_MODE='watch'` / `_MARKUP_FUNNEL`（紧跟 `_WASH_NOTE_MODE` 之后）；`_ctrl_note()` / `_observe_tags()` 各加第 10 / 第 8 个参数 `markup`，文案「拉升观察：<类型>」写进 `note`（**绝不进 `ctrl_tag`**，否则会重演 ctrl_tag 误染绿色「候选」的老 bug）；`_ALL_COLS` 56 → **59 列**（`markup_ok` / `markup_type` / `markup_score`），`_save_or_update` 的列清单 / 占位符（56 → **59 个 `?`**）/ 取值三处同步；`scan_stock` 局部量 + 计算块（复用同一个 `_df`）+ `_ctrl_tip` 调用 + 计数器 + `rec`；`scan_all` 漏斗清零 + 打印。
  - **实测标定（`tools\_calib_markup.py` → `tools\markup_calib.txt` / `.csv`；17516 条滚动观测 / 4384 只 / 锚点 k=20/40/60/80，无未来数据）**：

    | 分组 | n | 未来20日均值 | 中位 | 胜率 | t |
    |---|---|---|---|---|---|
    | 全样本基准 | 17516 | −0.78% | −1.07% | 45.2% | −7.79 |
    | 拉升命中（全部 12.05%） | 2111 | −0.73% | −0.79% | 46.0% | −2.40 |
    | ├ pos120 < 0.45 | 1250 | **+1.10%** | +0.82% | **54.3%** | **+3.31** |
    | ├ pos120 ∈ [0.45,0.60) | 266 | −2.79% | −3.57% | 32.3% | −3.90 |
    | ├ pos120 ∈ [0.60,0.75) | 211 | **−4.25%** | −5.84% | 32.7% | −4.48 |
    | └ pos120 ≥ 0.75 | 384 | −3.32% | −4.41% | 35.9% | −3.30 |
    | 阶梯式上行 | 1818 | −0.59% | −0.55% | 47.2% | −1.86 |
    | 缩量强势 | 247 | −0.89% | −2.15% | 40.5% | −0.90 |
    | 加速迹象 | 46 | **−5.39%** | −6.89% | 28.3% | −1.74 |
    > **结论（如实，别包装）**：① **整体没有正向价值** —— 增量仅 **+0.06pp**，等于噪音；② **分数越高越危险**（score≥90 的 497 条为 −4.18% / t=−5.40，因为高分 = 涨幅大 + 量能猛 + 位置高）；③ **唯一有信息的是位置**：pos120 < 0.45 那 1250 条是 +1.10% / 胜率 54.3% / **t=+3.31**，而 pos ≥ 0.45 的三档**全部显著为负**；④ **逐锚点 3/4 为负**（k=20 −1.95pp / k=40 −0.23pp / k=60 −6.85pp / k=80 +2.44pp），属「有结构但锚点依赖」；⑤ 与出货形态重叠仅 85 条（0.49%）、与试盘 115 条（0.66%）。
    > **方向说明（最重要）**：这个因子找的是「**已经拉起来**」的票，而本项目主线是「买在启动前、不接飞刀」→ 它在框架里是**追高提示 / 排他标记**，不是买入提示。**一键切换**：`_MARKUP_NOTE_MODE` 改 `'off'` 即只写字段不出文案（与 `_BUILD_NOTE_MODE` 同一套写法，无需改代码）。
  - 全市场扫描（`tools\run_scan_quiet.py` → `tools\_scan_after_markup.log`）：**5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**，与 1010k **逐项 0 变化**（只新增字段与文案，不参与任何筛选）；漏斗 `[拉升观察] 可算 3581 只 ｜ 阶梯式上行 237 ｜ 缩量强势 29 ｜ 加速迹象 10 ｜ 命中合计 276`；DB 230 条里 `markup_ok=1` **50 条**（阶梯式上行 46 / 缩量强势 4），界面（默认只看「建仓触发 + 等待确认」）可见 **49 行**。
  - 验证：`tools\_markup_unit.py` → `tools\markup_unit.txt`（**33 PASS / 0 FAIL**：[A] 三形态造数 + 3 反例 + 3 边界 + 2000 组随机分数分段；[B] 294 只真实数据（命中 19 / 6.46%，命中样本 pos120 中位 0.580 vs 全样本 0.269，关键中间值与独立算法逐只一致，可复现 60/60）；[C] **14580 组旧 9 参数组合 + 64 组旧 7 参数组合与 `.bak_before_markup` 逐字一致**（证明老规则一个字没变）+ 新文案可见/可关；[D] 无未来函数静态检查）。
  - 验证：`tools\_markup_dbui.py` → `tools\markup_dbui.txt`（**26 PASS / 0 FAIL**，跑前设 `QT_QPA_PLATFORM=offscreen`：DB 59 列同序、3 列 230/230 全填、`markup_ok=1` ⟺ note 含「拉升观察」、离屏真实渲染 203 行里 **49** 行能看到拉升文案、控盘列 31 条标签未被观察文案污染、环境分列未错位）。
  - 回退：`copy /Y "strategy\base.py.bak_before_markup" "strategy\base.py"` + `copy /Y "services\band_pattern_engine.py.bak_before_markup" "services\band_pattern_engine.py"`，**回退后必须重跑扫描**；只想去掉提示文案 → `_MARKUP_NOTE_MODE` 改 `'off'`。
  - `tools\_apply_markup_base.py` / `tools\_apply_markup_engine.py` / `tools\_fix_markup_holdwin.py` 都是**一次性补丁，勿重跑**。

- **规则① 洗盘文案降级（1010k 新增，纯文案层改动，不影响任何选股结果）**：滚动观测里「控盘分 ≥85 且 `stage_guess='wash'`」这一组胜率约 **37.9%**，低于全样本基准 **45.2%**，换过多种位置/分数门槛都跑不赢基准 → 结论是「字段有价值、提示没有价值」。
  - 做法（用户给的 A/B 二选一里选的 **B**，与项目已有 5 个文案开关同一套写法）：`services\band_pattern_engine.py`（**纯 LF，1997 → 2010 行**）新增常量 `_WASH_NOTE_MODE = 'off'`（**L433**，紧跟 `_DISTP_FUNNEL` 之后，含依据注释）；`_ctrl_note_tags()` 的洗盘分支加守卫（**L518-519**：`if _WASH_NOTE_MODE != 'off' and ctrl >= _CTRL_HIGH and stage == 'wash':`）；docstring **L508 / L516** 注明已关闭。**判定函数 `judge_wash_or_distribute()` 一个字没改**（与上一批备份逐字比对，2121 字符完全一致），`stage_guess` 仍照常写 wash / distribute / unknown。
  - **恢复方式**：把 `_WASH_NOTE_MODE` 改回 `'watch'` 即可，无需改代码（验证脚本已双向验过）。
  - **实测影响面（重跑全市场扫描 + 逐行比对改动前模块）**：扫描 **5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**，与 1010j 那次**逐项 0 变化**（纯文案改动）；230 条记录里**改前只有 2 条**会出洗盘文案 —— `300018 中元股份`（控盘 94.8 / pos120 0.3222，改后无任何标签）与 `301658 首航新能`（控盘 86.2 / pos120 0.0710，改后保留「高度控盘候选」）；库内 `note` 与 `ctrl_tag` 含「疑似洗盘」的记录**均为 0 条**，`ctrl_tag` 只剩候选 19 / 出货 16；界面控盘列带标签 **31 条（候选 15 / 出货 16 / 洗盘 0）**，与改前一致。
  - **口径坑（写验证脚本时踩过，别重复踩）**：`_ctrl_note_tags(ctrl, stage, pos)` 吃的 `pos` 是**近 120 日位置（0~1）**（引擎 L1642），而库里 `struct_pos` 是**横盘结构位置百分比**（引擎 L1548 `round(pos*100,1)`）——**两者不是同一个量**，不能拿 `struct_pos` 去反算 `ctrl_tag`，要独立算 pos120。
  - 验证：`tools\_verify_wash_off.py`（可重跑）→ `tools\washnote_off_verify.txt`（**7 PASS / 0 FAIL**：252 组矩阵无洗盘文案、另两条规则与独立算法逐格一致、开关可逆、判定函数源码与备份逐字一致、引擎 diff 剔掉注释后只剩「开关常量 + 一行门槛 + 两行 docstring」）；`tools\_verify_wash_off_dbui.py`（可重跑，需 `QT_QPA_PLATFORM=offscreen`）→ `tools\washnote_off_dbui.txt`（**14 PASS / 0 FAIL**，含真实库与离屏渲染的日K建仓表）。
  - 连带同步的单测期望值：`tools\_c1c2_unit.py`（全部通过）、`_c3c5_unit.py`（全部通过）、`_buildfactor_unit.py`（48/0）、`_ctrltag_unit.py`（35/0）、`_probedist_unit.py`（50/0）、`_test_ctrl_dist.py`（**11/11**）。其中 `_test_ctrl_dist.py` 有 5 条期望值**在本批之前就已失效**（C1/C2 把出货改成位置主导 pos≥0.65、C3 把候选位置门槛改成 pos<0.25 之后没同步），已用 `.bak_before_washnote` 的引擎证明「改动前就对不上」，再用 `tools\_fix_stale_ctrl_dist.py` + `tools\_fix_last_case.py`（一次性，勿重跑）同步。
  - 回退：`copy /Y "services\band_pattern_engine.py.bak_before_washnote" "services\band_pattern_engine.py"`（**回退后必须重跑扫描**）；`tools\` 下同名 `.bak_before_washnote` 一并回退。
  - `services\control_profile.py` 的 `_CTRL_TAGS`（L131）与 `ctrl_label()` 里 `if '疑似洗盘' in _j:`（L159）**本批之后成为死分支**（「洗盘」短标签将不再出现）—— 无害，是否清理未定。
  - `tools\` 里仍有约 16 个脚本内含旧洗盘文案（`_audit_ctrl_db.py` / `_chk_ctrl_8590.py` / `_chk_ctrl_dist.py` / `_c1c2_db.py` / `_c6_db.py` / `_verify_ma20_gate.py` / `_apply_c3c5.py` / `_fix_ctrl_tag_ui.py` 等），**多数是一次性补丁/审计脚本，不要重跑**；真要重跑需先按现状同步期望值。

- **试盘识别 + 出货形态确认（1010i 新增，1010j 收紧试盘位置门槛；两条观察规则，不参与选股/排序/建仓价）**：
  - `strategy\base.py`（**纯 CRLF**）新增常量块紧跟 `C6_MIN_BARS` 之后（L84-L115：`PROBE_*` 9 个 + `DIST_*` 16 个），新增两个方法：`TechnicalIndicators.detect_probe()`（**L818**）与 `TechnicalIndicators.detect_distribution_pattern()`（**L965**），插在 `is_c6_candidate()` 之后、`# K线数据解析`（L1148）之前。文件 1084 → **1449 行**（1010j 又加了两行注释）。
    - `detect_probe`：前置 `pos120 <= PROBE_POS_MAX`，**该常量在 1010j 已由 0.75 收紧到 0.35**（理由见下；超过直接判 `pos>0.35` 并把该股归给「出货形态」）。在最近 `PROBE_LOOKBACK=11` 根里从后往前找「试盘日」候选 P1~P4（长上影 `upper/rng >= 0.50` 且上影 >= 实体、冲高 `spike >= 5%`、放量 `vol/前5日均量 >= 1.20`、收盘回落 `close <= high*0.97`）；再验 P5 缩量（`后段均量 <= 试盘日量*0.80` 或 `后段最大量 <= 试盘日量`）、P6 不破位（后段最低 >= `min(试盘日最低, 试盘日收盘)*(1-3%)`）。`stage`：`confirmed`（P5/P6 都过）/ `pending`（试盘日就是最后一根，**不出文案**）/ `''`。
    - `detect_distribution_pattern`：三种形态取分最高者 —— ① `高位放量滞涨`（pos>=0.65 + 当日最高接近近60日最高 + 收盘弱/收阴 + 量比>=1.80）、② `高位破位`（跌破平台下沿 x0.98 + 放量>=1.50 + pos>=0.40）、③ `双顶雏形`（两个局部高点差<=3%、间隔>=6根、中间回撤>=6%、第二顶量能衰减或高度不足、当前收盘<=颈线 x1.03）。
    - **分数两段不重叠**：`ok=True` 必 `>= PROBE_SCORE_OK/DIST_SCORE_OK = 70`，未通过必 `<= 60`（DB 里可据此反查，单测与 DB 双向断言都验过）。
  - `services\band_pattern_engine.py`（**纯 LF**，1888 → **1997 行**；1010k 后又 +13 → **2010 行**，见上面「规则① 洗盘文案降级」）接入：`_PROBE_NOTE_MODE='watch'` / `_PROBE_FUNNEL`（**L415**）、`_DISTP_NOTE_MODE='watch'` / `_DISTP_FUNNEL`（**L423**）；`_ctrl_note()`（**L453**）与 `_observe_tags()`（**L516**）各加两个参数 `probe` / `distpat`，文案为「试盘观察：长上影测试抛压」「出货形态观察：<类型>」；`_ALL_COLS`（L913）加 5 列 → **56 列**（`probe_ok` / `probe_score` / `dist_pattern_ok` / `dist_pattern_type` / `dist_pattern_score`，L935-937），INSERT 列清单（L1020）+ 取值（L1045）+ 占位符（56）三处同步；`scan_stock` 里 `_probe_*` / `_distp_*` 局部量（L1617）与两段计算块（L1685-L1720）+ `rec` 字段（L1796）+ `scan_all` 漏斗清零（L1879）与打印（L1932）。
  - **实测标定（`tools\_calib_probe_dist.py` → `tools\probe_dist_calib.txt`，17516 条滚动观测 / 4384 只，锚点 k=20/40/60/80，无未来数据）**：

    | 分组 | n | 未来20日均值 | 中位 | 胜率 | t |
    |---|---|---|---|---|---|
    | 全样本基准 | 17516 | -0.78% | -1.07% | 45.2% | -7.79 |
    | 试盘 confirmed | 657 | **+0.78%** | 0.00% | 49.8% | +1.51 |
    | ├ 试盘且 pos<0.35 | 462 | **+2.02%** | +1.10% | **55.0%** | **+3.41** |
    | ├ 试盘且 pos∈[0.35,0.55) | 140 | -0.70% | -1.64% | 40.7% | -0.66 |
    | └ 试盘且 pos∈[0.55,0.75) | 55 | **-5.87%** | -6.44% | 29.1% | -2.80 |
    | 试盘 pending（当天刚试盘） | 186 | **-4.19%** | -5.19% | 32.8% | -3.77 |
    | 出货形态命中（全部） | 306 | **-3.85%** | -4.23% | 37.3% | **-4.09** |
    | ├ 双顶雏形 | 291 | -3.58% | -3.82% | 38.1% | -3.70 |
    | └ 高位放量滞涨 | 15 | **-9.16%** | -9.07% | 20.0% | -2.34 |
    > **结论（如实）**：① **出货形态确认是真有效**（命中后跑输基准约 3.1pp，20 日内最大回撤中位 15.4%，放量滞涨样本达 24.3%），可作为警示保留；② **试盘识别整体只有弱正**（+0.78% / t=+1.51），**但 pos<0.35 的低位子集很强**（+2.02% / 55.0% / t=+3.41），**pos>=0.35 反而为负**（[0.55,0.75) 达 -5.87%）；③ **pending（试盘当日）显著负**（-4.19%）—— 所以「试盘日 = 最后一根」时**不出文案**是必须保留的设计；④ 逐锚点看，试盘 3/4 为正（k80 为 -1.81pp）、出货 3/4 为负（k40 例外），属「有信息但锚点依赖」的观察级因子，**不能当强信号**。
    > **1010j 已执行（用户选 A）**：`PROBE_POS_MAX` 由 0.75 收紧到 **0.35** —— 即「只保留低位有效子集」，pos≥0.35 的试盘不再出文案。改法见 `tools\_apply_probe_pos35.py`（一次性补丁，勿重跑；只改常量 + 两处注释/docstring，其余 24 个 `PROBE_*` / `DIST_*` 常量与备份逐字一致，脚本已逐项比对）。回退：`copy /Y "strategy\base.py.bak_before_probe_pos35" "strategy\base.py"`。
  - **1010j 收紧后的实测（与 1010i 对比，同一套扫描）**：
    | 指标 | 0.75（1010i） | 0.35（1010j） |
    |---|---|---|
    | 试盘漏斗：位置超限跳过 | 235 | **1322** |
    | 试盘漏斗：无试盘形态 | 2930 | 2009 |
    | 试盘漏斗：找到候选 | 416 | **250** |
    | └ 当日待确认 / 结构未走完 / 已确认 | 19 / 322 / **75** | 10 / 204 / **36** |
    | 库内 probe_ok=1 记录 | 7 | **5** |
    | 界面可见试盘文案行 | 7 | **5** |
    | 出货形态（含漏斗 5/0/111/116） | — | **完全一致，0 变化** |
    | 总记录 / 模式一 / 模式三 / 异常 | 230 / 191 / 39 / 0 | **230 / 191 / 39 / 0** |
    当前 5 只（全是模式一）与独立算出的 pos120：601~600826 兰生股份 0.2647、603229 奥翔药业 0.2779、301378 通达海 0.2874、300669 沪宁股份 0.3448、301558 三态股份 0.3480（**全部 < 0.35，最贴近门槛的是 0.3480**）。
  - 验证（1010j 新增两份，均在收紧后跑）：`tools\_verify_probe_pos35.py` → `tools\probe_pos35_verify.txt`（**10 PASS / 0 FAIL**：自动搜出的临界样本 pos 0.3481 放行 / 0.3549 拦下，正好夹住 0.35；把常量临时改回 0.75 后两者都被放行，证明差异来自本次改动；25 个常量逐项比对只有 `PROBE_POS_MAX` 一项不同）；`tools\_verify_probe_pos35_db.py` → `tools\probe_pos35_db.txt`（**10 PASS / 0 FAIL**：不调 `detect_probe`，直接从 `kline_cache` 独立重算 pos120 —— probe_ok=1 的 5 条全部 < 0.35；pos120 ∈ [0.35,0.75) 的 **98 条记录全部 probe_ok=0**；出货形态与总记录数逐项与旧日志一致）。
  - 验证：`tools\_probedist_unit.py` → `tools\probedist_unit.txt`（**50 PASS / 0 FAIL**，收紧后重跑仍全过，含造数三形态 + 六类反例 + 边界 + 分数分段 + 1920 组旧参数组合与 `.bak_before_probedist` 逐字等价 + 299 只真实数据上 `pos120`/`vol_ratio` 与手工计算逐只一致）；`tools\_probedist_dbui.py` → `tools\probedist_dbui.txt`（**30 PASS / 0 FAIL**，收紧后重跑仍全过：DB 56 列同序、5 列 230/230 全填、`probe_ok=1` ⟺ note 含「试盘观察」、离屏真实渲染 203 行里 **5** 条试盘 + 12 条出货形态文案可见、控盘列 31 条标签未被观察文案污染）。
  - 全市场扫描（`tools\run_scan_quiet.py` → `tools\_scan_after_probedist.log`（0.75 版）/ `tools\_scan_after_probe_pos35.log`（0.35 版））：两次都是 **5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**；0.35 版的试盘漏斗为 `通过K线门槛 3581 ｜ 位置超限 1322 ｜ 无试盘形态 2009 ｜ 找到候选 250（当日待确认 10 / 结构未走完 204 / 已确认 36）`。**230 条记录里试盘 5 条、出货形态 15 条（全是双顶雏形）**；日K建仓表默认只看「建仓触发 + 等待确认」，所以界面显示 **5 / 12** 条。
  - 性能：`detect_probe` **0.147 ms/只**、`detect_distribution_pattern` **0.194 ms/只**（全市场各 +0.7~1.0 秒）。
  - 回退：`copy /Y "strategy\base.py.bak_before_probedist" "strategy\base.py"` + `copy /Y "services\band_pattern_engine.py.bak_before_probedist" "services\band_pattern_engine.py"`，**回退后必须重跑扫描**。
- **控盘度 + 洗盘/出货判断（1010 新增）**：`strategy\base.py` 新增 `TechnicalIndicators.estimate_control_score()`（L278）/ `judge_wash_or_distribute()`（L363），修掉了原版的换手分量恒为 0（原版理论封顶 67.8 分）、下跌放量被加分、无阴线误判洗盘、出货条件过松四个缺陷。`services\band_pattern_engine.py` 接入（`_ALL_COLS` / `_save_or_update` 列清单+占位符 / `rec` 三处同步，缺一处字段就全 0）；`pattern_record` 由 42 列升到 **44 列**（`control_score` REAL / `stage_guess` TEXT）。提醒阈值 `_CTRL_HIGH = 85.0` / `_CTRL_CAND = 90.0`（L302-303），出货警示另有 `_CTRL_DIST = 60.0` 门槛（L305）；文案追加进 `note`。日K建仓表新增第 10 列「控盘」（`COL_D_CTRL`）：显示「分数·标签」（绿=候选 / 红=出货 / 橙=洗盘，无提示只显示灰色分数），悬停看完整文案。改这列要同步 5 处：列常量 `range(12)`／`HEADER_DAILY`／`DAILY_WIDTHS`／`make_table(12, ...)`／行映射 + `_daily_render_table` 响应单元格，少一处列就是空的。
  > 注意：`backups\backup_20261010_005808` 是在**加 `_CTRL_DIST` 出货门槛之前**打的快照。恢复它 = 没有出货门槛（出货提示会从 9 条回到 33 条）。要含出货门槛的还原点需重新 `python scripts\backup.py`。
- **控盘度已铺到全部个股列表模块**（后续新增）：`services\control_profile.py` 是全项目唯一控盘数据源，内部只调 `band_pattern_engine._ctrl_note`（阈值只在那一处定义），并只读本地 `kline_cache`、**不做网络兜底**（避免列表刷新卡 UI）。已接：自选评分、竞价筛选（今日竞价 + 竞价追踪）、今日涨停、分时做T、日K建仓、市场节奏·追踪、**市场节奏·主表（连板梯队内联）**、**市场节奏·可介入（单元格内联 + 独立「控盘」列）**，共 9 张表，列名统一叫「控盘」。
  - 基类工具：`ui\battle_widgets\base.py` 的 `fetch_ctrl_for(rows)`（后台批量算）、`fetch_ctrl_cached(rows)`（**只读已有缓存、零计算**，可在 UI 线程直接调）、`attach_ctrl(table, rows)`（填末列）、`BattleModuleBase.ctrl_async_fill(rows, on_done)`（异步补数）、`BattleModuleBase.ctrl_fill_and_async(rows, on_done)`（缓存即时填 + 后台补算 + 回调重绘）。新列一律加在**末尾**，所以要把原末列的 `stretchLastSection` 改成显式 Stretch 某一列，否则控盘列会被撑开。
  - **反复踩过的坑（控盘列整片变 `--`，已修）**：行对象常在**渲染前被重新装配**（快照恢复、持久化合并、初始恢复），取数时挂上的 `ctrl` 会丢掉。因此已在**每个渲染函数最顶部**加 `fetch_ctrl_cached(...)`（唯一能覆盖全部装配路径的位置）：`limit_up_widget._render_rows` / `auction_filter_widget._render_rows` / `atr_t_widget._render_hold_table` / `picks_track_widget._render` / `watchlist_panel._update_table`。新增渲染入口时必须同步补这一行。快照路径（休市复盘）还要跟一句 `ctrl_fill_and_async`，否则没人去算缺的。
  - `services\control_profile.py` 的 `get_ctrl_map(codes, cached_only=True)` 只返回已缓存条目、**绝不计算**，就是给 UI 线程用的。
  - 性能：首次约 28ms/只（本地 duckdb），同一交易日内缓存命中几乎 0。**必须在后台线程调**，不要在 UI 线程直接调。
  - **板块级表格（按题材成行）怎么接（2026-10-11 本批新增；「市场节奏」三 Tab 现已全部接入）**：`ui\battle_widgets\market_rhythm_widget.py` 的 Tab1「市场节奏」与 Tab2「可介入」都是**板块/题材成行、行对象没有顶层 code 字段**（行内个股在 `row['ladder']` / `row['picks']` 里），所以 `fetch_ctrl_for` / `fetch_ctrl_cached` / `attach_ctrl`（都按 `row['code']` 取码）套不上，改用「双落点」：① 单元格内联 —— Tab1 连板梯队里每只个股名后跟控盘短文本（`_ctrl_inline` → `88候选`），Tab2「可介入」里每只候选名后跟控盘分；② Tab2 新增独立「控盘」列（`P_CTRL` = 第 6 列），显示**该题材可介入候选里控盘分最高者**，悬停列出逐只候选的分数/阶段/位置。数据全部走 `get_ctrl_map(..., cached_only=True)`（UI 线程零计算），缺的由新增的 `MarketRhythmWidget._ctrl_async_fill()` 在后台算完再重绘两个 Tab。
  - 本批具体改动（`ui\battle_widgets\market_rhythm_widget.py`，662 行 → **885 行 / 35943 字符**，仍**纯 LF**）：Tab2 列数 6 → 7（`(P_BOARD…P_MEMBERS) = range(7)`、`P_HEADERS` 第 6 项用统一常量 `CTRL_COL_TITLE`、`P_GRID = [104, 46, 100, 150, 470, 104, 260]`（可介入列 340 → 470，否则内联控盘会被截断）、`make_table(len(P_HEADERS), P_HEADERS)` 不再硬写 6、`pick_sorter` 加 `P_CTRL: _top_ctrl_score`）；新增 8 个模块级控盘工具（`_ctrl_lookup` / `_ctrl_inline` / `_ctrl_one_line` / `_ctrl_pos_txt` / `_ladder_ctrl` / `_picks_ctrl` / `_top_ctrl` / `_top_ctrl_score`）+ 2 个类方法（`_all_stock_codes` / `_ctrl_async_fill`）；`_apply()` 末尾触发 `_ctrl_async_fill()`。**末列仍是 `P_MEMBERS`（成分股）**，`setStretchLastSection(False)` 的写法不变。
  - 验证：`tools\_verify_rhythm_ctrl.py` → `tools\rhythm_ctrl_verify.txt`（**33 PASS / 0 FAIL**，含真实股票独立重算交叉验证与离屏真实渲染逐格比对）；版式截图 `tools\_shot_rhythm_ctrl.py` → `tools\_shot_rhythm_tab1.png` / `_shot_rhythm_tab2.png`（**离屏无中文字体，中文显示成方块，只可判版式**）。
  - 仍未接入控盘：`leader_ladder_widget.py` / `sector_spike_widget.py` 代码在但**未挂到界面**（无任何地方实例化）。
  - `leader_ladder_widget.py` / `sector_spike_widget.py` 代码在但**未挂到界面**（无任何地方实例化），未接入。
- **创业板已放行（2026-10-10）**：用户可买创业板，原先全项目「只保留主板」的过滤已放开 300/301。改的 6 处（科创板 688/689、北交所 8xx/4xx/920 仍剔除）：
  - `services\band_pattern_engine.py`：`_is_main_a_share()`（日K建仓全市场扫描的**前置**过滤，位置在 `_load_bars` 之前，属性能优化，不要挪到后面）+ `scan_stock` 注释
  - `ui\battle_widgets\auction_filter_widget.py`：`MAIN_BOARD_PREFIXES`（竞价筛选，成交额/涨幅两条路径都走它）
  - `services\intraday_opportunity_engine.py`：`MAIN_PREFIX`（异动池 → anchor_tracker 基准阳跟踪的信号源）
  - `services\market_rhythm_engine.py`：`is_main_board()`（市场节奏；注意创业板 20cm，混入后「均涨幅」列会从约 10% 偏到约 15%，已在 docstring 标注）
  - `services\board_anomaly_engine.py`：2 处 `startswith(('60','00'))` → `('60','00','30')`（可介入 Tab）
  - `services\picks_tracking_service.py`：1 处同上（追踪 Tab）
  > 未改（不在线上链路）：`data\stock_list_provider.py _is_main_board_code`（只被 `strategy\main_force_behavior.py`、`strategy\nine_filter_strategy.py` 用）、`strategy\*` 下若干老选股模块、`ui\stock_screener_panel.py`（有「仅主板」复选框，属用户可选开关）。
- **创业板需要先灌 K 线缓存**：本地 `kline_cache.duckdb` 原为增量模式（只更新已在库代码，`INCREMENTAL_FETCH_DAYS=15`），创业板从未入库。不灌也能跑（`_load_bars` 会兜底在线抓取，实测 0.6 秒/只），但全市场扫描会多花十几分钟。灌法：**关掉主程序**后双击根目录 `灌创业板K线缓存.bat`（调 `tools\seed_cyb_kline.py`）。脚本直连主库写入，主库被占用时**报错退出**、不写备用文件（`KlineCacheDB._get_conn` 被锁时是静默转写备用文件的，这里刻意避开）。无历史数据的新股记进 `tools\_cyb_nodata.txt`，下次自动跳过。
  > 灌数据期间主库是写锁独占，主程序读本地缓存会失败并降级在线抓取（不崩，只是慢），所以要在程序关闭时跑。
- **竞价模块的创业板单独门槛（2026-10-10）**：`ui\battle_widgets\auction_filter_widget.py`（**纯 CRLF**）。门槛原先按主板口径调，直接套到创业板会把最强的高开信号砍掉（创业板开盘能到 +20%）。按「涨停幅度比 = 2.0」等比缩放，主板口径一字未动：
  | 项 | 主板 10cm | 创业板 20cm |
  |---|---|---|
  | 高开区间 | 2~7% | **4~14%** |
  | 竞价换手上限 | 15% | **30%**（下限 0.5% 不变，那是「有没有人交易」） |
  | 高开分满分区间 | 3~4% | **6~8%** |
  | 高开分次优区间 | 2~3% / 4~5% | **4~6% / 8~10%** |
  | 形态标签闸门 | gap 3 / 2 / 2.5 | **6 / 4 / 5** |
  实现：模块级 `CYB_PREFIXES` / `GAP_BAND_*` / `TURNOVER_MAX_*` / `GAP_SCORE_*` + `_is_cyb()` / `_gap_band()` / `_turnover_max()` / `_gap_score_bands()`；闸门在 `_fetch_auction`（新浪路径）与 `_fetch_tencent_rank`（腾讯兜底路径）两处，打分在 `_score_volume_price`（高开分 + 形态标签）。
  > 未改：`_enrich_with_themes` 的题材热度（`avg_gap/5.0`、强势判定 `gap>=2`）——题材是跨板聚合的，按板缩放会自相矛盾。
  > 已验证：高开 7% 时主板 18 分 / 创业板 30 分；主板各档分值与改动前逐档一致。备用回退 `auction_filter_widget.py.bak_before_cyb_gate`。
- **分时做T的创业板风控阈值（2026-10-10）**：`ui\battle_widgets\atr_t_widget.py`（**纯 CRLF**）。这个模块**没有板性过滤**（股票池 = 持仓 DB → 自选兜底，两条路都不过滤板性），但它有 3 处「个股当日涨跌幅」绝对值阈值是按 10cm 写死的，创业板会被误判：
  | 行 | 逻辑 | 主板 | 创业板 |
  |---|---|---|---|
  | `_apply_risk_and_signal` | 涨停锁仓、禁止卖出做T（涨停的 80%） | 8.0% | **16.0%** |
  | 同上 | 主升浪、谨慎卖出（涨停的 50%） | 5.0% | **10.0%** |
  | `_compute_theme_strength` | 弱势降分 `f -= 0.10` | -5.0% | **-10.0%** |
  改前后果：一只 +9% 的创业板股票（离 20% 涨停还有 11%）会被判「🚀 强势涨停锁仓，不做T」并 `blocked='sell'`，**禁止用户做T卖出**。
  实现：模块级 `CYB_PREFIXES` / `PCT_LOCK_*` / `PCT_MAINUP_*` / `PCT_WEAK_*` + `_is_cyb()` / `_pct_thresholds(code)`；`_apply_risk_and_signal` 里由 `r.get('code')` 取板性。
  > **大盘指数那两处不算**：`_check_market_sentiment` 的 `pct < -1.0` 与 `_check_daily_market_warn` 的 `pct < -2.0` 读的是上证指数（`1.000001`），与板性无关，保持不动。
  > 已验证：+9% 时主板判「锁仓」、创业板判「正常」；主板各档与改动前逐档一致。回退 `.bak_before_cyb_risk`。
- **今日涨停模块的板性判定本来就是对的**（2026-10-10 核查）：`ui\battle_widgets\limit_up_widget.py` 的 `_fetch_limit_up` 按 `code.startswith(('300','301','688','689')) → 19.5` / `('8','4','920') → 29.5` / `else → 9.8` 判涨停，不用改。
- **涨停原因库上游无板性过滤**（2026-10-10 核查）：`services\limit_up_collector.py` 与 `data\limit_up_reason_db.py` 都不含板性过滤，创业板涨停原因一直在采，「日K建仓」的题材列能查到创业板。所以市场节奏 L243 的 `is_main_board()` 放开后，涨停统计口径自然变成主板 + 创业板（均涨幅那一档从约 10% 抬到约 15%，用户已确认按此口径）。
- **涨停阈值口径：唯一来源 `band_pattern_engine._lu_threshold(code)`（2026-10-10 全项目反推排查后新增）**：主板 9.5% / 创业板·科创板 19.5% / 北交所 29.5%。日K建仓的「行业涨停家数 / 大盘涨停家数」改为按板判定（原来全市场统一 `x >= 9.5`）。实测 2026-10-09：旧口径 87 家 → 新口径 69 家，差的 18 家全是创业板 +10%~19.4% 的非涨停股（300340 +15.89%、300111 +14.81% 等）。这两个数喂给环境分与题材因子，会直接改等级与排序，所以这处属于**影响选股结果**的改动。
  > 反推排查时发现：**全项目「判涨停」的容差不统一**（日K建仓 9.5 / 今日涨停 9.8 / 自选与图表 9.8~19.8）。
  > **已决定不拉平（2026-10-10）**：这 0.3% 是历史遗留，实际影响可忽略（只影响「恰好落在 9.5~9.8 之间」的极少数股票）；拉平要动 `market_sentiment_panel` / `echarts_kline` / `watchlist_panel` / `limit_up_widget` / `utils\indicators` 的 base 共 5 处，而 `utils\indicators` 的 base 还被 `strategy\*` 老调用方依赖，收益（少一个常量）远小于回归风险。
  > **因此：9.5 家族 = 「引擎/统计」口径，9.8 家族 = 「面板/展示」口径，这是有意保留的两套**，不要再当成待办去「修」它。要动必须先跟用户确认。
  > `band_pattern_engine._is_limit_up()`（约 L155）是**死代码，全项目无任何调用**——模式一/二的基准日实际用「实体 >=3% 且涨幅 >=3%」判定，不要以为涨停条件在这里生效。
- **同期按板性改掉的展示类阈值（2026-10-10）**：`ui\watchlist_panel.py` 近20日涨停次数（约 L1365，主板9.8/创业板19.8）、`ui\trading_dashboard_panel.py` 仪表盘涨停·跌停家数（约 L519/L523）、`services\intraday_opportunity_engine.py` L553 过期注释。备份后缀统一 `.bak_before_cyb_lu`。
- **判涨停口径按板性已铺满（2026-10-10 第二轮修复，备份后缀 `.bak_before_cyb_lu2`）**：上一轮只改了日K建仓的环境截面，本轮把剩下的 5 处全部按板性改掉。统一规则是「主板 9.5/9.8、创业板 `300`/`301` 与科创板 `688`/`689` 用 19.5/19.8、北交所 30cm 未覆盖」：
  - **`services\picks_tracking_service.py`（纯 LF）—— 这一处会影响筛选结果**：新增模块级 `_lu_pct(code)`（主板 9.5 / 创业板·科创板 19.5），把 `if pct >= LIMIT_UP_PCT:` 改成 `if pct >= _lu_pct(code):`。改前创业板涨 +10%~19.4%（离 20% 涨停还差 8%）会被当成「已涨停 → 是龙头，不是介入标的」而**从可介入候选里剔掉**。注意这是**历史回填**口径，已入库的历史候选仍是旧口径算的，要重跑得执行 `python services\picks_tracking_service.py --backfill`（会重写 `picks_tracking.duckdb`）。
  - `ui\market_sentiment_panel.py`（纯 CRLF）：新增 `PLUS_PREFIXES` + `limit_pct(code)`（9.8 / 19.8）。**改前板性分支是写反的** —— `if code.startswith('6') or code.startswith('0')` 的前缀 `'0'` 会把创业板 300/301、`'6'` 会把科创板 688 一起吞掉，导致 `elif code.startswith('3') or code.startswith('68')` **永远执行不到**；涨停/跌停/炸板三个家数对创业板全是错的。现在涨停与跌停共用 `_lp`，炸板下沿按板取（主板 7%、创业板 14%），主板三档行为与改前逐档一致。
  - `ui\echarts_kline.py`（纯 CRLF）：JS 写在**模块级常量 `ECHARTS_HTML`** 里（不是 f-string），所以做法是 Python 侧在 `set_kline_data` 调用 `updateKline` 之前先设 `window.__limitPct`（阈值由 `kline_data['code']` 取板性），JS 侧 `var luPct = ... || 9.8` 读它。
  - `ui\watchlist_panel.py`（纯 CRLF）：`KlineChartWidget.set_kline_data(kline_data, code='')` 新增了 `code` 参数（默认 `''`，旧调用方式仍可用），`paintEvent` 里预算 `_lu_pct`。调用方 `_on_kline_data_ready(self, kline, code, name)` 已补传。**改这个组件时注意 `code` 是新增参数**。
  - `services\intraday_opportunity_engine.py`（纯 LF）：追高提示文案两档 `5% / 3%` → 按板 `10% / 6%`（`_chase_hi` / `_chase_mid`），纯文案。
- **第三批：9.1 那 4 处线上残留也修了（备份后缀 `.bak_before_cyb_lu3`，4 文件 / 14 处，全部纯 CRLF）**：前七节审计只覆盖了 13 组主链路，`tools\_final_sweep.py` 全项目扫描（175 行命中）后又揪出 4 个文件在线上、但漏改的。这几个都**不影响**日K建仓 / 竞价 / 市场节奏 / 可介入四条主链路，只影响统计数字与提示文案：
  - 统一做法：模块顶层加 `_lu_pct(code)`（主板 9.5 / 创业板·科创板 19.5 / 北交所 29.5），使用点全换成它。
  - `ui\battle_console_v2.py` L3779：`if pct >= 9.5:` → `_lu_pct(code)`（「接近涨停，注意连板炸板风险」提示；`code` 来自 `for code in codes:`，作用域内已有）。
  - `services\v22_combat_service.py` L681/L682/L856/L857/L1054：市场温度与交易时段统计里的涨停·跌停家数、板块内涨停数。
  - `services\daily_close_summary_service.py` L159/L224/L225：收盘总结的「昨日涨停股今日表现」取材范围 + 涨跌停家数。
  - `utils\indicators.py` L332-L348：`calc_limit_up_count()` / `is_yesterday_limit_up()` **新增可选参数 `code=None`**，内部用 `_lu_pct(code, base=9.8)`；**code 为空时原样返回 base(9.8)**，所以 `strategy\stock_pool_v1.py` / `strategy\quant_scoring.py` 等老调用方**一行没改、行为逐位不变**。将来要按板判，传 `code=` 即可。
  > **本次最重要的安全性质**：三个「9.5 家族」文件的 `_lu_pct(None)` / `_lu_pct('')` 都返回 **9.5**，即**字典里没有 `code` 键时行为等于改前**。所以即使某条行情路径的 dict 结构与预期不符，最坏也是「等于改前」，不会变形。有单测。
  > 验证：`tools\_verify_lu_scope_fix2.py`（**54 项，0 失败**），含「从磁盘抠出真实代码行在合成样本上 exec」与真实 import 调用。
  > 剩余未统一：**9.5 与 9.8 这 0.3% 的历史容差 —— 已决定不拉平**（见上面「涨停阈值唯一来源」那条的理由），这是有意保留的两套口径，不是待办。
  > **北交所 30cm 在第二批两个函数里有意不覆盖（2026-10-10 决定）**：`picks_tracking_service._lu_pct` 的候选本来就只取 `60/00/30` 开头（北交所进不来），`market_sentiment_panel.limit_pct` 只分 9.8/19.8 两档；而用户**不买北交所**、全项目已把 8xx/4xx/920 剔除。补它收益≈0、只会增加回归面，故保持「与改前一致、无回归」。第三批那三个 `_lu_pct` 覆盖 29.5 是因为它们本来就要覆盖全市场家数统计。
  > `market_sentiment_panel` 里 `is_limit_up` 是**只写不读的死变量**，保留原样未删。另注：`band_pattern_engine._is_limit_up()` 也是死代码（全项目无调用）。
  > **确认不动**：`strategy\*` 下约 40 行（老选股模块，不在四模式链路）、`market\mock_api.py` / `test\*` / `tools\*` 约 30 行、`ui\battle_widgets.backup_2026*\` 历史备份约 40 行。其中 `strategy\limit_up_radar.py` L36-L42 **已经写对了**（9.5 / 19.5 按板判）。
- **第四批：创业板在「可介入」历史回填里完全不存在（真 bug，已修，备份后缀 `.bak_before_cyb_backfill`）**：准备重跑 `--backfill` 时读代码发现的，**不在前九节审计范围**。
  - 问题：`services\picks_tracking_service.py` 有两条候选路径，板性过滤不一致 —— 当日引擎 L438 `startswith(('60','00','30'))` **含创业板**（创业板放行那批改的），但**回填** `backfill_history()` 的取数 SQL **L505** 还是 `WHERE code LIKE '60%' OR code LIKE '00%'`。SQL 在 L537 的 `pct >= _lu_pct(code)` **之前 20 行就执行**，所以创业板根本进不到候选 → **第二批为这个文件做的按板性修复，在回填路径上对创业板是白改**。
  - 改法：L505 加 `OR code LIKE '30%'`（一行）。688/689/8xx/920 仍排除，与全项目一致。
  - 实测：`picks_tracking.duckdb` 4803 行（主板 4803 / **创业板 0**）→ 回填后瞬时 **5901 行**（主板 5201 / 创业板 700）→ **主程序清理后稳定态 5603 行**（主板 4966 / **创业板 637**），耗时 8.5 秒。
  - **为什么有「瞬时 / 稳定态」两个数（重要，别的 AI 看到别当成数据不一致）**：`TRACK_KEEP_DAYS = 100`（自然日，L54），L202/L203、L264/L265 与 `ui\battle_widgets\picks_track_widget.py` L371 都会 `DELETE ... WHERE trade_date < CURRENT_DATE - 100 DAY`。回填最早插到 06-26，而 2026-10-10 往前 100 天 = 07-02 → **刚插进去的 06-26~07-02 那段被正在运行的主程序剪掉**，库内最早日期现在正好是 07-03。属预期行为，不是 bug。
  - 主板净增 163 行（同在 07-03~10-09 内），来自涨停库新增数据让更多股票被算作「板块活跃标的」，不是口径变化。
  - **`backfill_history()` 是纯 INSERT + 遇到已存在 (日期,代码) 就跳过，不删不改老数据**（所以「重跑回填」本身非破坏性，但仍先做了库文件级备份 `picks_tracking.duckdb.bak_before_cyb_backfill`）。
  - 胜率基本不动（在稳定态 5603 行上算）：5日 41.0%→41.6%、30日 43.7%→43.9%、累计 35.5%→35.2%。加入 637 条创业板样本后**没有把这个信号拖差或变好**，但样本从「主板单一来源」变成「主板 + 创业板」。
  - 验证：`tools\_verify_all_batches.py` 第五节（含库内实际条数）。
  > 注意 `LIMIT_UP_PCT = 9.5` **是活常量**：`_lu_pct()` 内部主板分支就 `return LIMIT_UP_PCT`，且 `tools\_check_rhythm_doc.py` L65 还在断言它等于 9.5 —— 别当残留删掉。
- **「可介入」门槛收紧：涨幅上限 9.0 → 5.0（2026-10-10，实测驱动，备份后缀 `.bak_before_tighten`）**：门槛在**两个文件里各写一份**，必须同改 —— `services\picks_tracking_service.py` L49 `PICK_MAX_PCT`（回填/追踪路径）+ `services\board_anomaly_engine.py` L72 `_PICK_MAX_PCT`（当日引擎 / 可介入 Tab）**都纯 LF**。只改一处就会重演「两条路候选口径分叉」的老 bug。
  - 依据 `tools\_sweep_pick_thresholds.py`（5603 条真实样本，口径 = 程序自身 `fetch_tracking`，win = 收益 > 0），涨幅上限 9/8/7/6/5% 对应 5日胜率 **41.6 / 41.7 / 41.8 / 42.3 / 43.1%**、30日 **43.9 / 44.3 / 44.7 / 45.4 / 45.7%**、累计 **35.2 / 35.4 / 35.9 / 36.6 / 38.0%**，单调上升。
  - **反直觉、别再试（数据已否掉）**：量比下限**不能提**（1.2→41.6% 到 3.0→35.9%，单调**下降**）、价格下限**不能提**（6元 41.6% → 15元 40.4%，累计 28.2%）、涨幅下限**不能提**（1.0→41.6% 到 4.0→39.5%）。想再提高只能改「选什么、什么时候选」这个信号本身，不是改门槛。
  - 重建样本：`tools\_run_backfill_tighten.py`（先备份库 → **只删 `base_source='BACKFILL'` 行、保留 78 条 REALTIME** → 重跑回填）。库 5603 → 2980 行（主板 2253 / 创业板 448）。
  - **实际前后（同一套 `summarize` 口径）**：5日 41.6% → **42.9%**（n 5440 → 2636）、30日 43.9% → **43.5%**、累计 35.2% → **35.3%**。也就是**只有 5日改善约 1.3pt、在噪声范围内（SE≈1.2pt），30日/累计基本持平**。这是真实测量结论，别对外说成「胜率提升了」。
  - 已知小瑕疵：库内 7 行（0.26%）`pct0` 恰好 = 5.0 —— 是**入库时四舍五入**（真实 pct 为 4.995~5.0，判定用未舍入值），不是过滤失效。核对脚本 `tools\_check_picks_over.py`。
  - 回退：`copy /Y` 两个 `.bak_before_tighten` 源码 + `copy /Y "data\cache\picks_tracking.duckdb.bak_before_tighten" "data\cache\picks_tracking.duckdb"`。
- **MA20 门槛：两处本来就有，本次堵掉唯一的洞（2026-10-10，备份后缀 `.bak_before_ma20gate`）**：
  - 现状核查结论：**「可介入/追踪」的入选门槛含「现价 ≥ MA20」是早就有的**，两条路都在 —— 当日实盘 `services\board_anomaly_engine.py` `_pick_candidates`（原 L341-345）与历史回填 `services\picks_tracking_service.py` `backfill_history`（L545-546 `if ma20 > 0 and close < ma20: continue`）。`persist_picks`（当日写入追踪表）吃的就是 `_pick_candidates` 的产物，所以两条入库路都被门槛管着。MA20 来源 `board_anomaly_engine._load_ma20()`：kline_cache 最近 20 个收盘均值（要求 ≥20 根），600 秒缓存。
  - **唯一能绕过的地方（已堵）**：当日路径原来写的是 `if m20:` —— **取不到 MA20 就直接放行**，所以 K 线不足 20 根的次新股能混进来。改成「MA20 整表非空时按硬门槛：跌破剔除、**表里没有它也剔除**（无法确认站上均线）」。
  - **特意保留的兜底**：`ma20` 整表为空（kline_cache 被占用/加载失败）时**不做过滤**——否则一次读库失败就会把候选清空，那比漏几只次新严重得多。这条写进注释了，别当 bug 改掉。
  - **追踪表新增「距MA20%」列**（`ui\battle_widgets\picks_track_widget.py`，**实测是纯 LF**）：插在「当前价」后面，`T_NOW=5 / T_M20=6 / T_R5=7 / T_R30=8 / T_CUM=9 / T_CTRL=10`，`TRACK_COL_N=11`，`TRACK_WIDTHS` 同步 11 项。`fetch_tracking` 新增返回字段 `'ma20'`（本地 K 线最近 20 收盘均值，不足 20 根给 None → 显示 `--`）；该列跟随 3 秒实时价刷新（MA20 当日不变）。改这个表要同步 5 处：`TRACK_HEADERS` / `TRACK_COL_N` / `range()` 解包 / `TRACK_WIDTHS` / `_render` 行映射 + `HeaderSorter` 的 keys。
  - 验证：`tools\_verify_ma20_gate.py`（**21 项 / 0 失败**），含「恰好等于 MA20 应通过」「表里没有应剔除」「整表为空应放行」与离屏渲染真实单元格。
  - 回退：`copy /Y "<file>.bak_before_ma20gate" "<file>"`（三个文件各一份）。
- **竞价模块的「控盘」列为什么几乎不亮（2026-10-10 诊断，结论：不是数据异常）**：`tools\_diag_auction_ctrl.py` 实测（走 UI 同一条 `control_profile.compute_one`）：
  | 样本 | 只数 | 算得出分 | 显示 `--` | 控盘中位数 | ≥85 占比 |
  |---|---|---|---|---|---|
  | 今日竞价快照（09-30） | 27 | **27** | 0 | 46.3 | 7.4% |
  | 竞价追踪库 | 52 | 49 | 3（003026/003006/003001 无 K 线） | 45.3 | 10.2% |
  | 全市场随机 200 只 | 200 | 200 | 0 | **76.6** | **32.0%** |
  结论：**数据没坏**（27 只全部算得出分，显示的是灰色分数不是 `--`），但**命中提示只有 2/27、4/52**，远低于全市场 32%。原因是**口径不匹配**：控盘分里换手中枢与振幅是负向项（`turnover_score = 100 - 换手×8`、`amp_score = 100 - 振幅×300`），而竞价筛出来的就是「当天高开放量」的票 —— 换手高、振幅大，分数天然被压低。**不是阈值 85/90 失效，也不是渲染断了**。想让竞价这一列有意义，得为它单独定口径（别直接把 85/90 套上去），改之前先问用户。
- **`strategy\ai520_*` / `ai_520_engine.py` / `ai_520_scan_service.py` 里写死的 9.8% 不要去修**——AI520（选股雷达）早已下线，改它们没有意义。
- **三轴状态闸门**：`services\regime_gate.py`（温度/趋势/集中度），已接进日K建仓 + 市场节奏。
- **震仓四项提纯**：`_shake_factors()`，横盘周K 建仓触发要求 4 项全过（`_SHAKE_MIN_OK = 4`）。
- **属性词剔除**：市场节奏不再把「国资 / 半年增长」这类属性词当题材。
- **三模块合并**：「盘中机会 + 金铲子 + 板块异动」→ 单一 **📈 市场节奏**（三 Tab：市场节奏 / 可介入 / 追踪），旧界面与金铲子辅助已删（含 `atr_t_widget` 内 163 行死代码）。
- **涨停库采集链路修复**：新增 `services/limit_up_collector.py`，并挂进 `盘后扫描_波段四模式.bat` 第一步；补回停更 9 天的涨停原因数据。
- **`main.py` 新增异动检测后台线程**（只喂 `anchor_tracker`，无界面），保住盘后「基准阳跟踪 / 日K建仓」的信号源。
- 更早（0926 起）：**模式三（底部横盘）+ 模式四（周K确认）合并**为单一「横盘周K」，占用 `pattern_id = 3`（`PATTERN_WEEKLY = 4` 已删除）。规则：本周量 ≥ 上周量×1.3 且收阳 → 横盘窗口 8~40 日（振幅≤25%、低点抬高、后半段均价抬高、上涨日≥1.3 倍至少 1 次、下跌日≤1.0 倍满足率≥55%）→ 本周收盘 > 结构上沿；**移除聚宽(JoinQuant)回测**（5 个文件）；**主板/ST 过滤前置**修复扫描性能；9/25 节假日日历修复。

**1010m 稳定版（最新）**：`backups\backup_20261011_112723`（1212 文件 / 70.8 MB，2026-10-11 11:27，**含拉升位置门槛 `MARKUP_POS_MAX=0.45`**，功能最全）
**1010l 快照（1010m 的起点）**：`backups\backup_20261011_111222`（1203 文件 / 67.9 MB，2026-10-11 11:12，**= 1010l 状态、不含位置门槛**）
**1010l 稳定版**：`backups\backup_20261011_105720`（1188 文件 / 64.9 MB，2026-10-11 10:57，**新增拉升阶段识别 `_MARKUP_NOTE_MODE='watch'`**）
**1010k 稳定版**：`backups\backup_20261011_101025`（1174 文件，2026-10-11 10:10，**新增规则① 洗盘文案降级 `_WASH_NOTE_MODE='off'`**，功能最全）
**1010j 稳定版**：`backups\backup_20261011_080651`（1168 文件 / 64.6 MB，2026-10-11 08:06，**试盘位置门槛收紧到 0.35**）
**1010i 稳定版**：`backups\backup_20261010_225841`（1168 文件 / 64.6 MB，2026-10-10 22:58，试盘识别 + 出货形态确认，**试盘 pos 上限还是 0.75**）
**1010h**：`backups\backup_20261010_224708`（1158 文件 / 61.5 MB，C6 + ctrl_tag 修复，**不含**试盘/出货形态）
**1010g**：`backups\backup_20261010_224203`（1158 文件 / 61.5 MB，同 1010h，另一份）
**1010f**：`backups\backup_20261010_222816`（1141 文件 / 61.1 MB，C4 落盘后，不含 C6、不含 ctrl_tag 修复）
**1010e**：`backups\backup_20261010_220829`（1130 文件 / 60.9 MB，C4 落盘前）
**1010d 稳定版**：`backups\backup_20261010_215843`（1125 文件 / 48.8 MB，建仓因子落盘后 / B 任务前）
**1010c**：`backups\backup_20261010_211620`（1106 文件 / 45.4 MB，建仓因子落盘前，含 C1~C5）
**1010b**：`backups\backup_20261010_205553`（1094 文件 / 39.7 MB，C3/C5 落盘前）
**已被自动清理（磁盘上没有了）**：`150427`（1010c 旧）、`145546`（三批修复）、`134550`（控盘列+创业板放行）、`005808`、`20261009_172437`、`20260926_203651`、`20260924_170012`、1010 旧基线 `20261010_153652`（1069 文件 / 28.4 MB，2026-10-10 15:36，打 1010j 时被挤出），**以及 1010a `backup_20261010_193113`（1082 文件 / 34 MB，C1/C2 落盘前）—— 打 1010k 快照时被挤出前 10 名，已删除**，**以及 1010b `backup_20261010_205553`（1094 文件 / 39.7 MB，C3/C5 落盘前）—— 打 1010l 快照时被挤出前 10 名，已删除**。

### 用户说这些话时，就是要恢复到上面这个版本

用户说**任意一句**（或意思相近的说法），即执行恢复：

- **「回滚到稳定版」**
- **「恢复到 1010 稳定版」**
- **「回滚到 1010」**
- **「用 1010 的备份还原」**
- **「回到上次备份那个版本」**

> 注意：说「回滚到稳定版」= 最新快照 **`backup_20261011_112723`**（= **1010m 版**），含控盘/建仓因子/C1~C6/ctrl_tag/试盘/出货形态 + 试盘 pos 门槛 0.35 + 洗盘文案降级 + 拉升阶段识别 + **拉升位置门槛 pos<0.45**，**全部改动都含**。
> **只想丢「拉升位置门槛」→ 把 `MARKUP_POS_MAX` 改回 `1.01`**（或走 #2 `backup_20261011_111222`，那份是 1010l 状态），不用整体回滚；**只想让它不出文案（保留字段）→ 把 `_MARKUP_NOTE_MODE` 改 `'off'`**，也不用回滚。
> 只想丢「拉升阶段识别」这一批 → 走 **1010k**（`backup_20261011_101025`）。
> 只想丢「洗盘文案降级」这一批 → 走 **1010j**（`backup_20261011_080651`）。
> 只想丢「试盘 pos 门槛 0.35」这一批 → 走 **1010i**（`backup_20261010_225841`）。
> 只想丢「试盘识别 + 出货形态确认」这一批 → 走 **1010h**（`backup_20261010_224708`）。
> 只想丢「C6 + 控盘标签修复」→ 走 **1010f**（`backup_20261010_222816`）。
> 想回到「有控盘度、没有 C4/C6/试盘/出货形态」→ 那份 1010a（`backup_20261010_193113`）**已被自动清理，磁盘上没有**，只能走 Git 或退到 1010c（`backup_20261010_211620`，含 C1~C5、无 C4/C6）。
> 想丢掉控盘度 + 三轴闸门 + 提纯震仓、只保留三模块合并那版 → 那份 1010 旧基线（`backup_20261010_153652`）**已被自动清理，磁盘上没有**，只能走 Git。

如果用户明确说 **「回滚到 1009」** / **「恢复到 1009 稳定版」**，那份快照**已被自动清理**（磁盘上没有），1010 旧基线 `backups\backup_20261010_153652` 也已在打 1010j 时被删除，**只剩 Git 一条路**：`git reset --hard f2d3bcd`（0924 版）。
如果用户明确说 **「回滚到 0926」** / **「回滚到 0924」**，同样**已被清理**，只能走 Git `git reset --hard f2d3bcd`（0924 版）。

### 恢复怎么做

```powershell
cd D:\QuantMonitorV6
python scripts\restore.py --list                       # 先确认编号
python scripts\restore.py --pick <编号> --yes           # 恢复（覆盖前会自动备份当前状态）
```

`restore.py` 按名字倒序：

| 编号 | 快照 | 说明 |
|---|---|---|
| 1 | `backup_20261011_112723` | **1010m（当前默认回滚目标）· 全部改动都含**（新增：拉升位置门槛 `MARKUP_POS_MAX=0.45`） |
| 2 | `backup_20261011_111222` | 1010l 状态 · **不含**拉升位置门槛（1010m 的起点快照） |
| 3 | `backup_20261011_105720` | 1010l · 含拉升阶段识别 `_MARKUP_NOTE_MODE='watch'` |
| 4 | `backup_20261011_101025` | 1010k · 洗盘文案降级 `_WASH_NOTE_MODE='off'` |
| 5 | `backup_20261011_080651` | 1010j · 试盘 pos 门槛收紧到 0.35（**洗盘文案还在**） |
| 6 | `backup_20261010_225841` | 1010i · 试盘识别 + 出货形态确认（试盘 pos 上限仍是 0.75） |
| 7 | `backup_20261010_224708` | 1010h · C6 + ctrl_tag 修复，不含试盘/出货形态 |
| 8 | `backup_20261010_224203` | 1010g · 同 1010h（另一份） |
| 9 | `backup_20261010_222816` | 1010f · C4 落盘后，不含 C6 |
| 10 | `backup_20261010_220829` | 1010e · C4 落盘前 |

> 1010a `backup_20261010_193113` 与 1010 旧基线 `backup_20261010_153652` 都已被挤出前 10 名删除，**此处已无对应行**；**1010c `backup_20261010_211620` 在打 `20261011_111222` 时被挤出**，**1010d `backup_20261010_215843` 在打 `20261011_112723`（本次）时被挤出，磁盘上都没有了**。

> **每打一份新快照，这个表所有编号都要 +1**（`restore.py` 按名字倒序编号；只保留最近 10 份，第 11 份起会被自动删除）。
> 不确定就先用 `python tools\_verify_snapshot.py` 打印一份最新编号表。

**恢复后必须重启主程序**。

也可以走 Git：`git reset --hard f2d3bcd`（回到 0924 版）。

> `restore.py` 只覆盖备份目录里**已有**的内容（20 个代码目录 + main.py），不会删除项目里其他文件。
>
> **注意快照内的 AGENTS.md 可能比项目里这份旧一版**（备份是在文档更新前打的，自指没法自洽）。
> 判断「当前默认回滚目标」以**项目里这份 AGENTS.md 和磁盘上 `backups\` 里最新的 `backup_*` 目录**为准，
> 不要只看快照内部那一份。

---

## 改代码时必须注意

- **行尾符**：`ui\battle_console_v2.py`、`main.py`、`ui\battle_widgets\atr_t_widget.py`、`ui\battle_widgets\auction_filter_widget.py`、`ui\battle_widgets\limit_up_widget.py`、`ui\watchlist_panel.py`、`ui\trading_dashboard_panel.py`、`ui\echarts_kline.py`、`ui\market_sentiment_panel.py`、`services\v22_combat_service.py`、`services\daily_close_summary_service.py`、`utils\indicators.py`、`services\control_profile.py`、`strategy\base.py`（**1712 行，纯 CRLF**）、`盘后扫描_波段四模式_自动.bat`、`utils\http_market_data.py`、`灌创业板K线缓存.bat`（**GBK 编码**）是**纯 CRLF**；`services\intraday_opportunity_engine.py`（2028 行）、`services\band_pattern_engine.py`（**2074 行**）、`scripts\backup.py`、`scripts\restore.py`、`utils\trade_calendar.py`（461 行）、`tools\run_scan_quiet.py`、`services\concept_matcher.py`、`market_analysis\market_sentiment.py` 是**纯 LF**。改文件前先检测，多行锚点必须先 `\r\n → \n` 标准化，写回时转回原行尾，否则 `assert s.count(old)==1` 会命中 0 次。
- **改文件方式**：先 `shutil.copy2` 备份 → `assert s.count(old)==1` → 替换 → 写回 → `py_compile` 验证。
- **不要凭印象改**：必须实际定位到行号再改。用户反复强调「要实际找到代码位置，而不是敷衍我随便改改就说任务完成」。
- **改完要验证**：`py_compile` + 真实实例化（`_verify_radar_removed.py` 可离屏启动主窗口），并给出实际改动文件、行号、验证结果。

## 🎛 控盘选股页（2026-10-11 新增；独立页面，不改扫描逻辑）

以「控盘度」为主线单独开一个 Tab 筛全市场，不再把「控盘」列往已有表格里塞。

- **新增文件**：`services\control_screen_service.py`（服务，15776 字节）、`ui\battle_widgets\control_screen_widget.py`（页面，20761 字节）、`data\cache\control_screen.json`（扫描快照）。
- **挂载点**：`ui\battle_console_v2.py`（纯 CRLF，7068 → **7090 行 / 384447 字节**）两处 —— L6577 起创建 `self.ctrl_screen_page` 并 `addTab(..., '🎛 控盘选股')`（try/except 降级占位）、L6722 起连接 `stock_clicked → _show_stock_detail`。备份 `ui\battle_console_v2.py.bak_before_ctrlscreen`（382888 字节）。**需重启主程序才可见**。
- **口径全部复用唯一来源**：控盘分 / 阶段 / pos120 与 `services\control_profile.compute_one` 逐字一致（阈值只在 `band_pattern_engine` 一处定义），观察文案走 `_ctrl_note`，短标签走 `ctrl_label`。页面自己**不新造任何阈值**。
- **只读、不写库**：`data\cache\kline_cache.duckdb` 用 `read_only=True` + 一条 SQL 批量取每只最近 120 根；扫描前后 `band_pattern.db` / `kline_cache.duckdb` 字节与 mtime 均未变（有断言）。
- **股票池**：`60/00/30`（主板 + 创业板），剔 `688/689/8/4/920`；K 线不足 60 根跳过。
- **10 列 → 11 列（2026-10-11 加「涨停题材」）**：股票名称 / 代码 / 现价 / 涨跌幅 / **涨停题材** / 控盘分 / 阶段 / 位置 / 控盘提示 / 观察 / 数据日。阶段 = 出货/洗盘/—；位置 = pos120（<0.25 显示红）；控盘提示 = 短标签（绿候选/红出货/橙洗盘）+ tooltip 全文；观察 = 试盘 / C4 / C6 / 出货形态 / 拉升（可过滤）。
  - **涨停题材列**：按用户口径走 `data.limit_up_reason_db.get_last_limit_up_reason(code)`（最近一次**含「+」**的涨停原因），与「日K建仓」`atr_t_widget.py` L1860-1881 / L2115-2121 **同一来源、同一显示风格**（紫色 `#6a1b9a`、左对齐、空显示 `--`）。service 里新增 `limit_up_theme(code) -> (reason, date, lbc, ind)`（纯函数，异常一律返回空），`compute_stock` 的 rec 加 4 个字段（`theme` / `theme_date` / `theme_lbc` / `theme_ind`，默认空），**由 `scan_market` 逐只填**（4400 只约 1.2 秒），并计入 `stats['theme_ok']`。tooltip `_theme_tip()` 给「题材 + 最近涨停日 + 连板」（`industry` 在 ths 来源里基本为空，非空才显示）。**拉伸列由「观察」改成「涨停题材」**（题材串最长，如「参股算力建设（金额较小）+工程咨询+AI应用+甘肃国资」），观察列固定 190px。
  - **改这一列要同步 5 处**（漏一处列就是空的）：列索引元组 `(C_NAME…C_DATE) = range(11)`、`PAGE_HEADERS`、`PAGE_WIDTHS`、`sorter.keys`（新增 `C_THEME`）、`_render`。
  - 实测（2026-10-11 重扫）：**4416 只 / ok 4404 / theme_ok 3107（70.5%）**；控盘≥85 排出货 **993 只其中有题材 768 只（77.3%）**。库内没有含「+」题材的股票显示 `--`（如 301029 怡合达、301309 万得凯）。
  - ⚠ 旧快照（本次重扫之前）没有这 4 个字段，页面会整列显示 `--` —— 必须重跑扫描（`python tools\_rescan_ctrl_screen.py`，26 秒，写快照）或点页面「开始扫描」。
- **条件栏**：控盘分≥（默认 85）/ 位置≤（默认不限，可选 0.65/0.45/0.25）/ 排除出货（默认勾）/ 价格≥6元（默认勾）/ 剔除ST（默认勾）/ 观察下拉 / 打开页面自动扫描（默认勾，每个进程只跑一次）/ 开始扫描 / 导出代码；点名称或代码跳个股分析。
- **实测（2026-10-11）**：批量读库 52.9 万行 / 1.15 秒；全市场 **4416 只 / ok 4404 / skip_bars 12 / fail 0 / 22~25 秒**；**控盘≥85 排出货 = 993 只**（位置≤0.25 → 760；控盘≥90 → 259；≥95 → 472）。
- **验证（可重跑）**：`tools\_ctrl_screen_unit.py` → `tools\ctrl_screen_unit.txt`（**43 PASS / 0 FAIL**，含与 `compute_one` 抽样 250 只逐只一致、**题材 6 项**：字段类型 / 含「+」/ `theme_ok` 对账 / 抽样 30 只与 `get_last_limit_up_reason` 逐字段一致 / 无漏网、边界 85.0/84.99 与 0.4499/0.4501 与 6.0/5.99、导出、快照、扫描不改库）；`tools\_ctrl_screen_dbui.py`（需 `QT_QPA_PLATFORM=offscreen`）→ `tools\ctrl_screen_dbui.txt`（**45 PASS / 0 FAIL**，真实快照 993 行渲染、前 15 行 × 11 列逐格 + 颜色 + tooltip、**题材列专项 C6~C9**（文本/紫色/`--`/左对齐/宽度）、条件联动、点击发信号、排序、addTab 离屏、导出全链路）；截图 `tools\_shot_ctrl_screen.py`（`QT_QPA_PLATFORM=windows`）→ `tools\_shot_ctrl_screen.png`（中文可读；offscreen 中文成方块）。
- **回退**：`copy /Y "ui\battle_console_v2.py.bak_before_ctrlscreen" "ui\battle_console_v2.py"`（重启主程序）；彻底移除再删这三个新文件。只回退「涨停题材」：`copy /Y "services\control_screen_service.py.bak_before_theme" "services\control_screen_service.py"` + `copy /Y "ui\battle_widgets\control_screen_widget.py.bak_before_theme" "ui\battle_widgets\control_screen_widget.py"`（**回退后重跑扫描**，否则快照里的题材字段与页面列数不匹配）。
- 一次性补丁（**勿重跑**）：`tools\_apply_ctrl_screen_theme.py`；可重跑：`tools\_rescan_ctrl_screen.py`。
- **11 列 → 13 列（2026-10-11 本轮加「主营收入」「最新公告」两列；纯展示，不参与筛选/排序权重）**：股票名称 / 代码 / 现价 / 涨跌幅 / 涨停题材 / **主营收入** / 控盘分 / 阶段 / 位置 / 控盘提示 / 观察 / **最新公告** / 数据日。两列都**不重跑扫描**（不改 DB、不改快照）。
  - **数据源与口径**：主营 = `utils\main_business_service.fetch_main_business_composition`（东财 F10，按日文件缓存），取**占比最高的那一项**显示成「名称 营收」（如「智能终端 65.80亿」）；公告 = **最近 1 条**，单元格显示「MM-DD + 标题」、tooltip 给来源 + 最近 3 条 + 链接，取数链 **东财公告接口 → 新浪财经公告页 → 巨潮 provider**。
  - 缓存 `data\cache\ctrl_screen_extras.json`（`load_extras`/`save_extras`，含 `saved_at`+`items`）；TTL：主营 30 天 / 公告 6 小时（空结果 1 天 / 2 小时）。**两列不进 25 秒的全市场扫描**（4400 只联网要十几分钟）→ 「缓存优先 + 切到本页/扫描完成后后台并发补」，补数开关 `_ck_extra`（默认勾选）。
  - **⚠ 本轮最重要的实测发现（别忘）**：第一次全量补（978 只 / 61 秒 / 约 16 req/s）把上游**撞成风控** —— 东财公告接口在约 500 次请求后对 IP 返 **HTTP 567**（HTML 挑战页，2 分钟未恢复），后 478 只全被记成「公告为空」；巨潮 `hisAnnouncement/query` 同批返 **403**（连当天早些能出的 000779 也 403）；同花顺 len=0；东财 datacenter 三个 reportName 全「报表配置不存在」。**新浪 `vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/<code>.phtml` 未受影响**（GBK HTML、`日期&nbsp;<a href=…>标题</a>` 连排）→ 已作为次源。重补后**公告来源分布 = 东财 500 / 新浪 478**，正好复现风控分界。
  - 为此服务层做了四件事（都在 `services\control_screen_service.py`）：① **公告三源降级链** `fetch_ann_em`（显式判 `status_code != 200 → None`）→ `fetch_ann_sina`（正则 `_SINA_ANN_RE`、`r.encoding='gbk'`）→ 巨潮 provider（**要有 orgId 才算「有效响应」**）；`fetch_ann` 返回**三元组 `(list, 源名, ok)`**，`ok=False` 才算「上游没响应」，与「上游确认无公告」（`[]` + ok=True）严格区分。② **按主机桶限速** `_throttle(bucket, interval)`：公告 0.30s/次（三源共用）、主营 0.20s/次。③ **失败只记标记**：`biz_fail`/`ann_fail` + 时间戳，`extras_stale` 对失败只等 `BIZ_FAIL_COOLDOWN = ANN_FAIL_COOLDOWN = 15 分钟`、**不套 30 天/6 小时 TTL、不覆盖旧值**。④ **熔断** `fail_circuit=12`：连续 12 只「主营+公告都失败」= 被整体风控 → `stats['aborted']='rate_limited'` 直接停手，`workers` 默认 6 → **3**；`extras_missing` 支持 `need_biz`/`need_ann` → **按字段精确补**（重试公告时不再白撞 478 次主营）。
  - **修掉一个真 bug**：巨潮那一层原来写 `from data.stock_identity_provider import get_org_id`（模块级函数不存在，必抛 ImportError）→ **这一层从来没生效过**。改成单例方法 `get_stock_identity_provider().get_org_id(code)` 后，东财+新浪都失败时它真的能顶上来（单测 E5 实证 `ok=True src='cninfo'`）。
  - **单元格显示收敛**（tooltip 始终给上游原文，只影响一格显示）：`_strip_ann_prefix` 去开头「简称:」；新增 `_strip_company_prefix` 去开头**公司全称**（保守三条：前缀 ≥6 字、含「股份」或「集团」、且前缀不含「关于/全资/控股/拟/的」→ 避免把「关于全资子公司…提供担保的进展公告」误剥成「为全资子公司…」）；`_clip(txt, n)` 公告 30 字 / 主营 22 字，超出加 `…`。
  - 实测覆盖（筛选池 978 只，2026-10-11 重补后）：**主营 975/978 = 99.7%**（报告期 2026-06-30 共 928 只）、**公告 978/978 = 100.0%**（东财 500 / 新浪 478）；主板 567 + 创业板 411 两板都 100%（公告）；`extras_missing` 补完后 = **0**。缓存 1437616 字节。三只无主营的是上游确实没有 F10 主营构成（保留 `--` + 默认 tooltip）。
  - 改这两列要同步的 5 处：列索引元组 `(C_NAME…C_DATE) = range(13)`、`PAGE_HEADERS`、`PAGE_WIDTHS`（`[96,66,70,74,230,170,70,58,58,96,190,260,90]`）、`sorter.keys`（`C_BIZ`/`C_ANN`）、`_render`。**拉伸列仍是「涨停题材」**。
  - 补数状态文案：`主营/公告补数完成：主营 N ｜ 公告 N ｜ 失败 N（异常 N）/ X 秒 ｜来源 东财，公告新浪/巨潮兜底`（被限流时改提示「N 分钟后自动重试」）；统计条追加「主营已补 X/Y」。
  - **验证（均本轮重跑）**：`tools\_ctrl_screen_extra_unit.py`（**服务层，可重跑，含联网**）→ `tools\ctrl_screen_extra_unit.txt`（**50 PASS / 0 FAIL**：A 常量/源码三源+限速+退避+熔断、B TTL 与失败退避语义（失败标记 15 分钟内不重试 / 超时自动重试 / 优先于 TTL）、C 缓存往返、D 真实 8 只现拉比对（公告按**日期**比对，标题文案源差异只统计）、E 三源降级链（东财失败→新浪 / 三源全失败→`ok=False` / 东财优先 / 巨潮层不再 ImportError）、F 覆盖率与来源分布、G fmt 边界 + 前缀剥离 4 例 + 不误剥 4 例、H 真实 5 只 + 不存在代码不抛）；`tools\_ctrl_screen_dbui.py`（`QT_QPA_PLATFORM=offscreen`）→ `tools\ctrl_screen_dbui.txt`（**59 PASS / 0 FAIL**：13 列 × 993→978 行真实渲染、前 15 行**逐格 + 4 类 tooltip** 比对、**新增 K1~K11 两列专项** —— 缓存即显/主营文本色 tooltip/公告文本色 tooltip/**空态构造**（临时摘掉一行缓存再重绘，验 `--`+灰+默认 tooltip）/缓存驱动可恢复/两列排序/补数开关关闭不联网/`extras_missing=0` 时不联网/tooltip 不泄露本机路径）；`tools\_ctrl_screen_unit.py` → **43 PASS / 0 FAIL**（服务层快照，未受加列影响）；截图 `tools\_shot_ctrl_screen.py`（`QT_QPA_PLATFORM=windows`，已关掉自动扫描与补数开关保持离线）→ `tools\_shot_ctrl_screen.png`（1920x900，13 列中文可读）。
  - **回退**：`copy /Y "services\control_screen_service.py.bak_before_extras" "services\control_screen_service.py"` + `copy /Y "ui\battle_widgets\control_screen_widget.py.bak_before_extras" "ui\battle_widgets\control_screen_widget.py"`（回到 11 列；**重启主程序**，不需要重跑扫描）。中间态另有 `.bak_before_extras2` / `.bak_before_extras3` / `.bak_before_extras3b`（服务层）与 `.bak_before_extras3b` / `.bak_before_extras3c`（页面）。
  - 一次性补丁（**勿重跑**）：`tools\_apply_ctrl_screen_extras_svc.py`、`_svc2.py`、`_svc3.py`、`_v3b.py`、`_v3c.py`、`_apply_ctrl_screen_extras_wdg.py`；可重跑：`tools\_refill_ctrl_screen_extras.py`（迁移「被限流记成空」的记录 + 用新链路重补）、`tools\_fill_ctrl_screen_extras.py`（全量补，workers=6，**会撞限流**）、`tools\_extras_bench.py`（40 只压测）、探查类 `tools\_diag_ann_empty.py` / `_diag_ann_recover.py` / `_probe_cninfo_orgid.py` / `_probe_cninfo_hdr.py` / `_probe_ann_third.py` / `_probe_sina_struct.py`。
  - 定性备注：两列目前**只展示、不参与筛选**（用户未要求按公告/主营筛选）；「补数」默认只覆盖当前筛选池（978 只），改条件引入新代码时页面会按需补（实测会真的去补）。
  - **交付前最终检查（可重跑）**：`tools\_final_check_extras.py` → `tools\ctrl_screen_extras_final.txt`（**18 PASS / 0 FAIL**：两个文件纯 LF、服务/页面补丁关键字齐备、筛选池 978 只两列齐全、前 40 行都不空、单元格长度受控（公告 ≤30 / 主营 ≤22）、**真实「缺数→显示 `--`→后台补数→补回」联网闭环 1.2 秒**、缓存恢复后 `extras_missing=0`、交付物与备份目录存在）。
  - 定向备份 **`backups\ctrlscreen_extras_20261011_1358\`**（26 文件 / 2.1 MB：两个源文件 + 各自的 4/3 份 `.bak_before_*` + 两列缓存 + AGENTS.md + 6 个一次性补丁 + 4 个可重跑脚本 + 3 份验证报告 + 截图）。备份脚本 `tools\_backup_ctrlscreen_extras.py`（可重跑，会新建带时间戳的目录）。
- **全池补满（2026-10-11 本轮执行，用户选「2301」档）**：把「控盘分≥0 + 页面默认三勾」这一档补满 —— 这是该页面在现有勾选下**能达到的最大池**（3294 只）。
  - 结果：**3294 只全过手 / 异常 0 / `aborted` 空 / 墙钟 709 秒（11.8 分钟）**；主营 **3291/3294 = 99.9%**、公告 **3294/3294 = 100.0%**（主板 2140、创业板 1154，两板公告都是 100%）。缓存 `data\cache\ctrl_screen_extras.json` **4.64 MB**，`extras_missing = 0`。
  - **这次东财没有触发限流**：公告来源 **东财 2800 / 新浪 494**（对比最初一次 16 req/s 时约 500 次就被返 567）。→ 结论：**限速（公告 0.30s/次、主营 0.20s/次）+ 3 线程**足以把速率压到风控阈值以下，全市场补满是可行的；`workers` 不要调回 6。
  - 那 15 只「主营失败」**不是上游没有**：抽样直查 4 只（000777 中核科技 / 600547 山东黄金 / 601788 光大证券 / 600519 贵州茅台）全部拿到数据 → 属**瞬时超时**，清掉 `biz_fail` 重取即恢复（12 只恢复）。**最终仍无主营的只有 3 只**：`002011 盾安环境` / `603214 爱婴室` / `601872 招商轮船`（东财 F10 确实未返回主营构成，已挂 `biz_fail` 标记，15 分钟后自动重试）。
  - **池子上限的真实构成（实测，别再用猜的）**：快照 4404 只 → 默认三勾后 3294 只，砍掉的 **1110 只 = 价格<6 的 751 + 出货(distribute) 320 + ST 39**（互斥归属）。**跟「有没有控盘分」无关**；池子里 100% 是主板 3006 + 创业板 1398，科创板/北交所 0 只。
  - 本轮新增**可重跑**脚本：`tools\_fill_ctrl_screen_pool.py`（跑这一档，日志 `tools\_fill_pool2301.log`）、`tools\_verify_fill_pool.py` → `tools\ctrl_screen_fill_pool_verify.txt`（**16 PASS / 0 FAIL**：直接拆 JSON 独立复现池子与覆盖率、失败标记一致性、无静默空洞、全池单元格长度、4 只失败项当场回查并补回、离屏门槛=0 渲染 3294 行且公告列 0 空）、`tools\_retry_failed_biz.py` / `tools\_refill_last4.py`（失败项重补）、`tools\_cost_full_fill.py` + `_cost_by_board.py`/`_2`/`_3`（只读量化各档待补量）、`tools\_final_check_extras.py`（交付前 18 项）。
  - 三档待补量（真实快照 2026-10-11 14:03，数据日 2026-10-09）：门槛≥85 → 0 只待补；门槛≥70 → 925；门槛≥0+默认三勾 → 2301（本轮已补完）；三勾全不勾 → 3411（未补，只有取消勾选才用得到）。
- ⚠ 本批与上一批（市场节奏接入控盘）**都不在** `backups\backup_20261011_112723` 快照内。
- 坑：给纯 CRLF 文件打补丁时，插入的多行文本必须显式转成 `\r\n`，否则写回出现裸 LF（第一次打这个补丁就踩到，已还原重打）。`control_screen_service.py` / `control_screen_widget.py` 都是**新建的纯 LF 文件**。
- **控盘选股页列宽「按内容自适应」（2026-10-11 本轮）**：用户要「左右每个行列占用空间合适、能全部显示出来」，13 列里不要再出现被省略号截断的内容。
  - 改动文件：`ui\battle_widgets\control_screen_widget.py`（纯 LF，599 → **668 行**）。新增 `_autofit_columns()`，在 `_render()` 末尾调用 + `showEvent` 里 `QTimer.singleShot(120, self._autofit_columns)` 再校一次（首帧 viewport 还没尺寸）。常量块紧跟 `PAGE_WIDTHS` 之后：`_FIT_MAX_ROWS=6000` / `_FIT_SAMPLE=400` / `_HEAD_MIN_PAD=6` / `_THEME_MIN_W=150` / `_FIT_COLS`（除拉伸列 `C_THEME` 外的 12 列）/ `PAGE_WIDTHS_MIN` / `PAGE_WIDTHS_MAX`。**`PAGE_WIDTHS` 现在只是首帧初值**，真实宽度由 `_autofit_columns()` 算。
  - 口径：量字用 `self.table.sizeHintForColumn(c)`（C++ 侧做），先 `setResizeContentsPrecision(-1)`（= 全部行都量；默认只采样 1000 行会漏最长格）；取 `max(表头宽, hint) + _HEAD_MIN_PAD`，夹在 `[MIN, MAX]`；窗口放不下时按 **观察 → 主营收入 → 最新公告** 顺序压回下限（宁可出横向滚动条也不截断）。拉伸列仍是 `C_THEME`（涨停题材），吃掉剩余空间 —— 实测拿到 **384px ≥ 题材最长串需要的 334px**。
  - **两个必须记住的坑**：① `PAGE_WIDTHS_MAX` **不要**给「代码/现价/涨跌幅/位置/数据日」设上限 —— 它们的内容需要宽度会超过拍脑袋定的上限，被夹住反而截断（第一批就是这么翻车的，现在只给三个长文本列设上限）；② 不要退回「Python 逐格 `QFontMetrics.horizontalAdvance` + 采样」：全量 4 万次跨语言调用实测 **662ms**（切换筛选/排序会明显卡），而 Qt 原生 `sizeHintForColumn` 是 **156ms**；采样（step=8）还会漏掉没抽到的最长格（实测残留 5 格差 1~3px 被截断）。
  - 验证：`tools\_verify_colfit.py`（可重跑；**必须 `QT_QPA_PLATFORM=windows`**，离屏没有中文字体、字宽偏大判不准）→ `tools\ctrl_screen_colfit_verify.txt` **10 PASS / 0 FAIL**：门槛 0 渲染 3294 行，**全量 3294 × 13 逐格独立量字（need = 该格字体文字宽 + 16）→ 0 格截断**；短列被压缩（阶段/位置 58 → 52）、长列被放宽（主营 170 → 290、公告 260 → 353、观察 190 → 194）、题材列 384 ≥ 需要 334、窄窗(1250) 各列不低于下限、无横向溢出、自适应 156ms。回归：`tools\_ctrl_screen_dbui.py` **59 PASS / 0 FAIL**、`tools\_ctrl_screen_unit.py` **43 PASS / 0 FAIL**（真实快照 `saved_at=2026-10-11 15:38:07` / 4404 行，未被测试覆盖）。
  - 截图已肉眼复核：`tools\_shot_ctrl_screen.png`（1920×900，`QT_QPA_PLATFORM=windows`，默认门槛 85 → 993 行）—— 涨停题材、主营收入完整，最新公告完整显示到数据层给的长度。
  - **单元格里还会看到 `…` 的地方不是显示截断**：`services\control_screen_service.fmt_ann()` 是 `_clip('MM-DD '+标题, 30)`（`fmt_biz` 主营 22）截完才入库/进单元格，tooltip 里才是全标题。要显示更长标题必须同时改这个 `_clip` 长度**并重取缓存**（缓存里存的就是截断后的文本），不能只改列宽。
  - 回退：`copy /Y "ui\battle_widgets\control_screen_widget.py.bak_before_colfit" "ui\battle_widgets\control_screen_widget.py"`（纯 UI 改动，不动扫描与 DB，回退后**重启主程序**即可）；只退「上限口径」用 `.bak_before_colfit2`、退「全量量字」用 `.bak_before_colfit3`、退「Qt 原生量字」用 `.bak_before_colfit4`。
  - 一次性补丁（**勿重跑**）：`tools\_apply_colfit.py`、`_apply_colfit2.py`、`_apply_colfit3.py`、`_apply_colfit4.py`。

## 备份

```powershell
python scripts\backup.py     # 快照到 backups\backup_<时间戳>\，保留最近 10 份
```

备份范围：20 个代码目录（`ui/core/strategy/services/utils/config/market/market_analysis/news_center/news_engine/service/scripts/test/tests/tools/timed_report/docs/assets`）+ 根目录关键文件（`main.py`、`AGENTS.md`、`README.md`、`requirements.txt`、`start.bat`、`.gitignore`、两个扫描 bat）+ `data\*.py`。**不含** duckdb / logs / backups / cache。

> 恢复时 `restore.py` 对**目录**是「先删后复制」（整个目录被快照版本替换），对**文件**是「覆盖同名」。所以根目录里不在快照内的文件（如各类 `_*.py` 临时脚本、说明文档）不会被删掉。

## 已下线、不要再提的功能

- 选股雷达（AI520）页 —— 用户要求移除
- 30分钟新闻简报 —— 用户要求停用（服务文件 `services\news_30min_digest.py` 保留未删）
- v28 模块包 —— 代码已不存在，死引用已清理；残留文件 `config\v28_config.json`、`data\v28_cache.duckdb` 已于 2026-09-24 删除（无任何 .py 引用）。`docs\V28_UPGRADE_GUIDE.md` 保留作历史文档。
- **聚宽(JoinQuant)回测** —— 2026-09-26 移除 5 个文件：`joinquant_band_pattern.py`、`_fix_gap_prevday.py`、`_fix_gap_prevday2.py`、`_verify_gap_fix.py`、`_verify_jq_parity.py`（备份在 `backups\_removed_joinquant_20260926_184616\`）。
  > **别搞混**：`data\jqdata_provider.py`、`market\providers\joinquant_provider.py`、`config\jqdatasdk_config.json` 是**行情源**（早已 `enabled=false`），**不是回测，保留未动**。扫描取数链路 `_load_bars` 无任何聚宽调用（只有本地 DuckDB 缓存 + 腾讯在线兜底）。
- **「盘中机会」+「金铲子」+「板块异动」三模块** —— 2026-10-09 合并成单一模块 **📈 市场节奏**（`ui\battle_widgets\market_rhythm_widget.py`，单列不分栏，三个 Tab：市场节奏 / 可介入 / 追踪）。
  - 已删除文件（隔离在 `backups\_removed_三模块合并_20261009_170605\`）：`ui\battle_widgets\opportunity_widget.py`、`ui\battle_widgets\leading_theme_widget.py`、`services\golden_shovel_scanner.py`、`data\cache\golden_spade.duckdb`。
  - **不要再建**：旧「盘中机会」Tab、旧「金铲子(实时)/(辅助)」Tab、`golden_shovel_scanner`（东财 clist 接口已废）、`atr_t_widget` 里的金铲子弹窗（`_check_golden_spade` / `_daily_check_golden_spade` 及两个 QTimer 已于同日删除）。
  - **`services\intraday_opportunity_engine.py` 必须保留**（虽已无 UI）：`services\anchor_tracker.py` 的今日异动池只靠它的 `mark_anomaly` 填充，而盘后「基准阳跨日跟踪 / 日K建仓」依赖该池。它由 `main.py` 的 `_background_anomaly_detect()` 后台线程驱动（`get_engine().scan()`，内部自带 25 秒节流 + 锁，无界面）。
  - 涨停库采集 `services\limit_up_collector.py` + 市场节奏引擎 `services\market_rhythm_engine.py` + 可介入引擎 `services\board_anomaly_engine.py` 是三个数据源；`picks_tracking_service.py` + `picks_track_widget.py` 负责「追踪」Tab 的 5日/30日盈亏。

---

## 2026-10-11 A/B/C 三件套：破位—收复 / 量能分位（地量·天量·缩量上涨） / 拉升②位置下限修正

来源：用户贴《机构、庄家、主力操盘控盘的核心逻辑与手法拆解》，逐条对账后只做三个真缺口（A/B/C），
按用户「按照顺序升级」= A → B → C 落地。**照旧先标定、后落地**：两个因子都先用项目自己的滚动观测口径
（17516 条 / 4384 只 / 锚点 k=20/40/60/80 / 只喂 `df[:T+1]` / 无未来数据）标定，再决定出不出文案。

### 标定结论（决定「出不出文案」，不是手感）

| 分组 | n | 未来20日均值 | 胜率 | t | 处置 |
|---|---|---|---|---|---|
| 全样本基准 | 17516 | -0.78% | 45.2% | -7.79 | 基准 |
| A 破位未收 | 180 | **-3.63%** | 33.9% | -3.76 | **出风险文案** |
| A 洗盘收复（全） | 552 | -1.08% | 47.5% | -1.75 | 只写字段 |
| A 洗盘收复 pos<0.45 | 474 | -0.41% | 50.8% | -0.65 | 不显著 → 只写字段 |
| B 天量 | 2849 | **-2.44%** | 37.7% | **-8.36** | **出警示** |
| B 缩量上涨（全） | 702 | +2.64% | 58.5% | +4.84 | 限低位出 |
| B 缩量上涨 pos<0.45 | 518 | **+4.34%** | **66.4%** | **+8.21** | **限 pos<0.45 出文案** |
| B 地量 | 5604 | +0.02% | 47.6% | +0.14 | 噪音 → 只写字段 |
| C ②缩量强势 pos<0.35 | 2458 | +2.36% | 58.1% | +11.66 | 下限改 0.00 |
| C ②缩量强势 pos∈[0.55,0.75) | 147 | -2.83% | — | -2.89 | 原下限就锁在这里 |

量能分位整体单调：pct[0,20) -0.07% → [80,101) -2.44%（**分位越高越差**，故天量=风险而非机会）。

### 代码改动

**`strategy\base.py`（纯 CRLF，1949 → 1952 行）**
- 新增常量块 `BRK_*`（`BRK_LOOKBACK=12 / BRK_SUPPORT_WIN=20 / BRK_RECOVER_WIN=5 / BRK_SHRINK_MAX=1.00 /
  BRK_EXPAND_MIN=1.50 / BRK_RECOVER_VOL=1.20 / BRK_POS_LOW=0.55 / BRK_SCORE_OK=70.0 / BRK_MIN_BARS=60`）
  与 `VR_*`（`VR_WIN=60 / VR_LOW_PCT=20.0 / VR_HIGH_PCT=80.0 / VR_SU_WIN=5 / VR_SU_VOL_MAX=0.90 /
  VR_SU_GAIN_MIN=0.03 / VR_SU_YANG_MIN=0.60 / VR_SCORE_OK=70.0 / VR_MIN_BARS=60`），紧跟 `MARKUP_POS_MAX` 之后。
- 新增 `TechnicalIndicators.detect_breakdown_recover()` / `volume_percentile(df, win)` / `detect_volume_regime()`，
  插在 `detect_markup` 之后、`# K线数据解析` 段头之前。返回契约沿用项目约定（`ok/type|tags/score` 两段不重叠
  `ok=True` 必 ≥70、未通过 ≤60 / `pos120` / `detail` / `reason`）。
  - 口径坑：破位日必须是「`low[i] < min(low[i-20:i])`」的**最近一次**；收复要「其后 5 根内 `close >= 支撑`」；
    `p5 = sum(volumes[i-5:i]) / 5.0` **绝不含当前K线**（B 与模式四同一条硬约束）。
  - 分数两段不重叠是**给 DB 反查用的**，别改成连续打分。
- **C 项**：`MARKUP_LOCK_POS_MIN` **0.55 → 0.00** + 依据注释；`detect_markup` docstring 里「②不可达」那句
  改成「自 2026-10-11 起位置下限 0.00，在本门槛内可正常命中」。全局 `MARKUP_POS_MAX=0.45` 未动。

**`services\band_pattern_engine.py`（纯 LF，2074 → 2171 行）**
- 常量：`_BRK_NOTE_MODE='watch'` / `_BRK_FUNNEL={'ok','insuf','pos','nobreak','wash','dist','note'}` /
  `_VREG_NOTE_MODE='watch'` / `_VREG_FUNNEL={'ok','insuf','low','high','shrinkup','note'}`；
  拉升段那段「②不可达」的注释同步更新。
- `_ctrl_note(..., brk=None, vreg=None)` / `_observe_tags(..., brk=None, vreg=None, pos=None)`；
  新文案：`'破位警示：放量破位未收回'`（仅 `brk=='破位未收'`）、`'天量警示'`、
  `'缩量上涨·疑似控盘'`（**且 pos<0.45**）。「洗盘收复」「地量」**只写字段不出文案**。
- `_ALL_COLS` 59 → **64 列**（`brk_ok INTEGER / brk_type TEXT / brk_score REAL / vreg_tags TEXT / vreg_pct REAL`，
  自动 ALTER 已打印 `DB补齐字段(pattern_record): [...5 个]`）；`_save_or_update` 的列清单 / 占位符（59→64）/
  取值三处同步（**取值元组比列清单少 1 项是正常的**：末列 `updated_at` 是 `datetime.now()` 字面量表达式）；
  `scan_stock` 局部量 + 计算块（复用同一个 `_df`，接在 markup 漏斗后）+ `_ctrl_note` 调用 + 计数器 + `rec`；
  `scan_all` 清零 + 两组打印。

### 实测（`tools\run_scan_quiet.py` → `tools\_scan_after_brkvr.log`）

- 全市场 **5223 只 / 异常 0 / 模式一 191 / 模式三 39 / 总记录 230**，与上一批**逐项 0 变化**（新因子不参与筛选）。
- `[破位收复] 可算 2347 只 ｜ 洗盘收复 106 ｜ 破位未收 368 ｜ 位置超限(pos>=0.55) 620 ｜ 无破位日 614 ｜ 文案 474`
- `[量能分位] 可算 3581 只 ｜ 地量 298 ｜ 天量 812 ｜ 缩量上涨 54 ｜ 文案 1144 只`
- `[拉升观察] 可算 2675 ｜ 阶梯式上行 76 ｜ **缩量强势 58（修复前恒为 0）** ｜ 加速迹象 1 ｜ 命中合计 135`
- DB 230 条里：**破位警示 7 条 / 天量警示 67 条 / 缩量上涨·疑似控盘 4 条**（9 条 `缩量上涨` 里只有 4 条 pos<0.45）；
  日K建仓默认筛选（建仓触发+等待确认）203 行里 **59 行**能带出新文案。

### 验证

- `tools\_verify_brkvr.py`（**可重跑**）→ `tools\brkvr_verify.txt`：**28 PASS / 0 FAIL**。
  ① 源码结构：CRLF/LF 行尾、`BRK_POS_LOW=0.55`、`MARKUP_LOCK_POS_MIN=0.00`、三个 `@staticmethod`、
  docstring 无单反斜杠转义、`_ALL_COLS == INSERT 列 == 占位符 == 64`、取值元组与列清单逐项同序同名；
  ② **229 条 DB 记录用独立重写的实现逐只重算**（不调用被验证函数）：`brk_type/brk_ok/brk_score/vreg_tags/vreg_pct`
  **0 处不一致**；③ 文案与字段零矛盾（`破位未收` 7/7 都出警示、`天量` 67/67 都出警示、洗盘收复不出警示）；
  ④ C 项：`markup_type='缩量强势'` 的记录 **pos120 全部 <0.45**。
- `tools\_brkvr_dbui.py`（**可重跑**）→ `tools\brkvr_dbui.txt`：**6 PASS / 0 FAIL**。
  UI 侧 `atr_t_widget.py` L2128-2130 `_note = r.get('note','')` → `_tg_item.setToolTip(_note)`，
  新文案走**触发条件列 tooltip**，全文可见，不需要改 UI。
- 回退：`copy /Y "strategy\base.py.bak_before_brkvr_engine" "strategy\base.py"` +
  `copy /Y "services\band_pattern_engine.py.bak_before_brkvr_engine" "services\band_pattern_engine.py"` +
  （C 项另需）`copy /Y "strategy\base.py.bak_before_brkvr" "strategy\base.py"`，**回退后必须重跑全市场扫描**；
  只想去掉文案 → `_BRK_NOTE_MODE` / `_VREG_NOTE_MODE` 改 `'off'`（字段继续写，无需改代码）。
- 还原点：A/B/C **之前**的 `backups\backup_20261011_164852` 仍在；**A/B/C 之后尚未打新快照**
  （`scripts\backup.py` 只留最近 10 份，会挤掉最旧的一份，需要就说一声）。

### 本批踩的坑（别重复）

1. **`@staticmethod` 必补**：同族老函数（`estimate_control_score` / `detect_probe` / `detect_markup`）都带
   `@staticmethod`，引擎是 `_ti = _TI()` 后用**实例**调用 → 漏装饰器就 `TypeError: takes 1 positional argument
   but 2 were given`，异常被 try/except 吞掉、字段永远全 0（**本次真实发生过**）。
2. **docstring 里的 Windows 路径必须双反斜杠**：`tools\markup2_pos_calib.txt` 写成单反斜杠 → `SyntaxWarning: "\m"`
   （L1260）。**注释里的单反斜杠无害**，只有 docstring/字符串要改。
3. **打印里 import 常量要核对真名**：我写成 `from strategy.base import BRK_POS_MAX as _BPMAX`，真名是
   `BRK_POS_LOW` → 扫描数据已落库但尾部漏斗日志整体被 ImportError 打断（进程退 1）。
4. `_ALL_COLS` 与 INSERT **列顺序本来就不同**（列名显式给出），别拿两边顺序做相等断言；
   真正要对齐的是**取值元组 vs INSERT 列清单**，且取值元组天然少 1 项（`updated_at` 字面量）。
