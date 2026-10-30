# -*- coding: utf-8 -*-
"""确认 4.3 的 JS 注入方式 与 4.4 的变量作用域。"""
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


# 4.3：JS 模板是怎么被构造/注入的
ls = io.open(ROOT + r"ui\echarts_kline.py", encoding="utf-8-sig").read().splitlines()
print("### echarts_kline.py 里所有 f-string / format / % 注入线索（含 dates/klineData 变量定义）")
for i, t in enumerate(ls, 1):
    if re.search(r"klineData\s*=|dates\s*=|volumes\s*=|var dates|var volumes|"
                 r"js_code|html\s*=|\.format\(|f'''|f\"\"\"|% \(", t):
        print("  L%-5d %s" % (i, t.rstrip()[:130]))
print()
dump(r"ui\echarts_kline.py", 1030, 1070, "4.3-b Python 侧组装入口")

# 4.4：自选绘图方法的定义与变量来源
ls2 = io.open(ROOT + r"ui\watchlist_panel.py", encoding="utf-8-sig").read().splitlines()
print("### watchlist_panel.py 里 L192 所属方法：向上找最近的 def")
for n in range(192, 0, -1):
    if re.match(r"^\s*def ", ls2[n - 1]):
        print("   所在 def 在 L%d：%s" % (n, ls2[n - 1].strip()))
        break
print()
print("### 该 def 到 L192 之间所有赋值行（找 code / opens / closes 怎么来的）")
for n in range(60, 195):
    t = ls2[n - 1]
    if re.search(r"^\s*(def |code\s*=|opens\s*=|closes\s*=|highs\s*=|lows\s*=|self\.\w+\s*=|kline\w*\s*=)", t):
        print("  L%-5d %s" % (n, t.rstrip()[:130]))
