# -*- coding: utf-8 -*-
"""渲染三张版式图（可重跑）：标题栏 / 分时做T表(820px 半屏) / 我的自选表(945px 半屏)"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'tools')

from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
_f = r'C:\Windows\Fonts\msyh.ttc'
if os.path.exists(_f):
    _id = QFontDatabase.addApplicationFont(_f)
    if _id >= 0 and QFontDatabase.applicationFontFamilies(_id):
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(_id)[0], 9))

from ui.battle_widgets.atr_t_widget import AtrTWidget  # noqa: E402


def grab(widget, name):
    p = os.path.join(OUT, name)
    widget.grab().save(p)
    print('  ->', p, os.path.getsize(p), 'bytes')
    return p


w = AtrTWidget()
try:
    w.stop_refresh()
    w._daily_timer.stop()
except Exception:
    pass
w.resize(1600, 900)
w.show()
app.processEvents()
rows, _tr, _ow = w._fetch_and_calc()
w._on_hold_loaded((rows, _tr, _ow))
app.processEvents()

# 1) 标题栏整条（证明「添加个股」按钮没了，只剩 分时做T / 日K建仓 / 导出）
bar = w.grab()
bar.copy(0, 0, 900, min(60, bar.height())).save(os.path.join(OUT, '_shot_ui_title.png'))
print('  -> _shot_ui_title.png %d bytes' % os.path.getsize(os.path.join(OUT, '_shot_ui_title.png')))

# 2) 分时做T表：按你右半屏 820px 渲染
t = w.table
t.resize(820, 620)
app.processEvents()
w._fit_hold_columns()
app.processEvents()
grab(t, '_shot_ui_ttable.png')

# 3) 我的自选表：按你左半屏 945px 渲染
import ui.battle_widgets.watchlist_widget as WW  # noqa: E402

w2 = WW.WatchlistWidget()
w2.resize(945, 560)
w2.show()
app.processEvents()
app.processEvents()
t2 = w2.table
t2.resize(945, 500)
app.processEvents()
grab(t2, '_shot_ui_watch.png')
print('完成')
