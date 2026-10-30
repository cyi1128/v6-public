# -*- coding: utf-8 -*-
"""一次性补丁：把「策略看板」页记进 AGENTS.md（勿重跑）。"""
import io

P = r'D:\QuantMonitorV6\AGENTS.md'
ANCHOR = '- **控盘选股「数据日停在昨天」'

NEW = """- **「📈 策略看板」新页（2026-10-17 新增；对标 TickFlow Stock Panel 的选股/扫描部分）**：
  - **定位**：用户转发 TickFlow Stock Panel 安利贴，要求「在我程序单开一页做这个项目」。v1 只做其**选股/扫描**部分（回测引擎 / AI 复盘留后续迭代），全部吃本地 kline_cache，不引外部栈、不装重型依赖。
  - **新文件 `services\\strategy_scan_service.py`（纯 LF）**：`STRATEGIES` 7 个策略（`ma_gold` MA5上穿MA20 / `ma_long` 均线多头排列 / `macd_gold` DIF上穿DEA / `rsi_oversold` RSI14≤25 / `kdj_gold` K上穿D / `brk_vol` 收盘创20日新高且量比≥1.5 / `pull_ma20` 缩量回踩MA20）。纯 Python 指标（`_ma_series`/`_ema_series`/`_kdj_series`），全市场 4416 只实测 **3 秒**。复用 `control_screen_service.load_all_bars()` / `code_name_map()` / `is_st_name()`；结果落 `data/cache/strategy_panel.json`。**RSI 阈值定 25 而非 30**：实测普跌日 RSI≤30 会命中全市场 1/4（689→1100+），等于没筛。
  - **新文件 `ui\\battle_widgets\\strategy_panel_widget.py`（纯 LF）**：`StrategyPanelWidget(BattleModuleBase)`，7 列（股票名称/代码/现价/涨跌幅/命中策略/位置/数据日，命中策略列 Stretch）；工具栏 7 个策略复选框（默认全选）+ 开始扫描/停止 + 进度条；双击行发 `stock_clicked(code,name)`。
  - **挂 Tab**：`ui\\battle_console_v2.py`（纯 CRLF）在控盘选股块后插 try/except 注册 `📈 策略看板`，并在信号连接区把 `stock_clicked` 接到 `_show_stock_detail`（由 `tools\\_apply_strategy_tab.py` 一次性完成，勿重跑）。
  - **验证**：`tools\\_verify_strategy_panel.py` **13 PASS / 0 FAIL**（造数：多头排列/金叉/放量突破命中、不足60根不命中；实扫 1733/4416、数据日新鲜、每只至少命中一个；离屏渲染 1733 行）。命中分布：多头排列 891 / RSI超卖 689 / 缩量回踩MA20 139 / MA金叉 72 / KDJ金叉 59 / 放量突破 30 / MACD金叉 28。
  - **刻意没做（下一步候选）**：TickFlow 的回测（vectorbt 式 T+1/手续费/滑点/止损）、AI 复盘（DeepSeek/通义/Ollama）、连板梯队/概念轮动（项目已有「市场节奏」Tab，不必重复）。

"""

raw = io.open(P, encoding='utf-8', newline='').read()
assert raw.count(ANCHOR) == 1, '锚点命中 %d 次' % raw.count(ANCHOR)
raw = raw.replace(ANCHOR, NEW + ANCHOR, 1)
io.open(P, 'w', encoding='utf-8', newline='').write(raw)
print('AGENTS.md 已记录策略看板页')
