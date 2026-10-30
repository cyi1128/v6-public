# -*- coding: utf-8 -*-
"""一次性补丁：把「市场节奏 Tab1/Tab2 接入控盘度」这一批写进 AGENTS.md。

只做三处替换，每处断言唯一命中；AGENTS.md 是纯 LF，写回保持 LF。
执行一次即失效，勿重跑。
"""
import io

P = r'D:\QuantMonitorV6\AGENTS.md'
s = io.open(P, 'rb').read().decode('utf-8')
assert '\r\n' not in s, 'AGENTS.md 不是纯 LF'

o1 = '这个版本包含：\n\n- **拉升位置门槛（1010m 新增'
n1 = (
    '这个版本包含：\n\n'
    '- **⚠ 快照之后又改了 1 个文件（未进 20261011_112723 快照）**：'
    '`ui\\battle_widgets\\market_rhythm_widget.py` —— 「市场节奏」Tab1 / Tab2 接入控盘度'
    '（见下面「控盘度已铺到全部列表模块」一节）。纯 UI 列/文案改动，不涉及扫描与 DB，'
    '**不需要重跑全市场扫描**；回退 `copy /Y "ui\\battle_widgets\\market_rhythm_widget.py.bak_before_rhythm_ctrl" '
    '"ui\\battle_widgets\\market_rhythm_widget.py"` 后重启主程序即可。\n\n'
    '- **拉升位置门槛（1010m 新增'
)
assert s.count(o1) == 1, 'o1 miss'
s = s.replace(o1, n1)

o2 = ('已接：自选评分、竞价筛选（今日竞价 + 竞价追踪）、今日涨停、分时做T、日K建仓、'
      '市场节奏·追踪，共 7 张表，列名统一叫「控盘」。')
n2 = ('已接：自选评分、竞价筛选（今日竞价 + 竞价追踪）、今日涨停、分时做T、日K建仓、'
      '市场节奏·追踪、**市场节奏·主表（连板梯队内联）**、**市场节奏·可介入（单元格内联 + 独立「控盘」列）**，'
      '共 9 张表，列名统一叫「控盘」。')
assert s.count(o2) == 1, 'o2 miss'
s = s.replace(o2, n2)

o3 = '  - 按题材成行的**板块级**表格不可能放个股分数：市场节奏主表、可介入表、板块异动表均未接入。\n'
n3 = (
    '  - **板块级表格（按题材成行）怎么接（2026-10-11 本批新增；「市场节奏」三 Tab 现已全部接入）**：'
    '`ui\\battle_widgets\\market_rhythm_widget.py` 的 Tab1「市场节奏」与 Tab2「可介入」都是**板块/题材成行、'
    '行对象没有顶层 code 字段**（行内个股在 `row[\'ladder\']` / `row[\'picks\']` 里），所以 '
    '`fetch_ctrl_for` / `fetch_ctrl_cached` / `attach_ctrl`（都按 `row[\'code\']` 取码）套不上，'
    '改用「双落点」：① 单元格内联 —— Tab1 连板梯队里每只个股名后跟控盘短文本（`_ctrl_inline` → `88候选`），'
    'Tab2「可介入」里每只候选名后跟控盘分；② Tab2 新增独立「控盘」列（`P_CTRL` = 第 6 列），'
    '显示**该题材可介入候选里控盘分最高者**，悬停列出逐只候选的分数/阶段/位置。'
    '数据全部走 `get_ctrl_map(..., cached_only=True)`（UI 线程零计算），'
    '缺的由新增的 `MarketRhythmWidget._ctrl_async_fill()` 在后台算完再重绘两个 Tab。\n'
    '  - 本批具体改动（`ui\\battle_widgets\\market_rhythm_widget.py`，662 行 → **885 行 / 35943 字符**，仍**纯 LF**）：'
    'Tab2 列数 6 → 7（`(P_BOARD…P_MEMBERS) = range(7)`、`P_HEADERS` 第 6 项用统一常量 `CTRL_COL_TITLE`、'
    '`P_GRID = [104, 46, 100, 150, 470, 104, 260]`（可介入列 340 → 470，否则内联控盘会被截断）、'
    '`make_table(len(P_HEADERS), P_HEADERS)` 不再硬写 6、`pick_sorter` 加 `P_CTRL: _top_ctrl_score`）；'
    '新增 8 个模块级控盘工具（`_ctrl_lookup` / `_ctrl_inline` / `_ctrl_one_line` / `_ctrl_pos_txt` / '
    '`_ladder_ctrl` / `_picks_ctrl` / `_top_ctrl` / `_top_ctrl_score`）+ 2 个类方法（`_all_stock_codes` / '
    '`_ctrl_async_fill`）；`_apply()` 末尾触发 `_ctrl_async_fill()`。'
    '**末列仍是 `P_MEMBERS`（成分股）**，`setStretchLastSection(False)` 的写法不变。\n'
    '  - 验证：`tools\\_verify_rhythm_ctrl.py` → `tools\\rhythm_ctrl_verify.txt`（**33 PASS / 0 FAIL**，'
    '含真实股票独立重算交叉验证与离屏真实渲染逐格比对）；'
    '版式截图 `tools\\_shot_rhythm_ctrl.py` → `tools\\_shot_rhythm_tab1.png` / `_shot_rhythm_tab2.png`'
    '（**离屏无中文字体，中文显示成方块，只可判版式**）。\n'
    '  - 仍未接入控盘：`leader_ladder_widget.py` / `sector_spike_widget.py` 代码在但**未挂到界面**'
    '（无任何地方实例化）。\n'
)
assert s.count(o3) == 1, 'o3 miss'
s = s.replace(o3, n3)

io.open(P, 'wb').write(s.encode('utf-8'))
print('AGENTS.md 已更新：%d → %d 字符，行数 %d'
      % (40095, len(s), s.count('\n') + 1))
