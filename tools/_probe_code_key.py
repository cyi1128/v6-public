# -*- coding: utf-8 -*-
"""确认 quotes / sector_stocks 字典是否带 code 键（按板判的前提）。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"


def show(rel, a, b, label):
    ls = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read().split("\n")
    print("--- %s | %s L%d-L%d ---" % (label, rel, a, min(b, len(ls))))
    for i in range(a, min(b, len(ls)) + 1):
        print("  L%-5d %s" % (i, ls[i - 1].rstrip()[:120]))
    print()


def find_def(rel, pat, ctx=2):
    ls = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read().split("\n")
    print("--- %s ｜ 命中 %s ---" % (rel, pat))
    for i, t in enumerate(ls, 1):
        if re.search(pat, t):
            print("  L%-5d %s" % (i, t.rstrip()[:120]))
    print()


D = r"services\daily_close_summary_service.py"
V = r"services\v22_combat_service.py"
B = r"ui\battle_console_v2.py"

find_def(D, r"def _get_market_quotes")
find_def(D, r"def _load_cached_quotes")
find_def(D, r"quotes\.append|'code':|dict\(code=")
print("== 各文件行尾 ==")
for rel in [B, V, D, r"utils\indicators.py"]:
    raw = open(os.path.join(ROOT, rel), "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    print("  %-46s CRLF=%-5d LF=%-5d → %s" % (rel, crlf, lf, "CRLF" if crlf > lf else "LF"))
print()
find_def(V, r"def _get_market_quotes|sector_stocks =|'code':")
