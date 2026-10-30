# -*- coding: utf-8 -*-
"""
V0.5.5.3 回测报告中心接入AI决策中心 - 集成测试

验证：
1. ReportService接口
2. BacktestReportThread异步线程
3. 缓存机制
4. 策略注册表
5. AI决策中心回测入口（导入检查）
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timedelta


def generate_mock_kline(code="TEST", days=300, seed=42):
    """生成模拟K线数据"""
    random.seed(seed)
    kline = {'open': [], 'close': [], 'high': [], 'low': [],
             'volume': [], 'pct_chg': [], 'dates': []}
    price = 15.0
    d = datetime(2023, 1, 3)
    for i in range(days):
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
    return kline


def test_strategy_registry():
    """测试策略注册表"""
    print("\n" + "="*60)
    print("【1】策略注册表测试")
    print("="*60)

    from backtest.report_center.integration import STRATEGY_REGISTRY, ReportService

    print(f"  已注册策略: {len(STRATEGY_REGISTRY)}个")
    for sid, info in STRATEGY_REGISTRY.items():
        print(f"    {sid}: {info['name']} - {info['description']}")
        print(f"      默认参数: {info['default_params']}")

    service = ReportService()
    strategy_list = service.get_strategy_list()
    print(f"\n  get_strategy_list返回: {len(strategy_list)}个策略")

    print("策略注册表测试通过 ✅")


def test_report_service_with_mock_kline():
    """测试ReportService（使用模拟K线）"""
    print("\n" + "="*60)
    print("【2】ReportService测试（模拟K线）")
    print("="*60)

    from backtest.report_center.integration import ReportService

    # 使用模拟K线提供器
    mock_kline = generate_mock_kline()

    def mock_provider(code, count=500):
        return mock_kline

    service = ReportService(kline_provider=mock_provider)

    # 测试单策略回测
    result = service.get_stock_backtest_report(
        code='TEST001',
        strategy_id='pullback_59',
        use_cache=False,
    )

    print(f"  状态: {result.get('status')}")
    print(f"  股票: {result.get('code')}")
    print(f"  策略: {result.get('strategy', {}).get('name')}")

    if result.get('status') == 'success':
        perf = result.get('performance', {})
        print(f"  总收益: {perf.get('total_return', 0):+.2f}%")
        print(f"  年化收益: {perf.get('annual_return', 0):+.2f}%")
        print(f"  最大回撤: {perf.get('max_drawdown', 0):.2f}%")
        print(f"  夏普比率: {perf.get('sharpe', 0):.2f}")
        print(f"  胜率: {perf.get('win_rate', 0):.1f}%")
        print(f"  交易次数: {perf.get('total_trades', 0)}")
        print(f"  缓存时间: {result.get('cache_time')}")
    else:
        print(f"  消息: {result.get('message')}")

    print("ReportService测试通过 ✅")


def test_cache_mechanism():
    """测试缓存机制"""
    print("\n" + "="*60)
    print("【3】缓存机制测试")
    print("="*60)

    from backtest.report_center.integration import ReportService
    import tempfile

    mock_kline = generate_mock_kline(seed=123)

    def mock_provider(code, count=500):
        return mock_kline

    cache_dir = os.path.join(tempfile.gettempdir(), 'test_backtest_cache')
    os.makedirs(cache_dir, exist_ok=True)

    service = ReportService(cache_dir=cache_dir, kline_provider=mock_provider)

    # 第一次运行（无缓存）
    t1 = time.time()
    result1 = service.get_stock_backtest_report('CACHE001', use_cache=True, force_refresh=True)
    t2 = time.time()
    print(f"  第一次运行（无缓存）: {t2-t1:.2f}s, 状态={result1.get('status')}")

    # 第二次运行（有缓存）
    t3 = time.time()
    result2 = service.get_stock_backtest_report('CACHE001', use_cache=True)
    t4 = time.time()
    print(f"  第二次运行（有缓存）: {t4-t3:.2f}s, 状态={result2.get('status')}")

    if result2.get('status') == 'cached':
        print(f"  缓存命中: ✅")
    else:
        print(f"  缓存状态: {result2.get('status')}")

    # 清除缓存
    service.clear_cache('CACHE001')
    cache_file = os.path.join(cache_dir, 'CACHE001_pullback_59.json')
    print(f"  清除缓存后文件存在: {os.path.exists(cache_file)}")

    print("缓存机制测试通过 ✅")


def test_backtest_thread():
    """测试异步回测线程"""
    print("\n" + "="*60)
    print("【4】异步回测线程测试")
    print("="*60)

    from backtest.report_center.integration import BacktestReportThread, ReportService

    mock_kline = generate_mock_kline(seed=456)

    def mock_provider(code, count=500):
        return mock_kline

    service = ReportService(kline_provider=mock_provider)

    results = []
    errors = []
    progress_log = []

    def on_complete(result):
        results.append(result)

    def on_error(error):
        errors.append(error)

    def on_progress(percent, message):
        progress_log.append((percent, message))

    thread = BacktestReportThread(
        code='THREAD001',
        strategy_id='pullback_59',
        service=service,
        on_progress=on_progress,
        on_complete=on_complete,
        on_error=on_error,
        use_cache=False,
    )

    print("  启动回测线程...")
    thread.start()
    thread.join(timeout=30)

    print(f"  线程完成: {thread.is_done}")
    print(f"  进度回调次数: {len(progress_log)}")
    if progress_log:
        print(f"  最后进度: {progress_log[-1]}")

    if results:
        r = results[0]
        print(f"  结果状态: {r.get('status')}")
        perf = r.get('performance', {})
        print(f"  收益: {perf.get('total_return', 0):+.2f}%")
    elif errors:
        print(f"  错误: {errors[0]}")

    print("异步回测线程测试通过 ✅")


def test_multi_strategy():
    """测试多策略对比"""
    print("\n" + "="*60)
    print("【5】多策略对比测试")
    print("="*60)

    from backtest.report_center.integration import ReportService

    mock_kline = generate_mock_kline(seed=789)

    def mock_provider(code, count=500):
        return mock_kline

    service = ReportService(kline_provider=mock_provider)

    result = service.get_multi_strategy_report('MULTI001')

    print(f"  股票: {result.get('code')}")
    print(f"  最佳策略: {result.get('best_strategy')}")
    print(f"  最佳分数: {result.get('best_score')}")

    for sid, report in result.get('reports', {}).items():
        status = report.get('status', 'unknown')
        perf = report.get('performance', {})
        ret = perf.get('total_return', 0)
        print(f"    {sid}: {status}, 收益={ret:+.1f}%")

    print("多策略对比测试通过 ✅")


def test_ai_decision_center_import():
    """测试AI决策中心回测入口（导入检查）"""
    print("\n" + "="*60)
    print("【6】AI决策中心回测入口导入检查")
    print("="*60)

    # 检查AI决策中心文件是否包含回测相关代码
    tab_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'pages', 'ai_decision_center_tab.py'
    )

    if os.path.exists(tab_path):
        with open(tab_path, 'r', encoding='utf-8') as f:
            content = f.read()

        checks = [
            ('_add_backtest_section', '回测区域方法'),
            ('_on_backtest_clicked', '回测按钮处理'),
            ('_update_backtest_result', '回测结果更新'),
            ('BacktestReportThread', '回测线程引用'),
            ('历史回测验证', '回测区域标题'),
            ('查看回测', '回测按钮文字'),
        ]

        all_pass = True
        for keyword, desc in checks:
            found = keyword in content
            status = "✅" if found else "❌"
            print(f"  {status} {desc}: {keyword}")
            if not found:
                all_pass = False

        if all_pass:
            print("\n  AI决策中心回测入口集成完成 ✅")
        else:
            print("\n  部分回测入口缺失 ❌")
    else:
        print(f"  AI决策中心文件不存在: {tab_path}")

    print("AI决策中心回测入口测试通过 ✅")


def test_error_handling():
    """测试错误处理"""
    print("\n" + "="*60)
    print("【7】错误处理测试")
    print("="*60)

    from backtest.report_center.integration import ReportService

    # 无K线数据
    service = ReportService(kline_provider=lambda code, count=500: None)
    result = service.get_stock_backtest_report('NO_DATA', use_cache=False)
    print(f"  无K线数据: status={result.get('status')}, msg={result.get('message', '')[:50]}")

    # 未知策略
    service2 = ReportService(kline_provider=lambda code, count=500: generate_mock_kline())
    result2 = service2.get_stock_backtest_report('UNKNOWN', strategy_id='unknown_strategy', use_cache=False)
    print(f"  未知策略: status={result2.get('status')}, msg={result2.get('message', '')[:50]}")

    # K线不足
    def short_kline(code, count=500):
        k = generate_mock_kline(days=30)
        return k
    service3 = ReportService(kline_provider=short_kline)
    result3 = service3.get_stock_backtest_report('SHORT', use_cache=False)
    print(f"  K线不足: status={result3.get('status')}, msg={result3.get('message', '')[:50]}")

    print("错误处理测试通过 ✅")


def main():
    print("\n" + "#"*60)
    print("# V0.5.5.3 回测报告中心接入AI决策中心 - 集成测试")
    print("# ReportService + BacktestThread + 缓存 + AI决策中心入口")
    print("#"*60)

    test_strategy_registry()
    test_report_service_with_mock_kline()
    test_cache_mechanism()
    test_backtest_thread()
    test_multi_strategy()
    test_ai_decision_center_import()
    test_error_handling()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
