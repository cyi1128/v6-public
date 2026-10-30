import sys, sqlite3, os
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
import duckdb
from services.regime_gate import Z_COLD, Z_HOT, TREND_DOWN

MB = "('600','601','603','605','000','001','002','003')"
con = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
rows = con.execute("SELECT date, COUNT(*) c FROM limit_up_reasons WHERE substr(code,1,3) IN %s GROUP BY date ORDER BY date" % MB).fetchall()
con.close()
lu = dict(rows)
days = sorted(lu.keys())

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

def zof(i):
    w = [lu[d] for d in days[max(0, i-20):i]]
    if len(w) < 8: return None
    mu = sum(w)/len(w); sd = (sum((x-mu)**2 for x in w)/len(w))**0.5
    return (lu[days[i]]-mu)/sd if sd else 0.0

recs = []
for i, d in enumerate(days):
    z = zof(i)
    v = dev.get(d[:4]+"-"+d[4:6]+"-"+d[6:])
    if z is None or v is None: continue
    recs.append((d, lu[d], z, v))

tail = recs[-40:]
cold = [r for r in tail if r[2] <= Z_COLD and r[3] < 0]
fade = [r for r in tail if not (r[2] <= Z_COLD and r[3] < 0) and r[3] <= TREND_DOWN]
hot  = [r for r in tail if not (r[2] <= Z_COLD and r[3] < 0) and not (r[3] <= TREND_DOWN) and r[2] >= Z_HOT]
norm = [r for r in tail if r not in cold and r not in fade and r not in hot]
print("近 %d 个交易日（有完整三轴读数的）状态分布：" % len(tail))
print("  冰点     %2d 天 (%.0f%%)  %s" % (len(cold), 100.0*len(cold)/len(tail), [x[0][4:] for x in cold]))
print("  退潮下行 %2d 天 (%.0f%%)  %s" % (len(fade), 100.0*len(fade)/len(tail), [x[0][4:] for x in fade][:12]))
print("  过热抱团 %2d 天 (%.0f%%)  %s" % (len(hot), 100.0*len(hot)/len(tail), [x[0][4:] for x in hot]))
print("  常温轮动 %2d 天 (%.0f%%)" % (len(norm), 100.0*len(norm)/len(tail)))
print()
print("日期   涨停  z      等权距MA20")
for r in tail[-14:]:
    tag = "冰点" if (r[2]<=Z_COLD and r[3]<0) else ("退潮" if r[3]<=TREND_DOWN else ("过热" if r[2]>=Z_HOT else "常温"))
    print("   %s  %3d  %+5.2f  %+6.2f%%   %s" % (r[0], r[1], r[2], r[3], tag))
