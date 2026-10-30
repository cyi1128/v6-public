# -*- coding: utf-8 -*-
"""给「市场节奏」三个 Tab 各出一张渲染图（真实数据）"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication          # noqa: E402
from PyQt6.QtGui import QFont, QPixmap            # noqa: E402
from PyQt6.QtCore import Qt                       # noqa: E402

app = QApplication(sys.argv)
app.setFont(QFont('Microsoft YaHei', 10))

from services.market_rhythm_engine import get_rhythm              # noqa: E402
from services.board_anomaly_engine import (get_board_anomaly,      # noqa: E402
                                          get_flat_rows)
from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget  # noqa: E402

H = 452
W = 1890

rh = get_rhythm()
bd = get_board_anomaly()
rows_b = get_flat_rows(bd)

w = MarketRhythmWidget()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
w.resize(W, H)
w.show()
app.processEvents()

for idx, out in ((0, r'D:\QuantMonitorV6\_shot_rhythm_tab1.png'),
                 (1, r'D:\QuantMonitorV6\_shot_rhythm_tab2.png')):
    w._switch_tab(idx)
    if idx == 0:
        w._apply({'rhythm': rh, 'boards': rows_b, 'board_meta': bd})
    app.processEvents()
    pm = QPixmap(w.size())
    w.render(pm)
    pm.save(out)
    print('已保存: %s  (%d bytes)' % (out, __import__('os').path.getsize(out)))
print('Tab1 行数=%d   Tab2 行数=%d' % (w.table.rowCount(), w.pick_table.rowCount()))
