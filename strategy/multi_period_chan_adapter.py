# -*- coding: utf-8 -*-
"""
多周期缠论适配层
V1.2-B-1 新增

定位：
缠论结果翻译层，不是缠论计算层。
只读取已有缠论分析结果，重新组织展示结构。

原则：
- 不重新计算分型
- 不重新生成笔
- 不修改买卖点
- 不修改缠论评分
- 不修改交易建议
- 不影响AI决策中心原数据
- 独立模块，可删除
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MultiPeriodChanAdapter:
    """多周期缠论适配层"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 周期名称映射
        self.period_names = {
            'week': '周线',
            'day': '日线',
            '60min': '60分钟',
            '30min': '30分钟',
        }

        print("[MultiPeriodChanAdapter] 多周期缠论适配层初始化完成")

    def adapt_multi_period(self, chan_result):
        """
        适配多周期缠论结果

        参数：
            chan_result: 缠论核心模块的analyze_multi_period输出
                {
                    'periods': {
                        'week': {...},
                        'day': {...},
                        ...
                    },
                    'overall': {...}
                }

        返回：
            dict: 适配后的统一结构
        """
        if not chan_result or 'periods' not in chan_result:
            return {
                'periods': {},
                'chan_summary': {
                    'direction': '未知',
                    'buy_points': [],
                    'risk_points': [],
                    'chan_confirmation_score': 0,
                }
            }

        periods = chan_result.get('periods', {})
        adapted_periods = {}

        # 逐个周期适配
        for period, period_data in periods.items():
            adapted_periods[period] = self._adapt_single_period(period_data)

        # 生成总结
        summary = self._generate_summary(adapted_periods)

        return {
            'periods': adapted_periods,
            'chan_summary': summary,
        }

    def _adapt_single_period(self, period_data):
        """
        适配单周期缠论结果

        参数：
            period_data: 单周期缠论分析结果

        返回：
            dict: 适配后的单周期结构
        """
        if not period_data or period_data.get('status') != '分析完成':
            return {
                'trend': '未知',
                'structure': '数据不足',
                'signal': '无信号',
                'confidence': '低',
                'status': '数据不足',
            }

        # 趋势
        trend_info = period_data.get('trend', {})
        trend_status = trend_info.get('status', '未知')
        trend_direction = trend_info.get('direction', 'unknown')

        # 结构判断
        structure = self._judge_structure(period_data)

        # 买卖点信号
        signals = period_data.get('signals', [])
        buy_signals = [s for s in signals if s.get('type') == 'buy']
        sell_signals = [s for s in signals if s.get('type') == 'sell']

        if buy_signals:
            signal_name = buy_signals[0].get('name', '买点')
            signal_type = 'buy'
        elif sell_signals:
            signal_name = sell_signals[0].get('name', '卖点')
            signal_type = 'sell'
        else:
            signal_name = '无信号'
            signal_type = 'none'

        # 置信度
        confidence = self._judge_confidence(period_data)

        return {
            'trend': trend_status,
            'direction': trend_direction,
            'structure': structure,
            'signal': signal_name,
            'signal_type': signal_type,
            'confidence': confidence,
            'status': '正常',
        }

    def _judge_structure(self, period_data):
        """
        判断结构状态

        参数：
            period_data: 单周期缠论结果

        返回：
            str: 结构描述
        """
        trend_info = period_data.get('trend', {})
        trend_status = trend_info.get('status', '')
        zhongshu = period_data.get('zhongshu', None)
        signals = period_data.get('signals', [])
        beichi = period_data.get('beichi', None)

        # 有明确买卖点
        buy_signals = [s for s in signals if s.get('type') == 'buy']
        sell_signals = [s for s in signals if s.get('type') == 'sell']

        if buy_signals:
            signal_name = buy_signals[0].get('name', '')
            if signal_name == '一买':
                return '一买区域'
            elif signal_name == '二买':
                return '二买附近'
            elif signal_name == '三买':
                return '三买确认'
            else:
                return '买点区域'

        if sell_signals:
            signal_name = sell_signals[0].get('name', '')
            if signal_name == '一卖':
                return '一卖区域'
            elif signal_name == '二卖':
                return '二卖附近'
            elif signal_name == '三卖':
                return '三卖确认'
            else:
                return '卖点区域'

        # 背驰
        if beichi:
            if beichi.get('type') == 'bottom_beichi':
                return '底背驰'
            elif beichi.get('type') == 'top_beichi':
                return '顶背驰'

        # 中枢
        if zhongshu:
            if trend_status == '中枢震荡':
                return '中枢内部'
            elif trend_status == '上涨调整':
                return '上涨回调'
            elif trend_status == '下跌反弹':
                return '下跌反弹'

        # 趋势
        if trend_status == '上涨趋势':
            return '上涨笔'
        elif trend_status == '下跌趋势':
            return '下跌笔'

        return '震荡整理'

    def _judge_confidence(self, period_data):
        """
        判断置信度

        参数：
            period_data: 单周期缠论结果

        返回：
            str: 高/中/低
        """
        score = 0

        # 有明确买卖点
        signals = period_data.get('signals', [])
        if signals:
            score += 2
            # 强信号
            for s in signals:
                if s.get('confidence') == '高':
                    score += 1
                    break

        # 有中枢
        if period_data.get('zhongshu'):
            score += 1

        # 有背驰
        if period_data.get('beichi'):
            score += 1

        # 评分高
        chan_score = period_data.get('score', 0)
        if chan_score >= 70:
            score += 2
        elif chan_score >= 50:
            score += 1

        # 判断置信度
        if score >= 5:
            return '高'
        elif score >= 3:
            return '中'
        else:
            return '低'

    def _generate_summary(self, adapted_periods):
        """
        生成多周期缠论总结

        参数：
            adapted_periods: 适配后的各周期结果

        返回：
            dict: 总结结构
        """
        # 收集所有买卖点
        all_buy_points = []
        all_risk_points = []
        total_score = 0
        period_count = 0

        for period, data in adapted_periods.items():
            period_name = self.period_names.get(period, period)

            if data.get('signal_type') == 'buy':
                all_buy_points.append(f"{period_name}{data['signal']}")
            elif data.get('signal_type') == 'sell':
                all_risk_points.append(f"{period_name}{data['signal']}")

            # 背驰风险
            if data.get('structure') == '顶背驰':
                all_risk_points.append(f"{period_name}顶背驰")

            # 累计评分
            confidence = data.get('confidence', '低')
            if confidence == '高':
                total_score += 25
            elif confidence == '中':
                total_score += 15
            else:
                total_score += 5

            period_count += 1

        # 判断整体方向
        week_data = adapted_periods.get('week', {})
        day_data = adapted_periods.get('day', {})

        week_direction = week_data.get('direction', 'unknown')
        day_direction = day_data.get('direction', 'unknown')

        if week_direction == 'up' and day_direction == 'up':
            direction = '偏多'
        elif week_direction == 'down' and day_direction == 'down':
            direction = '偏空'
        elif week_direction == 'up' or day_direction == 'up':
            direction = '震荡偏多'
        elif week_direction == 'down' or day_direction == 'down':
            direction = '震荡偏空'
        else:
            direction = '震荡'

        # 确认度评分（独立字段，不影响其他评分）
        chan_confirmation_score = min(100, total_score)

        return {
            'direction': direction,
            'buy_points': all_buy_points,
            'risk_points': all_risk_points,
            'chan_confirmation_score': chan_confirmation_score,
            'period_count': period_count,
        }

    def analyze_stock(self, code):
        """
        分析单只股票的多周期缠论

        参数：
            code: 股票代码

        返回：
            dict: 适配后的多周期缠论结果
        """
        # 获取多周期K线
        from data.multi_period_provider import get_multi_period_provider
        provider = get_multi_period_provider()

        kline_dict = {}
        for period in ['week', 'day', '60min', '30min']:
            kline = provider.get_kline(code, period)
            if kline:
                kline_dict[period] = kline

        if not kline_dict:
            return self.adapt_multi_period({})

        # 调用缠论核心模块分析
        from strategy.chanlun_core import get_chanlun_core
        core = get_chanlun_core()

        chan_result = core.analyze_multi_period(kline_dict)

        # 适配
        return self.adapt_multi_period(chan_result)


# 单例获取函数
_multi_period_chan_adapter = None


def get_multi_period_chan_adapter():
    """获取多周期缠论适配层单例"""
    global _multi_period_chan_adapter
    if _multi_period_chan_adapter is None:
        _multi_period_chan_adapter = MultiPeriodChanAdapter()
    return _multi_period_chan_adapter
