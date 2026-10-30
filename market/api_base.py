"""
行情API基类 - 抽象接口定义
所有行情数据源需继承此类并实现对应方法
"""
from abc import ABC, abstractmethod


class MarketAPIBase(ABC):
    """行情API抽象基类"""

    @abstractmethod
    def get_stock_list(self):
        """
        获取股票列表
        返回: list of dict, 每个dict包含 ts_code, name, industry, market_cap, total_shares, list_date, is_st
        """
        pass

    @abstractmethod
    def get_daily_data(self, ts_code, start_date=None, end_date=None):
        """
        获取日线行情数据
        返回: list of dict, 每个dict包含 trade_date, open, high, low, close, volume, amount, pct_chg, turnover_rate
        """
        pass

    @abstractmethod
    def get_realtime_quote(self, ts_code):
        """
        获取单只股票实时行情
        返回: dict 包含 price, pre_close, open, high, low, volume, amount, pct_chg, turnover_rate 等
        """
        pass

    @abstractmethod
    def get_realtime_quotes(self, ts_code_list=None):
        """
        批量获取实时行情
        返回: list of dict
        """
        pass

    @abstractmethod
    def get_auction_data(self, ts_code_list=None):
        """
        获取集合竞价数据(9:15-9:25)
        返回: list of dict
        """
        pass

    @abstractmethod
    def get_minute_data(self, ts_code, freq='1min'):
        """
        获取分时数据
        返回: list of dict
        """
        pass

    def is_market_open(self):
        """判断当前是否交易时间"""
        from datetime import datetime, time
        now = datetime.now()
        # 工作日
        if now.weekday() >= 5:
            return False
        t = now.time()
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        if (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end):
            return True
        return False

    def is_auction_time(self):
        """判断是否集合竞价时间"""
        from datetime import datetime, time
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.time()
        return time(9, 15) <= t <= time(9, 25)
