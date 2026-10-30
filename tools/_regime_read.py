import sys, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT date, COUNT(*) n FROM limit_up_reasons GROUP BY date ORDER BY date DESC LIMIT 30").fetchall()
con.close()
rows = list(reversed(rows))
print("最近 %d 个交易日涨停家数（源：limit_up_reasons，全部含创业板等，仅作温度读数）:" % len(rows))
for r in rows:
    print("   %s  %3d 家" % (r["date"], r["n"]))
ns = [r["n"] for r in rows]
w = ns[:-1][-20:]
mu = sum(w) / len(w)
var = sum((x - mu) ** 2 for x in w) / len(w)
sd = var ** 0.5
print()
print("20 日均值 = %.1f 家 | 标准差 = %.1f" % (mu, sd))
print("今日 %d 家 -> z = %+.2f" % (ns[-1], (ns[-1] - mu) / sd if sd else 0))
print("近5日 =", ns[-5:], " 前5日 =", ns[-10:-5])
