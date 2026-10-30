# -*- coding: utf-8 -*-
"""看涨停库里 reason 的真实格式和来源分布 -> 决定采集怎么写"""
import os
import sqlite3
import sys

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")
c = sqlite3.connect(r"D:\QuantMonitorV6\data\limit_up_reason.db")
c.row_factory = sqlite3.Row

print('=' * 72)
print('按 source 统计')
print('=' * 72)
for r in c.execute('SELECT source, COUNT(*) n, MIN(date) a, MAX(date) b, '
                   'SUM(CASE WHEN reason LIKE "%+%" THEN 1 ELSE 0 END) withplus '
                   'FROM limit_up_reasons GROUP BY source ORDER BY n DESC'):
    print('  %-22s 行数%-7d %s ~ %s   含+号 %d' % (
        r['source'], r['n'], r['a'], r['b'], r['withplus']))

print()
print('=' * 72)
print('最近 3 个交易日 reason 抽样（看格式）')
print('=' * 72)
for d in ['20260930', '20260929', '20260928']:
    print('\n  --- %s ---' % d)
    for r in c.execute('SELECT code,name,industry,reason,source,lbc FROM limit_up_reasons '
                       'WHERE date=? LIMIT 8', (d,)):
        print('   %s %-7s [行业]%-10s [原因]%-30s src=%s 连板%s' % (
            r['code'], r['name'], r['industry'], r['reason'], r['source'], r['lbc']))

print()
print('=' * 72)
print('reason 出现的频率（TOP 25，看是不是真题材）')
print('=' * 72)
for r in c.execute('SELECT reason, COUNT(*) n FROM limit_up_reasons '
                   'WHERE date>="20260901" GROUP BY reason ORDER BY n DESC LIMIT 25'):
    print('  %-40s %d' % (r['reason'], r['n']))

print()
print('=' * 72)
print('每天行数（近 15 个交易日）')
print('=' * 72)
for r in c.execute('SELECT date, COUNT(*) n FROM limit_up_reasons '
                   'GROUP BY date ORDER BY date DESC LIMIT 15'):
    print('  %s  %d 只' % (r['date'], r['n']))
c.close()
