# -*- coding: utf-8 -*-
"""1) AGENTS.md 记录竞价创业板门槛  2) 打还原点"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + os.sep

# ---------- 1) AGENTS.md ----------
P = ROOT + "AGENTS.md"
raw = open(P, "rb").read()
assert raw.count(b"\r\n") == 0, "AGENTS.md 应为纯 LF"
shutil.copy2(P, P + ".bak_before_cyb_auction")
s = raw.decode("utf-8")

anchor = "- **三轴状态闸门**："
add = """- **竞价模块的创业板单独门槛（2026-10-10）**：`ui\\battle_widgets\\auction_filter_widget.py`（**纯 CRLF**）。门槛原先按主板口径调，直接套到创业板会把最强的高开信号砍掉（创业板开盘能到 +20%）。按「涨停幅度比 = 2.0」等比缩放，主板口径一字未动：
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
"""
assert s.count(anchor) == 1, "锚点命中 %d 次" % s.count(anchor)
s = s.replace(anchor, add + anchor, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
r2 = open(P, "rb").read()
print("OK AGENTS.md 已更新，行数 %d，CRLF=%d（应 0）"
      % (r2.decode("utf-8").count("\n") + 1, r2.count(b"\r\n")))

# ---------- 2) 打还原点 ----------
print()
print("=== 打还原点 ===")
p = subprocess.run([sys.executable, "-X", "utf8", "scripts\\backup.py"],
                   cwd=r"D:\QuantMonitorV6", capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
out = (p.stdout or "") + (p.stderr or "")
for line in out.strip().splitlines()[-14:]:
    print("   " + line)
