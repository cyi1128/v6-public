# -*- coding: utf-8 -*-
"""V0.5.6.5 交易复盘报告 - 六项验收测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.report import (
    TradeAnalyzer, SignalAccuracyAnalyzer, StrategyAttribution,
    RiskAttribution, DailyReportGenerator, ReportManager
)
from backtest.simulation import SimulatedAccount, Portfolio, TradeLog
from backtest.simulation.signal_bridge.signal_model import TradeSignal

print('========== V0.5.6.5 Integration Test ==========')
print()

# 构造测试数据
class MockTradeLog:
    """模拟TradeLog，返回带strategy/reason的dict列表"""
    def __init__(self, trades):
        self._trades = trades
    def get_trades(self, code=None, side=None, start_date=None, end_date=None):
        result = []
        for t in self._trades:
            if code and t.get('code') != code:
                continue
            if side and t.get('side') != side:
                continue
            result.append(t)
        return result

def make_trade_log():
    trades = [
        {'code': '600580', 'name': '卧龙电驱', 'side': 'buy', 'price': 25, 'quantity': 1000, 'time': '2026-08-10 09:35', 'strategy': '三倍量突破', 'realized_pnl': 0},
        {'code': '600580', 'name': '卧龙电驱', 'side': 'sell', 'price': 28, 'quantity': 1000, 'time': '2026-08-15 14:20', 'realized_pnl': 3000, 'strategy': '三倍量突破', 'reason': '止盈'},
        {'code': '000001', 'name': '平安银行', 'side': 'buy', 'price': 15, 'quantity': 2000, 'time': '2026-08-11 10:00', 'strategy': '回踩MA5', 'realized_pnl': 0},
        {'code': '000001', 'name': '平安银行', 'side': 'sell', 'price': 14, 'quantity': 2000, 'time': '2026-08-14 14:50', 'realized_pnl': -2000, 'strategy': '回踩MA5', 'reason': '止损触发跌破MA20'},
        {'code': '000510', 'name': '新金路', 'side': 'buy', 'price': 8, 'quantity': 3000, 'time': '2026-08-12 09:45', 'strategy': 'MACD金叉', 'realized_pnl': 0},
        {'code': '000510', 'name': '新金路', 'side': 'sell', 'price': 9.5, 'quantity': 3000, 'time': '2026-08-16 14:30', 'realized_pnl': 4500, 'strategy': 'MACD金叉', 'reason': '止盈'},
        {'code': '600330', 'name': '天通股份', 'side': 'buy', 'price': 12, 'quantity': 2000, 'time': '2026-08-13 10:30', 'strategy': '三倍量突破', 'realized_pnl': 0},
        {'code': '600330', 'name': '天通股份', 'side': 'sell', 'price': 11, 'quantity': 2000, 'time': '2026-08-15 14:00', 'realized_pnl': -2000, 'strategy': '三倍量突破', 'reason': '止损触发'},
    ]
    return MockTradeLog(trades)

def make_account():
    """构造测试账户"""
    acc = SimulatedAccount(1000000)
    acc.update_position_value(37300)  # 持仓市值37300，总资产1037300
    return acc

# [1] Trade Analyzer Test
print('[1] Trade Analyzer Test')
try:
    tl = make_trade_log()
    analyzer = TradeAnalyzer(tl)
    result = analyzer.analyze()
    assert result['total_trades'] == 4  # 4笔卖出
    assert result['win_count'] == 2
    assert result['loss_count'] == 2
    assert result['win_rate'] == 50.0
    assert result['total_pnl'] == 3500
    print(f"  总交易: {result['total_trades']} 胜率: {result['win_rate']}%")
    print(f"  盈亏比: {result['profit_loss_ratio']} 总盈亏: {result['total_pnl']:+,.0f}")
    print(f"  最大盈利: {result['max_win']:+,.0f} 最大亏损: {result['max_loss']:+,.0f}")
    print(analyzer.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [2] Signal Accuracy Test
print('[2] Signal Accuracy Test')
try:
    sa = SignalAccuracyAnalyzer()
    # 记录信号及结果
    signals = [
        TradeSignal('600580', '卧龙电驱', 'BUY', score=91, price=25, strategy='三倍量突破'),
        TradeSignal('000001', '平安银行', 'BUY', score=78, price=15, strategy='回踩MA5'),
        TradeSignal('000510', '新金路', 'BUY', score=85, price=8, strategy='MACD金叉'),
        TradeSignal('600330', '天通股份', 'BUY', score=72, price=12, strategy='三倍量突破'),
    ]
    results = [
        {'pnl': 3000, 'success': True},
        {'pnl': -2000, 'success': False},
        {'pnl': 4500, 'success': True},
        {'pnl': -2000, 'success': False},
    ]
    for sig, res in zip(signals, results):
        sa.record_signal(sig, res)

    result = sa.analyze()
    assert result['total_signals'] == 4
    assert result['buy_signals'] == 4
    assert result['overall_accuracy'] == 50.0
    print(f"  总信号: {result['total_signals']} 准确率: {result['overall_accuracy']}%")
    print(f"  买入成功: {result['buy_analysis']['success']}/{result['buy_analysis']['count']}")
    if result['quality_stats']:
        for q, s in result['quality_stats'].items():
            print(f"    {q}: {s['count']}次 成功率{s['success_rate']}%")
    print(sa.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [3] Strategy Attribution Test
print('[3] Strategy Attribution Test')
try:
    tl = make_trade_log()
    sa = StrategyAttribution(tl)
    result = sa.analyze()
    assert result['strategy_count'] >= 2
    assert result['total_pnl'] == 3500
    print(f"  策略数: {result['strategy_count']} 总盈亏: {result['total_pnl']:+,.0f}")
    print(f"  最佳: {result['best_strategy']} ({result['best_pnl']:+,.0f})")
    print(f"  最差: {result['worst_strategy']} ({result['worst_pnl']:+,.0f})")
    for name, info in result['sorted']:
        print(f"    {name}: {info['sell_count']}笔 胜率{info['win_rate']}% "
              f"盈亏{info['total_pnl']:+,.0f} 贡献{info['contribution_pct']}%")
    # AI学习数据
    learning = sa.get_ai_learning_data()
    print(f"  AI学习建议: {len(learning['recommendations'])}条")
    print(sa.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [4] Risk Attribution Test
print('[4] Risk Attribution Test')
try:
    tl = make_trade_log()
    ra = RiskAttribution(tl)
    # 添加风险事件
    ra.add_risk_event({'code': '600580', 'name': '卧龙', 'level': 'medium',
                       'risk_type': '跌破均线', 'message': '跌破MA5'})
    ra.add_risk_event({'code': '000001', 'name': '平安', 'level': 'high',
                       'risk_type': '止损触发', 'message': '浮亏触发止损'})
    result = ra.analyze()
    assert result['loss_analysis']['loss_count'] == 2
    assert result['loss_analysis']['total_loss'] == -4000
    assert result['event_analysis']['total'] == 2
    print(f"  主要风险: {result['main_risk']}")
    print(f"  亏损次数: {result['loss_analysis']['loss_count']} "
          f"总亏损: {result['loss_analysis']['total_loss']:+,.0f}")
    ml = result['loss_analysis']['max_loss_trade']
    print(f"  最大亏损: {ml.get('code','')} {ml.get('pnl',0):+,.0f} 原因:{ml.get('reason','')}")
    print(f"  风险事件: {result['event_analysis']['total']}个")
    print(ra.render_text())
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [5] Daily Report Generate Test
print('[5] Daily Report Generate Test')
try:
    acc = make_account()
    tl = make_trade_log()
    drg = DailyReportGenerator(acc, tl)
    report = drg.generate(date='2026-08-16')
    assert report['date'] == '2026-08-16'
    assert 'account' in report
    assert 'trade_stats' in report
    assert 'suggestions' in report
    print(f"  日期: {report['date']}")
    print(f"  账户: 资产{report['account']['total_asset']:,.0f} "
          f"收益{report['account']['total_return_pct']:+.2f}%")
    print(f"  交易: {report['trade_stats']['total_trades']}笔 "
          f"胜率{report['trade_stats']['win_rate']}%")
    print(f"  明日建议: {len(report['suggestions'])}条")
    for s in report['suggestions']:
        print(f"    - {s}")
    print(drg.render_text(report))
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()

# [6] Full Report Pipeline Test
print('[6] Full Report Pipeline Test')
try:
    acc = make_account()
    tl = make_trade_log()
    rm = ReportManager(acc, tl)

    # 生成每日报告
    daily = rm.generate_daily_report(date='2026-08-16')
    assert daily['report_type'] == 'daily'

    # 生成周报告
    weekly = rm.generate_weekly_report(end_date='2026-08-16')
    assert weekly['report_type'] == 'weekly'

    # 获取策略汇总
    strategy = rm.get_strategy_summary()
    assert strategy['strategy_count'] >= 2

    # 获取AI学习数据
    learning = rm.get_ai_learning_data()
    assert 'overall_performance' in learning
    assert 'signal_quality' in learning
    assert 'strategy_performance' in learning

    # 导出报告
    filepath = rm.export_report(daily, format='json', filename='test_daily.json')
    assert os.path.exists(filepath)

    # 历史记录
    history = rm.get_history()
    assert len(history) >= 1

    print(f"  每日报告: {daily['date']} 类型{daily['report_type']}")
    print(f"  周报告: {weekly['period']} 类型{weekly['report_type']}")
    print(f"  策略汇总: {strategy['strategy_count']}个策略")
    print(f"  AI学习数据: 版本{learning['version']}")
    print(f"  导出文件: {filepath}")
    print(f"  历史报告: {len(history)}份")
    print('PASS')
except Exception as ex:
    print(f'FAIL: {ex}')
    import traceback
    traceback.print_exc()

print()
print('===============================================')
print('V0.5.6.5 READY')
