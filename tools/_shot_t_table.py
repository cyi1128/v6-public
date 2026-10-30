# -*- coding: utf-8 -*-
"""走 UI 同一条路径取数+渲染分时做T表 → tools\\_shot_t_table.png（只读）"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'tools', '_shot_t_table.png')

from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
fam = ''
for f in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
    if os.path.exists(f):
        fid = QFontDatabase.addApplicationFont(f)
        if fid >= 0 and QFontDatabase.applicationFontFamilies(fid):
            fam = QFontDatabase.applicationFontFamilies(fid)[0]
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

src = w._get_holdings_source()
print('持仓来源行数 =', len(src), '｜前3:', [(x['code'], x['cost']) for x in src[:3]])

rows, _tr, _ow = w._fetch_and_calc()   # UI 同一条取数路径（含引擎判定）
print('取数完成 =', len(rows))
w._on_hold_loaded((rows, _tr, _ow))
app.processEvents()
tb = w.table
print('表行数 =', tb.rowCount() if tb is not None else 'n/a')
n_cost = len([r for r in (rows or []) if r.get('cost')])
print('其中带真实成本的 =', n_cost, '只')
for r in (rows or [])[:5]:
    print('   %s %-6s 现价 %-8s 成本 %-9s 偏离 %-8s 信号 %s' % (
        r.get('code'), r.get('name'), r.get('price'), r.get('cost'),
        r.get('cost_dev_pct'), r.get('signal_text') or r.get('signal_level')))
if tb is not None:
    w.resize(1780, 620)
    w.show()
    app.processEvents()
    w.grab().save(OUT)
    print('持仓表截图 ->', OUT, os.path.getsize(OUT), 'bytes')
