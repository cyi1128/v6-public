# -*- coding: utf-8 -*-
"""查封单额/炸板等字段到底有没有数据。"""
import io
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
DB = r'D:\QuantMonitorV6\data\limit_up_reason.db'
con = sqlite3.connect(DB)
try:
    d = con.execute('SELECT MAX(date) FROM limit_up_reasons').fetchone()[0]
    tot = con.execute('SELECT COUNT(*) FROM limit_up_reasons WHERE date=?',
                      (d,)).fetchone()[0]
    print('最新数据日 %s，共 %d 行' % (d, tot))
    print()
    print('=== 龙头排序用得到的字段，实际有没有值 ===')
    for col in ('time', 'lbc', 'fund', 'amount', 'hs', 'zbc', 'ltsz', 'industry'):
        nn = con.execute(
            "SELECT COUNT(*) FROM limit_up_reasons WHERE date=? AND %s IS NOT NULL "
            "AND %s != 0 AND %s != ''" % (col, col, col), (d,)).fetchone()[0]
        print('  %-9s 有值 %3d / %d  %s' % (col, nn, tot,
                                            'OK' if nn else '← 空'))
    print()
    print('=== 抽样 6 行 ===')
    for r in con.execute(
            'SELECT code,name,time,lbc,fund,amount,zbc FROM limit_up_reasons '
            'WHERE date=? LIMIT 6', (d,)):
        print('  ', r)
    print()
    print('=== 历史上 fund 有没有过值 ===')
    for dd, c in con.execute(
            'SELECT date, COUNT(*) FROM limit_up_reasons WHERE fund IS NOT NULL '
            'AND fund != 0 GROUP BY date ORDER BY date DESC LIMIT 5').fetchall():
        print('  %s  %d 行有封单额' % (dd, c))
finally:
    con.close()

print()
src = io.open(r'D:\QuantMonitorV6\services\limit_up_collector.py',
              encoding='utf-8').read()
i = src.find('def collect(')
print('=' * 78)
print('采集器 collect() 的写库语句')
print('=' * 78)
print(src[i:i + 1500])
