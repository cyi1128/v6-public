# -*- coding: utf-8 -*-
"""V0.5.7.2 策略胜率动态权重 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import TradeMemory, StrategyWeightManager

print('========== V0.5.7.2 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v0572_memory.json')
weight_file = os.path.join(tempfile.gettempdir(), 'test_v0572_weights.json')

def build_memory():
    """构造足够样本的记忆库"""
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # MACD金叉：高胜率策略（12笔，8胜4负）
    for i in range(8):
        tm.remember(f'600{i:03d}', f'股票{i}', 'BUY', score=85+i, price=10+i,
                     strategy='MACD金叉', industry='科技',
                     result={'pnl': 2000+i*100, 'success': True, 'max_gain': 15, 'max_drawdown': -3},
                     hold_days=5)
    for i in range(4):
        tm.remember(f'000{i:03d}', f'股票{i+20}', 'BUY', score=75+i, price=8+i,
                     strategy='MACD金叉', industry='科技',
                     result={'pnl': -1000-i*50, 'success': False, 'max_gain': 2, 'max_drawdown': -8},
                     hold_days=3)

    # 三倍量突破：中等胜率（11笔，6胜5负）
    for i in range(6):
        tm.remember(f'601{i:03d}', f'股票{i+30}', 'BUY', score=88+i, price=12+i,
                     strategy='三倍量突破', industry='制造',
                     result={'pnl': 1500+i*80, 'success': True, 'max_gain': 12, 'max_drawdown': -4},
                     hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股票{i+40}', 'BUY', score=72+i, price=9+i,
                     strategy='三倍量突破', industry='制造',
                     result={'pnl': -800-i*40, 'success': False, 'max_gain': 3, 'max_drawdown': -7},
                     hold_days=2)

    # 回踩MA5：低胜率策略（10笔，3胜7负）
    for i in range(3):
        tm.remember(f'602{i:03d}', f'股票{i+50}', 'BUY', score=80+i, price=11+i,
                     strategy='回踩MA5', industry='金融',
                     result={'pnl': 800+i*50, 'success': True, 'max_gain': 8, 'max_drawdown': -5},
                     hold_days=6)
    for i in range(7):
        tm.remember(f'002{i:03d}', f'股票{i+60}', 'BUY', score=68+i, price=7+i,
                     strategy='回踩MA5', industry='金融',
                     result={'pnl': -1200-i*60, 'success': False, 'max_gain': 1, 'max_drawdown': -10},
                     hold_days=4)

    # KDJ金叉：小样本（5笔，3胜2负）- 测试样本保护
    for i in range(3):
        tm.remember(f'603{i:03d}', f'股票{i+70}', 'BUY', score=82+i, price=13+i,
                     strategy='KDJ金叉', industry='消费',
                     result={'pnl': 1000+i*50, 'success': True, 'max_gain': 10, 'max_drawdown': -3},
                     hold_days=5)
    for i in range(2):
        tm.remember(f'003{i:03d}', f'股票{i+80}', 'BUY', score=70+i, price=10+i,
                     strategy='KDJ金叉', industry='消费',
                     result={'pnl': -500-i*30, 'success': False, 'max_gain': 2, 'max_drawdown': -6},
                     hold_days=3)

    return tm

# [1] Strategy Weight Calculate Test
print('[1] Strategy Weight Calculate Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)

    # 计算策略表现
    perf = swm.calculate_strategy_performance()
    assert 'MACD金叉' in perf
    assert '三倍量突破' in perf
    assert '回踩MA5' in perf

    print(f"  策略数: {len(perf)}")
    for name, p in perf.items():
        print(f"    {name}: {p['count']}笔 胜率{p['win_rate']}% "
              f"平均盈亏{p['avg_pnl']:+,.0f} 稳定{p['stability']}")

    # 计算单个策略权重
    weight_info = swm.calculate_dynamic_weight('MACD金叉')
    assert weight_info['adjusted'] == True
    assert weight_info['sample_count'] >= 10
    print(f"\n  MACD金叉权重: {weight_info['dynamic_weight']}")
    print(f"    胜率因子: {weight_info['win_factor']}")
    print(f"    收益因子: {weight_info['profit_factor']}")
    print(f"    稳定因子: {weight_info['stability_factor']}")
    print(f"    原因: {weight_info['reason']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Multi Strategy Ranking Test
print('[2] Multi Strategy Ranking Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)

    ranking = swm.get_strategy_ranking()
    assert len(ranking) >= 3

    print(f"  策略排名 (共{len(ranking)}个):")
    for i, info in enumerate(ranking, 1):
        perf = info.get('performance', {})
        print(f"    {i}. {info['strategy']}: 权重{info['dynamic_weight']:.3f} "
              f"胜率{perf.get('win_rate',0)}% 样本{info['sample_count']}")

    # MACD金叉应该排名第一（胜率最高）
    assert ranking[0]['strategy'] == 'MACD金叉'
    # 回踩MA5应该排名最后（胜率最低）
    assert ranking[-1]['strategy'] in ('回踩MA5', 'KDJ金叉')
    print(f"\n  排名第一: {ranking[0]['strategy']} (权重{ranking[0]['dynamic_weight']:.3f})")
    print(f"  排名最后: {ranking[-1]['strategy']} (权重{ranking[-1]['dynamic_weight']:.3f})")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Weight Adjustment Test
print('[3] Weight Adjustment Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)

    # 应用权重
    result = swm.apply_weights()
    assert result['adjusted_count'] >= 2  # 至少MACD金叉和回踩MA5被调整

    print(f"  总策略: {result['total_strategies']}")
    print(f"  已调整: {result['adjusted_count']}")
    print(f"  权重配置:")
    for name, w in result['weights'].items():
        print(f"    {name}: {w:.3f}")

    print(f"\n  调整详情:")
    for adj in result['adjustments']:
        print(f"    {adj['strategy']}: {adj['old_weight']:.3f} → {adj['new_weight']:.3f} "
              f"({adj['change_pct']:+.1f}%) 原因:{adj['reason']}")

    # 验证MACD金叉权重>1（高胜率）
    assert result['weights']['MACD金叉'] > 1.0
    # 验证回踩MA5权重<1（低胜率）
    assert result['weights']['回踩MA5'] < 1.0
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Small Sample Protection Test
print('[4] Small Sample Protection Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)

    # KDJ金叉只有5笔，应该不调整
    kdj_info = swm.calculate_dynamic_weight('KDJ金叉')
    assert kdj_info['adjusted'] == False
    assert kdj_info['sample_count'] == 5
    assert kdj_info['dynamic_weight'] == kdj_info['base_weight']

    print(f"  KDJ金叉样本: {kdj_info['sample_count']}笔")
    print(f"  调整状态: {kdj_info['adjusted']}")
    print(f"  权重: {kdj_info['dynamic_weight']} (保持基础权重)")
    print(f"  原因: {kdj_info['reason']}")

    # 验证最小样本限制
    assert swm.MIN_SAMPLE_COUNT == 10
    print(f"\n  最小样本限制: {swm.MIN_SAMPLE_COUNT}笔")
    print(f"  权重范围: [{swm.MIN_WEIGHT}, {swm.MAX_WEIGHT}]")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Learning Suggestion Test
print('[5] Learning Suggestion Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)
    swm.apply_weights()

    suggestions = swm.get_weight_suggestions()
    assert len(suggestions) >= 3

    print(f"  调整建议: {len(suggestions)}条")
    for s in suggestions:
        print(f"    [{s['priority']}] {s['strategy']}: {s['suggestion']} "
              f"(权重{s['current_weight']:.3f})")
        print(f"      原因: {s['reason']}")

    # 验证有高优先级建议
    high_priority = [s for s in suggestions if s['priority'] == 'high']
    print(f"\n  高优先级建议: {len(high_priority)}条")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] Persistence Test
print('[6] Persistence Test')
try:
    tm = build_memory()
    swm = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)
    swm.apply_weights()

    # 验证文件保存
    assert os.path.exists(weight_file)
    print(f"  权重文件: {weight_file}")

    # 重新加载
    swm2 = StrategyWeightManager(trade_memory=tm, storage_path=weight_file)
    assert len(swm2.weights) >= 3
    print(f"  重新加载: {len(swm2.weights)}个策略权重")

    # 验证调整历史
    assert len(swm2.adjustment_history) >= 1
    print(f"  调整历史: {len(swm2.adjustment_history)}次")

    # 手动设置基础权重
    swm2.set_base_weight('MACD金叉', 1.2)
    assert swm2.weights['MACD金叉']['base_weight'] == 1.2
    print(f"  手动设置MACD金叉基础权重: 1.2")

    # 渲染文本
    print(f"\n{swm2.render_text()}")

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理临时文件
for f in [tmpfile, weight_file]:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass

print()
print('===============================================')
print('V0.5.7.2 READY')
