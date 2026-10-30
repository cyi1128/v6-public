"""
AI做T系统
针对持仓股票，自动计算高抛区域和低吸区域
依据：分时、KDJ、MACD、均线、成交量
"""
from datetime import datetime
import numpy as np


class DayTradingSystem:
    """AI做T系统"""

    def __init__(self):
        pass

    def analyze(self, stock_data, daily_data, intraday_data=None, stock_info=None):
        """
        分析做T机会

        Args:
            stock_data: 股票数据
            daily_data: 日线数据
            intraday_data: 分时数据（可选）
            stock_info: 股票信息

        Returns:
            dict: 做T分析结果
        """
        if stock_info is None:
            stock_info = {}
        if intraday_data is None:
            intraday_data = []

        if len(daily_data) < 20:
            return {
                'has_opportunity': False,
                'message': '数据不足',
                'high_sell_zone': 0,
                'low_buy_zone': 0,
                'suggestion': '数据不足，无法判断',
            }

        closes = [d.get('close', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]

        current_price = stock_data.get('price', closes[-1] if closes else 0)

        # 计算技术指标
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        # KDJ（简化）
        kdj = self._calc_kdj(closes, highs, lows)

        # MACD（简化）
        macd_signal = self._calc_macd_signal(closes)

        # 布林带
        boll = self._calc_bollinger(closes)

        # 计算高抛和低吸区域
        high_sell_zone = self._calc_high_sell_zone(current_price, ma5, ma10, boll, kdj)
        low_buy_zone = self._calc_low_buy_zone(current_price, ma5, ma10, boll, kdj)

        # 判断是否有做T机会
        has_opportunity, suggestion = self._judge_opportunity(
            current_price, high_sell_zone, low_buy_zone, kdj, macd_signal, volumes
        )

        return {
            'has_opportunity': has_opportunity,
            'current_price': current_price,
            'high_sell_zone': round(high_sell_zone, 2),
            'low_buy_zone': round(low_buy_zone, 2),
            'ma5': round(ma5, 2),
            'ma10': round(ma10, 2),
            'ma20': round(ma20, 2),
            'kdj_k': round(kdj.get('k', 50), 1),
            'kdj_d': round(kdj.get('d', 50), 1),
            'kdj_j': round(kdj.get('j', 50), 1),
            'macd_signal': macd_signal,
            'boll_upper': round(boll['upper'], 2),
            'boll_middle': round(boll['middle'], 2),
            'boll_lower': round(boll['lower'], 2),
            'suggestion': suggestion,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _calc_kdj(self, closes, highs, lows, n=9):
        """计算KDJ"""
        if len(closes) < n:
            return {'k': 50, 'd': 50, 'j': 50}

        low_n = min(lows[-n:])
        high_n = max(highs[-n:])

        if high_n == low_n:
            rsv = 50
        else:
            rsv = (closes[-1] - low_n) / (high_n - low_n) * 100

        # 简化计算
        k = rsv * 0.33 + 50 * 0.67
        d = k * 0.33 + 50 * 0.67
        j = 3 * k - 2 * d

        return {'k': k, 'd': d, 'j': j}

    def _calc_macd_signal(self, closes):
        """计算MACD信号"""
        if len(closes) < 26:
            return '中性'

        ema12 = self._ema(closes[-12:], 12)
        ema26 = self._ema(closes[-26:], 26)
        diff = ema12 - ema26

        if diff > 0 and closes[-1] > closes[-5]:
            return '金叉/红柱扩大'
        elif diff > 0:
            return '红柱'
        elif diff < 0 and closes[-1] < closes[-5]:
            return '死叉/绿柱扩大'
        elif diff < 0:
            return '绿柱'
        else:
            return '中性'

    def _ema(self, data, period):
        """计算EMA"""
        if not data:
            return 0
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _calc_bollinger(self, closes, period=20):
        """计算布林带"""
        if len(closes) < period:
            period = len(closes)

        middle = np.mean(closes[-period:])
        std = np.std(closes[-period:])

        return {
            'upper': middle + 2 * std,
            'middle': middle,
            'lower': middle - 2 * std,
        }

    def _calc_high_sell_zone(self, current_price, ma5, ma10, boll, kdj):
        """计算高抛区域"""
        # 基础：当前价上方1.5%-3%
        base_high = current_price * 1.02

        # KDJ超卖时，高抛位降低
        if kdj['j'] > 90:
            base_high = current_price * 1.01  # 已经很高，稍微高一点就卖

        # 接近布林上轨，高抛位设在上轨附近
        if current_price > boll['middle']:
            base_high = min(base_high, boll['upper'] * 0.99)

        # MA5压力
        if current_price < ma5:
            base_high = min(base_high, ma5 * 1.005)

        return base_high

    def _calc_low_buy_zone(self, current_price, ma5, ma10, boll, kdj):
        """计算低吸区域"""
        # 基础：当前价下方1.5%-3%
        base_low = current_price * 0.98

        # KDJ超卖时，低吸位提高
        if kdj['j'] < 10:
            base_low = current_price * 0.99  # 已经很低，稍微低一点就买

        # 接近布林下轨，低吸位设在下轨附近
        if current_price < boll['middle']:
            base_low = max(base_low, boll['lower'] * 1.01)

        # MA5支撑
        if current_price > ma5:
            base_low = max(base_low, ma5 * 0.995)

        return base_low

    def _judge_opportunity(self, current_price, high_sell, low_buy, kdj, macd_signal, volumes):
        """判断做T机会"""
        suggestions = []

        # 空间判断
        high_space = (high_sell - current_price) / current_price * 100
        low_space = (current_price - low_buy) / current_price * 100

        if high_space < 0.5 and low_space < 0.5:
            return False, '当前价格波动空间小，不适合做T'

        # KDJ判断
        if kdj['j'] > 90:
            suggestions.append('KDJ超买，可考虑高抛')
        elif kdj['j'] < 10:
            suggestions.append('KDJ超卖，可考虑低吸')

        # MACD判断
        if '死叉' in macd_signal:
            suggestions.append('MACD死叉，逢高减仓')
        elif '金叉' in macd_signal:
            suggestions.append('MACD金叉，逢低加仓')

        # 量能判断
        if len(volumes) >= 5:
            vol_5 = np.mean(volumes[-5:])
            vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else vol_5
            if vol_20 > 0 and vol_5 / vol_20 > 1.5:
                suggestions.append('放量波动，做T机会增加')

        if not suggestions:
            suggestions.append('可在区间内高抛低吸')

        suggestion = f"高抛位: {high_sell:.2f} | 低吸位: {low_buy:.2f} | {' | '.join(suggestions)}"
        return True, suggestion
