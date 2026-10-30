"""
模拟行情API - 用于测试和演示
生成真实感的A股模拟数据
"""
import random
import math
from datetime import datetime, timedelta
from market.api_base import MarketAPIBase


class MockMarketAPI(MarketAPIBase):
    """模拟行情数据API"""

    def __init__(self):
        self._stock_pool = self._generate_stock_pool()
        self._daily_cache = {}
        self._realtime_cache = {}
        self._init_realtime_data()

    def _generate_stock_pool(self):
        """生成模拟股票池"""
        stocks = []
        industries = ['半导体', '新能源', '人工智能', '医药生物', '军工', '消费电子',
                      '汽车零部件', '光伏', '储能', '机器人', '云计算', '5G通信',
                      '化工新材料', '机械设备', '有色金属', '食品饮料']

        # 生成100只模拟股票
        prefixes = {
            '000': 'sz', '001': 'sz', '002': 'sz', '003': 'sz',
            '300': 'sz', '301': 'sz',
            '600': 'sh', '601': 'sh', '603': 'sh', '605': 'sh',
            '688': 'sh'
        }

        stock_names = [
            '中科曙光', '紫光国微', '韦尔股份', '兆易创新', '北方华创',
            '中芯国际', '卓胜微', '圣邦股份', '北京君正', '兆驰股份',
            '宁德时代', '比亚迪', '隆基绿能', '通威股份', '阳光电源',
            '天合光能', '晶澳科技', '亿纬锂能', '赣锋锂业', '天齐锂业',
            '海康威视', '大华股份', '科大讯飞', '浪潮信息', '中科曙光',
            '工业富联', '立讯精密', '歌尔股份', '蓝思科技', '领益智造',
            '恒瑞医药', '药明康德', '迈瑞医疗', '爱尔眼科', '智飞生物',
            '长春高新', '片仔癀', '云南白药', '同仁堂', '白云山',
            '中航沈飞', '中航西飞', '航发动力', '中直股份', '洪都航空',
            '三一重工', '中联重科', '徐工机械', '柳工', '山河智能',
            '汇川技术', '埃斯顿', '新时达', '机器人', '拓斯达',
            '用友网络', '金山办公', '广联达', '石基信息', '恒生电子',
            '中兴通讯', '烽火通信', '中际旭创', '新易盛', '光迅科技',
            '万华化学', '华鲁恒升', '扬农化工', '鲁西化工', '沧州大化',
            '紫金矿业', '洛阳钼业', '江西铜业', '云南铜业', '铜陵有色',
            '贵州茅台', '五粮液', '泸州老窖', '山西汾酒', '洋河股份',
            '长城汽车', '长安汽车', '广汽集团', '上汽集团', '北汽蓝谷',
            '阳光电源', '锦浪科技', '固德威', '德业股份', '禾迈股份',
            '派能科技', '南都电源', '雄韬股份', '亿华通', '美锦能源',
        ]

        for i in range(100):
            code_num = 300001 + i if i < 50 else 600001 + i - 50
            ts_code = f"{code_num:06d}.SZ" if code_num < 600000 else f"{code_num:06d}.SH"
            name = stock_names[i % len(stock_names)]
            industry = industries[i % len(industries)]
            market_cap = random.uniform(35, 220)  # 亿
            total_shares = market_cap * 1e8 / random.uniform(15, 40)  # 股
            list_date = (datetime.now() - timedelta(days=random.randint(365, 3650))).strftime('%Y%m%d')
            is_st = 0

            stocks.append({
                'ts_code': ts_code,
                'name': name,
                'industry': industry,
                'market_cap': round(market_cap, 2),
                'total_shares': round(total_shares, 0),
                'list_date': list_date,
                'is_st': is_st,
            })

        return stocks

    def _init_realtime_data(self):
        """初始化实时行情数据"""
        for stock in self._stock_pool:
            ts_code = stock['ts_code']
            daily = self.get_daily_data(ts_code)
            if daily:
                last_close = daily[-1]['close']
                pre_close = last_close
                # 随机生成今日开盘和当前价
                change_pct = random.uniform(-5, 8)
                price = pre_close * (1 + change_pct / 100)
                open_price = pre_close * (1 + random.uniform(-2, 3) / 100)
                high = max(price, open_price) * (1 + random.uniform(0, 1) / 100)
                low = min(price, open_price) * (1 - random.uniform(0, 1) / 100)

                base_volume = stock['total_shares'] * 0.01
                volume = base_volume * random.uniform(0.5, 3)
                amount = volume * price

                self._realtime_cache[ts_code] = {
                    'ts_code': ts_code,
                    'name': stock['name'],
                    'price': round(price, 2),
                    'pre_close': round(pre_close, 2),
                    'open': round(open_price, 2),
                    'high': round(high, 2),
                    'low': round(low, 2),
                    'volume': round(volume, 0),
                    'amount': round(amount, 0),
                    'pct_chg': round(change_pct, 2),
                    'turnover_rate': round(volume / stock['total_shares'] * 100, 2),
                    'avg_price': round(amount / volume if volume > 0 else price, 2),
                    'bid1_price': round(price * 0.999, 2),
                    'ask1_price': round(price * 1.001, 2),
                }

    def get_stock_list(self):
        """获取股票列表"""
        return self._stock_pool.copy()

    def get_daily_data(self, ts_code, start_date=None, end_date=None):
        """获取日线数据(生成250个交易日的模拟数据)"""
        if ts_code in self._daily_cache:
            return self._daily_cache[ts_code]

        stock = next((s for s in self._stock_pool if s['ts_code'] == ts_code), None)
        if not stock:
            return []

        # 生成250个交易日数据
        days = 250
        data = []
        base_price = random.uniform(10, 50)
        current_price = base_price
        today = datetime.now()

        # 生成有趋势的价格序列
        trend = random.choice(['up', 'down', 'sideways'])
        volatility = random.uniform(0.015, 0.035)

        prices = []
        for i in range(days):
            if trend == 'up':
                drift = 0.001
            elif trend == 'down':
                drift = -0.0005
            else:
                drift = 0

            change = random.gauss(drift, volatility)
            current_price = current_price * (1 + change)
            current_price = max(2, current_price)  # 不低于2元
            prices.append(current_price)

        # 确保最后价格在合理区间
        final_price = prices[-1]
        if final_price < 5 or final_price > 60:
            scale = random.uniform(8, 40) / final_price
            prices = [p * scale for p in prices]

        # 随机插入涨停
        limit_up_days = random.randint(2, 8)
        for _ in range(limit_up_days):
            idx = random.randint(20, days - 2)
            prices[idx] = prices[idx - 1] * 1.099
            # 后续几天适当调整
            if idx + 1 < days:
                prices[idx + 1] = prices[idx] * random.uniform(0.97, 1.03)

        # 生成完整K线数据
        for i in range(days):
            close = prices[i]
            prev_close = prices[i - 1] if i > 0 else close * 0.98
            pct_chg = (close - prev_close) / prev_close * 100

            high = close * (1 + random.uniform(0, 0.03))
            low = close * (1 - random.uniform(0, 0.03))
            open_p = prev_close * (1 + random.uniform(-0.02, 0.02))

            base_vol = stock['total_shares'] * 0.01
            vol_multiplier = 1 + abs(pct_chg) / 10 * 2
            if pct_chg >= 9.5:
                vol_multiplier *= 3
            volume = base_vol * vol_multiplier * random.uniform(0.7, 1.3)
            amount = volume * close

            trade_date = (today - timedelta(days=days - i - 1)).strftime('%Y%m%d')

            data.append({
                'trade_date': trade_date,
                'open': round(open_p, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': round(volume, 0),
                'amount': round(amount, 0),
                'pct_chg': round(pct_chg, 2),
                'turnover_rate': round(volume / stock['total_shares'] * 100, 2),
            })

        self._daily_cache[ts_code] = data
        return data

    def get_realtime_quote(self, ts_code):
        """获取单只股票实时行情"""
        if ts_code not in self._realtime_cache:
            self._init_realtime_data()
        return self._realtime_cache.get(ts_code, {}).copy()

    def get_realtime_quotes(self, ts_code_list=None):
        """批量获取实时行情(带模拟波动)"""
        # 模拟价格波动
        for ts_code, quote in self._realtime_cache.items():
            change = random.gauss(0, 0.002)  # 每次小波动
            new_price = quote['price'] * (1 + change)
            new_price = max(quote['low'], min(quote['high'], new_price))

            quote['price'] = round(new_price, 2)
            quote['pct_chg'] = round((new_price - quote['pre_close']) / quote['pre_close'] * 100, 2)
            quote['high'] = max(quote['high'], new_price)
            quote['low'] = min(quote['low'], new_price)

            # 成交量缓慢增加
            vol_increase = random.uniform(0, 0.005)
            quote['volume'] = round(quote['volume'] * (1 + vol_increase), 0)
            quote['amount'] = round(quote['volume'] * new_price, 0)

            stock = next((s for s in self._stock_pool if s['ts_code'] == ts_code), None)
            if stock:
                quote['turnover_rate'] = round(quote['volume'] / stock['total_shares'] * 100, 2)
                quote['avg_price'] = round(quote['amount'] / quote['volume'], 2) if quote['volume'] > 0 else new_price

        if ts_code_list:
            return [self._realtime_cache[code].copy() for code in ts_code_list if code in self._realtime_cache]
        return [q.copy() for q in self._realtime_cache.values()]

    def get_auction_data(self, ts_code_list=None):
        """获取集合竞价数据"""
        auction_list = []
        stocks = ts_code_list if ts_code_list else [s['ts_code'] for s in self._stock_pool[:50]]

        for ts_code in stocks:
            quote = self._realtime_cache.get(ts_code)
            if not quote:
                continue
            stock = next((s for s in self._stock_pool if s['ts_code'] == ts_code), None)
            if not stock:
                continue

            pre_close = quote['pre_close']
            # 模拟高开
            gap_up = random.uniform(-1, 6)
            auction_price = pre_close * (1 + gap_up / 100)

            base_vol = stock['total_shares'] * 0.001
            auction_volume = base_vol * random.uniform(0.5, 5)
            auction_amount = auction_volume * auction_price

            # 量比
            avg_daily_vol = stock['total_shares'] * 0.015
            volume_ratio = auction_volume / avg_daily_vol * 10 if avg_daily_vol > 0 else 0

            auction_list.append({
                'ts_code': ts_code,
                'name': stock['name'],
                'auction_price': round(auction_price, 2),
                'pre_close': round(pre_close, 2),
                'gap_up_pct': round(gap_up, 2),
                'auction_volume': round(auction_volume, 0),
                'auction_amount': round(auction_amount, 0),
                'volume_ratio': round(volume_ratio, 2),
                'sector_strength': round(random.uniform(0, 100), 1),
                'yesterday_strength': round(random.uniform(0, 100), 1),
            })

        return auction_list

    def get_minute_data(self, ts_code, freq='1min'):
        """获取分时数据"""
        quote = self._realtime_cache.get(ts_code)
        if not quote:
            return []

        minutes = 240  # 4小时交易
        data = []
        open_price = quote['open']
        close_price = quote['price']
        high = quote['high']
        low = quote['low']

        # 生成分时价格路径
        current = open_price
        total_change = close_price - open_price
        step_change = total_change / minutes

        for i in range(minutes):
            noise = random.gauss(0, (high - low) * 0.1)
            current = current + step_change + noise
            current = max(low, min(high, current))

            vol_per_min = quote['volume'] / minutes
            data.append({
                'time': f"{9 + i // 60:02d}:{i % 60:02d}",
                'price': round(current, 2),
                'volume': round(vol_per_min * random.uniform(0.5, 2), 0),
                'avg_price': round(quote['avg_price'], 2),
            })

        return data
