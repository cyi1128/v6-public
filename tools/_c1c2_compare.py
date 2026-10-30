# -*- coding: utf-8 -*-
"""C1 + C2 改前 / 改后对比（同一批 17570 条滚动观测，仅代码不同）

改前 = tools\\audit_ctrl_reverse.BEFORE_c1c2.csv（旧代码：有 +10 分、出货按 ctrl>=60）
改后 = tools\\audit_ctrl_reverse.csv（新代码：无 +10 分、出货按 pos>=0.65）
两份 CSV 列结构完全一致，且都是「T 之前算分 / T 之后看真实走势」的同一批锚点。
"""
import io, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import pandas as pd

import services.band_pattern_engine as E

OUT = os.path.join(ROOT, 'tools', 'c1c2_compare.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

B = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.BEFORE_c1c2.csv'), dtype={'code': str})
A = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv'), dtype={'code': str})
P('=' * 106)
P('改前 / 改后对比')
P('=' * 106)
P('   改前（旧代码） %d 条 / %d 只 | 改后（新代码） %d 条 / %d 只'
  % (len(B), B.code.nunique(), len(A), A.code.nunique()))
if len(B) != len(A):
    P('   !! 行数不一致，改用交集对齐')
key = ['code', 'T_date']
M = B.merge(A, on=key, suffixes=('_b', '_a'))
P('   对齐后可比样本 %d 条' % len(M))
N = len(M)

P('\n' + '=' * 106)
P('[1] 控盘分分布：删除 +10 分后的整体偏移')
P('=' * 106)
P('%-14s %10s %10s %10s' % ('分位', '改前', '改后', '差值'))
for q, nm in ((0.10, 'p10'), (0.25, 'p25'), (0.50, 'p50'), (0.75, 'p75'), (0.90, 'p90'), (0.99, 'p99')):
    b, a = M.score_b.quantile(q), M.score_a.quantile(q)
    P('%-14s %10.2f %10.2f %+10.2f' % (nm, b, a, a - b))
P('%-14s %10.2f %10.2f %+10.2f' % ('mean', M.score_b.mean(), M.score_a.mean(),
                                   M.score_a.mean() - M.score_b.mean()))
d = M.score_a - M.score_b
P('')
P('   分数下降的条数: %d / %d = %.2f%%' % ((d < -0.005).sum(), N, 100.0 * (d < -0.005).mean()))
P('   分数不变的条数: %d / %d = %.2f%%' % ((d.abs() <= 0.005).sum(), N, 100.0 * (d.abs() <= 0.005).mean()))
P('   分数上升的条数: %d（应为 0，因为只删了加分项）' % ((d > 0.005).sum()))
if (d < -0.005).any():
    P('   下降幅度: min=%.2f  p50=%.2f  max=%.2f' % (d[d < -0.005].min(), d[d < -0.005].median(), d[d < -0.005].abs().max()))
    P('   理论最大降幅 = 10 分 x 0.35 权重 x 1.2 位置权重 = 4.20（位置 <0.4 时）')

P('\n' + '=' * 106)
P('[2] 阈值命中率变化（分母 = %d 条）' % N)
P('=' * 106)
P('%-16s %10s %10s %10s' % ('阈值', '改前', '改后', '变化'))
for th, nm in ((60, '>=60'), (70, '>=70'), (80, '>=80'), (85, '>=85'), (90, '>=90'), (95, '>=95')):
    nb, na = int((M.score_b >= th).sum()), int((M.score_a >= th).sum())
    P('%-16s %10d %10d %+10d' % (nm, nb, na, na - nb))

P('\n' + '=' * 106)
P('[3] stage 分布变化')
P('=' * 106)
P('%-14s %10s %10s %10s' % ('stage', '改前', '改后', '变化'))
for st in ('unknown', 'distribute', 'wash'):
    nb = int((M.stage_b == st).sum()); na = int((M.stage_a == st).sum())
    P('%-14s %10d %10d %+10d' % (st, nb, na, na - nb))
chg = (M.stage_b != M.stage_a)
P('   stage 发生变化的条数: %d (%.2f%%)' % (chg.sum(), 100.0 * chg.mean()))
if chg.any():
    P('   变化明细（前5种）：')
    for (x, y), n in M[chg].groupby(['stage_b', 'stage_a']).size().sort_values(ascending=False).head(5).items():
        P('     %-11s -> %-11s  %d 条' % (x, y, n))

P('\n' + '=' * 106)
P('[4] 规则② 出货警示：两种口径对比（都用【改后】分数与 pos）')
P('=' * 106)
stats = A
B_R20, B_WIN, B_MDD = stats.r20.mean(), 100 * (stats.r20 > 0).mean(), stats.mdd20.mean()
P('   全样本基准: n=%d | r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%' % (len(stats), B_R20, B_WIN, B_MDD))
P('')
P('%-42s %7s %8s %8s %8s %8s %8s' % ('口径', 'n', '占比%', 'pos均', 'r20%', '胜率%', 'mdd%'))
P('-' * 106)
def ev(nm, mask):
    sub = stats[mask]
    if len(sub) < 10:
        P('%-42s %7d  样本不足' % (nm, len(sub))); return None
    P('%-42s %7d %8.1f %8.3f %8.2f %8.1f %8.2f'
      % (nm, len(sub), 100.0 * len(sub) / len(stats), sub.pos120.mean(),
         sub.r20.mean(), 100 * (sub.r20 > 0).mean(), sub.mdd20.mean()))
    return sub
d_all = stats.stage == 'distribute'
ev('旧口径  distribute & score>=60', d_all & (stats.score >= 60))
ev('新口径  distribute & pos>=0.65', d_all & (stats.pos120 >= 0.65))
ev('（对照）distribute 全部', d_all)
ev('（对照）非 distribute', ~d_all)
P('')
P('   新口径命中的高位危险股 vs 旧口径命中的低位无害股：')
sub_new = stats[d_all & (stats.pos120 >= 0.65)]
sub_old = stats[d_all & (stats.score >= 60)]
P('     新口径命中里 位置<0.4 的有 %d 条（应为 0）' % int((sub_new.pos120 < 0.4).sum()))
P('     旧口径命中里 位置>=0.65 的有 %d 条' % int((sub_old.pos120 >= 0.65).sum()))
if len(sub_old):
    P('     旧口径命中的 r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%' %
      (sub_old.r20.mean(), 100 * (sub_old.r20 > 0).mean(), sub_old.mdd20.mean()))

P('\n' + '=' * 106)
P('[5] 规则①③ 命中条数（①未改；③已按 C3 改为位置主导，同时列旧口径对照）')
P('=' * 106)
for nm, f in (('①高度控盘+疑似洗盘  score>=85 & wash', lambda D: (D.score >= E._CTRL_HIGH) & (D.stage == 'wash')),
              ('③高度控盘候选(新:位置主导)', lambda D: (D.pos120 < E._CTRL_CAND_POS) & (D.score >= E._CTRL_HIGH)),
              ('③高度控盘候选(旧:分数主导)', lambda D: (D.score >= E._CTRL_CAND) & (D.pos120 < E._CTRL_POS_LOW))):
    P('   %-44s 改前=%4d  改后=%4d' % (nm, int(f(B).sum()), int(f(A).sum())))

P('\n' + '=' * 106)
P('[6] 异常检查')
P('=' * 106)
bad = A[A.score.isna() | A.stage.isna() | A.pos120.isna()]
P('   改后 CSV 里 score/stage/pos120 有空值的行数: %d（应为 0）' % len(bad))
P('   改后 stage 取值是否只有 3 种: %s -> %s'
  % (sorted(A.stage.unique()), set(A.stage.unique()) <= {'unknown', 'distribute', 'wash'}))
P('   改后 score 是否都在 [0,100]: %s（min=%.2f max=%.2f）'
  % (bool((A.score >= 0).all() and (A.score <= 100).all()), A.score.min(), A.score.max()))
_fh.close()
