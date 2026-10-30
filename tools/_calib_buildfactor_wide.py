# -*- coding: utf-8 -*-
"""V20 建仓因子 · 参数扫描宽表标定（B 深挖，第一步）

口径与 tools/_calib_buildfactor.py **完全一致**，保证可与上一轮 17570 条对齐：
  kline_cache 每只取 200 根；4 个锚点 k=20/40/60/80；T = n-1-k
  每个锚点只喂 **截断到 T 的 120 根**（严格无未来数据）
  r20 = close[T+20]/close[T]-1 ；mdd20 = min(low[T+1..T+20])/close[T]-1

本脚本一次算完所有窗口组合，落一张宽表，后续分析只读 CSV（秒级）：
  堆量：recent ∈ {5,8,10,12,15} × base ∈ {15,20,30}   → 15 组
  红肥绿瘦：window ∈ {10,15,20,30}                      →  4 组
  另存：pos120(close口径，与上轮同) / pos_hl(函数内部 high-low 口径) /
        amp20 / up_r / dn_r（量价配合）/ score（控盘分）

**自校验**：向量化实现在 (10,20) 与 window=20 上必须与生产函数
（strategy.base.TechnicalIndicators）逐条一致，不一致直接报错退出，
避免"扫描算的是一套、引擎跑的是另一套"。
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
W_RECENT = (5, 8, 10, 12, 15)
W_BASE = (15, 20, 30)
W_RED = (10, 15, 20, 30)
CSV = os.path.join(ROOT, 'tools', 'buildfactor_wide.csv')
OUT = os.path.join(ROOT, 'tools', 'buildfactor_wide.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


# ---------- 向量化实现（与生产函数同公式） ----------
def v_stack(vol, w, b):
    """返回 (ratio, cont)。基准窗口 = 紧邻近端 w 日之前的 b 日，与近端不重叠。"""
    base = float(vol[-(w + b):-w].mean())
    rec = float(vol[-w:].mean())
    if base <= 0:
        return 0.0, 0.0
    return rec / (base + 1e-8), float((vol[-w:] > base).sum()) / float(w)


def v_red(closes, vol, w):
    """返回 (ratio, up_days, dn_days, ok)。涨跌按收盘 vs 前收；某侧<3 天则 ok=False。"""
    c = closes[-(w + 1):]
    v = vol[-w:]
    d = np.diff(c)
    up = d > 0
    dn = d < 0
    nu, nd = int(up.sum()), int(dn.sum())
    if nu < 3 or nd < 3:
        return 0.0, nu, nd, 0
    uv, dv = float(v[up].mean()), float(v[dn].mean())
    if dv <= 0:
        return 0.0, nu, nd, 0
    return uv / (dv + 1e-8), nu, nd, 1


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
P('=' * 118)
P('V20 建仓因子 · 参数扫描宽表标定')
P('=' * 118)
P('   kline_cache %d 行 / %d 只 / 载入 %.1fs' % (len(df_all), len(groups), time.time() - t0))
P('   锚点 k=%s ｜ 每只只喂截断到 T 的 120 根 ｜ 堆量 recent=%s x base=%s ｜ 红肥 window=%s'
  % (ANCHORS, W_RECENT, W_BASE, W_RED))

_k = [(w, b) for w in W_RECENT for b in W_BASE]
obs = []
chk_bad = 0
chk_n = 0
for c, g in groups.items():
    n = len(g)
    cl = g['close'].values.astype(float)
    lo_ = g['low'].values.astype(float)
    hi_ = g['high'].values.astype(float)
    vo = g['volume'].values.astype(float)
    op_ = g['open'].values.astype(float)
    for k in ANCHORS:
        T = n - 1 - k
        if T < 60 or T + 20 >= n:
            continue
        # 截断到 T 的 120 根
        s = slice(max(0, T + 1 - 120), T + 1)
        cv, lv, hv, vv, ov = cl[s], lo_[s], hi_[s], vo[s], op_[s]
        if len(cv) < 61:
            continue
        d = _bars_to_df(g.iloc[:T + 1].to_dict('records')[-120:])
        if d is None:
            continue
        base = float(cl[T])
        if base <= 0:
            continue

        # ---- 生产函数（默认参数），用于自校验 + 与上轮对齐 ----
        st = TI.bottom_volume_stack(d)
        rf = TI.red_fat_green_thin(d)
        # ---- 向量化 ----
        r10_20, c10_20 = v_stack(vv, 10, 20)
        rr20, ru20, rd20, rok20 = v_red(cv, vv, 20)
        chk_n += 1
        if abs(r10_20 - st['ratio']) > 1e-9 or abs(c10_20 - st['cont']) > 1e-9:
            chk_bad += 1
            if chk_bad <= 3:
                P('   !! 不一致 %s k=%d: 生产 ratio=%.10f cont=%.10f | 向量 ratio=%.10f cont=%.10f'
                  % (c, k, st['ratio'], st['cont'], r10_20, c10_20))
            continue
        if rf['up_days'] >= 3 and rf['down_days'] >= 3:
            if abs(rr20 - rf['ratio']) > 1e-9:
                chk_bad += 1
                if chk_bad <= 3:
                    P('   !! 红肥不一致 %s k=%d: 生产 %.10f | 向量 %.10f' % (c, k, rf['ratio'], rr20))
                continue

        sc = float(TI().estimate_control_score(d))

        # 位置（两种口径都存）
        t120c = cv[-120:]
        pos_c = (float(cv[-1]) - float(t120c.min())) / (float(t120c.max()) - float(t120c.min()) + 1e-8)
        t120h, t120l = hv[-120:], lv[-120:]
        pos_hl = (float(cv[-1]) - float(t120l.min())) / (float(t120h.max()) - float(t120l.min()) + 1e-8)

        # 振幅 20 日均值
        amp20 = float(np.mean((hv[-20:] - lv[-20:]) / (cv[-20:] + 1e-8)))

        # 量价配合（口径同 estimate_control_score：末 20 根，涨跌按 close vs 前收）
        c20 = cv[-20:]
        v20 = vv[-20:]
        dd = np.diff(c20)          # 19 个涨跌，对应切片第 1..19 根
        v19 = v20[1:]              # 与 dd 对齐的量能
        up20 = dd > 0
        dn20 = dd < 0
        vm = float(v20.mean()) + 1e-8
        up_r = float(v19[up20].mean()) / vm if up20.sum() > 0 else 1.0
        dn_r = float(v19[dn20].mean()) / vm if dn20.sum() > 0 else 1.0

        row = dict(code=c, k=k, score=sc, pos120=pos_c, pos_hl=pos_hl,
                   amp20=amp20, up_r=up_r, dn_r=dn_r,
                   s_ratio=st['ratio'], s_cont=st['cont'], s_score=st['score'],
                   r_ratio=rf['ratio'], r_up=rf['up_days'], r_dn=rf['down_days'],
                   r20=(float(cl[T + 20]) / base - 1.0) * 100.0,
                   mdd20=(float(lo_[T + 1:T + 21].min()) / base - 1.0) * 100.0)
        for w in W_RECENT:
            for b in W_BASE:
                rr, cc = v_stack(vv, w, b)
                row['s%02d_%02d_r' % (w, b)] = rr
                row['s%02d_%02d_c' % (w, b)] = cc
        for w in W_RED:
            rr, nu, nd, ok = v_red(cv, vv, w)
            row['f%02d_r' % w] = rr
            row['f%02d_u' % w] = nu
            row['f%02d_d' % w] = nd
        obs.append(row)

O = pd.DataFrame(obs)
P('   观测 %d 条 / %d 只 / %.1fs' % (len(O), O['code'].nunique(), time.time() - t0))
P('   自校验：比对 %d 条 ｜ 不一致 %d 条  →  %s'
  % (chk_n, chk_bad, 'PASS（向量化与生产函数逐条一致）' if chk_bad == 0 else 'FAIL'))
if chk_bad:
    P('   向量化与生产函数不一致，后续所有扫描结果不可信，已停止。')
    _fh.close()
    sys.exit(2)
P('   全样本 r20 基准 = %+.2f%%  胜率 = %.1f%%  mdd20 = %+.2f%%'
  % (O.r20.mean(), 100 * (O.r20 > 0).mean(), O.mdd20.mean()))
P('   锚点构成: %s' % dict(O.groupby('k').size()))

O.to_csv(CSV, index=False, encoding='utf-8-sig')
P('   宽表已写: tools\\buildfactor_wide.csv  (%d 行 x %d 列)' % (len(O), len(O.columns)))
P('   总用时 %.1fs' % (time.time() - t0))
_fh.close()
print('\n已写:', CSV)
