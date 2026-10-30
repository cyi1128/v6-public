"""
实时交易信号中心
分四类信号：买入（绿色）、持有观察（蓝色）、做T机会（黄色）、风险提醒（红色）
"""
from datetime import datetime
import numpy as np


class SignalCenter:
    """实时交易信号中心"""

    # 信号类型
    SIGNAL_BUY = '买入'
    SIGNAL_HOLD = '持有观察'
    SIGNAL_DAY_TRADE = '做T机会'
    SIGNAL_RISK = '风险提醒'

    # 信号颜色
    SIGNAL_COLORS = {
        SIGNAL_BUY: '#00e676',       # 绿色
        SIGNAL_HOLD: '#2979ff',      # 蓝色
        SIGNAL_DAY_TRADE: '#ffea00', # 黄色
        SIGNAL_RISK: '#ff1744',      # 红色
    }

    def __init__(self):
        self.signals = []

    def generate_signals(self, stock_data, daily_data, stock_info=None, portfolio=None):
        """
        生成交易信号

        Args:
            stock_data: 股票数据
            daily_data: 日线数据
            stock_info: 股票信息
            portfolio: 持仓信息（判断是否需要做T/风险提醒）

        Returns:
            list: 信号列表
        """
        if stock_info is None:
            stock_info = {}
        if portfolio is None:
            portfolio = {}

        signals = []

        if len(daily_data) < 20:
            return signals

        closes = [d.get('close', 0) for d in daily_data]
        volumes = [d.get('volume', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]

        current_price = stock_data.get('price', closes[-1] if closes else 0)

        # 1. 买入信号
        buy_signal = self._check_buy_signal(current_price, closes, volumes, highs, lows, stock_info)
        if buy_signal:
            signals.append(buy_signal)

        # 2. 持有观察信号
        hold_signal = self._check_hold_signal(current_price, closes, volumes, stock_info)
        if hold_signal:
            signals.append(hold_signal)

        # 3. 做T机会信号（仅持仓股）
        if portfolio:
            dt_signal = self._check_day_trade_signal(current_price, closes, volumes)
            if dt_signal:
                signals.append(dt_signal)

        # 4. 风险提醒信号
        risk_signal = self._check_risk_signal(current_price, closes, volumes, highs, stock_info)
        if risk_signal:
            signals.append(risk_signal)

        return signals

    def _check_buy_signal(self, price, closes, volumes, highs, lows, stock_info):
        """检查买入信号"""
        if len(closes) < 20:
            return None

        reasons = []
        score = 0

        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        # 条件1：站上5日线
        if price > ma5:
            score += 1
            reasons.append('站上5日线')

        # 条件2：5日线上穿10日线
        if len(closes) >= 6:
            ma5_prev = np.mean(closes[-6:-1])
            ma10_prev = np.mean(closes[-11:-1])
            if ma5_prev < ma10_prev and ma5 > ma10:
                score += 2
                reasons.append('5日线上穿10日线')

        # 条件3：放量上涨
        if len(volumes) >= 2 and len(closes) >= 2:
            vol_5 = np.mean(volumes[-5:])
            vol_20 = np.mean(volumes[-20:])
            if vol_20 > 0 and vol_5 / vol_20 > 1.5 and closes[-1] > closes[-2]:
                score += 2
                reasons.append('放量上涨')

        # 条件4：KDJ金叉（简化）
        if len(closes) >= 9:
            low_9 = min(lows[-9:])
            high_9 = max(highs[-9:])
            if high_9 > low_9:
                rsv = (closes[-1] - low_9) / (high_9 - low_9) * 100
                rsv_prev = (closes[-2] - low_9) / (high_9 - low_9) * 100 if len(closes) >= 10 else rsv
                if rsv_prev < 30 and rsv > rsv_prev:
                    score += 1
                    reasons.append('KDJ低位金叉')

        # 条件5：回踩20日线企稳
        if len(closes) >= 3:
            if closes[-3] < ma20 and closes[-1] > ma20 and abs(closes[-2] - ma20) / ma20 < 0.02:
                score += 2
                reasons.append('回踩20日线企稳')

        if score >= 4:
            return {
                'type': self.SIGNAL_BUY,
                'color': self.SIGNAL_COLORS[self.SIGNAL_BUY],
                'price': price,
                'score': score,
                'reasons': reasons,
                'suggestion': f'建议关注，买入理由：{"、".join(reasons)}',
                'time': datetime.now().strftime('%H:%M:%S'),
            }

        return None

    def _check_hold_signal(self, price, closes, volumes, stock_info):
        """检查持有观察信号"""
        if len(closes) < 20:
            return None

        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        # 多头排列且价格在均线上方
        if ma5 > ma10 > ma20 and price > ma5:
            return {
                'type': self.SIGNAL_HOLD,
                'color': self.SIGNAL_COLORS[self.SIGNAL_HOLD],
                'price': price,
                'reasons': ['MA多头排列', '股价在5日线上方', '趋势完好'],
                'suggestion': '趋势完好，建议持有，回踩可加仓',
                'time': datetime.now().strftime('%H:%M:%S'),
            }

        return None

    def _check_day_trade_signal(self, price, closes, volumes):
        """检查做T机会信号"""
        if len(closes) < 20:
            return None

        from strategy.day_trading import DayTradingSystem
        dt = DayTradingSystem()
        result = dt.analyze({'price': price}, closes)

        if result.get('has_opportunity'):
            return {
                'type': self.SIGNAL_DAY_TRADE,
                'color': self.SIGNAL_COLORS[self.SIGNAL_DAY_TRADE],
                'price': price,
                'high_sell': result['high_sell_zone'],
                'low_buy': result['low_buy_zone'],
                'reasons': [f"高抛位{result['high_sell_zone']:.2f}", f"低吸位{result['low_buy_zone']:.2f}"],
                'suggestion': result['suggestion'],
                'time': datetime.now().strftime('%H:%M:%S'),
            }

        return None

    def _check_risk_signal(self, price, closes, volumes, highs, stock_info):
        """检查风险信号"""
        if len(closes) < 20:
            return None

        reasons = []
        risk_level = 0

        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        # 跌破5日线
        if price < ma5:
            risk_level += 1
            reasons.append('跌破5日线')

        # 5日线下穿10日线
        if len(closes) >= 6:
            ma5_prev = np.mean(closes[-6:-1])
            ma10_prev = np.mean(closes[-11:-1])
            if ma5_prev > ma10_prev and ma5 < ma10:
                risk_level += 2
                reasons.append('5日线下穿10日线（死叉）')

        # 放量下跌
        if len(volumes) >= 2 and len(closes) >= 2:
            vol_5 = np.mean(volumes[-5:])
            vol_20 = np.mean(volumes[-20:])
            if vol_20 > 0 and vol_5 / vol_20 > 1.5 and closes[-1] < closes[-2]:
                risk_level += 2
                reasons.append('放量下跌')

        # 跌破20日线
        if price < ma20:
            risk_level += 2
            reasons.append('跌破20日线')

        # 换手率过高
        turnover = stock_info.get('turnover_rate', 0)
        if turnover > 25:
            risk_level += 1
            reasons.append(f'换手率过高({turnover:.1f}%)')

        if risk_level >= 3:
            return {
                'type': self.SIGNAL_RISK,
                'color': self.SIGNAL_COLORS[self.SIGNAL_RISK],
                'price': price,
                'risk_level': risk_level,
                'reasons': reasons,
                'suggestion': f'风险提醒：{"、".join(reasons)}，建议减仓或止损',
                'time': datetime.now().strftime('%H:%M:%S'),
            }

        return None

    def get_signal_summary(self, signals):
        """获取信号汇总"""
        summary = {
            'buy_count': sum(1 for s in signals if s['type'] == self.SIGNAL_BUY),
            'hold_count': sum(1 for s in signals if s['type'] == self.SIGNAL_HOLD),
            'day_trade_count': sum(1 for s in signals if s['type'] == self.SIGNAL_DAY_TRADE),
            'risk_count': sum(1 for s in signals if s['type'] == self.SIGNAL_RISK),
            'total': len(signals),
        }
        return summary
