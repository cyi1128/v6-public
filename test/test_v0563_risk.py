# -*- coding: utf-8 -*-
"""V0.5.6.3 实时风控 - 五项验收测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.risk import (
    RiskEvent, RiskLevel, RiskType, TradePermission, RiskReport,
    PositionRiskChecker, PortfolioRiskChecker, TradeGuard, RiskMonitor
)

print('========== V0.5.6.3 Integration Test ==========')
print()

# [1] Risk Model Test
print('[1] Risk Model Test')
try:
    e = RiskEvent('600580', '卧龙电驱', 'position_loss', 'high', '浮亏-9%', '减仓')
    assert e.level == RiskLevel.HIGH
    assert e.risk_type == RiskType.POSITION_LOSS
    d = e.to_dict()
    assert d['code'] == '600580' and d['level'] == 'high'
    p = TradePermission(True, '允许')
    assert p.allowed and not p.is_partial
    p2 = TradePermission(True, '部分', adjusted_quantity=1000)
    assert p2.is_partial
    p3 = TradePermission(False, '拒绝')
    assert not p3.allowed
    r = RiskReport()
    r.add(e)
    r.add(RiskEvent('000001', '平安', 'ma_break', 'critical', '跌破MA20', '卖出'))
    assert r.overall_level == RiskLevel.CRITICAL
    assert r.critical_count == 1 and r.high_count == 1
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Position Risk Test
print('[2] Position Risk Test')
try:
    pc = PositionRiskChecker(max_position_pct=0.30, stop_loss_pct=-0.08)
    pos = {'code': '600580', 'name': '卧龙', 'quantity': 1000,
           'avg_cost': 25, 'current_price': 22, 'market_value': 22000}
    events = pc.check(pos, 100000, {
        'ma5': 23, 'ma20': 24, 'recent_closes': [25, 24, 23, 22]
    })
    types = [e.risk_type for e in events]
    assert RiskType.POSITION_LOSS in types
    assert RiskType.MA_BREAK in types
    print(f'  检测到{len(events)}个风险事件')
    for e in events:
        print(f'    [{e.level.value}] {e.message}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Portfolio Risk Test
print('[3] Portfolio Risk Test')
try:
    prc = PortfolioRiskChecker(
        max_total_position_pct=0.80, max_positions=8, max_industry_pct=0.40)
    pf = {
        'total_value': 90000, 'position_count': 3,
        'positions': [
            {'code': '600580', 'market_value': 40000},
            {'code': '000001', 'market_value': 30000},
            {'code': '600330', 'market_value': 20000},
        ]
    }
    acc = {'total_asset': 100000, 'yesterday_asset': 105000}
    ind = {'600580': '科技', '000001': '科技', '600330': '银行'}
    events = prc.check(pf, acc, ind)
    types = [e.risk_type for e in events]
    assert RiskType.PORTFOLIO_EXPOSURE in types
    assert RiskType.PORTFOLIO_CONCENTRATION in types
    assert RiskType.DAILY_DRAWDOWN in types
    score = prc.calculate_risk_score(events)
    level = prc.get_risk_level(score)
    print(f'  检测到{len(events)}个风险, 评分{score}, 等级{level.value}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Trade Guard Test
print('[4] Trade Guard Test')
try:
    tg = TradeGuard(
        max_single_position_pct=0.30, max_total_position_pct=0.80,
        max_positions=5, blacklist={'000510'})
    acc = {'cash': 50000, 'total_asset': 100000}
    pf = {
        'positions': [{'code': '600580', 'market_value': 20000, 'available_qty': 1000}],
        'total_value': 20000, 'position_count': 1
    }
    # 正常买入
    p = tg.check_buy('600330', 10, 1000, acc, pf, '天通')
    assert p.allowed, p.reason
    # 黑名单
    p = tg.check_buy('000510', 5, 1000, acc, pf, '新金路')
    assert not p.allowed and '黑名单' in p.reason
    # 单票仓位超限
    p = tg.check_buy('600580', 25, 2000, acc, pf, '卧龙')
    assert p.is_partial or not p.allowed
    # 无持仓卖出
    p = tg.check_sell('999999', 1000, pf, '不存在')
    assert not p.allowed and '无持仓' in p.reason
    # 正常卖出
    p = tg.check_sell('600580', 500, pf, '卧龙')
    assert p.allowed
    print(f'  {tg.summary()}')
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Risk Monitor Full Pipeline Test
print('[5] Risk Monitor Full Pipeline Test')
try:
    rm = RiskMonitor(
        max_single_position_pct=0.30, max_total_position_pct=0.80,
        stop_loss_pct=-0.08)
    rm.update_account({
        'cash': 30000, 'total_asset': 100000, 'yesterday_asset': 100000})
    rm.update_portfolio({
        'positions': [
            {'code': '600580', 'name': '卧龙', 'quantity': 1000,
             'avg_cost': 25, 'current_price': 22, 'market_value': 22000,
             'available_qty': 1000},
            {'code': '000001', 'name': '平安', 'quantity': 2000,
             'avg_cost': 15, 'current_price': 16, 'market_value': 32000,
             'available_qty': 2000},
        ],
        'total_value': 54000, 'position_count': 2
    })
    rm.update_market({
        '600580': {'ma5': 23, 'ma20': 24, 'recent_closes': [25, 24, 23, 22]}
    })
    rm.update_industry({'600580': '科技', '000001': '银行'})
    report = rm.get_risk_report()
    summary = rm.get_risk_summary()
    print(f'  整体风险: {summary["overall_level"]} 评分{summary["risk_score"]}')
    print(f'  事件数: {summary["total_events"]} '
          f'(严重{summary["critical_count"]}高{summary["high_count"]}中{summary["medium_count"]})')
    bp = rm.check_buy_permission('600330', 10, 1000, '天通')
    print(f'  买入600330: {bp.summary()}')
    sp = rm.check_sell_permission('600580', 500, '卧龙')
    print(f'  卖出600580: {sp.summary()}')
    rm.print_risk_center()
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()
print('===============================================')
print('V0.5.6.3 READY')
