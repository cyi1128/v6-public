"""
AI市场状态识别引擎
自动判断市场处于：牛市攻击模式、震荡轮动模式、熊市防守模式
根据市场状态自动推荐策略和仓位
"""
from datetime import datetime
import numpy as np


class MarketStateEngine:
    """AI市场状态识别引擎"""

    # 市场状态常量
    STATE_BULL = '牛市攻击'
    STATE_BULL_BIAS = '震荡偏强'
    STATE_OSCILLATION = '震荡轮动'
    STATE_BEAR_BIAS = '震荡偏弱'
    STATE_BEAR = '熊市防守'

    # 状态颜色
    STATE_COLORS = {
        STATE_BULL: '#f85149',
        STATE_BULL_BIAS: '#d29922',
        STATE_OSCILLATION: '#58a6ff',
        STATE_BEAR_BIAS: '#8b949e',
        STATE_BEAR: '#3fb950',
    }

    # 推荐策略映射
    STRATEGY_MAP = {
        STATE_BULL: '游资短线攻击',
        STATE_BULL_BIAS: '趋势波段',
        STATE_OSCILLATION: '波段低吸',
        STATE_BEAR_BIAS: '超跌反弹',
        STATE_BEAR: '防守避险',
    }

    # 推荐仓位映射
    POSITION_MAP = {
        STATE_BULL: (70, 90),
        STATE_BULL_BIAS: (50, 70),
        STATE_OSCILLATION: (40, 60),
        STATE_BEAR_BIAS: (20, 40),
        STATE_BEAR: (10, 30),
    }

    # 禁止策略映射
    FORBIDDEN_MAP = {
        STATE_BULL: [],
        STATE_BULL_BIAS: ['追涨打板'],
        STATE_OSCILLATION: ['追涨打板', '满仓操作'],
        STATE_BEAR_BIAS: ['追涨打板', '满仓操作', '追高'],
        STATE_BEAR: ['追涨打板', '满仓操作', '追高', '抄底'],
    }

    def __init__(self):
        self.current_state = self.STATE_OSCILLATION
        self.state_history = []
        self.market_data = {}

    def analyze_market(self, index_data=None, market_stats=None):
        """
        分析市场状态

        Args:
            index_data: 指数数据列表，每个元素包含close, volume等
            market_stats: 市场统计数据，包含limit_up_count, limit_down_count,
                         sector_rotation, fund_flow等

        Returns:
            dict: 市场状态分析结果
        """
        if index_data is None:
            index_data = []
        if market_stats is None:
            market_stats = {}

        # 计算各维度得分
        trend_score = self._calc_trend_score(index_data)
        volume_score = self._calc_volume_score(index_data)
        sentiment_score = self._calc_sentiment_score(market_stats)
        fund_score = self._calc_fund_score(market_stats)
        rotation_score = self._calc_rotation_score(market_stats)

        # 综合得分（0-100）
        total_score = (
            trend_score * 0.30 +
            volume_score * 0.20 +
            sentiment_score * 0.25 +
            fund_score * 0.15 +
            rotation_score * 0.10
        )

        # 判断市场状态
        state = self._determine_state(total_score, trend_score, sentiment_score)

        # 生成分析原因
        reasons = self._generate_reasons(
            trend_score, volume_score, sentiment_score,
            fund_score, rotation_score, state
        )

        # 推荐策略
        recommended_strategy = self.STRATEGY_MAP.get(state, '波段低吸')
        position_range = self.POSITION_MAP.get(state, (40, 60))
        forbidden = self.FORBIDDEN_MAP.get(state, [])

        result = {
            'state': state,
            'state_color': self.STATE_COLORS.get(state, '#58a6ff'),
            'total_score': total_score,
            'trend_score': trend_score,
            'volume_score': volume_score,
            'sentiment_score': sentiment_score,
            'fund_score': fund_score,
            'rotation_score': rotation_score,
            'recommended_strategy': recommended_strategy,
            'position_min': position_range[0],
            'position_max': position_range[1],
            'forbidden_strategies': forbidden,
            'reasons': reasons,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        self.current_state = state
        self.state_history.append(result)

        # 只保留最近30天记录
        if len(self.state_history) > 30:
            self.state_history = self.state_history[-30:]

        return result

    def _calc_trend_score(self, index_data):
        """计算趋势得分（0-100）"""
        if len(index_data) < 20:
            return 50

        closes = [d.get('close', 0) for d in index_data[-60:]]
        if not closes or closes[-1] == 0:
            return 50

        score = 50

        # MA5 > MA10 > MA20 多头排列
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        if ma5 > ma10 > ma20:
            score += 25
        elif ma5 > ma10:
            score += 10
        elif ma5 < ma10 < ma20:
            score -= 25
        elif ma5 < ma10:
            score -= 10

        # 站上20日线
        if closes[-1] > ma20:
            score += 10
        else:
            score -= 10

        # 近5日涨幅
        if len(closes) >= 6:
            change_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
            if change_5d > 3:
                score += 15
            elif change_5d > 1:
                score += 5
            elif change_5d < -3:
                score -= 15
            elif change_5d < -1:
                score -= 5

        return max(0, min(100, score))

    def _calc_volume_score(self, index_data):
        """计算量能得分（0-100）"""
        if len(index_data) < 20:
            return 50

        volumes = [d.get('volume', 0) for d in index_data[-20:]]
        if not volumes or sum(volumes) == 0:
            return 50

        score = 50

        # 近5日均量 vs 20日均量
        vol_5 = np.mean(volumes[-5:])
        vol_20 = np.mean(volumes)

        if vol_20 > 0:
            vol_ratio = vol_5 / vol_20
            if vol_ratio > 1.5:
                score += 25
            elif vol_ratio > 1.2:
                score += 15
            elif vol_ratio > 1.0:
                score += 5
            elif vol_ratio < 0.7:
                score -= 20
            elif vol_ratio < 0.85:
                score -= 10

        # 量价配合
        closes = [d.get('close', 0) for d in index_data[-5:]]
        if len(closes) >= 2 and closes[-1] > closes[-2] and volumes[-1] > volumes[-2]:
            score += 15  # 放量上涨
        elif len(closes) >= 2 and closes[-1] < closes[-2] and volumes[-1] > volumes[-2]:
            score -= 15  # 放量下跌

        return max(0, min(100, score))

    def _calc_sentiment_score(self, market_stats):
        """计算市场情绪得分（0-100）"""
        score = 50

        limit_up = market_stats.get('limit_up_count', 30)
        limit_down = market_stats.get('limit_down_count', 10)
        limit_up_ratio = market_stats.get('limit_up_ratio', 0.5)

        # 涨停数量
        if limit_up >= 80:
            score += 25
        elif limit_up >= 50:
            score += 15
        elif limit_up >= 30:
            score += 5
        elif limit_up < 15:
            score -= 20
        elif limit_up < 25:
            score -= 10

        # 涨跌停比
        if limit_down > 0:
            ratio = limit_up / limit_down
            if ratio > 5:
                score += 15
            elif ratio > 2:
                score += 5
            elif ratio < 0.5:
                score -= 15
            elif ratio < 1:
                score -= 5

        # 涨停封板率
        if limit_up_ratio >= 0.8:
            score += 10
        elif limit_up_ratio >= 0.6:
            score += 5
        elif limit_up_ratio < 0.4:
            score -= 10

        return max(0, min(100, score))

    def _calc_fund_score(self, market_stats):
        """计算资金流向得分（0-100）"""
        score = 50

        fund_flow = market_stats.get('main_fund_flow', 0)  # 亿元
        north_flow = market_stats.get('north_flow', 0)  # 亿元

        # 主力资金
        if fund_flow > 100:
            score += 25
        elif fund_flow > 50:
            score += 15
        elif fund_flow > 0:
            score += 5
        elif fund_flow < -100:
            score -= 25
        elif fund_flow < -50:
            score -= 15
        elif fund_flow < 0:
            score -= 5

        # 北向资金
        if north_flow > 50:
            score += 15
        elif north_flow > 20:
            score += 5
        elif north_flow < -50:
            score -= 15
        elif north_flow < -20:
            score -= 5

        return max(0, min(100, score))

    def _calc_rotation_score(self, market_stats):
        """计算板块轮动得分（0-100）"""
        score = 50

        hot_sustain = market_stats.get('hot_sustain_days', 2)
        sector_count = market_stats.get('rising_sector_count', 10)

        # 热点持续性
        if hot_sustain >= 5:
            score += 20  # 热点持续，趋势行情
        elif hot_sustain >= 3:
            score += 10
        elif hot_sustain <= 1:
            score -= 15  # 快速轮动，震荡行情

        # 上涨板块数量
        if sector_count >= 20:
            score += 15
        elif sector_count >= 10:
            score += 5
        elif sector_count < 5:
            score -= 15

        return max(0, min(100, score))

    def _determine_state(self, total_score, trend_score, sentiment_score):
        """判断市场状态"""
        # 极端情况优先判断
        if total_score >= 80 and trend_score >= 70 and sentiment_score >= 70:
            return self.STATE_BULL
        if total_score <= 25 and trend_score <= 35 and sentiment_score <= 35:
            return self.STATE_BEAR

        # 细分状态
        if total_score >= 65:
            return self.STATE_BULL_BIAS
        elif total_score >= 45:
            return self.STATE_OSCILLATION
        else:
            return self.STATE_BEAR_BIAS

    def _generate_reasons(self, trend, volume, sentiment, fund, rotation, state):
        """生成分析原因"""
        reasons = []

        # 趋势原因
        if trend >= 70:
            reasons.append('指数趋势向上，多头排列')
        elif trend >= 50:
            reasons.append('指数震荡偏强')
        elif trend >= 35:
            reasons.append('指数横盘震荡')
        else:
            reasons.append('指数趋势向下，注意风险')

        # 量能原因
        if volume >= 65:
            reasons.append('成交量放大，资金活跃')
        elif volume <= 35:
            reasons.append('成交量萎缩，观望情绪浓')

        # 情绪原因
        if sentiment >= 70:
            reasons.append('市场情绪高涨，涨停数量增加')
        elif sentiment <= 35:
            reasons.append('市场情绪低迷，个股普跌')

        # 资金原因
        if fund >= 65:
            reasons.append('主力资金持续流入')
        elif fund <= 35:
            reasons.append('主力资金流出明显')

        # 轮动原因
        if rotation >= 65:
            reasons.append('热点持续，板块效应强')
        elif rotation <= 35:
            reasons.append('板块快速轮动，个股分化')

        # 策略建议
        if state == self.STATE_BULL:
            reasons.append('建议积极做多，关注龙头和热点')
        elif state == self.STATE_BULL_BIAS:
            reasons.append('建议趋势持股，回踩低吸')
        elif state == self.STATE_OSCILLATION:
            reasons.append('建议波段操作，不追涨不杀跌')
        elif state == self.STATE_BEAR_BIAS:
            reasons.append('建议控制仓位，等待企稳信号')
        else:
            reasons.append('建议防守为主，现金为王')

        return reasons

    def get_current_state(self):
        """获取当前市场状态"""
        return self.current_state

    def get_state_history(self, days=7):
        """获取历史状态"""
        return self.state_history[-days:]

    def get_position_advice(self):
        """获取仓位建议"""
        return self.POSITION_MAP.get(self.current_state, (40, 60))

    def get_recommended_strategy(self):
        """获取推荐策略"""
        return self.STRATEGY_MAP.get(self.current_state, '波段低吸')
