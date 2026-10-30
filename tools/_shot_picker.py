# -*- coding: utf-8 -*-
"""渲染新版「从我的自选添加」弹窗 → tools\\_shot_picker.png（只读真实库，不改数据）
离屏平台缺中文字体，这里显式加载系统雅黑，否则中文会渲染成方块。"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'tools', '_shot_picker.png')
FONTS = [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\simsun.ttc']

from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTableWidget  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
fam = ''
for f in FONTS:
    if os.path.exists(f):
        fid = QFontDatabase.addApplicationFont(f)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            fam = fams[0]
            print('已加载字体:', f, '->', fam)
            break
if fam:
    app.setFont(QFont(fam, 9))

from ui.battle_widgets.atr_t_widget import AtrTWidget  # noqa: E402

w = AtrTWidget()
w.stop_refresh()
try:
    w._daily_timer.stop()
except Exception:
    pass
dlg = w._build_holding_dialog()
if fam:
    dlg.setFont(QFont(fam, 9))
dlg.resize(820, 470)
dlg.show()
app.processEvents()
dlg.grab().save(OUT)
lw = dlg.findChild(QTableWidget, 'lst_watch')
lh = dlg.findChild(QTableWidget, 'lst_holdings')
print('截图 ->', OUT, os.path.getsize(OUT), 'bytes')
print('左(自选) %d 行，第1行=%s/%s' % (
    lw.rowCount(), lw.item(0, 0).text() if lw.item(0, 0) else '', lw.item(0, 1).text() if lw.item(0, 1) else ''))
print('右(学习做T) %d 行: %s' % (lh.rowCount(), [
    (lh.item(i, 0).text(), lh.item(i, 2).text(), lh.item(i, 3).text()) for i in range(lh.rowCount())]))
