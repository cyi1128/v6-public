"""
AI风险收益比模型
每次交易计算收益空间 vs 下跌风险
"""
import numpy as np


class RiskRewardModel:
    """AI风险收益比模型"""

    # 评级
    RATINGS = [
        (3.0, '优秀', '#3fb950'),
        (2.0, '良好', '#58a6ff'),
        (1.5, '一般', '#d29922'),
        (1.0, '较差', '#f85149'),
        (0, '不建议', '#da3633'),
    ]

    def __init__(self):
        pass

    def calculate(self, stock_data, daily_data, stock_info=None):
        """
        计算风险收益比

        Args:
            stock_data: 股票数据，包含price
            daily_data: 日线数据
            stock_info: 股票信息

        Returns:
            dict: 风险收益比结果
        """
        if stock_info is None:
            stock_info = {}

        current_price = stock_data.get('price', 0)
        if current_price <= 0 or len(daily_data) < 20:
            return {
                'ratio': 0,
                'rating': '数据不足',
                'rating_color': '#8b949e',
                'expected_return': 0,
                'max_risk': 0,
                'target_price': 0,
                'stop_loss': 0,
                'support': 0,
                'resistance': 0,
            }

        closes = [d.get('close', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]

        # 计算支撑位和压力位
        support = self._calc_support(closes, lows)
        resistance = self._calc_resistance(closes, highs)

        # 计算目标价和止损价
        target_price = self._calc_target(current_price, resistance, closes)
        stop_loss = self._calc_stop_loss(current_price, support, closes)

        # 计算预期收益和最大风险
        expected_return = (target_price - current_price) / current_price * 100 if current_price > 0 else 0
        max_risk = (current_price - stop_loss) / current_price * 100 if current_price > 0 else 0

        # 风险收益比
        if max_risk > 0:
            ratio = expected_return / max_risk
        else:
            ratio = 0

        # 评级
        rating, rating_color = self._get_rating(ratio)

        return {
            'ratio': round(ratio, 2),
            'rating': rating,
            'rating_color': rating_color,
            'expected_return': round(expected_return, 2),
            'max_risk': round(max_risk, 2),
            'target_price': round(target_price, 2),
            'stop_loss': round(stop_loss, 2),
            'support': round(support, 2),
            'resistance': round(resistance, 2),
            'current_price': current_price,
            'analysis': self._generate_analysis(ratio, expected_return, max_risk),
        }

    def _calc_support(self, closes, lows):
        """计算支撑位"""
        # 近20日最低点
        recent_low = min(lows[-20:])
        # 20日均线
        ma20 = np.mean(closes[-20:])
        # 取较低的作为支撑
        return min(recent_low, ma20 * 0.97)

    def _calc_resistance(self, closes, highs):
        """计算压力位"""
        # 近60日最高点
        recent_high = max(highs[-60:]) if len(highs) >= 60 else max(highs)
        # 前期高点
        return recent_high

    def _calc_target(self, current_price, resistance, closes):
        """计算目标价"""
        # 目标1：压力位
        target1 = resistance
        # 目标2：当前价+15%（短线目标）
        target2 = current_price * 1.15
        # 取较低的作为目标（更保守）
        return min(target1, target2)

    def _calc_stop_loss(self, current_price, support, closes):
        """计算止损价"""
        # 止损1：支撑位下方2%
        stop1 = support * 0.98
        # 止损2：当前价-5%（固定止损）
        stop2 = current_price * 0.95
        # 取较高的作为止损（更严格）
        return max(stop1, stop2)

    def _get_rating(self, ratio):
        """获取风险收益比评级"""
        for threshold, rating, color in self.RATINGS:
            if ratio >= threshold:
                return rating, color
        return '不建议', '#da3633'

    def _generate_analysis(self, ratio, expected_return, max_risk):
        """生成分析文字"""
        if ratio >= 3:
            return f"风险收益比{ratio:.1f}:1，预期收益{expected_return:.1f}%，最大风险{max_risk:.1f}%，性价比极高，值得参与"
        elif ratio >= 2:
            return f"风险收益比{ratio:.1f}:1，预期收益{expected_return:.1f}%，最大风险{max_risk:.1f}%，性价比良好，可以参与"
        elif ratio >= 1.5:
            return f"风险收益比{ratio:.1f}:1，预期收益{expected_return:.1f}%，最大风险{max_risk:.1f}%，性价比一般，轻仓参与"
        elif ratio >= 1:
            return f"风险收益比{ratio:.1f}:1，预期收益{expected_return:.1f}%，最大风险{max_risk:.1f}%，性价比差，不建议参与"
        else:
            return f"风险收益比{ratio:.1f}:1，预期收益{expected_return:.1f}%，最大风险{max_risk:.1f}%，风险大于收益，拒绝交易"
