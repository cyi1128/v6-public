# -*- coding: utf-8 -*-
"""一次性补丁：往 AGENTS.md（纯 LF）插入「🎛 控盘选股页」小节，位置在 ## 备份 之前。"""
import io
import os
import shutil

AG = r'D:\QuantMonitorV6\AGENTS.md'
src = io.open(AG, 'r', encoding='utf-8').read()

ANCHOR = '## 备份\n\n```powershell\n'
assert src.count(ANCHOR) == 1, '锚点命中 %d 次' % src.count(ANCHOR)
assert '控盘选股页（🎛' not in src, '疑似已插入过'

SEC = """## 🎛 控盘选股页（2026-10-11 新增；独立页面，不改扫描逻辑）

以「控盘度」为主线单独开一个 Tab 筛全市场，不再把「控盘」列往已有表格里塞。

- **新增文件**：`services\\control_screen_service.py`（服务，14066 字节）、`ui\\battle_widgets\\control_screen_widget.py`（页面，18639 字节）、`data\\cache\\control_screen.json`（扫描快照）。
- **挂载点**：`ui\\battle_console_v2.py`（纯 CRLF，7068 → **7090 行 / 384447 字节**）两处 —— L6577 起创建 `self.ctrl_screen_page` 并 `addTab(..., '🎛 控盘选股')`（try/except 降级占位）、L6722 起连接 `stock_clicked → _show_stock_detail`。备份 `ui\\battle_console_v2.py.bak_before_ctrlscreen`（382888 字节）。**需重启主程序才可见**。
- **口径全部复用唯一来源**：控盘分 / 阶段 / pos120 与 `services\\control_profile.compute_one` 逐字一致（阈值只在 `band_pattern_engine` 一处定义），观察文案走 `_ctrl_note`，短标签走 `ctrl_label`。页面自己**不新造任何阈值**。
- **只读、不写库**：`data\\cache\\kline_cache.duckdb` 用 `read_only=True` + 一条 SQL 批量取每只最近 120 根；扫描前后 `band_pattern.db` / `kline_cache.duckdb` 字节与 mtime 均未变（有断言）。
- **股票池**：`60/00/30`（主板 + 创业板），剔 `688/689/8/4/920`；K 线不足 60 根跳过。
- **10 列**：股票名称 / 代码 / 现价 / 涨跌幅 / 控盘分 / 阶段 / 位置 / 控盘提示 / 观察 / 数据日。阶段 = 出货/洗盘/—；位置 = pos120（<0.25 显示红）；控盘提示 = 短标签（绿候选/红出货/橙洗盘）+ tooltip 全文；观察 = 试盘 / C4 / C6 / 出货形态 / 拉升（可过滤）。
- **条件栏**：控盘分≥（默认 85）/ 位置≤（默认不限，可选 0.65/0.45/0.25）/ 排除出货（默认勾）/ 价格≥6元（默认勾）/ 剔除ST（默认勾）/ 观察下拉 / 打开页面自动扫描（默认勾，每个进程只跑一次）/ 开始扫描 / 导出代码；点名称或代码跳个股分析。
- **实测（2026-10-11）**：批量读库 52.9 万行 / 1.15 秒；全市场 **4416 只 / ok 4404 / skip_bars 12 / fail 0 / 22~23 秒**；**控盘≥85 排出货 = 993 只**（位置≤0.25 → 760；控盘≥90 → 259；≥95 → 472）。
- **验证（可重跑）**：`tools\\_ctrl_screen_unit.py` → `tools\\ctrl_screen_unit.txt`（**37 PASS / 0 FAIL**，含与 `compute_one` 抽样 250 只逐只一致、边界 85.0/84.99 与 0.4499/0.4501 与 6.0/5.99、导出、快照、扫描不改库）；`tools\\_ctrl_screen_dbui.py`（需 `QT_QPA_PLATFORM=offscreen`）→ `tools\\ctrl_screen_dbui.txt`（**40 PASS / 0 FAIL**，真实快照 993 行渲染、前 15 行 × 10 列逐格 + 颜色 + tooltip、条件联动、点击发信号、排序、addTab 离屏、导出全链路）；截图 `tools\\_shot_ctrl_screen.py`（`QT_QPA_PLATFORM=windows`）→ `tools\\_shot_ctrl_screen.png`（中文可读；offscreen 中文成方块）。
- **回退**：`copy /Y "ui\\battle_console_v2.py.bak_before_ctrlscreen" "ui\\battle_console_v2.py"`（重启主程序）；彻底移除再删这三个新文件。
- ⚠ 本批与上一批（市场节奏接入控盘）**都不在** `backups\\backup_20261011_112723` 快照内。
- 坑：给纯 CRLF 文件打补丁时，插入的多行文本必须显式转成 `\\r\\n`，否则写回出现裸 LF（第一次打这个补丁就踩到，已还原重打）。

"""

BAK = AG + '.bak_before_ctrlscreen_doc'
if not os.path.isfile(BAK):
    shutil.copy2(AG, BAK)
    print('备份: %s' % BAK)

out = src.replace(ANCHOR, SEC + ANCHOR, 1)
with io.open(AG, 'w', encoding='utf-8', newline='') as f:
    f.write(out)

raw = io.open(AG, 'rb').read()
print('写回: 行数=%d CRLF=%d 裸LF=%d 字节=%d'
      % (out.count('\n'), raw.count(b'\r\n'), raw.count(b'\n') - raw.count(b'\r\n'), len(raw)))
assert raw.count(b'\r\n') == 0, 'AGENTS.md 被写成了 CRLF'
