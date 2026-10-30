# -*- coding: utf-8 -*-
"""端到端：调用真实引擎，看龙头 tooltip 里的封单额有没有值。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.board_anomaly_engine import get_board_anomaly, get_flat_rows  # noqa

d = get_board_anomaly(force=True)
print('ok=%s  数据日=%s  涨停库=%s  涨停%d只  实时行情%d只  error=%s'
      % (d.get('ok'), d.get('date'), d.get('ludate'), d.get('lu_count', 0),
         d.get('rt_count', 0), d.get('error') or '无'))
rows = get_flat_rows(d)
print('拍平后 %d 行（题材 %d + 行业 %d）'
      % (len(rows), len(d.get('themes') or []), len(d.get('industries') or [])))
print()
print('%-18s %-9s %-4s %-13s %-6s %s'
      % ('板块/题材', '龙头', '连板', '封单', '炸板', '首封'))
print('-' * 86)
nz = 0
for r in rows[:16]:
    dg = (r.get('dragons') or [{}])[0]
    f = dg.get('fund') or 0
    nz += 1 if f else 0
    print('%-18s %-9s %-4s %-13s %-6s %s'
          % (r.get('name', '')[:16], dg.get('name', '--') or '--',
             dg.get('lbc', 0) or '-',
             ('%.2f亿' % (f / 1e8)) if f else '0.00亿 ←空',
             dg.get('zbc', 0) or '-', dg.get('time') or '--'))
print('-' * 86)
print('前 16 行封单额非零：%d / %d' % (nz, min(16, len(rows))))
