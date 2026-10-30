# -*- coding: utf-8 -*-
"""竞价修复验证：语法/导入/漏斗/非交易日崩溃"""
import sys, os, io, datetime
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

print('=== 1) 语法检查 ===')
import py_compile
try:
    py_compile.compile(r'D:\QuantMonitorV6\ui\battle_widgets\auction_filter_widget.py', doraise=True)
    print('  编译通过')
except Exception as e:
    print('  编译失败:', e); sys.exit(1)

print()
print('=== 2) 导入 + 新方法 ===')
from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget as W
print('  _auction_stage 存在:', hasattr(W, '_auction_stage'))
print('  当前阶段:', W._auction_stage())
print()

print('=== 3) 实跑 _fetch_auction（应带 funnel） ===')
print('  时间:', datetime.datetime.now().strftime('%H:%M:%S'))
r = W._fetch_auction()
print('  note   :', r.get('note'))
print('  funnel :', r.get('funnel'))
rows = r.get('rows') or []
print('  rows   :', len(rows))
for x in rows[:8]:
    print('     %s %-6s gap=%.2f%% 现价=%.2f MA20=%.2f 分=%.1f' % (
        x['code'], x['name'][:6], x['gap'], x['price'], x.get('ma20') or 0, x.get('score', 0)))
print()

print('=== 4) 非交易日分支（原 UnboundLocalError） ===')
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
try:
    w = W()
    from ui.battle_widgets import auction_filter_widget as M
    # 伪造：非交易日 + _rows 已有数据（原代码此处 latest 未定义 -> 崩溃）
    M._trade_cal.is_trading_day = lambda *a, **k: False
    w._rows = [{'code': '600000', 'name': '测试股', 'score': 50, 'gap': 3.0,
                'open': 10.0, 'price': 10.0, 'cur_pct': 3.0, 'cur_price': 10.0,
                'cur_time': '09:26:00', 'jj_amount_time': '09:26:00',
                'theme_display': '--'}]
    w.refresh()
    print('  refresh() 未抛异常 -> 修复生效')
    print('  标题:', w.title_label.text())
except Exception as e:
    import traceback
    print('  仍抛异常:', type(e).__name__, e)
    traceback.print_exc()
print()

print('=== 5) 非交易日 + _rows 为空 ===')
try:
    w2 = W()
    w2._rows = []
    w2.refresh()
    print('  未抛异常; 标题:', w2.title_label.text())
except Exception as e:
    print('  抛异常:', type(e).__name__, e)
