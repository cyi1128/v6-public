"""
选股池过滤模块（通达信股票列表 + 通达信K线）
8个筛选条件：
1. 当前价格 > 近8个月最高价 × 85%
2. 当前价格 < 近8个月最高价 × 130%
3. 前一天没有涨停
4. 一年内涨停次数 ≥ 3
5. 主板（排除创业板300/301、科创板688）
6. 非ST
7. 不包含行业：地产、农业、酒、保险
8. 总市值 > 30亿，≤ 230亿
"""
import requests
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.kline_provider import get_daily_kline
from utils.tdx_stock_list import get_stocks_with_quotes_tdx


class StockPoolFilter:
    """选股池过滤器"""

    EXCLUDE_INDUSTRIES = ['地产', '房地产', '农业', '农牧', '酒', '白酒', '保险']

    def __init__(self):
        self.config = {
            'price_high_min_ratio': 0.85,
            'price_high_max_ratio': 1.30,
            'limit_up_min_count': 3,
            'market_cap_min': 30,
            'market_cap_max': 230,
            'lookback_months': 8,
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        }

    def filter_stocks(self, stock_list=None):
        """筛选股票"""
        if stock_list is None:
            stock_list = self._get_all_stocks()

        results = []
        for stock in stock_list:
            try:
                if self._check_all_conditions(stock):
                    results.append(stock)
            except Exception:
                continue
        return results

    def _check_all_conditions(self, stock):
        """检查所有条件"""
        code = stock.get('code', '')
        name = stock.get('name', '')

        # 条件5：主板
        if not self._is_main_board(code):
            return False

        # 条件6：非ST
        if self._is_st_stock(name):
            return False

        # 条件7：排除行业
        industry = stock.get('industry', '')
        if industry and self._is_excluded_industry(industry):
            return False

        # 条件8：总市值
        market_cap = stock.get('market_cap', 0)
        if not (self.config['market_cap_min'] < market_cap <= self.config['market_cap_max']):
            return False

        # 条件1、2：价格相对于8个月最高价
        current_price = stock.get('price', 0)
        high_8m = stock.get('high_8m', 0)
        if high_8m <= 0:
            return False
        price_ratio = current_price / high_8m
        if not (self.config['price_high_min_ratio'] < price_ratio < self.config['price_high_max_ratio']):
            return False

        # 条件3：前一天没有涨停
        if stock.get('prev_limit_up', False):
            return False

        # 条件4：一年内涨停次数 ≥ 3
        if stock.get('limit_up_count_1y', 0) < self.config['limit_up_min_count']:
            return False

        return True

    def _is_main_board(self, code):
        """是否主板"""
        if not code or len(code) != 6:
            return False
        if code.startswith(('300', '301', '688')):
            return False
        return code.startswith(('600', '601', '603', '605', '000', '001', '002', '003'))

    def _is_st_stock(self, name):
        """是否ST"""
        if not name:
            return False
        return 'ST' in name.upper()

    def _is_excluded_industry(self, industry):
        """是否排除行业"""
        if not industry:
            return False
        for kw in self.EXCLUDE_INDUSTRIES:
            if kw in industry:
                return True
        return False

    def _get_all_stocks(self):
        """从通达信获取股票列表，腾讯补充市值和换手率"""
        # 1. 通达信获取股票列表+实时行情（涨幅前600）
        tdx_stocks = get_stocks_with_quotes_tdx(max_stocks=600)
        if not tdx_stocks:
            return []

        # 2. 用腾讯API批量补充市值和换手率（每批50只）
        all_stocks = []
        for i in range(0, len(tdx_stocks), 50):
            batch = tdx_stocks[i:i+50]
            codes_str = ','.join([
                ('sh' if s['code'].startswith(('6', '9')) else 'sz') + s['code']
                for s in batch
            ])
            try:
                url = f'https://qt.gtimg.cn/q={codes_str}'
                resp = requests.get(url, headers=self.headers, timeout=10)
                text = resp.content.decode('gbk', errors='ignore')
                lines = text.split(';')

                for j, s in enumerate(batch):
                    if j >= len(lines):
                        break
                    try:
                        parts = lines[j].split('"')[1].split('~')
                        if len(parts) > 45:
                            market_cap = float(parts[44]) if parts[44] else 0  # 总市值（亿）
                            turnover = float(parts[38]) if parts[38] else 0  # 换手率
                        else:
                            market_cap = 0
                            turnover = 0
                    except Exception:
                        market_cap = 0
                        turnover = 0

                    all_stocks.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'change': s['change'],
                        'market_cap': market_cap,
                        'turnover': turnover,
                        'industry': '',
                    })
            except Exception:
                # 腾讯失败时只用通达信数据
                for s in batch:
                    all_stocks.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'change': s['change'],
                        'market_cap': 0,
                        'turnover': 0,
                        'industry': '',
                    })

        return all_stocks

    def _get_kline_data(self, code, count=250):
        """获取日K线数据（优先通达信）"""
        return get_daily_kline(code, count)

    def enrich_stock_data(self, stock):
        """补充股票历史数据"""
        try:
            code = stock['code']
            kline = self._get_kline_data(code, 250)

            if not kline or len(kline) < 30:
                return stock

            # 8个月最高价（约160交易日）
            lookback = min(160, len(kline))
            stock['high_8m'] = max(d['high'] for d in kline[-lookback:])

            # 前一天是否涨停
            if len(kline) >= 3:
                prev_close = kline[-2]['close']
                prev_prev_close = kline[-3]['close']
                if prev_prev_close > 0:
                    prev_pct = (prev_close - prev_prev_close) / prev_prev_close * 100
                    stock['prev_limit_up'] = prev_pct >= 9.8
                else:
                    stock['prev_limit_up'] = False
            else:
                stock['prev_limit_up'] = False

            # 一年内涨停次数
            limit_count = 0
            for i in range(1, len(kline)):
                if kline[i-1]['close'] > 0:
                    pct = (kline[i]['close'] - kline[i-1]['close']) / kline[i-1]['close'] * 100
                    if pct >= 9.8:
                        limit_count += 1
            stock['limit_up_count_1y'] = limit_count

            return stock
        except Exception:
            return stock

    def filter_with_enrichment(self, stock_list=None, max_stocks=200):
        """筛选股票并补充历史数据"""
        if stock_list is None:
            stock_list = self._get_all_stocks()

        # 第一轮：基本条件筛选
        basic_filtered = []
        for stock in stock_list:
            code = stock.get('code', '')
            name = stock.get('name', '')

            if not self._is_main_board(code):
                continue
            if self._is_st_stock(name):
                continue
            if self._is_excluded_industry(stock.get('industry', '')):
                continue
            market_cap = stock.get('market_cap', 0)
            if not (self.config['market_cap_min'] < market_cap <= self.config['market_cap_max']):
                continue
            basic_filtered.append(stock)

        # 第二轮：补充历史数据并筛选
        results = []
        for i, stock in enumerate(basic_filtered[:max_stocks]):
            try:
                enriched = self.enrich_stock_data(stock)
                if self._check_all_conditions(enriched):
                    results.append(enriched)
            except Exception:
                continue

        return results


# 单例
_stock_pool_filter = None


def get_stock_pool_filter():
    global _stock_pool_filter
    if _stock_pool_filter is None:
        _stock_pool_filter = StockPoolFilter()
    return _stock_pool_filter
