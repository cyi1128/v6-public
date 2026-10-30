"""
多策略选股模块（新浪+腾讯数据源）
策略2：趋势回踩策略（17个条件）
策略3：突破放量策略（20日突破+放量+涨停）
"""
import requests
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.kline_provider import get_daily_kline


class Strategy2Filter:
    """策略2：趋势回踩选股策略"""

    # 排除行业
    EXCLUDE_INDUSTRIES = ['房地产', '地产', '农林牧渔', '农业', '林业', '牧业', '渔业',
                          '白酒', '酒', '保险', '旅游', '酒店', '餐饮']

    def __init__(self):
        self.config = {
            'price_high_min_ratio': 0.80,      # 现价 >= 8月最高价 * 0.80
            'price_high_max_ratio': 1.10,      # 现价 <= 8月最高价 * 1.10
            'limit_up_min_count': 2,           # 近1年涨停次数 >= 2
            'rise_20d_min': 15,                # 近20日涨幅 >= 15%
            'turnover_min': 2,                 # 换手率 >= 2%
            'market_cap_min': 40,              # 总市值 >= 40亿
            'market_cap_max': 300,             # 总市值 <= 300亿
        }

    def filter_stocks(self, max_stocks=200):
        """筛选股票"""
        # 获取全市场股票
        all_stocks = self._get_all_stocks()

        # 第一轮：基本条件筛选
        basic_filtered = []
        for stock in all_stocks:
            if self._check_basic_conditions(stock):
                basic_filtered.append(stock)

        # 第二轮：补充历史数据并筛选
        results = []
        for i, stock in enumerate(basic_filtered[:max_stocks]):
            try:
                enriched = self._enrich_stock_data(stock)
                if self._check_all_conditions(enriched):
                    results.append(enriched)
            except Exception:
                continue

        return results

    def _check_basic_conditions(self, stock):
        """检查基本条件（不需要历史数据）"""
        code = stock.get('code', '')
        name = stock.get('name', '')

        # 主板
        if not self._is_main_board(code):
            return False

        # 非ST
        if self._is_st_stock(name):
            return False

        # 排除行业
        industry = stock.get('industry', '')
        if self._is_excluded_industry(industry):
            return False

        # 市值
        market_cap = stock.get('market_cap', 0)
        if not (self.config['market_cap_min'] <= market_cap <= self.config['market_cap_max']):
            return False

        return True

    def _check_all_conditions(self, stock):
        """检查所有条件"""
        current_price = stock.get('price', 0)
        high_8m = stock.get('high_8m', 0)

        # 条件1、2：价格相对于8个月最高价
        if high_8m <= 0:
            return False
        price_ratio = current_price / high_8m
        if not (self.config['price_high_min_ratio'] <= price_ratio <= self.config['price_high_max_ratio']):
            return False

        # 条件3：近1年涨停次数 >= 2
        if stock.get('limit_up_count_1y', 0) < self.config['limit_up_min_count']:
            return False

        # 条件4：昨日非涨停
        if stock.get('prev_limit_up', False):
            return False

        # 条件5：近20日涨幅 >= 15%
        if stock.get('rise_20d', 0) < self.config['rise_20d_min']:
            return False

        # 条件6：5日线 >= 10日线
        ma5 = stock.get('ma5', 0)
        ma10 = stock.get('ma10', 0)
        if ma5 <= 0 or ma10 <= 0 or ma5 < ma10:
            return False

        # 条件7：现价 >= 10日线
        if current_price < ma10:
            return False

        # 条件8：现价 <= 5日线 * 1.08
        if current_price > ma5 * 1.08:
            return False

        # 条件9：换手率 >= 2%
        if stock.get('turnover', 0) < self.config['turnover_min']:
            return False

        return True

    def _enrich_stock_data(self, stock):
        """补充股票历史数据"""
        try:
            code = stock['code']
            data = get_daily_kline(code, 250)

            if not data or len(data) < 30:
                return stock

            closes = [d['close'] for d in data]
            volumes = [d['volume'] for d in data]

            # 8个月最高价（约160交易日）
            lookback = min(160, len(data))
            stock['high_8m'] = max(d['high'] for d in data[-lookback:])

            # 昨日是否涨停
            if len(data) >= 3:
                prev_pct = (data[-2]['close'] - data[-3]['close']) / data[-3]['close'] * 100
                stock['prev_limit_up'] = prev_pct >= 9.8
            else:
                stock['prev_limit_up'] = False

            # 近1年涨停次数
            limit_count = 0
            for i in range(1, len(data)):
                if data[i-1]['close'] > 0:
                    pct = (data[i]['close'] - data[i-1]['close']) / data[i-1]['close'] * 100
                    if pct >= 9.8:
                        limit_count += 1
            stock['limit_up_count_1y'] = limit_count

            # 近20日涨幅
            if len(closes) >= 21:
                stock['rise_20d'] = (closes[-1] - closes[-21]) / closes[-21] * 100
            else:
                stock['rise_20d'] = 0

            # MA5、MA10
            stock['ma5'] = sum(closes[-5:]) / 5 if len(closes) >= 5 else 0
            stock['ma10'] = sum(closes[-10:]) / 10 if len(closes) >= 10 else 0

            # 换手率（从东方财富获取）
            stock['turnover'] = self._get_turnover(code)

            return stock
        except Exception:
            return stock

    def _get_turnover(self, code):
        """获取换手率"""
        try:
            market = 'sh' if code.startswith(('6', '9')) else 'sz'
            url = f'https://qt.gtimg.cn/q={market}{code}'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')
            # parts[38] = 换手率
            if len(parts) > 38:
                return float(parts[38])
            return 0
        except Exception:
            return 0

    def _get_all_stocks(self):
        """从通达信获取股票列表，腾讯补充市值和换手率"""
        from utils.tdx_stock_list import get_stocks_with_quotes_tdx
        tdx_stocks = get_stocks_with_quotes_tdx(max_stocks=600)
        if not tdx_stocks:
            return []

        # 用腾讯API批量补充市值和换手率
        all_stocks = []
        headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'}
        for i in range(0, len(tdx_stocks), 50):
            batch = tdx_stocks[i:i+50]
            codes_str = ','.join([
                ('sh' if s['code'].startswith(('6', '9')) else 'sz') + s['code']
                for s in batch
            ])
            try:
                url = f'https://qt.gtimg.cn/q={codes_str}'
                resp = requests.get(url, headers=headers, timeout=10)
                text = resp.content.decode('gbk', errors='ignore')
                lines = text.split(';')
                for j, s in enumerate(batch):
                    if j >= len(lines):
                        break
                    try:
                        parts = lines[j].split('"')[1].split('~')
                        market_cap = float(parts[44]) if len(parts) > 44 and parts[44] else 0
                        turnover = float(parts[38]) if len(parts) > 38 and parts[38] else 0
                    except Exception:
                        market_cap = 0
                        turnover = 0
                    all_stocks.append({
                        'code': s['code'], 'name': s['name'],
                        'price': s['price'], 'change': s['change'],
                        'turnover': turnover, 'market_cap': market_cap, 'industry': '',
                    })
            except Exception:
                for s in batch:
                    all_stocks.append({
                        'code': s['code'], 'name': s['name'],
                        'price': s['price'], 'change': s['change'],
                        'turnover': 0, 'market_cap': 0, 'industry': '',
                    })
        return all_stocks

    def _is_main_board(self, code):
        """是否主板"""
        if not code or len(code) != 6:
            return False
        if code.startswith(('300', '301', '688')):
            return False
        return code.startswith(('600', '601', '603', '605', '000', '001', '002', '003'))

    def _is_st_stock(self, name):
        """是否ST"""
        return 'ST' in name.upper() if name else False

    def _is_excluded_industry(self, industry):
        """是否排除行业"""
        if not industry:
            return False
        for kw in self.EXCLUDE_INDUSTRIES:
            if kw in industry:
                return True
        return False


class Strategy3Filter:
    """策略3：突破放量选股策略"""

    def __init__(self):
        self.config = {
            'consecutive_days': 4,        # 连续4天站稳20日线
            'lookback_days': 15,          # 15个交易日内
            'vol_ma_period': 120,         # 120日均量
            'turnover_threshold': 7,      # 换手率 > 7%
            'limit_lookback': 7,          # 7个交易日内
            'big_rise_pct': 7,            # 涨幅超过7%
            'close_rise_pct': 5,          # 收盘涨幅5%以上
        }

    def filter_stocks(self, max_stocks=200):
        """筛选股票"""
        all_stocks = self._get_all_stocks()

        # 第一轮：基本条件（主板、非ST、非科创）
        basic_filtered = []
        for stock in all_stocks:
            if self._check_basic_conditions(stock):
                basic_filtered.append(stock)

        # 第二轮：技术形态筛选
        results = []
        for i, stock in enumerate(basic_filtered[:max_stocks]):
            try:
                if self._check_technical_conditions(stock):
                    results.append(stock)
            except Exception:
                continue

        return results

    def _check_basic_conditions(self, stock):
        """基本条件：主板、非ST、非科创"""
        code = stock.get('code', '')
        name = stock.get('name', '')

        # 主板（排除创业板、科创板）
        if not code or len(code) != 6:
            return False
        if code.startswith(('300', '301', '688')):
            return False
        if not code.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
            return False

        # 非ST
        if name and 'ST' in name.upper():
            return False

        return True

    def _check_technical_conditions(self, stock):
        """技术形态条件"""
        try:
            code = stock['code']
            data = get_daily_kline(code, 150)

            if not data or len(data) < 30:
                return False

            closes = [d['close'] for d in data]
            highs = [d['high'] for d in data]
            volumes = [d['volume'] for d in data]

            # 计算MA20
            ma20_list = []
            for i in range(len(closes)):
                if i >= 19:
                    ma20_list.append(sum(closes[i-19:i+1]) / 20)
                else:
                    ma20_list.append(0)

            # 条件1：15个交易日内出现连续4天收盘价站稳20日均线上方
            consecutive_start = -1
            lookback = min(self.config['lookback_days'], len(closes) - 4)

            for i in range(-lookback, -3):
                # 检查连续4天收盘价 > MA20
                all_above = True
                for j in range(4):
                    idx = i + j
                    if idx >= 0 or ma20_list[idx] == 0 or closes[idx] <= ma20_list[idx]:
                        all_above = False
                        break
                if all_above:
                    consecutive_start = i
                    break

            if consecutive_start == -1:
                return False

            # 条件2：上穿的4天里或后面5个交易日内，任意1天成交量 > 120日均量 且 换手率 > 7%
            vol_ma_120 = sum(volumes[-120:]) / 120 if len(volumes) >= 120 else sum(volumes) / len(volumes)

            vol_condition_met = False
            end_idx = min(consecutive_start + 4 + 5, -1)
            for i in range(consecutive_start, end_idx + 1):
                if i >= 0:
                    continue
                if volumes[i] > vol_ma_120:
                    turnover = self._get_turnover(code, data[i])
                    if turnover > self.config['turnover_threshold']:
                        vol_condition_met = True
                        break

            if not vol_condition_met:
                return False

            # 条件3：7个交易日内出现过涨停 或 收盘涨幅>7% 或 日内涨幅>=7%且收盘涨幅>=5%
            limit_lookback = min(self.config['limit_lookback'], len(closes) - 1)
            big_rise_found = False

            for i in range(-limit_lookback, 0):
                if i - 1 < -len(closes):
                    continue
                prev_close = closes[i-1]
                if prev_close <= 0:
                    continue

                close_pct = (closes[i] - prev_close) / prev_close * 100
                intraday_pct = (highs[i] - prev_close) / prev_close * 100

                # 涨停
                if close_pct >= 9.8:
                    big_rise_found = True
                    break
                # 收盘涨幅超过7%
                if close_pct > self.config['big_rise_pct']:
                    big_rise_found = True
                    break
                # 日内涨幅>=7% 且 收盘涨幅>=5%
                if intraday_pct >= self.config['big_rise_pct'] and close_pct >= self.config['close_rise_pct']:
                    big_rise_found = True
                    break

            if not big_rise_found:
                return False

            # 补充数据
            stock['ma20'] = ma20_list[-1] if ma20_list else 0
            stock['vol_ma_120'] = vol_ma_120
            return True

        except Exception:
            return False

    def _get_turnover(self, code, kline_data):
        """获取换手率"""
        try:
            market = 'sh' if code.startswith(('6', '9')) else 'sz'
            url = f'https://qt.gtimg.cn/q={market}{code}'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')
            if len(parts) > 38:
                return float(parts[38])
            return 0
        except Exception:
            return 0

    def _get_all_stocks(self):
        """从通达信获取股票列表+实时行情"""
        from utils.tdx_stock_list import get_stocks_with_quotes_tdx
        return get_stocks_with_quotes_tdx(max_stocks=600)
