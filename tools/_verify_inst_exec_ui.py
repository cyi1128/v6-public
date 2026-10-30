# -*- coding: utf-8 -*-
"""UI 实测：龙头 tooltip（含封成比/烂板）+ 可介入列 ✅ 与 tooltip + 出图。"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication                        # noqa: E402
from PyQt6.QtGui import QFont, QPixmap                          # noqa: E402
from PyQt6.QtCore import Qt                                     # noqa: E402

app = QApplication(sys.argv)
app.setFont(QFont('Microsoft YaHei', 10))

from services.board_anomaly_engine import (get_board_anomaly,    # noqa: E402
                                          get_flat_rows)
from services.market_rhythm_engine import get_rhythm            # noqa: E402
from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget  # noqa

rh, bd = get_rhythm(), get_board_anomaly()
rows_b = get_flat_rows(bd)

w = MarketRhythmWidget()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
w.resize(1890, 452)
w.show()
app.processEvents()
w._switch_tab(1)
w._apply({'rhythm': rh, 'boards': rows_b, 'board_meta': bd})
app.processEvents()

print('可介入 Tab 行数 = %d' % w.pick_table.rowCount())
print()
print('=' * 96)
print('一、可介入列文本（看 ✅ 标记）')
print('=' * 96)
for row in range(w.pick_table.rowCount()):
    nm = w.pick_table.item(row, 0)
    pk = w.pick_table.item(row, 4)
    if nm is None or pk is None:
        continue
    print('  %-10s │ %s' % (nm.text(), pk.text()))

print()
print('=' * 96)
print('二、可介入 tooltip 实测（带 ✅ 的那一行）')
print('=' * 96)
for row in range(w.pick_table.rowCount()):
    pk = w.pick_table.item(row, 4)
    if pk is None or '✅' not in (pk.text() or ''):
        continue
    nm = w.pick_table.item(row, 0)
    print('【%s】' % (nm.text() if nm else '?'))
    print(pk.toolTip())
    print('-' * 96)
    break

print()
print('=' * 96)
print('三、龙头 tooltip 实测（找一个带 ⚠烂板 的板块）')
print('=' * 96)
found = 0
for row in range(w.pick_table.rowCount()):
    it = w.pick_table.item(row, 3)
    if it is None:
        continue
    tip = it.toolTip() or ''
    nm = w.pick_table.item(row, 0)
    if '情绪龙头' not in tip:
        continue
    print('【%s】' % (nm.text() if nm else '?'))
    print(tip)
    print('-' * 96)
    found += 1
    if found >= 2:
        break

out = r'D:\QuantMonitorV6\_shot_inst_exec.png'
pm = QPixmap(w.size())
w.render(pm)
pm.save(out)
print('截图: %s (%d bytes)' % (out, os.path.getsize(out)))
