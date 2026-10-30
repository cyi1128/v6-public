# -*- coding: utf-8 -*-
"""C3 + C5 单元验证（2026-10-10）

C3  services/band_pattern_engine.py  _ctrl_note 规则③
    「分数主导 score>=_CTRL_CAND(90) & pos<_CTRL_POS_LOW(0.4)」
 -> 「位置主导 pos<_CTRL_CAND_POS(0.25) & ctrl>=_CTRL_HIGH(85)」

C5  strategy/base.py  estimate_control_score 的振幅分量
    「100 - amp*300」（振幅越低分越高，方向反了）
 -> 「峰值 4.0% 的帐篷」（过低与过高同样降分）

验证 1  C3 规则矩阵（含改前会误报 / 漏报的边界用例）
验证 2  C5 方向证明：构造三个只差振幅的 df，验证 适中 > 过大 > 过低
验证 3  C5 全公式对拍：真实函数 == 手工复算（防止分量与实际不一致）
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
from strategy.base import TechnicalIndicators as TI, _clamp100

OUT = os.path.join(ROOT, 'tools', 'c3c5_unit.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


fail = []


def chk(name, got, want):
    ok = (got == want)
    if not ok:
        fail.append(name)
    P('   %s %-58s got=%r' % ('OK ' if ok else 'XX ', name, got) +
      ('' if ok else '  want=%r' % (want,)))


P('=' * 104)
P('C3 + C5 单元验证')
P('=' * 104)
P('阈值实测:')
P('   _CTRL_HIGH=%s   _CTRL_CAND=%s（已停用C3）   _CTRL_CAND_POS=%s'
  % (E._CTRL_HIGH, E._CTRL_CAND, E._CTRL_CAND_POS))
P('   _CTRL_POS_LOW=%s（已停用C3）   _CTRL_DIST=%s（已停用C1）   _CTRL_DIST_POS=%s'
  % (E._CTRL_POS_LOW, E._CTRL_DIST, E._CTRL_DIST_POS))

# ==================================================================
P('\n' + '=' * 104)
P('验证 1  C3：规则③ 位置门槛 0.25 + 分数门槛 85')
P('=' * 104)
P('   --- 新口径应命中 ---')
chk('pos=0.20 + ctrl=85（分数含等号）-> 候选',
    E._ctrl_note(85.0, 'unknown', 0.20), '高度控盘候选')
chk('pos=0.249 + ctrl=95 -> 候选',
    E._ctrl_note(95.0, 'unknown', 0.249), '高度控盘候选')
chk('pos=0.00 + ctrl=100 -> 候选',
    E._ctrl_note(100.0, 'unknown', 0.00), '高度控盘候选')
P('   --- 新口径应挡住（改前会误报候选的正是这两类）---')
chk('pos=0.25（位置含等号外）-> 空',
    E._ctrl_note(95.0, 'unknown', 0.25), '')
chk('pos=0.30 + ctrl=95 -> 空（改前会报候选）',
    E._ctrl_note(95.0, 'unknown', 0.30), '')
chk('pos=0.39 + ctrl=95 -> 空（改前会报候选）',
    E._ctrl_note(95.0, 'unknown', 0.39), '')
chk('pos=0.20 + ctrl=84.9（分数不到）-> 空',
    E._ctrl_note(84.9, 'unknown', 0.20), '')
chk('pos=None + ctrl=95 -> 空（守卫生效，不抛异常）',
    E._ctrl_note(95.0, 'unknown', None), '')
P('   --- 与规则① / 规则② 的共存 ---')
chk('wash + ctrl=90 + pos=0.20 -> ①+③ 合并（设计如此）',
    E._ctrl_note(90.0, 'wash', 0.20), '高度控盘候选')      # 2026-10-11 wash 文案关闭
chk('wash + ctrl=90 + pos=0.30 -> 仅①（③位置被挡）',
    E._ctrl_note(90.0, 'wash', 0.30), '')                 # 2026-10-11 wash 文案关闭
chk('distribute + ctrl=95 + pos=0.20 -> 仅候选（未到出货位置）',
    E._ctrl_note(95.0, 'distribute', 0.20), '高度控盘候选')
chk('distribute + ctrl=95 + pos=0.80 -> 仅出货（位置太高不入候选）',
    E._ctrl_note(95.0, 'distribute', 0.80), '出货风险警示')

# ==================================================================
P('\n' + '=' * 104)
P('验证 2  C5：构造三个「只差振幅」的 df，验证 适中 > 过大 > 过低')
P('=' * 104)
n = 140
close = np.linspace(10.0, 11.0, n)
close = close * (1.0 + 0.01 * np.sin(np.arange(n) / 2.0))   # 加波动，保证有涨跌日
vol = np.full(n, 1.0e6) * (1.0 + 0.2 * np.cos(np.arange(n) / 3.0))


def mk(a):
    """high/low 相对 close 对称张开 a，则 20日均振幅 == 2a"""
    return pd.DataFrame({'open': close, 'high': close * (1 + a), 'low': close * (1 - a),
                         'close': close, 'volume': vol})


def tent(amp):
    v = (100.0 - (0.040 - amp) * 2300.0) if amp <= 0.040 else (100.0 - (amp - 0.040) * 1200.0)
    return float(_clamp100(v))


def old_amp(amp):
    return float(_clamp100(100.0 - amp * 300.0))


cases = [('死票(过窄)', 0.0075), ('适中(峰值)', 0.020), ('过大(剧烈)', 0.040)]
res = {}
P('   %-12s %-8s %-10s %-12s %-12s' % ('场景', 'amp', '新 amp_score', '旧 amp_score', '实测总分'))
for nm, a in cases:
    df = mk(a)
    amp = 2 * a
    sc = float(TI().estimate_control_score(df))
    res[nm] = (amp, tent(amp), old_amp(amp), sc)
    P('   %-12s %-8.3f %-10.2f %-12.2f %-12.4f' % (nm, amp, tent(amp), old_amp(amp), sc))

chk('适中 amp_score(100.0) > 过大 amp_score(52.0)', tent(0.040) > tent(0.080), True)
chk('过大 amp_score(52.0) > 死票 amp_score(42.5)', tent(0.080) > tent(0.015), True)
chk('方向已反转：旧口径 死票(95.5) > 适中(88.0)', old_amp(0.015) > old_amp(0.040), True)
chk('实测总分：适中 > 过大', res['适中(峰值)'][3] > res['过大(剧烈)'][3], True)
chk('实测总分：过大 > 死票', res['过大(剧烈)'][3] > res['死票(过窄)'][3], True)
chk('实测总分：适中 > 死票', res['适中(峰值)'][3] > res['死票(过窄)'][3], True)
P('   -> 三个 df 的 close/volume 完全相同，turnover_score、vol_score、pos_weight 逐位一致，')
P('      所以总分差只来自 amp_score，方向确实反过来了。')

# ==================================================================
P('\n' + '=' * 104)
P('验证 3  C5 全公式对拍：真实函数 == 手工复算（含新振幅分量）')
P('=' * 104)


def replicate(df):
    """按 strategy/base.py 现版公式逐项复算"""
    for c in ('close', 'high', 'low', 'volume'):
        if c not in df.columns:
            return None
    recent = df.tail(20)
    vm20 = float(df['volume'].tail(20).mean())
    vm60 = float(df['volume'].tail(60).mean())
    p = vm20 / (vm60 + 1e-8)
    ts = _clamp100((1.2 - p) / 0.5 * 100.0)
    seg = df.tail(21)
    ud = seg[seg['close'] > seg['close'].shift(1)]
    dd = seg[seg['close'] < seg['close'].shift(1)]
    vmn = float(seg['volume'].mean()) + 1e-8
    ur = float(ud['volume'].mean()) / vmn if len(ud) else 1.0
    dr = float(dd['volume'].mean()) / vmn if len(dd) else 1.0
    vs = 50.0
    if ur < 0.85:
        vs += 25.0
    if dr > 1.15:
        vs -= 15.0
    vs = _clamp100(vs)
    amp = float(((recent['high'] - recent['low']) / (recent['close'] + 1e-8)).mean())
    ams = tent(amp)
    t120 = df['close'].tail(120)
    lo, hi = float(t120.min()), float(t120.max())
    pos = (float(df['close'].iloc[-1]) - lo) / (hi - lo + 1e-8)
    pw = 1.2 if pos < 0.4 else (0.8 if pos > 0.7 else 1.0)
    return float(_clamp100((ts * 0.40 + vs * 0.35 + ams * 0.25) * pw)), dict(
        ts=ts, vs=vs, ams=ams, pw=pw, pos=pos, ur=ur, dr=dr, amp=amp)


rng = np.random.default_rng(20261010)
maxdiff = 0.0
nb = 0
for i in range(300):
    m = int(rng.integers(60, 121))
    c = 10.0 * np.cumprod(1 + rng.normal(0.0005, 0.02, m))
    a = rng.uniform(0.002, 0.06, m)
    d = pd.DataFrame({'open': c * (1 + rng.normal(0, 0.005, m)),
                      'high': c * (1 + a), 'low': c * (1 - a), 'close': c,
                      'volume': rng.uniform(5e5, 3e6, m)})
    real = float(TI().estimate_control_score(d))
    rep = replicate(d)
    if rep is None:
        continue
    nb += 1
    maxdiff = max(maxdiff, abs(real - rep[0]))
P('   随机 %d 个 df：真实函数 vs 手工复算  最大偏差 = %.3e' % (nb, maxdiff))
chk('全公式对拍最大偏差 < 1e-9', maxdiff < 1e-9, True)

# 边界
P('\n   边界：')
b1 = replicate(mk(0.001))
P('   极窄振幅 amp=0.002 -> amp_score=%.2f（旧口径 %.2f）' % (b1[1]['ams'], old_amp(0.002)))
b2 = replicate(mk(0.060))
P('   极宽振幅 amp=0.120 -> amp_score=%.2f（旧口径 %.2f）' % (b2[1]['ams'], old_amp(0.120)))
chk('极宽振幅仍被夹在 [0,100]', 0.0 <= b2[1]['ams'] <= 100.0, True)
chk('极窄振幅 amp_score 明显低于 60', b1[1]['ams'] < 60.0, True)
for bad in (None, pd.DataFrame()):
    chk('空输入返回 0.0', float(TI().estimate_control_score(bad)), 0.0)

P('\n' + '=' * 104)
P('单元验证结果：%s' % ('全部通过' if not fail else '失败 %d 项 -> %s' % (len(fail), fail)))
P('=' * 104)
_fh.close()
