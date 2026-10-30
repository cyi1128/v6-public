# -*- coding: utf-8 -*-
"""定位 4 个文件的模块级插入锚点 + 待改行原文。"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6"
FILES = [r"ui\battle_console_v2.py",
         r"services\v22_combat_service.py",
         r"services\daily_close_summary_service.py",
         r"utils\indicators.py"]

for rel in FILES:
    ls = io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read().split("\n")
    print("=" * 76)
    print("%s  （共 %d 行）" % (rel, len(ls)))
    print("=" * 76)
    print("  -- 顶部 1-14 行 --")
    for i in range(1, 15):
        print("  L%-5d %s" % (i, ls[i - 1].rstrip()[:110]))
    first_cls = next((i for i, t in enumerate(ls, 1)
                      if re.match(r"^(class |def )", t)), None)
    print("  -- 第一个模块级 class/def：L%s --" % first_cls)
    if first_cls:
        for i in range(max(1, first_cls - 3), first_cls + 2):
            print("  L%-5d %s" % (i, ls[i - 1].rstrip()[:110]))
    print()
