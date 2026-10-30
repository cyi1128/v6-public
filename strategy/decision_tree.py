"""
AI买卖决策树
不简单提示买卖，而是分析原因，给出条件满足情况和仓位建议
"""
from datetime import datetime


class DecisionTree:
    """AI买卖决策树"""

    # 决策结果
    DECISION_BUY = '买入'
    DECISION_WATCH = '观望'
    DECISION_AVOID = '拒绝交易'
    DECISION_SELL = '卖出'

    def __init__(self):
        pass

    def analyze(self, stock_data, score_result, strategy_result=None, risk_reward=None):
        """
        买卖决策分析

        Args:
            stock_data: 股票数据
            score_result: 六维评分结果
            strategy_result: 策略分析结果
            risk_reward: 风险收益比结果

        Returns:
            dict: 决策结果
        """
        if strategy_result is None:
            strategy_result = {}
        if risk_reward is None:
            risk_reward = {}

        # 收集条件
        conditions = self._collect_conditions(score_result, strategy_result, risk_reward)

        # 计算决策
        decision, confidence = self._make_decision(conditions, score_result, risk_reward)

        # 仓位建议
        position = self._calc_position(decision, confidence, risk_reward)

        # 原因分析
        reasons = self._generate_reasons(decision, conditions, score_result, risk_reward)

        return {
            'decision': decision,
            'confidence': confidence,
            'position': position,
            'conditions': conditions,
            'reasons': reasons,
            'buy_price': stock_data.get('price', 0),
            'stop_loss': risk_reward.get('stop_loss', 0),
            'target_price': risk_reward.get('target_price', 0),
            'risk_reward_ratio': risk_reward.get('ratio', 0),
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _collect_conditions(self, score_result, strategy_result, risk_reward):
        """收集决策条件"""
        conditions = {
            'industry_strong': False,
            'fund_inflow': False,
            'technical_breakout': False,
            'sentiment_ok': False,
            'market_ok': False,
            'policy_ok': False,
            'risk_reward_ok': False,
            'strategy_match': False,
        }

        # 行业强
        industry_score = score_result.get('industry_score', 0)
        if industry_score >= 10:
            conditions['industry_strong'] = True

        # 资金进入
        fund_score = score_result.get('fund_score', 0)
        if fund_score >= 15:
            conditions['fund_inflow'] = True

        # 技术突破
        technical_score = score_result.get('technical_score', 0)
        if technical_score >= 15:
            conditions['technical_breakout'] = True

        # 情绪允许
        sentiment_score = score_result.get('sentiment_score', 0)
        if sentiment_score >= 8:
            conditions['sentiment_ok'] = True

        # 市场环境
        market_score = score_result.get('market_score', 0)
        if market_score >= 10:
            conditions['market_ok'] = True

        # 政策消息
        policy_score = score_result.get('policy_score', 0)
        if policy_score >= 10:
            conditions['policy_ok'] = True

        # 风险收益比
        ratio = risk_reward.get('ratio', 0)
        if ratio >= 2:
            conditions['risk_reward_ok'] = True

        # 策略匹配
        strategy_score = strategy_result.get('score', 0)
        if strategy_score >= 60:
            conditions['strategy_match'] = True

        return conditions

    def _make_decision(self, conditions, score_result, risk_reward):
        """做出决策"""
        total_score = score_result.get('total_score', 0)
        ratio = risk_reward.get('ratio', 0)

        # 统计满足条件数
        met_count = sum(1 for v in conditions.values() if v)
        total_conditions = len(conditions)

        # 决策逻辑
        if total_score >= 90 and met_count >= 6 and ratio >= 2:
            return self.DECISION_BUY, 90
        elif total_score >= 75 and met_count >= 5 and ratio >= 1.5:
            return self.DECISION_BUY, 75
        elif total_score >= 60 and met_count >= 4:
            return self.DECISION_WATCH, 60
        elif total_score < 50 or met_count <= 2:
            return self.DECISION_AVOID, 30
        else:
            return self.DECISION_WATCH, 50

    def _calc_position(self, decision, confidence, risk_reward):
        """计算仓位建议"""
        if decision == self.DECISION_AVOID:
            return '0%（不参与）'

        ratio = risk_reward.get('ratio', 0)

        # 基础仓位
        if confidence >= 85:
            base = 30
        elif confidence >= 70:
            base = 20
        else:
            base = 10

        # 风险收益比调整
        if ratio >= 3:
            base += 10
        elif ratio >= 2:
            base += 5
        elif ratio < 1.5:
            base -= 5

        base = max(5, min(50, base))

        return f'{base}%'

    def _generate_reasons(self, decision, conditions, score_result, risk_reward):
        """生成原因分析"""
        reasons = {
            'met': [],
            'not_met': [],
            'summary': '',
        }

        condition_names = {
            'industry_strong': '行业强',
            'fund_inflow': '资金进入',
            'technical_breakout': '技术突破',
            'sentiment_ok': '情绪允许',
            'market_ok': '市场环境好',
            'policy_ok': '消息面支持',
            'risk_reward_ok': '风险收益比好',
            'strategy_match': '策略匹配',
        }

        for key, met in conditions.items():
            name = condition_names.get(key, key)
            if met:
                reasons['met'].append(name)
            else:
                reasons['not_met'].append(name)

        # 总结
        if decision == self.DECISION_BUY:
            reasons['summary'] = f"条件满足{len(reasons['met'])}/{len(conditions)}，综合评分{score_result.get('total_score', 0)}分，风险收益比{risk_reward.get('ratio', 0):.1f}:1，建议买入"
        elif decision == self.DECISION_WATCH:
            reasons['summary'] = f"条件满足{len(reasons['met'])}/{len(conditions)}，部分条件未满足，建议观望等待更好时机"
        else:
            reasons['summary'] = f"条件仅满足{len(reasons['met'])}/{len(conditions)}，虽然技术面可能有机会，但资金/消息/风险收益比不支持，拒绝交易"

        return reasons
