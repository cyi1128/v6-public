# -*- coding: utf-8 -*-
"""测试新增的59线和平行5信号"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.kline_scanner import KlineScanner

scanner = KlineScanner()
print(f'支持信号数: {len(scanner.SIGNALS)}')
for key in ['line_59', 'parallel_5']:
    print(f'  {key}: {scanner.SIGNALS[key]["name"]}')

# 测试59线信号：构造连续2天温和调整+放量+一阳穿五九
# 前2天每天跌幅<0.5元，今天放量阳线突破MA5/MA9
closes = [10.0, 9.8, 9.6, 9.5, 9.45, 9.4, 9.35, 9.3, 9.25, 9.2,
          9.25, 9.3, 9.35, 9.4, 9.45, 9.5, 9.55, 9.6, 9.65, 9.7,
          9.65, 9.6, 9.55, 9.5, 9.45, 9.4, 9.35, 9.3, 9.25, 9.5]
# 最后一天：9.5（阳线，突破MA5约9.35和MA9约9.4）
# 前2天：9.3->9.25（跌0.05），9.25->9.5（今天涨）
# 等等，需要前2天都是温和调整（跌幅<=0.5）
# 倒数第3天9.3, 倒数第2天9.25(跌0.05), 倒数第1天9.5(涨)
# 但条件是"连续≥2个交易日温和调整"，应该是调整期的2天，然后今天突破
# 让我重新构造：调整期2天，今天突破
# day-3: 9.5, day-2: 9.45(跌0.05), day-1: 9.4(跌0.05), day0: 9.6(涨突破)
closes = [10.0, 9.9, 9.8, 9.7, 9.6, 9.5, 9.45, 9.4, 9.35, 9.3,
          9.35, 9.4, 9.45, 9.5, 9.55, 9.6, 9.65, 9.7, 9.75, 9.8,
          9.75, 9.7, 9.65, 9.6, 9.55, 9.5, 9.45, 9.4, 9.35, 9.6]
lows = [c - 0.05 for c in closes]
highs = [c + 0.1 for c in closes]
opens = [c - 0.02 for c in closes]
opens[-1] = 9.35  # 今天开盘9.35，收盘9.6，阳线
volumes = [1000000] * 30
volumes[-1] = 2500000  # 今天放量

kline_data = {'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes}
signals = scanner.scan(kline_data, turnover=1.5)
signal_names = [s['name'] for s in signals]
print(f'\n59线测试 - 检测到信号: {signal_names}')
print(f'  59线是否触发: {"59线" in signal_names}')

# 验证MA值
from utils.indicators import calc_ma_series
import pandas as pd
ma5 = calc_ma_series(closes, 5)
ma9 = calc_ma_series(closes, 9)
print(f'  MA5={ma5.iloc[-1]:.3f}, MA9={ma9.iloc[-1]:.3f}')
print(f'  收盘={closes[-1]:.2f}, 开盘={opens[-1]:.2f}')
print(f'  前2天跌幅: day-2={closes[-2]-closes[-3]:.3f}, day-1={closes[-1]-closes[-2]:.3f}')

# 测试平行5信号：前一天收盘>今天，今天接近MA5
closes2 = [10.0, 9.9, 9.8, 9.7, 9.6, 9.5, 9.45, 9.4, 9.35, 9.3,
           9.35, 9.4, 9.45, 9.5, 9.55, 9.6, 9.65, 9.7, 9.75, 9.8,
           9.75, 9.7, 9.65, 9.6, 9.55, 9.5, 9.45, 9.5, 9.55, 9.52]
# 前一天9.55 > 今天9.52，今天MA5约9.5，相差0.02
lows2 = [c - 0.05 for c in closes2]
highs2 = [c + 0.1 for c in closes2]
opens2 = [c - 0.02 for c in closes2]
volumes2 = [1000000] * 30

kline_data2 = {'open': opens2, 'high': highs2, 'low': lows2, 'close': closes2, 'volume': volumes2}
signals2 = scanner.scan(kline_data2)
signal_names2 = [s['name'] for s in signals2]
print(f'\n平行5测试 - 检测到信号: {signal_names2}')
print(f'  平行5是否触发: {"平行5" in signal_names2}')
ma5_2 = calc_ma_series(closes2, 5)
print(f'  MA5={ma5_2.iloc[-1]:.3f}, 收盘={closes2[-1]:.2f}, 差={closes2[-1]-ma5_2.iloc[-1]:.3f}')
print(f'  前一天收盘={closes2[-2]:.2f} > 今天={closes2[-1]:.2f}: {closes2[-2] > closes2[-1]}')

print('\n所有测试完成 ✅')
