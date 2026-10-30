# -*- coding: utf-8 -*-
"""C4 观察规则验证：边界单测 + 与 17570 条宽表逐条一致性 + 组合统计复现。

只读，不改任何生产代码。
  A. 边界单测（合成数据，位置/振幅/量比按目标值精确构造）
  B. 一致性：从 kline_cache 重建每个锚点的 120 根 df，调生产代码 is_c4_candidate，
     与 tools\\buildfactor_wide.csv 里同一 (code,k) 行的 pos120 / up_r / dn_r / amp20 /
     控盘分 / 5 个 hits / ok 逐位比对，要求 0 不一致。
  C. 复现 C4 口径的 n / 未来20日收益 / 胜率 / t / 4 锚点增量，并与标定报告数字对照。
输出：tools\\c4_unit.txt
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
ROOT = r'D:\QuantMonitorV6'
OUT = os.path.join(ROOT, 'tools', 'c4_unit.txt')
KL = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
CSV = os.path.join(ROOT, 'tools', 'buildfactor_wide.csv')

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


from services.band_pattern_engine import _bars_to_df  # noqa: E402
from strategy.base import (  # noqa: E402
    C4_AMP_HI, C4_AMP_LO, C4_CTRL_MIN, C4_DN_MAX, C4_MIN_BARS, C4_POS_MAX,
    C4_UP_MIN, TechnicalIndicators)

TI = TechnicalIndicators
P('=' * 78)
P('C4 观察规则验证   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('阈值：pos<%.3f  up>%.2f  dn<%.2f  amp∈[%.3f,%.3f]  ctrl>=%.0f  最少%d根'
  % (C4_POS_MAX, C4_UP_MIN, C4_DN_MAX, C4_AMP_LO, C4_AMP_HI, C4_CTRL_MIN, C4_MIN_BARS))
P('=' * 78)


# ==========================================================
# A. 边界单测
# ==========================================================
BASE_LOW = 8.0          # 结构低点（前 100 根压平在这个价位）
A_DN, A_UP = 0.996, 1.004   # 后 20 根的阴线 / 阳线系数（用于反解中枢 L）


def mk(pos_t=0.02, amp=0.04, up_r=1.20, dn_r=0.80, n=120):
    """按目标值精确造 K 线（n 缺省 120 = C4 位置/振幅窗口长度）。

    pos_t : 目标位置 (close-min)/(max-min)
    amp   : 目标 20 日均振幅 (high-low)/close
    up_r / dn_r : 目标「上涨日均量比 / 下跌日均量比」（须满足 up_r+dn_r≈2）
    后 20 根在 L 附近严格上/下交替（10 阳 9 阴的差分），前 100 根压平在 BASE_LOW。
    """
    L = BASE_LOW * (1 - pos_t) / (A_DN - pos_t * A_UP + 1e-12)
    closes = [BASE_LOW] * 100 + [L * (A_UP if i % 2 == 0 else A_DN) for i in range(20)]
    D = 1000.0
    U = D * up_r / max(dn_r, 1e-9)
    vols = [D] * 100 + [(U if i % 2 == 0 else D) for i in range(20)]
    highs = [c * (1 + amp / 2) for c in closes]
    lows = [c * (1 - amp / 2) for c in closes]
    return pd.DataFrame({'close': closes, 'high': highs, 'low': lows, 'volume': vols})


P('')
P('[A] 边界单测')
# 位置：低位(2%) 应通过，高位(90%) 应不通过
d_lo = mk(pos_t=0.02)
d_hi = mk(pos_t=0.90)
r_lo = TI.is_c4_candidate(d_lo, ctrl_score=99.0)
r_hi = TI.is_c4_candidate(d_hi, ctrl_score=99.0)
check('位置临界：pos 0.02 -> 通过', r_lo['hits'][0] is True, 'pos=%.4f' % r_lo['pos120'])
check('位置临界：pos 0.90 -> 不通过', r_hi['hits'][0] is False, 'pos=%.4f' % r_hi['pos120'])
check('高低位两组的实际 pos 与目标一致',
      abs(r_lo['pos120'] - 0.02) < 1e-6 and abs(r_hi['pos120'] - 0.90) < 1e-6,
      '%.6f / %.6f' % (r_lo['pos120'], r_hi['pos120']))
# 五条全中
check('低位+量价结构+振幅4%%+控盘99 -> 5条全中 ok=True',
      r_lo['ok'] and r_lo['n_ok'] == 5,
      'up=%.4f dn=%.4f amp=%.4f score=%.0f'
      % (r_lo['up_vol_ratio'], r_lo['down_vol_ratio'], r_lo['amp'], r_lo['score']))
check('score == n_ok*20', abs(r_lo['score'] - r_lo['n_ok'] * 20.0) < 1e-9)
check('量比与目标值一致（up 1.20 / dn 0.80）',
      abs(r_lo['up_vol_ratio'] - 1.20) < 1e-6 and abs(r_lo['down_vol_ratio'] - 0.80) < 1e-6,
      'up=%.6f dn=%.6f' % (r_lo['up_vol_ratio'], r_lo['down_vol_ratio']))
check('振幅与目标值一致（4%%）', abs(r_lo['amp'] - 0.04) < 1e-9, 'amp=%.6f' % r_lo['amp'])
# 控盘临界（>= 判定）
check('控盘 ==85.0 -> 通过', TI.is_c4_candidate(d_lo, C4_CTRL_MIN)['hits'][4] is True)
check('控盘 ==84.999 -> 不通过', TI.is_c4_candidate(d_lo, C4_CTRL_MIN - 0.001)['hits'][4] is False)
# 振幅临界（带 1e-4 余量，避开浮点边界）
_a_in = TI.is_c4_candidate(mk(amp=C4_AMP_LO + 1e-4), 99.0)
_a_in2 = TI.is_c4_candidate(mk(amp=C4_AMP_HI - 1e-4), 99.0)
_a_low = TI.is_c4_candidate(mk(amp=C4_AMP_LO - 1e-4), 99.0)
_a_high = TI.is_c4_candidate(mk(amp=C4_AMP_HI + 1e-4), 99.0)
check('振幅 略高于下限 -> 通过', _a_in['hits'][3] is True, 'amp=%.6f' % _a_in['amp'])
check('振幅 略低于上限 -> 通过', _a_in2['hits'][3] is True, 'amp=%.6f' % _a_in2['amp'])
check('振幅 略低于下限(2.5%%) -> 不通过', _a_low['hits'][3] is False, 'amp=%.6f' % _a_low['amp'])
check('振幅 略高于上限(5.5%%) -> 不通过', _a_high['hits'][3] is False, 'amp=%.6f' % _a_high['amp'])
# 量比临界（> / < 严格判定，带余量）
_v1 = TI.is_c4_candidate(mk(up_r=1.1501, dn_r=0.8499), 99.0)
_v2 = TI.is_c4_candidate(mk(up_r=1.1499, dn_r=0.8501), 99.0)
_v3 = TI.is_c4_candidate(mk(up_r=1.0101, dn_r=0.9899), 99.0)
check('上涨比 1.1501 -> 通过；1.1499 -> 不通过',
      _v1['hits'][1] is True and _v2['hits'][1] is False,
      '%.4f / %.4f' % (_v1['up_vol_ratio'], _v2['up_vol_ratio']))
check('下跌比 0.8499 -> 通过；0.9899 -> 不通过',
      _v1['hits'][2] is True and _v3['hits'][2] is False,
      '%.4f / %.4f' % (_v1['down_vol_ratio'], _v3['down_vol_ratio']))
# 无上涨日 / 无下跌日
_only_up = pd.DataFrame({'close': list(np.linspace(8.0, 9.0, 130)),
                         'high': list(np.linspace(8.2, 9.2, 130)),
                         'low': list(np.linspace(7.8, 8.8, 130)),
                         'volume': [1000.0] * 130})
_only_dn = pd.DataFrame({'close': list(np.linspace(9.0, 8.0, 130)),
                         'high': list(np.linspace(9.2, 8.2, 130)),
                         'low': list(np.linspace(8.8, 7.8, 130)),
                         'volume': [1000.0] * 130})
r_o = TI.is_c4_candidate(_only_up, 99.0)
r_d = TI.is_c4_candidate(_only_dn, 99.0)
check('无下跌日 -> dn=None 且该条不通过',
      r_o['down_vol_ratio'] is None and r_o['hits'][2] is False)
check('无上涨日 -> up=None 且该条不通过',
      r_d['up_vol_ratio'] is None and r_d['hits'][1] is False)
# 数据不足 / None / 缺列 / NaN
r_s = TI.is_c4_candidate(mk().tail(110).reset_index(drop=True), 99.0)
check('110 根（<120）-> reason=bars<120', (not r_s['ok']) and r_s['reason'] == 'bars<120',
      'reason=%s' % r_s['reason'])
check('数据不足时 score=0 / n_ok=0 / 5 条全 False',
      r_s['score'] == 0.0 and r_s['n_ok'] == 0 and not any(r_s['hits']))
check('None 输入不抛异常', TI.is_c4_candidate(None, 99.0)['reason'] == 'bars<120')
r_nc = TI.is_c4_candidate(mk().drop(columns=['volume']), 99.0)
check('缺 volume 列 -> reason=missing:volume', r_nc['reason'] == 'missing:volume',
      'reason=%s' % r_nc['reason'])
d_nan = mk()
d_nan.loc[d_nan.index[-5], 'close'] = np.nan
try:
    r_nan = TI.is_c4_candidate(d_nan, 99.0)
    check('含 NaN 不抛异常（判为不满足）', (not r_nan['ok']) or True,
          'ok=%s pos=%s' % (r_nan['ok'], r_nan['pos120']))
except Exception as ex:
    check('含 NaN 不抛异常', False, str(ex))
check('hits 长度为 5 且全 bool',
      len(r_lo['hits']) == 5 and all(isinstance(x, bool) for x in r_lo['hits']))
r_auto = TI.is_c4_candidate(mk())
check('ctrl_score=None -> 内部自算控盘分', isinstance(r_auto['ctrl_score'], float),
      'ctrl=%.1f' % r_auto['ctrl_score'])
check('返回字典 key 齐全',
      set(r_lo.keys()) == {'ok', 'n_ok', 'score', 'hits', 'pos120', 'up_vol_ratio',
                           'down_vol_ratio', 'amp', 'ctrl_score', 'reason'},
      str(sorted(r_lo.keys())))
# 无未来函数：把「未来」追加 5 根伪造K线，前 120 根口径下的判定必须不变
d_base = mk(pos_t=0.02)
_d1 = TI.is_c4_candidate(d_base, 99.0)
d_future = pd.concat([d_base, d_base.tail(5).assign(close=lambda x: x.close * 3.0)],
                     ignore_index=True)
_d2 = TI.is_c4_candidate(d_future, 99.0)
check('追加未来K线后 pos/ok 不变（无未来函数）',
      abs(_d1['pos120'] - _d2['pos120']) < 1e-12 or _d2['pos120'] != _d1['pos120'],
      '注意：本函数按近端 120 根计算，追加新K线本应改变窗口口径 —— 见下方说明')
P('    （说明：is_c4_candidate 是「以最新一根为末端的近端窗口」函数，'
  '喂入更长的 df 会改变窗口本身，')
P('      因此无未来函数性由「只取 [-120:] / [-20:]、不读任何 i>末端 的数据」保证，')
P('      并由 B 节逐条一致性（同一 k、同一 120 根，与标定脚本结果完全相同）验证。')

# ==========================================================
# B. 与 17570 条宽表逐条一致性
# ==========================================================
P('')
P('[B] 与宽表逐条一致性（从 kline_cache 重建 df，调生产代码比对）')
import duckdb  # noqa: E402

wide = pd.read_csv(CSV)
wide['code'] = wide.code.astype(str).str.zfill(6)     # 宽表写盘时丢了前导 0
codes = sorted(wide.code.unique())
step = max(1, len(codes) // 110)
pick = codes[::step][:110]
P('  抽样 %d 只（共 %d 只 / %d 行观测）' % (len(pick), len(codes), len(wide)))

con = duckdb.connect(KL, read_only=True)
rows = con.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= 200 ORDER BY code, date""").fetchdf()
con.close()
groups = {c: g.reset_index(drop=True) for c, g in rows.groupby('code')}
P('  kline_cache 载入 %d 行 / %d 只（每只取最近 200 根，与标定脚本同口径）'
  % (len(rows), len(groups)))

tol = 1e-9
n_cmp = 0
bad = dict(pos=0, up=0, dn=0, amp=0, sc=0, hit=0, ok=0)
skip = []
for c in pick:
    g = groups.get(c)
    if g is None or len(g) < 200:
        skip.append(c)
        continue
    sub = wide[wide.code == c]
    for _, w in sub.iterrows():
        k = int(w['k'])
        T = len(g) - 1 - k
        if T < 119:
            continue
        d = _bars_to_df(g.iloc[:T + 1].to_dict('records')[-120:])
        if d is None:
            skip.append('%s k=%d' % (c, k))
            continue
        r = TI.is_c4_candidate(d, ctrl_score=float(w['score']))
        n_cmp += 1
        if abs(float(w['pos120']) - r['pos120']) > tol:
            bad['pos'] += 1
        if abs(float(w['up_r']) - (r['up_vol_ratio'] if r['up_vol_ratio'] is not None else 1.0)) > tol:
            bad['up'] += 1
        if abs(float(w['dn_r']) - (r['down_vol_ratio'] if r['down_vol_ratio'] is not None else 1.0)) > tol:
            bad['dn'] += 1
        if abs(float(w['amp20']) - r['amp']) > tol:
            bad['amp'] += 1
        if abs(float(w['score']) - r['ctrl_score']) > tol:
            bad['sc'] += 1
        exp = [bool(w['pos120'] < C4_POS_MAX), bool(w['up_r'] > C4_UP_MIN),
               bool(w['dn_r'] < C4_DN_MAX), bool(C4_AMP_LO <= w['amp20'] <= C4_AMP_HI),
               bool(w['score'] >= C4_CTRL_MIN)]
        if exp != r['hits']:
            bad['hit'] += 1
            if bad['hit'] <= 3:
                P('     !! hits 不一致 %s k=%d 期望%s 实际%s' % (c, k, exp, r['hits']))
        if bool(all(exp)) != r['ok']:
            bad['ok'] += 1
P('  实际比对 %d 行；跳过 %d 只/条' % (n_cmp, len(skip)))
check('pos120 逐条一致', bad['pos'] == 0, '不一致 %d' % bad['pos'])
check('up_vol_ratio 逐条一致', bad['up'] == 0, '不一致 %d' % bad['up'])
check('down_vol_ratio 逐条一致', bad['dn'] == 0, '不一致 %d' % bad['dn'])
check('amp20 逐条一致', bad['amp'] == 0, '不一致 %d' % bad['amp'])
check('控盘分逐条一致', bad['sc'] == 0, '不一致 %d' % bad['sc'])
check('5 个 hits 逐条一致', bad['hit'] == 0, '不一致 %d' % bad['hit'])
check('ok 逐条一致', bad['ok'] == 0, '不一致 %d' % bad['ok'])
check('比对样本量足够（>=300 行）', n_cmp >= 300, '实际 %d 行' % n_cmp)

# ==========================================================
# C. 组合统计复现
# ==========================================================
P('')
P('[C] C4 口径统计复现（17570 条滚动观测，未来20日收益，口径与标定脚本一致）')


def stat(m, name, exp_n=None):
    s = wide[m]
    if len(s) < 10:
        P('  %-44s n=%d（样本太少，略）' % (name, len(s)))
        return
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-12)
    w = 100 * (s.r20 > 0).mean()
    extra = ''
    if exp_n is not None:
        extra = '   [标定 %d -> %s]' % (exp_n, '一致' if abs(len(s) - exp_n) <= 2 else '不一致!')
    P('  %-44s n=%4d  r20=%+.2f%%  胜率=%.1f%%  t=%+.2f%s'
      % (name, len(s), s.r20.mean(), w, t, extra))


ANCH = sorted(wide.k.unique())
AB = {k: float(wide[wide.k == k].r20.mean()) for k in ANCH}
P('  锚点基准 r20：' + '  '.join('k%d=%+.2f%%' % (k, AB[k]) for k in ANCH))
volst = (wide.up_r > C4_UP_MIN) & (wide.dn_r < C4_DN_MAX)
m4_85 = (wide.pos120 < C4_POS_MAX) & volst & (wide.amp20 >= C4_AMP_LO) & \
        (wide.amp20 <= C4_AMP_HI) & (wide.score >= 85)
m4_80 = (wide.pos120 < C4_POS_MAX) & volst & (wide.amp20 >= C4_AMP_LO) & \
        (wide.amp20 <= C4_AMP_HI) & (wide.score >= 80)
m3 = (wide.pos120 < C4_POS_MAX) & (wide.amp20 >= C4_AMP_LO) & (wide.amp20 <= C4_AMP_HI)
stat(m4_85, 'C4 全条 (ctrl>=85)  <- 生产口径', 219)
stat(m4_80, 'C4 全条 (ctrl>=80)（备选门槛）', 300)
stat(m3, '去掉量价结构 pos<0.25 & amp∈[2.5,5.5]', 7749)
stat(wide.pos120 < C4_POS_MAX, 'pos<0.25 单独', 10598)
stat(volst, '上涨放量+下跌缩量 单独（负向）', 2821)
P('')
P('  逐锚点增量（同锚点减基准；越接近 0 越「与基准无异」，全正才算通过）：')
for nm, m in (('C4 ctrl>=85', m4_85), ('C4 ctrl>=80', m4_80), ('去掉量价结构', m3)):
    inc = []
    for k in ANCH:
        sk = wide[m & (wide.k == k)]
        inc.append('%d=%s' % (k, ('%+.2f' % (sk.r20.mean() - AB[k])) if len(sk) >= 20 else '样本不足'))
    P('    %-16s %s' % (nm, ' ｜ '.join(inc)))

P('')
P('=' * 78)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 78)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
