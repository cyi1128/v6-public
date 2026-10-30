# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui.battle_widgets.base import fetch_ctrl_for
CODES = [("600845", "宝信软件"), ("600587", "新华医疗"), ("605196", "华通线缆")]
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget, C_TRACK_CTRL, TRACK_COL_N
w = AuctionFilterWidget()
w.track_list = [{"trade_date": "2026-10-09", "name": n, "code": c, "theme": "测试",
                 "base_price": 10.0, "cur_price": 11.0, "r5": 5.0, "r30": None, "cum_pnl": 5.0}
                for c, n in CODES]
fetch_ctrl_for(w.track_list)
w._render_tracking()
print("【4】竞价追踪")
print("   列数 %d | 行数 %d" % (w.track_table.columnCount(), w.track_table.rowCount()))
print("   表头:", [w.track_table.horizontalHeaderItem(i).text() for i in range(w.track_table.columnCount())])
for i, (c, n) in enumerate(CODES):
    it = w.track_table.item(i, C_TRACK_CTRL)
    print("   %-6s %-8s 控盘='%s' 色=%s  tooltip=%s" % (
        c, n, it.text() if it else None, it.foreground().color().name() if it else "-",
        it.toolTip().split(chr(10))[0] if it else None))
print("   TRACK_COL_N=%d C_TRACK_CTRL=%d" % (TRACK_COL_N, C_TRACK_CTRL))
print("   原列未错位检查: 日期='%s' 名称='%s' 代码='%s'" % (
    w.track_table.item(0, 0).text(), w.track_table.item(0, 1).text(), w.track_table.item(0, 3).text()))
