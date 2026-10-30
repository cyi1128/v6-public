"""
9:25集合竞价分析模块
竞价评分100分
"""
from config.settings import AUCTION_CONFIG


class AuctionAnalyzer:
    """集合竞价分析器"""

    def __init__(self):
        self.config = AUCTION_CONFIG

    def analyze_auction(self, auction_data):
        """
        分析单只股票的集合竞价数据
        返回: 评分详情
        """
        if not auction_data:
            return None

        total_score = 0
        details = {}

        # 1. 高开幅度 2%-5% (20分)
        gap_score = self._score_gap_up(auction_data.get('gap_up_pct', 0))
        total_score += gap_score
        details['gap_up_score'] = gap_score

        # 2. 竞价量比 (25分)
        vol_score = self._score_volume_ratio(auction_data.get('volume_ratio', 0))
        total_score += vol_score
        details['volume_ratio_score'] = vol_score

        # 3. 竞价成交金额 (20分)
        amount_score = self._score_turnover(auction_data.get('auction_amount', 0))
        total_score += amount_score
        details['turnover_score'] = amount_score

        # 4. 板块强度 (20分)
        sector_score = self._score_sector_strength(auction_data.get('sector_strength', 0))
        total_score += sector_score
        details['sector_strength_score'] = sector_score

        # 5. 昨日强势表现 (15分)
        yest_score = self._score_yesterday_strength(auction_data.get('yesterday_strength', 0))
        total_score += yest_score
        details['yesterday_strength_score'] = yest_score

        # 评级
        if total_score >= 80:
            level = '强'
        elif total_score >= 60:
            level = '中'
        else:
            level = '弱'

        result = {
            'ts_code': auction_data.get('ts_code', ''),
            'name': auction_data.get('name', ''),
            'auction_price': auction_data.get('auction_price', 0),
            'pre_close': auction_data.get('pre_close', 0),
            'gap_up_pct': auction_data.get('gap_up_pct', 0),
            'auction_volume': auction_data.get('auction_volume', 0),
            'auction_amount': auction_data.get('auction_amount', 0),
            'volume_ratio': auction_data.get('volume_ratio', 0),
            'total_score': round(total_score, 1),
            'level': level,
        }
        result.update(details)
        return result

    def _score_gap_up(self, gap_up_pct):
        """高开幅度评分 20分"""
        max_score = self.config.get('gap_up_score', 20)
        gap = gap_up_pct / 100  # 转成小数

        gap_min = self.config.get('gap_up_min', 0.02)
        gap_max = self.config.get('gap_up_max', 0.05)

        if gap_min <= gap <= gap_max:
            return max_score
        elif gap > gap_max:
            # 高开过多,适当减分
            if gap <= 0.07:
                return max_score * 0.7
            else:
                return max_score * 0.4
        elif gap > 0:
            # 高开但不足2%
            return max_score * (gap / gap_min) * 0.5
        else:
            # 低开
            return 0

    def _score_volume_ratio(self, volume_ratio):
        """竞价量比评分 25分"""
        max_score = self.config.get('volume_ratio_score', 25)

        if volume_ratio >= 5:
            return max_score
        elif volume_ratio >= 3:
            return max_score * 0.8
        elif volume_ratio >= 2:
            return max_score * 0.6
        elif volume_ratio >= 1:
            return max_score * 0.4
        else:
            return 0

    def _score_turnover(self, auction_amount):
        """竞价成交金额评分 20分"""
        max_score = self.config.get('turnover_score', 20)

        # 金额单位: 元
        amount_wan = auction_amount / 10000  # 转万元

        if amount_wan >= 5000:
            return max_score
        elif amount_wan >= 3000:
            return max_score * 0.8
        elif amount_wan >= 1000:
            return max_score * 0.6
        elif amount_wan >= 500:
            return max_score * 0.4
        else:
            return max_score * 0.2

    def _score_sector_strength(self, sector_strength):
        """板块强度评分 20分"""
        max_score = self.config.get('sector_strength_score', 20)
        return max_score * (sector_strength / 100)

    def _score_yesterday_strength(self, yesterday_strength):
        """昨日强势表现评分 15分"""
        max_score = self.config.get('yesterday_strength_score', 15)
        return max_score * (yesterday_strength / 100)

    def analyze_batch(self, auction_list):
        """
        批量分析集合竞价数据
        返回: 按总分降序排列的排行榜
        """
        results = []
        for auction_data in auction_list:
            result = self.analyze_auction(auction_data)
            if result:
                results.append(result)

        results.sort(key=lambda x: x['total_score'], reverse=True)
        return results

    def get_top_stocks(self, auction_list, top_n=20, min_score=60):
        """获取竞价排名靠前的股票"""
        results = self.analyze_batch(auction_list)
        return [r for r in results if r['total_score'] >= min_score][:top_n]
