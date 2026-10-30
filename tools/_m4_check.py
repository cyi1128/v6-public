# -*- coding: utf-8 -*-
"""模式四 触发/等待 明细 + DB 总览"""
import sqlite3

con = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT code,name,signal_level,trigger_type,base_date,structure_days,"
    "up_days,up_vol_ok,up_rate,down_days,down_vol_ok,down_rate,"
    "struct_pos,recent_vol3,valid_until,note FROM pattern_record "
    "WHERE pattern_id=4 AND signal_level IN ('建仓触发','等待确认') "
    "ORDER BY signal_level"
).fetchall()
print('模式四 触发/等待 共', len(rows), '条')
for r in rows:
    print('---')
    for k in r.keys():
        print('  %-14s = %s' % (k, r[k]))

print()
print('=== DB 总览 ===')
for r in con.execute(
        'SELECT pattern_id, signal_level, COUNT(*) c FROM pattern_record '
        'GROUP BY pattern_id, signal_level ORDER BY pattern_id').fetchall():
    print('模式%d %s : %d' % (r['pattern_id'], r['signal_level'], r['c']))
print('总记录', con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0])

print()
print('=== 模式四结构天数分布（验证 8~20 日） ===')
for r in con.execute(
        'SELECT MIN(structure_days) mn, MAX(structure_days) mx, COUNT(*) c '
        'FROM pattern_record WHERE pattern_id=4').fetchall():
    print('结构天数 min=%s max=%s 条数=%s' % (r['mn'], r['mx'], r['c']))

print()
print('=== 模式四位置分布（验证 <=100% 未突破上沿） ===')
for r in con.execute(
        'SELECT MIN(struct_pos) mn, MAX(struct_pos) mx FROM pattern_record '
        'WHERE pattern_id=4').fetchall():
    print('结构位置 min=%s%% max=%s%%' % (r['mn'], r['mx']))

con.close()
