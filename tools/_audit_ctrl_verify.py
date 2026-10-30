# -*- coding: utf-8 -*-
"""控盘度审计 · 第5步：独立复核（从CSV重算头条数字）+ 出货降噪的替代方案"""
import io, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

OUT = os.path.join(ROOT, 'tools', 'audit_ctrl_verify.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

O = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv'))
A = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse_cross.csv'))
N = len(O)
B_R, B_W, B_M = O.r20.mean(), 100 * (O.r20 > 0).mean(), O.mdd20.mean()

P('=' * 104)
P('[I] 独立复核（直接用 pandas 从 CSV 重算，与脚本 1/2 的结论对拍）')
P('=' * 104)
P('观测 %d 条 / %d 只 | 基准 r20=%+.3f%% 胜率=%.2f%% mdd=%+.3f%%' % (N, O.code.nunique(), B_R, B_W, B_M))
P('')
chk = [
    ('[A] 全市场样本数（横截面）', len(A), 4404),
    ('[A] score>=85 只数', int((A.score >= 85).sum()), 1480),
    ('[A] score>=90 只数', int((A.score >= 90).sum()), 1194),
    ('[B] >=90 档 r20 均值', round(O[O.score >= 90].r20.mean(), 2), -0.00),
    ('[B] 80-85 档 r20 均值', round(O[(O.score >= 80) & (O.score < 85)].r20.mean(), 2), 1.04),
    ('[B] wash 胜率', round(100 * (O[O.stage == 'wash'].r20 > 0).mean(), 1), 37.9),
    ('[B] distribute 胜率', round(100 * (O[O.stage == 'distribute'].r20 > 0).mean(), 1), 39.8),
    ('[B] unknown 胜率', round(100 * (O[O.stage == 'unknown'].r20 > 0).mean(), 1), 45.8),
    ('[B] distribute&score>=60 条数', int(((O.stage == 'distribute') & (O.score >= 60)).sum()), 163),
    ('[B] distribute&score<60 条数', int(((O.stage == 'distribute') & (O.score < 60)).sum()), 561),
    ('[B] distribute&score<60 的 mdd', round(O[(O.stage == 'distribute') & (O.score < 60)].mdd20.mean(), 2), -15.88),
    ('[H] 低位+放量+score>=80 条数', int(((O.pos120 < 0.25) & (O.up_ratio > 1.15) & (O.down_ratio < 0.95) & (O.score >= 80)).sum()), 363),
    ('[H] 低位+放量+score>=80 胜率', round(100 * (O[(O.pos120 < 0.25) & (O.up_ratio > 1.15) & (O.down_ratio < 0.95) & (O.score >= 80)].r20 > 0).mean(), 1), 55.9),
]
ok = 0
for name, got, exp in chk:
    flag = 'OK ' if (abs(float(got) - float(exp)) < 0.6) else 'XX '
    ok += (flag == 'OK ')
    P('   %s %-34s 重算=%-9s 前文=%-9s' % (flag, name, got, exp))
P('   复核 %d/%d 一致' % (ok, len(chk)))

P('')
P('=' * 104)
P('[J] 出货警示：既降噪、又不漏掉危险子集 的替代过滤（现规则 = distribute & score>=60）')
P('=' * 104)
P('%-44s %6s %7s %8s %8s %8s %7s' % ('方案', 'n', '占比%', 'r20%', '胜率%', 'mdd%', 't(r20)'))
P('-' * 104)
def ev(name, mask):
    sub = O[mask]
    if len(sub) < 20:
        P('%-44s %6d  样本不足' % (name, len(sub))); return
    se = math.sqrt(sub.r20.var(ddof=1) / (len(sub) / 4.0) + O.r20.var(ddof=1) / (N / 4.0))
    t = (sub.r20.mean() - B_R) / se if se > 0 else 0
    P('%-44s %6d %7.1f %8.2f %8.1f %8.2f %+7.2f'
      % (name, len(sub), 100.0 * len(sub) / N, sub.r20.mean(),
         100 * (sub.r20 > 0).mean(), sub.mdd20.mean(), t))

d = O.stage == 'distribute'
ev('现规则  distribute & score>=60', d & (O.score >= 60))
ev('替代1   distribute & pos>=0.7（高位才警示）', d & (O.pos120 >= 0.7))
ev('替代2   distribute & pos>=0.6', d & (O.pos120 >= 0.6))
ev('替代3   distribute & score<60（低分才警示）', d & (O.score < 60))
ev('替代4   distribute & 振幅>0.05（放量剧烈）', d & (O.amp > 0.05))
ev('替代5   distribute & 未来量比…（不可用，属未来数据）', d & (O.amp < 0))
ev('替代6   distribute（不加任何过滤，原口径）', d)
P('')
P('  说明：替代方案要看两件事 —— ①提示条数是否可控（降噪）②r20/mdd 是否真的更差（有效）')
P('  替代1/2 的好处：只用「位置高」这一条（位置是本轮唯一显著的收益因子），')
P('               既能把条数压下来，又不会像 score>=60 那样把危险的低分子集排除在外。')
P('')
P('  位置 vs 分数 的对照（解释为什么「按分数过滤」是反的）：')
for nm, mask in [('distribute & pos>=0.7', d & (O.pos120 >= 0.7)),
                 ('distribute & pos<0.4 ', d & (O.pos120 < 0.4))]:
    sub = O[mask]
    if len(sub) < 20:
        P('    %s n=%d 样本不足' % (nm, len(sub))); continue
    P('    %-22s n=%5d | r20=%+7.2f%% 胜率=%5.1f%% mdd=%+7.2f%%'
      % (nm, len(sub), sub.r20.mean(), 100 * (sub.r20 > 0).mean(), sub.mdd20.mean()))

_fh.close()
