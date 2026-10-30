# -*- coding: utf-8 -*-
"""拉升阶段识别 detect_markup() 的真实数据标定。

口径与 C4/C6/试盘/出货形态批次一致：kline_cache 近 260 根，锚点 k=20/40/60/80
（T = n-1-k），因子只用 df[:T+1]（严格无未来数据）；
未来收益 r20 = (close[T+20]-close[T]) / close[T]；同时记录 20 日内最大回撤。
输出：tools\\markup_calib.txt + tools\\markup_calib.csv
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import duckdb  # noqa: E402

from strategy.base import TechnicalIndicators as TI  # noqa: E402
from services.band_pattern_engine import _bars_to_df  # noqa: E402

OUT_TXT = r'D:\QuantMonitorV6\tools\markup_calib.txt'
OUT_CSV = r'D:\QuantMonitorV6\tools\markup_calib.csv'
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
                win=(a > 0).mean() * 100,
                t=(a.mean() / se) if se and se > 0 else float('nan'),
                std=sd * 100)


def fmt(s):
    if s['n'] == 0:
        return 'n=0'
    return ('n=%-6d 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f'
            % (s['n'], s['mean'], s['med'], s['win'], s['t']))


P('=' * 104)
P('拉升阶段识别 标定（kline_cache 真实数据，锚点 k=%s，未来 %d 个交易日）'
  % ('/'.join(str(x) for x in ANCHORS), FWD))
P('=' * 104)

con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
P('')
P('[0] 数据源 kline_cache：取出 %d 行 / %d 只（每只最多 260 根）'
  % (len(rows), rows['code'].nunique()))

codes = sorted(rows['code'].unique())
by_code = {c: g for c, g in rows.groupby('code')}

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
        mdd = float(((np.maximum.accumulate(seg) - seg)
                     / np.maximum.accumulate(seg)).max())
        base_all.append(fwd)
        rm = TI.detect_markup(d)
        rp = TI.detect_probe(d)
        rd = TI.detect_distribution_pattern(d)
        recs.append(dict(code=cd, k=k, date=str(bars[T]['date'])[:10],
                         close=cl[T], fwd=fwd, mdd=mdd,
                         m_ok=int(bool(rm['ok'])), m_type=rm['type'],
                         m_score=rm['score'], m_n=rm.get('n_ok'),
                         m_pos=rm.get('pos120'), m_gain=rm.get('gain'),
                         m_vr=rm.get('vol_ratio'),
                         p_ok=int(bool(rp.get('ok'))),
                         d_ok=int(bool(rd.get('ok')))))
    if (i + 1) % 1000 == 0:
        print('  ... 已算 %d/%d 只' % (i + 1, len(codes)), flush=True)

S = pd.DataFrame(recs)
S.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
P('  观测样本 %d 条（%d 只）｜ 明细 CSV -> %s' % (len(S), S['code'].nunique(), OUT_CSV))
base = stat(base_all)
P('')
P('[1] 全样本基准：%s' % fmt(base))

P('')
P('[2] 拉升识别整体')
hit = S[S['m_ok'] == 1]
P('  命中 %d / %d（%.2f%%）' % (len(hit), len(S), 100.0 * len(hit) / max(len(S), 1)))
P('  ├ 命中后：%s' % fmt(stat(hit['fwd'])))
P('  └ 未命中后：%s' % fmt(stat(S[S['m_ok'] == 0]['fwd'])))
P('  分型（命中样本）：')
for t, g in hit.groupby('m_type'):
    P('    %-6s %s  ｜ 20日内最大回撤 中位 %.2f%%'
      % (t, fmt(stat(g['fwd'])), np.median(g['mdd']) * 100 if len(g) else float('nan')))
P('  按 pos120 分档（命中样本）：')
for lo, hi in ((0.0, 0.45), (0.45, 0.60), (0.60, 0.75), (0.75, 1.01)):
    sub = hit[(hit['m_pos'] >= lo) & (hit['m_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  按 score 分档（命中样本）：')
for lo, hi in ((70, 80), (80, 90), (90, 101)):
    sub = hit[(hit['m_score'] >= lo) & (hit['m_score'] < hi)]
    P('    score∈[%d,%d)  %s' % (lo, hi, fmt(stat(sub['fwd']))))

P('')
P('[3] 逐锚点（判断是否只靠某一个锚点 —— 只靠一个锚点就等于没有）')
for k in ANCHORS:
    sub = S[(S['k'] == k) & (S['m_ok'] == 1)]
    base_k = stat([r['fwd'] for r in recs if r['k'] == k])
    st = stat(sub['fwd'])
    inc = (st['mean'] - base_k['mean']) if st['n'] else float('nan')
    P('  k=%-3d 命中 %-4d %s  ｜同锚点基准均%+.2f%%  增量 %+.2fpp'
      % (k, st['n'], fmt(st), base_k['mean'], inc))
P('  分型逐锚点：')
for t in sorted(hit['m_type'].unique()):
    P('    【%s】' % t)
    for k in ANCHORS:
        sub = S[(S['k'] == k) & (S['m_type'] == t)]
        base_k = stat([r['fwd'] for r in recs if r['k'] == k])
        st = stat(sub['fwd'])
        inc = (st['mean'] - base_k['mean']) if st['n'] else float('nan')
        P('      k=%-3d %s  ｜增量 %+.2fpp'
          % (k, fmt(st), inc if st['n'] else float('nan')))

P('')
P('[4] 与试盘 / 出货形态的重叠（互斥性检查）')
both_p = S[(S['m_ok'] == 1) & (S['p_ok'] == 1)]
both_d = S[(S['m_ok'] == 1) & (S['d_ok'] == 1)]
P('  拉升 & 试盘 同时命中：%d 条（%.2f%%）—— 设计上试盘要 pos<=0.35、拉升多在高位，重叠应很少'
  % (len(both_p), 100.0 * len(both_p) / max(len(S), 1)))
P('  拉升 & 出货形态 同时命中：%d 条（%.2f%%）—— 两者都偏高位，重叠可能较多'
  % (len(both_d), 100.0 * len(both_d) / max(len(S), 1)))
P('  拉升 & 出货形态 同时命中的后续表现：%s' % fmt(stat(both_d['fwd'])))

P('')
P('[5] 抽样明细（命中样本按分数排序取前 15）')
show = hit.sort_values('m_score', ascending=False).head(15)
P('    %-8s %-6s %-12s %-7s %8s %8s %7s %7s %8s'
  % ('代码', '锚点', '日期', '类型', '位置', '窗口涨幅', '量能比', '分数', '20日'))
for _, r in show.iterrows():
    P('    %-8s k=%-3d %-12s %-7s %8.3f %7.2f%% %7.2f %7.1f %+7.2f%%'
      % (r['code'], r['k'], r['date'], r['m_type'], r['m_pos'],
         r['m_gain'] * 100, r['m_vr'], r['m_score'], r['fwd'] * 100))

P('')
P('[6] 一句话结论素材（不做主观推荐）')
P('  整体：%s' % fmt(stat(hit['fwd'])))
P('  全样本基准：%s' % fmt(base))
if len(hit):
    P('  整体增量：%+.2fpp ｜ 命中样本 20 日内最大回撤中位 %.2f%% ｜ 全样本 %.2f%%'
      % (stat(hit['fwd'])['mean'] - base['mean'],
         np.median(hit['mdd']) * 100, np.median(S['mdd']) * 100))

import io  # noqa: E402
io.open(OUT_TXT, 'w', encoding='utf-8').write('\n'.join(_lines) + '\n')
print('已写出', OUT_TXT)
