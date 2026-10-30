# -*- coding: utf-8 -*-
"""A「破位—收复」/ B「量能分位·缩量上涨」/ C「markup② 锁仓式」标定。

口径与 probe_dist / markup 批次完全一致：kline_cache 近 260 根，
锚点 k=20/40/60/80（T = n-1-k），因子只用 df[:T+1]（严格无未来数据）；
未来收益 r20 = (close[T+20]-close[T]) / close[T]，另算区间最大回撤。

C 项说明：markup 形态②（锁仓式/缩量强势）因 MARKUP_POS_MAX(0.45) < 自身位置下限
MARKUP_LOCK_POS_MIN(0.55) 而不可达，所以本脚本临时把 MARKUP_POS_MAX 放开到 1.01
再单独量 ② 的分布（**只在本进程内改内存，不动源码**）。
A 项同理：临时把 BRK_POS_LOW 放开到 1.01，一次性量出「门槛内」与「门槛外」两段。

输出：tools\\brk_volgem_calib.txt + tools\\brk_volgem_calib.csv
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
OUT_TXT = r'D:\QuantMonitorV6\tools\brk_volgem_calib.txt'
OUT_CSV = r'D:\QuantMonitorV6\tools\brk_volgem_calib.csv'
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
                    t=float('nan'))
    sd = a.std(ddof=1) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else float('nan')
    return dict(n=n, mean=a.mean() * 100, med=np.median(a) * 100,
                win=(a > 0).mean() * 100,
                t=(a.mean() / se) if se and se > 0 else float('nan'))


def fmt(s):
    if s['n'] == 0:
        return 'n=0'
    return ('n=%-6d 均%+6.2f%% 中位%+6.2f%% 胜率%5.1f%% t=%+5.2f'
            % (s['n'], s['mean'], s['med'], s['win'], s['t']))


P('=' * 108)
P('A 破位—收复 / B 量能分位 / C markup② 标定（kline_cache 真实数据，锚点 k=%s，未来 %d 日）'
  % ('/'.join(str(x) for x in ANCHORS), FWD))
P('=' * 108)

con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn"
    " FROM kline_cache) WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
P('')
P('[0] 数据源：%d 行 / %d 只（每只最多 260 根）' % (len(rows), rows['code'].nunique()))

codes = sorted(rows['code'].unique())
by_code = {c: g for c, g in rows.groupby('code')}

# ---- 临时放开两个位置门槛（只改本进程内存，不动源码）----
_SAVE = (B.BRK_POS_LOW, B.MARKUP_POS_MAX)
B.BRK_POS_LOW = 1.01
B.MARKUP_POS_MAX = 1.01
P('   临时放开 BRK_POS_LOW=%s / MARKUP_POS_MAX=%s（源码值 %s / %s，进程内改，盘后复核不变）'
  % (B.BRK_POS_LOW, B.MARKUP_POS_MAX, _SAVE[0], _SAVE[1]))

recs = []
base_all = []
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
        base_all.append(fwd)
        rb = TI.detect_breakdown_recover(d)
        rv = TI.detect_volume_regime(d)
        rm = TI.detect_markup(d)
        recs.append(dict(code=cd, k=k, date=str(bars[T]['date'])[:10], fwd=fwd, mdd=mdd,
                         brk_ok=int(bool(rb['ok'])), brk_type=rb['type'],
                         brk_score=rb['score'], brk_pos=rb.get('pos120'),
                         brk_vr=rb.get('vol_ratio'), brk_rec=int(bool(rb.get('recovered'))),
                         brk_ago=rb.get('detail', {}).get('brk_bars_ago', -1),
                         vr_ok=int(bool(rv['ok'])), vr_tags='|'.join(rv['tags']),
                         vr_pct=rv.get('pct'), vr_su=rv.get('detail', {}).get('su_vol_ratio'),
                         vr_gain=rv.get('detail', {}).get('su_gain'),
                         mk_ok=int(bool(rm['ok'])), mk_type=rm['type'], mk_score=rm['score'],
                         mk_pos=rm.get('pos120'), mk_gain=rm.get('gain')))
    if (i + 1) % 1000 == 0:
        print('  ... 已算 %d/%d 只' % (i + 1, len(codes)), flush=True)
P('   耗时 %.0f 秒' % (time.perf_counter() - t0))

S = pd.DataFrame(recs)
P('   观测样本 %d 条（%d 只）' % (len(S), S['code'].nunique()))
base = stat(base_all)

P('')
P('[1] 全样本基准：%s' % fmt(base))

POSBANDS = ((0.0, 0.45), (0.45, 0.55), (0.55, 0.75), (0.75, 1.01))

P('')
P('[2] A 破位—收复')
P('  破位成立（不限位置）：%d / %d（%.2f%%）'
  % ((S['brk_ok'] == 1).sum(), len(S), 100.0 * (S['brk_ok'] == 1).sum() / len(S)))
for t, g in S[S['brk_ok'] == 1].groupby('brk_type'):
    P('  ├ %-6s %s  ｜ 未来20日最大回撤 中位 %.2f%%'
      % (t, fmt(stat(g['fwd'])), np.median(g['mdd']) * 100 if len(g) else float('nan')))
P('  未命中（无破位 / 破位不成立）：%s' % fmt(stat(S[S['brk_ok'] == 0]['fwd'])))
P('  分位置档（含被门槛拦掉的 >=0.55 段）：')
for t in ('洗盘收复', '破位未收'):
    P('    %s：' % t)
    for lo, hi in POSBANDS:
        sub = S[(S['brk_type'] == t) & (S['brk_pos'] >= lo) & (S['brk_pos'] < hi)]
        P('      pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  逐锚点：')
for k in ANCHORS:
    base_k = stat([r['fwd'] for r in recs if r['k'] == k])
    for t in ('洗盘收复', '破位未收'):
        st = stat(S[(S['k'] == k) & (S['brk_type'] == t)]['fwd'])
        inc = (st['mean'] - base_k['mean']) if st['n'] else float('nan')
        P('    k=%-3d %-6s %s  ｜同锚点基准均%+.2f%%  增量 %+.2fpp'
          % (k, t, fmt(st), base_k['mean'], inc))
P('  按破位日量比分档：')
for lo, hi in ((0.0, 0.8), (0.8, 1.0), (1.0, 1.5), (1.5, 3.0), (3.0, 99)):
    sub = S[(S['brk_vr'] >= lo) & (S['brk_vr'] < hi)]
    P('    vr∈[%.1f,%.1f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))

P('')
P('[3] B 量能分位 / 缩量上涨')
P('  分位可算：%d 条（%.2f%%）' % (S['vr_pct'].notna().sum(),
                               100.0 * S['vr_pct'].notna().sum() / len(S)))
for t in ('地量', '天量', '缩量上涨'):
    sub = S[S['vr_tags'].str.contains(t)]
    P('  ├ %-5s 命中 %-5d %s' % (t, len(sub), fmt(stat(sub['fwd']))))
sub = S[S['vr_tags'] == '']
P('  └ 无标签  命中 %-5d %s' % (len(sub), fmt(stat(sub['fwd']))))
P('  按 pct 分档：')
for lo, hi in ((0, 20), (20, 40), (40, 60), (60, 80), (80, 101)):
    sub = S[(S['vr_pct'] >= lo) & (S['vr_pct'] < hi)]
    P('    pct∈[%d,%d)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  地量 × 位置（地量只有配低位才可能是「地量见地价」）：')
for lo, hi in POSBANDS:
    sub = S[(S['vr_tags'].str.contains('地量')) & (S['vr_pct'].notna())
            & (S['brk_pos'] >= lo) & (S['brk_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  缩量上涨 × 位置：')
for lo, hi in POSBANDS:
    sub = S[(S['vr_tags'].str.contains('缩量上涨')) & (S['brk_pos'] >= lo) & (S['brk_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  天量 × 位置（天量在高位才是顶）：')
for lo, hi in POSBANDS:
    sub = S[(S['vr_tags'].str.contains('天量')) & (S['brk_pos'] >= lo) & (S['brk_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))

P('')
P('[4] C markup 形态②（锁仓式/缩量强势）放开位置门槛后单独量')
P('  说明：源码 MARKUP_POS_MAX=0.45 把 ② 完全覆盖（② 自身要求 pos>=0.55），故常态 0 命中。')
m2 = S[S['mk_type'] == '缩量强势']
P('  ② 命中 %d / %d（%.2f%%）  %s'
  % (len(m2), len(S), 100.0 * len(m2) / len(S), fmt(stat(m2['fwd']))))
P('  按位置分档：')
for lo, hi in POSBANDS:
    sub = m2[(m2['mk_pos'] >= lo) & (m2['mk_pos'] < hi)]
    P('    pos∈[%.2f,%.2f)  %s' % (lo, hi, fmt(stat(sub['fwd']))))
P('  对照：① 阶梯式 / ③ 加速迹象（同一进程内仍是放开位置门槛后的口径）')
for t in ('阶梯式上行', '加速迹象'):
    sub = S[S['mk_type'] == t]
    P('    %-6s 命中 %-5d %s' % (t, len(sub), fmt(stat(sub['fwd']))))
P('  ② 与 A/B 的重叠：')
for nm, cond in (('A 洗盘收复', S['brk_type'] == '洗盘收复'),
                 ('A 破位未收', S['brk_type'] == '破位未收'),
                 ('B 天量', S['vr_tags'].str.contains('天量')),
                 ('B 缩量上涨', S['vr_tags'].str.contains('缩量上涨'))):
    P('    %-10s ∩ ② = %d 条' % (nm, int((cond & (S['mk_type'] == '缩量强势')).sum())))
P('  ② 命中样本数按 pos 最小 8 只（看它到底长在什么位置）：')
show = m2.sort_values('mk_pos').head(8)
P('    %-8s %-6s %-12s %8s %8s %7s %7s' % ('代码', '锚点', '日期', '位置', '分数', '20日', '最大回撤'))
for _, r in show.iterrows():
    P('    %-8s k=%-3d %-12s %8.3f %8.1f %+7.2f%% %7.2f%%'
      % (r['code'], r['k'], r['date'], r['mk_pos'], r['mk_score'], r['fwd'] * 100, r['mdd'] * 100))

P('')
P('[5] 抽样明细（判据可复核用）')
show = S[S['brk_ok'] == 1].sort_values('brk_score', ascending=False).head(10)
P('  A 破位—收复（分高前 10）：')
P('    %-8s %-6s %-12s %-6s %8s %7s %7s %7s' % ('代码', '锚点', '日期', '类型', '位置', '破位量比', '分数', '20日'))
for _, r in show.iterrows():
    P('    %-8s k=%-3d %-12s %-6s %8.3f %7.2f %7.1f %+6.2f%%'
      % (r['code'], r['k'], r['date'], r['brk_type'], r['brk_pos'], r['brk_vr'], r['brk_score'], r['fwd'] * 100))
show = S[S['vr_tags'].str.contains('缩量上涨')].head(8)
P('  B 缩量上涨（前 8）：')
P('    %-8s %-6s %-12s %8s %8s %8s %7s' % ('代码', '锚点', '日期', '量分位', '阳量比', '累计涨幅', '20日'))
for _, r in show.iterrows():
    P('    %-8s k=%-3d %-12s %8.1f %8.2f %8.2f%% %+6.2f%%'
      % (r['code'], r['k'], r['date'], r['vr_pct'], r['vr_su'], (r['vr_gain'] or 0) * 100, r['fwd'] * 100))

P('')
P('[6] 性能')
_cd = codes[0]
_d = _bars_to_df(by_code[_cd].to_dict('records')[-130:])
t0 = time.perf_counter()
for _ in range(200):
    TI.detect_breakdown_recover(_d)
t1 = time.perf_counter()
for _ in range(200):
    TI.detect_volume_regime(_d)
t2 = time.perf_counter()
P('  detect_breakdown_recover：%.3f ms/只' % ((t1 - t0) / 200 * 1000))
P('  detect_volume_regime    ：%.3f ms/只' % ((t2 - t1) / 200 * 1000))

B.BRK_POS_LOW, B.MARKUP_POS_MAX = _SAVE
P('')
P('（进程内已把 BRK_POS_LOW / MARKUP_POS_MAX 还原为 %s / %s）' % _SAVE)

S.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
with open(OUT_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出\n  %s\n  %s' % (OUT_TXT, OUT_CSV))
