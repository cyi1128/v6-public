# -*- coding: utf-8 -*-
"""V20 建仓因子单元测试 + C1~C5 回归（步骤四）

覆盖用户要求的：
  明显堆量 / 无明显堆量 / 明显红肥绿瘦 / 红瘦绿肥 / 数据不足
另加：缺列、None、NaN、纯上涨（无阴线）不默认通过、无未来数据。
回归：_ctrl_note 三参数行为必须与改动前逐字一致（7 张个股列表走的就是它）。
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'tools', 'buildfactor_unit.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')

OK = [0]
BAD = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


def check(nm, cond, detail=''):
    if cond:
        OK[0] += 1
        P('  [PASS] %s %s' % (nm, detail))
    else:
        BAD.append(nm)
        P('  [FAIL] %s %s' % (nm, detail))


import numpy as np
import pandas as pd
from strategy.base import TechnicalIndicators as TI

_ti = TI()


def mk(n=70, vol=None, closes=None, vol_up=None, vol_dn=None):
    """造 df。vol 给定则量能固定；vol_up/vol_dn 给定则按涨跌日给不同量。"""
    if closes is None:
        closes = list(np.linspace(10.0, 7.0, n))
    closes = np.array([float(x) for x in closes])
    if vol_up is not None or vol_dn is not None:
        v = []
        for i in range(n):
            if i == 0:
                v.append(float(vol_dn))
            else:
                v.append(float(vol_up) if closes[i] > closes[i - 1] else float(vol_dn))
    elif vol is None:
        v = [1000.0] * n
    elif isinstance(vol, (list, np.ndarray)):
        v = [float(x) for x in vol]
    else:
        v = [float(vol)] * n
    return pd.DataFrame({
        'close': closes, 'open': closes - 0.02,
        'high': closes + 0.06, 'low': closes - 0.06, 'volume': v,
    })


P('=' * 100)
P('V20 建仓因子单元测试 + C1~C5 回归')
P('=' * 100)

# ---------- A 数据不足 / 异常输入 ----------
P('\n[A] 数据不足与异常输入（必须不抛异常、给中性值）')
for nm, d in (('None', None), ('空 df', pd.DataFrame()),
              ('10 行（<60）', mk(10)), ('30 行', mk(30)), ('40 行', mk(40))):
    r1 = _ti.bottom_volume_stack(d)
    r2 = _ti.red_fat_green_thin(d)
    check('stack  %s -> ok=False score=0' % nm, r1['ok'] is False and r1['score'] == 0.0)
    check('redfat %s -> ok=False score=0' % nm, r2['ok'] is False and r2['score'] == 0.0)
d = mk(80)
check('缺 volume 列 -> ok=False',
      _ti.bottom_volume_stack(d.drop(columns=['volume']))['ok'] is False)
check('缺 close 列 -> ok=False',
      _ti.bottom_volume_stack(d.drop(columns=['close']))['ok'] is False)
check('redfat 缺 volume -> ok=False',
      _ti.red_fat_green_thin(d.drop(columns=['volume']))['ok'] is False)
_dn = mk(80)
_dn.loc[_dn.index[-5:], 'volume'] = np.nan
check('volume 含 NaN -> 不抛异常', isinstance(_ti.bottom_volume_stack(_dn), dict)
      and isinstance(_ti.red_fat_green_thin(_dn), dict))

# ---------- B 明显堆量 / 无明显堆量 ----------
P('\n[B] 底部堆量：明显 / 不明显')
_v = [1000.0] * 60 + [2000.0] * 10      # 近 10 日量 = 之前 20 日均量 x2
r = _ti.bottom_volume_stack(mk(70, vol=_v))
check('明显堆量 ok=True', r['ok'] is True, 'ratio=%.2f cont=%.2f pos=%.3f score=%.1f'
      % (r['ratio'], r['cont'], r['pos120'], r['score']))
check('明显堆量 ratio≈2.0', abs(r['ratio'] - 2.0) < 0.02, 'ratio=%.3f' % r['ratio'])
check('明显堆量 cont=1.0', abs(r['cont'] - 1.0) < 1e-9)
r = _ti.bottom_volume_stack(mk(70, vol=1000.0))
check('无明显堆量 ok=False（ratio<1.15）', r['ok'] is False, 'ratio=%.3f' % r['ratio'])
_v = [1000.0] * 69 + [9000.0]           # 仅末日爆量
r = _ti.bottom_volume_stack(mk(70, vol=_v))
check('单日爆量 cont 不足 -> ok=False', r['ok'] is False, 'ratio=%.2f cont=%.2f' % (r['ratio'], r['cont']))
_v = [1000.0] * 60 + [2000.0] * 10
_hi = list(np.linspace(7.0, 10.0, 70))  # 价格在高位（pos120 高）
r = _ti.bottom_volume_stack(mk(70, vol=_v, closes=_hi))
check('堆量但位置高 -> ok=False', r['ok'] is False, 'pos120=%.3f' % r['pos120'])
_v = [1000.0] * 60 + [4000.0] * 10      # ratio=4 > 上限 3.5
r = _ti.bottom_volume_stack(mk(70, vol=_v))
check('堆量过头 ratio>3.5 -> ok=False', r['ok'] is False, 'ratio=%.2f' % r['ratio'])

# ---------- C 红肥绿瘦 / 红瘦绿肥 ----------
P('\n[C] 红肥绿瘦 vs 红瘦绿肥')
_cl = [10.0, 10.2, 10.0, 10.2, 10.0] * 17  # 交替涨跌
r = _ti.red_fat_green_thin(mk(85, closes=_cl[:85], vol_up=2000.0, vol_dn=800.0), window=20)
check('明显红肥绿瘦 ok=True', r['ok'] is True,
      'ratio=%.2f up=%d dn=%d score=%.1f' % (r['ratio'], r['up_days'], r['down_days'], r['score']))
check('明显红肥绿瘦 ratio≈2.5', abs(r['ratio'] - 2.5) < 0.05, 'ratio=%.3f' % r['ratio'])
r = _ti.red_fat_green_thin(mk(85, closes=_cl[:85], vol_up=800.0, vol_dn=2000.0), window=20)
check('红瘦绿肥 ok=False', r['ok'] is False, 'ratio=%.3f' % r['ratio'])
check('红瘦绿肥 score=0（不为负）', r['score'] == 0.0, 'score=%.1f' % r['score'])
r = _ti.red_fat_green_thin(mk(85, closes=_cl[:85], vol_up=1100.0, vol_dn=1000.0), window=20)
check('临界 ratio=1.1 < 1.30 -> ok=False', r['ok'] is False, 'ratio=%.3f' % r['ratio'])

# ---------- D 纯上涨（无阴线）不能默认通过 ----------
P('\n[D] 只有上涨日 / 只有下跌日（缺失一侧不默认通过）')
_up = list(np.linspace(8.0, 12.0, 85))
r = _ti.red_fat_green_thin(mk(85, closes=_up), window=20)
check('纯上涨 dn<3 -> ok=False', r['ok'] is False and r['down_days'] < 3,
      'up=%d dn=%d' % (r['up_days'], r['down_days']))
_dw = list(np.linspace(12.0, 8.0, 85))
r = _ti.red_fat_green_thin(mk(85, closes=_dw), window=20)
check('纯下跌 up<3 -> ok=False', r['ok'] is False and r['up_days'] < 3,
      'up=%d dn=%d' % (r['up_days'], r['down_days']))

# ---------- E 无未来数据 ----------
P('\n[E] 无未来数据：把 T 之后的行改掉，T 时点的结果必须不变')
_a = mk(70, vol=[1000.0] * 60 + [2000.0] * 10)
_b = _a.copy()
_b.loc[_b.index[60:], 'volume'] = 99999.0   # 只改 T=59 之后的行
_r_a = _ti.bottom_volume_stack(_a.iloc[:60])
_r_b = _ti.bottom_volume_stack(_b.iloc[:60])
check('stack 截断到 T 的结果不受 T 之后影响', _r_a == _r_b, str(_r_a == _r_b))
_cl = [10.0, 10.2, 10.0, 10.2, 10.0] * 17
_c = mk(85, closes=_cl[:85], vol_up=2000.0, vol_dn=800.0)
_d = _c.copy()
_d.loc[_d.index[60:], 'volume'] = 99999.0
_r_c = _ti.red_fat_green_thin(_c.iloc[:61], window=20)
_r_d = _ti.red_fat_green_thin(_d.iloc[:61], window=20)
check('redfat 截断到 T 的结果不受 T 之后影响', _r_c == _r_d)

# ---------- F C1~C5 回归：_ctrl_note 三参数行为逐字不变 ----------
P('\n[F] C1~C5 回归：_ctrl_note(ctrl, stage, pos) 三参数行为（7 张个股列表走这条路）')
import services.band_pattern_engine as E

P('  当前阈值: _CTRL_HIGH=%.0f _CTRL_CAND_POS=%.2f _CTRL_DIST_POS=%.2f _BUILD_NOTE_MODE=%s'
  % (E._CTRL_HIGH, E._CTRL_CAND_POS, E._CTRL_DIST_POS, E._BUILD_NOTE_MODE))
cases = [
    (95.0, 'wash', 0.10, '高度控盘候选'),   # 2026-10-11 wash 文案关闭
    (95.0, 'wash', 0.90, ''),   # 2026-10-11 wash 文案关闭
    (95.0, 'distribute', 0.70, '出货风险警示'),
    (95.0, 'distribute', 0.30, ''),   # 0.30 既不 >=0.65（出货）也不 <0.25（候选）-> 无文案
    (95.0, 'distribute', 0.20, '高度控盘候选'),
    (95.0, 'unknown', 0.10, '高度控盘候选'),
    (95.0, 'unknown', 0.50, ''),
    (70.0, 'wash', 0.10, ''),
    (90.0, 'distribute', 0.65, '出货风险警示'),
    (95.0, 'distribute', None, ''),
    (0.0, 'unknown', None, ''),
]
for ctrl, st, pos, exp in cases:
    got = E._ctrl_note(ctrl, st, pos)
    check('_ctrl_note(%.0f,%s,%s)' % (ctrl, st, pos), got == exp, '-> %r' % got)
check('_ctrl_note 传 None pos 不抛异常', isinstance(E._ctrl_note(95.0, 'distribute', None), str))

# ---------- G 开关默认 off：建仓文案不出现 ----------
P('\n[G] 开关默认 off：即使传入因子分也不产生建仓文案')
check('默认 mode=off', E._BUILD_NOTE_MODE == 'off', "mode=%s" % E._BUILD_NOTE_MODE)
got = E._ctrl_note(95.0, 'unknown', 0.10, 99.0, 99.0)
check('off 时四参数 == 三参数', got == E._ctrl_note(95.0, 'unknown', 0.10), '-> %r' % got)


def _with_mode(mode, ctrl, st, pos, stack, redfat):
    old = E._BUILD_NOTE_MODE
    E._BUILD_NOTE_MODE = mode
    try:
        return E._ctrl_note(ctrl, st, pos, stack, redfat)
    finally:
        E._BUILD_NOTE_MODE = old


_g = _with_mode('buy', 95.0, 'unknown', 0.10, 99.0, 99.0)
check("mode='buy' 能出三条建仓文案",
      '疑似底部堆量' in _g and '红肥绿瘦建仓特征' in _g and '建仓加强' in _g, '-> %r' % _g)
_g = _with_mode('buy', 95.0, 'unknown', 0.50, 99.0, 99.0)
check("mode='buy' 位置高时不出「建仓加强」",
      '疑似底部堆量' in _g and '建仓加强' not in _g, '-> %r' % _g)
_g = _with_mode('warn', 95.0, 'unknown', 0.10, 99.0, 99.0)
check("mode='warn' 出「过热」文案", '过热' in _g, '-> %r' % _g)
_g = _with_mode('warn', 95.0, 'unknown', 0.10, 10.0, 10.0)
check("mode='warn' 因子不满足时不出", '过热' not in _g, '-> %r' % _g)

P('\n' + '=' * 100)
P('结果: %d 项通过 / %d 项失败' % (OK[0], len(BAD)))
if BAD:
    for b in BAD:
        P('  FAIL: ' + b)
P('=' * 100)
_fh.close()
print('\n已写:', OUT)
sys.exit(1 if BAD else 0)
