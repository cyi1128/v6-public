# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
app = QApplication([])
from ui.battle_widgets.base import fetch_ctrl_for

# 真实代码：97.8候选 / 44.1出货 / 91.0出货 / 002847候选
CODES = [("600845", "宝信软件"), ("600587", "新华医疗"), ("605196", "华通线缆"), ("002847", "盐津铺子")]

print("=" * 76)
print("【1】今日涨停")
from ui.battle_widgets.limit_up_widget import LimitUpWidget, COL_CTRL as LZ_CTRL
w1 = LimitUpWidget()
rows = [{"code": c, "name": n, "price": 10.0, "pct": 10.0, "mv": 100.0,
         "industry": "测试行业", "_theme": "测试题材"} for c, n in CODES]
fetch_ctrl_for(rows)
w1._stocks = rows
w1._render_rows()
print("   列数 %d | 行数 %d" % (w1.table.columnCount(), w1.table.rowCount()))
print("   末列标题:", w1.table.horizontalHeaderItem(w1.table.columnCount()-1).text())
for i, (c, n) in enumerate(CODES):
    it = w1.table.item(i, LZ_CTRL)
    print("   %-6s %-8s 控盘='%s'  色=%s  tooltip=%s" % (
        c, n, it.text() if it else None,
        it.foreground().color().name() if it else "-",
        (it.toolTip().replace(chr(10), " / ") if it else None)))

print()
print("=" * 76)
print("【2】自选评分")
from ui.battle_widgets.watchlist_widget import WatchlistWidget, COL_CTRL as WL_CTRL, HEADER_LABELS
w2 = WatchlistWidget()
w2._watchlist = [{"code": c, "name": n} for c, n in CODES]
quotes = {c: {"price": 10.0, "pct_chg": 1.0, "amplitude": 3.0, "total_mv": 100.0, "name": n}
          for c, n in CODES}
fetch_ctrl_for([dict(code=c, name=n) for c, n in CODES])
from services.control_profile import get_ctrl_map
m = get_ctrl_map([c for c, _ in CODES])
for c in quotes:
    quotes[c]["ctrl"] = m.get(c)
w2._themes = {c: "测试题材" for c, _ in CODES}
w2._populate_table(quotes)
print("   列数 %d | 行数 %d" % (w2.table.columnCount(), w2.table.rowCount()))
print("   表头:", [w2.table.horizontalHeaderItem(i).text() for i in range(w2.table.columnCount())])
for i in range(w2.table.rowCount()):
    it = w2.table.item(i, WL_CTRL)
    print("   %-8s 控盘='%s'  tooltip=%s" % (
        w2.table.item(i, 1).text(), it.text() if it else None,
        (it.toolTip().split(chr(10))[0] if it else None)))
print("   COL_CTRL=%d 表头长=%d" % (WL_CTRL, len(HEADER_LABELS)))
