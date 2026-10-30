# -*- coding: utf-8 -*-
"""V20 建仓因子阈值扫描（第 3 轮）：在「控盘高分区」内一维/二维扫，选组合门槛。

依据第 2 轮：全样本里两因子单调负相关，但在 score>=85 & pos<0.25 内翻正。
本轮只做扫描，不改引擎。
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

SRC = os.path.join(ROOT, 'tools', 'build_factor_calibration.csv')
OUT = os.path.join(ROOT, 'tools', 'build_factor_calibration3.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


O = pd.read_csv(SRC, encoding='utf-8-sig')
B2 = (O.score >= 85) & (O.pos120 < 0.25)
ref2 = O[B2].r20.mean()
P('=' * 112)
P('V20 建仓因子阈值扫描（第 3 轮）')
P('=' * 112)
P('   控盘高分区 score>=85 & pos<0.25 : n=%d  r20=%+.2f%% 胜率20=%.1f%%'
  % (B2.sum(), ref2, 100 * (O[B2].r20 > 0).mean()))
P('   全样本 : n=%d  r20=%+.2f%%' % (len(O), O.r20.mean()))


def line(nm, mask, ref):
    s = O[mask]
    if len(s) < 25:
        return '   %-52s n=%5d  (样本太少)' % (nm, len(s))
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    return ('   %-52s n=%5d | r20=%+6.2f%% 胜率20=%5.1f%% mdd20=%+7.2f%% t=%+5.2f  Δ=%+.2fpt'
            % (nm, len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(), s.mdd20.mean(), t,
               s.r20.mean() - ref))


# ============================================================
P('\n' + '=' * 112)
P('[1] 控盘高分区内 · 堆量分 s_score 阈值扫描')
P('=' * 112)
for T in (35, 40, 45, 50, 55, 60, 65, 70, 75):
    P(line('   s_score >= %-3d' % T, B2 & (O.s_score >= T), ref2))

P('\n' + '=' * 112)
P('[2] 控盘高分区内 · 红肥绿瘦比值 r_ratio 阈值扫描')
P('=' * 112)
for T in (0.95, 1.00, 1.05, 1.08, 1.10, 1.15, 1.20, 1.25):
    P(line('   r_ratio >= %.2f' % T, B2 & (O.r_ratio >= T), ref2))

P('\n' + '=' * 112)
P('[3] 控盘高分区内 · 堆量倍数 s_ratio 阈值扫描')
P('=' * 112)
for lo, hi in ((0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0), (1.0, 1.2), (1.2, 99)):
    P(line('   s_ratio[%.2f,%.2f)' % (lo, hi), B2 & (O.s_ratio >= lo) & (O.s_ratio < hi), ref2))

P('\n' + '=' * 112)
P('[4] 二维组合（控盘高分区内）：s_score x r_ratio')
P('=' * 112)
for T1 in (40, 45, 50, 55, 60):
    for T2 in (1.05, 1.10, 1.15):
        P(line('   s_score>=%d 且 r_ratio>=%.2f' % (T1, T2),
               B2 & (O.s_score >= T1) & (O.r_ratio >= T2), ref2))
    P('')

P('\n' + '=' * 112)
P('[5] 二维组合（控盘高分区内）：s_score x r_score')
P('=' * 112)
for T1 in (40, 45, 50, 55):
    for T2 in (30, 40, 50, 60):
        P(line('   s_score>=%d 且 r_score>=%d' % (T1, T2),
               B2 & (O.s_score >= T1) & (O.r_score >= T2), ref2))
    P('')

P('\n' + '=' * 112)
P('[6] 对照：同样的组合放到【全样本】上会怎样（说明必须挂在控盘高分区内）')
P('=' * 112)
for T1, T2 in ((50, 1.10), (55, 1.10), (50, 1.15)):
    P(line('   全样本 s_score>=%d 且 r_ratio>=%.2f' % (T1, T2),
           (O.s_score >= T1) & (O.r_ratio >= T2), O.r20.mean()))
P(line('   全样本 s_ok 且 r_ok（原草案口径）', (O.s_ok == 1) & (O.r_ok == 1), O.r20.mean()))

P('\n' + '=' * 112)
P('[7] 最终候选方案的稳健性检查（按 k 锚点切 4 段，看是否各段一致）')
P('=' * 112)
CAND = {
    '控盘高分区基准': B2,
    'A: s_score>=50 & r_ratio>=1.10': B2 & (O.s_score >= 50) & (O.r_ratio >= 1.10),
    'B: s_score>=55 & r_ratio>=1.10': B2 & (O.s_score >= 55) & (O.r_ratio >= 1.10),
    'C: s_score>=45 & r_ratio>=1.10': B2 & (O.s_score >= 45) & (O.r_ratio >= 1.10),
}
for nm, m in CAND.items():
    seg = []
    for k in (20, 40, 60, 80):
        s = O[m & (O.k == k)]
        seg.append('k%02d:%+5.2f%%(n=%d)' % (k, s.r20.mean(), len(s)) if len(s) >= 15
                   else 'k%02d:--' % k)
    s = O[m]
    P('   %-34s 总=%+6.2f%% n=%5d 胜率=%5.1f%% | %s'
      % (nm, s.r20.mean(), len(s), 100 * (s.r20 > 0).mean(), '  '.join(seg)))

P('\n' + '=' * 112)
P('[8] 同一方案的对照组：满足「控盘高分区」但不满足因子的那批')
P('=' * 112)
for nm, m in (('A 对照组（不满足两因子）', B2 & ~((O.s_score >= 50) & (O.r_ratio >= 1.10))),
              ('B 对照组（不满足两因子）', B2 & ~((O.s_score >= 55) & (O.r_ratio >= 1.10)))):
    P(line('   ' + nm, m, ref2))

_fh.close()
print('\n已写:', OUT)
