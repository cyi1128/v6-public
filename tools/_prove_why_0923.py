# -*- coding: utf-8 -*-
"""查引擎取数：kline_cache 里有哪些日期的数据，引擎为什么选到 9/23"""
import sys, os
sys.path.insert(0, r'D:\QuantMonitorV6')
import duckdb

print('=== 1. kline_cache.duckdb 最近日期分布 ===')
con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute("""
    select date, count(*) as n, max(update_time) as ut
    from kline_cache group by date order by date desc limit 8
""").fetchall()
for d, n, ut in rows:
    print('   %s   %6d 只   最后写入 %s' % (d, n, ut))
print()
print('=== 2. 单只股票最新几根（600675 中华企业）===')
r2 = con.execute("""
    select date, open, high, low, close, volume from kline_cache
    where code='600675' order by date desc limit 6
""").fetchall()
for x in r2:
    print('   ', x)
print()
print('=== 3. 是否已有 9/24 的K线 ===')
n24 = con.execute("select count(*) from kline_cache where date='2026-09-24'").fetchone()[0]
n23 = con.execute("select count(*) from kline_cache where date='2026-09-23'").fetchone()[0]
print('   2026-09-24 条数:', n24)
print('   2026-09-23 条数:', n23)
con.close()

print()
print('=== 4. 引擎取数函数 ===')
import io, re
s = io.open(r'D:\QuantMonitorV6\services\band_pattern_engine.py', encoding='utf-8').read()
for m in re.finditer(r'^def (_?load_bars|_?get_bars|_?fetch_bars|scan_all|_valid_until_cal)\b.*$', s, re.M):
    print('   找到:', m.group(0).strip())
print()
# 找 kline_cache 相关读取
for kw in ['kline_cache', 'fetch_kline', 'get_kline', 'bars =', 'date <', 'date >=']:
    idxs = [m.start() for m in re.finditer(re.escape(kw), s)]
    if idxs:
        print('   %-14s 出现 %d 次' % (kw, len(idxs)))
