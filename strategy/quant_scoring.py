"""
量化评分系统 - 总分100分
"""
from config.settings import SCORING_CONFIG
from utils.indicators import (
    calc_ma, calc_macd, calc_kdj, calc_volume_ratio,
    calc_high_price, calc_limit_up_count, is_ma_bullish,
    is_macd_red_expanding, is_kdj_golden_cross_low,
    calc_ma_series
)
import pandas as pd


class QuantScorer:
    """量化评分器"""

    def __init__(self):
        self.config = SCORING_CONFIG

    def score_stock(self, daily_data, realtime_data=None):
        """
        对单只股票进行量化评分
        返回: 评分详情dict
        """
        if not daily_data or len(daily_data) < 30:
            return None

        close_prices = [d['close'] for d in daily_data]
        high_prices = [d['high'] for d in daily_data]
        low_prices = [d['low'] for d in daily_data]
        volumes = [d['volume'] for d in daily_data]
        pct_changes = [d.get('pct_chg', 0) for d in daily_data]

        current_price = close_prices[-1]

        # 1. 趋势位置 (30分)
        trend_score = self._score_trend_position(close_prices, high_prices)

        # 2. 涨停基因 (20分)
        limit_up_score = self._score_limit_up_gene(close_prices, pct_changes)

        # 3. 成交量 (15分)
        volume_score = self._score_volume(volumes)

        # 4. 均线趋势 (15分)
        ma_score, ma5, ma10, ma20 = self._score_ma_trend(close_prices)

        # 5. MACD (10分)
        macd_score, macd_info = self._score_macd(close_prices)

        # 6. KDJ (10分)
        kdj_score, kdj_info = self._score_kdj(high_prices, low_prices, close_prices)

        # 总分
        total_score = trend_score + limit_up_score + volume_score + ma_score + macd_score + kdj_score

        # 评级
        if total_score >= 90:
            level = 'A'
            status = '主升启动'
            color = 'green'
        elif total_score >= 80:
            level = 'B'
            status = '重点关注'
            color = 'yellow'
        elif total_score >= 70:
            level = 'C'
            status = '观察'
            color = 'orange'
        else:
            level = 'D'
            status = '放弃'
            color = 'red'

        return {
            'total_score': round(total_score, 1),
            'level': level,
            'status': status,
            'color': color,
            'trend_score': round(trend_score, 1),
            'limit_up_score': round(limit_up_score, 1),
            'volume_score': round(volume_score, 1),
            'ma_score': round(ma_score, 1),
            'macd_score': round(macd_score, 1),
            'kdj_score': round(kdj_score, 1),
            'current_price': current_price,
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'macd_info': macd_info,
            'kdj_info': kdj_info,
        }

    def _score_trend_position(self, close_prices, high_prices):
        """趋势位置评分 30分"""
        max_score = self.config.get('trend_position', 30)
        current_price = close_prices[-1]

        # 近8个月最高价
        high_8m = calc_high_price(high_prices, days=168)
        if high_8m == 0:
            return 0

        # 距离高点越近得分越高
        ratio = current_price / high_8m
        # ratio = 0.7 -> 0分, ratio = 1.0 -> 30分, ratio > 1.0 (创新高) -> 满分
        if ratio >= 1.0:
            return max_score
        elif ratio >= 0.7:
            return max_score * (ratio - 0.7) / 0.3
        else:
            return 0

    def _score_limit_up_gene(self, close_prices, pct_changes):
        """涨停基因评分 20分"""
        max_score = self.config.get('limit_up_gene', 20)
        count = calc_limit_up_count(close_prices, pct_changes, days=252)

        # 3次 -> 10分, 5次 -> 15分, 8次以上 -> 20分
        if count >= 8:
            return max_score
        elif count >= 5:
            return max_score * 0.75
        elif count >= 3:
            return max_score * 0.5
        else:
            return 0

    def _score_volume(self, volumes):
        """成交量评分 15分"""
        max_score = self.config.get('volume_ratio', 15)
        vol_ratio = calc_volume_ratio(volumes, period=5)

        # 量比1.2 -> 10分, 1.5 -> 12分, 2.0以上 -> 15分
        if vol_ratio >= 2.0:
            return max_score
        elif vol_ratio >= 1.5:
            return max_score * 0.8
        elif vol_ratio >= 1.2:
            return max_score * 0.67
        elif vol_ratio >= 1.0:
            return max_score * 0.4
        else:
            return 0

    def _score_ma_trend(self, close_prices):
        """均线趋势评分 15分"""
        max_score = self.config.get('ma_trend', 15)
        ma5 = calc_ma(close_prices, 5)
        ma10 = calc_ma(close_prices, 10)
        ma20 = calc_ma(close_prices, 20)

        if ma5 is None or ma10 is None or ma20 is None:
            return 0, ma5, ma10, ma20

        score = 0
        # 多头排列 MA5 > MA10 > MA20
        if is_ma_bullish(ma5, ma10, ma20):
            score = max_score
        elif ma5 > ma10:
            score = max_score * 0.6
        elif ma10 > ma20:
            score = max_score * 0.3

        return score, ma5, ma10, ma20

    def _score_macd(self, close_prices):
        """MACD评分 10分"""
        max_score = self.config.get('macd', 10)
        dif, dea, macd_hist, hist_series = calc_macd(close_prices)

        info = {
            'dif': round(dif, 4),
            'dea': round(dea, 4),
            'macd_hist': round(macd_hist, 4),
        }

        # 红柱扩大 -> 10分
        if is_macd_red_expanding(hist_series):
            return max_score, info
        # 红柱但缩小 -> 6分
        elif macd_hist > 0:
            return max_score * 0.6, info
        # 绿柱缩小 -> 4分
        elif macd_hist < 0 and len(hist_series) >= 2:
            prev_hist = hist_series.iloc[-2]
            if abs(macd_hist) < abs(prev_hist):
                return max_score * 0.4, info
        # 绿柱扩大 -> 0分
        return 0, info

    def _score_kdj(self, high_prices, low_prices, close_prices):
        """KDJ评分 10分"""
        max_score = self.config.get('kdj', 10)
        k, d, j = calc_kdj(high_prices, low_prices, close_prices, n=13, m1=3, m2=3)

        info = {
            'k': round(k, 2),
            'd': round(d, 2),
            'j': round(j, 2),
        }

        # 计算KDJ序列判断金叉
        k_series = []
        d_series = []
        # 简化: 用最后几天的值近似
        for i in range(max(1, len(close_prices) - 20), len(close_prices) + 1):
            h = high_prices[:i]
            l = low_prices[:i]
            c = close_prices[:i]
            if len(h) >= 13:
                ki, di, ji = calc_kdj(h, l, c, n=13, m1=3, m2=3)
                k_series.append(ki)
                d_series.append(di)

        k_series = pd.Series(k_series)
        d_series = pd.Series(d_series)

        # 低位金叉 K<50 -> 10分
        if is_kdj_golden_cross_low(k_series, d_series, k_threshold=50):
            return max_score, info
        # K<30 超卖区 -> 8分
        elif k < 30:
            return max_score * 0.8, info
        # K<50 多头区 -> 5分
        elif k < 50:
            return max_score * 0.5, info
        # K>80 超买区 -> 2分
        elif k > 80:
            return max_score * 0.2, info
        # 其他
        else:
            return max_score * 0.3, info

    def score_stock_list(self, stock_data_list):
        """
        批量评分
        stock_data_list: [{'ts_code', 'name', 'daily_data'}, ...]
        返回: 按总分降序排列的评分列表
        """
        results = []
        for stock in stock_data_list:
            score_info = self.score_stock(stock.get('daily_data', []))
            if score_info:
                result = {
                    'ts_code': stock['ts_code'],
                    'name': stock['name'],
                    'industry': stock.get('industry', ''),
                }
                result.update(score_info)
                results.append(result)

        # 按总分降序
        results.sort(key=lambda x: x['total_score'], reverse=True)
        return results
