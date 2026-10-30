import sys
from collections import Counter
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import services.market_rhythm_engine as M
d = M.get_rhythm(force=True)
rows = M._load_day(d["date"])
c = Counter()
for r in rows:
    for t in M.split_reason(r.get("reason")):
        c[t] += 1
real = [(k, v) for k, v in c.items() if not M._is_attribute(k)]
real.sort(key=lambda x: -x[1])
print("今日涨停 %d 家，拆出真题材 %d 个（已去掉属性词 %d 个）" % (
    len(rows), len(real), len(c) - len(real)))
print("   >=2 家（进表）:", sum(1 for _, v in real if v >= 2))
print("   ==1 家（不进表）:", sum(1 for _, v in real if v == 1))
print()
print("全部真题材（按家数）:")
for k, v in real:
    print("   %-14s %d家 %s" % (k, v, "进表" if v >= 2 else "--- 1家未进"))
