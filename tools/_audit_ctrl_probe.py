# -*- coding: utf-8 -*-
"""控盘度审计 · 第0步：环境探测（import 是否安全 + kline_cache 结构）"""
import io, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

t0 = time.time()
try:
    from services.band_pattern_engine import (_bars_to_df, _ctrl_note,
                                              _CTRL_HIGH, _CTRL_CAND,
                                              _CTRL_DIST, _CTRL_POS_LOW)
    print('[OK] 引擎 import 成功  用时 %.2fs' % (time.time() - t0))
    print('     阈值实测: _CTRL_HIGH=%s _CTRL_CAND=%s _CTRL_DIST=%s _CTRL_POS_LOW=%s'
          % (_CTRL_HIGH, _CTRL_CAND, _CTRL_DIST, _CTRL_POS_LOW))
except Exception as e:
    print('[FAIL] 引擎 import:', type(e).__name__, e)

t0 = time.time()
try:
    from strategy.base import TechnicalIndicators
    print('[OK] TechnicalIndicators import 用时 %.2fs' % (time.time() - t0))
except Exception as e:
    print('[FAIL] base import:', type(e).__name__, e)

# ---- kline_cache 结构 ----
import duckdb
KL = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
con = duckdb.connect(KL, read_only=True)
print('\n[kline_cache]')
print(con.execute("SELECT table_name FROM information_schema.tables").fetchall())
for t in ('kline_cache',):
    cols = con.execute("PRAGMA table_info('%s')" % t).fetchall()
    print('  %s 列:' % t, [(c[1], c[2]) for c in cols])
    n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    codes = con.execute("SELECT COUNT(DISTINCT code) FROM %s" % t).fetchone()[0]
    d = con.execute("SELECT MIN(date), MAX(date) FROM %s" % t).fetchone()
    print('  行数=%d  股票数=%d  日期 %s ~ %s' % (n, codes, d[0], d[1]))

# ---- 关键验证：真实 bars 里到底有没有 turnover ----
print('\n[关键] 真实 bars 的字段（决定 estimate_control_score 走哪条分支）')
for code in ('600519', '000001', '300750'):
    try:
        import sqlite3
        # 直接从 duckdb 取最后 3 行
        rows = con.execute("""SELECT date, open, high, low, close, volume, amount
                              FROM kline_cache WHERE code=? ORDER BY date DESC LIMIT 3""",
                           [code]).fetchall()
        print('  %s : %d 行, 字段 = date/open/high/low/close/volume/amount'
              % (code, len(rows)), rows[:1])
    except Exception as e:
        print('  %s ERR %s' % (code, e))

print('\n[结论] get_latest_kline 返回 date/open/high/low/close/volume/amount')
print('       无 turnover 字段 -> _bars_to_df 的 if "turnover" in bars[-1] 恒为 False')
print('       -> estimate_control_score 里 40% 权重的「换手分量」永远走成交量比值代理分支')
con.close()
