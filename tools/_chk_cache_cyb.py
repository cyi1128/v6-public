# -*- coding: utf-8 -*-
import sys, duckdb
sys.stdout.reconfigure(encoding="utf-8")
con = duckdb.connect(r"D:\QuantMonitorV6\data\cache\kline_cache.duckdb", read_only=True)
tot = con.execute("SELECT COUNT(DISTINCT code) FROM kline_cache").fetchone()[0]
print("kline_cache 股票总数: %d" % tot)
for pre, label in [("60", "沪主板"), ("00", "深主板"), ("30", "创业板"), ("68", "科创板"), ("8", "北交所"), ("4", "北交所")]:
    n = con.execute("SELECT COUNT(DISTINCT code) FROM kline_cache WHERE code LIKE ?", [pre + "%"]).fetchone()[0]
    print("   %s开头(%s): %d 只" % (pre, label, n))
r = con.execute("SELECT MIN(date), MAX(date) FROM kline_cache").fetchone()
print("   日期范围: %s ~ %s" % (r[0], r[1]))
sample = con.execute("SELECT DISTINCT code FROM kline_cache WHERE code LIKE '30%' ORDER BY code LIMIT 5").fetchall()
print("   创业板样例: %s" % [x[0] for x in sample])
