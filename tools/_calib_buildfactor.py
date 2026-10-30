# -*- coding: utf-8 -*-
"""V20 建仓因子阈值标定（2026-10-10）

目的：在写死「是否满足」门槛之前，先用真实数据看这两个因子到底能不能分开未来收益。
口径与 tools/_audit_ctrl_reverse.py 完全一致：
  取数 kline_cache 每只 200 根，4 个锚点 k=20/40/60/80，T = n-1-k
  每个锚点只喂 **截断到 T 的 120 根** 给因子函数（严格无未来数据）
  未来收益 r20 = close[T+20]/close[T]-1，mdd20 = min(low[T+1..T+20])/close[T]-1

只统计，不修引擎。
"""
import io
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd
import duckdb

from services.band_pattern_engine import _bars_to_df
from strategy.base import TechnicalIndicators as TI

KL = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
BARS = 200
ANCHORS = (20, 40, 60, 80)
OUT = os.path.join(ROOT, 'tools', 'build_factor_calibration.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


t0 = time.time()
con = duckdb.connect(KL, read_only=True)
df_all = con.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= %d ORDER BY code, date
""" % BARS).df()
con.close()
groups = {c: g.reset_index(drop=True) for c, g in df_all.groupby('code', sort=False)}
P('=' * 108)
P('V20 建仓因子阈值标定（底部堆量 + 红肥绿瘦）')
P('=' * 108)
P('   kline_cache 载入 %d 行 / %d 只 / %.1fs | 锚点 k=%s | 每只只喂截断到 T 的 120 根'
  % (len(df_all), len(groups), time.time() - t0, ANCHORS))


def bars_of(g, T):
    rows = g.iloc[:T + 1]
    rows = rows.iloc[max(0, len(rows) - 120):]
    return rows.to_dict('records')


obs = []
for c, g in groups.items():
    n = len(g)
    for k in ANCHORS:
        T = n - 1 - k
        if T < 60 or T + 20 >= n:
            continue
        d = _bars_to_df(bars_of(g, T))
        if d is None:
            continue
        st = TI.bottom_volume_stack(d)
        rf = TI.red_fat_green_thin(d)
        sc = float(TI().estimate_control_score(d))
        t120 = d['close'].tail(120)
        lo_, hi_ = float(t120.min()), float(t120.max())
        pos = (float(d['close'].iloc[-1]) - lo_) / (hi_ - lo_ + 1e-8)
        cl = g['close'].values
        lows = g['low'].values
        base = float(cl[T])
        if base <= 0:
            continue
        obs.append(dict(
            code=c, k=k, score=sc, pos120=pos,
            s_ok=int(st['ok']), s_score=st['score'], s_ratio=st['ratio'],
            s_pos=st['pos120'], s_cont=st['cont'],
            r_ok=int(rf['ok']), r_score=rf['score'], r_ratio=rf['ratio'],
            r_up=rf['up_days'], r_dn=rf['down_days'],
            r20=(float(cl[T + 20]) / base - 1.0) * 100.0,
            mdd20=(float(lows[T + 1:T + 21].min()) / base - 1.0) * 100.0))
O = pd.DataFrame(obs)
P('   观测 %d 条 / %d 只 / %.1fs' % (len(O), O['code'].nunique(), time.time() - t0))
P('   全样本 r20 基准 = %+.2f%%  胜率 = %.1f%%  mdd20 = %+.2f%%'
  % (O.r20.mean(), 100 * (O.r20 > 0).mean(), O.mdd20.mean()))


def show(nm, mask, note=''):
    s = O[mask]
    if len(s) < 30:
        P('   %-34s n=%5d  (样本太少跳过)' % (nm, len(s)))
        return
    t = s.r20.mean() / (s.r20.std(ddof=1) / np.sqrt(len(s)) + 1e-9)
    P('   %-34s n=%5d 只=%5d | r20=%+6.2f%% 胜率20=%5.1f%% mdd20=%+7.2f%% t=%+5.2f %s'
      % (nm, len(s), s.code.nunique(), s.r20.mean(), 100 * (s.r20 > 0).mean(),
         s.mdd20.mean(), t, note))


# ============================================================
P('\n' + '=' * 108)
P('[1] 底部堆量：分项与总分')
P('=' * 108)
P('\n   1.1 堆量倍数 s_ratio（近10日均量 / 紧邻前20日均量）')
for lo, hi in ((0, 1.0), (1.0, 1.15), (1.15, 1.35), (1.35, 1.6), (1.6, 2.2), (2.2, 3.5), (3.5, 99)):
    show('   ratio[%.2f,%.2f)' % (lo, hi), (O.s_ratio >= lo) & (O.s_ratio < hi))
P('\n   1.2 连续性 s_cont（近10日内量>基准均量的天数占比）')
for lo, hi in ((0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)):
    show('   cont[%.1f,%.1f)' % (lo, hi), (O.s_cont >= lo) & (O.s_cont < hi))
P('\n   1.3 堆量分 s_score')
for lo, hi in ((0, 40), (40, 55), (55, 65), (65, 70), (70, 80), (80, 101)):
    show('   s_score[%d,%d)' % (lo, hi), (O.s_score >= lo) & (O.s_score < hi))
P('\n   1.4 ok 与否（ok = ratio 1.15~3.5 且 pos120<0.45 且 cont>=0.5）')
show('   stack ok', O.s_ok == 1)
show('   stack 不 ok', O.s_ok == 0)
P('\n   1.5 增量价值：在「低位」里再筛堆量（回答「堆量有没有额外信息」）')
show('   pos120<0.45（纯位置）', O.pos120 < 0.45)
show('   pos120<0.45 且 stack ok', (O.pos120 < 0.45) & (O.s_ok == 1))
show('   pos120<0.45 且 stack 不ok', (O.pos120 < 0.45) & (O.s_ok == 0))

# ============================================================
P('\n' + '=' * 108)
P('[2] 红肥绿瘦：分档与总分')
P('=' * 108)
P('\n   2.1 比值 r_ratio（上涨日均量 / 下跌日均量）—— 看方向是否单调')
for lo, hi in ((0, 0.8), (0.8, 1.0), (1.0, 1.15), (1.15, 1.3), (1.3, 1.5), (1.5, 2.0), (2.0, 4.1)):
    show('   ratio[%.2f,%.2f)' % (lo, hi), (O.r_ratio >= lo) & (O.r_ratio < hi))
P('\n   2.2 红肥绿瘦分 r_score')
for lo, hi in ((0, 20), (20, 40), (40, 60), (60, 65), (65, 80), (80, 101)):
    show('   r_score[%d,%d)' % (lo, hi), (O.r_score >= lo) & (O.r_score < hi))
P('\n   2.3 ok 与否（ok = ratio>=1.30 且 上涨日>=3 且 下跌日>=3）')
show('   redfat ok', O.r_ok == 1)
show('   redfat 不 ok', O.r_ok == 0)
P('\n   2.4 方向验证：反向「红瘦绿肥」应该更差')
show('   反向 ratio<0.90（红瘦绿肥）', O.r_ratio < 0.90)

# ============================================================
P('\n' + '=' * 108)
P('[3] 两因子 2x2（回答「要不要两个一起用」）')
P('=' * 108)
show('   两个都不满足', (O.s_ok == 0) & (O.r_ok == 0))
show('   只堆量', (O.s_ok == 1) & (O.r_ok == 0))
show('   只红肥绿瘦', (O.s_ok == 0) & (O.r_ok == 1))
show('   两个都满足', (O.s_ok == 1) & (O.r_ok == 1))

# ============================================================
P('\n' + '=' * 108)
P('[4] 与现有控盘体系叠加（回答「建仓加强」该不该做）')
P('=' * 108)
base_m = (O.score >= 85) & (O.pos120 < 0.25)
show('   基准：score>=85 且 pos<0.25', base_m)
show('   + stack ok', base_m & (O.s_ok == 1))
show('   + redfat ok', base_m & (O.r_ok == 1))
show('   + 两者都 ok', base_m & (O.s_ok == 1) & (O.r_ok == 1))
show('   + 两者都不满足', base_m & (O.s_ok == 0) & (O.r_ok == 0))

# ============================================================
P('\n' + '=' * 108)
P('[5] 相关性（spearman = 秩变换后的 pearson；本机没装 scipy，不引入新依赖）')
P('=' * 108)


def _spear(a, b):
    return pd.Series(a).rank().corr(pd.Series(b).rank())


for nm, col in (('s_ratio', 's_ratio'), ('s_score', 's_score'), ('s_cont', 's_cont'),
                ('r_ratio', 'r_ratio'), ('r_score', 'r_score'),
                ('pos120（越低越好，应负相关）', 'pos120'), ('score', 'score')):
    P('   %-32s rho(r20) = %+.4f' % (nm, _spear(O[col], O.r20)))

# ============================================================
P('\n' + '=' * 108)
P('[6] 当前阈值命中率（如果直接上线会报多少）')
P('=' * 108)
for lo in (60, 65, 70, 75, 80):
    m = O.s_score >= lo
    P('   stack 分 >= %-3d -> 命中 %6d 条（%5.1f%%）' % (lo, int(m.sum()), 100 * m.mean()))
for lo in (55, 60, 65, 70, 75):
    m = O.r_score >= lo
    P('   redfat 分 >= %-3d -> 命中 %6d 条（%5.1f%%）' % (lo, int(m.sum()), 100 * m.mean()))
P('   ok 口径: stack %d 条（%.1f%%）| redfat %d 条（%.1f%%）| 两者 %d 条（%.1f%%）'
  % (int(O.s_ok.sum()), 100 * O.s_ok.mean(), int(O.r_ok.sum()), 100 * O.r_ok.mean(),
     int((O.s_ok & O.r_ok).sum()), 100 * (O.s_ok & O.r_ok).mean()))

O.to_csv(os.path.join(ROOT, 'tools', 'build_factor_calibration.csv'),
         index=False, encoding='utf-8-sig')
P('\nCSV 已写: tools\\build_factor_calibration.csv (%d 行)' % len(O))
P('总用时 %.1fs' % (time.time() - t0))
_fh.close()
