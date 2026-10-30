# -*- coding: utf-8 -*-
"""C 项补充标定：把 markup 形态② 的**自身位置下限**也放开，直接量它在低位的表现。

上一份标定只放开了全局门槛 MARKUP_POS_MAX，② 自身还要求 pos>=0.55，
所以 pos<0.55 那一段是 0 条（分不出「被门槛挡」还是「低位本来就不成立」）。
本脚本把 MARKUP_LOCK_POS_MIN 也临时改成 0.0（仅进程内，不动源码），
再对比 ② 与 B「缩量上涨」的重合度。

输出：tools\\markup2_pos_calib.txt
"""
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import duckdb  # noqa: E402

import strategy.base as B  # noqa: E402
from services.band_pattern_engine import _bars_to_df  # noqa: E402

TI = B.TechnicalIndicators
OUT = r'D:\QuantMonitorV6\tools\markup2_pos_calib.txt'
ANCHORS = (20, 40, 60, 80)
FWD = 20
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


def stat(vals):
    a = np.asarray([x for x in vals if x is not None and np.isfinite(x)], float)
    n = len(a)
    if n == 0:
        return dict(n=0, mean=float('nan'), med=float('nan'), win=float('nan'), t=float('nan'))
    sd = a.std(ddof=1) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else float('nan')
    return dict(n=n, mean=a.mean() * 100, med=np.median(a) * 100,
                win=(a > 0).mean() * 100, t=(a.mean() / se) if se and se > 0 else float('nan'))


def fmt(s):
    if s['n'] == 0:
        return 'n=0'
    return ('n=%-6d 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f'
            % (s['n'], s['mean'], s['med'], s['win'], s['t']))


con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
codes = sorted(rows['code'].unique())
by_code = {c: g for c, g in rows.groupby('code')}

_save = (B.MARKUP_POS_MAX, B.MARKUP_LOCK_POS_MIN)
B.MARKUP_POS_MAX = 1.01          # 放开全局位置门槛
B.MARKUP_LOCK_POS_MIN = 0.0      # 放开 ② 自身位置下限
P('MARKUP_POS_MAX %s->1.01 ｜ MARKUP_LOCK_POS_MIN %s->0.0（仅本进程）' % (_save[0], _save[1]))
P('全样本基准沿上一份标定：均 -0.78%% / 中位 -1.07%% / 胜率 45.2%% / t=-7.79')
P('')

recs = []
t0 = time.perf_counter()
for i, cd in enumerate(codes):
    bars = by_code[cd].to_dict('records')
    n = len(bars)
    if n < 120 + FWD:
        continue
    cl = np.asarray([b['close'] for b in bars], float)
    for k in ANCHORS:
        T = n - 1 - k
        if T < 119 or T + FWD >= n:
            continue
        d = _bars_to_df(bars[:T + 1])[-130:]
        fwd = (cl[T + FWD] - cl[T]) / cl[T]
        seg = cl[T:T + FWD + 1]
        mdd = float(((np.maximum.accumulate(seg) - seg) / np.maximum.accumulate(seg)).max())
        rm = TI.detect_markup(d)
        rv = TI.detect_volume_regime(d)
        recs.append(dict(code=cd, k=k, date=str(bars[T]['date'])[:10], fwd=fwd, mdd=mdd,
                         mk_type=rm['type'], mk_pos=rm.get('pos120'), mk_score=rm['score'],
                         vr_tags='|'.join(rv['tags'])))
    if (i + 1) % 1500 == 0:
        print('  ... %d/%d' % (i + 1, len(codes)), flush=True)
P('观测 %d 条 / 耗时 %.0f 秒' % (len(recs), time.perf_counter() - t0))

S = pd.DataFrame(recs)
P('')
P('[1] 形态② 放开自身位置下限后的分档（② 其余判据一字未动）')
m2 = S[S['mk_type'] == '缩量强势']
P('  ② 命中 %d（%.2f%%）  %s' % (len(m2), 100.0 * len(m2) / len(S), fmt(stat(m2['fwd']))))
for lo, hi in ((0.0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.75), (0.75, 1.01)):
    sub = m2[(m2['mk_pos'] >= lo) & (m2['mk_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('')
P('[2] ② 与 B「缩量上涨」的重合度（低位谁在干活）')
su = S['vr_tags'].str.contains('缩量上涨')
m2m = S['mk_type'] == '缩量强势'
P('  B 缩量上涨命中 %d ｜ ② 命中 %d ｜ 两者同时 %d'
  % (int(su.sum()), int(m2m.sum()), int((su & m2m).sum())))
P('  ② 命中里同时是「缩量上涨」的占：%.1f%%'
  % (100.0 * (su & m2m).sum() / max(int(m2m.sum()), 1)))
P('  ② 命中且 pos<0.45：%d 条' % int((m2m & (m2['mk_pos'] < 0.45)).sum() if len(m2) else 0))
P('')
P('[3] 结论用的三条对照')
P('  全样本基准          ：%s' % '均 -0.78% / 胜率 45.2% / t=-7.79')
P('  B 缩量上涨(全位置)   ：%s' % fmt(stat(S[su]['fwd'])))
P('  B 缩量上涨(pos<0.45)：%s'
  % fmt(stat(S[su & (S['mk_pos'] < 0.45)]['fwd']) if 'mk_pos' in S.columns else []))

B.MARKUP_POS_MAX, B.MARKUP_LOCK_POS_MIN = _save
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
