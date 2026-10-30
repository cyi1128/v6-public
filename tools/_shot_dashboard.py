# -*- coding: utf-8 -*-
"""同步渲染仪表盘截图（绕开后台线程，定位崩溃点）。"""
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication([])
from services.market_dashboard_service import compute_dashboard
from ui.battle_widgets.market_dashboard_widget import MarketDashboardWidget
d = compute_dashboard()
print('data ok, n=%d' % d['breadth']['n_total'])
w = MarketDashboardWidget()
w.resize(1560, 980)
w._render(d)
w.show()
shot = r'D:\QuantMonitorV6\tools\_shot_dashboard.png'
def shoot():
    w.grab().save(shot)
    print('saved', shot, os.path.getsize(shot))
    app.quit()
QTimer.singleShot(500, shoot)
app.exec()
