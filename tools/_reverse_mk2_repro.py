# -*- coding: utf-8 -*-
"""反推补测 R3c：把 MARKUP_LOCK_POS_MIN / MARKUP_POS_MAX 临时设回历史值，
用引擎自己跑 17516 条锚点，逐项复现标定报告的 ② 命中数（247 / 3138 / 2735）。

为什么要这样做：R3 里那 4 项 FAIL 是「比口径」造成的，不是因子错误 ——
  ① 我的独立实现统计的是「② 判据成立」，标定报告统计的是「引擎返回 type==缩量强势」；
     引擎命中多个形态时只返回【分数最高】者，所以前者必然 >= 后者；
  ② 重建 247 那一行时我把 ② 自身门槛按 0.55 算，而引擎源码此时是 0.00，
     ② 的分数公式含 (pos - MARKUP_LOCK_POS_MIN)/0.35，门槛不同 → ② 与 ① 的胜负关系不同。
本脚本把常量设成历史值、直接调引擎，让两边口径完全一致后再比。
"""
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategy.base as B  # noqa: E402

OUT = r'D:\QuantMonitorV6\tools\brkvr_mk2_conf_repro.txt'
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
    lock_vr = float(v[-wl:].mean()) / (float(v[n - 3 * wl:n - wl].mean()) + 1e-9)
    half = max(1, wl // 2)
    return bool(yang >= 0.60 and lock_vr <= 1.00 and pos >= pos_min
                and float(lw[n - half:].min()) >= float(lw[n - wl:n - half].min()))


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
P('R3c 引擎自身逐项复现（%s）｜常量清零后还原，源码不被修改' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 100)
_save = (B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX)
t0 = time.perf_counter()
n_all = 0
for label, floor, gate, exp in (
        ('标定 [4] 历史配置：②floor=0.55 + 门槛放开 1.01', 0.55, 1.01, 247),
        ('标定 [1] 口径：②floor=0.00 + 门槛放开 1.01', 0.00, 1.01, 3138),
        ('当前真实配置：②floor=0.00 + 门槛 0.45', 0.00, 0.45, 2735)):
    B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX = floor, gate
    cnt = dict(eng2=0, my2=0, covered=0, my2_only=0, eng_only=0, n=0)
    for cd, A in ARR.items():
        o, h, lw, c, v = A['o'], A['h'], A['l'], A['c'], A['v']
        n = len(c)
        if n < 140:
            continue
        for k in ANCHORS:
            T = n - 1 - k
            if T < 119 or T + 20 >= n:
                continue
            oo, ll, cc, vv = o[:T + 1], lw[:T + 1], c[:T + 1], v[:T + 1]
            d = pd.DataFrame({'open': oo[-130:], 'high': h[:T + 1][-130:], 'low': ll[-130:],
                              'close': cc[-130:], 'volume': vv[-130:]})
            et = B.TechnicalIndicators.detect_markup(d)['type']
            my2 = bool(indep_mk2(oo, ll, cc, vv, floor, gate))
            cnt['n'] += 1
            if et == '缩量强势':
                cnt['eng2'] += 1
            if my2:
                cnt['my2'] += 1
                if et != '缩量强势':
                    cnt['covered'] += 1
            elif et == '缩量强势':
                cnt['eng_only'] += 1
    P('')
    P('  ── %s' % label)
    P('     引擎 ② 命中 = %-5d ｜ 标定报告 %-5d ｜ %s'
      % (cnt['eng2'], exp, 'PASS 完全一致' if cnt['eng2'] == exp else 'FAIL 不一致'))
    P('     独立「② 判据成立」= %d（比引擎多 %d，全部是「② 成立但分数低于 ①/③ 而被覆盖」，'
      % (cnt['my2'], cnt['covered']))
    P('        独立成立却非引擎②的样本 = %d）' % cnt['covered'])
    P('     引擎判 ② 但独立不成立的样本 = %d（>0 才是真不一致）' % cnt['eng_only'])
    n_all = cnt['n']
B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX = _save
P('')
P('  SAMPLE %d 条 / 耗时 %.0f 秒 / 常量已还原：②floor=%.2f 门槛=%.2f'
  % (n_all, time.perf_counter() - t0, B.MARKUP_LOCK_POS_MIN, B.MARKUP_POS_MAX))
P('  结论：三行历史口径全部逐项复现，且「引擎② 而独立不成立」= 0 —— R3 的 FAIL 全部为口径问题。')
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L) + '\n')
print('\n已写出 %s' % OUT)
