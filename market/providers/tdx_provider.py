"""
TDXQuant 通达信行情数据提供者
基于 pytdx 库连接通达信行情服务器
"""
from typing import List, Dict, Optional
from .base_provider import MarketDataProvider


class TDXProvider(MarketDataProvider):
    """通达信行情数据提供者"""

    provider_name = "tdx"
    provider_desc = "通达信行情"

    # 默认通达信行情服务器列表
    DEFAULT_SERVERS = [
        ('180.153.18.170', 7709),   # 上海联通（当前可用）
        ('119.147.212.81', 7709),   # 深圳行情主站1
        ('119.147.212.82', 7709),   # 深圳行情主站2
        ('218.108.98.244', 7709),   # 杭州电信
        ('218.108.47.69', 7709),    # 杭州联通
        ('124.160.88.183', 7709),   # 宁波电信
        ('60.12.136.250', 7709),    # 绍兴电信
        ('115.238.56.198', 7709),   # 台州电信
        ('218.75.126.9', 7709),     # 长沙电信
        ('124.74.236.94', 7709),    # 上海电信
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api = None
        self.server_index = 0
        self._stock_cache = None
        self._finance_cache = {}  # 财务信息缓存 {ts_code: finance_data}

    def connect(self) -> bool:
        """连接通达信行情服务器"""
        try:
            from pytdx.hq import TdxHq_API
        except ImportError:
            self.set_error("未安装pytdx库，请运行: pip install pytdx")
            return False

        servers = self.config.get('servers', self.DEFAULT_SERVERS)
        timeout = self.config.get('timeout', 5)

        self.api = TdxHq_API()

        # 尝试连接每个服务器
        for i, (host, port) in enumerate(servers):
            try:
                if self.api.connect(host, port, time_out=timeout):
                    self.server_index = i
                    self.connected = True
                    self.last_error = ""
                    return True
            except Exception:
                continue

        self.set_error(f"无法连接到任何通达信行情服务器，已尝试{len(servers)}个服务器")
        self.api = None
        return False

    def disconnect(self):
        """断开连接"""
        if self.api and self.connected:
            try:
                self.api.disconnect()
            except Exception:
                pass
        self.api = None
        self.connected = False

    def is_connected(self) -> bool:
        """检查是否已连接"""
        if not self.connected or not self.api:
            return False
        try:
            # 简单测试连接
            self.api.get_security_count(0)
            return True
        except Exception:
            self.connected = False
            return False

    def _ensure_connected(self) -> bool:
        """确保已连接"""
        if not self.connected:
            return self.connect()
        return self.connected

    def _convert_code(self, code: str) -> tuple:
        """
        转换股票代码格式为通达信格式

        Args:
            code: 股票代码，如 000001.SZ 或 000001

        Returns:
            (market, code) market: 0=深圳, 1=上海
        """
        if '.' in code:
            code_part = code.split('.')[0]
            market_part = code.split('.')[1].upper()
        else:
            code_part = code
            if code.startswith(('60', '68', '90', '11', '13', '5')):
                market_part = 'SH'
            else:
                market_part = 'SZ'

        market = 0 if market_part in ('SZ', '0') else 1
        return market, code_part

    def _convert_code_back(self, market: int, code: str) -> str:
        """转换回标准格式"""
        suffix = '.SZ' if market == 0 else '.SH'
        return f"{code}{suffix}"

    def get_stock_list(self) -> List[Dict]:
        """获取股票列表"""
        if not self._ensure_connected():
            return []

        if self._stock_cache:
            return self._stock_cache

        stocks = []
        try:
            # 获取深圳A股
            count = self.api.get_security_count(0)
            for i in range(0, count, 1000):
                data = self.api.get_security_list(0, i)
                if data:
                    for item in data:
                        code = item.get('code', '')
                        name = item.get('name', '')
                        # 只保留A股（000, 001, 002, 300, 301开头）
                        if code and (code.startswith(('000', '001', '002', '300', '301'))):
                            stocks.append({
                                'ts_code': self._convert_code_back(0, code),
                                'code': code,
                                'name': name,
                                'market': 'SZ',
                                'industry': '',
                            })

            # 获取上海A股
            count = self.api.get_security_count(1)
            for i in range(0, count, 1000):
                data = self.api.get_security_list(1, i)
                if data:
                    for item in data:
                        code = item.get('code', '')
                        name = item.get('name', '')
                        # 只保留A股（600, 601, 603, 605, 688开头）
                        if code and code.startswith(('600', '601', '603', '605', '688')):
                            stocks.append({
                                'ts_code': self._convert_code_back(1, code),
                                'code': code,
                                'name': name,
                                'market': 'SH',
                                'industry': '',
                            })

            self._stock_cache = stocks
        except Exception as e:
            self.set_error(f"获取股票列表失败: {str(e)}")

        return stocks

    def get_finance_info(self, code: str) -> Dict:
        """
        获取股票财务信息（总股本、流通股本等）
        通过股票基本信息模块获取（更可靠）
        返回: {total_share, float_share, total_market_cap, float_market_cap, ...}
        """
        # 检查缓存
        if code in self._finance_cache:
            return self._finance_cache[code]

        try:
            from market.stock_info import get_stock_info_provider
            info_provider = get_stock_info_provider()
            info = info_provider.get_stock_info(code)
            finance = {
                'total_share': info.get('total_share', 0),
                'float_share': info.get('float_share', 0),
                'total_market_cap': info.get('total_market_cap', 0),
                'float_market_cap': info.get('float_market_cap', 0),
                'pe': info.get('pe', 0),
                'pb': info.get('pb', 0),
                'industry': info.get('industry', ''),
                'main_business': info.get('main_business', ''),
            }
            self._finance_cache[code] = finance
            return finance
        except:
            return {}

    def get_realtime_quotes(self, codes: List[str] = None) -> List[Dict]:
        """获取实时行情（含换手率、市值计算）"""
        if not self._ensure_connected():
            return []

        if codes is None:
            # 如果没有指定代码，获取股票列表
            stock_list = self.get_stock_list()
            codes = [s['ts_code'] for s in stock_list[:100]]  # 默认取前100只

        if not codes:
            return []

        quotes = []
        try:
            # 分批获取，每批最多50只
            for i in range(0, len(codes), 50):
                batch = codes[i:i+50]
                tdx_codes = []
                for code in batch:
                    market, code_part = self._convert_code(code)
                    tdx_codes.append((market, code_part))

                data = self.api.get_security_quotes(tdx_codes)
                if data:
                    for j, item in enumerate(data):
                        if item:
                            code = batch[j]
                            price = item.get('price', 0)
                            last_close = item.get('last_close', 0)
                            vol = item.get('vol', 0)
                            amount = item.get('amount', 0)
                            high = item.get('high', 0)
                            low = item.get('low', 0)
                            open_price = item.get('open', 0)

                            pct_chg = 0
                            if last_close > 0:
                                pct_chg = round((price - last_close) / last_close * 100, 2)

                            # 计算换手率和市值（需要财务信息）
                            turnover_rate = 0
                            total_market_cap = 0
                            float_market_cap = 0

                            finance = self.get_finance_info(code)
                            if finance:
                                float_share = finance.get('float_share', 0)

                                # 换手率 = 成交量 / 流通股本 × 100%
                                # vol单位是手，1手=100股
                                if float_share > 0:
                                    turnover_rate = round((vol * 100) / float_share * 100, 2)

                                # 直接使用财务信息中的市值（更准确）
                                total_market_cap = finance.get('total_market_cap', 0)
                                float_market_cap = finance.get('float_market_cap', 0)

                                # 如果市值为0，通过价格计算
                                if total_market_cap == 0:
                                    total_share = finance.get('total_share', 0)
                                    if total_share > 0 and price > 0:
                                        total_market_cap = round(total_share * price / 100000000, 2)
                                if float_market_cap == 0:
                                    if float_share > 0 and price > 0:
                                        float_market_cap = round(float_share * price / 100000000, 2)

                            quotes.append({
                                'ts_code': code,
                                'name': item.get('name', ''),
                                'price': price,
                                'last_close': last_close,
                                'open': open_price,
                                'high': high,
                                'low': low,
                                'volume': vol,
                                'amount': amount,
                                'pct_chg': pct_chg,
                                'turnover_rate': turnover_rate,
                                'total_market_cap': total_market_cap,
                                'float_market_cap': float_market_cap,
                                'bid1': item.get('bid1', 0),
                                'ask1': item.get('ask1', 0),
                                'bid1_vol': item.get('bid_vol1', 0),
                                'ask1_vol': item.get('ask_vol1', 0),
                                'bid2': item.get('bid2', 0),
                                'bid3': item.get('bid3', 0),
                                'bid4': item.get('bid4', 0),
                                'bid5': item.get('bid5', 0),
                                'ask2': item.get('ask2', 0),
                                'ask3': item.get('ask3', 0),
                                'ask4': item.get('ask4', 0),
                                'ask5': item.get('ask5', 0),
                                'bid2_vol': item.get('bid_vol2', 0),
                                'bid3_vol': item.get('bid_vol3', 0),
                                'bid4_vol': item.get('bid_vol4', 0),
                                'bid5_vol': item.get('bid_vol5', 0),
                                'ask2_vol': item.get('ask_vol2', 0),
                                'ask3_vol': item.get('ask_vol3', 0),
                                'ask4_vol': item.get('ask_vol4', 0),
                                'ask5_vol': item.get('ask_vol5', 0),
                            })
        except Exception as e:
            self.set_error(f"获取实时行情失败: {str(e)}")

        return quotes

    def get_kline(self, code: str, period: str = 'daily', count: int = 250) -> List[Dict]:
        """
        获取K线数据

        Args:
            code: 股票代码
            period: daily/weekly/monthly/1min/5min/15min/30min/60min
            count: 数量
        """
        if not self._ensure_connected():
            return []

        market, code_part = self._convert_code(code)

        # 周期映射
        period_map = {
            'daily': 9,      # 日K
            'weekly': 5,     # 周K
            'monthly': 6,    # 月K
            '1min': 0,       # 1分钟
            '5min': 1,       # 5分钟
            '15min': 2,      # 15分钟
            '30min': 3,      # 30分钟
            '60min': 4,      # 60分钟
        }

        category = period_map.get(period, 9)

        klines = []
        try:
            data = self.api.get_security_bars(category, market, code_part, 0, count)
            if data:
                for item in data:
                    klines.append({
                        'trade_date': item.get('datetime', '').replace('-', '')[:8],
                        'open': item.get('open', 0),
                        'high': item.get('high', 0),
                        'low': item.get('low', 0),
                        'close': item.get('close', 0),
                        'volume': item.get('vol', 0),
                        'amount': item.get('amount', 0),
                    })
        except Exception as e:
            self.set_error(f"获取K线失败: {str(e)}")

        return klines

    def get_market_data(self, code: str) -> Dict:
        """获取单只股票完整市场数据"""
        result = {
            'ts_code': code,
            'realtime': None,
            'kline': [],
            'indicators': {},
            'error': '',
        }

        # 获取实时行情
        quotes = self.get_realtime_quotes([code])
        if quotes:
            result['realtime'] = quotes[0]

        # 获取K线
        klines = self.get_kline(code, 'daily', 250)
        result['kline'] = klines

        # 计算基础指标
        if klines:
            try:
                from utils.indicators import (
                    calc_ma, calc_macd, calc_kdj, calc_volume_ratio
                )
                close_prices = [k['close'] for k in klines]
                high_prices = [k['high'] for k in klines]
                low_prices = [k['low'] for k in klines]
                volumes = [k['volume'] for k in klines]

                result['indicators'] = {
                    'ma5': calc_ma(close_prices, 5),
                    'ma10': calc_ma(close_prices, 10),
                    'ma20': calc_ma(close_prices, 20),
                    'ma60': calc_ma(close_prices, 60),
                    'macd': calc_macd(close_prices),
                    'kdj': calc_kdj(high_prices, low_prices, close_prices),
                    'vol_ratio': calc_volume_ratio(volumes, 5),
                }
            except Exception as e:
                result['error'] = f"指标计算失败: {str(e)}"

        return result

    def get_auction_data(self, codes: List[str] = None) -> List[Dict]:
        """获取集合竞价数据"""
        if not self._ensure_connected():
            return []

        # 通达信没有直接的集合竞价接口，用开盘前的快照模拟
        # 实际使用时可以在9:15-9:25期间调用get_realtime_quotes获取竞价数据
        quotes = self.get_realtime_quotes(codes)
        auction_list = []

        for q in quotes:
            price = q.get('price', 0)
            last_close = q.get('last_close', 0)
            if last_close > 0 and price > 0:
                open_pct = round((price - last_close) / last_close * 100, 2)
            else:
                open_pct = 0

            auction_list.append({
                'ts_code': q['ts_code'],
                'name': q['name'],
                'auction_price': price,
                'last_close': last_close,
                'open_pct': open_pct,
                'auction_volume': q.get('volume', 0),
                'auction_amount': q.get('amount', 0),
                'bid1': q.get('bid1', 0),
                'ask1': q.get('ask1', 0),
            })

        return auction_list

    def get_minute_data(self, code: str) -> List[Dict]:
        """获取分时数据"""
        if not self._ensure_connected():
            return []

        market, code_part = self._convert_code(code)

        minutes = []
        try:
            data = self.api.get_minute_time_data(market, code_part)
            if data:
                for item in data:
                    minutes.append({
                        'time': item.get('time', ''),
                        'price': item.get('price', 0),
                        'volume': item.get('vol', 0),
                        'avg_price': 0,  # 需计算
                    })

                # 计算均价线
                total_vol = 0
                total_amount = 0
                for m in minutes:
                    total_vol += m['volume']
                    total_amount += m['price'] * m['volume']
                    if total_vol > 0:
                        m['avg_price'] = round(total_amount / total_vol, 3)
        except Exception as e:
            self.set_error(f"获取分时数据失败: {str(e)}")

        return minutes
