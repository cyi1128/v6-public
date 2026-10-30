# -*- coding: utf-8 -*-
"""量一下两个建仓因子（堆量 / 红肥绿瘦）在全市场上的 ok 占比，决定要不要进「观察」列。

理由：如果 ok 率高达八九成，这两个标签等于每行都挂、纯噪音（用户明确反感这种提示）。
只统计，不改任何代码。
"""
import os
import sys
import random
import duckdb

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

from strategy.base import TechnicalIndicators as TI
import services.band_pattern_engine as engine

DB = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'
con = duckdb.connect(DB, read_only=True)
codes = [r[0] for r in con.execute(
    "SELECT code FROM (SELECT code, COUNT(*) n FROM kline_cache "
    "WHERE code LIKE '60%' OR code LIKE '00%' OR code LIKE '30%' "
    "GROUP BY code) t WHERE n >= 120").fetchall()]
con.close()
print('可用代码数（>=120 根）:', len(codes))
random.seed(20261011)
sample = random.sample(codes, min(500, len(codes)))

ti = TI()
n = 0
s_ok = r_ok = 0
s_only = r_only = both = neither = 0
for c in sample:
    bars = engine._load_bars(c)
    if not bars or len(bars) < 60:
        continue
    df = engine._bars_to_df(bars)
    if df is None:
        continue
    st = ti.bottom_volume_stack(df) or {}
    rf = ti.red_fat_green_thin(df) or {}
    n += 1
    s_ok += 1 if st.get('ok') else 0
    r_ok += 1 if rf.get('ok') else 0
    a, b = bool(st.get('ok')), bool(rf.get('ok'))
    both += 1 if (a and b) else 0
    s_only += 1 if (a and not b) else 0
    r_only += 1 if (b and not a) else 0
    neither += 1 if (not a and not b) else 0

print('样本 n = %d' % n)
print('堆量      ok 占比 %.1f%%' % (100.0 * s_ok / max(n, 1)))
print('红肥绿瘦  ok 占比 %.1f%%' % (100.0 * r_ok / max(n, 1)))
print('两者都 ok %.1f%% / 只堆量 %.1f%% / 只红肥 %.1f%% / 都不 ok %.1f%%'
      % (100.0 * both / max(n, 1), 100.0 * s_only / max(n, 1),
         100.0 * r_only / max(n, 1), 100.0 * neither / max(n, 1)))
