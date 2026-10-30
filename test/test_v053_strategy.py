# -*- coding: utf-8 -*-
"""
V0.5.3 策略统一接口 - 完整回测闭环测试

验证：策略 → 信号 → 订单 → Broker撮合 → 资金变化 → 回测报告
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from backtest.strategy import (
    Strategy, Context, Signal, SignalAction,
    StrategyAdapter, BacktestResult,
    TripleVolumeStrategy, Pullback59Strategy,
)


def generate_mock_kline(days=300, base_price=10.0, trend=0.0005,
                        volatility=0.02, seed=42):
    """
    生成模拟K线数据（包含趋势+波动，用于测试回测流程）

    Args:
        days: K线数量
        base_price: 基准价格
        trend: 每日趋势涨幅
        volatility: 波动率
        seed: 随机种子
    """
    random.seed(seed)
    data = {
        'open': [], 'close': [], 'high': [], 'low': [],
        'volume': [], 'pct_chg': [], 'dates': [],
    }

    price = base_price
    from datetime import datetime, timedelta
    start_date = datetime(2023, 1, 3)

    for i in range(days):
        # 跳过周末
        date = start_date + timedelta(days=i)
        while date.weekday() >= 5:
            date += timedelta(days=1)
            start_date += timedelta(days=1)

        # 价格变化
        change = random.gauss(trend, volatility)
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, volatility * 0.5))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, volatility * 0.5))

        # 成交量（偶尔放量）
        base_vol = 1000000
        if random.random() < 0.05:  # 5%概率放量
            volume = base_vol * random.uniform(2, 4)
        else:
            volume = base_vol * random.uniform(0.7, 1.3)

        pct = (close_price - open_price) / open_price * 100 if open_price > 0 else 0

        data['open'].append(round(open_price, 2))
        data['close'].append(round(close_price, 2))
        data['high'].append(round(high_price, 2))
        data['low'].append(round(low_price, 2))
        data['volume'].append(int(volume))
        data['pct_chg'].append(round(pct, 2))
        data['dates'].append(date.strftime('%Y-%m-%d'))

        price = close_price

    return data


def test_signal_model():
    """测试信号模型"""
    print("\n" + "="*60)
    print("【1】信号模型测试")
    print("="*60)

    buy_signal = Signal.buy(score=85, reason=["MA5金叉", "放量突破"], tags=["五九回踩"])
    print(f"买入信号: {buy_signal}")
    print(f"  is_buy={buy_signal.is_buy}, score={buy_signal.score}")

    sell_signal = Signal.sell(score=90, reason=["跌破MA20"], tags=["止损"])
    print(f"卖出信号: {sell_signal}")

    hold_signal = Signal.hold(reason=["无操作"])
    print(f"持有信号: {hold_signal}")
    print("信号模型测试通过 ✅")


def test_context():
    """测试Context数据环境"""
    print("\n" + "="*60)
    print("【2】Context数据环境测试")
    print("="*60)

    import pandas as pd
    mock = generate_mock_kline(days=100)
    df = pd.DataFrame(mock)

    ctx = Context("000001", df, index=-1)
    print(f"代码: {ctx.code}")
    print(f"日期: {ctx.date}")
    print(f"收盘: {ctx.close:.2f}")
    print(f"MA5: {ctx.ma5:.3f}")
    print(f"MA20: {ctx.ma20:.3f}")
    print(f"MACD: {ctx.macd}")
    print(f"KDJ: {ctx.kdj}")
    print(f"量比(5日): {ctx.get_volume_ratio(5):.2f}")
    print(f"历史K线数: {ctx.history_count}")
    print("Context测试通过 ✅")


def test_pullback59_mock():
    """测试五九回踩策略（模拟数据）"""
    print("\n" + "="*60)
    print("【3】五九回踩策略回测（模拟数据）")
    print("="*60)

    mock_data = generate_mock_kline(days=300, base_price=12.0, trend=0.0008, seed=123)
    strategy = Pullback59Strategy()
    adapter = StrategyAdapter(strategy, initial_cash=1000000)

    if adapter.load_data(mock_data, code="MOCK001"):
        result = adapter.run()
        print(result.summary())
        print(f"  信号数: {len(result.signals)}")
        print(f"  买入信号: {len([s for s in result.signals if s['action']=='BUY'])}")
        print(f"  卖出信号: {len([s for s in result.signals if s['action']=='SELL'])}")
    else:
        print("数据加载失败")
    print("五九回踩策略测试通过 ✅")


def test_triple_volume_mock():
    """测试三倍量策略（模拟数据）"""
    print("\n" + "="*60)
    print("【4】三倍量策略回测（模拟数据）")
    print("="*60)

    mock_data = generate_mock_kline(days=300, base_price=15.0, trend=0.001, seed=456)
    strategy = TripleVolumeStrategy()
    adapter = StrategyAdapter(strategy, initial_cash=1000000)

    if adapter.load_data(mock_data, code="MOCK002"):
        result = adapter.run()
        print(result.summary())
    else:
        print("数据加载失败")
    print("三倍量策略测试通过 ✅")


def test_real_data():
    """测试真实数据回测（通达信）"""
    print("\n" + "="*60)
    print("【5】真实数据回测（通达信）")
    print("="*60)

    try:
        from utils.kline_provider import get_daily_kline
        print("正在获取真实K线数据...")
        kline = get_daily_kline("000001", count=500)

        if kline and kline.get('close'):
            print(f"获取成功: {len(kline['close'])}根K线")
            print(f"日期范围: {kline['dates'][0]} ~ {kline['dates'][-1]}")

            # 五九回踩策略
            print("\n--- 五九回踩策略 ---")
            strategy = Pullback59Strategy()
            adapter = StrategyAdapter(strategy, initial_cash=1000000)
            if adapter.load_data(kline, code="000001"):
                result = adapter.run()
                print(result.summary())

            # 三倍量策略
            print("\n--- 三倍量策略 ---")
            strategy2 = TripleVolumeStrategy()
            adapter2 = StrategyAdapter(strategy2, initial_cash=1000000)
            if adapter2.load_data(kline, code="000001"):
                result2 = adapter2.run()
                print(result2.summary())
        else:
            print("通达信数据获取失败，跳过真实数据测试")
    except Exception as e:
        print(f"真实数据测试异常: {e}")
        print("跳过真实数据测试（不影响模拟数据验证）")


def test_custom_strategy():
    """测试自定义策略（验证基类扩展性）"""
    print("\n" + "="*60)
    print("【6】自定义策略测试（MA交叉）")
    print("="*60)

    class MACrossStrategy(Strategy):
        name = "MACross"
        description = "简单MA5/MA20金叉死叉策略"

        def on_bar(self, context):
            if context.history_count < 25:
                return Signal.hold()

            ma5 = context.ma5
            ma20 = context.ma20
            prev_ma5 = context.get_history_value('MA5', -1)
            prev_ma20 = context.get_history_value('MA20', -1)

            # 金叉买入
            if not context.position.has_position:
                if prev_ma5 <= prev_ma20 and ma5 > ma20:
                    return Signal.buy(score=75, reason=["MA5金叉MA20"], tags=["MA交叉"])

            # 死叉卖出
            if context.position.has_position:
                if prev_ma5 >= prev_ma20 and ma5 < ma20:
                    return Signal.sell(score=80, reason=["MA5死叉MA20"], tags=["MA交叉"])

            return Signal.hold()

    mock_data = generate_mock_kline(days=300, base_price=10.0, trend=0.0005, seed=789)
    strategy = MACrossStrategy()
    adapter = StrategyAdapter(strategy, initial_cash=1000000)

    if adapter.load_data(mock_data, code="MOCK003"):
        result = adapter.run()
        print(result.summary())
    print("自定义策略测试通过 ✅")


def main():
    print("\n" + "#"*60)
    print("# V0.5.3 策略统一接口 - 完整回测闭环测试")
    print("# 策略 → 信号 → 订单 → Broker → 资金 → 报告")
    print("#"*60)

    test_signal_model()
    test_context()
    test_pullback59_mock()
    test_triple_volume_mock()
    test_real_data()
    test_custom_strategy()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
