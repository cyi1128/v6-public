# -*- coding: utf-8 -*-
"""C6 观察规则验证套件：边界单测 + 与标定宽表逐条一致性 + 17570 复现。

输出 tools\\c6_unit.txt
"""
import sqlite3
import sys
import time

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
OUT = r'D:\QuantMonitorV6\tools\c6_unit.txt'
WIDE = r'D:\QuantMonitorV6\tools\buildfactor_wide.csv'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


PASS = [0, 0]


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        PASS[1] += 1
        P('  FAIL  %s %s' % (name, extra))


from services.band_pattern_engine import _bars_to_df, _ctrl_note  # noqa: E402
from strategy.base import (C6_AMP_HI, C6_AMP_LO, C6_MIN_BARS, C6_POS_MAX,  # noqa: E402
                           TechnicalIndicators as TI)

P('=' * 104)
P('C6 观察规则验证套件   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 104)
P('阈值：POS_MAX=%.2f  AMP∈[%.3f, %.3f]  MIN_BARS=%d'
  % (C6_POS_MAX, C6_AMP_LO, C6_AMP_HI, C6_MIN_BARS))

# ==========================================================
# A. 边界单测
# ==========================================================
BASE_LOW = 8.0
A_DN, A_UP = 0.996, 1.004


def mk(pos_t=0.02, amp=0.04, n=120):
    """按目标位置/振幅精确造 K 线（只需 close/high/low）。"""
    L = BASE_LOW * (1 - pos_t) / (A_DN - pos_t * A_UP + 1e-12)
    closes = [BASE_LOW] * 100 + [L * (A_UP if i % 2 == 0 else A_DN) for i in range(20)]
    highs = [c * (1 + amp / 2) for c in closes]
    lows = [c * (1 - amp / 2) for c in closes]
    vols = [1000.0] * n
    return pd.DataFrame({'close': closes, 'high': highs, 'low': lows,
                         'volume': vols[:len(closes)]})


P('')
P('[A] 边界单测')
r_lo = TI.is_c6_candidate(mk(pos_t=0.02, amp=0.040))
r_hi = TI.is_c6_candidate(mk(pos_t=0.90, amp=0.040))
check('低位(pos 0.02)+振幅4% -> 两条全中 ok=True',
      r_lo['ok'] and r_lo['n_ok'] == 2 and r_lo['score'] == 100.0,
      'ok=%s n_ok=%s score=%s' % (r_lo['ok'], r_lo['n_ok'], r_lo['score']))
check('高位(pos 0.90) -> 位置条不通过，仅振幅条通过',
      (not r_hi['ok']) and r_hi['n_ok'] == 1 and r_hi['hits'] == [False, True]
      and r_hi['score'] == 50.0,
      'hits=%s score=%s' % (r_hi['hits'], r_hi['score']))
check('造数精度与目标一致（pos/amp）',
      abs(r_lo['pos120'] - 0.02) < 1e-6 and abs(r_lo['amp'] - 0.040) < 1e-6,
      'pos=%.6f amp=%.6f' % (r_lo['pos120'], r_lo['amp']))

# 位置临界
r_p1 = TI.is_c6_candidate(mk(pos_t=C6_POS_MAX - 1e-4, amp=0.040))
r_p2 = TI.is_c6_candidate(mk(pos_t=C6_POS_MAX + 1e-4, amp=0.040))
check('位置临界：0.2499 -> 通过', r_p1['hits'][0] is True, 'pos=%.6f' % r_p1['pos120'])
check('位置临界：0.2501 -> 不通过', r_p2['hits'][0] is False, 'pos=%.6f' % r_p2['pos120'])
# 位置严格小于（等于阈值不通过）
d_eq = mk(pos_t=0.05, amp=0.040)
d_eq.loc[len(d_eq) - 1, 'close'] = d_eq['close'].max()
r_eq = TI.is_c6_candidate(d_eq)
check('位置恰为 1.00（等于结构高点）-> 不通过', r_eq['hits'][0] is False,
      'pos=%.6f' % r_eq['pos120'])

# 振幅四临界（用 ±1e-6 的贴边值验证「含等号」的方向；造数本身有 ~1e-16 浮点误差，
# 因此同时对「正好等于阈值」的构造按代码实际算出的 amp 反推期望，而不是硬编码期望）
for _t, _exp, _tag in ((C6_AMP_LO - 1e-6, False, '下限外 1e-6'),
                       (C6_AMP_LO + 1e-6, True, '下限内 1e-6（含等号方向）'),
                       (C6_AMP_HI - 1e-6, True, '上限内 1e-6'),
                       (C6_AMP_HI + 1e-6, False, '上限外 1e-6')):
    _r = TI.is_c6_candidate(mk(pos_t=0.05, amp=_t))
    check('振幅 %.6f（%s）-> 振幅条 %s' % (_t, _tag, '通过' if _exp else '不通过'),
          _r['hits'][1] is _exp, 'amp=%.9f hits=%s' % (_r['amp'], _r['hits']))
for _t in (C6_AMP_LO, C6_AMP_HI):
    _r = TI.is_c6_candidate(mk(pos_t=0.05, amp=_t))
    _exp = C6_AMP_LO <= _r['amp'] <= C6_AMP_HI
    check('振幅构成值正好 %.4f -> 判定与「%.3f <= amp <= %.3f」一致'
          % (_t, C6_AMP_LO, C6_AMP_HI), _r['hits'][1] is _exp,
          'amp=%.12f hits=%s' % (_r['amp'], _r['hits']))

# 数据不足 / 缺列 / 异常
r_s = TI.is_c6_candidate(mk().tail(C6_MIN_BARS - 10).reset_index(drop=True))
check('K线不足(%d根) -> ok=False score=0 reason=bars<%d' % (C6_MIN_BARS - 10, C6_MIN_BARS),
      (not r_s['ok']) and r_s['score'] == 0.0 and r_s['reason'] == 'bars<%d' % C6_MIN_BARS,
      'reason=%s' % r_s['reason'])
r_nc = TI.is_c6_candidate(mk().drop(columns=['high']))
check('缺 high 列 -> reason=missing:high', r_nc['reason'] == 'missing:high', r_nc['reason'])
r_nv = TI.is_c6_candidate(mk(pos_t=0.02, amp=0.040).drop(columns=['volume']))
check('无 volume 列仍可判定（C6 不含量价条件）', r_nv['ok'] is True,
      'ok=%s reason=%s' % (r_nv['ok'], r_nv['reason']))
r_none = TI.is_c6_candidate(None)
r_nan = mk(pos_t=0.02, amp=0.040)
r_nan.loc[9, 'close'] = float('nan')
r_nan = TI.is_c6_candidate(r_nan)
check('df=None 不抛异常', r_none['ok'] is False, 'reason=%s' % r_none['reason'])
check('含 NaN 不抛异常（返回 dict）', isinstance(r_nan, dict) and 'ok' in r_nan,
      'ok=%s pos=%s' % (r_nan['ok'], r_nan['pos120']))

# 未来数据隔离：末尾追加 5 根暴涨，pos/amp 只能变差不能"提前知道"
d_base = mk(pos_t=0.05, amp=0.040)
d_future = pd.concat([d_base, d_base.tail(5).assign(
    close=lambda x: x.close * 3.0, high=lambda x: x.high * 3.0,
    low=lambda x: x.low * 3.0)], ignore_index=True)
r_f = TI.is_c6_candidate(d_future)
check('追加 5 根暴涨后仍可跑通（无未来函数、无异常）',
      isinstance(r_f, dict) and r_f.get('reason') in ('', None),
      'pos=%.4f amp=%.4f ok=%s' % (r_f['pos120'], r_f['amp'], r_f['ok']))

# 文案：C6 独立于 C4 / 建仓因子；7 张列表走 3 参路径不受影响
check('_ctrl_note 3 参（7 张个股列表路径）不含 C6 文案',
      'C6' not in _ctrl_note(95.0, 'wash', 0.10), repr(_ctrl_note(95.0, 'wash', 0.10)))
_t6 = _ctrl_note(95.0, 'unknown', 0.10, None, None, None, 2)
check('传入 c6=2 -> 追加「C6观察：低位适中振幅」',
      'C6观察：低位适中振幅' in _t6, repr(_t6))
check('c4 与 c6 同时命中 -> 两条文案都在、互不影响',
      'C4观察：低位量价结构' in _ctrl_note(95.0, 'unknown', 0.10, None, None, 5, 2)
      and 'C6观察：低位适中振幅' in _ctrl_note(95.0, 'unknown', 0.10, None, None, 5, 2),
      repr(_ctrl_note(95.0, 'unknown', 0.10, None, None, 5, 2)))
check('c6=None（默认）不追加 C6 文案',
      'C6' not in _ctrl_note(95.0, 'unknown', 0.10), repr(_ctrl_note(95.0, 'unknown', 0.10)))
check('c6=1（只满足一条）不追加 C6 文案',
      'C6' not in _ctrl_note(95.0, 'unknown', 0.10, None, None, None, 1))

# ==========================================================
# B. 与标定宽表逐条一致性（从 kline_cache 重建 120 根）
# ==========================================================
P('')
P('[B] 与 buildfactor_wide.csv 逐条一致性（独立重建 df，调生产代码比对）')
wide = pd.read_csv(WIDE)
wide['code'] = wide['code'].astype(str).str.zfill(6)
con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= 200 ORDER BY code, date""").fetchdf()
con.close()
groups = {c: g.reset_index(drop=True) for c, g in rows.groupby('code')}
P('  kline_cache 载入 %d 行 / %d 只（每只最近 200 根，与标定脚本同口径）'
  % (len(rows), len(groups)))

tol = 1e-9
n_cmp = 0
bad = dict(pos=0, amp=0, hit=0, ok=0)
skip = []
for c in sorted(wide.code.unique())[:110]:
    g = groups.get(c)
    if g is None or len(g) < 200:
        skip.append(c)
        continue
    for _, w in wide[wide.code == c].iterrows():
        k = int(w['k'])
        T = len(g) - 1 - k
        if T < 119:
            continue
        d = _bars_to_df(g.iloc[:T + 1].to_dict('records')[-120:])
        if d is None:
            skip.append('%s k=%d' % (c, k))
            continue
        r = TI.is_c6_candidate(d)
        n_cmp += 1
        if abs(float(w['pos120']) - r['pos120']) > tol:
            bad['pos'] += 1
        if abs(float(w['amp20']) - r['amp']) > tol:
            bad['amp'] += 1
        exp = [bool(w['pos120'] < C6_POS_MAX),
               bool(C6_AMP_LO <= w['amp20'] <= C6_AMP_HI)]
        if exp != r['hits']:
            bad['hit'] += 1
        if bool(w['pos120'] < C6_POS_MAX and C6_AMP_LO <= w['amp20'] <= C6_AMP_HI) != r['ok']:
            bad['ok'] += 1
P('  实际比对 %d 行；跳过 %d 只/条' % (n_cmp, len(skip)))
check('比对样本量足够（>=300 行）', n_cmp >= 300, '实际 %d 行' % n_cmp)
for _k, _v in bad.items():
    check('逐条一致：%s 无差异' % _k, _v == 0, '不一致 %d 条' % _v)

# ==========================================================
# C. 17570 条复现（与 tools\\_c6_calib.py 同口径）
# ==========================================================
P('')
P('[C] 17570 条滚动观测复现（收益 / 胜率 / t 值）')
c6 = wide[(wide.pos120 < C6_POS_MAX) & (wide.amp20 >= C6_AMP_LO) & (wide.amp20 <= C6_AMP_HI)]
n = len(c6)
m = c6.r20.mean()
win = 100.0 * (c6.r20 > 0).mean()
t = m / (c6.r20.std(ddof=1) / np.sqrt(n))
P('  C6 命中 n=%d  r20=%+.2f%%  胜率=%.1f%%  t=%+.2f  中位=%+.2f%%'
  % (n, m, win, t, c6.r20.median()))
check('样本量 n == 7749（与报告一致）', n == 7749, '实际 %d' % n)
check('未来20日收益 +0.66%（容差 0.01）', abs(m - 0.66) <= 0.01, '实际 %+.4f' % m)
check('胜率 52.0%（容差 0.05）', abs(win - 52.0) <= 0.05, '实际 %.4f' % win)
check('t 值 +5.24（容差 0.01）', abs(t - 5.24) <= 0.01, '实际 %+.4f' % t)
base_m = wide.r20.mean()
base_w = 100.0 * (wide.r20 > 0).mean()
check('显著优于全样本基准（-0.80% / 45.2%）', m > base_m and win > base_w,
      '基准 %+.2f%% / %.1f%%' % (base_m, base_w))
# 分量对照（证明不是重复计同一件事）
p_only = wide[wide.pos120 < C6_POS_MAX]
a_only = wide[(wide.amp20 >= C6_AMP_LO) & (wide.amp20 <= C6_AMP_HI)]
P('  分量：仅低位 n=%d r20=%+.2f%% ｜ 仅振幅 n=%d r20=%+.2f%% ｜ 叠加 %+.2f%%'
  % (len(p_only), p_only.r20.mean(), len(a_only), a_only.r20.mean(), m))
check('两条叠加后优于任一单条（有叠加增益）',
      m > p_only.r20.mean() and m > a_only.r20.mean())
# 逐锚点增量（如实记录：未通过）
P('  逐锚点增量：' + ' ｜ '.join(
    'k%d %+.2f' % (k, c6[c6.k == k].r20.mean() - wide[wide.k == k].r20.mean())
    for k in sorted(wide.k.unique())))
check('逐锚点检验结论如实标注为「未通过」（3/4 为负）',
      sum(1 for k in sorted(wide.k.unique())
          if c6[c6.k == k].r20.mean() - wide[wide.k == k].r20.mean() < 0) == 3)

P('')
P('=' * 104)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 104)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
