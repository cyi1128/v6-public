"""
AI机会优先级排序
全市场自动排名，今日机会TOP50
排序维度：上涨概率、主力资金、题材强度、技术位置、风险收益比
"""
from datetime import datetime


class OpportunityRanker:
    """AI机会优先级排序器"""

    def __init__(self):
        pass

    def rank(self, stocks_list):
        """
        对股票列表进行机会优先级排序

        Args:
            stocks_list: 股票列表，每个元素包含：
                - ts_code, name, price
                - six_dim_score: 六维评分结果
                - risk_reward: 风险收益比结果
                - strategy_score: 策略评分
                - fund_score: 资金分
                - technical_score: 技术分
                - industry_score: 行业分

        Returns:
            list: 排序后的股票列表，每项含排名和综合得分
        """
        ranked = []

        for stock in stocks_list:
            # 计算各维度得分（0-100）
            probability_score = self._calc_probability_score(stock)
            fund_score = self._calc_fund_score(stock)
            theme_score = self._calc_theme_score(stock)
            technical_score = self._calc_technical_position_score(stock)
            risk_reward_score = self._calc_risk_reward_score(stock)

            # 综合得分（加权）
            total_score = (
                probability_score * 0.25 +
                fund_score * 0.25 +
                theme_score * 0.20 +
                technical_score * 0.15 +
                risk_reward_score * 0.15
            )

            stock_copy = dict(stock)
            stock_copy.update({
                'rank_score': round(total_score, 2),
                'probability_score': round(probability_score, 1),
                'fund_rank_score': round(fund_score, 1),
                'theme_score': round(theme_score, 1),
                'technical_position_score': round(technical_score, 1),
                'risk_reward_rank_score': round(risk_reward_score, 1),
            })
            ranked.append(stock_copy)

        # 按综合得分排序
        ranked.sort(key=lambda x: x['rank_score'], reverse=True)

        # 添加排名
        for i, stock in enumerate(ranked):
            stock['rank'] = i + 1

        return ranked

    def get_top_n(self, stocks_list, n=50):
        """获取TOP N机会"""
        ranked = self.rank(stocks_list)
        return ranked[:n]

    def _calc_probability_score(self, stock):
        """上涨概率得分（基于六维评分）"""
        six_dim = stock.get('six_dim_score', {})
        total = six_dim.get('total_score', 60)
        # 120分制映射到100分
        return min(100, total / 120 * 100)

    def _calc_fund_score(self, stock):
        """主力资金得分"""
        six_dim = stock.get('six_dim_score', {})
        fund = six_dim.get('fund_score', 12)
        # 25分制映射到100分
        return min(100, fund / 25 * 100)

    def _calc_theme_score(self, stock):
        """题材强度得分"""
        six_dim = stock.get('six_dim_score', {})
        industry = six_dim.get('industry_score', 8)
        policy = six_dim.get('policy_score', 10)
        # 行业15 + 政策20 = 35分，映射到100分
        combined = industry + policy
        return min(100, combined / 35 * 100)

    def _calc_technical_position_score(self, stock):
        """技术位置得分"""
        six_dim = stock.get('six_dim_score', {})
        technical = six_dim.get('technical_score', 12)
        sentiment = six_dim.get('sentiment_score', 8)
        # 技术25 + 情绪15 = 40分，映射到100分
        combined = technical + sentiment
        return min(100, combined / 40 * 100)

    def _calc_risk_reward_score(self, stock):
        """风险收益比得分"""
        risk_reward = stock.get('risk_reward', {})
        ratio = risk_reward.get('ratio', 1)
        # 3:1以上为满分
        return min(100, ratio / 3 * 100)
