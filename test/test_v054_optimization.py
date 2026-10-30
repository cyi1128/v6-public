# -*- coding: utf-8 -*-
"""
V0.5.4 智能参数优化 - 集成测试

验证：参数空间 + 网格搜索 + 多目标评分 + Walk Forward + AI阈值
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from backtest.strategy import Pullback59Strategy
from backtest.optimization import (
    Parameter, ParameterSpace,
    OptimizationResult, OptimizationResultSet,
    MultiObjectiveScorer, balanced_scorer, conservative_scorer, aggressive_scorer,
    GridSearch,
    WalkForwardValidator,
    ThresholdFilteredStrategy, AIThresholdOptimizer,
)


def generate_mock_kline(days=400, base_price=10.0, trend=0.0003,
                        volatility=0.02, seed=42):
    """生成模拟K线"""
    random.seed(seed)
    data = {'open': [], 'close': [], 'high': [], 'low': [],
            'volume': [], 'pct_chg': [], 'dates': []}
    price = base_price
    from datetime import datetime, timedelta
    d = datetime(2022, 1, 3)
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


def test_parameter_space():
    """测试参数空间"""
    print("\n" + "="*60)
    print("【1】参数空间测试")
    print("="*60)

    space = ParameterSpace([
        Parameter("stop_loss_pct", [3, 5, 8]),
        Parameter("take_profit_pct", [10, 15, 20]),
        Parameter("max_hold_days", [10, 15, 20]),
    ])

    print(space.summary())

    # 网格搜索
    grid = space.generate_grid()
    print(f"  网格组合数: {len(grid)}")
    print(f"  示例: {grid[0]}")

    # 随机采样
    sample = space.generate_random(10, seed=42)
    print(f"  随机采样: {len(sample)}组")

    # 添加约束
    space.add_constraint(lambda p: p['take_profit_pct'] > p['stop_loss_pct'] * 2)
    grid_constrained = space.generate_grid()
    print(f"  约束后组合数: {len(grid_constrained)}")

    print("参数空间测试通过 ✅")


def test_multi_objective_scoring():
    """测试多目标评分"""
    print("\n" + "="*60)
    print("【2】多目标评分测试")
    print("="*60)

    # 模拟结果
    results = [
        OptimizationResult({'stop_loss': 5, 'take_profit': 20}, {
            'total_return': 35.0, 'max_drawdown': 8.0,
            'win_rate': 55.0, 'profit_loss_ratio': 2.0, 'trade_count': 50,
        }),
        OptimizationResult({'stop_loss': 3, 'take_profit': 10}, {
            'total_return': 15.0, 'max_drawdown': 4.0,
            'win_rate': 65.0, 'profit_loss_ratio': 1.5, 'trade_count': 80,
        }),
        OptimizationResult({'stop_loss': 8, 'take_profit': 30}, {
            'total_return': 80.0, 'max_drawdown': 25.0,
            'win_rate': 45.0, 'profit_loss_ratio': 2.5, 'trade_count': 30,
        }),
    ]

    # 平衡型评分
    scorer = balanced_scorer()
    for r in results:
        scorer.score_result(r)

    print("  平衡型评分:")
    for r in sorted(results, key=lambda x: x.score, reverse=True):
        print(f"    {r.params}: 评分{r.score:.1f} "
              f"(收益{r.total_return:+.0f}%, 回撤{r.max_drawdown:.0f}%, 胜率{r.win_rate:.0f}%)")

    # 保守型评分
    cons_scorer = conservative_scorer()
    for r in results:
        cons_scorer.score_result(r)
    print("\n  保守型评分(更看重回撤):")
    for r in sorted(results, key=lambda x: x.score, reverse=True):
        print(f"    {r.params}: 评分{r.score:.1f}")

    # 激进型评分
    agg_scorer = aggressive_scorer()
    for r in results:
        agg_scorer.score_result(r)
    print("\n  激进型评分(更看重收益):")
    for r in sorted(results, key=lambda x: x.score, reverse=True):
        print(f"    {r.params}: 评分{r.score:.1f}")

    # 评分解释
    print(f"\n  评分解释(平衡型):")
    scorer.score_result(results[0])
    print(scorer.explain_score(results[0]))

    print("多目标评分测试通过 ✅")


def test_grid_search():
    """测试网格搜索"""
    print("\n" + "="*60)
    print("【3】网格搜索测试")
    print("="*60)

    kline = generate_mock_kline(days=300, base_price=12.0, seed=111)

    # 小参数空间（9组）
    space = ParameterSpace([
        Parameter("stop_loss_pct", [3, 5, 8]),
        Parameter("take_profit_pct", [10, 15, 20]),
    ])

    progress = []
    def on_progress(current, total, params, result):
        progress.append(current)

    gs = GridSearch(
        Pullback59Strategy, space, kline,
        code="OPT001", initial_cash=1000000,
        scorer=balanced_scorer(),
        progress_callback=on_progress,
    )

    result_set = gs.run(max_combinations=9)

    print(f"\n{result_set.summary(top_n=5)}")
    print(f"  进度回调次数: {len(progress)}")

    # 帕累托前沿
    pareto = result_set.get_pareto_front()
    print(f"  帕累托前沿: {len(pareto)}个解")
    for p in pareto:
        print(f"    {p.params}: 收益{p.total_return:+.1f}%, 回撤{p.max_drawdown:.1f}%")

    print("网格搜索测试通过 ✅")


def test_walk_forward():
    """测试Walk Forward验证"""
    print("\n" + "="*60)
    print("【4】Walk Forward验证测试")
    print("="*60)

    kline = generate_mock_kline(days=500, base_price=10.0, seed=222)

    # 小参数空间
    space = ParameterSpace([
        Parameter("stop_loss_pct", [5, 8]),
        Parameter("take_profit_pct", [15, 20]),
    ])

    wf = WalkForwardValidator(
        Pullback59Strategy, space, kline,
        code="WF001", initial_cash=1000000,
        train_years=1, test_months=3,
    )

    windows = wf.generate_windows()
    print(f"  生成窗口数: {len(windows)}")
    for w in windows[:3]:
        print(f"    窗口{w.window_id+1}: 训练{w.train_start}~{w.train_end}, "
              f"验证{w.test_start}~{w.test_end}")

    if windows:
        # 运行（限制训练组合数加速）
        result = wf.run(max_train_combinations=4)
        summary = result.get('validation_summary', {})
        print(f"\n  验证期平均收益: {summary.get('avg_return', 0):+.2f}%")
        print(f"  验证期平均回撤: {summary.get('avg_drawdown', 0):.2f}%")
        print(f"  参数稳定性: {result.get('param_stability', {}).get('stability_rate', 0):.0f}%")

    print("Walk Forward验证测试通过 ✅")


def test_ai_threshold():
    """测试AI评分阈值优化"""
    print("\n" + "="*60)
    print("【5】AI评分阈值优化测试")
    print("="*60)

    kline = generate_mock_kline(days=300, base_price=15.0, seed=333)

    optimizer = AIThresholdOptimizer(
        Pullback59Strategy, {}, kline,
        code="TH001", initial_cash=1000000,
    )

    result = optimizer.optimize(
        min_score_range=[50, 60, 70],
        full_score_range=[75, 85],
    )

    print(f"\n{result.summary(top_n=5)}")

    if result.best_result:
        print(f"  最佳阈值: {result.best_result.params}")
        print(f"  最佳评分: {result.best_result.score:.1f}")

    print("AI评分阈值优化测试通过 ✅")


def test_optimization_result_set():
    """测试优化结果集合"""
    print("\n" + "="*60)
    print("【6】优化结果集合测试")
    print("="*60)

    result_set = OptimizationResultSet("TestStrategy")

    # 添加模拟结果
    for i in range(20):
        params = {'param_a': i, 'param_b': i * 2}
        metrics = {
            'total_return': random.uniform(-20, 80),
            'max_drawdown': random.uniform(2, 30),
            'win_rate': random.uniform(35, 70),
            'profit_loss_ratio': random.uniform(0.8, 3.0),
            'trade_count': random.randint(5, 50),
        }
        r = OptimizationResult(params, metrics)
        balanced_scorer().score_result(r)
        result_set.add(r)

    result_set.sort_by('score')

    print(f"  总结果数: {result_set.count}")
    print(f"  最佳: {result_set.best_result}")

    top5 = result_set.get_top_n(5)
    print(f"  Top5:")
    for r in top5:
        print(f"    {r.params}: 评分{r.score:.1f}, 收益{r.total_return:+.1f}%")

    # 保存
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    filepath = os.path.join(output_dir, "test_optimization_result.json")
    result_set.save_json(filepath)
    print(f"  已保存: {filepath}")

    print("优化结果集合测试通过 ✅")


def main():
    print("\n" + "#"*60)
    print("# V0.5.4 智能参数优化 - 集成测试")
    print("# 参数空间 + 网格搜索 + 多目标评分 + WalkForward + AI阈值")
    print("#"*60)

    test_parameter_space()
    test_multi_objective_scoring()
    test_grid_search()
    test_walk_forward()
    test_ai_threshold()
    test_optimization_result_set()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
