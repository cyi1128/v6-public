# -*- coding: utf-8 -*-
"""侦察：DuckDB 表结构 + 日线覆盖范围"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import duckdb

DB = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'
con = duckdb.connect(DB, read_only=True)
print("TABLES:", [r[0] for r in con.execute("SHOW TABLES").fetchall()])
for (t,) in con.execute("SHOW TABLES").fetchall():
    print("\n== DESCRIBE", t, "==")
    for row in con.execute(f"DESCRIBE {t}").fetchall():
        print("  ", row[0], row[1])
print("\n== kline_cache date range / codes ==")
try:
    print(con.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM kline_cache").fetchall())
    print("codes:", con.execute("SELECT DISTINCT code FROM kline_cache ORDER BY code").fetchall())
except Exception as e:
    print("err:", e)
con.close()
