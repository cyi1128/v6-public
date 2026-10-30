# -*- coding: utf-8 -*-
"""V20 建仓因子逐锚点增量检验（第 4 轮）

第 3 轮 [7] 段显示：控盘高分区基准本身就随锚点剧烈波动
  (k20 -3.28% / k40 +3.21% / k60 +6.89% / k80 -6.57%)
而三维组合的样本 63% 落在 k60 -> 汇总值可能是锚点构成偏差（Simpson 悖论）。

本轮逐锚点算【同锚点内的增量】，只有 4 个锚点方向一致才算可信。
只统计，不改引擎。
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

O = pd.read_csv(os.path.join(ROOT, 'tools', 'build_factor_calibration.csv'),
                encoding='utf-8-sig')
OUT = os.path.join(ROOT, 'tools', 'build_factor_calibration4.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


K = (20, 40, 60, 80)


def per_anchor(nm, mask, base_mask=None):
    """逐锚点输出组内均值，以及相对同锚点基准的增量。"""
    P('   ' + nm)
    deltas = []
    for k in K:
        s = O[mask & (O.k == k)]
        if base_mask is None:
            b = None
        else:
            b = O[base_mask & (O.k == k)]
        if len(s) < 12:
            P('      k%-3d n=%4d  (样本太少，不参与判定)' % (k, len(s)))
            continue
        if b is None or len(b) < 12:
            P('      k%-3d n=%4d | r20=%+6.2f%% 胜率=%5.1f%%' %
              (k, len(s), s.r20.mean(), 100 * (s.r20 > 0).mean()))
            continue
        d = s.r20.mean() - b.r20.mean()
        deltas.append(d)
        P('      k%-3d n=%4d | 组=%+6.2f%% 同锚点基准=%+6.2f%% | 增量=%+6.2fpt 胜率=%5.1f%%'
          % (k, len(s), s.r20.mean(), b.r20.mean(), d, 100 * (s.r20 > 0).mean()))
    if deltas:
        sign = '全部同号' if (all(x > 0 for x in deltas) or all(x < 0 for x in deltas)) else '符号不一致'
        P('      => 4 锚点增量: %s  平均 %+.2fpt  【%s】'
          % (', '.join('%+.2f' % x for x in deltas), np.mean(deltas), sign))
    P('')


P('=' * 112)
P('V20 建仓因子逐锚点增量检验（第 4 轮）')
P('=' * 112)
P('   判据：只有 4 个锚点【同锚点增量同号】才算可信；只汇总是锚点构成偏差。')
P('')

B2 = (O.score >= 85) & (O.pos120 < 0.25)

P('=' * 112)
P('[1] 孤立使用（原草案口径）：相对【全样本】的增量')
P('=' * 112)
per_anchor('1.1 s_ok 且 r_ok（堆量高 + 红肥绿瘦）', (O.s_ok == 1) & (O.r_ok == 1), None)
per_anchor('1.2 s_score>=50 且 r_ratio>=1.10', (O.s_score >= 50) & (O.r_ratio >= 1.10), None)
per_anchor('1.3 仅 s_ok（堆量）', O.s_ok == 1, None)
per_anchor('1.4 仅 r_ok（红肥绿瘦）', O.r_ok == 1, None)
per_anchor('1.5 反向 s_ratio<1.0 且 r_ratio<0.90', (O.s_ratio < 1.00) & (O.r_ratio < 0.90), None)

P('=' * 112)
P('[2] 条件使用：相对【控盘高分区】同锚点基准的增量')
P('=' * 112)
per_anchor('2.0 控盘高分区基准本身', B2, None)
per_anchor('2.1 + s_score>=40 且 r_ratio>=1.10', B2 & (O.s_score >= 40) & (O.r_ratio >= 1.10), B2)
per_anchor('2.2 + s_score>=45 且 r_ratio>=1.10', B2 & (O.s_score >= 45) & (O.r_ratio >= 1.10), B2)
per_anchor('2.3 + s_score>=50 且 r_ratio>=1.10', B2 & (O.s_score >= 50) & (O.r_ratio >= 1.10), B2)
per_anchor('2.4 + s_ok 且 r_ok', B2 & (O.s_ok == 1) & (O.r_ok == 1), B2)
per_anchor('2.5 + r_ratio>=1.10（只用红肥绿瘦）', B2 & (O.r_ratio >= 1.10), B2)
per_anchor('2.6 + s_ratio 在 0.80~1.00（温和堆量区间）',
           B2 & (O.s_ratio >= 0.80) & (O.s_ratio < 1.00), B2)
per_anchor('2.7 + s_score>=60', B2 & (O.s_score >= 60), B2)
per_anchor('2.8 反向 + r_ratio<0.90（红瘦绿肥）', B2 & (O.r_ratio < 0.90), B2)
per_anchor('2.9 + s_score>=40 且 r_score>=40', B2 & (O.s_score >= 40) & (O.r_score >= 40), B2)

P('=' * 112)
P('[3] 锚点构成核对（为什么汇总会骗人）')
P('=' * 112)
both = B2 & (O.s_score >= 40) & (O.r_ratio >= 1.10)
P('   组合总样本 %d 条，各锚点占比：' % both.sum())
for k in K:
    n1 = int((both & (O.k == k)).sum())
    n0 = int((B2 & (O.k == k)).sum())
    P('      k%-3d 组合 %4d 条 (%.1f%%) | 同锚点基准 %4d 条 | 该锚点基准 r20=%+6.2f%%'
      % (k, n1, 100.0 * n1 / max(1, both.sum()), n0, O[B2 & (O.k == k)].r20.mean()))
P('   组合加权均值 %.2f%% = Σ(占比 x 组内均值)，锚点间差异远大于效应量 -> 汇总量不可用于判定'
  % O[both].r20.mean())

_fh.close()
print('\n已写:', OUT)
