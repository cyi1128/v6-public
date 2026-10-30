# -*- coding: utf-8 -*-
"""V0.5.7.4 风险参数自适应 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import TradeMemory, RiskOptimizer

print('========== V0.5.7.4 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v0574_memory.json')
risk_file = os.path.join(tempfile.gettempdir(), 'test_v0574_risk.json')

def build_memory():
    """构造包含亏损/回撤/连续亏损的记忆库"""
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # A+高评分：胜率高，回撤小（12笔，9胜3负）
    for i in range(9):
        tm.remember(f'600{i:03d}', f'股{i}', 'BUY', score=92+i%5, price=10+i,
                     strategy='MACD金叉',
                     result={'pnl': 2500+i*100, 'success': True,
                             'max_gain': 15+i, 'max_drawdown': -3-i%2},
                     hold_days=5)
    for i in range(3):
        tm.remember(f'000{i:03d}', f'股{i+20}', 'BUY', score=90+i, price=8+i,
                     strategy='三倍量',
                     result={'pnl': -800-i*50, 'success': False,
                             'max_gain': 2, 'max_drawdown': -6-i},
                     hold_days=3)

    # A中等评分：胜率中等，回撤中等（10笔，5胜5负）
    for i in range(5):
        tm.remember(f'601{i:03d}', f'股{i+30}', 'BUY', score=82+i%5, price=12+i,
                     strategy='MACD金叉',
                     result={'pnl': 1500+i*80, 'success': True,
                             'max_gain': 12, 'max_drawdown': -5-i%2},
                     hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股{i+40}', 'BUY', score=80+i, price=9+i,
                     strategy='回踩MA5',
                     result={'pnl': -1000-i*60, 'success': False,
                             'max_gain': 3, 'max_drawdown': -8-i},
                     hold_days=2)

    # B低评分：胜率低，回撤大（8笔，2胜6负，含连续亏损）
    for i in range(2):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=72+i, price=11+i,
                     strategy='KDJ金叉',
                     result={'pnl': 800+i*50, 'success': True,
                             'max_gain': 8, 'max_drawdown': -7},
                     hold_days=6)
    for i in range(6):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=70+i, price=7+i,
                     strategy='回踩MA5',
                     result={'pnl': -1500-i*80, 'success': False,
                             'max_gain': 1, 'max_drawdown': -12-i},
                     hold_days=4)

    return tm

# [1] Risk Statistics Test
print('[1] Risk Statistics Test')
try:
    tm = build_memory()
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    stats = ro.analyze_risk_statistics()
    assert stats['total_trades'] == 30
    assert stats['loss_count'] == 14
    assert stats['max_consecutive_loss'] >= 3  # B级有6连亏

    print(f"  总交易: {stats['total_trades']}")
    print(f"  亏损: {stats['loss_count']} 亏损率: {stats['loss_rate']}%")
    print(f"  最大亏损: {stats['max_loss']:+,.0f}")
    print(f"  平均亏损: {stats['avg_loss']:+,.0f}")
    print(f"  最大回撤: {stats['max_drawdown']}%")
    print(f"  平均回撤: {stats['avg_drawdown']}%")
    print(f"  最大连续亏损: {stats['max_consecutive_loss']}次")
    print(f"  止损触发率: {stats['stop_loss_trigger_rate']}%")

    print(f"\n  按质量亏损:")
    for q, d in stats['loss_by_quality'].items():
        print(f"    {q}: {d['count']}次 总亏损{d['total_loss']:+,.0f} 最大回撤{d['max_drawdown']}%")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Stop Loss Optimization Test
print('[2] Stop Loss Optimization Test')
try:
    tm = build_memory()
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    result = ro.optimize_stop_loss()
    assert 'current_stop_loss' in result
    assert 'suggested_stop_loss' in result
    assert 'quality_stop_loss' in result

    print(f"  当前止损: {result['current_stop_loss']}%")
    print(f"  建议止损: {result['suggested_stop_loss']}%")
    print(f"  整体调整: {result['overall_adjusted']}")
    print(f"  原因: {result['reason']}")

    print(f"\n  分级止损:")
    for q, sl in result['quality_stop_loss'].items():
        print(f"    {q}: {sl}%")

    if result['quality_changes']:
        print(f"\n  分级调整:")
        for c in result['quality_changes']:
            print(f"    {c['quality']}: {c['old_stop_loss']}% → {c['new_stop_loss']}% "
                  f"(回撤{c['avg_drawdown']}%)")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Position Adjustment Test
print('[3] Position Adjustment Test')
try:
    tm = build_memory()
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    result = ro.optimize_position()
    assert 'current_position' in result
    assert 'suggested_position' in result
    assert 'quality_position' in result

    print(f"  当前仓位: {result['current_position']}%")
    print(f"  建议仓位: {result['suggested_position']}%")
    print(f"  整体调整: {result['overall_adjusted']}")

    print(f"\n  分级仓位:")
    for q, pos in result['quality_position'].items():
        print(f"    {q}: {pos}%")

    if result['quality_changes']:
        print(f"\n  分级调整:")
        for c in result['quality_changes']:
            print(f"    {c['quality']}: {c['old_position']}% → {c['new_position']}% "
                  f"(胜率{c['win_rate']}%)")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Drawdown Protection Test
print('[4] Drawdown Protection Test')
try:
    tm = build_memory()
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    result = ro.optimize_drawdown_protection()
    assert 'current_max_consecutive_loss' in result
    assert 'suggested_max_consecutive_loss' in result
    assert 'current_max_drawdown' in result
    assert 'suggested_max_drawdown' in result

    print(f"  当前最大连续亏损: {result['current_max_consecutive_loss']}次")
    print(f"  建议最大连续亏损: {result['suggested_max_consecutive_loss']}次")
    print(f"  历史最大连续亏损: {result['historical_max_consecutive']}次")
    print(f"  当前最大回撤: {result['current_max_drawdown']}%")
    print(f"  建议最大回撤: {result['suggested_max_drawdown']}%")
    print(f"  历史最大回撤: {result['historical_max_drawdown']}%")
    print(f"  是否调整: {result['adjusted']}")
    print(f"  原因: {result['reason']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Risk Suggestion Test
print('[5] Risk Suggestion Test')
try:
    tm = build_memory()
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    suggestions = ro.get_risk_suggestions()
    assert len(suggestions) >= 2

    print(f"  风险建议: {len(suggestions)}条")
    for s in suggestions:
        print(f"    [{s['priority']}] {s['type']}: {s['reason']}")

    # 人工确认模式
    ro.set_manual_confirm = True if hasattr(ro, 'set_manual_confirm') else None
    if hasattr(ro, 'config'):
        ro.config['manual_confirm'] = True
    applied = ro.apply_optimization()
    assert '需要人工确认' in applied.get('message', '')
    print(f"\n  人工确认模式: 已开启，应用被拦截")
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
    ro = RiskOptimizer(trade_memory=tm, storage_path=risk_file)

    # 修改配置
    ro.config['stop_loss'] = -7.0
    ro.config['position_pct'] = 18.0
    ro.config['manual_confirm'] = False
    ro._save()

    assert os.path.exists(risk_file)
    print(f"  配置文件: {risk_file}")

    # 重新加载
    ro2 = RiskOptimizer(trade_memory=tm, storage_path=risk_file)
    assert ro2.config['stop_loss'] == -7.0
    assert ro2.config['position_pct'] == 18.0
    assert ro2.config['manual_confirm'] == False
    print(f"  重新加载: 止损{ro2.config['stop_loss']}% 仓位{ro2.config['position_pct']}%")

    # 应用优化
    ro2.apply_optimization(auto_confirm=True)
    assert len(ro2.optimization_history) >= 1
    print(f"  优化历史: {len(ro2.optimization_history)}次")

    # 渲染文本
    print(f"\n{ro2.render_text()}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理临时文件
for f in [tmpfile, risk_file]:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass

print()
print('===============================================')
print('V0.5.7.4 READY')
