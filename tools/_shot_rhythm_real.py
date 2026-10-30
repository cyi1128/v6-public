# -*- coding: utf-8 -*-
"""用**真实引擎数据**给「市场节奏 · 可介入」Tab 截图（交付验收用）。

与 _shot_rhythm_ctrl.py 不同：这里不构造行，直接走控件自己的 refresh 链路，
拿到的就是当前程序里会显示的内容（数据来自本地缓存 / 涨停原因库）。
"""
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication            # noqa: E402

app = QApplication.instance() or QApplication([])
from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget   # noqa: E402

w = MarketRhythmWidget()
w.resize(int(os.environ.get('SHOT_W', '1850')), 520)
w.show()
try:
    w.refresh(force=True)
except Exception as _e:
    print('refresh 失败:', _e, flush=True)

t0 = time.time()
while time.time() - t0 < int(os.environ.get('SHOT_WAIT', '150')):
    app.processEvents()
    if w.pick_table.rowCount() > 0 or w.table.rowCount() > 0:
        break
    time.sleep(0.1)
for _ in range(20):
    app.processEvents()
    time.sleep(0.05)

print('Tab1 行数 %d ｜ Tab2 行数 %d ｜ 用时 %.1fs'
      % (w.table.rowCount(), w.pick_table.rowCount(), time.time() - t0), flush=True)
w._switch_tab(1)
app.processEvents()
time.sleep(0.3)
w.grab().save(r'D:\QuantMonitorV6\tools\_shot_rhythm_real_tab2.png')
w._switch_tab(0)
app.processEvents()
time.sleep(0.3)
w.grab().save(r'D:\QuantMonitorV6\tools\_shot_rhythm_real_tab1.png')
print('真实数据截图: tools\\_shot_rhythm_real_tab1.png / _shot_rhythm_real_tab2.png', flush=True)
