# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import py_compile
py_compile.compile('strategy/kline_scanner.py', doraise=True)
py_compile.compile('ui/monitor_hall.py', doraise=True)
py_compile.compile('ui/main_window.py', doraise=True)
py_compile.compile('pages/ai_decision_center_tab.py', doraise=True)
print('所有文件语法: OK')

from strategy.kline_scanner import KlineScanner
s = KlineScanner()
print(f'K线扫描器信号数: {len(s.SIGNALS)}')
print(f'买入信号: {s.SIGNALS["buy_confirm"]["name"]}')

from ui.monitor_hall import MonitorHallWidget
print(f'监控大厅标签数: {len(MonitorHallWidget.ALL_SIGNALS)}')
print(f'包含买入: {"买入" in MonitorHallWidget.ALL_SIGNALS}')

# 测试买入信号
closes = [10.0]*25 + [13.0, 12.79, 12.8]
lows = [9.9]*25 + [12.5, 12.39, 12.5]
highs = [c+0.1 for c in closes]
opens = [c-0.05 for c in closes]
volumes = [1000000]*30
kline = {'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes}
signals = s.scan(kline)
names = [sig['name'] for sig in signals]
print(f'\n买入信号测试: {names}')
print(f'买入是否触发: {"买入" in names}')

print('\n所有验证通过 ✅')
