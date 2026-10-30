# -*- coding: utf-8 -*-
"""
AI情绪分析模块
基于财经新闻标题的情绪分析，判断利好/利空，给出-1到1的情绪分数
"""
import re


class SentimentAnalyzer:
    """财经新闻情绪分析器"""

    def __init__(self):
        # 利好关键词（权重）
        self.bullish_keywords = {
            # 强利好
            '涨停': 0.8,
            '大涨': 0.7,
            '暴涨': 0.8,
            '创新高': 0.7,
            '突破': 0.6,
            '利好': 0.7,
            '业绩预增': 0.7,
            '大幅增长': 0.6,
            '盈利': 0.4,
            '增持': 0.5,
            '回购': 0.5,
            '超预期': 0.6,
            '翻倍': 0.7,
            '爆发': 0.6,
            '飙升': 0.7,
            '走强': 0.5,
            '上涨': 0.4,
            '增长': 0.3,
            '新高': 0.5,
            '受益': 0.4,
            '订单': 0.3,
            '中标': 0.4,
            '签约': 0.3,
            '合作': 0.2,
            '扩产': 0.4,
            '产能释放': 0.4,
            '政策支持': 0.5,
            '降息': 0.5,
            '降准': 0.5,
            '宽松': 0.4,
            '刺激': 0.4,
            '复苏': 0.5,
            '回暖': 0.4,
            '改善': 0.3,
            '向好': 0.3,
            '乐观': 0.4,
            '看多': 0.5,
            '买入': 0.5,
            '推荐': 0.3,
            '上调': 0.4,
            '评级': 0.2,
            '目标价': 0.2,
            '资金流入': 0.5,
            '主力净流入': 0.6,
            '抄底': 0.4,
            '反弹': 0.4,
            '反转': 0.5,
            '拐点': 0.5,
            '启动': 0.4,
            '拉升': 0.5,
            '封板': 0.6,
            '连板': 0.6,
            '龙头': 0.3,
            '风口': 0.4,
            '赛道': 0.2,
            '景气': 0.4,
            '高景气': 0.5,
        }

        # 利空关键词（权重）
        self.bearish_keywords = {
            # 强利空
            '跌停': -0.8,
            '大跌': -0.7,
            '暴跌': -0.8,
            '创新低': -0.7,
            '利空': -0.7,
            '业绩预减': -0.7,
            '大幅下滑': -0.6,
            '亏损': -0.5,
            '减持': -0.5,
            '爆雷': -0.8,
            '退市': -0.9,
            '风险': -0.4,
            '下跌': -0.4,
            '下滑': -0.3,
            '下降': -0.3,
            '减少': -0.2,
            '低于预期': -0.6,
            '不及预期': -0.6,
            '腰斩': -0.7,
            '崩盘': -0.8,
            '走弱': -0.5,
            '下跌': -0.4,
            '新低': -0.5,
            '受损': -0.4,
            '违约': -0.7,
            '逾期': -0.5,
            '债务': -0.3,
            '诉讼': -0.5,
            '处罚': -0.5,
            '立案': -0.6,
            '调查': -0.5,
            '减持': -0.5,
            '抛售': -0.6,
            '出逃': -0.6,
            '资金流出': -0.5,
            '主力净流出': -0.6,
            '跳水': -0.6,
            '崩': -0.7,
            '跌': -0.3,
            '降': -0.2,
            '减': -0.2,
            '缩量': -0.2,
            '低迷': -0.4,
            '疲软': -0.4,
            '衰退': -0.5,
            '下行': -0.4,
            '承压': -0.3,
            '看空': -0.5,
            '卖出': -0.5,
            '下调': -0.4,
            '降级': -0.5,
            '利空出尽': 0.3,  # 利空出尽是利好
            '靴子落地': 0.2,
        }

        # 否定词（会反转情绪）
        self.negation_words = ['不', '未', '无', '没', '非', '难', '避免', '防止', '减少']

        # 程度副词（会加强或减弱情绪）
        self.intensifiers = {
            '大幅': 1.5,
            '显著': 1.5,
            '明显': 1.3,
            '略微': 0.7,
            '小幅': 0.7,
            '轻微': 0.6,
            '严重': 1.5,
            '重大': 1.5,
            '超级': 1.8,
            '极度': 1.8,
            '非常': 1.5,
            '十分': 1.3,
            '比较': 0.8,
        }

    def analyze(self, text):
        """
        分析文本情绪
        Args:
            text: 新闻标题或内容
        Returns:
            dict: {
                'score': float,  # -1到1的情绪分数，正数利好，负数利空
                'sentiment': str,  # '利好'、'中性'、'利空'
                'bullish_words': list,  # 匹配到的利好关键词
                'bearish_words': list,  # 匹配到的利空关键词
                'confidence': float,  # 置信度0-1
            }
        """
        if not text:
            return {
                'score': 0,
                'sentiment': '中性',
                'bullish_words': [],
                'bearish_words': [],
                'confidence': 0
            }

        bullish_matches = []
        bearish_matches = []
        total_score = 0
        match_count = 0

        # 匹配利好关键词
        for keyword, weight in self.bullish_keywords.items():
            if keyword in text:
                # 检查前面是否有否定词
                negated = self._is_negated(text, keyword)
                if negated:
                    bearish_matches.append(keyword)
                    total_score += -weight * 0.8  # 否定后权重稍弱
                else:
                    bullish_matches.append(keyword)
                    total_score += weight
                match_count += 1

        # 匹配利空关键词
        for keyword, weight in self.bearish_keywords.items():
            if keyword in text:
                # 检查前面是否有否定词
                negated = self._is_negated(text, keyword)
                if negated:
                    bullish_matches.append(keyword)
                    total_score += -weight * 0.8  # 否定后权重稍弱
                else:
                    bearish_matches.append(keyword)
                    total_score += weight
                match_count += 1

        # 归一化到-1到1
        if match_count > 0:
            # 基础分数
            score = total_score / (match_count * 0.8)  # 平均权重，稍微放大
            # 限制在-1到1
            score = max(-1, min(1, score))
            # 置信度：匹配关键词越多，置信度越高
            confidence = min(1, match_count * 0.2 + 0.3)
        else:
            score = 0
            confidence = 0.1

        # 判断情绪标签
        if score > 0.2:
            sentiment = '利好'
        elif score < -0.2:
            sentiment = '利空'
        else:
            sentiment = '中性'

        return {
            'score': round(score, 3),
            'sentiment': sentiment,
            'bullish_words': bullish_matches,
            'bearish_words': bearish_matches,
            'confidence': round(confidence, 2)
        }

    def _is_negated(self, text, keyword):
        """检查关键词前面是否有否定词"""
        try:
            idx = text.index(keyword)
            # 检查前面10个字符内是否有否定词
            prefix = text[max(0, idx - 10):idx]
            for neg in self.negation_words:
                if neg in prefix:
                    return True
            return False
        except ValueError:
            return False

    def analyze_news_list(self, news_list):
        """
        分析新闻列表的整体情绪
        Args:
            news_list: 新闻列表，每个元素是dict，包含title等字段
        Returns:
            dict: {
                'overall_score': float,  # 整体情绪分数-1到1
                'overall_sentiment': str,  # 整体情绪
                'bullish_count': int,  # 利好新闻数量
                'bearish_count': int,  # 利空新闻数量
                'neutral_count': int,  # 中性新闻数量
                'analyzed_news': list,  # 分析后的新闻列表
            }
        """
        if not news_list:
            return {
                'overall_score': 0,
                'overall_sentiment': '中性',
                'bullish_count': 0,
                'bearish_count': 0,
                'neutral_count': 0,
                'analyzed_news': []
            }

        analyzed = []
        total_score = 0
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0

        for news in news_list:
            title = news.get('title', '') or news.get('content', '')[:50]
            result = self.analyze(title)
            news_with_sentiment = dict(news)
            news_with_sentiment['sentiment_score'] = result['score']
            news_with_sentiment['sentiment'] = result['sentiment']
            news_with_sentiment['bullish_words'] = result['bullish_words']
            news_with_sentiment['bearish_words'] = result['bearish_words']
            analyzed.append(news_with_sentiment)

            total_score += result['score'] * result['confidence']
            if result['score'] > 0.2:
                bullish_count += 1
            elif result['score'] < -0.2:
                bearish_count += 1
            else:
                neutral_count += 1

        # 计算整体情绪（加权平均）
        n = len(news_list)
        if n > 0:
            overall_score = total_score / n
            overall_score = max(-1, min(1, overall_score))
        else:
            overall_score = 0

        # 整体情绪标签
        if overall_score > 0.15:
            overall_sentiment = '偏多'
        elif overall_score > 0.05:
            overall_sentiment = '中性偏多'
        elif overall_score < -0.15:
            overall_sentiment = '偏空'
        elif overall_score < -0.05:
            overall_sentiment = '中性偏空'
        else:
            overall_sentiment = '中性'

        return {
            'overall_score': round(overall_score, 3),
            'overall_sentiment': overall_sentiment,
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'neutral_count': neutral_count,
            'analyzed_news': analyzed
        }


# 单例
_analyzer = None


def get_sentiment_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer
