# -*- coding: utf-8 -*-
"""C6 规则（低位 + 适中振幅）标定复现：总体收益/胜率/t + 逐锚点增量检验。

数据源 tools\\buildfactor_wide.csv（17570 条滚动观测，k=20/40/60/80 四个锚点）
输出 tools\\c6_calib.txt
"""
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
CSV = r'D:\QuantMonitorV6\tools\buildfactor_wide.csv'
OUT = r'D:\QuantMonitorV6\tools\c6_calib.txt'
L = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    L.append(s)
    print(s, flush=True)


w = pd.read_csv(CSV)
P('=' * 104)
P('C6 规则标定复现（低位 + 适中振幅）   观测数 %d ｜ 锚点 %s ｜ 股票 %d 只'
  % (len(w), sorted(w.k.unique()), w.code.nunique()))
P('=' * 104)


def stat(d):
    n = len(d)
    if n == 0:
        return 0, float('nan'), float('nan'), float('nan')
    m = d.r20.mean()
    s = d.r20.std(ddof=1)
    t = m / (s / np.sqrt(n)) if n > 1 and s > 0 else float('nan')
    return n, m, 100.0 * (d.r20 > 0).mean(), t


def row(tag, d):
    n, m, win, t = stat(d)
    P('%-26s n=%6d  r20=%+7.2f%%  胜率=%5.1f%%  t=%+6.2f  中位=%+6.2f%%'
      % (tag, n, m, win, t, d.r20.median() if n else float('nan')))
    return n, m, win, t


P('【一、总体口径】')
row('全样本基准', w)
row('仅过低位置 pos120<0.25', w[w.pos120 < 0.25])
row('仅适中振幅 amp∈[2.5%,5.5%]', w[(w.amp20 >= 0.025) & (w.amp20 <= 0.055)])
row('★ C6 = 低位 + 适中振幅',
    w[(w.pos120 < 0.25) & (w.amp20 >= 0.025) & (w.amp20 <= 0.055)])
row('对照 C4（+量价结构+控盘≥85）',
    w[(w.pos120 < 0.25) & (w.up_r > 1.15) & (w.dn_r < 0.95)
      & (w.amp20 >= 0.025) & (w.amp20 <= 0.055) & (w.score >= 85)])
row('对照 C4（+量价结构，无控盘）',
    w[(w.pos120 < 0.25) & (w.up_r > 1.15) & (w.dn_r < 0.95)
      & (w.amp20 >= 0.025) & (w.amp20 <= 0.055)])
row('反向：低位 + 过低振幅(<2%)',
    w[(w.pos120 < 0.25) & (w.amp20 < 0.02)])
row('反向：低位 + 过高振幅(>7%)',
    w[(w.pos120 < 0.25) & (w.amp20 > 0.07)])

P('')
P('【二、逐锚点增量检验（只有 4 个锚点同号且全为正才算通过）】')
c6 = w[(w.pos120 < 0.25) & (w.amp20 >= 0.025) & (w.amp20 <= 0.055)]
P('%-8s %8s %10s %8s %10s %10s' % ('锚点k', '基准n', '基准r20', '命中n', '命中r20', '增量(命中-基准)'))
inc = []
for k in sorted(w.k.unique()):
    b = w[w.k == k]
    h = c6[c6.k == k]
    if len(h) == 0:
        P('%-8s %8d %+10.2f%% %8d %10s %10s' % (k, len(b), b.r20.mean(), 0, '-', '-'))
        inc.append(float('nan'))
        continue
    d = h.r20.mean() - b.r20.mean()
    inc.append(d)
    P('%-8s %8d %+10.2f%% %8d %+10.2f%% %+10.2f%%'
      % (k, len(b), b.r20.mean(), len(h), h.r20.mean(), d))
valid = [x for x in inc if not np.isnan(x)]
verdict = ('通过' if len(valid) == 4 and all(x > 0 for x in valid)
           else '未通过（存在负增量）')
P('结论：%s   增量明细 %s' % (verdict, ' ｜ '.join('k%d %+.2f' % (k, x)
                                                   for k, x in zip(sorted(w.k.unique()), inc))))

P('')
P('【三、稳健性：C6 各阈值档位（看结论是否单调、是否只靠某一档）】')
for p_hi in (0.20, 0.25, 0.30):
    for a_lo, a_hi in ((0.025, 0.045), (0.025, 0.055), (0.030, 0.055), (0.025, 0.065)):
        d = w[(w.pos120 < p_hi) & (w.amp20 >= a_lo) & (w.amp20 <= a_hi)]
        n, m, win, t = stat(d)
        P('  pos<%s amp∈[%.1f%%,%.1f%%]  n=%6d  r20=%+7.2f%%  胜率=%5.1f%%  t=%+6.2f'
          % (p_hi, a_lo * 100, a_hi * 100, n, m, win, t))

P('')
P('【四、振幅分档（低位区内，看振幅与收益的关系是不是帐篷形）】')
low = w[w.pos120 < 0.25]
edges = [0, 0.015, 0.02, 0.025, 0.035, 0.045, 0.055, 0.07, 0.10, 99]
for i in range(len(edges) - 1):
    d = low[(low.amp20 >= edges[i]) & (low.amp20 < edges[i + 1])]
    n, m, win, t = stat(d)
    P('  振幅 [%5.1f%%, %5.1f%%)  n=%6d  r20=%+7.2f%%  胜率=%5.1f%%  t=%+6.2f'
      % (edges[i] * 100, edges[i + 1] * 100 if edges[i + 1] < 99 else 999, n, m, win, t))

P('')
P('=' * 104)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L) + '\n')
print('已写出 %s' % OUT)
