# -*- coding: utf-8 -*-
"""验证：DB 模式名/触发条件已去掉"模式N"字样 + UI 显示层映射"""
import sys, sqlite3
sys.path.insert(0, r'D:\QuantMonitorV6')

con = sqlite3.connect(r'D:\QuantMonitorV6\data\cache\band_pattern.db')
con.row_factory = sqlite3.Row
print('=== DB pattern_name 去重（应无"模式一/二/三/四"） ===')
for r in con.execute('SELECT DISTINCT pattern_id, pattern_name FROM pattern_record ORDER BY pattern_id').fetchall():
    print('  模式%d -> %s' % (r['pattern_id'], r['pattern_name']))
print()
print('=== DB trigger_type 去重 ===')
for r in con.execute('SELECT DISTINCT trigger_type FROM pattern_record ORDER BY trigger_type').fetchall():
    print('  %s' % r['trigger_type'])
print()
print('总记录', con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0])
con.close()

print()
print('=== UI 显示层映射验证（旧值也能正确显示） ===')
import ui.battle_widgets.atr_t_widget as m
for k, v in m._PATTERN_SHORT.items():
    print('  %s -> %s' % (k, v))
for k, v in m._TRIGGER_SHORT.items():
    print('  %s -> %s' % (k, v))

print()
print('=== 风控状态文字 ===')
for rs in ['正常(VWAP上方)', '正常(VWAP下方)']:
    print('  %s -> %s' % (rs, m.AtrTWidget._short_risk({'risk_status': rs})))

print()
print('=== UI 表格最终将显示的 模式/触发条件（前8行） ===')
from services.band_pattern_engine import query_signals
sigs = query_signals() or []
n = 0
for s in sigs:
    if s.get('signal_level') not in ('建仓触发', '等待确认'):
        continue
    pn = m._PATTERN_SHORT.get(s.get('pattern_name', ''), s.get('pattern_name', ''))
    tt = m._TRIGGER_SHORT.get(s.get('trigger_type', ''), s.get('trigger_type', ''))
    print('  %s %-6s 模式=%-6s 状态=%-5s 触发条件=%s'
          % (s['code'], (s.get('name') or '')[:6], pn, s.get('signal_level'), tt))
    n += 1
    if n >= 8:
        break
print('  ... 表格共', sum(1 for s in sigs if s.get('signal_level') in ('建仓触发', '等待确认')), '行')
