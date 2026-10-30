"""
AI策略自动选择
根据市场状态自动选择最佳交易策略
"""
from datetime import datetime
from strategy.market_state_engine import MarketStateEngine
from strategy.strategy_library import StrategyLibrary


class StrategySelector:
    """AI策略自动选择器"""

    def __init__(self):
        self.market_engine = MarketStateEngine()
        self.strategy_library = StrategyLibrary()
        self.current_strategy = StrategyLibrary.STRATEGY_TREND
        self.selection_history = []

    def select_strategy(self, index_data=None, market_stats=None):
        """
        自动选择最佳策略

        Returns:
            dict: 策略选择结果
        """
        # 分析市场状态
        market_result = self.market_engine.analyze_market(index_data, market_stats)
        market_state = market_result['state']

        # 根据市场状态选择策略
        strategy_map = {
            MarketStateEngine.STATE_BULL: StrategyLibrary.STRATEGY_HOT_MONEY,
            MarketStateEngine.STATE_BULL_BIAS: StrategyLibrary.STRATEGY_TREND,
            MarketStateEngine.STATE_OSCILLATION: StrategyLibrary.STRATEGY_TREND,
            MarketStateEngine.STATE_BEAR_BIAS: StrategyLibrary.STRATEGY_OVERSOLD,
            MarketStateEngine.STATE_BEAR: StrategyLibrary.STRATEGY_DEFENSE,
        }

        selected_strategy = strategy_map.get(market_state, StrategyLibrary.STRATEGY_TREND)
        self.current_strategy = selected_strategy

        # 生成选择原因
        reasons = self._generate_reasons(market_result, selected_strategy)

        # 操作建议
        suggestions = self._generate_suggestions(selected_strategy, market_state)

        result = {
            'market_state': market_state,
            'market_state_color': market_result['state_color'],
            'market_score': market_result['total_score'],
            'selected_strategy': selected_strategy,
            'strategy_color': StrategyLibrary.STRATEGY_COLORS.get(selected_strategy, '#8b949e'),
            'position_min': market_result['position_min'],
            'position_max': market_result['position_max'],
            'forbidden_strategies': market_result['forbidden_strategies'],
            'reasons': reasons,
            'suggestions': suggestions,
            'market_details': market_result,
            'selection_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        self.selection_history.append(result)
        if len(self.selection_history) > 30:
            self.selection_history = self.selection_history[-30:]

        return result

    def _generate_reasons(self, market_result, strategy):
        """生成选择原因"""
        reasons = []

        # 市场状态原因
        reasons.extend(market_result['reasons'][:3])

        # 策略匹配原因
        strategy_reasons = {
            StrategyLibrary.STRATEGY_HOT_MONEY: [
                '市场强势，游资活跃',
                '热点持续性好，龙头效应明显',
                '短线情绪高涨，适合快进快出',
            ],
            StrategyLibrary.STRATEGY_TREND: [
                '指数稳定，趋势股表现好',
                '资金集中在优质方向',
                '短线情绪一般，不适合追涨',
                '回踩低吸胜率更高',
            ],
            StrategyLibrary.STRATEGY_VALUE: [
                '市场震荡，价值股抗跌',
                '资金偏好确定性高的标的',
                '适合中长期布局',
            ],
            StrategyLibrary.STRATEGY_OVERSOLD: [
                '市场偏弱，超跌股有反弹需求',
                '资金避险情绪浓',
                '寻找错杀机会，快进快出',
            ],
            StrategyLibrary.STRATEGY_DEFENSE: [
                '市场弱势，控制风险第一',
                '减少操作，保留现金',
                '配置防御性品种',
            ],
        }

        reasons.extend(strategy_reasons.get(strategy, []))

        return reasons

    def _generate_suggestions(self, strategy, market_state):
        """生成操作建议"""
        suggestions = {
            StrategyLibrary.STRATEGY_HOT_MONEY: [
                '关注板块龙头和连板股',
                '买点：回封板、分歧低吸',
                '严格止损，不恋战',
                '仓位可积极，但单票不超过30%',
            ],
            StrategyLibrary.STRATEGY_TREND: [
                '关注趋势完好的主升股',
                '买点：回踩10日/20日线低吸',
                '不追涨，耐心等待回调',
                '持有为主，减少频繁交易',
            ],
            StrategyLibrary.STRATEGY_VALUE: [
                '关注低估值高成长标的',
                '分批建仓，中长期持有',
                '忽略短期波动',
                '关注行业景气度变化',
            ],
            StrategyLibrary.STRATEGY_OVERSOLD: [
                '关注严重超跌+基本面好的股票',
                '买点：放量止跌时',
                '快进快出，不贪心',
                '目标位：20日/60日线',
            ],
            StrategyLibrary.STRATEGY_DEFENSE: [
                '减少操作，多看少动',
                '配置银行、公用事业等防御股',
                '保留现金，等待机会',
                '严格控制仓位在30%以下',
            ],
        }

        return suggestions.get(strategy, [])

    def get_current_strategy(self):
        """获取当前策略"""
        return self.current_strategy

    def get_market_state(self):
        """获取当前市场状态"""
        return self.market_engine.get_current_state()

    def get_position_advice(self):
        """获取仓位建议"""
        return self.market_engine.get_position_advice()
