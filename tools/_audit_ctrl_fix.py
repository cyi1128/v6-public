# -*- coding: utf-8 -*-
"""控盘度审计 · 第4步：优化方案的数据验证（哪个改法真的更好）"""
import io, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

OUT = os.path.join(ROOT, 'tools', 'audit_ctrl_fix.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

O = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv'))
N = len(O)
BASE_R20, BASE_WIN, BASE_MDD = O.r20.mean(), 100 * (O.r20 > 0).mean(), O.mdd20.mean()

P('=' * 104)
P('[G] 备选方案的实测对比（基准：全样本 n=%d r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%）'
  % (N, BASE_R20, BASE_WIN, BASE_MDD))
P('=' * 104)
P('口径：r20/mdd20 是 T 之后的 20 日真实走势；n_eff = n/4 用于 t 值（4 锚点重叠）')
P('')
P('%-46s %6s %7s %7s %7s %7s %6s' % ('方案', 'n', '占比%', 'r20%', '胜率%', 'mdd%', 't(r20)'))
P('-' * 104)

def ev(name, mask, col='r20'):
    sub = O[mask]
    if len(sub) < 20:
        P('%-46s %6d  样本不足' % (name, len(sub))); return
    n_eff = len(sub) / 4.0
    se = math.sqrt(sub[col].var(ddof=1) / n_eff + O[col].var(ddof=1) / (N / 4.0))
    t = (sub[col].mean() - O[col].mean()) / se if se > 0 else 0.0
    P('%-46s %6d %7.1f %7.2f %7.1f %7.2f %+6.2f'
      % (name, len(sub), 100.0 * len(sub) / N, sub.r20.mean(),
         100 * (sub.r20 > 0).mean(), sub.mdd20.mean(), t))

# --- 现状 ---
ev('①现规则 高度控盘候选 = score>=90 & pos<0.4',
   (O.score >= 90) & (O.pos120 < 0.4))
ev('②现规则 高度控盘+疑似洗盘 = score>=85 & wash',
   (O.score >= 85) & (O.stage == 'wash'))
ev('③现规则 出货警示 = distribute & score>=60',
   (O.stage == 'distribute') & (O.score >= 60))

P('')
P('--- 候选规则：改阈值 ---')
for th in (80, 85, 90, 95):
    ev('score>=%d & pos<0.4' % th, (O.score >= th) & (O.pos120 < 0.4))
P('')
P('--- 候选规则：收紧位置（位置是唯一显著因子）---')
for p in (0.15, 0.20, 0.25, 0.30):
    ev('score>=85 & pos<%.2f' % p, (O.score >= 85) & (O.pos120 < p))
P('')
P('--- 候选规则：纯位置，不加控盘分 ---')
for p in (0.15, 0.20, 0.25, 0.30):
    ev('仅 pos<%.2f（不用控盘分）' % p, O.pos120 < p)
P('')
P('--- 出货警示的三种改法 ---')
ev('现：distribute & score>=60', (O.stage == 'distribute') & (O.score >= 60))
ev('改法A：distribute（不加分数过滤）', O.stage == 'distribute')
ev('改法B：distribute & score<60（反向）', (O.stage == 'distribute') & (O.score < 60))
ev('改法C：distribute & score>=60  OR  score<50',
   ((O.stage == 'distribute') & (O.score >= 60)) | (O.score < 50))
P('')
P('--- 洗盘提示是否该留 ---')
ev('wash（全部）', O.stage == 'wash')
ev('wash & score>=85（现规则的一半）', (O.stage == 'wash') & (O.score >= 85))
ev('wash & score>=85 & pos<0.3', (O.stage == 'wash') & (O.score >= 85) & (O.pos120 < 0.3))
ev('wash 的反面：非wash', O.stage != 'wash')
P('')
P('--- 把「量价配合」真正用起来：上涨日均量比>1 且 下跌日均量比<1 ---')
ev('up_ratio>1.15 & down_ratio<0.9', (O.up_ratio > 1.15) & (O.down_ratio < 0.9))
ev('up_ratio>1.30 & down_ratio<0.8（源码里的强条件）',
   (O.up_ratio > 1.30) & (O.down_ratio < 0.8))
ev('up_ratio<0.85（源码 +25 分的那条）', O.up_ratio < 0.85)
ev('up_ratio>1.15 & down_ratio<0.9 & score>=85',
   (O.up_ratio > 1.15) & (O.down_ratio < 0.9) & (O.score >= 85))

P('')
P('=' * 104)
P('[H] 极端组合：把「位置低 + 真正放量上涨」合起来（庄家吸筹的可能画像）')
P('=' * 104)
m = (O.pos120 < 0.25) & (O.up_ratio > 1.15) & (O.down_ratio < 0.95)
ev('pos<0.25 & up>1.15 & down<0.95', m)
m2 = (O.pos120 < 0.25) & (O.up_ratio > 1.15) & (O.down_ratio < 0.95) & (O.amp > 0.03)
ev('上一行 + 振幅>3%（有波动，排除死票）', m2)
m3 = (O.pos120 < 0.25) & (O.up_ratio > 1.15) & (O.down_ratio < 0.95) & (O.score >= 80)
ev('上一行 + score>=80', m3)
P('')
P('参考：死票特征（极度缩量+极低振幅+低位）实测')
ev('pos<0.25 & amp<0.02（极度缩量低振幅）', (O.pos120 < 0.25) & (O.amp < 0.02))
ev('pos<0.25 & amp>=0.03（低位但有波动）', (O.pos120 < 0.25) & (O.amp >= 0.03))

_fh.close()
