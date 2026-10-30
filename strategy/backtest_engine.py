# -*- coding: utf-8 -*-
"""
回测引擎模块
V1.1-3.7-A 新增

职责：
回测任务管理，股票循环，时间窗口控制。

第一阶段：基础框架
- 跑通单股票回测链路
- 用技术信号模拟事件（验证框架）
- 后续接入真实历史事件

原则：
- 不修改任何冻结模块
- 只读取已有数据
- 独立模块，可删除
"""

from datetime import datetime
from strategy.return_calculator import get_return_calculator
from strategy.backtest_report import get_backtest_report_generator


class BacktestEngine:
    """回测引擎"""

    def __init__(self):
        self.return_calculator = get_return_calculator()
        self.report_generator = get_backtest_report_generator()

    def backtest_single_stock(self, code, name, kline_data, event_dates, periods=[5, 10, 20]):
        """
        回测单只股票

        参数：
            code: 股票代码
            name: 股票名称
            kline_data: K线数据
            event_dates: 事件日期列表
            periods: 计算周期

        返回：
            dict: 回测结果
        """
        result = {
            'code': code,
            'name': name,
            'event_count': len(event_dates),
            'event_dates': event_dates,
            'period_results': {},
            'summary': {},
        }

        if not event_dates or not kline_data:
            return result

        # 计算各事件的收益
        event_returns = self.return_calculator.calculate_event_returns(
            kline_data, event_dates, periods
        )

        # 汇总各周期统计
        for period in [f't{p}' for p in periods]:
            summary = self.return_calculator.summarize_returns(event_returns, period)
            result['period_results'][period] = summary

        # 默认用T+10作为主要统计
        result['summary'] = result['period_results'].get('t10', {})

        return result

    def backtest_event_type(self, stock_events, period='t10'):
        """
        回测某类事件在多只股票上的表现

        参数：
            stock_events: dict，key是股票代码，value是事件日期列表
            period: 统计周期

        返回：
            dict: 汇总统计结果
        """
        all_returns = []

        for code, dates in stock_events.items():
            # 注意：这里需要K线数据，第一阶段先留接口
            # 后续接入真实数据后完善
            pass

        return {
            'sample_count': 0,
            'win_rate': 0,
            'avg_return': 0,
            'avg_max_up': 0,
            'avg_max_drawdown': 0,
        }

    def generate_single_report(self, code, name, backtest_result, period='t10'):
        """生成单股票回测报告"""
        summary = backtest_result.get('period_results', {}).get(period, {})
        event_name = f"{name}({code}) 事件回测"
        return self.report_generator.generate_event_report(event_name, summary, period)

    def generate_comparison_report(self, event_summaries, period='t10'):
        """生成多事件对比报告"""
        return self.report_generator.generate_comparison_report(event_summaries, period)

    def generate_resonance_report(self, resonance_summaries, period='t10'):
        """生成共振对比报告"""
        return self.report_generator.generate_resonance_report(resonance_summaries, period)


# 单例
_backtest_engine = None


def get_backtest_engine():
    """获取回测引擎单例"""
    global _backtest_engine
    if _backtest_engine is None:
        _backtest_engine = BacktestEngine()
    return _backtest_engine
