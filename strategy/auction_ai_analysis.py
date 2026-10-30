"""
集合竞价AI分析模块
9:15-9:25集合竞价实时分析
评分100分：价格强度25 + 量能25 + 技术25 + 资金板块25
"""
import numpy as np
from datetime import datetime


class AuctionAIAnalyzer:
    """集合竞价AI分析器"""

    def __init__(self):
        self.auction_data = {}  # {ts_code: auction_info}
        self.scored_stocks = []  # 评分后的股票列表

    def analyze(self, ts_code, stock_name, auction_data, daily_data=None, triple_volume_info=None, sector_info=None):
        """
        分析单只股票的集合竞价
        参数：
            ts_code: 股票代码
            stock_name: 股票名称
            auction_data: 竞价数据 {price, pct_chg, volume, amount, match_volume, cancel_volume, prev_close}
            daily_data: 日线数据（用于技术分析）
            triple_volume_info: 三倍量信息 {has_tv, lifeline, pullback_confirmed}
            sector_info: 板块信息 {sector_name, sector_rank, fund_inflow, is_hot}
        返回：
            评分结果字典
        """
        result = {
            'ts_code': ts_code,
            'stock_name': stock_name,
            'auction_price': auction_data.get('price', 0),
            'auction_pct_chg': auction_data.get('pct_chg', 0),
            'auction_volume': auction_data.get('volume', 0),
            'auction_amount': auction_data.get('amount', 0),
            'match_volume': auction_data.get('match_volume', 0),
            'cancel_volume': auction_data.get('cancel_volume', 0),
            'prev_close': auction_data.get('prev_close', 0),
            'total_score': 0,
            'price_score': 0,
            'volume_score': 0,
            'tech_score': 0,
            'fund_score': 0,
            'rating': '',
            'suggestion': '',
            'risk_warning': '',
            'details': [],
            'analyze_time': datetime.now().strftime('%H:%M:%S'),
        }

        # 1. 价格强度评分（25分）
        price_score, price_details = self._score_price(auction_data)
        result['price_score'] = price_score
        result['details'].extend(price_details)

        # 2. 量能评分（25分）
        volume_score, vol_details = self._score_volume(auction_data)
        result['volume_score'] = volume_score
        result['details'].extend(vol_details)

        # 3. 技术评分（25分）
        tech_score, tech_details = self._score_tech(daily_data, triple_volume_info)
        result['tech_score'] = tech_score
        result['details'].extend(tech_details)

        # 4. 资金板块评分（25分）
        fund_score, fund_details = self._score_fund(sector_info, auction_data)
        result['fund_score'] = fund_score
        result['details'].extend(fund_details)

        # 总分
        total_score = price_score + volume_score + tech_score + fund_score
        result['total_score'] = total_score

        # 评级
        if total_score >= 85:
            result['rating'] = '强烈关注'
        elif total_score >= 70:
            result['rating'] = '重点观察'
        elif total_score >= 55:
            result['rating'] = '等待确认'
        else:
            result['rating'] = '过滤'

        # 操作建议
        result['suggestion'] = self._generate_suggestion(result)

        # 风险提示
        result['risk_warning'] = self._generate_risk_warning(result, auction_data)

        # 保存
        self.auction_data[ts_code] = result
        return result

    def _score_price(self, auction_data):
        """价格强度评分（25分）"""
        score = 0
        details = []
        pct_chg = auction_data.get('pct_chg', 0)

        # 高开3%-5%：+15分
        if 3 <= pct_chg < 5:
            score += 15
            details.append(f'高开{pct_chg:.1f}%（3-5%区间）: +15分')
        # 高开5%-7%：+20分
        elif 5 <= pct_chg <= 7:
            score += 20
            details.append(f'高开{pct_chg:.1f}%（5-7%区间）: +20分')
        # 高开1%-3%：+8分
        elif 1 <= pct_chg < 3:
            score += 8
            details.append(f'高开{pct_chg:.1f}%（1-3%区间）: +8分')
        # 高开7%以上：+10分（风险加大）
        elif pct_chg > 7:
            score += 10
            details.append(f'高开{pct_chg:.1f}%（>7%，风险加大）: +10分')
        else:
            details.append(f'涨幅{pct_chg:.1f}%: 0分')

        # 价格稳定（竞价波动小）：+5分
        price_std = auction_data.get('price_std', 0)
        if price_std > 0 and price_std < 0.02:
            score += 5
            details.append('竞价价格稳定: +5分')

        return min(score, 25), details

    def _score_volume(self, auction_data):
        """量能评分（25分）"""
        score = 0
        details = []

        # 竞价量超过昨日2倍：+15分
        vol_ratio = auction_data.get('vol_ratio', 0)  # 竞价量/昨日成交量
        if vol_ratio >= 2:
            score += 15
            details.append(f'竞价量是昨日{vol_ratio:.1f}倍: +15分')
        elif vol_ratio >= 1:
            score += 10
            details.append(f'竞价量是昨日{vol_ratio:.1f}倍: +10分')
        elif vol_ratio >= 0.5:
            score += 5
            details.append(f'竞价量是昨日{vol_ratio:.1f}倍: +5分')

        # 竞价金额排名靠前：+10分
        amount_rank = auction_data.get('amount_rank', 0)
        if 0 < amount_rank <= 50:
            score += 10
            details.append(f'竞价金额排名第{amount_rank}: +10分')
        elif 50 < amount_rank <= 200:
            score += 5
            details.append(f'竞价金额排名第{amount_rank}: +5分')

        # 匹配量占比高：+5分
        match_ratio = auction_data.get('match_ratio', 0)
        if match_ratio >= 0.7:
            score += 5
            details.append(f'匹配量占比{match_ratio*100:.0f}%: +5分')

        return min(score, 25), details

    def _score_tech(self, daily_data, triple_volume_info):
        """技术评分（25分）"""
        score = 0
        details = []

        if triple_volume_info:
            # 三倍量阳线：+10分
            if triple_volume_info.get('has_tv', False):
                score += 10
                details.append('前期有三倍量阳线: +10分')

            # 回踩确认：+5分
            if triple_volume_info.get('pullback_confirmed', False):
                score += 5
                details.append('回踩确认不破关键价: +5分')

        if daily_data and len(daily_data) >= 30:
            from utils.indicators import calc_macd_series, calc_kdj_series, calc_ma_series
            close_prices = [d['close'] for d in daily_data]
            high_prices = [d['high'] for d in daily_data]
            low_prices = [d['low'] for d in daily_data]
            last_idx = len(daily_data) - 1

            # MACD强势：+5分
            try:
                dif, dea, hist = calc_macd_series(close_prices)
                if dif.iloc[last_idx] > dea.iloc[last_idx] and dif.iloc[last_idx] > 0:
                    score += 5
                    details.append('MACD零轴上金叉: +5分')
            except:
                pass

            # KDJ金叉：+5分
            try:
                k, d_v, j = calc_kdj_series(high_prices, low_prices, close_prices)
                if k.iloc[last_idx] > d_v.iloc[last_idx] and k.iloc[last_idx-1] <= d_v.iloc[last_idx-1]:
                    score += 5
                    details.append('KDJ金叉: +5分')
            except:
                pass

        return min(score, 25), details

    def _score_fund(self, sector_info, auction_data):
        """资金板块评分（25分）"""
        score = 0
        details = []

        if sector_info:
            # 板块排名靠前：+10分
            sector_rank = sector_info.get('sector_rank', 0)
            if 0 < sector_rank <= 5:
                score += 10
                details.append(f'板块强度排名第{sector_rank}: +10分')
            elif 5 < sector_rank <= 15:
                score += 5
                details.append(f'板块强度排名第{sector_rank}: +5分')

            # 资金流入：+10分
            fund_inflow = sector_info.get('fund_inflow', 0)
            if fund_inflow > 100000000:  # 1亿以上
                score += 10
                details.append(f'板块资金流入{fund_inflow/100000000:.1f}亿: +10分')
            elif fund_inflow > 0:
                score += 5
                details.append(f'板块资金流入{fund_inflow/100000000:.1f}亿: +5分')

            # 热门题材：+5分
            if sector_info.get('is_hot', False):
                score += 5
                details.append('属于热门题材: +5分')

        return min(score, 25), details

    def _generate_suggestion(self, result):
        """生成操作建议"""
        score = result['total_score']
        pct = result['auction_pct_chg']

        if score >= 85:
            if 3 <= pct <= 7:
                return '竞价强势，开盘后若量能持续可考虑介入，仓位20-30%'
            elif pct > 7:
                return '高开过多，建议观察开盘后5分钟走势，不追高'
            else:
                return '综合评分高，可重点关注开盘表现'
        elif score >= 70:
            return '竞价表现较好，建议加入自选观察，等待盘中确认信号'
        elif score >= 55:
            return '竞价一般，需结合盘中走势判断，暂不操作'
        else:
            return '竞价较弱，建议过滤'

    def _generate_risk_warning(self, result, auction_data):
        """生成风险提示"""
        warnings = []
        pct = result['auction_pct_chg']

        if pct > 7:
            warnings.append('高开过多，有冲高回落风险')

        cancel_ratio = auction_data.get('cancel_ratio', 0)
        if cancel_ratio > 0.3:
            warnings.append('撤单比例较高，可能有虚假竞价')

        if result['volume_score'] < 10:
            warnings.append('竞价量能不足，持续性存疑')

        if result['tech_score'] < 10:
            warnings.append('技术面不支持，需谨慎')

        if not warnings:
            return '暂无明显风险'
        return '；'.join(warnings)

    def get_top_stocks(self, count=20, min_score=60):
        """获取评分最高的股票"""
        scored = [v for v in self.auction_data.values() if v['total_score'] >= min_score]
        scored.sort(key=lambda x: x['total_score'], reverse=True)
        return scored[:count]

    def clear(self):
        """清空数据"""
        self.auction_data.clear()
        self.scored_stocks.clear()
