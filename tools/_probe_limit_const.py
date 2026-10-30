# -*- coding: utf-8 -*-
"""确认 picks_tracking_service.LIMIT_UP_PCT 现在的状态（定义 / 使用 / 外部引用）。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
TARGET = r"services\picks_tracking_service.py"

s = io.open(os.path.join(ROOT, TARGET), encoding="utf-8-sig").read()
print("--- %s 里所有 LIMIT_UP_PCT 出现处 ---" % TARGET)
for i, t in enumerate(s.split("\n"), 1):
    if "LIMIT_UP_PCT" in t:
        tag = "定义" if re.match(r"^\s*LIMIT_UP_PCT\s*=", t) else "使用/注释"
        print("  L%-5d [%s] %s" % (i, tag, t.strip()[:104]))

print()
print("--- 全项目其它文件对 LIMIT_UP_PCT 的引用 ---")
SKIP = {"backups", ".git", "__pycache__", "logs", "data", "assets", ".preview"}
n = 0
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP and "backup" not in d]
    for fn in files:
        if not fn.endswith(".py") or ".bak" in fn:
            continue
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, ROOT)
        if rel == TARGET:
            continue
        try:
            txt = io.open(p, encoding="utf-8-sig").read()
        except Exception:
            continue
        for i, t in enumerate(txt.split("\n"), 1):
            if "LIMIT_UP_PCT" in t:
                print("  %-42s L%-5d %s" % (rel, i, t.strip()[:96]))
                n += 1
if n == 0:
    print("  （无外部引用）")
