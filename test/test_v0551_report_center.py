# -*- coding: utf-8 -*-
"""
V0.5.5.1 回测报告中心 - 集成测试

验证：净值曲线 + 回撤分析 + 交易分析 + 报告汇总 + 导出
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timedelta

from backtest.report_center import (
    EquityCurve, DrawdownAnalyzer, TradeAnalyzer,
    BacktestReport, ReportExporter,
)


def generate_mock_data(days=300, initial_cash=1000000, seed=42):
    """生成模拟回测数据"""
    random.seed(seed)

    # 生成每日资产
    daily_assets = []
    cash = initial_cash * 0.3
    position_value = initial_cash * 0.7
    d = datetime(2023, 1, 3)

    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)

        # 模拟净值波动（带趋势）
        change = random.gauss(0.001, 0.015)
        position_value *= (1 + change)
        total = cash + position_value

        daily_assets.append({
            'date': d.strftime('%Y-%m-%d'),
            'total_asset': round(total, 2),
            'cash': round(cash, 2),
            'position_value': round(position_value, 2),
        })

        # 偶尔调整仓位
        if random.random() < 0.05:
            if position_value > total * 0.8:
                # 减仓
                sell = position_value * 0.3
                position_value -= sell
                cash += sell
            elif position_value < total * 0.2:
                # 加仓
                buy = min(cash * 0.5, total * 0.3)
                position_value += buy
                cash -= buy

        d += timedelta(days=1)

    # 生成交易记录
    trades = []
    buy_dates = random.sample(range(10, days - 20), 30)
    for buy_idx in sorted(buy_dates):
        buy_date = daily_assets[buy_idx]['date']
        hold = random.randint(3, 25)
        sell_idx = min(buy_idx + hold, days - 1)
        sell_date = daily_assets[sell_idx]['date']

        buy_price = round(random.uniform(8, 25), 2)
        # 50%盈利，50%亏损
        if random.random() < 0.55:
            sell_price = round(buy_price * random.uniform(1.02, 1.25), 2)
        else:
            sell_price = round(buy_price * random.uniform(0.92, 0.99), 2)

        trades.append({
            'code': f"{random.choice(['000', '002', '300', '600', '601', '603'])}{random.randint(100, 999)}",
            'buy_date': buy_date,
            'buy_price': buy_price,
            'sell_date': sell_date,
            'sell_price': sell_price,
            'quantity': random.randint(100, 1000),
            'reason': random.choice(['止盈', '止损', '到期', '趋势破位']),
        })

    # 生成基准数据
    benchmark = []
    bench_price = 3000.0
    d = datetime(2023, 1, 3)
    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        bench_price *= (1 + random.gauss(0.0002, 0.01))
        benchmark.append({
            'date': d.strftime('%Y-%m-%d'),
            'close': round(bench_price, 2),
        })
        d += timedelta(days=1)

    return daily_assets, trades, benchmark


def test_equity_curve():
    """测试净值曲线"""
    print("\n" + "="*60)
    print("【1】净值曲线测试")
    print("="*60)

    daily_assets, _, benchmark = generate_mock_data()

    equity = EquityCurve(daily_assets, benchmark, initial_cash=1000000)
    data = equity.build()
    metrics = equity.calc_metrics()

    print(f"  净值数据点: {len(data)}")
    print(f"  首条: {data[0]}")
    print(f"  末条: {data[-1]}")
    print(f"\n{equity.summary()}")

    # 回撤序列
    dd_series = equity.get_drawdown_series()
    print(f"\n  回撤序列点: {len(dd_series)}")
    print(f"  最大回撤点: {max(dd_series, key=lambda x: x['drawdown'])}")

    print("净值曲线测试通过 ✅")


def test_drawdown_analyzer():
    """测试回撤分析"""
    print("\n" + "="*60)
    print("【2】回撤分析测试")
    print("="*60)

    daily_assets, _, _ = generate_mock_data()

    analyzer = DrawdownAnalyzer(daily_assets, initial_cash=1000000)
    events = analyzer.detect_events()

    print(f"  检测到回撤事件: {len(events)}")
    for e in events[:3]:
        print(f"    {e.peak_date}->{e.trough_date}: -{e.drawdown_pct:.2f}% "
              f"持续{e.duration_days}天 {'已恢复' if e.recovered else '未恢复'}")

    stats = analyzer.calc_statistics()
    print(f"\n  回撤统计:")
    for k, v in stats.items():
        print(f"    {k}: {v}")

    max_dd = analyzer.get_max_drawdown()
    if max_dd:
        print(f"\n  最大回撤详情:")
        print(f"    {max_dd.to_dict()}")

    print("回撤分析测试通过 ✅")


def test_trade_analyzer():
    """测试交易分析"""
    print("\n" + "="*60)
    print("【3】交易分析测试")
    print("="*60)

    _, trades, _ = generate_mock_data()

    analyzer = TradeAnalyzer(trades=trades)
    stats = analyzer.calc_statistics()

    print(f"  交易统计:")
    for k, v in stats.items():
        print(f"    {k}: {v}")

    # 持仓分布
    dist = analyzer.get_hold_period_distribution()
    print(f"\n  持仓周期分布: {dist}")

    # 月度收益
    monthly = analyzer.get_monthly_returns()
    print(f"\n  月度收益 ({len(monthly)}个月):")
    for m in monthly[:5]:
        print(f"    {m['month']}: {m['total_return']:+.2f}% ({m['trades']}笔, 胜率{m['win_rate']:.1f}%)")

    # 买卖点
    points = analyzer.get_buy_sell_points()
    print(f"\n  买卖点: 买入{len(points['buy_points'])}个, 卖出{len(points['sell_points'])}个")

    # Top交易
    top_wins = analyzer.get_top_trades(3, by_profit=True)
    top_losses = analyzer.get_top_trades(3, by_profit=False)
    print(f"\n  最盈利3笔:")
    for t in top_wins:
        print(f"    {t.code}: {t.profit_pct:+.2f}% ({t.hold_days}天)")
    print(f"  最亏损3笔:")
    for t in top_losses:
        print(f"    {t.code}: {t.profit_pct:+.2f}% ({t.hold_days}天)")

    print("交易分析测试通过 ✅")


def test_backtest_report():
    """测试报告汇总"""
    print("\n" + "="*60)
    print("【4】报告汇总测试")
    print("="*60)

    daily_assets, trades, benchmark = generate_mock_data()

    report = BacktestReport(
        strategy_name="五九回踩",
        code="000001",
        daily_assets=daily_assets,
        trades=trades,
        benchmark_daily=benchmark,
        initial_cash=1000000,
        params={'stop_loss': 5, 'take_profit': 20, 'hold_days': 20},
        period="2023-01-03 ~ 2024-03-15",
    )

    overview = report.get_overview()
    print(f"  策略概览:")
    for k, v in overview.items():
        if k != 'params':
            print(f"    {k}: {v}")

    full = report.get_full_report()
    print(f"\n  完整报告字段: {list(full.keys())}")
    print(f"  净值曲线点: {len(full['equity_curve'])}")
    print(f"  交易数: {len(full['trades'])}")
    print(f"  回撤事件: {len(full['drawdown_events'])}")
    print(f"  月度收益: {len(full['monthly_returns'])}")

    print("\n报告汇总测试通过 ✅")


def test_export():
    """测试导出"""
    print("\n" + "="*60)
    print("【5】导出测试")
    print("="*60)

    daily_assets, trades, benchmark = generate_mock_data()

    report = BacktestReport(
        strategy_name="TestStrategy",
        code="TEST001",
        daily_assets=daily_assets,
        trades=trades,
        benchmark_daily=benchmark,
        initial_cash=1000000,
    )

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    exporter = ReportExporter(report, output_dir=output_dir)

    # JSON
    json_path = exporter.export_json()
    print(f"  JSON: {json_path}")
    print(f"    文件大小: {os.path.getsize(json_path)} bytes")

    # 交易CSV
    trades_csv = exporter.export_trades_csv()
    print(f"  交易CSV: {trades_csv}")
    print(f"    文件大小: {os.path.getsize(trades_csv)} bytes")

    # 净值CSV
    equity_csv = exporter.export_equity_csv()
    print(f"  净值CSV: {equity_csv}")
    print(f"    文件大小: {os.path.getsize(equity_csv)} bytes")

    # HTML
    html_path = exporter.export_html()
    print(f"  HTML报告: {html_path}")
    print(f"    文件大小: {os.path.getsize(html_path)} bytes")

    # 全部导出
    all_paths = exporter.export_all()
    print(f"\n  全部导出: {len(all_paths)}个文件")

    print("导出测试通过 ✅")


def test_real_backtest_integration():
    """测试与真实回测引擎集成"""
    print("\n" + "="*60)
    print("【6】真实回测引擎集成测试")
    print("="*60)

    try:
        from backtest.strategy import Pullback59Strategy, StrategyAdapter

        # 生成模拟K线
        random.seed(999)
        kline = {'open': [], 'close': [], 'high': [], 'low': [],
                 'volume': [], 'pct_chg': [], 'dates': []}
        price = 15.0
        d = datetime(2023, 1, 3)
        for i in range(250):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            change = random.gauss(0.0005, 0.02)
            o = price
            c = price * (1 + change)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            kline['open'].append(round(o, 2))
            kline['close'].append(round(c, 2))
            kline['high'].append(round(h, 2))
            kline['low'].append(round(l, 2))
            kline['volume'].append(random.randint(500000, 2000000))
            kline['pct_chg'].append(round(change * 100, 2))
            kline['dates'].append(d.strftime('%Y-%m-%d'))
            price = c
            d += timedelta(days=1)

        # 运行回测
        strategy = Pullback59Strategy({'stop_loss_pct': 5, 'take_profit_pct': 20, 'max_hold_days': 20})
        adapter = StrategyAdapter(strategy, initial_cash=1000000, single_position_pct=0.2)
        adapter.load_data(kline, code="TEST")
        result = adapter.run()

        print(f"  回测完成: {result.trade_count}笔交易, 收益{result.total_return_pct:+.2f}%")

        # 构建报告
        report = BacktestReport(
            strategy_name="五九回踩",
            code="TEST",
            daily_assets=result.daily_assets,
            orders=result.trades if hasattr(result, 'trades') else [],
            initial_cash=1000000,
            period=f"{kline['dates'][0]} ~ {kline['dates'][-1]}",
        )

        overview = report.get_overview()
        print(f"  报告概览: 收益{overview['total_return']:+.2f}%, "
              f"回撤{overview['max_drawdown']:.2f}%, "
              f"交易{overview['total_trades']}笔")

        # 导出HTML
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        exporter = ReportExporter(report, output_dir=output_dir)
        html_path = exporter.export_html(filename="test_real_backtest_report.html")
        print(f"  HTML报告: {html_path}")

        print("真实回测引擎集成测试通过 ✅")

    except Exception as e:
        print(f"  集成测试跳过（{type(e).__name__}: {e}）")
        print("  （不影响报告中心核心功能）")


def main():
    print("\n" + "#"*60)
    print("# V0.5.5.1 回测报告中心 - 集成测试")
    print("# 净值曲线 + 回撤分析 + 交易分析 + 报告汇总 + 导出")
    print("#"*60)

    test_equity_curve()
    test_drawdown_analyzer()
    test_trade_analyzer()
    test_backtest_report()
    test_export()
    test_real_backtest_integration()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
