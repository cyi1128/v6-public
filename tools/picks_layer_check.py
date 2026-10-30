# -*- coding: utf-8 -*-
"""可介入信号分层检验：看哪一类子集的期望值不是负的

维度（都是入库时就有的字段，不需要额外取数）：
  A. 入选时涨幅 pct0      1~3% / 3~6% / 6~9%
  B. 入选时量比 vol_ratio  1.2~2 / 2~3 / 3~5 / ≥5
  C. 入场价 base_price     6~10 / 10~20 / 20~40 / ≥40
只做统计，不改任何筛选口径。
"""
import os
import sys
import json

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

from services.picks_tracking_service import fetch_tracking, summarize

rows = fetch_tracking()
print('总样本 %d 条' % len(rows))

OUT = []


def bucket(name, fn, edges):
    """edges: [(lo, hi, label), ...]"""
    OUT.append('')
    OUT.append('=' * 96)
    OUT.append(name)
    OUT.append('-' * 96)
    OUT.append('%-16s %7s | %-26s | %-26s | %-26s' %
               ('分组', '样本', '5日 胜率/均值', '30日 胜率/均值', '累计 胜率/均值'))
    for lo, hi, lbl in edges:
        sub = [r for r in rows if fn(r) is not None and lo <= fn(r) < hi]
        if not sub:
            OUT.append('%-16s %7d | %s' % (lbl, 0, '（无样本）'))
            continue
        s = summarize(sub)
        cells = []
        for k in ('r5', 'r30', 'cum'):
            v = s.get(k) or {}
            if v.get('n'):
                cells.append('%5.1f%% / %+6.2f%% (n=%d)' %
                             (v['win'], v['avg'], v['n']))
            else:
                cells.append('%s' % ('样本不足'))
        OUT.append('%-16s %7d | %-26s | %-26s | %-26s' %
                   (lbl, len(sub), cells[0], cells[1], cells[2]))


bucket('A. 入选时涨幅 pct0',
       lambda r: r.get('pct0'),
       [(0, 3, '1~3%'), (3, 6, '3~6%'), (6, 9.01, '6~9%')])

bucket('B. 入选时量比 vol_ratio',
       lambda r: r.get('vol_ratio'),
       [(1.2, 2, '1.2~2'), (2, 3, '2~3'), (3, 5, '3~5'), (5, 1e9, '≥5')])

bucket('C. 入选价 base_price',
       lambda r: r.get('base_price'),
       [(6, 10, '6~10元'), (10, 20, '10~20元'),
        (20, 40, '20~40元'), (40, 1e9, '≥40元')])

# ---- 交叉：低涨幅 + 高量比（最常见的"启动前放量"形态）----
OUT.append('')
OUT.append('=' * 96)
OUT.append('D. 交叉筛选（量比 × 涨幅）')
OUT.append('-' * 96)
combos = [
    ('量比≥2 且 涨幅1~5%', lambda r: r.get('vol_ratio', 0) >= 2 and 1 <= r.get('pct0', 0) < 5),
    ('量比≥3 且 涨幅1~5%', lambda r: r.get('vol_ratio', 0) >= 3 and 1 <= r.get('pct0', 0) < 5),
    ('量比≥3 且 涨幅<3%', lambda r: r.get('vol_ratio', 0) >= 3 and r.get('pct0', 0) < 3),
    ('量比≥2 且 价6~15元', lambda r: r.get('vol_ratio', 0) >= 2 and 6 <= r.get('base_price', 0) < 15),
    ('量比≥3 且 价6~15元', lambda r: r.get('vol_ratio', 0) >= 3 and 6 <= r.get('base_price', 0) < 15),
]
for lbl, fn in combos:
    sub = [r for r in rows if fn(r)]
    if not sub:
        OUT.append('%-22s %7d | （无样本）' % (lbl, 0))
        continue
    s = summarize(sub)
    cells = []
    for k in ('r5', 'r30', 'cum'):
        v = s.get(k) or {}
        cells.append('%5.1f%% / %+6.2f%% (n=%d)' % (v['win'], v['avg'], v['n'])
                     if v.get('n') else '样本不足')
    OUT.append('%-22s %7d | 5日 %-24s | 30日 %-24s | 累计 %s'
               % (lbl, len(sub), cells[0], cells[1], cells[2]))

txt = '\n'.join(OUT)
print(txt)
open(r"D:\QuantMonitorV6\tools\picks_layer_check.txt", 'w',
     encoding='utf-8').write(txt)
print('\n已写 tools\\picks_layer_check.txt')

# 给可视化用的 JSON
data = {'total': len(rows), 'r5': summarize(rows)['r5'],
        'r30': summarize(rows)['r30'], 'cum': summarize(rows)['cum']}
print('\nJSON:' + json.dumps(data, ensure_ascii=False))
