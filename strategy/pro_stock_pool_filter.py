# -*- coding: utf-8 -*-
"""
V6.0 Pro 股票池筛选逻辑

基于用户最新选股策略：
- 价格条件：当前价格 > 近8个月最高价×70%，当前价格 < 近8个月最高价×105%
- 强度条件：前一天没有涨停，一年内涨停次数≥3次
- 股票范围：主板
- 过滤：ST股票，排除行业（地产、农业、酒类、保险）
- 市值：30亿 < 总市值 ≤230亿
- 股价过滤：剔除60元以上、5元以下
"""
import time
from datetime import datetime, timedelta


class ProStockPoolFilter:
    """V6.0 Pro 专业股票池过滤器"""

    # 排除行业
    EXCLUDE_INDUSTRIES = ['地产', '农业', '酒', '保险']

    # 价格区间
    MIN_PRICE = 5.0
    MAX_PRICE = 60.0

    # 市值区间（亿）
    MIN_MARKET_CAP = 30.0
    MAX_MARKET_CAP = 230.0

    # 8个月交易日数（约160个交易日）
    HIGH_PERIOD_DAYS = 160

    # 一年涨停次数阈值
    MIN_LIMIT_UP_COUNT = 3

    # 价格相对8个月高点的区间
    PRICE_RATIO_LOW = 0.70
    PRICE_RATIO_HIGH = 1.05

    def __init__(self):
        self._last_filter_time = None
        self._cached_result = []

    def filter_stock(self, stock, kline_data):
        """
        单只股票筛选

        参数：
            stock: 股票基本信息 {'code','name','price','market_cap','industry',...}
            kline_data: K线数据 {'close':[], 'high':[], 'low':[], 'volume':[], 'date':[]}

        返回：
            dict or None（通过筛选返回股票信息，否则None）
        """
        if not stock or not kline_data:
            return None

        code = stock.get('code', '')
        name = stock.get('name', '')
        price = stock.get('price', 0)
        market_cap = stock.get('market_cap', 0)  # 单位：亿
        industry = stock.get('industry', '')

        # 1. ST过滤
        if 'ST' in name or 'st' in name.lower() or '*ST' in name:
            return None

        # 2. 主板过滤（60开头沪市主板，00开头深市主板）
        if not (code.startswith('60') or code.startswith('00')):
            return None

        # 3. 行业过滤
        for excl in self.EXCLUDE_INDUSTRIES:
            if excl in industry:
                return None

        # 4. 价格过滤
        if price < self.MIN_PRICE or price > self.MAX_PRICE:
            return None

        # 5. 市值过滤
        if market_cap <= self.MIN_MARKET_CAP or market_cap > self.MAX_MARKET_CAP:
            return None

        # 6. K线数据检查
        closes = kline_data.get('close', [])
        highs = kline_data.get('high', [])
        if len(closes) < 30 or len(highs) < 30:
            return None

        # 7. 近8个月最高价
        recent_highs = highs[-self.HIGH_PERIOD_DAYS:] if len(highs) >= self.HIGH_PERIOD_DAYS else highs
        if not recent_highs:
            return None
        high_8m = max(recent_highs)

        # 8. 价格区间条件
        price_ratio = price / high_8m if high_8m > 0 else 0
        if price_ratio < self.PRICE_RATIO_LOW or price_ratio > self.PRICE_RATIO_HIGH:
            return None

        # 9. 前一天没有涨停
        if len(closes) >= 2:
            yesterday_close = closes[-2]
            today_close = closes[-1]
            if yesterday_close > 0:
                yesterday_change = (today_close - yesterday_close) / yesterday_close * 100
                # 前一天涨停（涨幅>=9.8%）
                if yesterday_change >= 9.8:
                    return None

        # 10. 一年内涨停次数≥3
        limit_up_count = self._calc_limit_up_count(kline_data)
        if limit_up_count < self.MIN_LIMIT_UP_COUNT:
            return None

        # 通过筛选
        result = dict(stock)
        result['high_8m'] = round(high_8m, 2)
        result['price_ratio'] = round(price_ratio * 100, 1)
        result['limit_up_count'] = limit_up_count
        result['filter_pass'] = True
        return result

    def _calc_limit_up_count(self, kline_data, days=240):
        """计算近N天涨停次数"""
        closes = kline_data.get('close', [])
        if len(closes) < 2:
            return 0

        recent = closes[-days:] if len(closes) > days else closes
        count = 0
        for i in range(1, len(recent)):
            if recent[i-1] > 0:
                change = (recent[i] - recent[i-1]) / recent[i-1] * 100
                if change >= 9.8:
                    count += 1
        return count

    def batch_filter(self, stock_list, kline_provider, progress_callback=None):
        """
        批量筛选股票池

        参数：
            stock_list: 股票列表 [{'code','name','price','market_cap','industry'},...]
            kline_provider: K线数据提供函数(code)->kline_data
            progress_callback: 进度回调(current, total)

        返回：
            通过筛选的股票列表
        """
        results = []
        total = len(stock_list)

        for i, stock in enumerate(stock_list):
            try:
                code = stock.get('code', '')
                kline = kline_provider(code)
                filtered = self.filter_stock(stock, kline)
                if filtered:
                    results.append(filtered)
            except Exception as e:
                print(f"[ProStockPool] 筛选{stock.get('code','?')}失败: {e}")

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(i + 1, total)

        if progress_callback:
            progress_callback(total, total)

        self._cached_result = results
        self._last_filter_time = datetime.now()
        return results

    def get_cached_result(self):
        """获取缓存的筛选结果"""
        return self._cached_result

    def get_filter_summary(self):
        """获取筛选条件摘要"""
        return {
            'price_range': f'{self.MIN_PRICE}-{self.MAX_PRICE}元',
            'market_cap_range': f'{self.MIN_MARKET_CAP}-{self.MAX_MARKET_CAP}亿',
            'exclude_industries': ','.join(self.EXCLUDE_INDUSTRIES),
            'limit_up_min': self.MIN_LIMIT_UP_COUNT,
            'high_period': '8个月',
            'price_ratio': f'{int(self.PRICE_RATIO_LOW*100)}%-{int(self.PRICE_RATIO_HIGH*100)}%',
            'board': '主板',
            'last_filter_time': self._last_filter_time.strftime('%Y-%m-%d %H:%M:%S') if self._last_filter_time else '未筛选',
            'result_count': len(self._cached_result),
        }


# 单例
_pro_filter = None


def get_pro_stock_pool_filter():
    """获取V6.0 Pro股票池过滤器单例"""
    global _pro_filter
    if _pro_filter is None:
        _pro_filter = ProStockPoolFilter()
    return _pro_filter
