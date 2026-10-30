# -*- coding: utf-8 -*-
"""一次性补丁：把「控盘选股数据日停在昨天」这一批的改动记进 AGENTS.md（勿重跑）。

插在「这个版本包含：」列表最前面（该文件是最新在上）。
"""
import io
import os

P = r'D:\QuantMonitorV6\AGENTS.md'
ANCHOR = '- **日K线图修复 + 板性阈值/周期切换真正生效（2026-10-11 深夜；'

NEW = """- **控盘选股「数据日停在昨天」→ 取数源顺序修复 + 当日 bar 补齐 + 接到页面扫描前（2026-10-12；用户「控盘选股没有更新实际数据」→ 选「要」自动补）**：
  - **根因**：`utils\\kline_fetcher.py` 的 `fetch_kline()` 旧顺序 `pytdx → 新浪 → 腾讯 → 东财`，判据是「根数够就 return」。盘中实测：pytdx 服务器可连但**无数据**；**新浪日线不含当天未收盘 bar（末根=上一交易日）**；腾讯**有**当天 bar 却排在新浪之后永远用不上；东财连接被断 → K线缓存与控盘选股的数据日停在上一交易日（当时是 10-09）。
  - **修复 1（取数源）**：`fetch_kline` 改**新鲜度优先** —— 逐源尝试，优先返回「末根=今天」的那一份，都不新才退回第一份能用的；新增 `_kline_last_date()` / `_today_bar_expected()`（工作日 + 非节假日 + 已过 09:30，按分钟缓存）。380 → **431 行**，仍**纯 CRLF + BOM**，编译 OK。实测 8 只不同板块代码全部拿到当天 bar（0.26~0.75s/只）。
  - **修复 2（当日 bar 补齐器）**：`services\\kline_cache_service.py`（**纯 LF，11664 → 16079 B**）新增 `seed_today_bar(codes=None, progress_cb=None, only_in_session=True, sleep_per_batch=0.0)` —— 走腾讯**批量实时行情**（`qt.gtimg.cn`，80 只/请求、全市场 56 请求、约 55 秒），用当日快照拼今天这根**未收盘** bar（open/high/low=快照、close=最新价、volume=手×100、amount=volume×close、`ON CONFLICT(code,date)` 更新、同步 `kline_cache_meta` 记 `source='realtime_seed'`），停牌/无成交跳过不写假 bar，DB 被占用退避重试 6×2s。`tools\\seed_today_bar.py` 改为它的**薄 CLI 封装**（`--codes` / `--force-anytime`）。
  - **为什么不用逐个代码抓日线**：实测 4427 只里 **3242 只腾讯日线被 WAF 限流**（`[KLINE TX] 解析异常`），退回新浪旧数据 → 命中不了当天 bar。
  - **修复 3（接到页面扫描前）**：`ui\\battle_widgets\\control_screen_widget.py`（**纯 LF，717 → 758 行**）工具栏新增复选框 `_ck_seed = QCheckBox('补当日K线')`（默认勾选 + 说明 tooltip），`_start_scan` 的 `_job()` 在 `SS.load_all_bars()` **之前**调 `seed_today_bar(progress_cb=_p)`，状态栏依次显示「补当日K线 n/N」→「当日K线已补 N 只（覆盖 a→b），开始扫描…」/「当日K线未补：<原因>」/「当日K线补齐异常：…」；只在交易日 09:15~15:05 生效（`utils.trade_calendar.is_market_open`），失败不打断扫描。
  - **顺手修掉的真实缺陷**：`_on_scan_ok` 原来**无条件** `save_snapshot` —— 点一次「停止扫描」就把残缺结果（实测 0 行 / **122 B 空壳**）覆盖掉上一次完整快照，下次打开本页是空表。现在 `_cancelled or not rows` 时不覆盖快照，列表与快照保持上一次结果，状态栏提示「扫描已中止：本次 N 只…」（提示必须放在 `_apply_and_render()` **之后**，否则会被 `_update_count` 重写的统计条盖掉）。
  - **验证**：`tools\\_verify_seed_bar.py` **22 PASS / 0 FAIL**（服务层：写库成功、库里真有今天行、volume 是**股**、meta 同步、非交易时段被打回且不写行、无行情代码不写假 bar；页面层：开关存在/默认勾选/挂在 bar1、源码顺序「先补数后读K线」、真跑扫描 91s（补数≈58s + 扫描 31s）vs 关掉开关 **33s**、结果 `data_date`=今天）；`tools\\_verify_seed_msg.py` **4 PASS / 0 FAIL**（成功/跳过/异常三条状态文案）；`tools\\_verify_cancel_snapshot.py`（中止不覆盖快照 + 正常扫描照旧覆盖）。
  - 实测数据：当日 bar 覆盖 **1835 → 4418 / 4427 只**（9 只当日无有效行情，多为停牌）；快照 `data\\cache\\control_screen.json` 数据日 **2026-10-09 → 2026-10-12**（4404 行）；页面渲染统计条「符合条件 1083 只 ｜ 全量 4404 只 ｜ 扫描 4416 只 ｜ 数据日 2026-10-12」。
  - 回退：`copy /Y "utils\\kline_fetcher.py.bak_before_fresh" "utils\\kline_fetcher.py"`、`copy /Y "services\\kline_cache_service.py.bak_before_seed" "services\\kline_cache_service.py"`、`copy /Y "ui\\battle_widgets\\control_screen_widget.py.bak_before_seed" "ui\\battle_widgets\\control_screen_widget.py"`、`copy /Y "tools\\seed_today_bar.py.bak_before_seed" "tools\\seed_today_bar.py"`。**纯取数 + UI 改动，不需要重跑全市场扫描，但必须重启主程序**（运行中的实例内存里是旧取数代码）。
  - 一次性补丁勿重跑：`tools\\_fix_kline_source_order.py`、`tools\\_refill_today_kline.py`、`tools\\_apply_agents_seed.py`；可重跑：`tools\\seed_today_bar.py`、`tools\\_rescan_ctrl_today.py`、`tools\\_verify_seed_bar.py`、`tools\\_verify_seed_msg.py`、`tools\\_verify_cancel_snapshot.py`、`tools\\_shot_ctrl_screen.py`。
"""

raw = io.open(P, encoding='utf-8', newline='').read()
n_crlf = raw.count('\r\n')
n_lf = raw.count('\n')
assert raw.count(ANCHOR) == 1, '锚点命中 %d 次，未改动' % raw.count(ANCHOR)
assert n_crlf == 0 and n_lf == raw.count('\n'), '行尾不是纯 LF，未改动'

body = raw.replace(ANCHOR, NEW + ANCHOR, 1)
with io.open(P, 'w', encoding='utf-8', newline='') as f:
    f.write(body)
print('AGENTS.md: %d → %d 字符（纯 LF）' % (len(raw), len(body)))
print('插入位置: 第 %d 行之前' % (raw[:raw.index(ANCHOR)].count('\n') + 1))
