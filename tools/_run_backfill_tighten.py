# -*- coding: utf-8 -*-
"""
用新门槛（涨幅上限 5.0%）重建可介入历史样本，并对比前后。

- 先备份库
- 只删 base_source='BACKFILL' 的行（REALTIME 的实时记录保留）
- 重跑 backfill_history(70)
- 用程序自身的 fetch_tracking + summarize 统计前后
"""
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

DB = os.path.join(ROOT, "data", "cache", "picks_tracking.duckdb")
BAK = DB + ".bak_before_tighten"


def snap(tag):
    con = duckdb.connect(DB, read_only=True)
    rows = con.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN code LIKE '30%' THEN 1 ELSE 0 END), "
        "MAX(pct0), MIN(pct0) "
        "FROM picks_tracking").fetchone()
    src = dict(con.execute(
        "SELECT base_source, COUNT(*) FROM picks_tracking GROUP BY base_source").fetchall())
    con.close()
    print("  [%s] 总 %s 行 ｜ 创业板 %s ｜ pct0 %.2f ~ %.2f ｜ 来源 %s"
          % (tag, rows[0], rows[1], rows[3] or 0, rows[2] or 0, src))
    return rows[0]


def report(tag):
    from services.picks_tracking_service import fetch_tracking, summarize
    s = summarize(fetch_tracking())
    print("  [%s] 样本 %d" % (tag, s["total"]))
    for k, lbl in (("r5", "5日"), ("r30", "30日"), ("cum", "累计")):
        v = s[k]
        print("      %-4s 样本 %4d  胜率 %5s%%  均值 %6s%%  最好 %7s%%  最差 %7s%%"
              % (lbl, v["n"], v["win"], v["avg"], v["max"], v["min"]))
    return s


print("=" * 100)
print("一、改前")
print("=" * 100)
snap("改前")
before = report("改前")

print()
print("=" * 100)
print("二、备份库 + 只清 BACKFILL 行（实时记录保留）")
print("=" * 100)
if not os.path.exists(BAK):
    shutil.copy2(DB, BAK)
    print("  已备份 -> %s（%.2f MB）" % (os.path.basename(BAK), os.path.getsize(BAK) / 1024 / 1024))
else:
    print("  备份已存在，不覆盖")

con = duckdb.connect(DB)
n_del = con.execute("SELECT COUNT(*) FROM picks_tracking WHERE base_source='BACKFILL'").fetchone()[0]
con.execute("DELETE FROM picks_tracking WHERE base_source='BACKFILL'")
left = con.execute("SELECT COUNT(*) FROM picks_tracking").fetchone()[0]
con.close()
print("  删除 BACKFILL %d 行，剩余 %d 行（实时记录）" % (n_del, left))

print()
print("=" * 100)
print("三、用新门槛重跑回填（PICK_MAX_PCT=5.0）")
print("=" * 100)
t0 = datetime.now()
from services.picks_tracking_service import backfill_history  # noqa: E402
res = backfill_history(70)
print("  返回：%s" % res)
print("  耗时 %.1f 秒" % (datetime.now() - t0).total_seconds())

print()
print("=" * 100)
print("四、改后")
print("=" * 100)
snap("改后")
after = report("改后")

print()
print("=" * 100)
print("五、对比")
print("=" * 100)
print("  %-8s %-22s %-22s" % ("口径", "改前(涨幅<=9%)", "改后(涨幅<=5%)"))
for k, lbl in (("r5", "5日"), ("r30", "30日"), ("cum", "累计")):
    b, a = before[k], after[k]
    print("  %-8s 胜率 %5s%% (n=%4d)     胜率 %5s%% (n=%4d)"
          % (lbl, b["win"], b["n"], a["win"], a["n"]))
    print("  %-8s 均值 %6s%%             均值 %6s%%" % ("", b["avg"], a["avg"]))
print()
print("  扫描脚本对 涨幅<=5%% 的预测：5日 43.1% / 30日 45.7% / 累计 38.0%")
print("  （实际可能偏离：门槛收紧后每个(日期,板块) 的 top5 选出来的人变了，")
print("    不只是原样本的子集）")
print()
print("回退命令：")
print('  copy /Y "data\\cache\\picks_tracking.duckdb.bak_before_tighten" "data\\cache\\picks_tracking.duckdb"')
