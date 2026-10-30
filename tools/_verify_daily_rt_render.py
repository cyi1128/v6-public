# -*- coding: utf-8 -*-
"""验证渲染层：调 _daily_on_loaded 后，表格单元格与状态栏的实际文本"""
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from ui.battle_widgets.atr_t_widget import AtrTWidget, HEADER_DAILY
w = AtrTWidget()

# 捕获 set_status 的入参
_status = []
_orig_set_status = w.set_status
def _cap(msg):
    _status.append(msg)
    return _orig_set_status(msg)
w.set_status = _cap

print('=== 后台取数 ===')
rows = w._daily_fetch_and_calc()
print('行数:', len(rows), ' _daily_rt_stat:', getattr(w, '_daily_rt_stat', None))
print()

print('=== 主线程渲染 _daily_on_loaded ===')
w._daily_on_loaded(rows)
print('表格行数:', w.daily_table.rowCount())
print('表格列数:', w.daily_table.columnCount(), ' 表头:', HEADER_DAILY)
print('标题:', w.title_label.text())
print('状态栏调用:', _status)
print()

print('=== 表格前 6 行的 现价/涨跌幅 单元格实际文本 ===')
print('%-8s %-8s %-10s %-10s %s' % ('名称', '代码', '现价列', '涨跌幅列', '结构状态'))
print('-' * 62)
for i in range(min(6, w.daily_table.rowCount())):
    def txt(col):
        it = w.daily_table.item(i, col)
        return it.text() if it else ''
    print('%-8s %-8s %-10s %-10s %s' % (txt(0), txt(1), txt(2), txt(3), txt(5)))
print()

print('=== 与接口实时值比对（表格实际显示）===')
codes = [r['code'] for r in rows[:6]]
from utils.http_market_data import get_realtime_quotes_http
q = get_realtime_quotes_http(codes) or {}
bad = 0
for i in range(min(6, w.daily_table.rowCount())):
    c = w.daily_table.item(i, 1).text()
    disp_p = w.daily_table.item(i, 2).text()
    disp_pct = w.daily_table.item(i, 3).text()
    v = q.get(c) or {}
    rt_p = float(v.get('price') or 0)
    ok = abs(float(disp_p) - rt_p) < 0.03
    if not ok:
        bad += 1
    print('  %s 表格=%s / %s   接口=%.2f / %+.2f%%   %s'
          % (c, disp_p, disp_pct, rt_p, float(v.get('pct_chg') or 0),
             '一致' if ok else '偏差(盘中跳动)'))
print()
print('偏差只数: %d / 6  (价格差>0.03 才算偏差)' % bad)
