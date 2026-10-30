# -*- coding: utf-8 -*-
"""C1 + C2 落盘后的单元验证（v2，修正期望值 + 定向命中被删分支）

前一次运行报的 2 项失败经核对是【测试脚本期望值写错】，代码行为正确：
  - wash+ctrl=90+pos=0.30 应同时命中规则①与规则③（多条用 ' ｜ ' 连接是设计如此）
  - distribute+pos=None 时规则②③ 都不触发（守卫生效），正确结果就是 ''
本版把期望值改对，并把「验证2」改成能真正命中被删分支的定向用例。
"""
import io, os, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np, pandas as pd

import services.band_pattern_engine as E
from strategy.base import TechnicalIndicators as TI, _clamp100

OUT = os.path.join(ROOT, 'tools', 'c1c2_unit.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

fail = []
def chk(name, got, want):
    ok = (got == want)
    if not ok:
        fail.append(name)
    P('   %s %-56s got=%r' % ('OK ' if ok else 'XX ', name, got) +
      ('' if ok else '  want=%r' % (want,)))

P('=' * 104)
P('阈值实测')
P('=' * 104)
P('   _CTRL_HIGH=%s  _CTRL_CAND=%s（已停用C3）  _CTRL_CAND_POS=%s  _CTRL_POS_LOW=%s（已停用C3）'
  % (E._CTRL_HIGH, E._CTRL_CAND, E._CTRL_CAND_POS, E._CTRL_POS_LOW))
P('   _CTRL_DIST=%s（已停用）  _CTRL_DIST_POS=%s' % (E._CTRL_DIST, E._CTRL_DIST_POS))

P('\n' + '=' * 104)
P('验证 1  _ctrl_note 规则矩阵（含改前会误报的用例）')
P('=' * 104)
chk('distribute + pos=0.80 -> 出货警示',
    E._ctrl_note(50.0, 'distribute', 0.80), '出货风险警示')
chk('distribute + pos=0.65（边界，含等号）-> 出货警示',
    E._ctrl_note(50.0, 'distribute', 0.65), '出货风险警示')
chk('distribute + pos=0.649（边界外）-> 空',
    E._ctrl_note(50.0, 'distribute', 0.649), '')
chk('distribute + pos=0.20（低位；改前 ctrl=50<60 不报，但 ctrl=80 会误报）',
    E._ctrl_note(50.0, 'distribute', 0.20), '')
chk('distribute + ctrl=80 + pos=0.20 -> 空（改前会误报「出货风险警示」）',
    E._ctrl_note(80.0, 'distribute', 0.20), '')
chk('distribute + ctrl=95 + pos=0.20 -> 仅候选',
    E._ctrl_note(95.0, 'distribute', 0.20), '高度控盘候选')
chk('distribute + ctrl=95 + pos=0.80 -> 仅出货',
    E._ctrl_note(95.0, 'distribute', 0.80), '出货风险警示')
# 2026-10-10 C3：规则③ 位置门槛改为 <0.25，pos=0.30 不再命中③
chk('wash + ctrl=90 + pos=0.30 -> 仅①（C3 后 ③ 位置门槛=0.25）',
    E._ctrl_note(90.0, 'wash', 0.30), '')                 # 2026-10-11 wash 文案关闭
chk('wash + ctrl=90 + pos=0.20 -> ①+③ 合并（设计如此）',
    E._ctrl_note(90.0, 'wash', 0.20), '高度控盘候选')      # 2026-10-11 wash 文案关闭
chk('wash + ctrl=90 + pos=0.60 -> 仅①',
    E._ctrl_note(90.0, 'wash', 0.60), '')                 # 2026-10-11 wash 文案关闭
chk('unknown + ctrl=80 -> 空', E._ctrl_note(80.0, 'unknown', 0.20), '')
P('   --- pos=None 守卫（关键：不守会抛 TypeError -> 被 except 吞掉 -> 该股全部提示消失）---')
chk('distribute + ctrl=95 + pos=None -> 空（不抛异常）',
    E._ctrl_note(95.0, 'distribute', None), '')
chk('unknown + ctrl=95 + pos=None -> 空',
    E._ctrl_note(95.0, 'unknown', None), '')
chk('wash + ctrl=90 + pos=None -> 仅①（③被守卫挡住）',
    E._ctrl_note(90.0, 'wash', None), '')                 # 2026-10-11 wash 文案关闭

P('\n' + '=' * 104)
P('验证 2  C2 定向用例：构造一个「up>1.3 且 down<0.8」的 df，看 +10 分是否真的没了')
P('=' * 104)
n = 80
rng = np.random.default_rng(1)
close = np.full(n, 10.0)
for i in range(1, n):
    close[i] = close[i - 1] * (1 + (0.004 if i % 3 else -0.002))
vol = np.full(n, 1.0e6)
# 最后 21 根里：上涨日放大、下跌日缩小 -> up_ratio>1.3 且 down_ratio<0.8
for i in range(n - 21, n):
    if close[i] > close[i - 1]:
        vol[i] = 2.2e6
    else:
        vol[i] = 0.35e6
df = pd.DataFrame({'open': close, 'high': close * 1.012, 'low': close * 0.988,
                   'close': close, 'volume': vol})

# 复刻分量（与 _audit_ctrl_reverse.py 的对拍公式一致，曾验证最大偏差 0.000e+00）
window = 20
recent = df.tail(window)
r = df['close'].tail(60).mean()
vm20 = float(df['volume'].tail(window).mean()); vm60 = float(df['volume'].tail(60).mean())
p = vm20 / (vm60 + 1e-8)
ts = _clamp100((1.2 - p) / 0.5 * 100.0)
seg = df.tail(window + 1)
ud = seg[seg['close'] > seg['close'].shift(1)]
dd = seg[seg['close'] < seg['close'].shift(1)]
vmn = float(seg['volume'].mean()) + 1e-8
ur = float(ud['volume'].mean()) / vmn if len(ud) else 1.0
dr = float(dd['volume'].mean()) / vmn if len(dd) else 1.0
vsb = 50.0
if ur < 0.85: vsb += 25.0
if dr > 1.15: vsb -= 15.0
amp = ((recent['high'] - recent['low']) / (recent['close'] + 1e-8)).mean()
# 2026-10-10 C5：振幅分量已改为「峰值 4.0% 帐篷」，复刻同步
amps = (100.0 - (0.040 - float(amp)) * 2300.0) if float(amp) <= 0.040 \
    else (100.0 - (float(amp) - 0.040) * 1200.0)
amps = _clamp100(amps)
t120 = df['close'].tail(120); lo, hi = float(t120.min()), float(t120.max())
pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
pw = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)

P('   构造样本：上涨日均量比=%.3f  下跌日均量比=%.3f  -> 命中被删分支的条件是 (%.3f>1.3 且 %.3f<0.8) = %s'
  % (ur, dr, ur, dr, (ur > 1.3 and dr < 0.8)))
exp_new = float(_clamp100((ts * 0.40 + _clamp100(vsb) * 0.35 + amps * 0.25) * pw))
exp_old = float(_clamp100((ts * 0.40 + _clamp100(vsb + 10.0) * 0.35 + amps * 0.25) * pw))
live = float(TI().estimate_control_score(df))
P('   实测 estimate_control_score = %.4f' % live)
P('   复算「无 +10 分」（= 改后应有值） = %.4f' % exp_new)
P('   复算「有 +10 分」（= 改前应有值） = %.4f' % exp_old)
chk('实测算分 == 无+10 的复算值', abs(live - exp_new) < 0.01, True)
chk('实测算分 != 有+10 的复算值（证明 +10 已删）', abs(live - exp_old) > 0.01, True)
P('   分数下降 = %.4f - %.4f = %.4f  （= 0.35 vol权重 x %.1f pos_weight x 10 分 = %.2f）'
  % (exp_old, live, exp_old - live, pw, 0.35 * pw * 10.0))

P('\n' + '=' * 104)
P('验证 3  真实库：改后出货警示命中集合（新口径 = distribute 且 pos>=0.65）')
P('=' * 104)
A = pd.read_csv(os.path.join(ROOT, 'tools', 'audit_ctrl_reverse_cross.BEFORE_c1c2.csv'), dtype={'code': str})
old_hit = A[(A.stage == 'distribute') & (A.score >= 60)]
new_hit = A[(A.stage == 'distribute') & (A.pos120 >= E._CTRL_DIST_POS)]
P('   改前口径 distribute & score>=60 : 命中 %3d 只 | 平均 pos120=%.3f' % (len(old_hit), old_hit.pos120.mean()))
P('   改后口径 distribute & pos>=0.65 : 命中 %3d 只 | 平均 pos120=%.3f' % (len(new_hit), new_hit.pos120.mean()))
P('   交集 %d 只 / 并集 %d 只 -> 命中数量几乎不变，但集合基本换掉了' %
  (len(set(old_hit.code) & set(new_hit.code)), len(set(old_hit.code) | set(new_hit.code))))
P('   改后才纳入的高位出货股（按 pos120 降序 前 12 只）：')
for _, rr in new_hit.sort_values('pos120', ascending=False).head(12).iterrows():
    tag = '改前已报' if rr.code in set(old_hit.code) else '改前漏报'
    P('     %-8s pos120=%.2f score=%.1f  %s' % (rr.code, rr.pos120, rr.score, tag))

P('\n' + '=' * 104)
P('单元验证结果：%s' % ('全部通过' if not fail else '失败 %d 项 -> %s' % (len(fail), fail)))
P('=' * 104)
_fh.close()
