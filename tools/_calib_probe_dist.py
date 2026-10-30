# -*- coding: utf-8 -*-
"""试盘识别（detect_probe）/ 出货形态确认（detect_distribution_pattern）的真实数据标定。

口径与 C4/C6 批次一致：kline_cache 近 260 根，锚点 k=20/40/60/80（T = n-1-k），
因子只用 df[:T+1]（严格无未来数据）；未来收益 r20 = (close[T+20]-close[T]) / close[T]。
输出：tools\\probe_dist_calib.txt  +  tools\\probe_dist_calib.csv
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import duckdb  # noqa: E402

from strategy.base import TechnicalIndicators as TI  # noqa: E402
from services.band_pattern_engine import _bars_to_df  # noqa: E402

OUT_TXT = r'D:\QuantMonitorV6\tools\probe_dist_calib.txt'
OUT_CSV = r'D:\QuantMonitorV6\tools\probe_dist_calib.csv'
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
        return dict(n=0, mean=float('nan'), med=float('nan'), win=float('nan'),
                    t=float('nan'), std=float('nan'))
    sd = a.std(ddof=1) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else float('nan')
    return dict(n=n, mean=a.mean() * 100, med=np.median(a) * 100,
                win=(a > 0).mean() * 100, t=(a.mean() / se) if se and se > 0 else float('nan'),
                std=sd * 100)


def fmt(s):
    if s['n'] == 0:
        return 'n=0'
    return ('n=%-6d 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f'
            % (s['n'], s['mean'], s['med'], s['win'], s['t']))


P('=' * 104)
P('试盘识别 / 出货形态确认 标定（kline_cache 真实数据，锚点 k=%s，未来 %d 个交易日）'
  % ('/'.join(str(x) for x in ANCHORS), FWD))
P('=' * 104)

con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
P('')
P('[0] 数据源')
P('  kline_cache 列：%s' % (con.execute('DESCRIBE kline_cache').fetchdf()['column_name'].tolist(),))
rows = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
P('  取出 %d 行 / %d 只（每只最多 260 根）' % (len(rows), rows['code'].nunique()))

codes = sorted(rows['code'].unique())
by_code = {c: g for c, g in rows.groupby('code')}

# ---------- 逐锚点计算 ----------
recs = []
base_all = []
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
        base_all.append(fwd)
        rp = TI.detect_probe(d)
        rd = TI.detect_distribution_pattern(d)
        recs.append(dict(code=cd, k=k, date=str(bars[T]['date'])[:10],
                         close=cl[T], fwd=fwd, mdd=mdd,
                         probe_ok=int(bool(rp['ok'])), probe_stage=rp['stage'],
                         probe_score=rp['score'], probe_n=rp.get('n_ok'),
                         probe_sr=rp.get('shadow_ratio'), probe_vr=rp.get('vol_ratio'),
                         probe_pos=rp.get('pos120'),
                         dist_ok=int(bool(rd['ok'])), dist_type=rd['type'],
                         dist_score=rd['score'], dist_n=rd.get('n_ok'),
                         dist_pos=rd.get('pos120'), dist_vr=rd.get('vol_ratio')))
    if (i + 1) % 1000 == 0:
        print('  ... 已算 %d/%d 只' % (i + 1, len(codes)), flush=True)

S = pd.DataFrame(recs)
P('  观测样本 %d 条（%d 只）' % (len(S), S['code'].nunique()))
base = stat(base_all)
P('')
P('[1] 全样本基准：%s' % fmt(base))

P('')
P('[2] 试盘识别')
hit = S[S['probe_ok'] == 1]
P('  命中 %d / %d（%.2f%%）' % (len(hit), len(S), 100.0 * len(hit) / max(len(S), 1)))
P('  ├ 命中后：%s' % fmt(stat(hit['fwd'])))
P('  └ 未命中后：%s' % fmt(stat(S[S['probe_ok'] == 0]['fwd'])))
P('  按状态：')
for st in ('confirmed', 'pending', ''):
    sub = S[S['probe_stage'] == st]
    P('    stage=%-10s %s' % (st or '(无)', fmt(stat(sub['fwd']))))
P('  按 n_ok（命中条数）分档：')
for kk in (6, 5, 4):
    sub = S[(S['probe_ok'] == 1) & (S['probe_n'] == kk)]
    P('    n_ok=%d  %s' % (kk, fmt(stat(sub['fwd']))))
P('  按 pos120 分档（命中样本）：')
for lo, hi in ((0.0, 0.35), (0.35, 0.55), (0.55, 0.75)):
    sub = hit[(hit['probe_pos'] >= lo) & (hit['probe_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  逐锚点（检验是否只靠某一个锚点）：')
for k in ANCHORS:
    sub = S[(S['k'] == k) & (S['probe_ok'] == 1)]
    base_k = stat([r['fwd'] for r in recs if r['k'] == k])
    st = stat(sub['fwd'])
    inc = (st['mean'] - base_k['mean']) if st['n'] else float('nan')
    P('    k=%-3d 命中 %-4d %s  ｜同锚点基准均%+.2f%%  增量 %+.2fpp'
      % (k, st['n'], fmt(st), base_k['mean'], inc))

P('')
P('[3] 出货形态确认')
hitd = S[S['dist_ok'] == 1]
P('  命中 %d / %d（%.2f%%）' % (len(hitd), len(S), 100.0 * len(hitd) / max(len(S), 1)))
P('  ├ 命中后：%s' % fmt(stat(hitd['fwd'])))
P('  └ 未命中后：%s' % fmt(stat(S[S['dist_ok'] == 0]['fwd'])))
P('  分型：')
for t, g in hitd.groupby('dist_type'):
    P('    %-8s %s  ｜ 未来20日最大回撤 中位 %.2f%%'
      % (t, fmt(stat(g['fwd'])), np.median(g['mdd']) * 100 if len(g) else float('nan')))
P('  按 pos120 分档（命中样本）：')
for lo, hi in ((0.55, 0.75), (0.75, 0.90), (0.90, 1.01)):
    sub = hitd[(hitd['dist_pos'] >= lo) & (hitd['dist_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  按 score 分档（命中样本）：')
for lo, hi in ((70, 80), (80, 90), (90, 101)):
    sub = hitd[(hitd['dist_score'] >= lo) & (hitd['dist_score'] < hi)]
    P('    score∈[%d,%d)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  逐锚点：')
for k in ANCHORS:
    sub = S[(S['k'] == k) & (S['dist_ok'] == 1)]
    base_k = stat([r['fwd'] for r in recs if r['k'] == k])
    st = stat(sub['fwd'])
    inc = (st['mean'] - base_k['mean']) if st['n'] else float('nan')
    P('    k=%-3d 命中 %-4d %s  ｜同锚点基准均%+.2f%%  增量 %+.2fpp'
      % (k, st['n'], fmt(st), base_k['mean'], inc))

P('')
P('[4] 两个因子的联动（试盘命中 + 出货形态命中 互斥性检查）')
both = S[(S['probe_ok'] == 1) & (S['dist_ok'] == 1)]
P('  同时命中：%d 条（%.2f%%）—— 设计上试盘限 pos<=0.75、出货形态要 pos>=0.40/0.55，重叠应很少'
  % (len(both), 100.0 * len(both) / max(len(S), 1)))
P('  同时命中样本后续：%s' % fmt(stat(both['fwd'])))
P('')
P('[5] 抽样明细（命中样本，按分数排序取前 12 / 后 6）')
show = hitd.sort_values('dist_score', ascending=False).head(12)
P('  出货形态：')
P('    %-8s %-6s %-12s %-11s %8s %7s %6s %7s %8s'
  % ('代码', '锚点', '日期', '类型', '控盘位置', '量比', '分数', '20日', '最大回撤'))
for _, r in show.iterrows():
    P('    %-8s k=%-3d %-12s %-11s %8.2f %7.2f %6.1f %+7.2f%% %7.2f%%'
      % (r['code'], r['k'], r['date'], r['dist_type'], r['dist_pos'], r['dist_vr'],
         r['dist_score'], r['fwd'] * 100, r['mdd'] * 100))
showp = hit.sort_values('probe_score', ascending=False).head(12)
P('  试盘识别：')
P('    %-8s %-6s %-12s %-13s %8s %7s %6s %7s %8s'
  % ('代码', '锚点', '日期', '状态', '位置', '量比', '分数', '20日', '最大回撤'))
for _, r in showp.iterrows():
    P('    %-8s k=%-3d %-12s %-13s %8.2f %7.2f %6.1f %+7.2f%% %7.2f%%'
      % (r['code'], r['k'], r['date'], r['probe_stage'] or '-', r['probe_pos'],
         r['probe_vr'], r['probe_score'], r['fwd'] * 100, r['mdd'] * 100))

P('')
P('[6] 性能')
import time  # noqa: E402
_cd = codes[0]
_b = by_code[_cd].to_dict('records')
_d = _bars_to_df(_b[-130:])
t0 = time.perf_counter()
for _ in range(200):
    TI.detect_probe(_d)
t1 = time.perf_counter()
for _ in range(200):
    TI.detect_distribution_pattern(_d)
t2 = time.perf_counter()
P('  detect_probe              ：%.3f ms/只' % ((t1 - t0) / 200 * 1000))
P('  detect_distribution_pattern：%.3f ms/只' % ((t2 - t1) / 200 * 1000))

S.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
with open(OUT_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出\n  %s\n  %s' % (OUT_TXT, OUT_CSV))
