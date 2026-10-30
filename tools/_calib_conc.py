import sys, sqlite3
from collections import Counter
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from services.market_rhythm_engine import split_reason, _is_attribute

MB = ('600','601','603','605','000','001','002','003')
con = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
con.row_factory = sqlite3.Row
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM limit_up_reasons ORDER BY date DESC LIMIT 40")]
dates = sorted(dates)
print("近 %d 个交易日的题材集中度（最大题材家数 / 主板涨停家数）:" % len(dates))
vals = []
for d in dates:
    rows = con.execute("SELECT code,reason FROM limit_up_reasons WHERE date=?", (d,)).fetchall()
    mb = [r for r in rows if str(r["code"])[:3] in MB]
    c = Counter()
    for r in mb:
        for t in split_reason(r["reason"]):
            if not _is_attribute(t):
                c[t] += 1
    n = len(mb)
    if n < 10:
        print("   %s  涨停%2d家  样本太少跳过" % (d, n)); continue
    top, topn = c.most_common(1)[0]
    share = topn / float(n)
    vals.append(share)
    print("   %s  涨停%3d家  最大题材 %-8s %2d家  = %5.1f%%" % (d, n, top, topn, share * 100))
con.close()
vals.sort()
def pct(p):
    if not vals: return 0
    i = min(len(vals) - 1, int(round(p * (len(vals) - 1))))
    return vals[i] * 100
print()
print("分布：最小 %.1f%%  25分位 %.1f%%  中位 %.1f%%  75分位 %.1f%%  90分位 %.1f%%  最大 %.1f%%"
      % (vals[0] * 100, pct(0.25), pct(0.5), pct(0.75), pct(0.9), vals[-1] * 100))
