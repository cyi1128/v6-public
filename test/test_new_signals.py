# -*- coding: utf-8 -*-
"""测试新增的4个五九回踩信号"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.kline_scanner import KlineScanner

scanner = KlineScanner()
print(f'支持信号数: {len(scanner.SIGNALS)}')
for key in ['low_5k', 'low_9k', 'close_5k', 'close_9k']:
    print(f'  {key}: {scanner.SIGNALS[key]["name"]}')

# 构造测试数据
closes = [9.5 + i * 0.01 for i in range(30)]
closes[-1] = 9.7
lows = [c - 0.1 for c in closes]
lows[-1] = 10.15
highs = [c + 0.1 for c in closes]
opens = [c - 0.05 for c in closes]
volumes = [1000000] * 30

kline_data = {'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes}
signals = scanner.scan(kline_data)
signal_names = [s['name'] for s in signals]
print(f'\n检测到信号: {signal_names}')

# 验证MA9计算
from utils.indicators import calc_ma_series
import pandas as pd
ma5 = calc_ma_series(closes, 5)
ma9 = calc_ma_series(closes, 9)
print(f'\nMA5最后值: {ma5.iloc[-1]:.3f}')
print(f'MA9最后值: {ma9.iloc[-1]:.3f}')
print(f'最低价: {lows[-1]:.2f}')
print(f'收盘价: {closes[-1]:.2f}')
print(f'low-MA5: {lows[-1] - ma5.iloc[-1]:.3f} (低价5k要求0.03~0.3)')
print(f'low-MA9: {lows[-1] - ma9.iloc[-1]:.3f} (低价9k要求0.1~0.4)')
print(f'close-MA5: {closes[-1] - ma5.iloc[-1]:.3f} (收盘5k要求-0.5~-0.1)')
print(f'close-MA9: {closes[-1] - ma9.iloc[-1]:.3f} (收盘9k要求-0.3~0.01)')

print('\n测试完成 ✅')
