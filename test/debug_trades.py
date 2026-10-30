# -*- coding: utf-8 -*-
"""调试交易统计"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import pandas as pd
from backtest.strategy import Pullback59Strategy, StrategyAdapter
from backtest.engine.order import OrderSide


def generate_mock_kline(days=200, base_price=10.0, seed=42):
    random.seed(seed)
    data = {'open': [], 'close': [], 'high': [], 'low': [],
            'volume': [], 'pct_chg': [], 'dates': []}
    price = base_price
    from datetime import datetime, timedelta
    d = datetime(2023, 1, 3)
    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        change = random.gauss(0.001, 0.02)
        o = price
        c = price * (1 + change)
        h = max(o, c) * 1.008
        l = min(o, c) * 0.992
        v = 1000000 * random.uniform(0.8, 1.5)
        data['open'].append(round(o, 2))
        data['close'].append(round(c, 2))
        data['high'].append(round(h, 2))
        data['low'].append(round(l, 2))
        data['volume'].append(int(v))
        data['pct_chg'].append(round(change*100, 2))
        data['dates'].append(d.strftime('%Y-%m-%d'))
        price = c
        d += timedelta(days=1)
    return data


mock = generate_mock_kline(days=200, base_price=12.0, seed=123)
strategy = Pullback59Strategy()
adapter = StrategyAdapter(strategy, initial_cash=1000000)
adapter.load_data(mock, code="DEBUG001")
result = adapter.run()

print(f"最终资产: {adapter.broker.account.total_asset:.0f}")
print(f"现金: {adapter.broker.account.cash:.0f}")
print(f"持仓数: {adapter.broker.account.position_count}")
print(f"account.trades数量: {len(adapter.broker.account.trades)}")

for i, t in enumerate(adapter.broker.account.trades):
    print(f"  交易#{i}: side={t.side} value={t.side.value} is_sell={t.is_sell} "
          f"qty={t.quantity} price={t.filled_price} status={t.status}")

print(f"\nbuy信号: {len([s for s in result.signals if s['action']=='BUY'])}")
print(f"sell信号: {len([s for s in result.signals if s['action']=='SELL'])}")
