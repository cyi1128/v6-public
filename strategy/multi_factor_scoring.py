"""
AI多因子决策模型（100分）
由5个维度组成：
1. 市场环境评分（20分）
2. 消息面AI评分（20分）
3. 技术指标评分（25分）
4. 资金强度评分（20分）
5. 市场情绪AI评分（15分）
"""
from datetime import datetime
import numpy as np
import requests


class MultiFactorScorer:
    """AI多因子决策模型"""

    # 评级
    RATING_STRONG_BUY = '强烈买入'
    RATING_BUY = '买入'
    RATING_WATCH = '观望'
    RATING_AVOID = '回避'

    RATING_COLORS = {
        RATING_STRONG_BUY: '#ff1744',  # 红色
        RATING_BUY: '#00e676',         # 绿色
        RATING_WATCH: '#ffea00',       # 黄色
        RATING_AVOID: '#757575',       # 灰色
    }

    def __init__(self):
        pass

    def score(self, stock_data, daily_data, stock_info=None, news_list=None, market_data=None):
        """
        综合评分

        Args:
            stock_data: 股票数据
            daily_data: 日线数据
            stock_info: 股票信息
            news_list: 消息列表
            market_data: 市场数据

        Returns:
            dict: 评分结果
        """
        if stock_info is None:
            stock_info = {}
        if news_list is None:
            news_list = []
        if market_data is None:
            market_data = self._get_market_data()

        # 各维度评分
        market_score, market_detail = self._score_market(market_data)
        news_score, news_detail = self._score_news(news_list)
        tech_score, tech_detail = self._score_technical(daily_data, stock_data)
        fund_score, fund_detail = self._score_fund(daily_data, stock_info)
        sentiment_score, sentiment_detail = self._score_sentiment(market_data, news_list)

        total = market_score + news_score + tech_score + fund_score + sentiment_score

        # 评级
        if total >= 80:
            rating = self.RATING_STRONG_BUY
        elif total >= 65:
            rating = self.RATING_BUY
        elif total >= 50:
            rating = self.RATING_WATCH
        else:
            rating = self.RATING_AVOID

        # 操作建议
        suggestion = self._generate_suggestion(total, rating, tech_detail, fund_detail)

        return {
            'total_score': total,
            'rating': rating,
            'rating_color': self.RATING_COLORS[rating],
            'suggestion': suggestion,
            'dimensions': {
                'market': {'score': market_score, 'max': 20, 'detail': market_detail},
                'news': {'score': news_score, 'max': 20, 'detail': news_detail},
                'technical': {'score': tech_score, 'max': 25, 'detail': tech_detail},
                'fund': {'score': fund_score, 'max': 20, 'detail': fund_detail},
                'sentiment': {'score': sentiment_score, 'max': 15, 'detail': sentiment_detail},
            },
            'score_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def _get_market_data(self):
        """获取市场数据"""
        market_data = {
            'sh_trend': '震荡',
            'sz_trend': '震荡',
            'cy_trend': '震荡',
            'amount': 8000,
            'up_count': 2000,
            'down_count': 2500,
            'limit_up': 30,
            'limit_down': 10,
            'profit_effect': 0.5,
        }

        try:
            # 上证指数
            url = 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')

            lines = text.strip().split(';')
            for i, line in enumerate(lines[:3]):
                if '~' in line:
                    parts = line.split('"')[1].split('~')
                    if len(parts) > 32:
                        change_pct = float(parts[32])
                        trend = '上涨' if change_pct > 0.5 else ('下跌' if change_pct < -0.5 else '震荡')
                        if i == 0:
                            market_data['sh_trend'] = trend
                        elif i == 1:
                            market_data['sz_trend'] = trend
                        else:
                            market_data['cy_trend'] = trend
        except Exception:
            pass

        return market_data

    def _score_market(self, market_data):
        """市场环境评分（20分）"""
        score = 0
        details = []

        # 指数趋势（8分）
        trends = [market_data.get('sh_trend', ''), market_data.get('sz_trend', ''), market_data.get('cy_trend', '')]
        up_count = sum(1 for t in trends if t == '上涨')
        down_count = sum(1 for t in trends if t == '下跌')

        if up_count >= 2:
            score += 8
            details.append('指数强势(8分)')
        elif up_count == 1:
            score += 5
            details.append('指数分化(5分)')
        elif down_count >= 2:
            score += 2
            details.append('指数弱势(2分)')
        else:
            score += 4
            details.append('指数震荡(4分)')

        # 成交额（4分）
        amount = market_data.get('amount', 0)
        if amount > 12000:
            score += 4
            details.append('成交活跃(4分)')
        elif amount > 8000:
            score += 3
            details.append('成交正常(3分)')
        elif amount > 5000:
            score += 2
            details.append('成交萎缩(2分)')
        else:
            score += 1
            details.append('成交低迷(1分)')

        # 涨跌家数（4分）
        up = market_data.get('up_count', 0)
        down = market_data.get('down_count', 0)
        total = up + down
        if total > 0:
            ratio = up / total
            if ratio > 0.6:
                score += 4
                details.append('涨多跌少(4分)')
            elif ratio > 0.45:
                score += 2
                details.append('涨跌均衡(2分)')
            else:
                score += 1
                details.append('跌多涨少(1分)')

        # 涨跌停（4分）
        limit_up = market_data.get('limit_up', 0)
        limit_down = market_data.get('limit_down', 0)
        if limit_up > 50 and limit_down < 10:
            score += 4
            details.append('涨停潮(4分)')
        elif limit_up > limit_down * 2:
            score += 3
            details.append('涨停占优(3分)')
        elif limit_down > limit_up:
            score += 1
            details.append('跌停偏多(1分)')
        else:
            score += 2
            details.append('涨跌停均衡(2分)')

        # 市场状态
        if score >= 15:
            state = '强势-适合进攻'
        elif score >= 10:
            state = '震荡-精选个股'
        else:
            state = '弱势-降低仓位'

        return score, {'state': state, 'details': details}

    def _score_news(self, news_list):
        """消息面AI评分（20分）"""
        score = 10  # 基础分
        details = []

        if not news_list:
            return score, {'level': '中性', 'details': ['无相关消息']}

        positive_count = 0
        negative_count = 0
        major_positive = False
        major_negative = False

        for news in news_list:
            level = news.get('level', '中性')
            if level == '重大利好':
                major_positive = True
                positive_count += 3
            elif level == '普通利好':
                positive_count += 1
            elif level == '风险提示':
                negative_count += 1
            elif level == '重大利空':
                major_negative = True
                negative_count += 3

        if major_positive:
            score += 8
            details.append('重大利好(+8)')
        if major_negative:
            score -= 8
            details.append('重大利空(-8)')

        score += min(positive_count, 5)
        score -= min(negative_count, 5)

        score = max(0, min(20, score))

        if score >= 15:
            level = '★★★★★ 强烈利好'
        elif score >= 12:
            level = '★★★★ 偏利好'
        elif score >= 8:
            level = '★★★ 中性'
        elif score >= 5:
            level = '★★ 偏空'
        else:
            level = '★ 利空'

        return score, {'level': level, 'details': details, 'positive': positive_count, 'negative': negative_count}

    def _score_technical(self, daily_data, stock_data):
        """技术指标评分（25分）"""
        if len(daily_data) < 30:
            return 12, {'kdj': '数据不足', 'macd': '数据不足', 'ma': '数据不足'}

        score = 0
        details = {}

        closes = [d.get('close', 0) for d in daily_data]
        highs = [d.get('high', 0) for d in daily_data]
        lows = [d.get('low', 0) for d in daily_data]

        current_price = stock_data.get('price', closes[-1])

        # KDJ评分（8分）
        kdj = self._calc_kdj(closes, highs, lows, n=13)
        k_score = 0
        if 20 <= kdj['k'] <= 60 and kdj['k'] > kdj['d']:
            k_score = 8
            details['kdj'] = '低位金叉(8分)'
        elif kdj['k'] > kdj['d'] and kdj['k'] < 80:
            k_score = 5
            details['kdj'] = '金叉(5分)'
        elif kdj['k'] > 80 and kdj['k'] < kdj['d']:
            k_score = 1
            details['kdj'] = '高位死叉(1分)'
        else:
            k_score = 3
            details['kdj'] = '中性(3分)'
        score += k_score

        # MACD评分（8分）
        macd = self._calc_macd(closes)
        m_score = 0
        if macd['golden_cross'] and macd['above_zero']:
            m_score = 8
            details['macd'] = '0轴上方金叉(8分)'
        elif macd['golden_cross']:
            m_score = 5
            details['macd'] = '金叉(5分)'
        elif macd['red_expanding']:
            m_score = 6
            details['macd'] = '红柱扩大(6分)'
        elif macd['death_cross']:
            m_score = 2
            details['macd'] = '死叉(2分)'
        elif macd['red_shrinking']:
            m_score = 3
            details['macd'] = '红柱缩短(3分)'
        else:
            m_score = 4
            details['macd'] = '中性(4分)'
        score += m_score

        # 均线评分（9分）
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

        ma_score = 0
        if ma5 > ma10 > ma20 > ma60 and current_price > ma5:
            ma_score = 9
            details['ma'] = '多头排列(9分)'
        elif ma5 > ma10 > ma20:
            ma_score = 6
            details['ma'] = '短期多头(6分)'
        elif ma5 > ma10:
            ma_score = 4
            details['ma'] = '5日线上穿(4分)'
        elif ma5 < ma10 < ma20:
            ma_score = 1
            details['ma'] = '空头排列(1分)'
        else:
            ma_score = 3
            details['ma'] = '震荡(3分)'
        score += ma_score

        return score, details

    def _score_fund(self, daily_data, stock_info):
        """资金强度评分（20分）"""
        if len(daily_data) < 20:
            return 10, {'volume': '数据不足', 'turnover': '数据不足'}

        score = 0
        details = {}

        volumes = [d.get('volume', 0) for d in daily_data]
        closes = [d.get('close', 0) for d in daily_data]

        # 成交量/量比（6分）
        vol_5 = np.mean(volumes[-5:])
        vol_20 = np.mean(volumes[-20:])
        if vol_20 > 0:
            volume_ratio = vol_5 / vol_20
            if volume_ratio > 2:
                score += 6
                details['volume'] = f'放量(量比{volume_ratio:.1f})(6分)'
            elif volume_ratio > 1.3:
                score += 4
                details['volume'] = f'温和放量(量比{volume_ratio:.1f})(4分)'
            elif volume_ratio > 0.7:
                score += 3
                details['volume'] = '量能平稳(3分)'
            else:
                score += 1
                details['volume'] = '缩量(1分)'

        # 换手率（6分）
        turnover = stock_info.get('turnover_rate', 0)
        if 5 <= turnover <= 15:
            score += 6
            details['turnover'] = f'健康换手({turnover:.1f}%)(6分)'
        elif 3 <= turnover < 5 or 15 < turnover <= 25:
            score += 4
            details['turnover'] = f'换手正常({turnover:.1f}%)(4分)'
        elif turnover > 25:
            score += 2
            details['turnover'] = f'高换手({turnover:.1f}%)(2分)'
        else:
            score += 2
            details['turnover'] = f'低换手({turnover:.1f}%)(2分)'

        # 主力资金流向（8分）
        up_volume = sum(volumes[-i] for i in range(1, 11) if closes[-i] > closes[-i-1])
        down_volume = sum(volumes[-i] for i in range(1, 11) if closes[-i] < closes[-i-1])
        total = up_volume + down_volume

        if total > 0:
            fund_ratio = up_volume / total
            if fund_ratio > 0.65:
                score += 8
                details['fund_flow'] = '主力大幅流入(8分)'
                details['stage'] = '主力启动'
                details['stage_color'] = '#ff1744'
            elif fund_ratio > 0.55:
                score += 6
                details['fund_flow'] = '主力净流入(6分)'
                details['stage'] = '主力吸筹'
                details['stage_color'] = '#00e676'
            elif fund_ratio > 0.45:
                score += 4
                details['fund_flow'] = '资金博弈(4分)'
                details['stage'] = '观察'
                details['stage_color'] = '#ffea00'
            elif fund_ratio > 0.35:
                score += 2
                details['fund_flow'] = '主力净流出(2分)'
                details['stage'] = '主力出货'
                details['stage_color'] = '#ffea00'
            else:
                score += 1
                details['fund_flow'] = '主力大幅流出(1分)'
                details['stage'] = '风险'
                details['stage_color'] = '#757575'

        return score, details

    def _score_sentiment(self, market_data, news_list):
        """市场情绪AI评分（15分）"""
        score = 7  # 基础分
        details = []

        # 涨停情绪（5分）
        limit_up = market_data.get('limit_up', 0)
        if limit_up > 80:
            score += 5
            details.append('涨停潮-情绪高潮(5分)')
            sentiment = '高潮'
        elif limit_up > 40:
            score += 3
            details.append('涨停活跃-情绪修复(3分)')
            sentiment = '修复'
        elif limit_up > 20:
            score += 2
            details.append('涨停一般-情绪平稳(2分)')
            sentiment = '平稳'
        elif limit_up > 10:
            score += 1
            details.append('涨停稀少-情绪退潮(1分)')
            sentiment = '退潮'
        else:
            score += 0
            details.append('涨停冰点-情绪冰点(0分)')
            sentiment = '冰点'

        # 板块强度（5分）
        # 简化：用涨跌比代替
        up = market_data.get('up_count', 0)
        down = market_data.get('down_count', 0)
        total = up + down
        if total > 0:
            ratio = up / total
            if ratio > 0.65:
                score += 5
                details.append('板块普涨(5分)')
            elif ratio > 0.5:
                score += 3
                details.append('板块分化(3分)')
            else:
                score += 1
                details.append('板块普跌(1分)')

        # 消息热度（5分）
        if news_list:
            news_count = len(news_list)
            if news_count >= 10:
                score += 5
                details.append('消息热度高(5分)')
            elif news_count >= 5:
                score += 3
                details.append('消息热度中(3分)')
            else:
                score += 2
                details.append('消息热度低(2分)')
        else:
            score += 1
            details.append('无相关消息(1分)')

        score = max(0, min(15, score))

        return score, {'sentiment': sentiment, 'details': details}

    def _calc_kdj(self, closes, highs, lows, n=13):
        """计算KDJ(13,3,3)"""
        if len(closes) < n:
            return {'k': 50, 'd': 50, 'j': 50}

        low_n = min(lows[-n:])
        high_n = max(highs[-n:])

        if high_n == low_n:
            rsv = 50
        else:
            rsv = (closes[-1] - low_n) / (high_n - low_n) * 100

        k = rsv * (1/3) + 50 * (2/3)
        d = k * (1/3) + 50 * (2/3)
        j = 3 * k - 2 * d

        return {'k': k, 'd': d, 'j': j}

    def _calc_macd(self, closes):
        """计算MACD"""
        if len(closes) < 26:
            return {'golden_cross': False, 'death_cross': False, 'above_zero': False,
                    'red_expanding': False, 'red_shrinking': False}

        ema12 = self._ema(closes[-12:], 12)
        ema26 = self._ema(closes[-26:], 26)
        diff = ema12 - ema26

        ema12_prev = self._ema(closes[-13:-1], 12)
        ema26_prev = self._ema(closes[-27:-1], 26)
        diff_prev = ema12_prev - ema26_prev

        return {
            'golden_cross': diff_prev < 0 and diff > 0,
            'death_cross': diff_prev > 0 and diff < 0,
            'above_zero': diff > 0,
            'red_expanding': diff > 0 and diff > diff_prev,
            'red_shrinking': diff > 0 and diff < diff_prev,
            'diff': diff,
        }

    def _ema(self, data, period):
        """计算EMA"""
        if not data:
            return 0
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _generate_suggestion(self, total, rating, tech_detail, fund_detail):
        """生成操作建议"""
        if rating == self.RATING_STRONG_BUY:
            return f'强烈买入，建议仓位50%-70%。综合评分{total}分，技术面和资金面共振。'
        elif rating == self.RATING_BUY:
            return f'可以买入，建议仓位30%-50%。综合评分{total}分，可逢低介入。'
        elif rating == self.RATING_WATCH:
            return f'观望为主，等待确认信号。综合评分{total}分，需进一步观察。'
        else:
            return f'回避风险，不建议介入。综合评分{total}分，风险大于机会。'
