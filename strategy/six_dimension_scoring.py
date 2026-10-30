"""
AI股票六维评分系统
评分120分：
1. 市场环境 20分
2. 政策消息 20分
3. 行业强度 15分
4. 主力资金 25分
5. 技术形态 25分
6. AI情绪 15分
"""
from datetime import datetime
import numpy as np


class SixDimensionScorer:
    """AI股票六维评分系统"""

    # 评分维度
    DIMENSIONS = [
        ('market', '市场环境', 20),
        ('policy', '政策消息', 20),
        ('industry', '行业强度', 15),
        ('fund', '主力资金', 25),
        ('technical', '技术形态', 25),
        ('sentiment', 'AI情绪', 15),
    ]

    # 评级
    RATINGS = [
        (100, '强烈推荐', '#f85149'),
        (85, '重点关注', '#d29922'),
        (70, '值得关注', '#e3b341'),
        (55, '等待确认', '#58a6ff'),
        (0, '暂不关注', '#8b949e'),
    ]

    def __init__(self):
        pass

    def score(self, stock_data, daily_data, stock_info=None, market_state=None, news_list=None):
        """
        六维评分

        Args:
            stock_data: 股票基本数据
            daily_data: 日线数据
            stock_info: 股票信息（换手率、市值、PE等）
            market_state: 市场状态结果
            news_list: 相关新闻列表

        Returns:
            dict: 评分结果
        """
        if stock_info is None:
            stock_info = {}
        if news_list is None:
            news_list = []

        # 各维度评分
        market_score = self._score_market(market_state)
        policy_score = self._score_policy(news_list, stock_info)
        industry_score = self._score_industry(stock_info)
        fund_score = self._score_fund(daily_data, stock_info)
        technical_score = self._score_technical(daily_data)
        sentiment_score = self._score_sentiment(daily_data, stock_info)

        # 总分
        total_score = (
            market_score + policy_score + industry_score +
            fund_score + technical_score + sentiment_score
        )

        # 评级
        rating, rating_color = self._get_rating(total_score)

        # 各维度详情
        dimensions = {
            'market': {'score': market_score, 'max': 20, 'name': '市场环境'},
            'policy': {'score': policy_score, 'max': 20, 'name': '政策消息'},
            'industry': {'score': industry_score, 'max': 15, 'name': '行业强度'},
            'fund': {'score': fund_score, 'max': 25, 'name': '主力资金'},
            'technical': {'score': technical_score, 'max': 25, 'name': '技术形态'},
            'sentiment': {'score': sentiment_score, 'max': 15, 'name': 'AI情绪'},
        }

        # 优势和劣势
        strengths, weaknesses = self._analyze_strengths_weaknesses(dimensions)

        return {
            'total_score': total_score,
            'max_score': 120,
            'rating': rating,
            'rating_color': rating_color,
            'dimensions': dimensions,
            'market_score': market_score,
            'policy_score': policy_score,
            'industry_score': industry_score,
            'fund_score': fund_score,
            'technical_score': technical_score,
            'sentiment_score': sentiment_score,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'score_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _score_market(self, market_state):
        """市场环境评分（20分）"""
        if market_state is None:
            return 10  # 默认中性

        score = market_state.get('total_score', 50)
        # 将0-100映射到0-20
        return int(score / 100 * 20)

    def _score_policy(self, news_list, stock_info):
        """政策消息评分（20分）"""
        score = 10  # 默认中性

        if not news_list:
            return score

        positive_keywords = [
            '利好', '政策支持', '补贴', '减税', '扶持', '规划',
            '增长', '突破', '创新', '订单', '中标', '合作',
            '增持', '回购', '业绩预增', '超预期',
        ]
        negative_keywords = [
            '利空', '监管', '处罚', '减持', '退市', '风险',
            '下滑', '亏损', '调查', '诉讼', '违规', '警示',
        ]

        positive_count = 0
        negative_count = 0

        for news in news_list:
            title = news.get('title', '') + news.get('content', '')
            for kw in positive_keywords:
                if kw in title:
                    positive_count += 1
                    break
            for kw in negative_keywords:
                if kw in title:
                    negative_count += 1
                    break

        if positive_count > 0:
            score += min(10, positive_count * 3)
        if negative_count > 0:
            score -= min(10, negative_count * 3)

        return max(0, min(20, score))

    def _score_industry(self, stock_info):
        """行业强度评分（15分）"""
        score = 8  # 默认中性

        industry = stock_info.get('industry', '')
        sector_strong = stock_info.get('sector_strong', False)
        sector_rank = stock_info.get('sector_rank', 99)

        # 行业是否强势
        if sector_strong:
            score += 5
        if sector_rank <= 5:
            score += 5
        elif sector_rank <= 15:
            score += 3

        # 热门行业加分
        hot_industries = [
            '人工智能', '半导体', '新能源', '光伏', '储能',
            '军工', '医药', '消费电子', '机器人', '算力',
        ]
        if any(h in industry for h in hot_industries):
            score += 3

        return max(0, min(15, score))

    def _score_fund(self, daily_data, stock_info):
        """主力资金评分（25分）"""
        score = 12  # 默认中性

        if len(daily_data) < 10:
            return score

        volumes = [d.get('volume', 0) for d in daily_data]
        closes = [d.get('close', 0) for d in daily_data]

        # 1. 大单/资金流入（用量价判断）
        vol_5 = np.mean(volumes[-5:])
        vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else vol_5
        if vol_20 > 0:
            vol_ratio = vol_5 / vol_20
            if vol_ratio > 1.5 and closes[-1] > closes[-5]:
                score += 8  # 放量上涨，资金流入
            elif vol_ratio > 1.2 and closes[-1] > closes[-5]:
                score += 4
            elif vol_ratio > 1.5 and closes[-1] < closes[-5]:
                score -= 5  # 放量下跌，资金流出

        # 2. 资金持续性
        if len(closes) >= 6:
            up_days = sum(1 for i in range(-5, 0) if closes[i] > closes[i-1])
            if up_days >= 4:
                score += 5  # 持续上涨，资金持续流入
            elif up_days <= 1:
                score -= 3

        # 3. 换手率
        turnover = stock_info.get('turnover_rate', 0)
        if 5 <= turnover <= 15:
            score += 4  # 健康换手
        elif turnover > 20:
            score -= 2  # 换手过高
        elif turnover < 2:
            score -= 2  # 交投清淡

        # 4. 龙虎榜（简化：用涨幅和量能判断）
        if len(closes) >= 2 and closes[-2] > 0:
            change = (closes[-1] - closes[-2]) / closes[-2] * 100
            if change > 7 and vol_5 > vol_20 * 1.5:
                score += 3  # 可能上龙虎榜

        return max(0, min(25, score))

    def _score_technical(self, daily_data):
        """技术形态评分（25分）"""
        score = 12  # 默认中性

        if len(daily_data) < 20:
            return score

        closes = [d.get('close', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]

        # 1. KDJ（简化）
        if len(closes) >= 9:
            recent_closes = closes[-9:]
            low_9 = min(lows[-9:])
            high_9 = max(highs[-9:])
            if high_9 > low_9:
                rsv = (closes[-1] - low_9) / (high_9 - low_9) * 100
                if 20 <= rsv <= 80:
                    score += 4  # KDJ健康
                elif rsv < 20:
                    score += 3  # 超卖，可能反弹
                elif rsv > 90:
                    score -= 3  # 超买

        # 2. MACD（简化用价格动量）
        if len(closes) >= 12:
            ma12 = np.mean(closes[-12:])
            ma26 = np.mean(closes[-26:]) if len(closes) >= 26 else np.mean(closes)
            diff = ma12 - ma26
            if diff > 0:
                score += 5  # MACD金叉/红柱
                if closes[-1] > closes[-5]:
                    score += 2  # 红柱扩大
            else:
                score -= 3

        # 3. 均线
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            score += 5  # 多头排列
        elif ma5 > ma10:
            score += 2
        elif ma5 < ma10 < ma20:
            score -= 4  # 空头排列

        # 4. 量价配合
        volumes = [d.get('volume', 0) for d in daily_data]
        if len(closes) >= 2 and len(volumes) >= 2:
            if closes[-1] > closes[-2] and volumes[-1] > volumes[-2]:
                score += 3  # 放量上涨
            elif closes[-1] < closes[-2] and volumes[-1] < volumes[-2]:
                score += 1  # 缩量下跌，健康调整

        return max(0, min(25, score))

    def _score_sentiment(self, daily_data, stock_info):
        """AI情绪评分（15分）"""
        score = 8  # 默认中性

        if len(daily_data) < 10:
            return score

        closes = [d.get('close', 0) for d in daily_data]

        # 1. 市场情绪（用近期涨幅判断）
        if len(closes) >= 6:
            change_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
            if 5 <= change_5d <= 15:
                score += 4  # 温和上涨，情绪健康
            elif change_5d > 20:
                score -= 2  # 涨幅过大，情绪过热
            elif change_5d < -10:
                score += 2  # 超跌，情绪修复

        # 2. 涨停基因
        limit_up_count = 0
        for i in range(1, min(20, len(closes))):
            if closes[i-1] > 0 and (closes[i] - closes[i-1]) / closes[i-1] >= 0.095:
                limit_up_count += 1
        if limit_up_count >= 2:
            score += 4  # 股性活跃
        elif limit_up_count >= 1:
            score += 2

        # 3. 连板情况
        consecutive_up = 0
        for i in range(-1, -min(5, len(closes)), -1):
            if closes[i] > closes[i-1]:
                consecutive_up += 1
            else:
                break
        if consecutive_up >= 3:
            score -= 2  # 连板过多，追高风险
        elif consecutive_up == 2:
            score += 2  # 二板，情绪好

        return max(0, min(15, score))

    def _get_rating(self, total_score):
        """获取评级"""
        for threshold, rating, color in self.RATINGS:
            if total_score >= threshold:
                return rating, color
        return '暂不关注', '#8b949e'

    def _analyze_strengths_weaknesses(self, dimensions):
        """分析优势和劣势"""
        strengths = []
        weaknesses = []

        for key, dim in dimensions.items():
            ratio = dim['score'] / dim['max'] if dim['max'] > 0 else 0
            if ratio >= 0.7:
                strengths.append(f"{dim['name']}强({dim['score']}/{dim['max']})")
            elif ratio <= 0.3:
                weaknesses.append(f"{dim['name']}弱({dim['score']}/{dim['max']})")

        return strengths, weaknesses
