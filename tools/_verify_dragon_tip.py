# -*- coding: utf-8 -*-
"""验收 UI：可介入 Tab 的龙头 tooltip 是否真的写入了新内容，并出图。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication          # noqa: E402
from PyQt6.QtGui import QFont, QPixmap            # noqa: E402
from PyQt6.QtCore import Qt                       # noqa: E402

app = QApplication(sys.argv)
app.setFont(QFont('Microsoft YaHei', 10))

from services.board_anomaly_engine import (get_board_anomaly,      # noqa: E402
                                          get_flat_rows)
from services.market_rhythm_engine import get_rhythm              # noqa: E402
from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget  # noqa

rh = get_rhythm()
bd = get_board_anomaly()
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
print('=' * 90)
print('龙头单元格 tooltip 实测内容（前 4 行）')
print('=' * 90)
P_LEAD = 3
shown = 0
for row in range(w.pick_table.rowCount()):
    it = w.pick_table.item(row, P_LEAD)
    if it is None:
        continue
    tip = it.toolTip() or ''
    if '接力' in tip:
        shown += 1
        if shown <= 4:
            name = w.pick_table.item(row, 0)
            print('板 块：%s' % (name.text() if name else '?'))
            print(tip)
            print('-' * 90)

has = sum(1 for row in range(w.pick_table.rowCount())
          if (w.pick_table.item(row, P_LEAD) is not None
              and '接力参考' in (w.pick_table.item(row, P_LEAD).toolTip() or '')))
print('带「次日接力参考」的单元格：%d / %d 行'
      % (has, w.pick_table.rowCount()))

out = r'D:\QuantMonitorV6\_shot_dragon_v2.png'
pm = QPixmap(w.size())
w.render(pm)
pm.save(out)
import os
print('截图已保存: %s (%d bytes)' % (out, os.path.getsize(out)))
