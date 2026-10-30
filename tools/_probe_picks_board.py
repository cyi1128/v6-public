# -*- coding: utf-8 -*-
"""核查 picks_tracking_service.py 的板性过滤：回填 SQL 是否包含创业板。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\services\picks_tracking_service.py"
raw = open(P, "rb").read()
crlf = raw.count(b"\r\n")
lf = raw.count(b"\n") - crlf
print("行尾：CRLF=%d  LF=%d  ->  %s" % (crlf, lf, "纯 LF" if crlf == 0 else ("纯 CRLF" if lf == 0 else "混合")))
print()

s = raw.decode("utf-8-sig")
L = s.split("\n")
KEYS = ["LIKE '6", "LIKE '0", "LIKE '3", "startswith((", "PREFIX", "_is_main"]
print("--- 板性 / 前缀过滤的所有出现处 ---")
for i, t in enumerate(L, 1):
    if any(k in t for k in KEYS):
        print("  L%-5d %s" % (i, t.strip()[:118]))

print()
print("--- backfill_history 里那段 SQL 的 WHERE ---")
inside = False
for i, t in enumerate(L, 1):
    if "def backfill_history" in t:
        inside = True
    if inside and ("FROM kline_cache" in t or "WHERE code LIKE" in t):
        print("  L%-5d %s" % (i, t.strip()[:118]))
    if inside and i > 520:
        break

print()
print("--- 引擎当日筛选路径里的板性过滤（fetch_candidates / 相关函数）---")
for i, t in enumerate(L, 1):
    if "def " in t and ("fetch" in t or "candidate" in t.lower() or "scan" in t):
        print("  L%-5d %s" % (i, t.strip()[:118]))
