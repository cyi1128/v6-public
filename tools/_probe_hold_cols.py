# -*- coding: utf-8 -*-
"""量出分时做T表每列真实需要多宽（不写任何东西）。"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
for f in (r'C:\Windows\Fonts\msyh.ttc',):
    if os.path.exists(f):
        fid = QFontDatabase.addApplicationFont(f)
        if fid >= 0 and QFontDatabase.applicationFontFamilies(fid):
            app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0], 9))

import ui.battle_widgets.atr_t_widget as M  # noqa: E402
from ui.battle_widgets.atr_t_widget import AtrTWidget, HEADER_HOLD  # noqa: E402

w = AtrTWidget()
w.stop_refresh()
try:
    w._daily_timer.stop()
except Exception:
    pass
rows, _tr, _ow = w._fetch_and_calc()
w._on_hold_loaded((rows, _tr, _ow))
app.processEvents()
t = w.table
fm_plain = t.fontMetrics()
f_bold = t.font()
f_bold.setBold(True)
from PyQt6.QtGui import QFontMetrics  # noqa: E402
fm_bold = QFontMetrics(f_bold)

print('表宽 =', t.viewport().width(), '｜可见列合计 =', sum(t.columnWidth(c) for c in range(t.columnCount())))
print('%-10s %8s %10s %10s' % ('列', '当前宽', '需要宽(常规)', '需要宽(加粗)'))
need = {}
for c in range(t.columnCount()):
    mx_p = mx_b = fm_plain.horizontalAdvance(HEADER_HOLD[c])
    for r in range(t.rowCount()):
        it = t.item(r, c)
        if it is None or not it.text():
            continue
        _f = QFontMetrics(it.font())
        mx_p = max(mx_p, _f.horizontalAdvance(it.text()))
    need[c] = mx_p
    print('%-10s %8d %10d %10d' % (HEADER_HOLD[c], t.columnWidth(c), mx_p, mx_b))

CELL_PAD = 26
tot = sum(min(need[c] + CELL_PAD, 999) for c in range(t.columnCount()) if c != M.COL_H_ACT)
print('\n除「操作建议」外全按内容给量，合计 =', tot)
print('可用宽 ~820 时，留给「操作建议」=', 820 - tot)
print('「操作建议」最长文案需要 =', max(need[M.COL_H_ACT] + CELL_PAD, 120))
print('窗口整宽 1920 时版式 =', 1920 - tot)
