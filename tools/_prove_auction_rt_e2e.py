# -*- coding: utf-8 -*-
"""端到端实证：竞价结束后 refresh() 能否把真实行情写进表格

用真实腾讯行情接口，不替换任何函数。
"""
import os, sys, time
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication
app = QApplication([])

from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget

w = AuctionFilterWidget()

# 故意塞入 9:29 的"死数据"
STALE = {'cur_pct': 2.10, 'cur_price': 10.55}
w._rows = [
    {'code': '600650', 'name': '锦江在线', 'score': 67.0, 'gap': 3.69,
     'cur_pct': STALE['cur_pct'], 'cur_price': STALE['cur_price'], 'open': 10.69,
     'theme_display': '在线旅游', 'cur_time': '09:29:58',
     'jj_amount_time': '09:29:58', 'jj_amount': 0.0},
    {'code': '600358', 'name': '国旅联合', 'score': 66.0, 'gap': 3.46,
     'cur_pct': 3.46, 'cur_price': 5.38, 'open': 5.38,
     'theme_display': '旅游酒店', 'cur_time': '09:29:58',
     'jj_amount_time': '09:29:58', 'jj_amount': 0.0},
    {'code': '002579', 'name': '中京电子', 'score': 65.0, 'gap': 3.44,
     'cur_pct': 3.44, 'cur_price': 19.24, 'open': 19.24,
     'theme_display': 'PCB', 'cur_time': '09:29:58',
     'jj_amount_time': '09:29:58', 'jj_amount': 0.0},
]


def dump(tag):
    print('  %s:' % tag)
    for i in range(w.table.rowCount()):
        n = w.table.item(i, 0).text() if w.table.item(i, 0) else '?'
        c = w.table.item(i, 1).text() if w.table.item(i, 1) else '?'
        p = w.table.item(i, 4).text() if w.table.item(i, 4) else '?'
        q = w.table.item(i, 6).text() if w.table.item(i, 6) else '?'
        r = w._rows[i]
        print('     %-6s %s  当前涨幅=%-16s 当前价=%-8s rt_live=%s'
              % (n, c, p, q, r.get('rt_live')))


print('=== 步骤1: 渲染（塞入 9:29 死数据） ===')
w._render_rows()
dump('渲染后')
print()

print('=== 步骤2: 模拟 9:56 调用 refresh()（snapshot 阶段） ===')
w.refresh()
# 跑 Qt 事件循环，等后台线程 + 信号回来
for _ in range(60):
    app.processEvents()
    time.sleep(0.05)
dump('refresh 后')
print()

print('=== 步骤3: 再等 2 秒让异步回调落地 ===')
for _ in range(40):
    app.processEvents()
    time.sleep(0.05)
dump('最终')
print()

# 对照：直接查真实行情
from utils.http_market_data import get_realtime_quotes_http
real = get_realtime_quotes_http(['600650', '600358', '002579'])
print('=== 对照：接口真实值 ===')
for c in ['600650', '600358', '002579']:
    v = real.get(c) or {}
    print('  %s 真实价=%s 真实涨幅=%s' % (c, v.get('price'), v.get('pct_chg')))

print()
ok = all(w._rows[i].get('rt_live') for i in range(len(w._rows)))
print('结论：行情是否已实时刷新 ->', '是' if ok else '否')
