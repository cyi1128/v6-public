# -*- coding: utf-8 -*-
"""C4 命中样本独立复核：不调用 is_c4_candidate，改用独立的 pandas 写法重算五条，
逐只与库内字段比对。输出 tools\\c4_samples.txt
"""
import sqlite3
import sys
import time

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
DB = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
KL = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'
OUT = r'D:\QuantMonitorV6\tools\c4_samples.txt'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


P('=' * 118)
P('C4 命中样本独立复核（独立写法重算五条，逐只与库内字段比对）   %s'
  % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 118)
con = sqlite3.connect(DB)
recs = con.execute("""
    SELECT code, name, pattern_id, signal_level, c4_ok, c4_score, control_score, note
    FROM pattern_record ORDER BY c4_ok DESC, code""").fetchall()
con.close()
hits = [r for r in recs if r[4] == 1]
P('库内记录 %d 条；c4_ok=1 共 %d 条（全部复核）' % (len(recs), len(hits)))
P('')

dk = duckdb.connect(KL, read_only=True)
rows = dk.execute("""
    SELECT code, date, open, high, low, close, volume
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn
          FROM kline_cache)
    WHERE rn <= 160 ORDER BY code, date""").fetchdf()
dk.close()
groups = {c: g.reset_index(drop=True) for c, g in rows.groupby('code')}

P('%-7s %-7s %-6s %-6s %-6s %-7s %-7s %-6s %-6s %-6s %-6s %-6s  %s'
  % ('代码', '名称', '现价位', '上涨比', '下跌比', '20均振幅', '控盘分', '位置', '上涨', '下跌',
     '振幅', '控盘', '结论'))
P('-' * 118)
bad = 0
for code, name, pid, lvl, c4ok, c4sc, ctrl_db, note in hits:
    g = groups.get(code)
    if g is None:
        P('%-7s %-7s  kline_cache 无数据' % (code, name))
        continue
    c = g['close'].values.astype(float)          # 独立实现：直接用整列 pandas/numpy
    h = g['high'].values.astype(float)
    lo_ = g['low'].values.astype(float)
    v = g['volume'].values.astype(float)
    w120c = pd.Series(c).tail(120)
    pos = (c[-1] - w120c.min()) / (w120c.max() - w120c.min() + 1e-8)
    amp = float(pd.Series((h - lo_) / (c + 1e-8)).tail(20).mean())
    cc = pd.Series(c).tail(20)
    vv = pd.Series(v).tail(20)
    chg = cc.diff()
    up = chg > 0
    dn = chg < 0
    vm = vv.mean() + 1e-8
    up_r = float(vv[up].mean()) / vm if up.sum() else float('nan')
    dn_r = float(vv[dn].mean()) / vm if dn.sum() else float('nan')
    h1 = pos < 0.25
    h2 = up_r > 1.15
    h3 = dn_r < 0.95
    h4 = 0.025 <= amp <= 0.055
    h5 = float(ctrl_db) >= 85.0
    ok = all([h1, h2, h3, h4, h5])
    if not ok:
        bad += 1
    P('%-7s %-7s %6.3f %7.3f %7.3f %8.4f %7.1f %-6s %-6s %-6s %-6s %-6s  %s'
      % (code, (name or '')[:6], pos, up_r, dn_r, amp, float(ctrl_db),
         'O' if h1 else 'X', 'O' if h2 else 'X', 'O' if h3 else 'X',
         'O' if h4 else 'X', 'O' if h5 else 'X',
         '独立复核通过' if ok else '!! 不一致'))
    P('        note: %s' % (note or '').replace('\n', ' / '))

P('')
P('-' * 118)
P('c4_ok=1 共 %d 只，独立复核不一致 %d 只' % (len(hits), bad))
P('c4_ok=1 占比：%d / %d = %.2f%%' % (len(hits), len(recs), 100.0 * len(hits) / max(1, len(recs))))
P('=' * 118)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if bad else 0)
