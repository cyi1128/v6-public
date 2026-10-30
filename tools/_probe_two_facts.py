# -*- coding: utf-8 -*-
"""探测两个前置事实：仪表盘 stocks 的键名、环境截面函数名。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

print("=== A. utils\\tdx_stock_list.py 里 get_stocks_with_quotes_tdx 返回的键 ===")
s = io.open(ROOT + r"utils\tdx_stock_list.py", encoding="utf-8-sig").read()
lines = s.splitlines()
start = None
for i, ln in enumerate(lines):
    if "def get_stocks_with_quotes_tdx" in ln:
        start = i
        print("   L%d : %s" % (i + 1, ln.rstrip()))
        break
if start is None:
    print("   !! 未找到该函数")
else:
    for j in range(start, min(len(lines), start + 60)):
        t = lines[j]
        if re.search(r"""['"]code['"]|['"]pct_chg['"]|['"]name['"]""", t):
            print("   L%d : %s" % (j + 1, t.strip()[:120]))

print()
print("=== B. band_pattern_engine 里环境截面相关函数定义 ===")
s2 = io.open(ROOT + r"services\band_pattern_engine.py", encoding="utf-8-sig").read()
lines2 = s2.splitlines()
for i, ln in enumerate(lines2, 1):
    if re.match(r"^def |^    def ", ln):
        if any(k in ln for k in ("env", "ctx", "cross", "环境", "截面")):
            print("   L%d : %s" % (i, ln.rstrip()))
print("   --- _ENV_CTX 出现处 ---")
for i, ln in enumerate(lines2, 1):
    if "_ENV_CTX" in ln:
        print("   L%d : %s" % (i, ln.strip()[:110]))
print("   --- 含 kline_cache 的 SELECT 所在函数附近 ---")
for i, ln in enumerate(lines2, 1):
    if "SELECT DISTINCT date FROM kline_cache" in ln:
        for j in range(max(0, i - 40), i):
            if re.match(r"^def |^    def ", lines2[j]):
                print("   该段属于 L%d : %s" % (j + 1, lines2[j].strip()))
