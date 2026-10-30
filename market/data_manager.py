"""
行情数据管理器 - 统一管理行情数据源
基于 DataProvider 统一接口层，增加数据库缓存能力
"""
from typing import List, Dict, Optional
from market.data_provider import get_data_provider, DataProvider
from core.database import get_db


class DataManager:
    """数据管理器"""

    def __init__(self, provider_name: str = None):
        """
        初始化数据管理器

        Args:
            provider_name: 指定行情源，None则使用默认配置
        """
        self.provider: DataProvider = get_data_provider(provider_name)
        self.db = get_db()
        self._stock_pool = []
        self._connected = False

    def connect(self) -> bool:
        """连接行情服务器"""
        if self.provider.connect():
            self._connected = True
            return True
        self._connected = False
        return False

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self.provider.is_connected()

    def get_last_error(self) -> str:
        """获取最后错误信息"""
        return self.provider.get_last_error()

    def get_provider_name(self) -> str:
        """获取当前行情源名称"""
        return self.provider.get_provider_name()

    def get_provider_desc(self) -> str:
        """获取当前行情源描述"""
        return self.provider.get_provider_desc()

    def init_stock_pool(self) -> List[Dict]:
        """初始化股票池"""
        stocks = self.provider.get_stock_list()
        if stocks:
            for s in stocks:
                self.db.save_stock_info(
                    ts_code=s['ts_code'],
                    name=s['name'],
                    industry=s.get('industry', ''),
                    market_cap=s.get('market_cap', 0),
                    total_shares=s.get('total_shares', 0),
                    list_date=s.get('list_date', ''),
                    is_st=s.get('is_st', 0)
                )
            self._stock_pool = stocks
        else:
            # 如果API获取失败，从数据库加载
            self._stock_pool = self.db.get_all_stocks()
        return self._stock_pool

    def get_stock_pool(self) -> List[Dict]:
        """获取股票池"""
        if not self._stock_pool:
            self._stock_pool = self.db.get_all_stocks()
            if not self._stock_pool:
                self.init_stock_pool()
        return self._stock_pool

    def get_daily_data(self, ts_code: str, days: int = 250) -> List[Dict]:
        """
        获取日线数据(优先从数据库,不足则从API)

        Args:
            ts_code: 股票代码
            days: 获取天数

        Returns:
            日线数据列表
        """
        # 先从数据库取
        db_data = self.db.get_daily_data(ts_code, limit=days)
        if len(db_data) >= days * 0.8:
            # 统一字段名，同时支持 vol 和 volume
            for d in db_data:
                if 'vol' in d and 'volume' not in d:
                    d['volume'] = d['vol']
                elif 'volume' in d and 'vol' not in d:
                    d['vol'] = d['volume']
            return db_data

        # 从API获取
        api_data = self.provider.get_kline(ts_code, 'daily', days)
        if api_data:
            # 转换格式并存入数据库
            daily_list = []
            for k in api_data:
                vol = k.get('volume', k.get('vol', 0))
                daily_list.append({
                    'trade_date': k.get('trade_date', ''),
                    'open': k.get('open', 0),
                    'high': k.get('high', 0),
                    'low': k.get('low', 0),
                    'close': k.get('close', 0),
                    'vol': vol,
                    'volume': vol,  # 兼容字段名
                    'amount': k.get('amount', 0),
                    'pct_chg': 0,  # 需计算
                    'turnover_rate': 0,
                })
            # 计算涨跌幅
            for i in range(1, len(daily_list)):
                prev_close = daily_list[i-1]['close']
                if prev_close > 0:
                    daily_list[i]['pct_chg'] = round(
                        (daily_list[i]['close'] - prev_close) / prev_close * 100, 2
                    )

            self.db.save_daily_data(ts_code, daily_list)
            return daily_list[-days:] if len(daily_list) > days else daily_list

        return db_data

    def get_realtime_quotes(self, ts_code_list: List[str] = None) -> List[Dict]:
        """
        获取实时行情

        Args:
            ts_code_list: 股票代码列表，None表示全部

        Returns:
            实时行情列表
        """
        quotes = self.provider.get_realtime_quotes(ts_code_list)
        if quotes:
            # 转换格式并存入数据库
            rt_list = []
            for q in quotes:
                rt_list.append({
                    'ts_code': q['ts_code'],
                    'name': q.get('name', ''),
                    'price': q.get('price', 0),
                    'last_close': q.get('last_close', 0),
                    'open': q.get('open', 0),
                    'high': q.get('high', 0),
                    'low': q.get('low', 0),
                    'volume': q.get('volume', 0),
                    'amount': q.get('amount', 0),
                    'pct_chg': q.get('pct_chg', 0),
                    'bid1': q.get('bid1', 0),
                    'ask1': q.get('ask1', 0),
                })
            self.db.save_realtime_data(rt_list)
        return quotes

    def get_realtime_quote(self, ts_code: str) -> Optional[Dict]:
        """获取单只股票实时行情"""
        quotes = self.provider.get_realtime_quotes([ts_code])
        if quotes:
            return quotes[0]
        return None

    def get_auction_data(self, ts_code_list: List[str] = None) -> List[Dict]:
        """
        获取集合竞价数据

        Args:
            ts_code_list: 股票代码列表

        Returns:
            集合竞价数据列表
        """
        return self.provider.get_auction_data(ts_code_list)

    def get_minute_data(self, ts_code: str, freq: str = '1min') -> List[Dict]:
        """
        获取分时数据

        Args:
            ts_code: 股票代码
            freq: 频率

        Returns:
            分时数据列表
        """
        return self.provider.get_minute_data(ts_code)

    def get_market_data(self, ts_code: str) -> Dict:
        """
        获取单只股票完整市场数据

        Args:
            ts_code: 股票代码

        Returns:
            包含realtime、kline、indicators的字典
        """
        return self.provider.get_market_data(ts_code)

    def test_connection(self) -> Dict:
        """测试连接"""
        return self.provider.test_connection()

    def switch_provider(self, provider_name: str) -> bool:
        """切换行情源"""
        if self.provider.switch_provider(provider_name):
            self._connected = False
            self._stock_pool = []
            return True
        return False

    def is_market_open(self) -> bool:
        """
        判断是否交易时间

        Returns:
            True表示交易时间，False表示非交易时间
        """
        import datetime
        now = datetime.datetime.now()

        # 周末休市
        if now.weekday() >= 5:
            return False

        # 交易时间: 9:30-11:30, 13:00-15:00
        hour = now.hour
        minute = now.minute
        time_val = hour * 60 + minute

        # 上午 9:30 - 11:30
        if 9 * 60 + 30 <= time_val <= 11 * 60 + 30:
            return True

        # 下午 13:00 - 15:00
        if 13 * 60 <= time_val <= 15 * 60:
            return True

        return False

    def is_auction_time(self) -> bool:
        """
        判断是否集合竞价时间

        Returns:
            True表示集合竞价时间
        """
        import datetime
        now = datetime.datetime.now()

        # 周末休市
        if now.weekday() >= 5:
            return False

        hour = now.hour
        minute = now.minute
        time_val = hour * 60 + minute

        # 早盘集合竞价: 9:15 - 9:25
        if 9 * 60 + 15 <= time_val <= 9 * 60 + 25:
            return True

        # 尾盘集合竞价: 14:57 - 15:00
        if 14 * 60 + 57 <= time_val <= 15 * 60:
            return True

        return False

    def get_market_status(self) -> str:
        """
        获取市场状态

        Returns:
            'closed' / 'auction' / 'trading'
        """
        if self.is_auction_time():
            return 'auction'
        elif self.is_market_open():
            return 'trading'
        else:
            return 'closed'


# 全局单例
_data_manager = None


def get_data_manager(provider_name: str = None) -> DataManager:
    """
    获取数据管理器单例

    Args:
        provider_name: 指定行情源，None则使用默认

    Returns:
        DataManager 实例
    """
    global _data_manager
    if _data_manager is None or (provider_name and _data_manager.get_provider_name() != provider_name):
        _data_manager = DataManager(provider_name)
    return _data_manager
