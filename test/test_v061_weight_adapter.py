# -*- coding: utf-8 -*-
"""V0.6.1 策略权重适配器 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('========== V0.6.1 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v061_adapter_memory.json')

def build_memory():
    """构造记忆库"""
    from backtest.learning import TradeMemory
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # MACD金叉：高胜率（12笔，9胜3负）
    for i in range(9):
        tm.remember(f'600{i:03d}', f'股{i}', 'BUY', score=92+i%5, price=10+i,
                     strategy='MACD金叉',
                     result={'pnl': 2500+i*100, 'success': True, 'max_gain': 15, 'max_drawdown': -3},
                     hold_days=5)
    for i in range(3):
        tm.remember(f'000{i:03d}', f'股{i+20}', 'BUY', score=90+i, price=8+i,
                     strategy='MACD金叉',
                     result={'pnl': -800-i*50, 'success': False, 'max_gain': 2, 'max_drawdown': -6},
                     hold_days=3)

    # 三倍量突破：中等胜率（11笔，6胜5负）
    for i in range(6):
        tm.remember(f'601{i:03d}', f'股{i+30}', 'BUY', score=82+i%5, price=12+i,
                     strategy='三倍量突破',
                     result={'pnl': 1500+i*80, 'success': True, 'max_gain': 12, 'max_drawdown': -5},
                     hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股{i+40}', 'BUY', score=80+i, price=9+i,
                     strategy='三倍量突破',
                     result={'pnl': -600-i*40, 'success': False, 'max_gain': 3, 'max_drawdown': -8},
                     hold_days=2)

    # 回踩MA5：低胜率（5笔，2胜3负）- 小样本
    for i in range(2):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=72+i, price=11+i,
                     strategy='回踩MA5',
                     result={'pnl': 800+i*50, 'success': True, 'max_gain': 8, 'max_drawdown': -7},
                     hold_days=6)
    for i in range(3):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=70+i, price=7+i,
                     strategy='回踩MA5',
                     result={'pnl': -1200-i*60, 'success': False, 'max_gain': 1, 'max_drawdown': -12},
                     hold_days=4)

    return tm

# [1] Weight Adapter Import Test
print('[1] Weight Adapter Import Test')
try:
    from strategy.weight_adapter import WeightAdapter, get_weight_adapter
    adapter = WeightAdapter(enable=False)
    assert adapter is not None
    assert adapter.enable == False
    print(f"  模块导入: 成功")
    print(f"  类名: {type(adapter).__name__}")
    print(f"  默认启用: {adapter.enable}")
    print(f"  最小样本: {adapter.MIN_SAMPLE_COUNT}")
    print(f"  评分上限: {adapter.MAX_SCORE}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Strategy Weight Load Test
print('[2] Strategy Weight Load Test')
try:
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import WeightAdapter

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    adapter = WeightAdapter(enable=True, weight_manager=wm)

    # 读取MACD金叉权重
    macd_weight = adapter.get_strategy_weight('MACD金叉')
    assert macd_weight['strategy'] == 'MACD金叉'
    assert macd_weight['source'] == 'learning'
    assert macd_weight['sample'] >= 10
    assert macd_weight['weight'] > 1.0  # 高胜率应该增强

    print(f"  MACD金叉:")
    print(f"    权重: {macd_weight['weight']}")
    print(f"    样本: {macd_weight['sample']}")
    print(f"    胜率: {macd_weight['win_rate']}%")
    print(f"    来源: {macd_weight['source']}")
    print(f"    已调整: {macd_weight['adjusted']}")

    # 读取三倍量突破权重
    triple_weight = adapter.get_strategy_weight('三倍量突破')
    print(f"\n  三倍量突破:")
    print(f"    权重: {triple_weight['weight']}")
    print(f"    样本: {triple_weight['sample']}")
    print(f"    胜率: {triple_weight['win_rate']}%")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Score Adjustment Test
print('[3] Score Adjustment Test')
try:
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import WeightAdapter

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    adapter = WeightAdapter(enable=True, weight_manager=wm)

    # MACD金叉：80分 × 权重>1 = 增强
    macd_result = adapter.adjust_score('MACD金叉', 80)
    assert macd_result['original_score'] == 80
    assert macd_result['adjusted_score'] > 80
    assert macd_result['score_change'] > 0
    assert macd_result['enabled'] == True

    print(f"  MACD金叉:")
    print(f"    原始评分: {macd_result['original_score']}")
    print(f"    动态权重: {macd_result['weight']}")
    print(f"    修正评分: {macd_result['adjusted_score']}")
    print(f"    评分变化: {macd_result['score_change']:+.1f}")
    print(f"    已启用: {macd_result['enabled']}")

    # 评分上限测试：95分 × 1.2 = 114 → 限制为100
    high_result = adapter.adjust_score('MACD金叉', 95)
    assert high_result['adjusted_score'] <= 100
    print(f"\n  上限测试: 95 × {high_result['weight']} = {high_result['adjusted_score']} (≤100)")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Small Sample Protection Test
print('[4] Small Sample Protection Test')
try:
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import WeightAdapter

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    adapter = WeightAdapter(enable=True, weight_manager=wm)

    # 回踩MA5只有5笔样本，应该保持权重1.0
    small_result = adapter.adjust_score('回踩MA5', 70)
    assert small_result['weight'] == 1.0
    assert small_result['adjusted_score'] == 70
    assert small_result['enabled'] == False
    assert '样本不足' in small_result['reason']

    print(f"  回踩MA5 (5笔样本):")
    print(f"    原始评分: {small_result['original_score']}")
    print(f"    动态权重: {small_result['weight']} (保持默认)")
    print(f"    修正评分: {small_result['adjusted_score']} (不变)")
    print(f"    已启用: {small_result['enabled']}")
    print(f"    原因: {small_result['reason']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Disable Switch Test
print('[5] Disable Switch Test')
try:
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import WeightAdapter

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)

    # 关闭状态
    adapter_off = WeightAdapter(enable=False, weight_manager=wm)
    result_off = adapter_off.adjust_score('MACD金叉', 80)
    assert result_off['enabled'] == False
    assert result_off['adjusted_score'] == 80
    assert result_off['weight'] == 1.0

    print(f"  关闭状态:")
    print(f"    原始评分: {result_off['original_score']}")
    print(f"    修正评分: {result_off['adjusted_score']} (不变)")
    print(f"    已启用: {result_off['enabled']}")

    # 开启状态
    adapter_on = WeightAdapter(enable=True, weight_manager=wm)
    result_on = adapter_on.adjust_score('MACD金叉', 80)
    assert result_on['enabled'] == True
    assert result_on['adjusted_score'] > 80

    print(f"\n  开启状态:")
    print(f"    原始评分: {result_on['original_score']}")
    print(f"    修正评分: {result_on['adjusted_score']} (增强)")
    print(f"    已启用: {result_on['enabled']}")

    # 运行时切换
    adapter_on.set_enable(False)
    result_switched = adapter_on.adjust_score('MACD金叉', 80)
    assert result_switched['enabled'] == False
    print(f"\n  运行时切换: 开启→关闭后修正评分={result_switched['adjusted_score']} (不变)")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] Decision Engine Integration Test
print('[6] Decision Engine Integration Test')
try:
    from backtest.learning import StrategyWeightManager
    from strategy.weight_adapter import WeightAdapter

    tm = build_memory()
    wm = StrategyWeightManager(trade_memory=tm)
    adapter = WeightAdapter(enable=True, weight_manager=wm)

    # 模拟decision_engine输出
    decision = {
        'code': '600519',
        'name': '贵州茅台',
        'strategy': 'MACD金叉',
        'score': 80,
        'rating': '重点观察',
        'action': '买入',
        'reason': 'MACD轴下金叉，量价配合',
    }

    # 完整链路：策略 → 权重 → 评分 → 决策
    enhanced = adapter.adjust_decision(decision)

    assert enhanced['original_score'] == 80
    assert enhanced['adjusted_score'] > 80
    assert enhanced['weight_enabled'] == True
    assert enhanced['score'] > 80  # score被覆盖为修正后的值

    print(f"  完整链路:")
    print(f"    股票: {enhanced['name']}({enhanced['code']})")
    print(f"    策略: {enhanced['strategy']}")
    print(f"    原始评分: {enhanced['original_score']}")
    print(f"    动态权重: {enhanced['dynamic_weight']}")
    print(f"    修正评分: {enhanced['adjusted_score']}")
    print(f"    评分变化: {enhanced['score_change']:+.1f}")
    print(f"    最终score: {enhanced['score']}")
    print(f"    权重启用: {enhanced['weight_enabled']}")
    print(f"    权重原因: {enhanced['weight_reason']}")

    # 批量调整测试
    decisions = [
        {'strategy': 'MACD金叉', 'score': 85, 'name': '股A'},
        {'strategy': '三倍量突破', 'score': 75, 'name': '股B'},
        {'strategy': '回踩MA5', 'score': 70, 'name': '股C'},
    ]
    batch_result = adapter.batch_adjust(decisions)
    assert len(batch_result) == 3
    print(f"\n  批量调整: {len(batch_result)}只股票")
    for d in batch_result:
        print(f"    {d['name']}: {d['original_score']}→{d['adjusted_score']} "
              f"(权重{d['dynamic_weight']}, 启用{d['weight_enabled']})")

    # 单例测试
    from strategy.weight_adapter import get_weight_adapter
    singleton1 = get_weight_adapter(enable=True)
    singleton2 = get_weight_adapter()
    assert singleton1 is singleton2
    print(f"\n  单例测试: singleton1 is singleton2 = {singleton1 is singleton2}")

    # 状态渲染
    print(f"\n{adapter.render_status()}")
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
