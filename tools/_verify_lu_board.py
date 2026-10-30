# -*- coding: utf-8 -*-
"""实测：_build_env_context 的涨停家数在板性口径下的真实变化。

用 kline_cache.duckdb 里最新两个交易日，独立重算「旧口径(全 9.5)」
与「新口径(主板9.5/创业板19.5)」，并与引擎实际输出对比。
"""
import io
import os
import sys

sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

from services import band_pattern_engine as E   # noqa: E402

print("=== 1. 阈值函数单测 ===")
for code in ('600000', '000001', '002594', '300001', '301001', '688001', '830799'):
    print("   %s → %s%%" % (code, E._lu_threshold(code)))

print()
print("=== 2. 独立重算（直接读 kline_cache）===")
import duckdb  # noqa: E402
kp = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
con = duckdb.connect(kp, read_only=True)
try:
    ds = [str(r[0])[:10] for r in con.execute(
        'SELECT DISTINCT date FROM kline_cache ORDER BY date DESC LIMIT 2').fetchall()]
    rows = con.execute('SELECT code, date, close FROM kline_cache WHERE date IN (?, ?)',
                       ds).fetchall()
finally:
    con.close()
print("   数据日：%s / %s" % (ds[0], ds[1]))

px = {}
for code, d, c in rows:
    px.setdefault(code, {})[str(d)[:10]] = c
pcts = {}
for code, m in px.items():
    a, b = m.get(ds[0]), m.get(ds[1])
    if a and b and b > 0:
        pcts[code] = (a - b) / b * 100
print("   可比对股票：%d 只" % len(pcts))
cyb = [c for c in pcts if str(c).startswith(('300', '301'))]
print("   其中创业板：%d 只" % len(cyb))

old_lu = sum(1 for x in pcts.values() if x >= 9.5)
new_lu = sum(1 for c, x in pcts.items() if x >= E._lu_threshold(c))
# 旧口径误算的量：涨幅落在 9.5% 和该股真实涨停线之间的（创业板/科创板/北交所都算）
wrong = sum(1 for c, x in pcts.items() if 9.5 <= x < E._lu_threshold(c))
by_board = {}
for c, x in pcts.items():
    if 9.5 <= x < E._lu_threshold(c):
        k = ('创业板' if str(c).startswith(('300', '301'))
             else '科创板' if str(c).startswith(('688', '689'))
             else '北交所' if str(c).startswith(('8', '4', '920')) else '其他')
        by_board[k] = by_board.get(k, 0) + 1
print()
print("   旧口径（全市场统一 9.5%%）：涨停 %d 家" % old_lu)
print("   新口径（主板9.5 / 创业板·科创板19.5 / 北交所29.5）：涨停 %d 家" % new_lu)
print("   差异：%d 家 —— %s" % (old_lu - new_lu, by_board))
print("   校验：误算数 %d == 差异 %d → %s"
      % (wrong, old_lu - new_lu, "一致" if wrong == old_lu - new_lu else "不一致 !!"))
idx = sorted((x, c) for c, x in pcts.items()
             if str(c).startswith(('300', '301')) and 9.5 <= x < 19.5)[-5:]
print("   被纠正的创业板股样例（涨幅从高到低）：")
for x, c in reversed(idx):
    print("      %s  %+.2f%%" % (c, x))

print()
print("=== 3. 引擎实际输出（_build_env_context）===")
ctx = E._build_env_context(verbose=True)
print("   market = %s" % ctx.get('market'))

print()
print("=== 4. 源码断言 ===")
src = io.open(ROOT + r"services\band_pattern_engine.py", encoding="utf-8-sig").read()
print("   已无统一 9.5 判定：", "是" if "x >= 9.5" not in src else "!! 还在")
print("   已无统一跌停 9.5：", "是" if "<= -9.5" not in src else "!! 还在")
print("   用了 _lu_threshold：", src.count("_lu_threshold("))
