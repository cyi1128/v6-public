# -*- coding: utf-8 -*-
"""调试：为什么有买入信号但没有成交"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import pandas as pd
from backtest.strategy import Pullback59Strategy, StrategyAdapter
from backtest.engine.broker import Broker
from backtest.engine.order import Order, OrderSide, OrderType, OrderStatus


def generate_simple_kline(days=50):
    """生成简单上涨K线"""
    random.seed(42)
    data = {'open': [], 'close': [], 'high': [], 'low': [],
            'volume': [], 'pct_chg': [], 'dates': []}
    price = 10.0
    from datetime import datetime, timedelta
    d = datetime(2023, 1, 3)
    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        change = random.gauss(0.002, 0.015)
        o = price
        c = price * (1 + change)
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        v = 1000000 * random.uniform(0.8, 1.2)
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


# 测试1：直接测试Broker买入流程
print("="*60)
print("测试1：Broker直接买入测试")
print("="*60)
broker = Broker(initial_cash=1000000, max_positions=1, single_position_pct=0.95)
print(f"初始资金: {broker.account.cash}")

# 提交买入订单
order = broker.buy("000001", 1000, price=10.0, date="2023-01-03", reason="测试")
print(f"提交订单: {order}")
print(f"待处理订单数: {len(broker.pending_orders)}")

# 执行订单
bar_data = {"000001": {"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1,
                        "pre_close": 9.95, "volume": 1000000}}
broker.execute_pending(bar_data, "2023-01-04")
print(f"执行后待处理: {len(broker.pending_orders)}")
print(f"成交记录: {len(broker.account.trades)}")
pos = broker.get_position("000001")
if pos:
    print(f"持仓: {pos.quantity}股, 成本={pos.avg_cost}")
print(f"剩余资金: {broker.account.cash}")


# 测试2：StrategyAdapter流程调试
print("\n" + "="*60)
print("测试2：StrategyAdapter流程调试")
print("="*60)
mock = generate_simple_kline(days=50)
strategy = Pullback59Strategy()
adapter = StrategyAdapter(strategy, initial_cash=1000000)
adapter.load_data(mock, code="TEST001")

# 手动模拟前10bar
df = adapter._kline_df
print(f"数据行数: {len(df)}")

for i in range(min(15, len(df))):
    date = str(df.iloc[i]['date'])
    bar_data = adapter._get_bar_data(df, i)

    # 执行pending
    adapter.broker.execute_pending(bar_data, date)

    # 更新context
    ctx = adapter.context = type(adapter.context)("TEST001", df, index=i)
    pos = adapter.broker.get_position("TEST001")
    from backtest.strategy.context import PositionInfo
    ctx.update_account(
        cash=adapter.broker.account.cash,
        total_asset=adapter.broker.account.total_asset,
        position=PositionInfo("TEST001", pos.quantity if pos else 0,
                              pos.avg_cost if pos else 0,
                              pos.available_qty if pos else 0),
    )

    # 策略信号
    signal = strategy.on_bar(ctx)

    if signal.is_buy:
        print(f"  [{i}] {date}: 买入信号 score={signal.score}")
        # 手动提交
        current_price = df.iloc[i]['close']
        max_amount = adapter.broker.account.total_asset * 0.95
        qty = int(max_amount / current_price / 100) * 100
        print(f"    计算数量: {qty}股, 价格={current_price}, 金额={qty*current_price:.0f}")
        order = adapter.broker.buy("TEST001", qty, price=current_price, date=date)
        if order:
            print(f"    订单已提交: status={order.status}")
        else:
            print(f"    订单被拒绝!")

    # 检查成交
    if len(adapter.broker.account.trades) > 0:
        last_trade = adapter.broker.account.trades[-1]
        print(f"  [{i}] {date}: 成交! {last_trade.side} {last_trade.quantity}股 @ {last_trade.filled_price}")

print(f"\n最终成交数: {len(adapter.broker.account.trades)}")
print(f"最终持仓: {adapter.broker.get_position('TEST001')}")
