# -*- coding: utf-8 -*-
"""端到端验证：实跑补丁后的 _daily_fetch_and_calc，看现价/涨跌幅是否变成实时值"""
import os, sys, datetime
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from ui.battle_widgets.atr_t_widget import AtrTWidget
w = AtrTWidget()
print('控件创建成功:', type(w).__name__)
print()

print('=== 调用补丁后的 _daily_fetch_and_calc() ===')
t0 = datetime.datetime.now()
rows = w._daily_fetch_and_calc()
dt = (datetime.datetime.now() - t0).total_seconds()
print('返回行数: %d   耗时 %.2f 秒' % (len(rows), dt))
print('_daily_rt_stat =', getattr(w, '_daily_rt_stat', None))
print()

print('=== 前 8 行：表格将显示的值 vs 接口实时值 ===')
codes = [r['code'] for r in rows[:8]]
from utils.http_market_data import get_realtime_quotes_http
q = get_realtime_quotes_http(codes) or {}
print('%-8s %-8s | %-22s | %-22s | %s' % ('代码', '名称', '表格显示(补丁后)', '接口实时', '一致'))
print('-' * 98)
bad = 0
for r in rows[:8]:
    c = r['code']
    v = q.get(c) or {}
    rt_p = float(v.get('price') or 0)
    rt_pct = float(v.get('pct_chg') or 0)
    same = abs(r['price'] - rt_p) < 0.005 and abs(r['pct'] - rt_pct) < 0.02
    if not same:
        bad += 1
    print('%-8s %-8s | %8.2f / %+7.2f%%     | %8.2f / %+7.2f%%     | %s'
          % (c, (r.get('name') or '')[:6], r['price'], r['pct'], rt_p, rt_pct,
             '一致' if same else '不一致'))
print()
print('抽样 8 只中不一致: %d 只' % bad)
print()
print('=== 对照：DB 里原来的 push_price（补丁前表格显示的就是它）===')
from services.band_pattern_engine import query_signals
db = {s['code']: s for s in (query_signals() or [])}
for r in rows[:8]:
    d = db.get(r['code']) or {}
    print('  %s %-8s DB原值 %8.2f / %+7.2f%%   ->  现在 %8.2f / %+7.2f%%'
          % (r['code'], (r.get('name') or '')[:6],
             d.get('push_price') or 0, d.get('push_pct') or 0,
             r['price'], r['pct']))
print()
print('=== 关键：拿不到实时价时是否保留 DB 原值（不置 0）===')
zero = [r for r in rows if not r['price']]
print('  价格为 0 的行数: %d  (应为 0)' % len(zero))
print()
print('=== 表头列顺序确认 ===')
from ui.battle_widgets.atr_t_widget import HEADER_DAILY
print(' ', HEADER_DAILY)
print('  现价列 index=2, 涨跌幅列 index=3 -> 渲染用 r["price"] / r["pct"]')
