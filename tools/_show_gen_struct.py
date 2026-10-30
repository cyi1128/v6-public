# -*- coding: utf-8 -*-
"""查看生成脚本结构（章节标题 + 末尾），供追加新章节用。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
L = io.open(r"D:\QuantMonitorV6\tools\_gen_audit_detail.py", encoding="utf-8").read().split("\n")
N = len(L)
print("生成脚本共 %d 行" % N)
print()
print("--- 所有 W(\"# ...\") 章节标题 ---")
for i, t in enumerate(L, 1):
    ts = t.strip()
    if ts.startswith('W("#') or ts.startswith("W('#"):
        print("  L%-4d %s" % (i, ts[:110]))
print()
print("--- 末尾 45 行 ---")
for i in range(max(1, N - 44), N + 1):
    print("  L%-4d %s" % (i, L[i - 1][:130]))
