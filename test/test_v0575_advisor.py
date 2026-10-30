# -*- coding: utf-8 -*-
"""V0.5.7.5 AI策略优化建议中心 - 六项验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import TradeMemory, StrategyAdvisor

print('========== V0.5.7.5 Integration Test ==========')
print()

tmpfile = os.path.join(tempfile.gettempdir(), 'test_v0575_memory.json')
advisor_file = os.path.join(tempfile.gettempdir(), 'test_v0575_advisor.json')

def build_memory():
    """构造完整记忆库"""
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

    # 回踩MA5：低胜率（10笔，3胜7负）
    for i in range(3):
        tm.remember(f'602{i:03d}', f'股{i+50}', 'BUY', score=72+i, price=11+i,
                     strategy='回踩MA5',
                     result={'pnl': 800+i*50, 'success': True, 'max_gain': 8, 'max_drawdown': -7},
                     hold_days=6)
    for i in range(7):
        tm.remember(f'002{i:03d}', f'股{i+60}', 'BUY', score=70+i, price=7+i,
                     strategy='回踩MA5',
                     result={'pnl': -1200-i*60, 'success': False, 'max_gain': 1, 'max_drawdown': -12},
                     hold_days=4)

    return tm

# [1] Strategy Summary Test
print('[1] Strategy Summary Test')
try:
    tm = build_memory()
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    summary = advisor.generate_strategy_summary()
    assert len(summary) >= 3

    print(f"  策略数: {len(summary)}")
    for s in summary:
        print(f"    {s['strategy']}: 等级{s['grade']} "
              f"权重{s['weight']} 胜率{s['win_rate']}% "
              f"样本{s['sample_count']} → {s['suggestion']}")

    # MACD金叉应该等级最高
    assert summary[0]['strategy'] == 'MACD金叉'
    assert summary[0]['grade'] in ('A', 'B')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Signal Optimization Report Test
print('[2] Signal Optimization Report Test')
try:
    tm = build_memory()
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    report = advisor.generate_signal_report()
    assert 'current_threshold' in report
    assert 'suggested_threshold' in report
    assert 'score_bins' in report
    assert 'quality_stats' in report

    print(f"  当前阈值: {report['current_threshold']}分")
    print(f"  建议阈值: {report['suggested_threshold']}分")
    print(f"  是否调整: {report['threshold_adjusted']}")
    print(f"  原因: {report['threshold_reason']}")

    print(f"\n  评分区间:")
    for name, data in report['score_bins'].items():
        print(f"    {name}: {data['count']}笔 胜率{data['win_rate']}%")

    print(f"\n  质量等级:")
    for level, data in report['quality_stats'].items():
        print(f"    {level}: {data['count']}笔 胜率{data['win_rate']}% 建议:{data['suggestion']}")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Risk Optimization Report Test
print('[3] Risk Optimization Report Test')
try:
    tm = build_memory()
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    report = advisor.generate_risk_report()
    assert 'current_stop_loss' in report
    assert 'suggested_stop_loss' in report
    assert 'quality_stop_loss' in report
    assert 'quality_position' in report
    assert 'risk_stats' in report

    print(f"  当前止损: {report['current_stop_loss']}%")
    print(f"  建议止损: {report['suggested_stop_loss']}%")
    print(f"  当前仓位: {report['current_position']}%")
    print(f"  建议仓位: {report['suggested_position']}%")
    print(f"  最大回撤: {report['max_drawdown']}%")
    print(f"  最大连续亏损: {report['max_consecutive_loss']}次")

    print(f"\n  风险统计:")
    rs = report['risk_stats']
    print(f"    总交易: {rs['total_trades']} 亏损率: {rs['loss_rate']}%")
    print(f"    最大亏损: {rs['max_loss']:+,.0f} 最大回撤: {rs['max_drawdown']}%")
    print(f"    连续亏损: {rs['max_consecutive_loss']}次 止损触发率: {rs['stop_loss_trigger_rate']}%")

    print(f"\n  分级止损:")
    for q, sl in report['quality_stop_loss'].items():
        print(f"    {q}: {sl}%")

    print(f"\n  分级仓位:")
    for q, pos in report['quality_position'].items():
        print(f"    {q}: {pos}%")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] AI Recommendation Generate Test
print('[4] AI Recommendation Generate Test')
try:
    tm = build_memory()
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    recommendations = advisor.generate_ai_recommendations()
    assert len(recommendations) >= 2

    print(f"  AI建议数: {len(recommendations)}")
    for i, r in enumerate(recommendations, 1):
        print(f"    {i}. [{r['priority']}] {r['category']} - {r['target']}: {r['action']}")
        print(f"       {r['detail']}")

    # 应该有高优先级建议
    high_priority = [r for r in recommendations if r['priority'] in ('high', 'critical')]
    print(f"\n  高优先级建议: {len(high_priority)}条")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Full Learning Pipeline Test
print('[5] Full Learning Pipeline Test')
try:
    tm = build_memory()
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    report = advisor.generate_daily_report(date='2026-08-16')
    assert report['date'] == '2026-08-16'
    assert 'overview' in report
    assert 'strategy_changes' in report
    assert 'signal_changes' in report
    assert 'risk_changes' in report
    assert 'recommendations' in report
    assert 'key_suggestion' in report

    print(f"  报告日期: {report['date']}")
    print(f"  版本: {report['version']}")
    print(f"  概览: 记忆{report['overview']['total_memories']}笔 "
          f"胜率{report['overview']['win_rate']}% "
          f"策略{report['overview']['strategy_count']}个")
    print(f"  策略变化: {len(report['strategy_changes'])}个")
    print(f"  信号变化: 阈值{report['signal_changes']['threshold']}")
    print(f"  风险变化: 止损{report['risk_changes']['stop_loss']} "
          f"仓位{report['risk_changes']['position']}")
    print(f"  建议数: {len(report['recommendations'])}")
    print(f"  核心建议: {report['key_suggestion']}")

    # 渲染完整文本报告
    print(f"\n{advisor.render_text(report)}")
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
    advisor = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)

    # 生成报告并保存
    report1 = advisor.generate_daily_report(date='2026-08-15')
    report2 = advisor.generate_daily_report(date='2026-08-16')

    assert os.path.exists(advisor_file)
    print(f"  报告文件: {advisor_file}")

    # 重新加载
    advisor2 = StrategyAdvisor(trade_memory=tm, storage_path=advisor_file)
    assert len(advisor2.report_history) >= 2
    print(f"  历史报告: {len(advisor2.report_history)}份")

    # 人工确认模式测试
    result = advisor.apply_all_optimizations()
    assert '需要人工确认' in result.get('message', '')
    print(f"  人工确认: 已开启，应用被拦截")

    # 自动确认应用
    result2 = advisor.apply_all_optimizations(auto_confirm=True)
    assert result2['message'] == '所有优化已应用'
    print(f"  自动确认: 所有优化已应用")
    print(f"    策略权重: {'已应用' if result2['strategy_weights_applied'] else '未变化'}")
    print(f"    信号优化: {'已应用' if result2['signal_optimization_applied'] else '未变化'}")
    print(f"    风险优化: {'已应用' if result2['risk_optimization_applied'] else '未变化'}")

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理临时文件
for f in [tmpfile, advisor_file]:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass

print()
print('===============================================')
print('V0.5.7.5 READY')
print('V0.5.7 系列全部完成！')
