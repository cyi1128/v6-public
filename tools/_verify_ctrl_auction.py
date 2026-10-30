# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui.battle_widgets.base import fetch_ctrl_for
from services.control_profile import get_ctrl_map

CODES = [("600845", "宝信软件"), ("600587", "新华医疗"), ("605196", "华通线缆")]
print("=" * 74)
print("【3】竞价筛选 · 今日竞价")
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget, COL_CTRL, C_TRACK_CTRL, TRACK_COL_N
w = AuctionFilterWidget()
rows = []
for c, n in CODES:
    rows.append({"code": c, "name": n, "score": 66.0, "gap": 3.0, "jj_turnover": 1.0,
                 "open": 10.0, "cur_price": 10.5, "cur_pct": 2.0, "theme_display": "测试题材"})
fetch_ctrl_for(rows)
w._rows = rows
w._render_rows()
print("   列数 %d | 行数 %d" % (w.table.columnCount(), w.table.rowCount()))
print("   表头:", [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())])
for i, (c, n) in enumerate(CODES):
    it = w.table.item(i, COL_CTRL)
    print("   %-6s %-8s 控盘='%s' 色=%s" % (c, n, it.text() if it else None,
          it.foreground().color().name() if it else "-"))

print()
print("【4】竞价筛选 · 竞价追踪")
w.track_list = [{"trade_date": "2026-10-09", "name": n, "code": c, "theme": "测试",
                 "base_price": 10.0, "cur_price": 11.0, "p5": 5.0, "p30": None, "cum": 5.0}
                for c, n in CODES]
fetch_ctrl_for(w.track_list)
w._render_tracking()
print("   列数 %d | 行数 %d" % (w.track_table.columnCount(), w.track_table.rowCount()))
print("   表头:", [w.track_table.horizontalHeaderItem(i).text() for i in range(w.track_table.columnCount())])
for i, (c, n) in enumerate(CODES):
    it = w.track_table.item(i, C_TRACK_CTRL)
    print("   %-6s %-8s 控盘='%s' 色=%s" % (c, n, it.text() if it else None,
          it.foreground().color().name() if it else "-"))
print("   TRACK_COL_N=%d  C_TRACK_CTRL=%d" % (TRACK_COL_N, C_TRACK_CTRL))
