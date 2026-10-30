import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\QuantMonitorV6")
from services.band_pattern_engine import _load_bars
for code, wd in [("603230","2026-08-31"),("605577","2026-08-31"),("600088","2026-08-31")]:
    bars = _load_bars(code)
    si = next(i for i,b in enumerate(bars) if b["date"][:10] >= wd)
    print("== %s 启动周 %s 收盘 %.2f" % (code, bars[si]["date"][:10], bars[si]["close"]))
    for b in bars[si:si+22]:
        print("   %s  收 %.2f  量 %d" % (b["date"][:10], b["close"], b["volume"]))
