# -*- coding: utf-8 -*-
"""端到端验收：创业板股票能否真正走完 日K建仓 扫描链路并产出记录。"""
import sys, time
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")

from utils.stock_name_manager import get_all_stock_names
from services.band_pattern_engine import BandPatternEngine, _load_bars, _is_main_a_share

raw = get_all_stock_names()
c2n = {}
for nm, cd in raw.items():
    c2n.setdefault(cd, nm)
cyb = [(c, n) for c, n in c2n.items() if str(c).startswith(("300", "301"))]
print("创业板代码总数: %d" % len(cyb))

# 取前后各 25 只做样本
sample = cyb[:25] + cyb[-25:]
eng = BandPatternEngine()
t0 = time.time()
hit = []
nofilter = links = 0
for code, name in sample:
    if not _is_main_a_share(code):
        nofilter += 1
        continue
    bars = _load_bars(code)
    if bars:
        links += 1
    try:
        recs = eng.scan_stock(code, name)
    except Exception as e:
        print("  !! %s 扫描异常: %s" % (code, e)); continue
    if recs:
        for r in recs:
            hit.append((code, name, r.get("pattern_name"), r.get("signal_level"),
                        r.get("trigger_type"), r.get("base_date"), r.get("base_price")))
print("样本 %d 只：通过过滤 %d / 未通过 %d；拿到K线 %d 只；耗时 %.1f 秒"
      % (len(sample), len(sample) - nofilter, nofilter, links, time.time() - t0))
print("产出记录 %d 条：" % len(hit))
for h in hit[:25]:
    print("   %s %-8s %-10s [%s] %s 基准日%s 基准价%s" % h)
