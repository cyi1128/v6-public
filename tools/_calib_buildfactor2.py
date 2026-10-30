# -*- coding: utf-8 -*-
"""V20 建仓因子补充检验：分档单调性 + 反向组合 + 控盘高分区内的增量

读 tools/build_factor_calibration.csv（17570 条），不重算 kline。
回答三个问题：
  Q1 全样本里 s_score / r_score 有没有任何一档是正的？
  Q2 在控盘高分区（score>=85 & pos<0.25）内部，两个因子分档是否单调？
  Q3 反向使用（低堆量 / 红瘦绿肥）是否稳定更好？组合起来如何？
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

SRC = os.path.join(ROOT, 'tools', 'build_factor_calibration.csv')
OUT = os.path.join(ROOT, 'tools', 'build_factor_calibration2.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


O = pd.read_csv(SRC, encoding='utf-8-sig')
BASE_R, BASE_W = O.r20.mean(), 100 * (O.r20 > 0).mean()
P('=' * 112)
P('V20 建仓因子补充检验（读 build_factor_calibration.csv，%d 条 / %d 只）' % (len(O), O.code.nunique()))
P('=' * 112)
P('   全样本基准: r20=%+.2f%%  胜率20=%.1f%%  mdd20=%+.2f%%' % (BASE_R, BASE_W, O.mdd20.mean()))


def show(nm, mask, ref=None):
    s = O[mask]
    if len(s) < 25:
        P('   %-44s n=%5d  (样本太少跳过)' % (nm, len(s)))
        return
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    d = '' if ref is None else '  Δ基准=%+.2fpt' % (s.r20.mean() - ref)
    P('   %-44s n=%5d | r20=%+6.2f%% 胜率20=%5.1f%% mdd20=%+7.2f%% t=%+5.2f%s'
      % (nm, len(s), s.r20.mean(), 100 * (s.r20 > 0).mean(), s.mdd20.mean(), t, d))


def spear(a, b):
    return pd.Series(a).rank().corr(pd.Series(b).rank())


def quint(nm, col, mask, asc=True):
    s = O[mask].copy()
    if len(s) < 100:
        P('   %s 样本不足' % nm)
        return
    try:
        s['q'] = pd.qcut(s[col], 5, labels=False, duplicates='drop')
    except Exception:
        return
    P('   %s  （%s）' % (nm, col))
    for q in sorted(s['q'].dropna().unique()):
        g = s[s['q'] == q]
        P('      Q%d  %-18s n=%5d | r20=%+6.2f%% 胜率20=%5.1f%% mdd20=%+7.2f%%'
          % (q + 1, '%.3f~%.3f' % (g[col].min(), g[col].max()), len(g),
             g.r20.mean(), 100 * (g.r20 > 0).mean(), g.mdd20.mean()))
    P('      rho(%s, r20) = %+.4f' % (col, spear(s[col], s.r20)))


# ============================================================
P('\n' + '=' * 112)
P('[Q1] 全样本：两个因子的分数每一档都是负的吗')
P('=' * 112)
for lo, hi in ((0, 40), (40, 55), (55, 65), (65, 70), (70, 80), (80, 101)):
    show('   stack 分[%d,%d)' % (lo, hi), (O.s_score >= lo) & (O.s_score < hi), BASE_R)
P('')
for lo, hi in ((0, 20), (20, 40), (40, 60), (60, 65), (65, 80), (80, 101)):
    show('   redfat 分[%d,%d)' % (lo, hi), (O.r_score >= lo) & (O.r_score < hi), BASE_R)
P('\n   -> 结论：两边的每一档都低于 0，且越高越差（没有一个正向档）')

# ============================================================
P('\n' + '=' * 112)
P('[Q2] 控盘高分区内部（score>=85 且 pos<0.25，n=3122）的分档单调性')
P('=' * 112)
B2 = (O.score >= 85) & (O.pos120 < 0.25)
ref2 = O[B2].r20.mean()
P('   该子集基准: r20=%+.2f%% 胜率20=%.1f%%  (n=%d)' % (ref2, 100 * (O[B2].r20 > 0).mean(), B2.sum()))
P('')
quint('   控盘高分区 · 堆量分五档', 's_score', B2)
P('')
quint('   控盘高分区 · 红肥绿瘦分五档', 'r_score', B2)
P('')
quint('   控盘高分区 · 堆量倍数五档', 's_ratio', B2)
P('')
quint('   控盘高分区 · 红肥绿瘦比值五档', 'r_ratio', B2)

# ============================================================
P('\n' + '=' * 112)
P('[Q3] 反向使用：低堆量 / 红瘦绿肥')
P('=' * 112)
show('   全样本 · r_ratio < 0.90（红瘦绿肥）', O.r_ratio < 0.90, BASE_R)
show('   全样本 · s_ratio < 1.00（没有堆量）', O.s_ratio < 1.00, BASE_R)
show('   全样本 · s_ratio < 1.00 且 r_ratio < 0.90',
     (O.s_ratio < 1.00) & (O.r_ratio < 0.90), BASE_R)
show('   全样本 · s_cont < 0.30（量能没有连续高于基准）', O.s_cont < 0.30, BASE_R)
P('')
P('   --- 叠加控盘高分区（score>=85 & pos<0.25）---')
show('   基准(不加因子)', B2, ref2)
show('   + r_ratio < 0.90', B2 & (O.r_ratio < 0.90), ref2)
show('   + s_ratio < 1.00', B2 & (O.s_ratio < 1.00), ref2)
show('   + 两者（低堆量 + 红瘦绿肥）', B2 & (O.s_ratio < 1.00) & (O.r_ratio < 0.90), ref2)
show('   + 两者（堆量高 + 红瘦绿肥）', B2 & (O.s_ratio >= 1.15) & (O.r_ratio < 0.90), ref2)
show('   + 反向(堆量高 + 红肥绿瘦)', B2 & (O.s_ratio >= 1.15) & (O.r_ratio >= 1.30), ref2)

# ============================================================
P('\n' + '=' * 112)
P('[Q4] 宽低位区（pos120<0.45）内的增量：这是「底部」口径最相关的检验')
P('=' * 112)
B3 = O.pos120 < 0.45
ref3 = O[B3].r20.mean()
show('   基准 pos120<0.45', B3, BASE_R)
show('   + stack ok（原草案口径）', B3 & (O.s_ok == 1), ref3)
show('   + redfat ok（原草案口径）', B3 & (O.r_ok == 1), ref3)
show('   + r_ratio<0.90', B3 & (O.r_ratio < 0.90), ref3)
show('   + s_ratio<1.00', B3 & (O.s_ratio < 1.00), ref3)

P('\n' + '=' * 112)
P('[Q5] 一句话结论')
P('=' * 112)
P('   1. 底部堆量：堆量倍数与未来20日收益【单调负相关】(rho=%+.4f)。'
  % spear(O.s_ratio, O.r20))
P('      ratio<1.0 -> %+.2f%% ；ratio 1.6~2.2 -> %+.2f%% ；ratio>3.5 -> %+.2f%%'
  % (O[O.s_ratio < 1.0].r20.mean(), O[(O.s_ratio >= 1.6) & (O.s_ratio < 2.2)].r20.mean(),
     O[O.s_ratio >= 3.5].r20.mean()))
P('   2. 红肥绿瘦：同样是单调负相关 (rho=%+.4f)。反向「红瘦绿肥」反而 %+.2f%%（胜率%.1f%%）'
  % (spear(O.r_ratio, O.r20), O[O.r_ratio < 0.9].r20.mean(),
     100 * (O[O.r_ratio < 0.9].r20 > 0).mean()))
P('   3. 「两个都满足」是全样本最差组合之一：%+.2f%%（n=%d）'
  % (O[(O.s_ok == 1) & (O.r_ok == 1)].r20.mean(), int((O.s_ok & O.r_ok).sum())))
P('   4. 控盘高分区内部：「高控盘+堆量+红肥绿瘦」=%+.2f%%（n=%d），比基准还差'
  % (O[B2 & (O.s_ok == 1) & (O.r_ok == 1)].r20.mean(), int((B2 & (O.s_ok == 1) & (O.r_ok == 1)).sum())))
P('   5. => 按原草案方向上线会往程序里塞一个负 alpha 的「建仓加强」提示。')
_fh.close()
print('\n已写:', OUT)
