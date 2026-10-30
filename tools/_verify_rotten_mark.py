# -*- coding: utf-8 -*-
"""确认 ⚠烂板 标记真的渲染到界面 + 出最终截图。"""
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

n_all, n_rot, n_entry, n_inst = 0, 0, 0, 0
for row in range(w.pick_table.rowCount()):
    nm = w.pick_table.item(row, 0)
    lead = w.pick_table.item(row, 3)
    pk = w.pick_table.item(row, 4)
    if lead is not None and lead.toolTip():
        n_all += 1
        if '⚠烂板' in lead.toolTip():
            n_rot += 1
            print('  龙一为烂板：%-8s  %s'
                  % (nm.text() if nm else '?',
                     (lead.toolTip().split('\n')[1] if '\n' in lead.toolTip() else '')))
    if pk is not None and pk.toolTip() and '可介入' in pk.toolTip():
        n_entry += 1
    if pk is not None and '✅' in (pk.text() or ''):
        n_inst += 1

print()
print('龙头 tooltip 渲染：%d 行；其中标 ⚠烂板：%d 行' % (n_all, n_rot))
print('可介入 tooltip 渲染：%d 行；含 ✅ 算法单痕迹标记：%d 行' % (n_entry, n_inst))

out = r'D:\QuantMonitorV6\_shot_inst_exec.png'
pm = QPixmap(w.size())
w.render(pm)
pm.save(out)
print('截图: %s (%d bytes)' % (out, os.path.getsize(out)))
