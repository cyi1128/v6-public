# -*- coding: utf-8 -*-
"""控盘度审计 · 第3步：显著性 / 性能 / 边界 / 可复现性"""
import io, os, sys, time, sqlite3, math
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import duckdb

from services.band_pattern_engine import _bars_to_df, _CTRL_HIGH, _CTRL_CAND, _CTRL_DIST
from strategy.base import TechnicalIndicators as TI

OUT = os.path.join(ROOT, 'tools', 'audit_ctrl_stats.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); _fh.write(s + '\n')

CSV = os.path.join(ROOT, 'tools', 'audit_ctrl_reverse.csv')
O = pd.read_csv(CSV)
P('=' * 100)
P('[C] 显著性检验（关键：17570 条观测含重叠窗口，有效独立样本远少于 17570）')
P('=' * 100)
P('观测 %d 条 / %d 只，每只用 4 个锚点 -> 每只股票内部高度相关' % (len(O), O['code'].nunique()))
P('保守做法：把 n 除以 4 当作「有效独立样本」，再算标准误（SE）')
P('')

def cmp(name, m1, m2, col='r20'):
    a = O[m1][col].values; b = O[m2][col].values
    if len(a) < 20 or len(b) < 20:
        P('   %-40s 样本不足' % name); return
    na, nb = len(a) / 4.0, len(b) / 4.0           # 折半保守
    se = math.sqrt(a.var(ddof=1) / na + b.var(ddof=1) / nb)
    d = a.mean() - b.mean()
    t = d / se if se > 0 else 0.0
    P('   %-40s %s: %+6.2f%% vs %+6.2f%%  delta=%+6.2f  t=%+5.2f  %s'
      % (name, col, a.mean(), b.mean(), d, t,
         '显著(|t|>2)' if abs(t) > 2 else '不显著'))

P('--- r20（20日收益）---')
cmp('80-85  vs  85-90', (O.score >= 80) & (O.score < 85), (O.score >= 85) & (O.score < 90))
cmp('80-85  vs  >=90   ', (O.score >= 80) & (O.score < 85), O.score >= 90)
cmp('>=85   vs  <60   ', O.score >= 85, O.score < 60)
cmp('distribute vs unknown', O.stage == 'distribute', O.stage == 'unknown')
cmp('wash   vs  unknown', O.stage == 'wash', O.stage == 'unknown')
cmp('wash   vs  distribute', O.stage == 'wash', O.stage == 'distribute')
cmp('位置<0.4 vs 位置>=0.7', O.pos120 < 0.4, O.pos120 >= 0.7)
cmp('位置<0.4 & score>=85  vs  位置<0.4 全', (O.pos120 < 0.4) & (O.score >= 85), O.pos120 < 0.4)

P('\n--- mdd20（20日最大回撤）---')
cmp('80-85  vs  >=90   ', (O.score >= 80) & (O.score < 85), O.score >= 90, 'mdd20')
cmp('>=85   vs  <60   ', O.score >= 85, O.score < 60, 'mdd20')
cmp('distribute vs unknown', O.stage == 'distribute', O.stage == 'unknown', 'mdd20')

P('\n--- 出货警示的两种口径对比（这是本轮最关键的检验）---')
w_now = (O.stage == 'distribute') & (O.score >= _CTRL_DIST)
w_raw = (O.stage == 'distribute') & (O.score < 60)
cmp('现规则(score>=60) vs 全样本', w_now, pd.Series([True] * len(O)), 'r20')
cmp('被漏掉的(score<60) vs 全样本', w_raw, pd.Series([True] * len(O)), 'r20')
cmp('现规则  vs  被漏掉的那批', w_now, w_raw, 'r20')
cmp('现规则  vs  被漏掉的那批', w_now, w_raw, 'mdd20')
P('   现规则(score>=%.0f)  n=%d | r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%'
  % (_CTRL_DIST, w_now.sum(), O[w_now]['r20'].mean(), 100 * (O[w_now]['r20'] > 0).mean(), O[w_now]['mdd20'].mean()))
P('   被过滤掉的(score<60) n=%d | r20=%+.2f%% 胜率=%.1f%% mdd=%+.2f%%'
  % (w_raw.sum(), O[w_raw]['r20'].mean(), 100 * (O[w_raw]['r20'] > 0).mean(), O[w_raw]['mdd20'].mean()))

# ============================================================
P('\n' + '=' * 100)
P('[D] 性能：算一只要多久（决定全市场扫描会不会变慢）')
P('=' * 100)
KL = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
con = duckdb.connect(KL, read_only=True)
codes = [r[0] for r in con.execute(
    "SELECT code FROM (SELECT code, COUNT(*) c FROM kline_cache GROUP BY code HAVING COUNT(*)>=60) t LIMIT 300").fetchall()]
bars_map = {}
for c in codes:
    rows = con.execute("""SELECT date,open,high,low,close,volume FROM kline_cache
                          WHERE code=? ORDER BY date DESC LIMIT 120""", [c]).fetchall()
    rows = rows[::-1]
    bars_map[c] = [dict(date=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in rows]

t0 = time.time()
n_ok = 0
for c in codes:
    d = _bars_to_df(bars_map[c])
    if d is None:
        continue
    TI().estimate_control_score(d)
    TI().judge_wash_or_distribute(d)
    n_ok += 1
dt = time.time() - t0
P('   300 只（含 DF 构建 + 两个函数）: %.2f s  -> 单只 %.2f ms' % (dt, dt / max(1, n_ok) * 1000))
P('   推算全市场 4400 只: 约 %.1f 秒（纯计算，不含读库）' % (dt / max(1, n_ok) * 4400))
P('   引擎在 scan_stock 里对【每只股票】都算一次（在模式判断之前），与「只有 145 只命中」无关')

# ============================================================
P('\n' + '=' * 100)
P('[E] 边界：K 线不足 60 根的股票（会被整列跳过）')
P('=' * 100)
rows = con.execute("""SELECT CASE WHEN c<30 THEN '1 <30根' WHEN c<60 THEN '2 30~59根'
                    WHEN c<120 THEN '3 60~119根' ELSE '4 >=120根' END b, COUNT(*)
                    FROM (SELECT code, COUNT(*) c FROM kline_cache GROUP BY code) GROUP BY b ORDER BY b""").fetchall()
tot = sum(r[1] for r in rows)
for b, n in rows:
    P('   %-12s %4d 只 (%.1f%%)' % (b, n, 100.0 * n / tot))
P('   -> 不足 60 根的整只股票会被 _bars_to_df 判 None，控盘列显示 "--"，且不报错（静默）')
con.close()

# ============================================================
P('\n' + '=' * 100)
P('[F] 可复现性：库里 145 条的 control_score 能否用现在的代码重算出来')
P('=' * 100)
DB = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')
con2 = sqlite3.connect(DB)
recs = con2.execute("SELECT code, name, pattern_id, base_date, control_score, stage_guess, push_price, push_date FROM pattern_record").fetchall()
con2.close()

con = duckdb.connect(KL, read_only=True)
cache = {}
for c in set(r[0] for r in recs):
    rr = con.execute("""SELECT date,open,high,low,close,volume FROM kline_cache
                        WHERE code=? ORDER BY date DESC LIMIT 120""", [c]).fetchall()[::-1]
    cache[c] = [dict(date=x[0], open=x[1], high=x[2], low=x[3], close=x[4], volume=x[5]) for x in rr]
con.close()

same = diff = nodata = 0
worst = []
for code, name, pid, bd, cs, sg, pp, pd_ in recs:
    d = _bars_to_df(cache.get(code) or [])
    if d is None:
        nodata += 1; continue
    s2 = float(TI().estimate_control_score(d))
    g2 = TI().judge_wash_or_distribute(d)
    if abs(s2 - cs) < 0.01 and g2 == sg:
        same += 1
    else:
        diff += 1
        worst.append((abs(s2 - cs), code, name, cs, s2, sg, g2, pd_))
P('   逐条重算: 完全一致 %d 条 | 不一致 %d 条 | 无K线 %d 条  （共 %d 条）'
  % (same, diff, nodata, len(recs)))
worst.sort(reverse=True)
if worst:
    P('   偏差最大的 10 条（分数/阶段）：')
    for w in worst[:10]:
        P('     %s %-8s 库存=%6.2f %-11s -> 重算=%6.2f %-11s  base=%s'
          % (w[1], w[2], w[3], w[5], w[4], w[6], w[7]))
P('   注：若偏差普遍为 0，说明「库里的两列 = 现在这份代码算的」，可复现；')
P('       若有成片偏差，说明库是旧版代码写的或 K 线已变（后面举例说明）。')

P('\n' + '=' * 100)
P('第3步完成')
_fh.close()
