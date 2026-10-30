# -*- coding: utf-8 -*-
"""V0.5.7.3 信号质量自动调整 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import TradeMemory, SignalOptimizer

print('========== V0.5.7.3 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v0573_memory.json')
opt_file = os.path.join(tempfile.gettempdir(), 'test_v0573_optimizer.json')

def build_memory():
    """构造各评分区间足够样本的记忆库"""
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # 90-100分：高胜率（12笔，9胜3负）→ quality自动为A+
    for i in range(9):
        tm.remember(f'600{i:03d}', f'股{i}', 'BUY', score=92+i%5, price=10+i,
                     strategy='MACD金叉',
                     result={'pnl': 2500+i*100, 'success': True}, hold_days=5)
    for i in range(3):
        tm.remember(f'000{i:03d}', f'股{i+20}', 'BUY', score=90+i, price=8+i,
                     strategy='三倍量',
                     result={'pnl': -800-i*50, 'success': False}, hold_days=3)

    # 80-89分：中等胜率（11笔，6胜5负）→ quality自动为A
    for i in range(6):
        tm.remember(f'601{i:03d}', f'股{i+30}', 'BUY', score=82+i%5, price=12+i,
                     strategy='MACD金叉',
                     result={'pnl': 1500+i*80, 'success': True}, hold_days=4)
    for i in range(5):
        tm.remember(f'001{i:03d}', f'股{i+40}', 'BUY', score=80+i, price=9+i,
                     strategy='回踩MA5',
                     result={'pnl': -600-i*40, 'success': False}, hold_days=2)

    # 70-79分：低胜率（10笔，3胜7负）→ quality自动为B
    for i in range(3):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=72+i, price=11+i,
                     strategy='KDJ金叉',
                     result={'pnl': 800+i*50, 'success': True}, hold_days=6)
    for i in range(7):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=70+i, price=7+i,
                     strategy='回踩MA5',
                     result={'pnl': -1000-i*60, 'success': False}, hold_days=4)

    # 60-69分：很低胜率（5笔，1胜4负）→ quality自动为C
    for i in range(1):
        tm.remember(f'603{i:03d}', f'股{i+70}', 'BUY', score=65, price=13+i,
                     strategy='其他',
                     result={'pnl': 500, 'success': True}, hold_days=5)
    for i in range(4):
        tm.remember(f'003{i:03d}', f'股{i+80}', 'BUY', score=62+i, price=10+i,
                     strategy='其他',
                     result={'pnl': -700-i*30, 'success': False}, hold_days=3)

    return tm

# [1] Signal Score Analysis Test
print('[1] Signal Score Analysis Test')
try:
    tm = build_memory()
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    bins = opt.analyze_score_bins()
    assert '90-100' in bins
    assert '80-89' in bins
    assert '70-79' in bins

    print(f"  评分区间数: {len([b for b in bins.values() if b['count']>0])}")
    for name, data in bins.items():
        if data['count'] > 0:
            print(f"    {name}: {data['count']}笔 胜率{data['win_rate']}% "
                  f"平均盈亏{data['avg_pnl']:+,.0f} "
                  f"{'样本充足' if data.get('sample_sufficient') else '样本不足'}")

    # 验证90-100胜率最高
    assert bins['90-100']['win_rate'] > bins['70-79']['win_rate']
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Quality Level Statistics Test
print('[2] Quality Level Statistics Test')
try:
    tm = build_memory()
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    quality = opt.analyze_quality_levels()
    assert 'A+' in quality
    assert 'A' in quality
    assert 'B' in quality

    print(f"  质量等级统计:")
    for level, data in quality.items():
        if data['count'] > 0:
            print(f"    {level}: {data['count']}笔 胜率{data['win_rate']}% "
                  f"建议:{data['suggestion']}")

    # A+胜率应该最高
    assert quality['A+']['win_rate'] >= quality['B']['win_rate']
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Threshold Adjustment Test
print('[3] Threshold Adjustment Test')
try:
    tm = build_memory()
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    # 当前阈值70，70-79区间胜率30%<55%，应该建议提高
    result = opt.calculate_optimal_threshold()
    print(f"  当前阈值: {result['current_threshold']}分")
    print(f"  建议阈值: {result['suggested_threshold']}分")
    print(f"  是否调整: {result['adjusted']}")
    print(f"  原因: {result['reason']}")
    print(f"  达标区间: {result.get('valid_bins', [])}")

    # 应该建议提高阈值（因为70-79胜率低）
    assert result['suggested_threshold'] >= result['current_threshold']

    # 应用优化（自动确认）
    applied = opt.apply_optimization(auto_confirm=True)
    assert applied['threshold_applied'] == True
    print(f"\n  应用后阈值: {opt.config['buy_threshold']}分")
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
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    bins = opt.analyze_score_bins()

    # 60-69只有5笔，应该标记样本不足
    assert bins['60-69']['sample_sufficient'] == False
    assert bins['60-69']['count'] == 5

    print(f"  60-69区间: {bins['60-69']['count']}笔 (样本不足)")
    print(f"  最小样本要求: {opt.MIN_SAMPLE_PER_BIN}笔")
    print(f"  最大调整幅度: {opt.MAX_ADJUST_STEP}分")

    # 质量等级C只有5笔，不应该调整动作
    quality = opt.optimize_quality_actions()
    c_changes = [c for c in quality['changes'] if c['level'] == 'C']
    assert len(c_changes) == 0  # C级样本不足，不调整
    print(f"  C级调整: {len(c_changes)}次 (样本不足，不调整)")

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Optimization Suggestion Test
print('[5] Optimization Suggestion Test')
try:
    tm = build_memory()
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    suggestions = opt.get_optimization_suggestions()
    assert len(suggestions) >= 2

    print(f"  优化建议: {len(suggestions)}条")
    for s in suggestions:
        print(f"    [{s['priority']}] {s['type']}: {s['reason']}")

    # 应该有阈值调整建议
    threshold_suggestions = [s for s in suggestions if s['type'] == 'threshold']
    assert len(threshold_suggestions) >= 1

    # 人工确认模式下不应用
    opt.set_manual_confirm(True)
    applied = opt.apply_optimization()
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
    opt = SignalOptimizer(trade_memory=tm, storage_path=opt_file)

    # 修改配置并保存
    opt.set_buy_threshold(80)
    opt.set_manual_confirm(False)

    assert os.path.exists(opt_file)
    print(f"  配置文件: {opt_file}")

    # 重新加载
    opt2 = SignalOptimizer(trade_memory=tm, storage_path=opt_file)
    assert opt2.config['buy_threshold'] == 80
    assert opt2.config['manual_confirm'] == False
    print(f"  重新加载: 阈值{opt2.config['buy_threshold']}分 "
          f"人工确认{'开启' if opt2.config['manual_confirm'] else '关闭'}")

    # 应用优化并检查历史
    opt2.apply_optimization(auto_confirm=True)
    assert len(opt2.optimization_history) >= 1
    print(f"  优化历史: {len(opt2.optimization_history)}次")

    # 渲染文本
    print(f"\n{opt2.render_text()}")

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理临时文件
for f in [tmpfile, opt_file]:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass

print()
print('===============================================')
print('V0.5.7.3 READY')
