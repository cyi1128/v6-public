# -*- coding: utf-8 -*-
"""
「可介入」门槛收紧扫描：用真实历史样本，找哪一档能提高胜率。

口径与程序完全一致：直接调 services.picks_tracking_service.fetch_tracking()，
再用它自己的规则（win = 收益 > 0 的占比）分组统计 —— 不自己另写一套算法。
只读评估，不改任何常量。

输出：tools\\picks_threshold_sweep.txt
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

from services.picks_tracking_service import fetch_tracking  # noqa: E402

OUT = os.path.join(ROOT, "tools", "picks_threshold_sweep.txt")
buf = []


def W(s=""):
    buf.append(s)
    print("  " + s)


def stat(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    win = sum(1 for v in vals if v > 0)
    return {
        "n": len(vals),
        "win": round(win / len(vals) * 100.0, 1),
        "avg": round(sum(vals) / len(vals), 2),
        "max": round(max(vals), 2),
        "min": round(min(vals), 2),
    }


def line(label, rows):
    r5 = stat(rows, "r5")
    r30 = stat(rows, "r30")
    cu = stat(rows, "cum")
    def fmt(s):
        if not s:
            return "  --   "
        return "%5.1f%%" % s["win"]
    def fmta(s):
        if not s:
            return "   --  "
        return "%+6.2f%%" % s["avg"]
    W("%-30s 总%5d | 5日 %s %s (n=%d) | 30日 %s %s (n=%d) | 累计 %s %s (n=%d)"
      % (label, len(rows), fmt(r5), fmta(r5), r5["n"] if r5 else 0,
         fmt(r30), fmta(r30), r30["n"] if r30 else 0,
         fmt(cu), fmta(cu), cu["n"] if cu else 0))


W("=" * 150)
W("「可介入」门槛收紧扫描  ——  口径与程序一致（fetch_tracking + win=收益>0）")
W("=" * 150)

rows = fetch_tracking()
W("总样本 %d 条" % len(rows))
mb = [r for r in rows if str(r["code"]).startswith(("60", "00"))]
cy = [r for r in rows if str(r["code"]).startswith(("300", "301"))]
W("  主板 %d ｜ 创业板 %d" % (len(mb), len(cy)))
W()

W("【基准】当前门槛：量比>=1.2  涨幅 1.0~9.0%%  价格>=6元")
line("当前全部", rows)
W()

W("=" * 150)
W("一、单项收紧：量比下限")
W("=" * 150)
for v in (1.2, 1.5, 1.8, 2.0, 2.5, 3.0):
    line("量比 >= %.1f" % v, [r for r in rows if float(r["vol_ratio"] or 0) >= v])
W()

W("=" * 150)
W("二、单项收紧：涨幅上限（PICK_MAX_PCT）")
W("=" * 150)
for v in (9.0, 8.0, 7.0, 6.0, 5.0):
    line("涨幅 <= %.1f%%" % v, [r for r in rows if float(r["pct0"] or 0) <= v])
W()

W("=" * 150)
W("三、单项收紧：涨幅下限（PICK_MIN_PCT）")
W("=" * 150)
for v in (1.0, 2.0, 3.0, 4.0):
    line("涨幅 >= %.1f%%" % v, [r for r in rows if float(r["pct0"] or 0) >= v])
W()

W("=" * 150)
W("四、单项收紧：价格下限（PICK_MIN_PRICE）")
W("=" * 150)
for v in (6.0, 8.0, 10.0, 15.0):
    line("价格 >= %.0f元" % v, [r for r in rows if float(r["base_price"] or 0) >= v])
W()

W("=" * 150)
W("五、组合收紧（量比 × 涨幅上限）")
W("=" * 150)
for vr in (1.5, 1.8, 2.0):
    for pc in (9.0, 7.0, 6.0):
        line("量比>=%.1f 且 涨幅<=%.0f%%" % (vr, pc),
             [r for r in rows if float(r["vol_ratio"] or 0) >= vr
              and float(r["pct0"] or 0) <= pc])
W()

W("=" * 150)
W("六、组合收紧（量比 × 涨幅上限 × 价格下限）")
W("=" * 150)
for vr in (1.5, 1.8, 2.0):
    for pc in (9.0, 7.0):
        for pr in (6.0, 8.0):
            line("量比>=%.1f 涨幅<=%.0f%% 价格>=%.0f元" % (vr, pc, pr),
                 [r for r in rows if float(r["vol_ratio"] or 0) >= vr
                  and float(r["pct0"] or 0) <= pc
                  and float(r["base_price"] or 0) >= pr])
W()

W("=" * 150)
W("七、只收紧创业板（主板门槛不动）")
W("=" * 150)
W("--- 创业板 ---")
for vr in (1.2, 1.5, 1.8, 2.0):
    line("创 量比>=%.1f" % vr, [r for r in cy if float(r["vol_ratio"] or 0) >= vr])
W("--- 主板对照 ---")
line("主 全部（不动）", mb)
line("主 量比>=1.5", [r for r in mb if float(r["vol_ratio"] or 0) >= 1.5])
W()

W("=" * 150)
W("八、最优候选档的明细（量比>=1.8 且 涨幅<=7%）")
W("=" * 150)
best = [r for r in rows if float(r["vol_ratio"] or 0) >= 1.8 and float(r["pct0"] or 0) <= 7.0]
b5 = stat(best, "r5")
b30 = stat(best, "r30")
bc = stat(best, "cum")
W("样本 %d 条" % len(best))
if b5:
    W("  5日  n=%d 胜率 %.1f%% 均值 %+.2f%% 最好 %+.2f%% 最差 %+.2f%%"
      % (b5["n"], b5["win"], b5["avg"], b5["max"], b5["min"]))
if b30:
    W("  30日 n=%d 胜率 %.1f%% 均值 %+.2f%% 最好 %+.2f%% 最差 %+.2f%%"
      % (b30["n"], b30["win"], b30["avg"], b30["max"], b30["min"]))
if bc:
    W("  累计 n=%d 胜率 %.1f%% 均值 %+.2f%% 最好 %+.2f%% 最差 %+.2f%%"
      % (bc["n"], bc["win"], bc["avg"], bc["max"], bc["min"]))

io.open(OUT, "w", encoding="utf-8").write("\n".join(buf) + "\n")
print()
print("已写入 %s" % OUT)
