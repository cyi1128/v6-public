# -*- coding: utf-8 -*-
"""把 5 处待修区域的完整上下文一次性读出来。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + "\\"

REGIONS = [
    (r"services\picks_tracking_service.py", 40, 60, "4.1-a 常量区"),
    (r"services\picks_tracking_service.py", 500, 545, "4.1-b 使用处"),
    (r"services\picks_tracking_service.py", 462, 472, "4.1-c 注释"),
    (r"ui\market_sentiment_panel.py", 1, 40, "4.2-0 文件头（找放常量的位置）"),
    (r"ui\market_sentiment_panel.py", 385, 435, "4.2-a 涨停/跌停/炸板"),
    (r"ui\echarts_kline.py", 238, 275, "4.3-a JS 上色"),
    (r"ui\watchlist_panel.py", 168, 205, "4.4 自选K线小图配色"),
    (r"services\intraday_opportunity_engine.py", 1455, 1485, "4.5 追高提示文案"),
]

for rel, a, b, label in REGIONS:
    ls = io.open(ROOT + rel, encoding="utf-8-sig").read().splitlines()
    print("=" * 80)
    print("%s ｜ %s  L%d-L%d" % (label, rel, a, b))
    print("=" * 80)
    for n in range(a, min(b, len(ls)) + 1):
        print("  L%-5d %s" % (n, ls[n - 1].rstrip()))
    print()
