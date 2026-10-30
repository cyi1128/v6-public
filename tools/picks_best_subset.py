# -*- coding: utf-8 -*-
"""验证最有希望的子集：低价(6~10元) + 温和启动(涨幅1~3%)

分层检验里只有这一组在 30 日维度同时做到「胜率>50% 且 均值为正」，
且样本量够大。再叠加量比条件看还能不能更好。
"""
import os
import sys

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

from services.picks_tracking_service import fetch_tracking, summarize

rows = fetch_tracking()
print('总样本 %d 条\n' % len(rows))

CASES = [
    ('基准：全部可介入标的',
     lambda r: True),
    ('低价 6~10元',
     lambda r: 6 <= r.get('base_price', 0) < 10),
    ('温和启动：涨幅 1~3%',
     lambda r: 1 <= r.get('pct0', 0) < 3),
    ('低价6~10元 + 涨幅1~3%',
     lambda r: 6 <= r.get('base_price', 0) < 10 and 1 <= r.get('pct0', 0) < 3),
    ('低价6~10元 + 涨幅1~3% + 量比≥1.5',
     lambda r: (6 <= r.get('base_price', 0) < 10 and 1 <= r.get('pct0', 0) < 3
                and r.get('vol_ratio', 0) >= 1.5)),
    ('低价6~10元 + 涨幅1~3% + 量比≥2',
     lambda r: (6 <= r.get('base_price', 0) < 10 and 1 <= r.get('pct0', 0) < 3
                and r.get('vol_ratio', 0) >= 2)),
    ('低价6~10元 + 涨幅1~3% + 量比 1.2~2',
     lambda r: (6 <= r.get('base_price', 0) < 10 and 1 <= r.get('pct0', 0) < 3
                and 1.2 <= r.get('vol_ratio', 0) < 2)),
]

lines = []
lines.append('%-38s %6s | %-24s | %-24s | %-24s' %
             ('组合', '样本', '5日 胜率/均值', '30日 胜率/均值', '累计 胜率/均值'))
lines.append('-' * 130)
for lbl, fn in CASES:
    sub = [r for r in rows if fn(r)]
    if not sub:
        lines.append('%-38s %6d | （无样本）' % (lbl, 0))
        continue
    s = summarize(sub)
    cells = []
    for k in ('r5', 'r30', 'cum'):
        v = s.get(k) or {}
        if v.get('n'):
            cells.append('%5.1f%% / %+6.2f%% (n=%3d)' % (v['win'], v['avg'], v['n']))
        else:
            cells.append('样本不足')
    lines.append('%-38s %6d | %-24s | %-24s | %-24s'
                 % (lbl, len(sub), cells[0], cells[1], cells[2]))

txt = '\n'.join(lines)
print(txt)
open(r"D:\QuantMonitorV6\tools\picks_best_subset.txt", 'w',
     encoding='utf-8').write(txt)
print('\n已写 tools\\picks_best_subset.txt')
