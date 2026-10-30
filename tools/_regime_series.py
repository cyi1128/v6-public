import sys, sqlite3
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import duckdb
MB = "('600','601','603','605','000','001','002','003')"
con = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
lu = dict(con.execute("SELECT date, COUNT(*) FROM limit_up_reasons WHERE substr(code,1,3) IN %s GROUP BY date" % MB).fetchall())
con.close()
days = sorted(lu)
k = duckdb.connect(r"D:\QuantMonitorV6\data\cache\kline_cache.duckdb", read_only=True)
tr = k.execute("""
  WITH s AS (SELECT CAST(code AS VARCHAR) code, date, close,
             LAG(close) OVER (PARTITION BY code ORDER BY date) pc FROM kline_cache
             WHERE substr(CAST(code AS VARCHAR),1,3) IN %s),
  r AS (SELECT date, avg(close/pc-1.0) ret FROM s WHERE pc IS NOT NULL AND pc>0 GROUP BY date),
  e AS (SELECT date, exp(sum(ln(1+ret)) OVER (ORDER BY date))*100 idx FROM r WHERE ret>-0.5)
  SELECT date, idx, avg(idx) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ma20 FROM e
""" % MB).fetchall()
k.close()
dev = {r[0]: (r[1]/r[2]-1)*100 for r in tr if r[2]}
out = []
for i, d in enumerate(days):
    w = [lu[x] for x in days[max(0,i-20):i]]
    if len(w) < 8: continue
    mu = sum(w)/len(w); sd = (sum((x-mu)**2 for x in w)/len(w))**0.5
    z = (lu[d]-mu)/sd if sd else 0.0
    v = dev.get(d[:4]+"-"+d[4:6]+"-"+d[6:])
    if v is None: continue
    out.append(("%s-%s" % (d[4:6], d[6:]), lu[d], round(z,2), round(v,2)))
out = out[-40:]
print("DATES =", repr([o[0] for o in out]))
print()
print("Z =", repr([o[2] for o in out]))
print()
print("DEV =", repr([o[3] for o in out]))
print()
print("LU =", repr([o[1] for o in out]))
