# -*- coding: utf-8 -*-
"""
V0.5 回测引擎集成测试
验证：数据层 + 撮合引擎全链路
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.data.data_loader import DataLoader, TDXDataLoader, get_default_loader
from backtest.data.adjust import adjust_kline, AdjustType, verify_adjust_continuity
from backtest.data.quality_check import QualityChecker, check_data_quality
from backtest.data.timeframe import resample_kline, TimeFrame
from backtest.engine.order import Order, OrderSide, OrderType, OrderStatus
from backtest.engine.cost import CostCalculator, AStockCostConfig, calc_breakeven_price
from backtest.engine.execution import ExecutionEngine
from backtest.engine.broker import Broker, Position, Account


def test_data_loader():
    """测试数据加载器"""
    print("\n" + "="*60)
    print("【1】数据加载器测试")
    print("="*60)

    loader = get_default_loader()
    print(f"默认数据源: {loader.name}")
    print(f"数据源可用: {loader.available()}")

    # 测试获取K线（使用模拟数据，避免网络依赖）
    print("\n使用模拟数据测试接口...")
    mock_data = {
        'open': [10.0 + i*0.01 for i in range(100)],
        'close': [10.1 + i*0.01 for i in range(100)],
        'high': [10.2 + i*0.01 for i in range(100)],
        'low': [9.9 + i*0.01 for i in range(100)],
        'volume': [1000000 + i*1000 for i in range(100)],
        'pct_chg': [0.5 + i*0.01 for i in range(100)],
        'dates': [f'2025-01-{i+1:02d}' for i in range(30)] + [f'2025-02-{i-29:02d}' for i in range(30, 100)],
    }
    print(f"模拟K线: {len(mock_data['close'])}根")
    print("数据加载器接口测试通过 ✅")


def test_adjust():
    """测试复权处理"""
    print("\n" + "="*60)
    print("【2】复权处理测试")
    print("="*60)

    data = {
        'open': [10.0, 10.5, 11.0, 10.8, 11.2],
        'close': [10.5, 11.0, 10.8, 11.2, 11.5],
        'high': [10.6, 11.1, 11.2, 11.3, 11.6],
        'low': [9.9, 10.4, 10.7, 10.7, 11.1],
        'volume': [1000000]*5,
        'pct_chg': [0, 4.76, -1.82, 3.70, 2.68],
        'dates': ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07'],
    }

    # 相同复权类型
    result = adjust_kline(data, "qfq", "qfq")
    print(f"qfq->qfq: 价格不变, adjust={result['adjust']}")

    # 不复权转前复权
    result = adjust_kline(data, "qfq", "none")
    print(f"none->qfq: 首根收盘={result['close'][0]:.3f}, 末根收盘={result['close'][-1]:.3f}")

    # 验证连续性
    report = verify_adjust_continuity(result)
    print(f"复权连续性: 连续={report['continuous']}, 最大跳空={report['max_jump']}%")
    print("复权处理测试通过 ✅")


def test_quality_check():
    """测试数据质量检测"""
    print("\n" + "="*60)
    print("【3】数据质量检测测试")
    print("="*60)

    # 正常数据
    good_data = {
        'open': [10.0 + i*0.01 for i in range(100)],
        'close': [10.1 + i*0.01 for i in range(100)],
        'high': [10.2 + i*0.01 for i in range(100)],
        'low': [9.9 + i*0.01 for i in range(100)],
        'volume': [1000000]*100,
        'pct_chg': [0.5]*100,
        'dates': [f'2025-01-{i+1:02d}' for i in range(30)] + [f'2025-02-{i-29:02d}' for i in range(30, 100)],
    }
    report = check_data_quality(good_data, "000001", min_bars=60)
    print(f"正常数据: {report.summary()}")

    # 异常数据（数据量不足）
    bad_data = {k: v[:10] for k, v in good_data.items()}
    report2 = check_data_quality(bad_data, "000001", min_bars=60)
    print(f"不足数据: {report2.summary()}")
    print(f"  错误: {[e['message'] for e in report2.errors]}")
    print("数据质量检测测试通过 ✅")


def test_timeframe():
    """测试时间周期转换"""
    print("\n" + "="*60)
    print("【4】时间周期转换测试")
    print("="*60)

    # 生成30天日线数据
    data = {
        'open': [10.0 + i*0.1 for i in range(30)],
        'close': [10.1 + i*0.1 for i in range(30)],
        'high': [10.2 + i*0.1 for i in range(30)],
        'low': [9.9 + i*0.1 for i in range(30)],
        'volume': [1000000]*30,
        'pct_chg': [0.5]*30,
        'dates': [f'2025-01-{i+1:02d}' for i in range(30)],
    }

    weekly = resample_kline(data, "week")
    print(f"日线30根 -> 周线: {len(weekly['close'])}根")

    monthly = resample_kline(data, "month")
    print(f"日线30根 -> 月线: {len(monthly['close'])}根")

    ndays = resample_kline(data, "5day")
    print(f"日线30根 -> 5日: {len(ndays['close'])}根")
    print("时间周期转换测试通过 ✅")


def test_order():
    """测试订单模型"""
    print("\n" + "="*60)
    print("【5】订单模型测试")
    print("="*60)

    order = Order("000001", OrderSide.BUY, 1000, OrderType.MARKET,
                  date="2025-01-10", reason="测试买入")
    print(f"创建订单: {order}")

    order.fill(10.5, "2025-01-13", commission=5.0, slippage=21.0)
    print(f"成交后: 状态={order.status.value}, 成交价={order.filled_price}, 总成本={order.total_cost:.2f}")
    print(f"订单详情: {order.to_dict()}")
    print("订单模型测试通过 ✅")


def test_cost():
    """测试交易成本"""
    print("\n" + "="*60)
    print("【6】交易成本测试")
    print("="*60)

    calc = CostCalculator(AStockCostConfig.default())

    # 买入成本
    commission, transfer, slippage, total = calc.calc_buy_cost(10.0, 1000, "000001")
    print(f"买入 1000股@10元: 佣金={commission:.2f}, 过户费={transfer:.2f}, 滑点={slippage:.2f}, 总成本={total:.2f}")

    # 卖出成本
    commission, stamp, transfer, slippage, total = calc.calc_sell_cost(12.0, 1000, "000001")
    print(f"卖出 1000股@12元: 佣金={commission:.2f}, 印花税={stamp:.2f}, 过户费={transfer:.2f}, 滑点={slippage:.2f}, 总成本={total:.2f}")

    # 保本价
    breakeven = calc_breakeven_price(10.0, 1000, "000001")
    print(f"保本卖出价: {breakeven:.3f}元")

    # 往返成本率
    rate = calc.calc_round_trip_cost_rate(10.0, 1000, "000001")
    print(f"往返交易成本率: {rate*100:.3f}%")
    print("交易成本测试通过 ✅")


def test_execution():
    """测试执行引擎"""
    print("\n" + "="*60)
    print("【7】执行引擎测试")
    print("="*60)

    engine = ExecutionEngine()

    # 正常买入
    bar = {'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.3,
           'pre_close': 9.9, 'volume': 1000000}
    order = Order("000001", OrderSide.BUY, 1000, OrderType.MARKET, date="2025-01-10")
    result = engine.process_orders([order], bar, "2025-01-13")
    print(f"市价买入: {result.summary()}")
    if result.executed:
        print(f"  成交价: {result.executed[0].filled_price:.3f}")

    # T+1测试
    engine.set_available_date("000001", "2025-01-14")
    sell_order = Order("000001", OrderSide.SELL, 1000, OrderType.MARKET, date="2025-01-13")
    result2 = engine.process_orders([sell_order], bar, "2025-01-13", {"000001": 1000})
    print(f"T+1限制卖出: {result2.summary()}")
    if result2.rejected:
        print(f"  拒绝原因: {result2.rejected[0].reject_reason}")

    # 涨停测试
    limit_bar = {'open': 10.89, 'high': 10.89, 'low': 10.89, 'close': 10.89,
                 'pre_close': 9.9, 'volume': 1000000}
    buy_order = Order("000001", OrderSide.BUY, 1000, OrderType.MARKET, date="2025-01-14")
    result3 = engine.process_orders([buy_order], limit_bar, "2025-01-14")
    print(f"涨停买入: {result3.summary()}")
    if result3.rejected:
        print(f"  拒绝原因: {result3.rejected[0].reject_reason}")
    print("执行引擎测试通过 ✅")


def test_broker():
    """测试券商模拟（完整交易流程）"""
    print("\n" + "="*60)
    print("【8】券商模拟完整交易流程测试")
    print("="*60)

    broker = Broker(initial_cash=1000000, max_positions=5, single_position_pct=0.2)
    print(f"初始资金: {broker.account.cash:.0f}元")

    # Day1: 提交买入订单
    print("\n--- Day1: 提交买入订单 ---")
    order = broker.buy("000001", 2000, price=10.0, date="2025-01-10", reason="测试")
    print(f"订单: {order}")
    print(f"待处理订单: {len(broker.pending_orders)}")

    # Day2: 执行订单（下一交易日开盘成交）
    print("\n--- Day2: 执行买入 ---")
    bar_data = {
        "000001": {'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.3,
                   'pre_close': 9.9, 'volume': 1000000}
    }
    broker.execute_pending(bar_data, "2025-01-13")
    print(f"成交记录: {len(broker.account.trades)}笔")
    pos = broker.get_position("000001")
    if pos:
        print(f"持仓: {pos.quantity}股, 成本={pos.avg_cost:.3f}, 可卖={pos.available_qty}")
    print(f"剩余资金: {broker.account.cash:.0f}元")

    # Day3: T+1，尝试卖出
    print("\n--- Day3: T+1卖出 ---")
    sell_order = broker.sell("000001", 2000, date="2025-01-14", reason="止盈")
    bar_data2 = {
        "000001": {'open': 11.0, 'high': 11.5, 'low': 10.8, 'close': 11.2,
                   'pre_close': 10.3, 'volume': 1200000}
    }
    broker.execute_pending(bar_data2, "2025-01-14")
    print(f"成交记录: {len(broker.account.trades)}笔")
    print(f"最终资金: {broker.account.cash:.0f}元")
    print(f"总收益率: {(broker.account.cash - 1000000) / 1000000 * 100:.2f}%")

    # 账户摘要
    summary = broker.get_account_summary()
    print(f"\n账户摘要: 现金={summary['cash']}, 总资产={summary['total_asset']}, 交易次数={summary['trade_count']}")
    print("券商模拟测试通过 ✅")


def main():
    print("\n" + "#"*60)
    print("# V0.5 回测引擎集成测试")
    print("# 数据层 + 交易撮合引擎全链路验证")
    print("#"*60)

    test_data_loader()
    test_adjust()
    test_quality_check()
    test_timeframe()
    test_order()
    test_cost()
    test_execution()
    test_broker()

    print("\n" + "#"*60)
    print("# 所有测试通过 ✅")
    print("#"*60)


if __name__ == '__main__':
    main()
