# -*- coding: utf-8 -*-
"""动态实证：9:30 后 refresh() 到底有没有刷新"当前涨幅/当前价"列"""
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication
app = QApplication([])

from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget

w = AuctionFilterWidget()

# 造两条模拟"9:29 快照"结果
w._rows = [
    {'code': '600650', 'name': '锦江在线', 'score': 67.0, 'gap': 3.69,
     'cur_pct': 2.10, 'cur_price': 10.55, 'open': 10.69, 'theme_display': '在线旅游',
     'cur_time': '09:29:58', 'jj_amount_time': '09:29:58', 'jj_amount': 0.0},
    {'code': '002579', 'name': '中京电子', 'score': 65.0, 'gap': 3.44,
     'cur_pct': 5.10, 'cur_price': 19.55, 'open': 19.24, 'theme_display': 'PCB',
     'cur_time': '09:29:58', 'jj_amount_time': '09:29:58', 'jj_amount': 0.0},
]

calls = {'render': 0, 'rt': 0}
_orig_render = w._render_rows
_orig_rt = w._fetch_realtime_from_tencent


def fake_render():
    calls['render'] += 1
    _orig_render()


def fake_rt():
    calls['rt'] += 1


w._render_rows = fake_render
w._fetch_realtime_from_tencent = fake_rt

# 先完整渲染一次（模拟进入页面）
w._render_rows()
print('初始渲染后 _render_rows=%d _fetch_realtime=%d' % (calls['render'], calls['rt']))

# 记录渲染后的表格文字
print('  表格第4列(当前涨幅) =', repr(w.table.item(0, 4).text() if w.table.item(0, 4) else None))
print('  表格第6列(当前价)   =', repr(w.table.item(0, 6).text() if w.table.item(0, 6) else None))

calls['render'] = 0
calls['rt'] = 0

import datetime as _d
print()
print('=== 模拟 9:56（snapshot 阶段）连续 3 次 refresh() ===')
for n in range(3):
    w.refresh()
    print('  第%d次 refresh 后: _render_rows=%d  _fetch_realtime=%d'
          % (n + 1, calls['render'], calls['rt']))

print()
print('结论: 9:30 后 refresh() 调用 _render_rows 次数 = %d，调用实时行情次数 = %d'
      % (calls['render'], calls['rt']))
print('      表格第4列现在 =', repr(w.table.item(0, 4).text() if w.table.item(0, 4) else None))
print('      表格第6列现在 =', repr(w.table.item(0, 6).text() if w.table.item(0, 6) else None))
print('      → 列文字是否随行情变化:', '是' if calls['rt'] > 0 else '否（被冻结）')
