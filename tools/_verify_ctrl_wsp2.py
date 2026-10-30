# -*- coding: utf-8 -*-
"""自选评分（主界面 ⭐ Tab）控盘列：分两段验证，避开 QtWebEngine 离屏崩溃。
 链路A：_ctrl_async 能把 ctrl 填进行数据（纯线程，不需事件循环）
 链路B：_update_table 会把 row['ctrl'] 写进第 9 列
"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
from ui.watchlist_panel import WatchlistWidget
app = QApplication([])

CODES = [("600845", "宝信软件"), ("002847", "盐津铺子"), ("605196", "华通线缆"), ("600587", "新华医疗")]
EXP = {"600845": "98·候选", "002847": "97·候选", "605196": "91·出货", "600587": "44"}
w = WatchlistWidget()

print("【链路A】_ctrl_async 后台补算（不跑事件循环，只看行数据是否被填）")
stocks = [dict(code=c, name=n, price=10.0, pct_chg=1.0, signals=[], trend="--",
               limit_up_count=0, sector="--") for c, n in CODES]
w._ctrl_async(stocks)
t0 = time.time()
while time.time() - t0 < 30 and not all(s.get("ctrl") for s in stocks):
    time.sleep(0.1)
a_ok = all(s.get("ctrl") for s in stocks)
print("   填完=%s 耗时%.1fs  分数=%s" % (a_ok, time.time() - t0,
      [round(s["ctrl"]["score"], 1) if s.get("ctrl") else None for s in stocks]))
print("   不会重复触发: 再调一次 _ctrl_async -> %s" % (
    (w._ctrl_async(stocks), "已填过，直接返回")[1]))

print()
print("【链路B】_update_table 把 ctrl 写进第 9 列")
print("   列数 %d | 表头 %s" % (w.table.columnCount(),
      [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())]))
w._update_table(stocks)
bad = []
for i, (c, n) in enumerate(CODES):
    it = w.table.item(i, 9)
    txt = it.text() if it else None
    col = it.foreground().color().name() if it else "-"
    tip = (it.toolTip().split(chr(10))[0] if it else None)
    if txt != EXP[c]:
        bad.append((c, txt, EXP[c]))
    print("   row%d %-6s %-8s 控盘=%r 色=%s  %s" % (i, c, n, txt, col, tip))
print()
print("自选评分（主界面⭐Tab）：%s" % ("链路A + 链路B 全部通过" if (a_ok and not bad) else "失败 a_ok=%s %s" % (a_ok, bad)))
sys.stdout.flush()
os._exit(0)
