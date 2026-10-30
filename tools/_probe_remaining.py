# -*- coding: utf-8 -*-
"""查清上一轮审计没覆盖的几处写死 10cm 是否在线上链路。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
SKIP_DIR = {"backups", ".git", "__pycache__", "logs", "data", "assets", ".preview", "test", "tests"}


def grep_project(pat, label):
    print("--- 谁引用了 %s ---" % label)
    n = 0
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR and "backup" not in d]
        for fn in files:
            if not fn.endswith(".py") or ".bak" in fn:
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ROOT)
            if rel.replace("\\", ".")[:-3].endswith(pat.replace("\\", ".")[:-3]):
                continue          # 跳过自己
            try:
                txt = io.open(p, encoding="utf-8-sig").read()
            except Exception:
                continue
            for i, t in enumerate(txt.split("\n"), 1):
                if re.search(pat, t):
                    print("   %-44s L%-5d %s" % (rel, i, t.strip()[:100]))
                    n += 1
    if n == 0:
        print("   （无引用）")
    print()


def show(rel, a, b, label):
    ls = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read().split("\n")
    print("--- %s ｜ %s L%d-L%d ---" % (label, rel, a, b))
    for i in range(a, min(b, len(ls)) + 1):
        print("   L%-5d %s" % (i, ls[i - 1].rstrip()[:118]))
    print()


grep_project(r"daily_close_summary_service", "services\\daily_close_summary_service.py")
grep_project(r"v22_combat_service", "services\\v22_combat_service.py")
grep_project(r"from utils\.indicators|import indicators|utils import indicators", "utils.indicators")
grep_project(r"Indicators\.(calc_limit_up|is_limit_up|limit_up_count)|calc_limit_up", "utils.indicators 的涨停函数")

show(r"ui\battle_console_v2.py", 3768, 3790, "主界面 L3779 上下文")
show(r"utils\indicators.py", 328, 352, "utils/indicators 涨停函数")
show(r"services\daily_close_summary_service.py", 150, 165, "收盘总结 L159")
