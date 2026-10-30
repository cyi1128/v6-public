# -*- coding: utf-8 -*-
"""看那 7 行 pct0 >= 5.0 的 BACKFILL 到底是多少（判断是否浮点四舍五入）。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb  # noqa: E402

con = duckdb.connect(r"D:\QuantMonitorV6\data\cache\picks_tracking.duckdb", read_only=True)
rs = con.execute(
    "SELECT trade_date, code, pct0 FROM picks_tracking "
    "WHERE base_source='BACKFILL' AND pct0 >= 5.0 ORDER BY pct0 DESC").fetchall()
print("这 7 行的实际 pct0（库内全精度）：")
for r in rs:
    print("   %s  %s  pct0=%.10f  %s" % (r[0], r[1], r[2],
                                        "== 5.0 恰好，说明入库时四舍五入"
                                        if abs(r[2] - 5.0) < 1e-9 else ""))
n = con.execute("SELECT COUNT(*) FROM picks_tracking WHERE base_source='BACKFILL'").fetchone()[0]
print()
print("占比：%d / %d = %.2f%%" % (len(rs), n, len(rs) / n * 100))
con.close()
