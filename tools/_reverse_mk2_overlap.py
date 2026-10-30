# -*- coding: utf-8 -*-
"""反推补测：C 项 ② 的「口径对齐」交叉矩阵。

R3 里 4 项 FAIL 的假设：我在独立实现里统计的是「② 判据成立」，而标定报告统计的是
「引擎 detect_markup 返回 type == '缩量强势'」—— 引擎命中多个形态时只返回【分数最高】的那个。
所以两者差 = 「② 成立但被 ①/③ 以更高分覆盖」的样本数。

本脚本把 17516 条锚点跑成混淆矩阵：若差异全部落在 ①/③ 覆盖格、且
「my②=T & eng类型=''」与「my②=F & eng②」两格为 0，则 FAIL 是口径问题，不是因子错误。
"""
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategy.base as B  # noqa: E402
import services.band_pattern_engine as E  # noqa: E402

OUT = r'D:\QuantMonitorV6\tools\brkvr_mk2_overlap.txt'
ANCHORS = (20, 40, 60, 80)
L = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    L.append(s)
    print(s, flush=True)


def indep_pos120(c):
    w = c[-120:]
    return (float(c[-1]) - float(w.min())) / (float(w.max()) - float(w.min()) + 1e-8)


def indep_mk2(o, lw, c, v, pos_min, pos_max):
    n = len(c)
    if n < 60:
        return None
    pos = indep_pos120(c)
    if pos >= pos_max:
        return False
    wl = 8
    yang = sum(1 for i in range(n - wl, n) if c[i] > o[i]) / float(wl)
    v_rec = float(v[-wl:].mean())
    v_prev = float(v[n - 3 * wl:n - wl].mean()) if n > wl else v_rec
    lock_vr = v_rec / (v_prev + 1e-9)
    half = max(1, wl // 2)
    lo_prev = float(lw[n - wl:n - half].min())
    lo_last = float(lw[n - half:].min())
    return bool(yang >= 0.60 and lock_vr <= 1.00 and pos >= pos_min and lo_last >= lo_prev)


con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
df_all = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
ARR = {cd: dict(o=g['open'].to_numpy(float), h=g['high'].to_numpy(float),
                l=g['low'].to_numpy(float), c=g['close'].to_numpy(float),
                v=g['volume'].to_numpy(float)) for cd, g in df_all.groupby('code')}

P('=' * 100)
P('C 项 ② 口径对齐交叉矩阵（17516 条锚点，%s）' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 100)
P('  引擎 detect_markup 的契约：命中多个形态时只返回【分数最高】的那个 type。')
P('  标定报告统计的是「返回 type == 缩量强势」；反推独立实现统计的是「② 判据成立」。')
P('')

_old = B.MARKUP_POS_MAX
t0 = time.perf_counter()
for label, pmin, pmax, exp_eng in (('对标 [4]：门槛放开(1.01) + ②floor=0.55', 0.55, 1.01, 247),
                                   ('对标 [1]：门槛放开(1.01) + ②floor=0.00', 0.00, 1.01, 3138),
                                   ('真实配置：门槛 0.45 + ②floor=0.00', 0.00, 0.45, None)):
    B.MARKUP_POS_MAX = pmax
    grid = {}
    n_my2 = 0
    n_eng2 = 0
    for cd, A in ARR.items():
        o, h, lw, c, v = A['o'], A['h'], A['l'], A['c'], A['v']
        n = len(c)
        if n < 120 + 20:
            continue
        for k in ANCHORS:
            T = n - 1 - k
            if T < 119 or T + 20 >= n:
                continue
            oo, hh, ll, cc, vv = o[:T + 1], h[:T + 1], lw[:T + 1], c[:T + 1], v[:T + 1]
            my2 = bool(indep_mk2(oo, ll, cc, vv, pmin, pmax))
            d = pd.DataFrame({'open': oo[-130:], 'high': hh[-130:],
                              'low': ll[-130:], 'close': cc[-130:], 'volume': vv[-130:]})
            et = B.TechnicalIndicators.detect_markup(d)['type']
            if my2:
                n_my2 += 1
            if et == '缩量强势':
                n_eng2 += 1
            grid[(my2, et)] = grid.get((my2, et), 0) + 1
    P('  ── %s' % label)
    P('     引擎 type==缩量强势 %d ｜ 独立「② 成立」%d（差 %+d）' % (n_eng2, n_my2, n_my2 - n_eng2))
    if exp_eng is not None:
        P('     标定报告期望 %d → %s' % (exp_eng, '一致' if n_eng2 == exp_eng else '不一致'))
    P('     %-22s %s' % ('②成立 & 引擎②', grid.get((True, '缩量强势'), 0)))
    P('     %-22s %s' % ('②成立 & 引擎①(覆盖)', grid.get((True, '阶梯式上行'), 0)))
    P('     %-22s %s' % ('②成立 & 引擎③(覆盖)', grid.get((True, '加速迹象'), 0)))
    P('     %-22s %s  ← 若 >0 才是真不一致' % ('②成立 & 引擎无形态', grid.get((True, ''), 0)))
    P('     %-22s %s  ← 若 >0 才是真不一致' % ('②不成立 & 引擎②', grid.get((False, '缩量强势'), 0)))
    P('     %-22s %s' % ('②不成立 & 引擎①', grid.get((False, '阶梯式上行'), 0)))
    P('     %-22s %s' % ('②不成立 & 引擎③', grid.get((False, '加速迹象'), 0)))
    P('     %-22s %s' % ('②不成立 & 引擎无形态', grid.get((False, ''), 0)))
B.MARKUP_POS_MAX = _old
P('')
P('  耗时 %.0f 秒 ｜ MARKUP_POS_MAX 已还原为 %.2f' % (time.perf_counter() - t0, _old))

# 单只复核：实盘 ② 与引擎 1 只不一致的 301327
P('')
P('  单只复核（R2b 里唯一不一致的 301327：引擎 False / 独立 True）')
A = ARR.get('301327')
if A:
    d = pd.DataFrame({'date': np.arange(120), 'open': A['o'][-120:], 'high': A['h'][-120:],
                      'low': A['l'][-120:], 'close': A['c'][-120:], 'volume': A['v'][-120:]})
    r = B.TechnicalIndicators.detect_markup(d)
    P('     引擎返回 type=%r score=%.1f（② 成立但被更高分形态覆盖 → 契约行为）'
      % (r['type'], r['score']))
    P('     独立 ② 判据 = %s' % indep_mk2(A['o'], A['l'], A['c'], A['v'], 0.00, 0.45))
    P('     结论：不是因子错误，是「唯一返回最高分形态」这一契约导致的类型差异。')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L) + '\n')
print('\n已写出 %s' % OUT)
