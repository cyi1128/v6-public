# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.kline_scanner import KlineScanner

s = KlineScanner()

# 测试买入信号：确保30个元素
# 前27天平稳，第28天冲高，第29天长下影，第30天确认上涨
closes = [10.0]*27 + [13.0, 12.79, 12.8]
lows = [9.9]*27 + [12.5, 12.39, 12.5]
highs = [c+0.1 for c in closes]
opens = [c-0.05 for c in closes]
volumes = [1000000]*30
kline = {'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes}

print(f'closes长度: {len(closes)}')
print(f'前一天: close={closes[-2]}, low={lows[-2]}, 下影线={closes[-2]-lows[-2]:.2f}')
print(f'今天: close={closes[-1]}, low={lows[-1]}')
print(f'今天收盘>前一天: {closes[-1] > closes[-2]}')
print(f'今天最低>=前一天最低: {lows[-1] >= lows[-2]}')

signals = s.scan(kline)
names = [sig['name'] for sig in signals]
print(f'\n检测到信号: {names}')
print(f'买入是否触发: {"买入" in names}')

if '买入' in names:
    for sig in signals:
        if sig['name'] == '买入':
            print(f'买入信号描述: {sig["desc"]}')

print('\n测试完成 ✅')
