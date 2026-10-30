# -*- coding: utf-8 -*-
"""导出 2026-10-09 全部涨停股的 市值/封单额/连板，用于画图。"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
con = sqlite3.connect(r'D:\QuantMonitorV6\data\limit_up_reason.db')
rows = con.execute(
    "SELECT name,lbc,fund,ltsz,time,zbc,hs FROM limit_up_reasons "
    "WHERE date='20261009' AND fund>0 AND ltsz>0 ORDER BY fund DESC").fetchall()
con.close()

print('// name, 连板, 封单额(亿), 流通市值(亿), 首封, 炸板, 换手')
for n, lbc, f, l, t, z, h in rows:
    print("[%r, %d, %.4f, %.2f, %r, %d, %.2f],"
          % (n, lbc or 0, f / 1e8, l / 1e8, t or '', z or 0, h or 0))
print()
print('共 %d 只' % len(rows))
