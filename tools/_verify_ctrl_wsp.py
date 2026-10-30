# -*- coding: utf-8 -*-
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
from ui.watchlist_panel import WatchlistWidget  # 必须先于 QApplication 导入（QtWebEngine 要求）
app = QApplication([])

CODES = [("600845", "宝信软件"), ("002847", "盐津铺子"), ("605196", "华通线缆"), ("600587", "新华医疗")]
w = WatchlistWidget()
print("列数 %d" % w.table.columnCount())
print("表头 %s" % [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())])
stocks = [dict(code=c, name=n, price=10.0, pct_chg=1.0, signals=[], trend="--",
               limit_up_count=0, sector="--") for c, n in CODES]
w._update_table(stocks)
it0 = w.table.item(0, 9)
print("第一次渲染（后台还没算完）列9 = %r" % (it0.text() if it0 else None))
t0 = time.time()
while time.time() - t0 < 25:
    app.processEvents()
    time.sleep(0.1)
    if all(s.get("ctrl") for s in stocks):
        app.processEvents()
        break
print("后台补算耗时 %.1fs | ctrl 已填: %s" % (time.time() - t0, all(s.get("ctrl") for s in stocks)))
w._update_table(w.stocks)
bad = []
for i, (c, n) in enumerate(CODES):
    it = w.table.item(i, 9)
    txt = it.text() if it else None
    col = it.foreground().color().name() if it else "-"
    exp = {"600845": "98·候选", "002847": "97·候选", "605196": "91·出货", "600587": "44"}[c]
    if txt != exp:
        bad.append((c, txt, exp))
    print("  row%d %-6s %-8s 控盘=%r 色=%s %s" % (i, c, n, txt, col, "" if txt == exp else "← 期望 %s" % exp))
print()
print("自选评分（主界面⭐Tab）：%s" % ("全部通过" if not bad else "失败 %s" % bad))
