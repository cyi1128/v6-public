# -*- coding: utf-8 -*-
"""自检生成出来的明细文档：有没有空块 / 提取失败 / 行号异常。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\QuantMonitorV6\docs\全量反推核对明细_20261010.md"
s = io.open(P, encoding="utf-8").read()
lines = s.splitlines()
print("总行数 %d ｜ 字符 %d" % (len(lines), len(s)))

print()
print("=== 1. 提取失败检查 ===")
bad = [i + 1 for i, t in enumerate(lines) if "文件缺失" in t or "无命中" in t]
print("   异常标记处：%d %s" % (len(bad), bad if bad else "→ 无"))

print()
print("=== 2. 代码块配对检查 ===")
fence = [i + 1 for i, t in enumerate(lines) if t.strip().startswith("```")]
print("   围栏数：%d → %s" % (len(fence), "配对 OK" if len(fence) % 2 == 0 else "!! 不配对"))

print()
print("=== 3. 代码块内容抽样（每个文件块首行）===")
for i, t in enumerate(lines):
    if re.match(r"^```(python|javascript|text)?$", t.strip()) and i + 1 < len(lines):
        nxt = lines[i + 1]
        if re.match(r"^L\d+ ", nxt) or nxt.strip().startswith("L"):
            print("   文档行%-5d %s" % (i + 2, nxt[:100]))

print()
print("=== 4. 是否出现「本文件不存在」的锚点（空块）===")
empty = 0
for i, t in enumerate(lines):
    if re.match(r"^\*\*.+\*\*", t):
        # 找该标题后的第一个围栏
        for j in range(i + 1, min(i + 8, len(lines))):
            if lines[j].strip().startswith("```"):
                if j + 1 >= len(lines) or lines[j + 1].strip().startswith("```"):
                    print("   !! 标题后是空块：文档行%d %s" % (i + 1, t[:80]))
                    empty += 1
                break
print("   空块数：%d" % empty)

print()
print("=== 5. 章节标题 ===")
for i, t in enumerate(lines, 1):
    if re.match(r"^#{2,3} ", t):
        print("   %-6d %s" % (i, t[:90]))
