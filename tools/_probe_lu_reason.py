# -*- coding: utf-8 -*-
"""探查涨停原因库：规模、来源、样例、单只查询耗时（只读）。"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import data.limit_up_reason_db as L   # noqa: E402

print('DB:', L.DB_PATH, os.path.getsize(L.DB_PATH), '字节')
print('stats:', L.get_stats())

c = sqlite3.connect(L.DB_PATH)
c.row_factory = sqlite3.Row
print('来源分布:', [tuple(r) for r in c.execute(
    "select source, count(*) from limit_up_reasons group by source")])
print('最近 8 条带 + 的题材:')
for r in c.execute("select code,name,date,lbc,reason,industry,source from limit_up_reasons "
                   "where reason like '%+%' order by date desc limit 8"):
    print('   ', dict(r))
codes = [r[0] for r in c.execute("select distinct code from limit_up_reasons")]
print('库里出现过的股票数:', len(codes))
c.close()

t = time.perf_counter()
for x in codes[:300]:
    L.get_last_limit_up_reason(x)
dt = time.perf_counter() - t
print('300 次单只查询 %.2fs -> 4400 只推算 %.1fs' % (dt, dt / 300 * 4400))

# 命中率抽样（含 3 个真实代码）
for x in codes[:5] + ['600203', '000779', '300821']:
    print('  %s -> %s' % (x, L.get_last_limit_up_reason(x)))
