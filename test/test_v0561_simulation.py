# -*- coding: utf-8 -*-
"""
V0.5.6.1 实盘模拟账户 - 集成测试

验证：账户 + 持仓 + 订单 + 交易记录 完整流程
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.simulation import (
    SimulatedAccount, Portfolio, OrderManager, TradeLog,
    OrderSide, OrderType, OrderStatus,
)


def test_account():
    """测试模拟账户"""
    print("\n" + "="*60)
    print("【1】模拟账户测试")
    print("="*60)

    account = SimulatedAccount(initial_cash=1000000, account_id="TEST001")

    print(f"  初始资金: {account.initial_cash:,.2f}")
    print(f"  可用资金: {account.available_cash:,.2f}")
    print(f"  总资产: {account.total_asset:,.2f}")

    # 冻结资金
    assert account.freeze_cash(200000) == True
    print(f"  冻结20万后: 可用{account.cash:,.0f} 冻结{account.frozen_cash:,.0f}")

    # 解冻
    account.unfreeze_cash(50000)
    print(f"  解冻5万后: 可用{account.cash:,.0f} 冻结{account.frozen_cash:,.0f}")

    # 扣除冻结（成交）
    account.deduct_frozen(100000)
    print(f"  扣除10万冻结后: 冻结{account.frozen_cash:,.0f}")

    # 记录交易
    account.record_trade(5000)
    account.record_trade(-2000)
    print(f"  记录2笔交易: 总{account.total_trades} 胜{account.win_trades} 负{account.loss_trades}")
    print(f"  胜率: {account.win_rate:.1f}%")

    # 快照
    snapshot = account.take_snapshot('2026-08-16')
    print(f"  快照: 总资产{snapshot['total_asset']:,.0f} 收益率{snapshot['total_return_pct']:+.2f}%")

    # 序列化
    data = account.to_dict()
    account2 = SimulatedAccount.from_dict(data)
    print(f"  序列化/反序列化: 总资产{account2.total_asset:,.0f} ✅")

    print(account.summary())
    print("模拟账户测试通过 ✅")


def test_portfolio():
    """测试持仓管理"""
    print("\n" + "="*60)
    print("【2】持仓管理测试")
    print("="*60)

    account = SimulatedAccount(1000000)
    portfolio = Portfolio(account)

    # 买入
    result = portfolio.buy('600580', 1000, 25.0, name='卧龙电驱', date='2026-08-10')
    print(f"  买入600580: {result['message']}")
    assert result['success']

    # 再次买入（摊薄成本）
    result = portfolio.buy('600580', 1000, 27.0, name='卧龙电驱', date='2026-08-12')
    pos = portfolio.get_position('600580')
    print(f"  再次买入后: 数量{pos.quantity} 平均成本{pos.avg_cost:.2f}")
    assert abs(pos.avg_cost - 26.0) < 0.01  # (25+27)/2=26

    # T+1前不可卖
    print(f"  T+1前可卖: {pos.available_qty}")
    assert pos.available_qty == 0

    # T+1结算
    portfolio.settle_t1()
    print(f"  T+1后可卖: {pos.available_qty}")
    assert pos.available_qty == 2000

    # 更新价格
    portfolio.update_prices({'600580': 28.0})
    print(f"  现价28元: 市值{pos.market_value:,.0f} 浮盈{pos.unrealized_pnl:,.0f} ({pos.unrealized_pnl_pct:+.2f}%)")

    # 卖出
    result = portfolio.sell('600580', 1000, 28.0)
    print(f"  卖出1000股: 金额{result['amount']:,.0f} 盈亏{result['realized_pnl']:+,.0f}")
    assert result['success']

    # 持仓集中度
    portfolio.buy('000001', 500, 15.0, name='平安银行')
    portfolio.update_prices({'600580': 28.0, '000001': 15.5})
    conc = portfolio.get_concentration()
    print(f"  持仓集中度: {conc}")

    # 行业分布
    portfolio.set_industry('600580', '电气设备')
    portfolio.set_industry('000001', '银行')
    dist = portfolio.get_industry_distribution()
    print(f"  行业分布: {dist}")

    print(portfolio.summary())
    print("持仓管理测试通过 ✅")


def test_order_manager():
    """测试订单管理"""
    print("\n" + "="*60)
    print("【3】订单管理测试")
    print("="*60)

    account = SimulatedAccount(1000000)
    portfolio = Portfolio(account)
    order_mgr = OrderManager(account, portfolio)

    # 创建市价买单
    result = order_mgr.create_order('600580', 'buy', 1000, order_type='market', name='卧龙电驱')
    print(f"  创建市价买单: {result['message']}")
    assert result['success']
    order_id = result['order_id']

    # 检查资金冻结
    print(f"  资金冻结后: 可用{account.cash:,.0f} 冻结{account.frozen_cash:,.0f}")

    # 撮合市价单
    order_mgr.match_market_orders({'600580': 25.5})
    order = order_mgr.get_order(order_id)
    print(f"  撮合后: 状态{order.status.value} 成交价{order.filled_price:.2f}")
    assert order.status == OrderStatus.FILLED

    # T+1结算
    portfolio.settle_t1()

    # 创建限价卖单
    result = order_mgr.create_order('600580', 'sell', 500, price=27.0, order_type='limit')
    print(f"  创建限价卖单: {result['message']}")
    sell_id = result['order_id']

    # 价格未到，不成交
    order_mgr.match_limit_orders({'600580': 26.0})
    order = order_mgr.get_order(sell_id)
    print(f"  价格26<27: 状态{order.status.value}（未成交）")
    assert order.status == OrderStatus.PENDING

    # 价格到达，成交
    order_mgr.match_limit_orders({'600580': 27.5})
    order = order_mgr.get_order(sell_id)
    print(f"  价格27.5>=27: 状态{order.status.value} 成交价{order.filled_price:.2f}")
    assert order.status == OrderStatus.FILLED

    # 撤单测试
    result = order_mgr.create_order('000001', 'buy', 1000, price=15.0, order_type='limit')
    cancel_id = result['order_id']
    result = order_mgr.cancel_order(cancel_id)
    print(f"  撤单: {result['message']}")
    assert result['success']

    # 无效订单测试
    result = order_mgr.create_order('600580', 'buy', 150)  # 不是100整数倍
    print(f"  非100整数倍买单: {result['message']}")
    assert not result['success']

    # 活跃订单
    active = order_mgr.get_active_orders()
    print(f"  活跃订单数: {len(active)}")

    print(order_mgr.summary())
    print("订单管理测试通过 ✅")


def test_trade_log():
    """测试交易记录"""
    print("\n" + "="*60)
    print("【4】交易记录测试")
    print("="*60)

    log = TradeLog()

    # 记录交易
    log.record_trade('ORD001', '600580', '卧龙电驱', 'buy', 1000, 25.0, 25000,
                     ai_signal='确认买入', ai_score=85)
    log.record_trade('ORD002', '600580', '卧龙电驱', 'sell', 1000, 28.0, 28000,
                     realized_pnl=3000, ai_signal='确认买入', ai_score=85)
    log.record_trade('ORD003', '000001', '平安银行', 'buy', 500, 15.0, 7500,
                     ai_signal='重点关注', ai_score=72)
    log.record_trade('ORD004', '000001', '平安银行', 'sell', 500, 14.5, 7250,
                     realized_pnl=-250, ai_signal='重点关注', ai_score=72)

    print(f"  总交易记录: {len(log.trades)}")

    # 每日汇总
    summaries = log.get_all_daily_summaries()
    print(f"  交易日数: {len(summaries)}")
    for s in summaries:
        print(f"    {s['date']}: 买{s['buy_count']}卖{s['sell_count']} 盈亏{s['realized_pnl']:+,.0f}")

    # 交易统计
    stats = log.get_trade_statistics()
    print(f"  交易统计: 胜率{stats['win_rate']:.1f}% 盈亏比{stats['profit_loss_ratio']:.2f}")
    print(f"    总已实现盈亏: {stats['total_realized_pnl']:+,.0f}")

    # AI预测记录
    log.record_ai_prediction('600580', '确认买入', 85, '2026-08-10', 'success')
    log.record_ai_prediction('000001', '重点关注', 72, '2026-08-11', 'failure')
    log.record_ai_prediction('600330', '确认买入', 90, '2026-08-12', 'pending')

    ai_acc = log.get_ai_accuracy()
    print(f"  AI准确率: {ai_acc['accuracy']:.1f}% (成功{ai_acc['success']}/失败{ai_acc['failure']}/待定{ai_acc['pending']})")
    print(f"  按信号: {ai_acc['by_signal']}")

    # 每日报告
    report = log.generate_daily_report()
    print(f"  每日报告日期: {report['date']}")

    # 序列化
    import tempfile
    path = os.path.join(tempfile.gettempdir(), 'test_trade_log.json')
    log.save(path)
    log2 = TradeLog.load(path)
    print(f"  序列化/反序列化: 交易数{len(log2.trades)} ✅")

    print(log.summary())
    print("交易记录测试通过 ✅")


def test_full_workflow():
    """测试完整流程：账户+持仓+订单+记录"""
    print("\n" + "="*60)
    print("【5】完整流程测试")
    print("="*60)

    # 初始化
    account = SimulatedAccount(1000000, "SIMFULL")
    portfolio = Portfolio(account)
    order_mgr = OrderManager(account, portfolio)
    trade_log = TradeLog()

    print("  初始状态:")
    print(f"    资金: {account.total_asset:,.0f}")

    # Day1: 买入
    print("\n  Day1: 买入600580")
    result = order_mgr.create_order('600580', 'buy', 1000, order_type='market', name='卧龙电驱')
    order_mgr.match_market_orders({'600580': 25.0})
    order = order_mgr.get_order(result['order_id'])
    trade_log.record_trade(order.order_id, '600580', '卧龙电驱', 'buy',
                           order.filled_qty, order.filled_price,
                           order.filled_qty * order.filled_price,
                           ai_signal='确认买入', ai_score=85)
    portfolio.update_prices({'600580': 25.5})
    account.take_snapshot('Day1')
    print(f"    买入价: {order.filled_price:.2f} 现价: 25.5 浮盈: {portfolio.total_unrealized_pnl:+,.0f}")

    # Day2: T+1，价格上涨
    print("\n  Day2: T+1结算，价格上涨")
    portfolio.settle_t1()
    portfolio.update_prices({'600580': 28.0})
    account.take_snapshot('Day2')
    print(f"    现价: 28.0 浮盈: {portfolio.total_unrealized_pnl:+,.0f} ({portfolio.total_unrealized_pnl/25000*100:+.1f}%)")

    # Day3: 卖出
    print("\n  Day3: 卖出")
    result = order_mgr.create_order('600580', 'sell', 1000, order_type='market')
    # 记录卖出前的已实现盈亏
    old_realized = account.realized_pnl
    order_mgr.match_market_orders({'600580': 27.5})
    order = order_mgr.get_order(result['order_id'])
    realized_pnl = account.realized_pnl - old_realized
    trade_log.record_trade(order.order_id, '600580', '卧龙电驱', 'sell',
                           order.filled_qty, order.filled_price,
                           order.filled_qty * order.filled_price,
                           realized_pnl=realized_pnl,
                           ai_signal='确认买入', ai_score=85)
    portfolio.update_prices({'600580': 27.5})
    account.take_snapshot('Day3')

    print(f"    卖出价: {order.filled_price:.2f} 已实现盈亏: {realized_pnl:+,.0f}")
    print(f"    最终资金: {account.total_asset:,.0f} 收益率: {account.total_return_pct:+.2f}%")

    # 最终统计
    print("\n  最终统计:")
    print(f"    总资产: {account.total_asset:,.0f}")
    print(f"    已实现盈亏: {account.realized_pnl:+,.0f}")
    print(f"    交易次数: {account.total_trades}")
    print(f"    胜率: {account.win_rate:.1f}%")
    print(f"    持仓数: {portfolio.position_count}")

    stats = trade_log.get_trade_statistics()
    print(f"    交易日志胜率: {stats['win_rate']:.1f}%")

    print("\n完整流程测试通过 ✅")


def main():
    print("\n" + "#"*60)
    print("# V0.5.6.1 实盘模拟账户 - 集成测试")
    print("# 账户 + 持仓 + 订单 + 交易记录")
    print("#"*60)

    test_account()
    test_portfolio()
    test_order_manager()
    test_trade_log()
    test_full_workflow()

    print("\n" + "#"*60)
    print("# 所有测试完成 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
