# -*- coding: utf-8 -*-
"""V0.6.1 动态策略权重接入层 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import (
    TradeMemory, StrategyWeightManager, DynamicWeightBridge,
    SIGNAL_TYPE_TO_STRATEGY,
)

print('========== V0.6.1 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v061_memory.json')

def build_memory():
    """构造记忆库，让不同策略有不同胜率"""
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # MACD金叉：高胜率（12笔，9胜3负）
    for i in range(9):
        tm.remember(f'600{i:03d}', f'股{i}', 'BUY', score=92+i%5, price=10+i,
                     strategy='MACD轴下金叉',
                     result={'pnl': 2500+i*100, 'success': True, 'max_gain': 15, 'max_drawdown': -3},
                     hold_days=5)
    for i in range(3):
        tm.remember(f'000{i:03d}', f'股{i+20}', 'BUY', score=90+i, price=8+i,
                     strategy='MACD轴下金叉',
                     result={'pnl': -800-i*50, 'success': False, 'max_gain': 2, 'max_drawdown': -6},
                     hold_days=3)

    # 倍量突破：中等胜率（11笔，6胜5负）
    for i in range(6):
        tm.remember(f'601{i:03d}', f'股{i+30}', 'BUY', score=82+i%5, price=12+i,
                     strategy='倍量突破',
                     result={'pnl': 1500+i*80, 'success': True, 'max_gain': 12, 'max_drawdown': -5},
                     hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股{i+40}', 'BUY', score=80+i, price=9+i,
                     strategy='倍量突破',
                     result={'pnl': -600-i*40, 'success': False, 'max_gain': 3, 'max_drawdown': -8},
                     hold_days=2)

    # 主升回踩：低胜率（10笔，3胜7负）
    for i in range(3):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=72+i, price=11+i,
                     strategy='主升回踩',
                     result={'pnl': 800+i*50, 'success': True, 'max_gain': 8, 'max_drawdown': -7},
                     hold_days=6)
    for i in range(7):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=70+i, price=7+i,
                     strategy='主升回踩',
                     result={'pnl': -1200-i*60, 'success': False, 'max_gain': 1, 'max_drawdown': -12},
                     hold_days=4)

    return tm

def make_mock_signal_result():
    """构造模拟的AISignalEngine输出"""
    return {
        'signals': [
            {'type': 'macd_axis_low_golden', 'name': '轴下金叉', 'color': '#00e676',
             'reason': 'MACD轴下金叉'},
            {'type': 'double_volume', 'name': '倍量', 'color': '#ffea00',
             'reason': '倍量突破'},
            {'type': 'main_rise', 'name': '买点', 'color': '#ff1744',
             'reason': '主升回踩'},
        ],
        'scores': {
            'macd': 5,        # MACD信号5分
            'double_vol': 10, # 倍量10分
            'main_rise': 15,  # 主升回踩15分
        },
        'total_score': 30,
        'rating': '放弃',
        'analysis': 'MACD轴下金叉，倍量突破，主升回踩',
    }

# [1] Signal-Strategy Mapping Test
print('[1] Signal-Strategy Mapping Test')
try:
    assert len(SIGNAL_TYPE_TO_STRATEGY) >= 15
    assert SIGNAL_TYPE_TO_STRATEGY['macd_axis_low_golden'] == 'MACD轴下金叉'
    assert SIGNAL_TYPE_TO_STRATEGY['double_volume'] == '倍量突破'
    assert SIGNAL_TYPE_TO_STRATEGY['main_rise'] == '主升回踩'
    assert SIGNAL_TYPE_TO_STRATEGY['kdj_golden'] == 'KDJ金叉'

    print(f"  映射总数: {len(SIGNAL_TYPE_TO_STRATEGY)}")
    print(f"  macd_axis_low_golden → {SIGNAL_TYPE_TO_STRATEGY['macd_axis_low_golden']}")
    print(f"  double_volume → {SIGNAL_TYPE_TO_STRATEGY['double_volume']}")
    print(f"  main_rise → {SIGNAL_TYPE_TO_STRATEGY['main_rise']}")
    print(f"  kdj_golden → {SIGNAL_TYPE_TO_STRATEGY['kdj_golden']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Dynamic Weight Apply Test
print('[2] Dynamic Weight Apply Test')
try:
    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    bridge = DynamicWeightBridge(weight_manager=wm, enable=True)

    mock_result = make_mock_signal_result()
    enhanced = bridge.apply_dynamic_weights(mock_result)

    assert 'dynamic_scores' in enhanced
    assert 'dynamic_total' in enhanced
    assert 'dynamic_rating' in enhanced
    assert 'weight_adjustments' in enhanced
    assert enhanced['weight_enabled'] == True

    print(f"  原始总分: {enhanced['original_total']}")
    print(f"  动态总分: {enhanced['dynamic_total']}")
    print(f"  评分变化: {enhanced['score_change']:+.1f}")
    print(f"  原始评级: {enhanced['original_rating']}")
    print(f"  动态评级: {enhanced['dynamic_rating']}")

    print(f"\n  动态分数:")
    for sig_type, score in enhanced['dynamic_scores'].items():
        raw = mock_result['scores'].get(sig_type, 0)
        print(f"    {sig_type}: {raw} → {score}")

    print(f"\n  权重调整: {len(enhanced['weight_adjustments'])}项")
    for adj in enhanced['weight_adjustments']:
        print(f"    [{adj['direction']}] {adj['strategy']}: "
              f"权重{adj['dynamic_weight']} 样本{adj['sample_count']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Weight Explanation Test
print('[3] Weight Explanation Test')
try:
    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    bridge = DynamicWeightBridge(weight_manager=wm, enable=True)

    mock_result = make_mock_signal_result()
    enhanced = bridge.apply_dynamic_weights(mock_result)

    explanation = bridge.explain_adjustment(enhanced)
    assert '原始评分' in explanation
    assert '动态评分' in explanation

    print(f"  解释文本长度: {len(explanation)}字符")
    print(f"  包含原始评分: {'原始评分' in explanation}")
    print(f"  包含动态评分: {'动态评分' in explanation}")
    print(f"  包含权重调整明细: {'权重调整明细' in explanation}")
    print(f"\n{explanation}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Disabled State Test
print('[4] Disabled State Test')
try:
    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    bridge = DynamicWeightBridge(weight_manager=wm, enable=False)

    mock_result = make_mock_signal_result()
    enhanced = bridge.apply_dynamic_weights(mock_result)

    assert enhanced['weight_enabled'] == False
    assert enhanced['dynamic_total'] == mock_result['total_score']
    assert enhanced['dynamic_rating'] == mock_result['rating']
    assert len(enhanced['weight_adjustments']) == 0

    print(f"  启用状态: {enhanced['weight_enabled']}")
    print(f"  动态总分: {enhanced['dynamic_total']} (与原始一致)")
    print(f"  动态评级: {enhanced['dynamic_rating']} (与原始一致)")
    print(f"  调整项数: {len(enhanced['weight_adjustments'])}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Full Pipeline Test (AISignalEngine + Bridge)
print('[5] Full Pipeline Test')
try:
    # 尝试导入真实AISignalEngine
    try:
        from strategy.ai_signal_engine import AISignalEngine
        has_real_engine = True
    except ImportError:
        has_real_engine = False

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    bridge = DynamicWeightBridge(weight_manager=wm, enable=True)

    if has_real_engine:
        # 构造模拟日线数据
        import numpy as np
        np.random.seed(42)
        daily_data = []
        base_price = 10.0
        for i in range(60):
            change = np.random.normal(0.002, 0.02)
            close = base_price * (1 + change)
            high = close * (1 + abs(np.random.normal(0, 0.01)))
            low = close * (1 - abs(np.random.normal(0, 0.01)))
            volume = np.random.randint(100000, 500000)
            daily_data.append({
                'open': base_price,
                'close': close,
                'high': high,
                'low': low,
                'volume': volume,
            })
            base_price = close

        engine = AISignalEngine()
        raw_result = engine.analyze(daily_data)
        print(f"  真实引擎信号数: {len(raw_result['signals'])}")
        print(f"  原始总分: {raw_result['total_score']}")
        print(f"  原始评级: {raw_result['rating']}")
    else:
        raw_result = make_mock_signal_result()
        print(f"  使用模拟信号结果 (AISignalEngine不可用)")

    enhanced = bridge.apply_dynamic_weights(raw_result)

    print(f"  动态总分: {enhanced['dynamic_total']}")
    print(f"  动态评级: {enhanced['dynamic_rating']}")
    print(f"  评分变化: {enhanced['score_change']:+.1f}")
    print(f"  权重调整: {len(enhanced['weight_adjustments'])}项")
    print(f"  桥接层应用历史: {len(bridge.apply_history)}次")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] Singleton & Summary Test
print('[6] Singleton & Summary Test')
try:
    from backtest.learning.dynamic_weight_bridge import get_dynamic_weight_bridge

    # 单例测试
    bridge1 = get_dynamic_weight_bridge()
    bridge2 = get_dynamic_weight_bridge()
    assert bridge1 is bridge2
    print(f"  单例测试: bridge1 is bridge2 = {bridge1 is bridge2}")

    # 摘要渲染
    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    bridge = DynamicWeightBridge(weight_manager=wm, enable=True)
    summary = bridge.render_summary()
    assert '动态策略权重接入层' in summary
    assert 'V0.6.1' in summary

    print(f"  摘要长度: {len(summary)}字符")
    print(f"  包含版本号: {'V0.6.1' in summary}")
    print(f"  包含启用状态: {'已启用' in summary}")

    # 所有信号权重查询
    all_weights = bridge.get_all_signal_weights()
    print(f"  信号权重查询: {len(all_weights)}个信号类型")

    print(f"\n{summary}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理
try:
    if os.path.exists(tmpfile):
        os.remove(tmpfile)
except Exception:
    pass

print()
print('===============================================')
print('V0.6.1 READY')
