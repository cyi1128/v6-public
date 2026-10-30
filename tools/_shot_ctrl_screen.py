# -*- coding: utf-8 -*-
"""控盘选股页 真实数据截图（可重跑）。

用真实快照 data/cache/control_screen.json 渲染整页并抓图，供人工核对版式。
中文可读需要 QT_QPA_PLATFORM=windows（offscreen 无中文字体，中文会变方块）。
"""
import os
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication   # noqa: E402

from ui.battle_widgets.control_screen_widget import ControlScreenWidget   # noqa: E402

W = int(os.environ.get('SHOT_W', '1920'))
H = int(os.environ.get('SHOT_H', '900'))
OUT = os.environ.get('SHOT_OUT', r'D:\QuantMonitorV6\tools\_shot_ctrl_screen.png')


def main():
    app = QApplication.instance() or QApplication([])
    w = ControlScreenWidget()
    # 截图只要静态版式：关掉「打开页面自动扫描」，否则 show() 会真的起一个扫描线程，
    # 抓到的就是「扫描中 0%」而不是常态（2026-10-11 第一张就是这样）。
    try:
        w._ck_auto.setChecked(False)
    except Exception:
        pass
    # 补数开关也关掉：截图要保持离线（缓存已有的数据照样显示，只是不联网补缺项）
    try:
        w._ck_extra.setChecked(False)
    except Exception:
        pass
    w.resize(W, H)
    w.show()
    for _ in range(12):
        app.processEvents()
    print('表格行数=%d ｜ 统计条=%s' % (w.table.rowCount(), w._count_label.text()), flush=True)
    print('表头=%s' % [w.table.horizontalHeaderItem(i).text() for i in range(w.table.columnCount())],
          flush=True)
    for i in range(min(8, w.table.rowCount())):
        print('第%d行: %s' % (i, [w.table.item(i, c).text() if w.table.item(i, c) else None
                                 for c in range(w.table.columnCount())]), flush=True)
    pm = w.grab()
    ok = pm.save(OUT, 'PNG')
    print('截图保存=%s (%s) %dx%d' % (ok, OUT, pm.width(), pm.height()), flush=True)
    w.close()


if __name__ == '__main__':
    main()
