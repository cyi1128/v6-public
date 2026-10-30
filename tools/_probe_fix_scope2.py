# -*- coding: utf-8 -*-
"""确认 4.3 的 HTML 模板边界、4.4 的代码属性名。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"


def dump(rel, a, b, label):
    ls = io.open(ROOT + rel, encoding="utf-8-sig").read().splitlines()
    print("=" * 80)
    print("%s ｜ %s  L%d-L%d" % (label, rel, a, b))
    print("=" * 80)
    for n in range(a, min(b, len(ls)) + 1):
        print("  L%-5d %s" % (n, ls[n - 1].rstrip()))
    print()


ls = io.open(ROOT + r"ui\echarts_kline.py", encoding="utf-8-sig").read().splitlines()
print("### echarts_kline.py：L247 之前最近的 3 个 三引号/赋值（定位模板边界）")
cnt = 0
for n in range(247, 0, -1):
    t = ls[n - 1]
    if re.search(r'"""?\s*$|=\s*[rf]?"""|^"""|f"""', t) and ("=" in t or t.strip().startswith('"""')):
        print("  L%-5d %s" % (n, t.rstrip()[:120]))
        cnt += 1
        if cnt >= 4:
            break
print()
dump(r"ui\echarts_kline.py", 196, 250, "4.3-c 模板起头与 applyLimitColors 所在位置")
dump(r"ui\echarts_kline.py", 1145, 1172, "4.3-d set_kline_data 的 f-string")

ls2 = io.open(ROOT + r"ui\watchlist_panel.py", encoding="utf-8-sig").read().splitlines()
print("### watchlist_panel.py：自选K线小图类里的 code/name 属性名")
for n in range(1, 260):
    t = ls2[n - 1]
    if re.search(r"self\.(code|current_code|stock_code|stock_name|industry|name)\s*=", t):
        print("  L%-5d %s" % (n, t.rstrip()[:120]))
print()
dump(r"ui\watchlist_panel.py", 40, 100, "4.4-b 类头与 paintEvent 起头")
