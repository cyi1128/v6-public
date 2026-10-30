# -*- coding: utf-8 -*-
"""核对控盘选股页在主窗口里的挂载位置与跳转方法签名（一次性检查，只读）。"""
import io
import re

P = r'D:\QuantMonitorV6\ui\battle_console_v2.py'
lines = io.open(P, 'r', encoding='utf-8').read().split('\n')
defs = [(i + 1, t.strip()) for i, t in enumerate(lines) if re.match(r'\s{4}def ', t)]

print('包含 addTab(self.ctrl_screen_page) 的行:',
      [i + 1 for i, t in enumerate(lines) if 'tabs.addTab(self.ctrl_screen_page' in t])
print('包含 stock_clicked 连接的行:',
      [i + 1 for i, t in enumerate(lines) if 'ctrl_screen_page.stock_clicked' in t])
print('_show_stock_detail 定义:', [(n, t) for n, t in defs if '_show_stock_detail' in t])
print('_build_pages 定义行:', [n for n, t in defs if 'def _build_pages' in t])
_before1 = [(n, t) for n, t in defs if n < 6581]
print('6581 之前最近的方法:', _before1[-1] if _before1 else None)
_before2 = [(n, t) for n, t in defs if n < 6725]
print('6725 之前最近的方法:', _before2[-1] if _before2 else None)
print('_connect_signals 定义行:', [n for n, t in defs if 'def _connect_signals' in t])
# 控盘页是否只创建一次、是否在 _build_pages 内
print('ctrl_screen_page 出现次数:', sum(1 for t in lines if 'ctrl_screen_page' in t))
print('模块级是否有扫描副作用（import 即扫描）:',
      'scan_market(' in io.open(r'D:\QuantMonitorV6\ui\battle_widgets\control_screen_widget.py',
                                'r', encoding='utf-8').read().split('\n')[0:60].__str__())
