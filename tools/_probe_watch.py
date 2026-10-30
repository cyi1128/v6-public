# -*- coding: utf-8 -*-
"""查 watchlist 7只股票各自的日线日期覆盖"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import duckdb, json
DB = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'
codes = [d['code'] for d in json.load(open(r'D:\QuantMonitorV6\data\watchlist.json', encoding='utf-8'))]
con = duckdb.connect(DB, read_only=True)
for c in codes:
    r = con.execute("SELECT MIN(date),MAX(date),COUNT(*) FROM kline_cache WHERE code=?", [c]).fetchone()
    print(c, r)
con.close()
