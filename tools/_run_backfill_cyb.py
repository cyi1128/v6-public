# -*- coding: utf-8 -*-
"""
备份 picks_tracking.duckdb -> 跑 --backfill（现在含创业板）-> 输出前后对比。

先备份再跑；backfill_history 是纯 INSERT + 跳过已存在 (日期,代码)，不删不改老数据。
"""
import io
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

DB = os.path.join(ROOT, "data", "cache", "picks_tracking.duckdb")
BAK = DB + ".bak_before_cyb_backfill"


def board_of(code):
    c = str(code)
    if c.startswith(("60", "00")):
        return "主板"
    if c.startswith(("300", "301")):
        return "创业板"
    if c.startswith(("688", "689")):
        return "科创板"
    return "其它"


def snap(tag):
    con = duckdb.connect(DB, read_only=True)
    rows = con.execute("SELECT trade_date, code, base_price, pct0, board FROM picks_tracking").fetchall()
    d0 = con.execute("SELECT MIN(trade_date), MAX(trade_date) FROM picks_tracking").fetchone()
    con.close()
    stat = {}
    for r in rows:
        stat[board_of(r[1])] = stat.get(board_of(r[1]), 0) + 1
    print("  [%s] 总 %d 行 ｜ 日期 %s ~ %s" % (tag, len(rows), d0[0], d0[1]))
    for k in ("主板", "创业板", "科创板", "其它"):
        if stat.get(k):
            print("      %-4s %5d" % (k, stat[k]))
    return len(rows), stat


print("=" * 78)
print("一、改前快照")
print("=" * 78)
before_n, before_stat = snap("改前")

print()
print("=" * 78)
print("二、备份 picks_tracking.duckdb")
print("=" * 78)
if not os.path.exists(BAK):
    shutil.copy2(DB, BAK)
    print("  已备份 -> %s（%.2f MB）" % (os.path.basename(BAK), os.path.getsize(BAK) / 1024 / 1024))
else:
    print("  备份已存在，不覆盖 -> %s" % os.path.basename(BAK))

print()
print("=" * 78)
print("三、跑 --backfill（BACKFILL_DAYS=70，取数 SWL 已含 30%）")
print("=" * 78)
t0 = datetime.now()
try:
    from services.picks_tracking_service import backfill_history, fetch_tracking, summarize
    res = backfill_history(70)
    print("  返回：%s" % res)
except Exception as e:
    import traceback
    traceback.print_exc()
    res = {"error": str(e)}
print("  耗时 %.1f 秒" % (datetime.now() - t0).total_seconds())

print()
print("=" * 78)
print("四、改后快照 + 增量")
print("=" * 78)
after_n, after_stat = snap("改后")
print()
print("  增量：总 %+d 行" % (after_n - before_n))
for k in ("主板", "创业板", "科创板", "其它"):
    b = before_stat.get(k, 0)
    a = after_stat.get(k, 0)
    if a or b:
        print("      %-4s %5d -> %5d  (%+d)" % (k, b, a, a - b))

print()
print("=" * 78)
print("五、5日/30日/累计胜率（用户最关心的那三行）")
print("=" * 78)
try:
    s = summarize(fetch_tracking())
    print("  样本 %d 只" % s["total"])
    for k, lbl in (("r5", "5日"), ("r30", "30日"), ("cum", "累计")):
        v = s[k]
        print("    %-4s 样本 %4d  胜率 %5s%%  均值 %6s%%  最好 %7s%%  最差 %7s%%"
              % (lbl, v["n"], v["win"], v["avg"], v["max"], v["min"]))
except Exception as e:
    print("  统计失败：%s: %s" % (type(e).__name__, e))

print()
print("回退命令：copy /Y \"data\\cache\\picks_tracking.duckdb.bak_before_cyb_backfill\" \"data\\cache\\picks_tracking.duckdb\"")
