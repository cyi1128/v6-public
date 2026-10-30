# -*- coding: utf-8 -*-
"""
收益计算器模块
V1.1-3.7-A 新增

职责：
计算事件发生后的未来收益、最大上涨、最大回撤。

只做计算，不做策略判断。
"""


class ReturnCalculator:
    """收益计算器"""

    def __init__(self):
        pass

    def calculate_forward_returns(self, kline_data, event_index, periods=[5, 10, 20]):
        """
        计算事件发生后的未来收益

        参数：
            kline_data: K线数据dict，包含close列表
            event_index: 事件发生日的索引
            periods: 计算哪些周期的收益，默认[5, 10, 20]

        返回：
            dict: 各周期收益数据
        """
        result = {}

        closes = kline_data.get('close', [])
        highs = kline_data.get('high', [])
        lows = kline_data.get('low', [])

        if not closes or event_index >= len(closes) - 1:
            return result

        event_price = closes[event_index]

        for period in periods:
            end_index = min(event_index + period, len(closes) - 1)

            if end_index <= event_index:
                continue

            # 期末收益
            end_price = closes[end_index]
            return_rate = (end_price - event_price) / event_price * 100

            # 最大上涨
            period_highs = highs[event_index+1:end_index+1]
            max_up = 0
            if period_highs:
                max_high = max(period_highs)
                max_up = (max_high - event_price) / event_price * 100

            # 最大回撤
            period_lows = lows[event_index+1:end_index+1]
            max_drawdown = 0
            if period_lows:
                min_low = min(period_lows)
                max_drawdown = (min_low - event_price) / event_price * 100

            # 是否上涨
            is_up = return_rate > 0

            result[f't{period}'] = {
                'return_rate': round(return_rate, 2),
                'max_up': round(max_up, 2),
                'max_drawdown': round(max_drawdown, 2),
                'is_up': is_up,
                'end_price': end_price,
                'event_price': event_price,
            }

        return result

    def calculate_event_returns(self, kline_data, event_dates, periods=[5, 10, 20]):
        """
        计算多个事件日的收益

        参数：
            kline_data: K线数据dict
            event_dates: 事件日期列表
            periods: 计算周期

        返回：
            list: 各事件的收益数据
        """
        results = []
        dates = kline_data.get('dates', [])
        closes = kline_data.get('close', [])

        if not dates or not closes:
            return results

        for event_date in event_dates:
            # 找到事件日对应的索引
            event_index = None
            for i, d in enumerate(dates):
                if d == event_date:
                    event_index = i
                    break

            if event_index is None:
                continue

            returns = self.calculate_forward_returns(kline_data, event_index, periods)
            if returns:
                results.append({
                    'event_date': event_date,
                    'event_index': event_index,
                    'event_price': closes[event_index],
                    'returns': returns,
                })

        return results

    def summarize_returns(self, return_list, period='t10'):
        """
        汇总收益统计

        参数：
            return_list: 收益数据列表
            period: 统计哪个周期，默认t10

        返回：
            dict: 统计结果
        """
        if not return_list:
            return {
                'sample_count': 0,
                'win_rate': 0,
                'avg_return': 0,
                'avg_max_up': 0,
                'avg_max_drawdown': 0,
                'max_return': 0,
                'min_return': 0,
            }

        returns = []
        max_ups = []
        max_drawdowns = []

        for item in return_list:
            period_data = item.get('returns', {}).get(period, {})
            if period_data:
                returns.append(period_data['return_rate'])
                max_ups.append(period_data['max_up'])
                max_drawdowns.append(period_data['max_drawdown'])

        if not returns:
            return {
                'sample_count': 0,
                'win_rate': 0,
                'avg_return': 0,
                'avg_max_up': 0,
                'avg_max_drawdown': 0,
                'max_return': 0,
                'min_return': 0,
            }

        sample_count = len(returns)
        win_count = sum(1 for r in returns if r > 0)
        win_rate = win_count / sample_count * 100
        avg_return = sum(returns) / sample_count
        avg_max_up = sum(max_ups) / sample_count
        avg_max_drawdown = sum(max_drawdowns) / sample_count
        max_return = max(returns)
        min_return = min(returns)

        return {
            'sample_count': sample_count,
            'win_rate': round(win_rate, 1),
            'avg_return': round(avg_return, 2),
            'avg_max_up': round(avg_max_up, 2),
            'avg_max_drawdown': round(avg_max_drawdown, 2),
            'max_return': round(max_return, 2),
            'min_return': round(min_return, 2),
        }


# 单例
_return_calculator = None


def get_return_calculator():
    """获取收益计算器单例"""
    global _return_calculator
    if _return_calculator is None:
        _return_calculator = ReturnCalculator()
    return _return_calculator
