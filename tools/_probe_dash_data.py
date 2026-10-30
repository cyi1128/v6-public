# -*- coding: utf-8 -*-
"""探查仪表盘可用数据源。"""
import os, sqlite3, sys
sys.path.insert(0, r'D:\QuantMonitorV6')

p = r'D:\QuantMonitorV6\data\limit_up_reason.db'
if os.path.exists(p):
    c = sqlite3.connect(p); cur = c.cursor()
    print('tables:', [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")])
    try:
        cols = [r[1] for r in cur.execute('PRAGMA table_info(limit_up_reasons)')]
        print('limit_up_reasons cols:', cols)
        print('rows/maxdate:', cur.execute('SELECT COUNT(*), MAX(date) FROM limit_up_reasons').fetchone())
        print('sample:', cur.execute('SELECT * FROM limit_up_reasons ORDER BY date DESC LIMIT 2').fetchall())
    except Exception as e:
        print('lu err', e)
    c.close()
else:
    print('no limit_up_reason.db')

import duckdb
con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
print('kline tables:', [r[0] for r in con.execute('SHOW TABLES').fetchall()])
print('latest date:', con.execute('SELECT MAX(date) FROM klines').fetchone())
con.close()
