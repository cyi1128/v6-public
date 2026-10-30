"""
Tushare行情API实现
需要配置token才能使用
"""
try:
    import tushare as ts
except ImportError:
    ts = None

from market.api_base import MarketAPIBase


class TushareAPI(MarketAPIBase):
    """Tushare行情API"""

    def __init__(self, token=''):
        self.token = token
        self.pro = None
        if ts and token:
            ts.set_token(token)
            self.pro = ts.pro_api()

    def is_available(self):
        return self.pro is not None

    def get_stock_list(self):
        """获取股票列表"""
        if not self.pro:
            return []
        try:
            df = self.pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,industry,list_date,market'
            )
            stocks = []
            for _, row in df.iterrows():
                stocks.append({
                    'ts_code': row['ts_code'],
                    'name': row['name'],
                    'industry': row.get('industry', ''),
                    'market_cap': 0,  # 需要另外获取
                    'total_shares': 0,
                    'list_date': row.get('list_date', ''),
                    'is_st': 1 if 'ST' in row['name'] else 0,
                })
            return stocks
        except Exception as e:
            print(f"Tushare获取股票列表失败: {e}")
            return []

    def get_daily_data(self, ts_code, start_date=None, end_date=None):
        """获取日线数据"""
        if not self.pro:
            return []
        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            if df is None or df.empty:
                return []
            df = df.sort_values('trade_date')
            data = []
            for _, row in df.iterrows():
                data.append({
                    'trade_date': row['trade_date'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['vol'],
                    'amount': row['amount'],
                    'pct_chg': row.get('pct_chg', 0),
                    'turnover_rate': 0,
                })
            return data
        except Exception as e:
            print(f"Tushare获取日线数据失败 {ts_code}: {e}")
            return []

    def get_realtime_quote(self, ts_code):
        """获取实时行情(Tushare pro 不支持实时行情,返回空)"""
        return {}

    def get_realtime_quotes(self, ts_code_list=None):
        """批量获取实时行情"""
        return []

    def get_auction_data(self, ts_code_list=None):
        """获取集合竞价数据"""
        return []

    def get_minute_data(self, ts_code, freq='1min'):
        """获取分时数据"""
        if not self.pro:
            return []
        try:
            df = ts.pro_bar(
                ts_code=ts_code,
                freq=freq,
                asset='E'
            )
            if df is None or df.empty:
                return []
            data = []
            for _, row in df.iterrows():
                data.append({
                    'time': row.get('trade_time', ''),
                    'price': row['close'],
                    'volume': row['vol'],
                    'amount': row.get('amount', 0),
                })
            return data
        except Exception as e:
            print(f"Tushare获取分时数据失败 {ts_code}: {e}")
            return []
