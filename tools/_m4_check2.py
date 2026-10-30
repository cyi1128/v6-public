# -*- coding: utf-8 -*-
"""模式四 触发/等待 明细（含题材） + 自动失效验证 + DB总览"""
import sys, sqlite3
sys.path.insert(0, r'D:\QuantMonitorV6')
from data.limit_up_reason_db import get_last_limit_up_reason

con = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT code,name,signal_level,trigger_type,base_date,structure_days,"
    "up_days,up_vol_ok,up_rate,down_days,down_vol_ok,down_rate,"
    "struct_pos,recent_vol3,valid_until,invalid_reason,note FROM pattern_record "
    "WHERE pattern_id=4 AND signal_level IN ('建仓触发','等待确认') "
    "ORDER BY signal_level, struct_pos DESC").fetchall()

print('模式四 触发/等待 共 %d 条' % len(rows))
for r in rows:
    th = get_last_limit_up_reason(r['code'])[0] or '--'
    print('  %s %s  [%s]  位置%.1f%%  上涨%d/%d(%.0f%%) 下跌%d/%d(%.0f%%) 最近3日=%s'
          % (r['code'], r['name'], r['signal_level'], r['struct_pos'],
             r['up_vol_ok'], r['up_days'], r['up_rate'],
             r['down_vol_ok'], r['down_days'], r['down_rate'],
             '是' if r['recent_vol3'] else '否'))
    print('      题材: %s' % th)
    print('      valid_until=%s  invalid_reason=%s' % (r['valid_until'], r['invalid_reason']))

print()
print('=== DB 总览 ===')
for r in con.execute('SELECT pattern_id, signal_level, COUNT(*) c FROM pattern_record '
                     'GROUP BY pattern_id, signal_level ORDER BY pattern_id').fetchall():
    print('  模式%d %s : %d' % (r['pattern_id'], r['signal_level'], r['c']))
print('  总记录', con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0])
r = con.execute('SELECT MIN(structure_days) a, MAX(structure_days) b FROM pattern_record WHERE pattern_id=4').fetchone()
print('  模式四结构天数 min=%s max=%s' % (r['a'], r['b']))
r = con.execute('SELECT MIN(struct_pos) a, MAX(struct_pos) b FROM pattern_record WHERE pattern_id=4').fetchone()
print('  模式四位置 min=%s%% max=%s%%' % (r['a'], r['b']))
r = con.execute('SELECT MIN(valid_until) a, MAX(valid_until) b FROM pattern_record WHERE pattern_id=4').fetchone()
print('  模式四 valid_until %s ~ %s' % (r['a'], r['b']))
con.close()

print()
print('=== 自动失效 expire_overdue() 验证 ===')
from services.band_pattern_engine import expire_overdue, query_signals
n = expire_overdue()
print('  本次标记失效记录数:', n)
sigs = query_signals()
print('  query_signals 返回:', len(sigs), '条')
from collections import Counter
print('  状态分布:', dict(Counter(s.get('signal_level') for s in sigs)))
print('  UI 实际显示(建仓触发+等待确认):',
      sum(1 for s in sigs if s.get('signal_level') in ('建仓触发', '等待确认')), '条')
