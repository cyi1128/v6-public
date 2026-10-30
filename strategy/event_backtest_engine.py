# -*- coding: utf-8 -*-
"""
事件回测引擎模块
V1.1-3.7-B 新增

职责：
基于真实历史事件数据，回测各事件的历史表现。

只读取数据，不修改任何冻结模块。
"""

from datetime import datetime
from strategy.return_calculator import get_return_calculator
from strategy.backtest_report import get_backtest_report_generator
from data.historical_event_provider import get_historical_event_provider


class EventBacktestEngine:
    """事件回测引擎"""

    def __init__(self):
        self.return_calculator = get_return_calculator()
        self.report_generator = get_backtest_report_generator()
        self.event_provider = get_historical_event_provider()

    def backtest_single_event_type(self, code, name, kline_data, event_type):
        """
        回测单只股票的单一事件类型

        参数：
            code: 股票代码
            name: 股票名称
            kline_data: K线数据
            event_type: 事件类型（B1/B2/B3/B4/B6）

        返回：
            dict: 回测结果
        """
        # 获取事件日期
        event_dates = self.event_provider.get_event_dates(code, event_type)

        if not event_dates:
            return {
                'code': code,
                'name': name,
                'event_type': event_type,
                'event_count': 0,
                'summary': {},
            }

        # 计算事件收益
        event_returns = self.return_calculator.calculate_event_returns(
            kline_data, event_dates, [5, 10, 20]
        )

        # 汇总各周期
        period_results = {}
        for period in ['t5', 't10', 't20']:
            summary = self.return_calculator.summarize_returns(event_returns, period)
            period_results[period] = summary

        return {
            'code': code,
            'name': name,
            'event_type': event_type,
            'event_count': len(event_dates),
            'event_dates': event_dates,
            'period_results': period_results,
            'summary': period_results.get('t10', {}),
        }

    def backtest_all_events(self, code, name, kline_data):
        """
        回测单只股票的所有事件类型

        参数：
            code: 股票代码
            name: 股票名称
            kline_data: K线数据

        返回：
            dict: 各事件类型的回测结果
        """
        results = {}
        event_types = ['B1', 'B2', 'B3', 'B4', 'B6']

        for et in event_types:
            result = self.backtest_single_event_type(code, name, kline_data, et)
            results[et] = result

        return results

    def backtest_multiple_stocks(self, stock_list, klines_dict, event_type='B2'):
        """
        回测多只股票的同一事件类型，汇总统计

        参数：
            stock_list: 股票列表 [(code, name), ...]
            klines_dict: K线数据字典 {code: kline_data}
            event_type: 事件类型

        返回：
            dict: 汇总统计结果
        """
        all_returns = []

        for code, name in stock_list:
            if code not in klines_dict:
                continue

            result = self.backtest_single_event_type(code, name, klines_dict[code], event_type)
            if result['event_count'] == 0:
                continue

            # 收集所有事件收益
            event_dates = result.get('event_dates', [])
            event_returns = self.return_calculator.calculate_event_returns(
                klines_dict[code], event_dates, [5, 10, 20]
            )
            all_returns.extend(event_returns)

        # 汇总统计
        summary = {}
        for period in ['t5', 't10', 't20']:
            summary[period] = self.return_calculator.summarize_returns(all_returns, period)

        return {
            'event_type': event_type,
            'stock_count': len(stock_list),
            'event_count': len(all_returns),
            'period_summary': summary,
            'summary': summary.get('t10', {}),
        }

    def backtest_resonance(self, code, name, kline_data):
        """
        回测共振策略（简化版）

        注意：第一阶段简化处理，后续完善
        目前用事件数量来近似共振等级

        参数：
            code: 股票代码
            name: 股票名称
            kline_data: K线数据

        返回：
            dict: 共振回测结果
        """
        # 获取所有事件日期
        all_events = self.event_provider.get_events(code)
        if not all_events:
            return {
                'code': code,
                'name': name,
                'resonance_levels': {},
            }

        # 按日期分组，统计每天的事件数量
        date_events = {}
        for e in all_events:
            date = e.get('event_date', '')
            if not date:
                continue
            if date not in date_events:
                date_events[date] = 0
            date_events[date] += 1

        # 按事件数量分级
        single_dates = [d for d, c in date_events.items() if c == 1]
        double_dates = [d for d, c in date_events.items() if c >= 2]

        result = {
            'code': code,
            'name': name,
            'resonance_levels': {
                '单事件': self._calc_summary(kline_data, single_dates),
                '双事件+': self._calc_summary(kline_data, double_dates),
            }
        }

        return result

    def _calc_summary(self, kline_data, dates):
        """计算一组日期的收益汇总"""
        if not dates:
            return {'sample_count': 0, 'win_rate': 0, 'avg_return': 0}

        event_returns = self.return_calculator.calculate_event_returns(
            kline_data, dates, [5, 10, 20]
        )

        return self.return_calculator.summarize_returns(event_returns, 't10')

    def generate_event_report(self, event_name, summary_data, period='t10'):
        """生成单事件回测报告"""
        return self.report_generator.generate_event_report(event_name, summary_data, period)

    def generate_comparison_report(self, event_summaries, period='t10'):
        """生成多事件对比报告"""
        return self.report_generator.generate_comparison_report(event_summaries, period)

    def generate_resonance_report(self, resonance_summaries, period='t10'):
        """生成共振对比报告"""
        return self.report_generator.generate_resonance_report(resonance_summaries, period)


# 单例
_event_backtest_engine = None


def get_event_backtest_engine():
    """获取事件回测引擎单例"""
    global _event_backtest_engine
    if _event_backtest_engine is None:
        _event_backtest_engine = EventBacktestEngine()
    return _event_backtest_engine
