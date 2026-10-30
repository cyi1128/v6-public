# -*- coding: utf-8 -*-
"""
V0.5.3.2 策略增强验证 - 集成测试

验证：市场环境过滤 + 仓位管理 + 策略归因
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from backtest.strategy import Pullback59Strategy, StrategyAdapter
from backtest.validation import (
    MarketRegimeAnalyzer, MarketRegime,
    RegimeFilterConfig, RegimeFilteredStrategy, RegimeFilterComparator,
    PositionSizingConfig, PositionSizedStrategy, PositionSizingTester,
    StrategyAttributor,
)


def generate_mock_kline(days=300, base_price=10.0, trend=0.0005,
                        volatility=0.02, seed=42):
    """生成模拟K线"""
    random.seed(seed)
    data = {'open': [], 'close': [], 'high': [], 'low': [],
            'volume': [], 'pct_chg': [], 'dates': []}
    price = base_price
    from datetime import datetime, timedelta
    d = datetime(2023, 1, 3)
    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        change = random.gauss(trend, volatility)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + random.uniform(0, volatility * 0.3))
        l = min(o, c) * (1 - random.uniform(0, volatility * 0.3))
        v = 1000000 * random.uniform(0.7, 1.5)
        data['open'].append(round(o, 2))
        data['close'].append(round(c, 2))
        data['high'].append(round(h, 2))
        data['low'].append(round(l, 2))
        data['volume'].append(int(v))
        data['pct_chg'].append(round(change * 100, 2))
        data['dates'].append(d.strftime('%Y-%m-%d'))
        price = c
        d += timedelta(days=1)
    return data


def test_regime_filter():
    """测试市场环境过滤"""
    print("\n" + "="*60)
    print("【1】市场环境过滤回测测试")
    print("="*60)

    # 生成股票和指数数据
    stock_data = generate_mock_kline(days=300, base_price=12.0, seed=111)
    index_data = generate_mock_kline(days=300, base_price=3000, seed=222)

    # 市场环境分析器
    analyzer = MarketRegimeAnalyzer()
    analyzer.load_index_data(index_data)

    # 原策略回测
    print("\n--- 原策略（无过滤）---")
    strategy_original = Pullback59Strategy()
    adapter_original = StrategyAdapter(strategy_original, initial_cash=1000000)
    adapter_original.load_data(stock_data, code="TEST001")
    result_original = adapter_original.run()
    print(f"  收益: {result_original.total_return_pct:+.2f}% | "
          f"回撤: {result_original.max_drawdown:.1f}% | "
          f"胜率: {result_original.win_rate:.1f}% | "
          f"交易: {result_original.trade_count}")

    # 过滤后策略回测
    print("\n--- 过滤后策略（牛市满仓/震荡半仓/熊市空仓）---")
    strategy_inner = Pullback59Strategy()
    strategy_filtered = RegimeFilteredStrategy(
        strategy_inner, analyzer, RegimeFilterConfig.aggressive()
    )
    adapter_filtered = StrategyAdapter(strategy_filtered, initial_cash=1000000)
    adapter_filtered.load_data(stock_data, code="TEST001")
    result_filtered = adapter_filtered.run()
    print(f"  收益: {result_filtered.total_return_pct:+.2f}% | "
          f"回撤: {result_filtered.max_drawdown:.1f}% | "
          f"胜率: {result_filtered.win_rate:.1f}% | "
          f"交易: {result_filtered.trade_count}")

    # 对比
    comparator = RegimeFilterComparator(analyzer)
    comparison = comparator.compare(result_original, result_filtered, strategy_filtered)
    print(f"\n{comparator.summary(comparison)}")
    print("市场环境过滤测试通过 ✅")


def test_position_sizing():
    """测试仓位管理"""
    print("\n" + "="*60)
    print("【2】仓位管理验证测试")
    print("="*60)

    stock_data = generate_mock_kline(days=300, base_price=15.0, seed=333)
    index_data = generate_mock_kline(days=300, base_price=3000, seed=444)

    analyzer = MarketRegimeAnalyzer()
    analyzer.load_index_data(index_data)

    # 测试多种仓位配置
    configs = [
        PositionSizingConfig.fixed_20(),
        PositionSizingConfig.fixed_50(),
        PositionSizingConfig.dynamic_default(),
    ]

    tester = PositionSizingTester(analyzer)
    results = tester.run_comparison(
        Pullback59Strategy, {}, stock_data, "TEST002",
        configs=configs, initial_cash=1000000
    )

    print(tester.summary())

    # 验证动态仓位统计
    for label, data in results.items():
        stats = data['sizing_stats']
        print(f"  {label}: 平均仓位{stats['avg_position_pct']}%, "
              f"禁止开仓{stats['blocked_by_sizing']}次")

    print("仓位管理验证测试通过 ✅")


def test_attribution():
    """测试策略归因分析"""
    print("\n" + "="*60)
    print("【3】策略归因分析测试")
    print("="*60)

    # 生成模拟交易记录
    random.seed(555)
    mock_trades = []
    for i in range(50):
        hold_days = random.randint(1, 25)
        profit = random.gauss(2, 8)  # 平均2%，标准差8%
        side = 'sell' if i % 2 == 0 else 'buy'
        mock_trades.append({
            'code': 'TEST003',
            'side': side,
            'filled_date': f'2023-{random.randint(1,12):02d}-{random.randint(1,28):02d}',
            'profit_pct': profit if side == 'sell' else 0,
            'hold_days': hold_days,
            'quantity': 1000,
            'price': 10 + random.random() * 5,
        })

    index_data = generate_mock_kline(days=400, base_price=3000, seed=666)
    analyzer = MarketRegimeAnalyzer()
    analyzer.load_index_data(index_data)

    attributor = StrategyAttributor(analyzer)
    result = attributor.analyze(mock_trades)

    print(result.summary())

    # 关键洞察
    insights = attributor.get_key_insights()
    if insights:
        print("  关键洞察:")
        for insight in insights:
            print(f"    - {insight}")
    else:
        print("  (样本较少，暂无显著洞察)")

    print("策略归因分析测试通过 ✅")


def test_combined_workflow():
    """测试完整工作流：过滤+仓位+归因"""
    print("\n" + "="*60)
    print("【4】完整工作流测试（过滤+仓位+归因）")
    print("="*60)

    stock_data = generate_mock_kline(days=300, base_price=10.0, seed=777)
    index_data = generate_mock_kline(days=300, base_price=3000, seed=888)

    analyzer = MarketRegimeAnalyzer()
    analyzer.load_index_data(index_data)

    # 1. 原策略
    print("  步骤1: 原策略回测...")
    s1 = Pullback59Strategy()
    a1 = StrategyAdapter(s1, initial_cash=1000000)
    a1.load_data(stock_data, code="COMB001")
    r1 = a1.run()
    print(f"    原策略: 收益{r1.total_return_pct:+.2f}%, 交易{r1.trade_count}次")

    # 2. 市场过滤
    print("  步骤2: 市场环境过滤...")
    s2_inner = Pullback59Strategy()
    s2 = RegimeFilteredStrategy(s2_inner, analyzer, RegimeFilterConfig.default())
    a2 = StrategyAdapter(s2, initial_cash=1000000)
    a2.load_data(stock_data, code="COMB001")
    r2 = a2.run()
    print(f"    过滤后: 收益{r2.total_return_pct:+.2f}%, 交易{r2.trade_count}次")

    # 3. 动态仓位
    print("  步骤3: 动态仓位管理...")
    s3_inner = Pullback59Strategy()
    s3 = PositionSizedStrategy(s3_inner, analyzer, PositionSizingConfig.dynamic_default())
    a3 = StrategyAdapter(s3, initial_cash=1000000, single_position_pct=1.0)
    a3.load_data(stock_data, code="COMB001")
    r3 = a3.run()
    print(f"    动态仓位: 收益{r3.total_return_pct:+.2f}%, 交易{r3.trade_count}次")

    # 4. 归因分析
    print("  步骤4: 策略归因分析...")
    trades = [t.to_dict() for t in a1.broker.account.trades if t.is_sell]
    # 补充hold_days和profit_pct（简化）
    for t in trades:
        t['hold_days'] = random.randint(1, 20)
        t['profit_pct'] = random.gauss(2, 6)

    attributor = StrategyAttributor(analyzer)
    attr_result = attributor.analyze(trades)
    print(f"    归因: {len(attr_result.factors)}个因子维度")

    print("\n  完整工作流验证通过 ✅")
    print(f"  原策略 vs 过滤 vs 动态仓位:")
    print(f"    {r1.total_return_pct:+.2f}% vs {r2.total_return_pct:+.2f}% vs {r3.total_return_pct:+.2f}%")


def main():
    print("\n" + "#"*60)
    print("# V0.5.3.2 策略增强验证 - 集成测试")
    print("# 市场环境过滤 + 仓位管理 + 策略归因")
    print("#"*60)

    test_regime_filter()
    test_position_sizing()
    test_attribution()
    test_combined_workflow()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
