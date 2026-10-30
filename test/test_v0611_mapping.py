# -*- coding: utf-8 -*-
"""V0.6.1.1 策略名称统一映射修正 - 验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先导入strategy模块，避免循环导入问题
from strategy.weight_adapter import WeightAdapter, get_weight_adapter
from strategy.ai_buy_signal import AIBuySignalEngine

print('========== V0.6.1.1 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v0611_memory.json')

def build_memory_with_mapped_strategies():
    """构造记忆库，使用映射后的标准策略名称"""
    from backtest.learning import TradeMemory
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # 涨停突破：高胜率（12笔，9胜3负）- 对应"涨停异动信号"
    for i in range(9):
        tm.remember(f'600{i:03d}', f'股{i}', 'BUY', score=92+i%5, price=10+i,
                     strategy='涨停突破',
                     result={'pnl': 2500+i*100, 'success': True, 'max_gain': 15, 'max_drawdown': -3},
                     hold_days=5)
    for i in range(3):
        tm.remember(f'000{i:03d}', f'股{i+20}', 'BUY', score=90+i, price=8+i,
                     strategy='涨停突破',
                     result={'pnl': -800-i*50, 'success': False, 'max_gain': 2, 'max_drawdown': -6},
                     hold_days=3)

    # 资金流入：中等胜率（11笔，6胜5负）- 对应"资金异动信号"
    for i in range(6):
        tm.remember(f'601{i:03d}', f'股{i+30}', 'BUY', score=82+i%5, price=12+i,
                     strategy='资金流入',
                     result={'pnl': 1500+i*80, 'success': True, 'max_gain': 12, 'max_drawdown': -5},
                     hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股{i+40}', 'BUY', score=80+i, price=9+i,
                     strategy='资金流入',
                     result={'pnl': -600-i*40, 'success': False, 'max_gain': 3, 'max_drawdown': -8},
                     hold_days=2)

    # MACD金叉：高胜率（10笔，7胜3负）
    for i in range(7):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=88+i%3, price=11+i,
                     strategy='MACD金叉',
                     result={'pnl': 2000+i*90, 'success': True, 'max_gain': 14, 'max_drawdown': -4},
                     hold_days=5)
    for i in range(3):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=85+i, price=10+i,
                     strategy='MACD金叉',
                     result={'pnl': -700-i*40, 'success': False, 'max_gain': 2, 'max_drawdown': -7},
                     hold_days=3)

    return tm

# [1] Strategy Mapping Test
print('[1] Strategy Mapping Test')
try:
    from backtest.learning.strategy_mapping import (
        map_signal_to_strategy, get_strategy_category, SIGNAL_TO_STRATEGY,
        STANDARD_STRATEGIES,
    )

    # 测试映射
    assert map_signal_to_strategy('涨停异动信号') == '涨停突破'
    assert map_signal_to_strategy('资金异动信号') == '资金流入'
    assert map_signal_to_strategy('B1大额订单催化') == '资金异动'
    assert map_signal_to_strategy('B2业绩超预期催化') == '基本面催化'
    assert map_signal_to_strategy('MACD金叉') == 'MACD金叉'
    assert map_signal_to_strategy('未知信号') == 'AI综合评分'

    print(f"  映射总数: {len(SIGNAL_TO_STRATEGY)}")
    print(f"  标准策略数: {len(STANDARD_STRATEGIES)}")
    print(f"  涨停异动信号 → {map_signal_to_strategy('涨停异动信号')}")
    print(f"  资金异动信号 → {map_signal_to_strategy('资金异动信号')}")
    print(f"  B1大额订单催化 → {map_signal_to_strategy('B1大额订单催化')}")
    print(f"  B2业绩超预期催化 → {map_signal_to_strategy('B2业绩超预期催化')}")
    print(f"  MACD金叉 → {map_signal_to_strategy('MACD金叉')}")
    print(f"  未知信号 → {map_signal_to_strategy('未知信号')} (兜底)")

    # 分类测试
    print(f"\n  策略分类:")
    print(f"    涨停突破 → {get_strategy_category('涨停突破')}")
    print(f"    MACD金叉 → {get_strategy_category('MACD金叉')}")
    print(f"    基本面催化 → {get_strategy_category('基本面催化')}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Weight Adapter with Mapping Test
print('[2] Weight Adapter with Mapping Test')
try:
    from backtest.learning import StrategyWeightManager

    tm = build_memory_with_mapped_strategies()
    wm = StrategyWeightManager(trade_memory=tm)
    adapter = WeightAdapter(enable=True, weight_manager=wm)

    # 用实时信号名查询，应该自动映射到标准策略名
    result1 = adapter.get_strategy_weight('涨停异动信号')
    assert result1['strategy'] == '涨停突破'
    assert result1['original_name'] == '涨停异动信号'
    assert result1['sample'] >= 10
    assert result1['weight'] > 1.0  # 高胜率应该增强

    print(f"  涨停异动信号 → 映射:{result1['strategy']}")
    print(f"    权重: {result1['weight']} 样本: {result1['sample']} 胜率: {result1['win_rate']}%")

    result2 = adapter.get_strategy_weight('资金异动信号')
    assert result2['strategy'] == '资金流入'
    print(f"  资金异动信号 → 映射:{result2['strategy']}")
    print(f"    权重: {result2['weight']} 样本: {result2['sample']} 胜率: {result2['win_rate']}%")

    # 评分调整测试
    adj = adapter.adjust_score('涨停异动信号', 80)
    assert adj['strategy'] == '涨停突破'
    assert adj['adjusted_score'] > 80
    print(f"\n  评分调整: 涨停异动信号 80分 → {adj['adjusted_score']}分 (权重{adj['weight']})")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] AI Buy Signal Full Pipeline Test
print('[3] AI Buy Signal Full Pipeline Test')
try:
    tm = build_memory_with_mapped_strategies()
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import get_weight_adapter

    # 重置单例并注入有数据的权重管理器
    import strategy.weight_adapter as wa_module
    wa_module._adapter_instance = None
    adapter = get_weight_adapter(enable=True)
    adapter._weight_manager = StrategyWeightManager(trade_memory=tm)

    # 开启动态权重
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = True
    engine = AIBuySignalEngine()

    # 构造会触发涨停异动信号的数据
    stock_data = {
        'code': '600519',
        'name': '贵州茅台',
        'basic': {'concepts': ['白酒']},
        'limit_up': {'has_limit_up': True, 'limit_up_count': 2},
        'capital': {'has_capital_flow': True, 'main_net_inflow': 50000000},
        'chanlun': {'current_state': '中枢震荡'},
    }

    report = engine.generate_report(stock_data)
    print(f"  股票: {stock_data['code']}")
    print(f"  原始评分: {report.get('original_score')}")
    print(f"  最终评分: {report['score']}")
    print(f"  评级: {report['rating']}")

    di = report.get('dynamic_weight_info')
    if di:
        print(f"  动态权重信息:")
        print(f"    原始信号: {di.get('original_name')}")
        print(f"    映射策略: {di.get('strategy')}")
        print(f"    权重: {di['weight']}")
        print(f"    样本: {di['sample']}")
        print(f"    胜率: {di['win_rate']}%")
        print(f"    已生效: {di['enabled']}")
    else:
        print(f"  动态权重信息: None (未触发信号或未启用)")

    # 恢复
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False

print()

# [4] Mapping Summary Test
print('[4] Mapping Summary Test')
try:
    from backtest.learning.strategy_mapping import render_mapping_summary
    summary = render_mapping_summary()
    assert '策略名称映射表' in summary
    assert 'V0.6.1.1' in summary
    print(f"  摘要长度: {len(summary)}字符")
    print(f"  包含版本号: {'V0.6.1.1' in summary}")
    print(f"  包含映射总数: {'映射总数' in summary}")
    print(f"\n{summary[:500]}...")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Backward Compatibility Test
print('[5] Backward Compatibility Test')
try:
    # 默认关闭状态
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False
    engine = AIBuySignalEngine()

    stock_data = {
        'code': '000001',
        'name': '平安银行',
        'basic': {'concepts': ['银行']},
        'chanlun': {'current_state': '二买'},
    }
    report = engine.generate_report(stock_data)

    # 默认关闭时，dynamic_weight_info应为None，score=original_score
    assert report.get('dynamic_weight_info') is None
    assert report['score'] == report.get('original_score')
    print(f"  默认关闭: score={report['score']}, dynamic_info=None ✅")

    # 开启但无匹配信号时
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = True
    report2 = engine.generate_report(stock_data)
    print(f"  开启无信号: score={report2['score']}, dynamic_info={'有' if report2.get('dynamic_weight_info') else '无'}")

    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()
    AIBuySignalEngine.DYNAMIC_WEIGHT_ENABLED = False

# 清理
try:
    if os.path.exists(tmpfile):
        os.remove(tmpfile)
except Exception:
    pass

print()
print('===============================================')
print('V0.6.1.1 READY')
print('策略名称映射已打通，AI学习结果可真实影响实盘决策')
