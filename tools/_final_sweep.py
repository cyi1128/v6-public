# -*- coding: utf-8 -*-
"""最终收尾核对：AGENTS.md 行尾 + 全项目残留写死 10cm 扫描。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"

print("=" * 78)
print("一、AGENTS.md 与 5 个被改文件的行尾")
print("=" * 78)
for rel in ["AGENTS.md",
            r"services\picks_tracking_service.py",
            r"ui\market_sentiment_panel.py",
            r"ui\echarts_kline.py",
            r"ui\watchlist_panel.py",
            r"services\intraday_opportunity_engine.py"]:
    raw = open(os.path.join(ROOT, rel), "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    print("  %-46s CRLF=%-5d LF=%-5d → %s" % (rel, crlf, lf, "CRLF" if crlf > lf else "LF"))

print()
print("=" * 78)
print("二、全项目「判涨停」阈值残留扫描（只看 .py，排除 AI520 与备份）")
print("=" * 78)
SKIP_DIR = {"backups", ".git", "__pycache__", "logs", "data", "assets", ".preview"}
SKIP_NAME = ("ai520", "ai_520")
PAT = re.compile(r"(9\.5|9\.8|9\.9|19\.5|19\.8|19\.9|29\.5)")
hits = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIR]
    for fn in files:
        if not fn.endswith(".py") or fn.endswith(".bak") or ".bak_" in fn:
            continue
        if any(s in fn for s in SKIP_NAME):
            continue
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, ROOT)
        try:
            for i, t in enumerate(io.open(p, encoding="utf-8-sig").read().split("\n"), 1):
                if PAT.search(t) and re.search(r"pct|涨幅|涨停|limit_up|limitup|lu_|>= *9|<= *-9", t):
                    hits.append((rel, i, t.strip()[:104]))
        except Exception as e:
            print("  ! 读取失败 %s：%s" % (rel, e))

for rel, i, t in hits:
    print("  %-44s L%-5d %s" % (rel, i, t))
print()
print("  共 %d 行命中 —— 需逐条判断是否还需要按板性处理" % len(hits))
