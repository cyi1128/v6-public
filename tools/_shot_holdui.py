# -*- coding: utf-8 -*-
"""截图：分时做T 标题栏的「➕ 添加个股」按钮（真字体渲染，可重跑）。

输出：tools\\_shot_hold_btn.png（整块控件）与 tools\\_shot_hold_btn_crop.png（标题栏放大）
"""
import os
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
from ui.battle_widgets.atr_t_widget import AtrTWidget  # noqa: E402

w = AtrTWidget()
w.resize(1500, 430)
w.stop_refresh()
try:
    w._daily_timer.stop()
except Exception:
    pass
w.show()


def _shoot():
    out = os.path.join(ROOT, 'tools', '_shot_hold_btn.png')
    pm = w.grab()
    pm.save(out)
    print('已保存', out, pm.width(), 'x', pm.height())
    # 标题栏局部放大（含按钮）
    bar = w._card_frame.layout().itemAt(0).layout()
    h = max(28, w._btn_add.height() + 6)
    crop = pm.copy(0, 0, min(1000, pm.width()), h)
    crop = crop.scaled(crop.width() * 2, crop.height() * 2)
    out2 = os.path.join(ROOT, 'tools', '_shot_hold_btn_crop.png')
    crop.save(out2)
    print('已保存', out2, crop.width(), 'x', crop.height())
def _shoot2():
    dlg = w._build_holding_dialog()
    dlg.resize(620, 450)
    dlg.show()
    QTimer.singleShot(700, lambda: _shoot3(dlg))


def _shoot3(dlg):
    out3 = os.path.join(ROOT, 'tools', '_shot_hold_dialog.png')
    pm = dlg.grab()
    pm.save(out3)
    print('已保存', out3, pm.width(), 'x', pm.height())
    print('弹窗标题 =', dlg.windowTitle())
    dlg.close()
    w.close()
    app.quit()


QTimer.singleShot(1500, _shoot)
QTimer.singleShot(2000, _shoot2)
app.exec()
