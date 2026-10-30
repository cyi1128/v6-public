# -*- coding: utf-8 -*-
"""验证：创业板现在能从本地缓存读 K 线 + 走完四模式筛选，并按模式统计。"""
import sys
import time

sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

from services.band_pattern_engine import BandPatternEngine, _load_bars
from utils.stock_name_manager import get_all_stock_names

raw = get_all_stock_names()
c2n = {}
for nm, cd in raw.items():
    c2n.setdefault(cd, nm)
cyb = sorted([(c, n) for c, n in c2n.items() if str(c).startswith(("300", "301"))])
sample = cyb[::12][:120]          # 均匀抽 120 只
print("创业板代码 %d 只，抽样 %d 只" % (len(cyb), len(sample)))

eng = BandPatternEngine()
t0 = time.time()
local = net = 0
by_pat = {}
for code, name in sample:
    t1 = time.time()
    bars = _load_bars(code)
    dt = time.time() - t1
    if bars:
        # 本地缓存读取一般在 0.02s 内；在线兜底 > 0.2s
        if dt < 0.15:
            local += 1
        else:
            net += 1
    try:
        for r in (eng.scan_stock(code, name) or []):
            by_pat.setdefault(r.get("pattern_name"), []).append(
                (code, name, r.get("signal_level"), r.get("trigger_type")))
    except Exception as e:
        print("  !! %s %s" % (code, e))

el = time.time() - t0
print("耗时 %.1f 秒（%.2f 秒/只）" % (el, el / len(sample)))
print("K线来源：本地缓存 %d 只 / 在线兜底 %d 只" % (local, net))
print()
print("产出记录：")
if not by_pat:
    print("   （本次抽样无信号，属正常——四模式本身是严格条件）")
for pat, rows in by_pat.items():
    print("   %s：%d 条" % (pat, len(rows)))
    for x in rows[:12]:
        print("      %s %-8s [%s] %s" % x)
