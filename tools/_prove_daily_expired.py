# -*- coding: utf-8 -*-
"""统计日K建仓表里展示的记录，有多少已过期"""
import sqlite3, collections

TODAY = '2026-09-24'
con = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
rows = con.execute(
    "select code,name,pattern_id,pattern_name,push_date,valid_until,signal_level,base_date "
    "from pattern_record where signal_level in ('建仓触发','等待确认')").fetchall()
print('展示条件: signal_level in (建仓触发, 等待确认)')
print('展示总条数:', len(rows))
print()
c = collections.Counter()
for r in rows:
    exp = (r[5] or '') < TODAY
    c[(r[2], '已过期' if exp else '有效')] += 1
for k in sorted(c):
    print('   模式%d %s: %d 条' % (k[0], k[1], c[k]))
print()
print('push_date 分布:', dict(collections.Counter(r[4] for r in rows)))
print('valid_until 分布:', dict(collections.Counter(r[5] for r in rows)))
print()
print('模式1/2/3 且已过期（不会被自动失效）的样例：')
n = 0
for r in rows:
    if r[2] in (1, 2, 3) and (r[5] or '') < TODAY:
        print('   %s %-8s 模式%d %-6s base_date=%s push_date=%s valid_until=%s %s'
              % (r[0], r[1][:6], r[2], r[3], r[7], r[4], r[5], r[6]))
        n += 1
        if n >= 8:
            break
print()
tot = collections.Counter(r[2] for r in rows)
print('展示记录按模式: ', dict(sorted(tot.items())))
con.close()
