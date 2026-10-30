# -*- coding: utf-8 -*-
"""确认两个调用关系：谁调用 updateKline、谁调用自选小K线的 set_kline_data。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

print("### A. echarts_kline.py 里 updateKline 的所有调用/定义")
ls = io.open(ROOT + r"ui\echarts_kline.py", encoding="utf-8-sig").read().splitlines()
for i, t in enumerate(ls, 1):
    if "updateKline" in t:
        print("  L%-5d %s" % (i, t.rstrip()[:130]))

print()
print("### B. 自选小K线组件的类名 与 set_kline_data 的调用方")
ls2 = io.open(ROOT + r"ui\watchlist_panel.py", encoding="utf-8-sig").read().splitlines()
for n in range(39, 1, -1):
    if re.match(r"^class ", ls2[n - 1]):
        print("  L%-5d %s" % (n, ls2[n - 1].strip()))
        break
for i, t in enumerate(ls2, 1):
    if "set_kline_data" in t or "MiniKline" in t or "kline_widget" in t.lower():
        print("  L%-5d %s" % (i, t.rstrip()[:130]))
