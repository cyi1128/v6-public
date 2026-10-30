# -*- coding: utf-8 -*-
"""核对收紧后的库内实际状态。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import duckdb  # noqa: E402

DB = r"D:\QuantMonitorV6\data\cache\picks_tracking.duckdb"
con = duckdb.connect(DB, read_only=True)

print("BACKFILL pct0 范围 (min, max, n):",
      con.execute("SELECT MIN(pct0), MAX(pct0), COUNT(*) FROM picks_tracking "
                  "WHERE base_source='BACKFILL'").fetchone())
print("REALTIME pct0 范围 (min, max, n):",
      con.execute("SELECT MIN(pct0), MAX(pct0), COUNT(*) FROM picks_tracking "
                  "WHERE base_source='REALTIME'").fetchone())
print("日期范围:",
      con.execute("SELECT MIN(trade_date), MAX(trade_date) FROM picks_tracking").fetchone())

n_over = con.execute(
    "SELECT COUNT(*) FROM picks_tracking "
    "WHERE base_source='BACKFILL' AND pct0 >= 5.0").fetchone()[0]
print("超 5.0%% 的 BACKFILL 行数（应为 0）:", n_over)

cy = con.execute("SELECT COUNT(*) FROM picks_tracking "
                 "WHERE base_source='BACKFILL' AND code LIKE '30%'").fetchone()[0]
mb = con.execute("SELECT COUNT(*) FROM picks_tracking "
                 "WHERE base_source='BACKFILL' AND (code LIKE '60%' OR code LIKE '00%')").fetchone()[0]
print("BACKFILL 构成：主板 %d ｜ 创业板 %d" % (mb, cy))

print("pct0 分桶:")
for r in con.execute(
        "SELECT CAST(FLOOR(pct0) AS INT) b, COUNT(*) FROM picks_tracking "
        "WHERE base_source='BACKFILL' GROUP BY b ORDER BY b").fetchall():
    print("   %d~%d%%: %d" % (r[0], r[0] + 1, r[1]))

con.close()
print()
print("判定：BACKFILL 最大值应 < 5.0 ->", "通过 √" if n_over == 0 else "未生效 X")
