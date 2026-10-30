# -*- coding: utf-8 -*-
"""查 TRACK_KEEP_DAYS 的清理逻辑，解释 5901 -> 5603 的差额。"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
sys.path.insert(0, ROOT)

print("=" * 78)
print("一、TRACK_KEEP_DAYS 在哪些地方用到")
print("=" * 78)
found = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in {"backups", ".git", "__pycache__", "logs", ".preview"}
               and "backup" not in d]
    for fn in files:
        if not fn.endswith(".py") or ".bak" in fn:
            continue
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, ROOT)
        try:
            txt = io.open(p, encoding="utf-8-sig").read()
        except Exception:
            continue
        for i, t in enumerate(txt.split("\n"), 1):
            if "TRACK_KEEP_DAYS" in t or "DELETE FROM picks_tracking" in t:
                print("  %-42s L%-5d %s" % (rel, i, t.strip()[:100]))
                found.append((rel, i, t.strip()))

print()
print("=" * 78)
print("二、库内按日期的分布（看被删掉的是不是最早那几天）")
print("=" * 78)
import duckdb  # noqa: E402

DB = os.path.join(ROOT, "data", "cache", "picks_tracking.duckdb")
con = duckdb.connect(DB, read_only=True)
rows = con.execute(
    "SELECT trade_date, COUNT(*) AS n, SUM(CASE WHEN code LIKE '30%' THEN 1 ELSE 0 END) AS cyb "
    "FROM picks_tracking GROUP BY trade_date ORDER BY trade_date").fetchall()
con.close()
print("  共 %d 个交易日" % len(rows))
print("  最早 8 天：")
for d, n, c in rows[:8]:
    print("    %s  合计 %4d ｜ 创业板 %3d" % (d, n, c))
print("  最晚 5 天：")
for d, n, c in rows[-5:]:
    print("    %s  合计 %4d ｜ 创业板 %3d" % (d, n, c))

import datetime  # noqa: E402
today = datetime.date(2026, 10, 10)
print()
print("  按 100 个自然日推算的保留边界：%s" % (today - datetime.timedelta(days=100)))
print("  -> 早于该日期的记录会被清理，正好解释我回填进来的 06-26 ~ 07-0x 被删掉")
