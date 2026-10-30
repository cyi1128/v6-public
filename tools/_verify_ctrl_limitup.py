import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"D:\QuantMonitorV6")
sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui.battle_widgets.limit_up_widget import LimitUpWidget, HEADER_LABELS, COL_CTRL
from ui.battle_widgets.base import fetch_ctrl_for, attach_ctrl
print("表头:", HEADER_LABELS)
print("COL_CTRL =", COL_CTRL)
w = LimitUpWidget()
print("表格列数:", w.table.columnCount(), "| 行数:", w.table.rowCount())
c = w.table.columnCount()
print("末列标题:", w.table.horizontalHeaderItem(c-1).text() if w.table.horizontalHeaderItem(c-1) else None)
