# -*- coding: utf-8 -*-
"""验收 ①②③⑤：新旧排序键对比 + 端到端跑引擎 + 接力参考。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
import py_compile

py_compile.compile(r'D:\QuantMonitorV6\services\board_anomaly_engine.py',
                   doraise=True)
print('py_compile OK')

from services.board_anomaly_engine import (                      # noqa: E402
    _dragon_key, _entry_key, _entry_of, _seal_slot, _seal_strength,
    _load_limit_up, get_board_anomaly, get_flat_rows)

ludate, recs = _load_limit_up()
print('涨停库数据日=%s  %d 只' % (ludate, len(recs)))

print()
print('=' * 96)
print('一、封板时段分档（③⑤）—— 今天 69 只落在哪些档')
print('=' * 96)
from collections import defaultdict                                # noqa: E402
d = defaultdict(list)
for r in recs:
    idx, label = _seal_slot(r.get('time'))
    d[(idx, label)].append(r['name'])
for (idx, label) in sorted(d):
    print('  档%d %-8s %2d 只  %s'
          % (idx, label, len(d[(idx, label)]),
             '、'.join(d[(idx, label)][:7])
             + ('…' if len(d[(idx, label)]) > 7 else '')))

print()
print('=' * 96)
print('二、同身位内，新旧键排序差异（拿 2 板组做样本）')
print('=' * 96)
two = [r for r in recs if (r.get('lbc') or 0) == 2]
old = sorted(two, key=lambda r: (r.get('time') or '99:99'))
new = sorted(two, key=lambda r: _dragon_key(r, {}))
print('  %-4s %-9s %-9s %8s %9s %7s   %-8s'
      % ('序号', '旧键', '新键', '封单(亿)', '流通市值', '强度', '时段'))
print('-' * 96)
for i in range(len(new)):
    o, n = old[i], new[i]
    idx, label = _seal_slot(n.get('time'))
    mark = '' if o['code'] == n['code'] else '  ← 变了'
    print('  %-4d %-9s %-9s %8.4f %9.1f %6.2f%%   %-8s%s'
          % (i + 1, o['name'], n['name'], n['fund'] / 1e8,
             n['ltsz'] / 1e8, _seal_strength(n) * 100, label, mark))

print()
print('=' * 96)
print('三、端到端：每个板块的情绪龙头 + 次日接力参考')
print('=' * 96)
bd = get_board_anomaly(force=True)
rows = get_flat_rows(bd)
print('引擎 ok=%s  拍平 %d 行' % (bd.get('ok'), len(rows)))
print()
print('%-12s %-16s %-20s %s' % ('板块/题材', '情绪龙头', '次日接力参考', '注明'))
print('-' * 96)
for r in rows[:14]:
    dg = (r.get('dragons') or [{}])[0]
    e = r.get('entry') or {}
    print('%-12s %-16s %-20s %s'
          % (r.get('name', '')[:10],
             '%s %d板 %s' % (dg.get('name', '--'), dg.get('lbc', 0),
                             dg.get('slot_name', '')),
             ('%s %d板 %s 强%.2f%%' % (e.get('name'), e.get('lbc'),
                                       e.get('slot_name'), e.get('strength', 0) * 100))
             if e else '（无合格标的）',
             ('龙头强度%.2f%%' % ((dg.get('strength') or 0) * 100))))
