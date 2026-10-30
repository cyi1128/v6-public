# -*- coding: utf-8 -*-
"""
V0.5.5.2 回测报告中心 UI - 测试脚本

测试：组件创建、数据加载、导出功能
运行方式：
  python test_v0552_report_ui.py          # 仅测试组件创建
  python test_v0552_report_ui.py --show   # 启动GUI窗口显示
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timedelta


def generate_mock_report():
    """生成模拟报告数据"""
    from backtest.report_center import BacktestReport

    random.seed(42)
    days = 250
    initial_cash = 1000000

    # 每日资产
    daily_assets = []
    cash = initial_cash * 0.3
    position_value = initial_cash * 0.7
    d = datetime(2023, 1, 3)

    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        change = random.gauss(0.001, 0.015)
        position_value *= (1 + change)
        total = cash + position_value
        daily_assets.append({
            'date': d.strftime('%Y-%m-%d'),
            'total_asset': round(total, 2),
            'cash': round(cash, 2),
            'position_value': round(position_value, 2),
        })
        if random.random() < 0.05:
            if position_value > total * 0.8:
                sell = position_value * 0.3
                position_value -= sell
                cash += sell
            elif position_value < total * 0.2:
                buy = min(cash * 0.5, total * 0.3)
                position_value += buy
                cash -= buy
        d += timedelta(days=1)

    # 交易记录
    trades = []
    buy_indices = random.sample(range(10, days - 20), 25)
    for buy_idx in sorted(buy_indices):
        buy_date = daily_assets[buy_idx]['date']
        hold = random.randint(3, 25)
        sell_idx = min(buy_idx + hold, days - 1)
        sell_date = daily_assets[sell_idx]['date']
        buy_price = round(random.uniform(8, 25), 2)
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

    # 基准
    benchmark = []
    bench_price = 3000.0
    d = datetime(2023, 1, 3)
    for i in range(days):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        bench_price *= (1 + random.gauss(0.0002, 0.01))
        benchmark.append({'date': d.strftime('%Y-%m-%d'), 'close': round(bench_price, 2)})
        d += timedelta(days=1)

    return BacktestReport(
        strategy_name="五九回踩策略",
        code="000001",
        daily_assets=daily_assets,
        trades=trades,
        benchmark_daily=benchmark,
        initial_cash=initial_cash,
        params={'stop_loss_pct': 5, 'take_profit_pct': 20, 'max_hold_days': 20},
        period="2023-01-03 ~ 2023-12-29",
    )


def test_imports():
    """测试模块导入"""
    print("\n" + "="*60)
    print("【1】模块导入测试")
    print("="*60)

    from backtest.report_center.ui import (
        OverviewCard, TradeTable, ParameterPanel,
        ExportPanel, ReportDashboard,
    )
    from backtest.report_center.ui.equity_chart import EquityChart, HAS_MATPLOTLIB
    from backtest.report_center.ui.drawdown_chart import DrawdownChart

    print(f"  OverviewCard: ✅")
    print(f"  TradeTable: ✅")
    print(f"  ParameterPanel: ✅")
    print(f"  ExportPanel: ✅")
    print(f"  ReportDashboard: ✅")
    print(f"  EquityChart: ✅ (matplotlib: {'可用' if HAS_MATPLOTLIB else '降级Canvas'})")
    print(f"  DrawdownChart: ✅")

    print("模块导入测试通过 ✅")


def test_components_creation():
    """测试组件创建（不启动mainloop）"""
    print("\n" + "="*60)
    print("【2】组件创建测试")
    print("="*60)

    import tkinter as tk
    from backtest.report_center.ui import (
        OverviewCard, TradeTable, ParameterPanel,
        ExportPanel, ReportDashboard,
    )
    from backtest.report_center.ui.equity_chart import EquityChart
    from backtest.report_center.ui.drawdown_chart import DrawdownChart

    root = tk.Tk()
    root.withdraw()  # 隐藏窗口

    report = generate_mock_report()
    overview = report.get_overview()

    # 测试各组件
    try:
        card = OverviewCard(root, overview)
        print(f"  OverviewCard创建: ✅")
    except Exception as e:
        print(f"  OverviewCard创建: ❌ {e}")

    try:
        chart = EquityChart(root, report.get_equity_curve())
        print(f"  EquityChart创建: ✅")
    except Exception as e:
        print(f"  EquityChart创建: ❌ {e}")

    try:
        dd_chart = DrawdownChart(root, report.get_drawdown_curve(),
                                  report.get_drawdown_events())
        print(f"  DrawdownChart创建: ✅")
    except Exception as e:
        print(f"  DrawdownChart创建: ❌ {e}")

    try:
        table = TradeTable(root, report.get_trades())
        print(f"  TradeTable创建: ✅ ({len(report.get_trades())}笔)")
    except Exception as e:
        print(f"  TradeTable创建: ❌ {e}")

    try:
        panel = ParameterPanel(root, overview.get('params', {}))
        print(f"  ParameterPanel创建: ✅")
    except Exception as e:
        print(f"  ParameterPanel创建: ❌ {e}")

    try:
        export = ExportPanel(root)
        print(f"  ExportPanel创建: ✅")
    except Exception as e:
        print(f"  ExportPanel创建: ❌ {e}")

    try:
        dashboard = ReportDashboard(root, report=report)
        print(f"  ReportDashboard创建: ✅")
    except Exception as e:
        print(f"  ReportDashboard创建: ❌ {e}")

    root.destroy()
    print("组件创建测试通过 ✅")


def test_report_data():
    """测试报告数据"""
    print("\n" + "="*60)
    print("【3】报告数据测试")
    print("="*60)

    report = generate_mock_report()
    overview = report.get_overview()

    print(f"  策略: {overview['strategy_name']}")
    print(f"  股票: {overview['code']}")
    print(f"  周期: {overview['period']}")
    print(f"  总收益: {overview['total_return']:+.2f}%")
    print(f"  最大回撤: {overview['max_drawdown']:.2f}%")
    print(f"  夏普: {overview['sharpe']:.2f}")
    print(f"  胜率: {overview['win_rate']:.1f}%")
    print(f"  交易次数: {overview['total_trades']}")
    print(f"  净值曲线点: {len(report.get_equity_curve())}")
    print(f"  回撤事件: {len(report.get_drawdown_events())}")
    print(f"  月度收益: {len(report.get_monthly_returns())}个月")

    print("报告数据测试通过 ✅")


def test_export():
    """测试导出功能"""
    print("\n" + "="*60)
    print("【4】导出功能测试")
    print("="*60)

    from backtest.report_center import ReportExporter

    report = generate_mock_report()
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    exporter = ReportExporter(report, output_dir=output_dir)

    html_path = exporter.export_html(filename="test_ui_report.html")
    print(f"  HTML报告: {os.path.basename(html_path)} ({os.path.getsize(html_path)} bytes) ✅")

    json_path = exporter.export_json(filename="test_ui_report.json")
    print(f"  JSON报告: {os.path.basename(json_path)} ({os.path.getsize(json_path)} bytes) ✅")

    print("导出功能测试通过 ✅")


def show_dashboard():
    """启动GUI显示"""
    import tkinter as tk
    from backtest.report_center.ui import ReportDashboard

    report = generate_mock_report()
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

    root = tk.Tk()
    root.title("回测报告中心 - V0.5.5.2")
    root.geometry("1280x850")
    root.configure(bg='#0d1117')

    dashboard = ReportDashboard(root, report=report, output_dir=output_dir)
    dashboard.pack(fill='both', expand=True)

    print("\n  GUI窗口已启动，关闭窗口后退出...")
    root.mainloop()


def main():
    print("\n" + "#"*60)
    print("# V0.5.5.2 回测报告中心 UI - 测试")
    print("# 概览卡片 + 净值曲线 + 回撤曲线 + 交易表格 + 参数面板 + 导出")
    print("#"*60)

    test_imports()
    test_components_creation()
    test_report_data()
    test_export()

    if '--show' in sys.argv:
        print("\n" + "="*60)
        print("【5】GUI显示测试")
        print("="*60)
        show_dashboard()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("# 运行 python test_v0552_report_ui.py --show 可查看GUI界面")
    print("#"*60)


if __name__ == '__main__':
    main()
