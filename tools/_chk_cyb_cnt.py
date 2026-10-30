import sys, duckdb
sys.stdout.reconfigure(encoding="utf-8")
try:
    con = duckdb.connect(r"D:\QuantMonitorV6\data\cache\kline_cache.duckdb", read_only=True)
    print("  30开头代码数:", con.execute("SELECT COUNT(DISTINCT code) FROM kline_cache WHERE code LIKE '30%'").fetchone()[0])
except Exception as e:
    print("  读不到(被写锁占用):", str(e)[:60])
