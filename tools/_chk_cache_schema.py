import sys, duckdb
sys.stdout.reconfigure(encoding="utf-8")
con = duckdb.connect(r"D:\QuantMonitorV6\data\cache\kline_cache.duckdb", read_only=True)
for t in con.execute("SHOW TABLES").fetchall():
    print(" 表:", t[0])
    print("   ", con.execute("DESCRIBE " + t[0]).df().to_string().replace("\n", "\n    "))
print(" 样例行:", con.execute("SELECT * FROM kline_cache WHERE code='300207' ORDER BY date DESC LIMIT 2").fetchall())
print(" 300207 行数:", con.execute("SELECT COUNT(*) FROM kline_cache WHERE code='300207'").fetchone()[0])
