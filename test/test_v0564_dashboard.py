# -*- coding: utf-8 -*-
"""V0.5.6.4 模拟交易面板 - 六项验收测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.dashboard import (
    SignalView, AccountView, PositionView, RiskView,
    TradeHistoryView, TradingPanel
)
from backtest.simulation import SimulatedAccount, Portfolio, OrderManager, TradeLog
from backtest.simulation.signal_bridge import ExecutionService
from backtest.risk import RiskMonitor

print('========== V0.5.6.4 Integration Test ==========')
print()

# [1] UI模块导入测试
print('[1] UI Module Import Test')
try:
    sv = SignalView()
    av = AccountView()
    pv = PositionView()
    rv = RiskView()
    tv = TradeHistoryView()
    tp = TradingPanel()
    print('  所有6个模块导入成功')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] AI信号显示测试
print('[2] AI Signal Display Test')
try:
    sv = SignalView()
    decisions = [
        {'code': '600580', 'name': '卧龙电驱', 'score': 91, 'price': 25,
         'status': '确认买入', 'quality': 'A+', 'risk': 'low',
         'reason': ['三倍量突破', 'MACD金叉'], 'strategy': 'ai_decision'},
        {'code': '000001', 'name': '平安银行', 'score': 78, 'price': 15,
         'status': '重点关注', 'quality': 'A', 'risk': 'medium',
         'reason': ['回踩MA5'], 'strategy': 'ai_decision'},
        {'code': '000510', 'name': '新金路', 'score': 35, 'price': 8,
         'status': '风险提醒', 'quality': 'C', 'risk': 'high',
         'reason': ['跌破MA20'], 'strategy': 'ai_decision'},
    ]
    batch = sv.load_signals(decisions)
    signals = sv.get_display_signals()
    summary = sv.get_summary()
    assert len(signals) == 3
    assert summary['buy'] >= 1
    print(f'  信号数: {summary["total"]} (买{summary["buy"]} 卖{summary["sell"]} 观察{summary["hold"]})')
    for s in signals:
        print(f'    {s["code"]} {s["name"]} 评分{s["score"]:.0f} {s["action_cn"]} 风险{s["risk_level"]}')
    # 查看原因
    reason = sv.view_reason('600580')
    assert reason['success']
    print(f'  600580原因: {reason["reason"]}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] 模拟买卖按钮测试
print('[3] Simulated Buy/Sell Button Test')
try:
    tp = TradingPanel()
    decisions = [
        {'code': '600580', 'name': '卧龙电驱', 'score': 91, 'price': 25,
         'status': '确认买入', 'quality': 'A+', 'risk': 'low',
         'reason': ['x'], 'strategy': 'ai_decision'},
    ]
    tp.load_ai_signals(decisions)
    # 模拟买入
    result = tp.execute_signal_buy('600580')
    print(f'  买入600580: {result["success"]} {result.get("message", "")}')
    assert result['success']
    # 检查持仓
    positions = tp.position_view.get_display_positions()
    assert len(positions) >= 1
    print(f'  持仓数: {len(positions)}')
    # T+1后卖出
    tp.execution.portfolio.settle_t1()
    result = tp.execute_position_sell('600580')
    print(f'  卖出600580: {result["success"]} {result.get("message", "")}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] 持仓同步测试
print('[4] Position Sync Test')
try:
    acc = SimulatedAccount(1000000)
    pf = Portfolio(acc)
    pf.buy('600580', 1000, 25, '卧龙电驱')
    pf.buy('000001', 2000, 15, '平安银行')
    pf.update_prices({'600580': 28, '000001': 14})
    pv = PositionView(pf)
    positions = pv.get_display_positions()
    summary = pv.get_summary()
    assert len(positions) == 2
    assert summary['count'] == 2
    print(f'  持仓数: {summary["count"]} 市值{summary["total_value"]:,.0f} 浮盈{summary["total_pnl"]:+,.0f}')
    for p in positions:
        print(f'    {p["code"]} {p["name"]} 成本{p["avg_cost"]:.2f} 现价{p["current_price"]:.2f} '
              f'盈亏{p["unrealized_pnl_pct"]:+.1f}% 风险{p["risk_level"]}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] 风险数据显示测试
print('[5] Risk Data Display Test')
try:
    rm = RiskMonitor(max_single_position_pct=0.30, stop_loss_pct=-0.08)
    rm.update_account({'cash': 30000, 'total_asset': 100000, 'yesterday_asset': 100000})
    rm.update_portfolio({
        'positions': [
            {'code': '600580', 'name': '卧龙', 'quantity': 1000,
             'avg_cost': 25, 'current_price': 22, 'market_value': 22000,
             'available_qty': 1000},
        ],
        'total_value': 22000, 'position_count': 1
    })
    rm.update_market({'600580': {'ma5': 23, 'ma20': 24, 'recent_closes': [25, 24, 23, 22]}})
    rv = RiskView(rm)
    data = rv.get_display_data()
    assert data['total_events'] > 0
    assert data['critical_count'] >= 1  # 浮亏-12%触发止损
    print(f'  风险等级: {data["overall_level_cn"]} 评分{data["risk_score"]}/100')
    print(f'  事件: 严重{data["critical_count"]} 高{data["high_count"]} 中{data["medium_count"]}')
    print(f'  建议: {data["suggestion"]}')
    print(rv.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] 完整交易展示链路测试
print('[6] Full Trading Display Pipeline Test')
try:
    tp = TradingPanel()
    # 加载信号
    decisions = [
        {'code': '600580', 'name': '卧龙电驱', 'score': 91, 'price': 25,
         'status': '确认买入', 'quality': 'A+', 'risk': 'low',
         'reason': ['x'], 'strategy': 'ai_decision'},
        {'code': '000001', 'name': '平安银行', 'score': 82, 'price': 15,
         'status': '确认买入', 'quality': 'A', 'risk': 'low',
         'reason': ['x'], 'strategy': 'ai_decision'},
    ]
    tp.load_ai_signals(decisions)
    # 执行买入
    tp.execute_signal_buy('600580')
    tp.execute_signal_buy('000001')
    # T+1
    tp.execution.portfolio.settle_t1()
    tp.execution.portfolio.update_prices({'600580': 27, '000001': 16})
    # 刷新面板
    data = tp.refresh()
    assert 'account' in data
    assert 'positions' in data
    assert 'risk' in data
    assert 'signals' in data
    assert 'trades' in data
    print(f'  账户: 资产{data["account"]["total_asset"]:,.0f} 收益{data["account"]["total_return_pct"]:+.2f}%')
    print(f'  持仓: {len(data["positions"])}只')
    print(f'  风险: {data["risk"]["overall_level"]} 评分{data["risk"]["risk_score"]}')
    print(f'  信号: {len(data["signals"])}个')
    print(f'  交易: {len(data["trades"])}笔')
    print(f'  {tp.summary()}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()
print('===============================================')
print('V0.5.6.4 READY')
