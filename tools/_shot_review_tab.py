# -*- coding: utf-8 -*-
"""单独截「盘后复盘」子页。"""
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication([])
from ui.battle_widgets.strategy_panel_widget import StrategyPanelWidget
w = StrategyPanelWidget()
w.resize(1500, 820)
w.show()
# 切到第二个外层页签（盘后复盘）
outer = w.content_layout.itemAt(0).widget()
print('外层页签:', [outer.tabText(i) for i in range(outer.count())])
outer.setCurrentIndex(1)
inner = outer.widget(1)
print('内层页签:', [inner.tabText(i) for i in range(inner.count())])
inner.setCurrentIndex(0)  # 连板梯队
app.processEvents()
shot = r'D:\QuantMonitorV6\tools\_shot_review_tab1.png'
def shoot():
    w.grab().save(shot)
    print('saved', shot)
    app.quit()
QTimer.singleShot(1500, shoot)
app.exec()
