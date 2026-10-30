# -*- coding: utf-8 -*-
"""C3 + C5 改前 / 改后对比（2026-10-10）

改前基准 = tools/audit_ctrl_reverse.BEFORE_c5.csv  （C1/C2 已落盘、C3/C5 未落盘）
改后      = tools/audit_ctrl_reverse.csv           （C3/C5 已落盘）

同一批 17570 条滚动观测（4401 只 x 4 锚点），锚点与股票完全相同，只有代码不同。
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd

import services.band_pattern_engine as E

OUT = os.path.join(ROOT, 'tools', 'c3c5_compare.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


B = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.BEFORE_c5.csv'), dtype={'code': str})
A = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv'), dtype={'code': str})
B = B.sort_values(['code', 'k']).reset_index(drop=True)
A = A.sort_values(['code', 'k']).reset_index(drop=True)

P('=' * 106)
P('C3 + C5 改前 / 改后对比')
P('=' * 106)
P('   改前（C1C2，未含C3C5） %d 条 / %d 只 | 改后（含C3C5） %d 条 / %d 只'
  % (len(B), B.code.nunique(), len(A), A.code.nunique()))
same = (len(A) == len(B)) and bool((A['code'] == B['code']).all()) and bool((A['k'] == B['k']).all())
P('   锚点逐条对齐: %s' % same)
if not same:
    P('   !! 锚点不一致，对比无效，请检查')
    _fh.close()
    sys.exit(1)


# ==================================================================
P('\n' + '=' * 106)
P('[1] 控盘分分布：C5 改振幅分量后的整体位移')
P('=' * 106)
P('   %-14s %10s %10s %10s' % ('分位', '改前', '改后', '差值'))
for q in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
    b, a = B.score.quantile(q), A.score.quantile(q)
    P('   %-14s %10.2f %10.2f %+10.2f' % ('p%d' % int(q * 100), b, a, a - b))
P('   %-14s %10.2f %10.2f %+10.2f' % ('mean', B.score.mean(), A.score.mean(), A.score.mean() - B.score.mean()))
P('   %-14s %10.2f %10.2f %+10.2f' % ('std', B.score.std(), A.score.std(), A.score.std() - B.score.std()))
d = A.score - B.score
P('\n   分数下降 %d 条 / 上升 %d 条 / 不变 %d 条'
  % (int((d < -1e-9).sum()), int((d > 1e-9).sum()), int((d.abs() <= 1e-9).sum())))
P('   变化幅度: min=%+.2f  p25=%+.2f  p50=%+.2f  p75=%+.2f  max=%+.2f'
  % (d.min(), d.quantile(.25), d.median(), d.quantile(.75), d.max()))

P('\n   --- 高分区间是否收窄（用户关注点）---')
P('   %-14s %10s %10s %10s %10s' % ('阈值', '改前条数', '改后条数', '改前占比', '改后占比'))
for th in (60, 70, 75, 80, 85, 90, 95):
    nb, na = int((B.score >= th).sum()), int((A.score >= th).sum())
    P('   %-14s %10d %10d %9.1f%% %9.1f%%' % ('>=%d' % th, nb, na, 100 * nb / len(B), 100 * na / len(A)))
P('   -> 看分布 std 与 p90/p95：std 变大 = 分数被拉开，区分度提升')

# ==================================================================
P('\n' + '=' * 106)
P('[2] C5 影响分解：按振幅分档看分数变化')
P('=' * 106)
bands = ((0, 0.02), (0.02, 0.025), (0.025, 0.03), (0.03, 0.0375), (0.0375, 0.045),
         (0.045, 0.055), (0.055, 0.07), (0.07, 9))
P('   %-18s %7s %9s %9s %6s %8s %8s' % ('amp 区间', '条数', '改前均分', '改后均分', '均差',
                                        '改前>=85', '改后>=85'))
for lo, hi in bands:
    m = (B.amp >= lo) & (B.amp < hi)
    n = int(m.sum())
    if n == 0:
        continue
    mid = (lo + min(hi, 0.12)) / 2.0
    old_ams = max(0.0, min(100.0, 100.0 - mid * 300.0))
    new_ams = (100.0 - (0.040 - mid) * 2300.0) if mid <= 0.040 else (100.0 - (mid - 0.040) * 1200.0)
    new_ams = max(0.0, min(100.0, new_ams))
    P('   [%.4f,%.4f) %7d %9.2f %9.2f %+6.2f %7.1f%% %7.1f%%   (amp_score %5.1f -> %5.1f)'
      % (lo, hi, n, B.score[m].mean(), A.score[m].mean(), A.score[m].mean() - B.score[m].mean(),
         100 * (B.score[m] >= 85).mean(), 100 * (A.score[m] >= 85).mean(), old_ams, new_ams))

# ==================================================================
P('\n' + '=' * 106)
P('[3] 规则③「高度控盘候选」新旧口径（都用【改后】分数与位置）')
P('=' * 106)
P('   全样本: n=%d | r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%'
  % (len(A), A.r20.mean(), 100 * (A.r20 > 0).mean(), A.mdd20.mean()))


def stat(nm, m):
    s = A[m]
    if len(s) == 0:
        P('   %-40s n=0' % nm)
        return
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    P('   %-40s n=%6d 只=%5d | r20=%+6.2f%% 胜率=%5.1f%% mdd=%+6.2f%% t=%+5.2f'
      % (nm, len(s), s.code.nunique(), s.r20.mean(), 100 * (s.r20 > 0).mean(), s.mdd20.mean(), t))


stat('【C3新】pos<0.25 且 score>=85', (A.pos120 < E._CTRL_CAND_POS) & (A.score >= E._CTRL_HIGH))
stat('【旧】score>=90 且 pos<0.4', (A.score >= E._CTRL_CAND) & (A.pos120 < E._CTRL_POS_LOW))
stat('  参考：pos<0.25 且 score>=90', (A.pos120 < 0.25) & (A.score >= 90))
stat('  参考：pos<0.25 且 score>=80', (A.pos120 < 0.25) & (A.score >= 80))
stat('  参考：pos<0.25 纯位置', (A.pos120 < 0.25))
stat('  参考：pos<0.25 且 amp>=0.025', (A.pos120 < 0.25) & (A.amp >= 0.025))
hit_new = A[(A.pos120 < E._CTRL_CAND_POS) & (A.score >= E._CTRL_HIGH)]
hit_old = A[(A.score >= E._CTRL_CAND) & (A.pos120 < E._CTRL_POS_LOW)]
kk = ['code', 'k']
so = set(map(tuple, hit_old[kk].values))
sn = set(map(tuple, hit_new[kk].values))
P('\n   交集 %d 条 / 旧口径 %d 条 / 新口径 %d 条' % (len(so & sn), len(so), len(sn)))
P('   改前报、改后不报（被 C3 挡掉）: %d 条' % len(so - sn))
P('   改前不报、改后新报（被 C3 纳入）: %d 条' % len(sn - so))

# ==================================================================
P('\n' + '=' * 106)
P('[4] 规则①② 命中条数（①本质未改，②按位置；仅受分数位移影响）')
P('=' * 106)
for nm, f in (('①高度控盘+疑似洗盘 score>=85 & wash',
               lambda D: (D.score >= E._CTRL_HIGH) & (D.stage == 'wash')),
              ('②出货风险警示 distribute & pos>=0.65',
               lambda D: (D.stage == 'distribute') & (D.pos120 >= E._CTRL_DIST_POS))):
    P('   %-44s 改前=%5d  改后=%5d' % (nm, int(f(B).sum()), int(f(A).sum())))

# ==================================================================
P('\n' + '=' * 106)
P('[5] 异常检查')
P('=' * 106)
bad = A[A.score.isna() | A.stage.isna() | A.pos120.isna()]
P('   改后 score/stage/pos120 空值行数: %d（应为 0）' % len(bad))
P('   改后 stage 取值: %s -> 只有3种: %s'
  % (sorted(A.stage.unique()), set(A.stage.unique()) <= {'unknown', 'distribute', 'wash'}))
P('   改后 score 落在 [0,100]: %s（min=%.2f max=%.2f）'
  % (bool((A.score >= 0).all() and (A.score <= 100).all()), A.score.min(), A.score.max()))
P('   改后 amp_score 分量落在 [0,100]: %s'
  % bool((np.array([max(0.0, min(100.0, (100.0 - (0.040 - x) * 2300.0) if x <= 0.040
                             else (100.0 - (x - 0.040) * 1200.0))) for x in A.amp] ) >= 0).all()))
_fh.close()
