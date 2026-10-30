# -*- coding: utf-8 -*-
"""V0.5.7.1 AI交易记忆库 - 验收测试"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.learning import TradeMemory

print('========== V0.5.7.1 Integration Test ==========')
print()

# 使用临时文件避免污染真实数据
tmpfile = os.path.join(tempfile.gettempdir(), 'test_trade_memory.json')

# [1] 记忆库创建与记录测试
print('[1] Memory Create & Record Test')
try:
    tm = TradeMemory(storage_path=tmpfile)
    tm.clear()

    # 记录多笔交易记忆
    m1 = tm.remember('600580', '卧龙电驱', 'BUY', score=91, price=25,
                     strategy='三倍量突破', industry='电气设备',
                     result={'pnl': 3000, 'success': True, 'max_gain': 15, 'max_drawdown': -3},
                     reason=['三倍量', 'MACD金叉'], hold_days=5)
    m2 = tm.remember('000001', '平安银行', 'BUY', score=78, price=15,
                     strategy='回踩MA5', industry='银行',
                     result={'pnl': -2000, 'success': False, 'max_gain': 2, 'max_drawdown': -8},
                     reason=['回踩五日线'], hold_days=3)
    m3 = tm.remember('000510', '新金路', 'BUY', score=85, price=8,
                     strategy='MACD金叉', industry='化工',
                     result={'pnl': 4500, 'success': True, 'max_gain': 20, 'max_drawdown': -2},
                     reason=['MACD金叉', '放量'], hold_days=4)
    m4 = tm.remember('600330', '天通股份', 'BUY', score=72, price=12,
                     strategy='三倍量突破', industry='电子',
                     result={'pnl': -2000, 'success': False, 'max_gain': 3, 'max_drawdown': -10},
                     reason=['三倍量'], hold_days=2)
    m5 = tm.remember('000735', '罗牛山', 'BUY', score=95, price=10,
                     strategy='三倍量突破', industry='农业',
                     result={'pnl': 2500, 'success': True, 'max_gain': 18, 'max_drawdown': -4},
                     reason=['三倍量突破', '行业强势'], hold_days=6)

    assert len(tm.memories) == 5
    assert m1['quality'] == 'A+'
    assert m2['quality'] == 'B'
    print(f'  记录记忆: {len(tm.memories)}条')
    print(f'  质量分级: A+ {m1["quality"]}, B {m2["quality"]}, A {m3["quality"]}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] 多条件查询测试
print('[2] Multi-condition Query Test')
try:
    tm = TradeMemory(storage_path=tmpfile)

    # 按策略查询
    by_strategy = tm.query(strategy='三倍量突破')
    assert len(by_strategy) == 3
    print(f'  策略=三倍量突破: {len(by_strategy)}条')

    # 按成功查询
    successes = tm.query(success=True)
    assert len(successes) == 3
    print(f'  成功交易: {len(successes)}条')

    # 按质量查询
    a_plus = tm.query(quality='A+')
    assert len(a_plus) == 2
    print(f'  A+质量: {len(a_plus)}条')

    # 按最低评分
    high_score = tm.query(min_score=85)
    assert len(high_score) == 3
    print(f'  评分>=85: {len(high_score)}条')

    # 组合查询
    combo = tm.query(strategy='三倍量突破', success=True)
    assert len(combo) == 2
    print(f'  三倍量突破+成功: {len(combo)}条')

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] 相似案例检索测试
print('[3] Similar Case Retrieval Test')
try:
    tm = TradeMemory(storage_path=tmpfile)

    # 查找相似案例
    similar = tm.find_similar(strategy='三倍量突破', score=90, industry='电气设备', top_n=3)
    assert len(similar) > 0
    assert 'similarity' in similar[0]

    print(f'  查找相似案例(三倍量突破, 评分90, 电气设备):')
    for s in similar:
        print(f'    {s["code"]} {s["name"]} 相似度{s["similarity"]:.1%} '
              f'结果{"成功" if s["result"]["success"] else "失败"} 盈亏{s["result"]["pnl"]:+,.0f}')

    # 最相似的应该是卧龙电驱（同策略+同行业）
    assert similar[0]['code'] == '600580'
    print(f'  最相似: {similar[0]["name"]} (相似度{similar[0]["similarity"]:.1%})')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] 记忆库统计测试
print('[4] Memory Statistics Test')
try:
    tm = TradeMemory(storage_path=tmpfile)
    stats = tm.get_statistics()

    assert stats['total_memories'] == 5
    assert stats['buy_count'] == 5
    assert stats['success_count'] == 3
    assert stats['win_rate'] == 60.0
    assert stats['total_pnl'] == 6000

    print(f"  总记忆: {stats['total_memories']}")
    print(f"  买入: {stats['buy_count']} 成功: {stats['success_count']} 胜率: {stats['win_rate']}%")
    print(f"  总盈亏: {stats['total_pnl']:+,.0f} 平均: {stats['avg_pnl']:+,.0f}")
    print(f"  最大涨幅: {stats['max_gain']}% 最大回撤: {stats['max_drawdown']}%")

    print("\n  按策略:")
    for s, v in stats['by_strategy'].items():
        print(f"    {s}: {v['count']}次 胜率{v['win_rate']}% 盈亏{v['total_pnl']:+,.0f}")

    print("\n  按质量:")
    for q, v in stats['by_quality'].items():
        print(f"    {q}: {v['count']}次 胜率{v['win_rate']}%")

    print(tm.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] 学习洞察测试
print('[5] Learning Insights Test')
try:
    tm = TradeMemory(storage_path=tmpfile)
    insights = tm.get_learning_insights()

    assert 'best_strategy' in insights
    assert 'recommendations' in insights
    assert len(insights['recommendations']) > 0

    print(f"  最佳策略: {insights['best_strategy']}")
    print(f"  最差策略: {insights['worst_strategy']}")
    print(f"  最佳质量: {insights['best_quality']}")
    print(f"  学习建议: {len(insights['recommendations'])}条")
    for r in insights['recommendations']:
        print(f"    - {r}")

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] 持久化与导入导出测试
print('[6] Persistence & Export Test')
try:
    tm = TradeMemory(storage_path=tmpfile)

    # 验证文件已保存
    assert os.path.exists(tmpfile)
    print(f'  持久化文件: {tmpfile}')

    # 重新加载验证
    tm2 = TradeMemory(storage_path=tmpfile)
    assert len(tm2.memories) == 5
    print(f'  重新加载: {len(tm2.memories)}条记忆')

    # 导出
    export_path = tm.export()
    assert os.path.exists(export_path)
    print(f'  导出文件: {export_path}')

    # 从交易记录记忆
    trade = {'code': '600410', 'name': '华胜天成', 'side': 'sell',
             'price': 18, 'realized_pnl': 1500, 'ai_score': 88}
    signal = {'score': 88, 'strategy': 'AI决策', 'risk': 'low',
              'industry': 'IT', 'reason': ['AI评分高']}
    m = tm.remember_from_trade(trade, signal)
    assert m['code'] == '600410'
    assert m['result']['success'] == True
    print(f'  从交易记录记忆: {m["code"]} {m["name"]} 质量{m["quality"]}')

    # 清空
    tm.clear()
    assert len(tm.memories) == 0
    print(f'  清空后: {len(tm.memories)}条')

    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

# 清理临时文件
try:
    if os.path.exists(tmpfile):
        os.remove(tmpfile)
except Exception:
    pass

print()
print('===============================================')
print('V0.5.7.1 READY')
