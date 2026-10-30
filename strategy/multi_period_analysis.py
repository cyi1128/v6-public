# -*- coding: utf-8 -*-
"""
多周期分析模块
V1.2-A-2 新增

定位：
对多周期K线数据进行技术指标分析和趋势判断。

原则：
- 只读取多周期数据，不修改任何冻结模块
- 独立模块，可删除
- 输出统一格式，供共振评分层使用
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MultiPeriodAnalyzer:
    """多周期分析器"""

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

        # 指标参数（严格沿用系统冻结参数）
        self.ma_periods = [5, 10, 20, 60, 120]
        self.macd_fast = 8
        self.macd_slow = 21
        self.macd_signal = 5
        self.kdj_n = 13
        self.kdj_m1 = 3
        self.kdj_m2 = 3

        # 周期用途说明
        self.period_purposes = {
            'week': '判断大趋势',
            'day': '寻找机会',
            '60min': '寻找买入时机',
            '30min': '精确执行',
        }

        print("[MultiPeriodAnalyzer] 多周期分析器初始化完成")

    def analyze_period(self, kline_data):
        """
        分析单周期K线数据

        参数：
            kline_data: 统一格式的K线数据

        返回：
            dict: 周期分析结果
                {
                    'period': 'day',
                    'period_name': '日线',
                    'purpose': '寻找机会',
                    'ma': {...},
                    'macd': {...},
                    'kdj': {...},
                    'trend': '上涨趋势/震荡/下跌趋势',
                    'status': '正常/买点附近/卖点附近',
                    'signals': [...],
                }
        """
        if not kline_data or len(kline_data.get('close', [])) < 20:
            return None

        period = kline_data.get('period', 'day')
        period_name = kline_data.get('period_name', period)
        closes = kline_data.get('close', [])
        highs = kline_data.get('high', [])
        lows = kline_data.get('low', [])
        current_price = closes[-1] if closes else 0

        # 1. 均线分析
        ma_result = self._analyze_ma(closes, current_price)

        # 2. MACD分析
        macd_result = self._analyze_macd(closes)

        # 3. KDJ分析
        kdj_result = self._analyze_kdj(highs, lows, closes)

        # 4. 趋势判断
        trend = self._judge_trend(ma_result, macd_result, kdj_result)

        # 5. 状态判断
        status, signals = self._judge_status(ma_result, macd_result, kdj_result, current_price)

        result = {
            'period': period,
            'period_name': period_name,
            'purpose': self.period_purposes.get(period, ''),
            'current_price': current_price,
            'ma': ma_result,
            'macd': macd_result,
            'kdj': kdj_result,
            'trend': trend,
            'status': status,
            'signals': signals,
        }

        return result

    def _analyze_ma(self, closes, current_price):
        """
        均线分析

        返回：
            dict: {
                'ma5': value,
                'ma10': value,
                'ma20': value,
                'ma60': value,
                'ma120': value,
                'arrangement': '多头排列/震荡/空头排列',
                'price_above_ma20': True/False,
                'price_above_ma60': True/False,
            }
        """
        from utils.indicators import calc_ma

        result = {}
        ma_values = {}

        for period in self.ma_periods:
            ma_val = calc_ma(closes, period)
            ma_values[f'ma{period}'] = ma_val
            result[f'ma{period}'] = ma_val

        # 判断均线排列
        ma5 = ma_values.get('ma5', 0) or 0
        ma10 = ma_values.get('ma10', 0) or 0
        ma20 = ma_values.get('ma20', 0) or 0
        ma60 = ma_values.get('ma60', 0) or 0

        if ma5 > ma10 > ma20 > ma60 and ma60 > 0:
            arrangement = '多头排列'
        elif ma5 < ma10 < ma20 < ma60 and ma60 > 0:
            arrangement = '空头排列'
        else:
            arrangement = '震荡'

        result['arrangement'] = arrangement
        result['price_above_ma20'] = current_price >= ma20 if ma20 > 0 else False
        result['price_above_ma60'] = current_price >= ma60 if ma60 > 0 else False

        return result

    def _analyze_macd(self, closes):
        """
        MACD分析（参数：8,21,5）

        返回：
            dict: {
                'diff': value,
                'dea': value,
                'hist': value,
                'signal': '金叉/死叉/红柱扩大/绿柱缩短/...',
                'above_zero': True/False,
                'strength': '强势/中性/弱势',
            }
        """
        from utils.indicators import calc_macd_series

        result = {}

        try:
            diff_series, dea_series, hist_series = calc_macd_series(
                closes, self.macd_fast, self.macd_slow, self.macd_signal
            )

            if len(diff_series) < 2:
                result['diff'] = 0
                result['dea'] = 0
                result['hist'] = 0
                result['signal'] = '数据不足'
                result['above_zero'] = False
                result['strength'] = '中性'
                return result

            diff = float(diff_series.iloc[-1])
            dea = float(dea_series.iloc[-1])
            hist = float(hist_series.iloc[-1])

            prev_diff = float(diff_series.iloc[-2])
            prev_dea = float(dea_series.iloc[-2])
            prev_hist = float(hist_series.iloc[-2])

            result['diff'] = diff
            result['dea'] = dea
            result['hist'] = hist

            # 判断信号
            if prev_diff <= prev_dea and diff > dea:
                signal = '金叉'
            elif prev_diff >= prev_dea and diff < dea:
                signal = '死叉'
            elif hist > 0 and hist > prev_hist:
                signal = '红柱扩大'
            elif hist > 0 and hist < prev_hist:
                signal = '红柱缩小'
            elif hist < 0 and hist < prev_hist:
                signal = '绿柱扩大'
            elif hist < 0 and hist > prev_hist:
                signal = '绿柱缩短'
            else:
                signal = '中性'

            result['signal'] = signal
            result['above_zero'] = diff > 0 and dea > 0

            # 判断强度
            if diff > 0 and dea > 0 and hist > 0:
                strength = '强势'
            elif diff < 0 and dea < 0 and hist < 0:
                strength = '弱势'
            else:
                strength = '中性'

            result['strength'] = strength

        except Exception as e:
            print(f"[MultiPeriod] MACD计算异常: {e}")
            result['diff'] = 0
            result['dea'] = 0
            result['hist'] = 0
            result['signal'] = '计算异常'
            result['above_zero'] = False
            result['strength'] = '中性'

        return result

    def _analyze_kdj(self, highs, lows, closes):
        """
        KDJ分析（参数：13,3,3）

        返回：
            dict: {
                'k': value,
                'd': value,
                'j': value,
                'signal': '低位金叉/高位死叉/钝化/...',
                'zone': '超买/正常/超卖',
            }
        """
        from utils.indicators import calc_kdj_series

        result = {}

        try:
            k_series, d_series, j_series = calc_kdj_series(
                highs, lows, closes, self.kdj_n, self.kdj_m1, self.kdj_m2
            )

            if len(k_series) < 2:
                result['k'] = 50
                result['d'] = 50
                result['j'] = 50
                result['signal'] = '数据不足'
                result['zone'] = '中性'
                return result

            k = float(k_series.iloc[-1])
            d = float(d_series.iloc[-1])
            j = float(j_series.iloc[-1])

            prev_k = float(k_series.iloc[-2])
            prev_d = float(d_series.iloc[-2])

            result['k'] = k
            result['d'] = d
            result['j'] = j

            # 判断信号
            if prev_k <= prev_d and k > d and k < 50:
                signal = '低位金叉'
            elif prev_k >= prev_d and k < d and k > 80:
                signal = '高位死叉'
            elif prev_k <= prev_d and k > d:
                signal = '金叉'
            elif prev_k >= prev_d and k < d:
                signal = '死叉'
            elif j > 100:
                signal = '高位钝化'
            elif j < 0:
                signal = '低位钝化'
            else:
                signal = '中性'

            result['signal'] = signal

            # 判断区域
            if k > 80:
                zone = '超买'
            elif k < 20:
                zone = '超卖'
            else:
                zone = '正常'

            result['zone'] = zone

        except Exception as e:
            print(f"[MultiPeriod] KDJ计算异常: {e}")
            result['k'] = 50
            result['d'] = 50
            result['j'] = 50
            result['signal'] = '计算异常'
            result['zone'] = '中性'

        return result

    def _judge_trend(self, ma_result, macd_result, kdj_result):
        """
        判断周期趋势

        返回：
            str: '上涨趋势' / '震荡' / '下跌趋势'
        """
        score = 0

        # 均线得分
        arrangement = ma_result.get('arrangement', '震荡')
        if arrangement == '多头排列':
            score += 2
        elif arrangement == '空头排列':
            score -= 2

        if ma_result.get('price_above_ma60', False):
            score += 1
        else:
            score -= 1

        # MACD得分
        strength = macd_result.get('strength', '中性')
        if strength == '强势':
            score += 2
        elif strength == '弱势':
            score -= 2

        if macd_result.get('above_zero', False):
            score += 1
        else:
            score -= 1

        # KDJ得分
        zone = kdj_result.get('zone', '中性')
        if zone == '超卖':
            score += 0.5  # 超卖可能反弹
        elif zone == '超买':
            score -= 0.5  # 超买可能回调

        # 判断趋势
        if score >= 3:
            return '上涨趋势'
        elif score <= -3:
            return '下跌趋势'
        else:
            return '震荡'

    def _judge_status(self, ma_result, macd_result, kdj_result, current_price):
        """
        判断周期状态和信号

        返回：
            (status, signals)
            status: '买点附近' / '正常' / '卖点附近'
            signals: 信号列表
        """
        signals = []
        buy_signals = 0
        sell_signals = 0

        # 均线信号
        if ma_result.get('arrangement') == '多头排列':
            signals.append('均线多头排列')
            buy_signals += 1
        elif ma_result.get('arrangement') == '空头排列':
            signals.append('均线空头排列')
            sell_signals += 1

        if ma_result.get('price_above_ma20'):
            signals.append('站上MA20')
            buy_signals += 0.5
        else:
            signals.append('跌破MA20')
            sell_signals += 0.5

        # MACD信号
        macd_signal = macd_result.get('signal', '')
        if macd_signal in ['金叉', '红柱扩大', '绿柱缩短']:
            signals.append(f'MACD{macd_signal}')
            buy_signals += 1
        elif macd_signal in ['死叉', '红柱缩小', '绿柱扩大']:
            signals.append(f'MACD{macd_signal}')
            sell_signals += 1

        # KDJ信号
        kdj_signal = kdj_result.get('signal', '')
        if kdj_signal in ['低位金叉', '金叉']:
            signals.append(f'KDJ{kdj_signal}')
            buy_signals += 1
        elif kdj_signal in ['高位死叉', '死叉']:
            signals.append(f'KDJ{kdj_signal}')
            sell_signals += 1

        if kdj_result.get('zone') == '超卖':
            signals.append('KDJ超卖区')
            buy_signals += 0.5
        elif kdj_result.get('zone') == '超买':
            signals.append('KDJ超买区')
            sell_signals += 0.5

        # 判断状态
        if buy_signals >= 3 and sell_signals <= 1:
            status = '买点附近'
        elif sell_signals >= 3 and buy_signals <= 1:
            status = '卖点附近'
        else:
            status = '正常'

        return status, signals

    def analyze_all_periods(self, code, periods=None):
        """
        分析所有周期

        参数：
            code: 股票代码
            periods: 周期列表，None则分析所有支持的周期

        返回：
            dict: {
                'code': '600580',
                'period_analysis': {
                    'week': {...},
                    'day': {...},
                    '60min': {...},
                    '30min': {...},
                }
            }
        """
        if periods is None:
            periods = ['week', 'day', '60min', '30min']

        from data.multi_period_provider import get_multi_period_provider
        provider = get_multi_period_provider()

        result = {
            'code': code,
            'period_analysis': {},
        }

        for period in periods:
            kline = provider.get_kline(code, period)
            if kline:
                analysis = self.analyze_period(kline)
                if analysis:
                    result['period_analysis'][period] = analysis

        return result

    def analyze_multi_period(self, code, periods):
        """
        分析指定周期

        参数：
            code: 股票代码
            periods: 周期列表

        返回：
            dict: 周期分析结果
        """
        return self.analyze_all_periods(code, periods)


# 单例获取函数
_multi_period_analyzer = None


def get_multi_period_analyzer():
    """获取多周期分析器单例"""
    global _multi_period_analyzer
    if _multi_period_analyzer is None:
        _multi_period_analyzer = MultiPeriodAnalyzer()
    return _multi_period_analyzer
