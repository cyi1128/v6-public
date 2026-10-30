# -*- coding: utf-8 -*-
"""C4 单只耗时微基准（只读，不改代码）。输出 tools\\c4_perf.txt"""
import sys
import time

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from services.band_pattern_engine import _bars_to_df  # noqa: E402
from strategy.base import TechnicalIndicators as TI  # noqa: E402

dk = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = dk.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= 200 ORDER BY code, date""").fetchdf()
dk.close()
g = {c: v.reset_index(drop=True) for c, v in rows.groupby('code')}
codes = sorted(g)[:800]
print('样本 %d 只（每只最近 200 根）' % len(codes))
dfs = [_bars_to_df(g[c].to_dict('records')[-200:]) for c in codes]
ctrls = [TI.estimate_control_score(d) for d in dfs]

t0 = time.time()
for d, c in zip(dfs, ctrls):
    TI.is_c4_candidate(d, ctrl_score=c)
e1 = time.time() - t0

t0 = time.time()
for d in dfs:
    TI.estimate_control_score(d)
e2 = time.time() - t0

t0 = time.time()
for d in dfs:
    TI.bottom_volume_stack(d)
    TI.red_fat_green_thin(d)
e3 = time.time() - t0

txt = ('每只耗时（%d 只）：\n'
       '  is_c4_candidate      %8.3f ms/只  (合计 %.2f s)\n'
       '  estimate_control_score %8.3f ms/只  (C4 复用它传入，不再重算)\n'
       '  堆量+红肥绿瘦        %8.3f ms/只\n'
       '按全市场 5223 只外推：C4 增加约 %.1f 秒\n'
       % (len(codes), e1 / len(dfs) * 1000, e1, e2 / len(dfs) * 1000,
          e3 / len(dfs) * 1000, e1 / len(dfs) * 5223))
print(txt)
open(r'D:\QuantMonitorV6\tools\c4_perf.txt', 'w', encoding='utf-8').write(txt)
