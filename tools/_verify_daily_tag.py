# -*- coding: utf-8 -*-
"""验证日K建仓标题：三种时段的实际输出"""
import os, sys, datetime as _dt
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

import ui.battle_widgets.atr_t_widget as M
w = M.AtrTWidget()

print('=== 1) 取数，检查 push_date 是否带上 ===')
rows = w._daily_fetch_and_calc()
print('行数:', len(rows))
print('前 3 行的 push_date:', [r.get('push_date') for r in rows[:3]])
dd = sorted({(r.get('push_date') or '') for r in rows})
print('push_date 全部取值:', dd)
print('最大值(将用于标题):', dd[-1] if dd else '(空)')
print()

w._tab_active = 1   # 模拟已切到「日K建仓」Tab


class FakeDT:
    """伪造 datetime，用于测试标题分支"""
    def __init__(self, y, mo, d, h, mi):
        self._d = _dt.datetime(y, mo, d, h, mi)
    @classmethod
    def now(cls):
        return cls._cur
    def weekday(self):
        return self._d.weekday()
    @property
    def hour(self):
        return self._d.hour
    @property
    def minute(self):
        return self._d.minute
    def strftime(self, f):
        return self._d.strftime(f)


_real = M.datetime
print('=== 2) 三种时段标题实际输出 ===')
cases = [
    ('盘中 周四 10:31', FakeDT(2026, 9, 24, 10, 31)),
    ('盘中 周四 14:20', FakeDT(2026, 9, 24, 14, 20)),
    ('盘后 周四 16:00', FakeDT(2026, 9, 24, 16, 0)),
    ('盘前 周四 09:00', FakeDT(2026, 9, 24, 9, 0)),
    ('休市 周六 10:00', FakeDT(2026, 9, 26, 10, 0)),
]
for label, fake in cases:
    FakeDT._cur = fake
    M.datetime = FakeDT
    w._daily_on_loaded(rows)
    print('  %-16s -> %s' % (label, w.title_label.text()))

M.datetime = _real
print()
print('=== 3) 无 push_date 时的兜底（应为不带"数据"的旧格式）===')
FakeDT._cur = FakeDT(2026, 9, 24, 10, 31)
M.datetime = FakeDT
_bak = [dict(r) for r in rows]
for r in rows:
    r.pop('push_date', None)
w._daily_on_loaded(rows)
print('  空 push_date -> %s' % w.title_label.text())
M.datetime = _real

print()
print('=== 4) 表格未被破坏 ===')
w._daily_on_loaded(_bak)
print('  表格行数:', w.daily_table.rowCount(), ' 列数:', w.daily_table.columnCount())
print('  表头:', [w.daily_table.horizontalHeaderItem(i).text()
                   for i in range(w.daily_table.columnCount())])
print('  首行现价/涨跌幅:', w.daily_table.item(0, 2).text(), w.daily_table.item(0, 3).text())
print()
print('=== 5) 源码里是否还残留"盘中监控"/"盘后复盘" ===')
import io
_s = io.open(r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py', encoding='utf-8').read()
print("  '盘中监控' 出现次数:", _s.count('盘中监控'))
print("  '盘后复盘' 出现次数:", _s.count('盘后复盘'))
