# -*- coding: utf-8 -*-
"""修复生成器里被拼掉换行的那一行。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
p = r"D:\QuantMonitorV6\tools\_gen_audit_detail.py"
s = io.open(p, encoding="utf-8").read()
bad = 'txt = "\\n".join(D)os.makedirs('
good = 'txt = "\\n".join(D)' + "\n" + "os.makedirs("
print("找到拼接行:", bad in s)
if bad in s:
    s = s.replace(bad, good)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("已修复")
L = io.open(p, encoding="utf-8").read().split("\n")
for n in range(734, 741):
    print("L%-4d %s" % (n, L[n - 1][:110]))
