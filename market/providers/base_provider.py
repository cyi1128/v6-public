"""
行情数据提供基类
所有行情数据源必须继承此类并实现所有抽象方法
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class MarketDataProvider(ABC):
    """行情数据提供基类"""

    provider_name = "base"
    provider_desc = "基类"

    def __init__(self, config: dict = None):
        """
        初始化行情提供者

        Args:
            config: 配置字典，包含连接参数等
        """
        self.config = config or {}
        self.connected = False
        self.last_error = ""

    @abstractmethod
    def connect(self) -> bool:
        """
        连接行情服务器

        Returns:
            True连接成功，False连接失败
        """
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查是否已连接"""
        pass

    @abstractmethod
    def get_stock_list(self) -> List[Dict]:
        """
        获取股票列表

        Returns:
            股票列表，每项包含 ts_code, name, industry 等
        """
        pass

    @abstractmethod
    def get_realtime_quotes(self, codes: List[str] = None) -> List[Dict]:
        """
        获取实时行情

        Args:
            codes: 股票代码列表，None表示全部

        Returns:
            实时行情列表
        """
        pass

    @abstractmethod
    def get_kline(self, code: str, period: str = 'daily', count: int = 250) -> List[Dict]:
        """
        获取K线数据

        Args:
            code: 股票代码
            period: 周期 daily/weekly/minute/5min/15min/30min/60min
            count: 数量

        Returns:
            K线数据列表
        """
        pass

    @abstractmethod
    def get_market_data(self, code: str) -> Dict:
        """
        获取单只股票完整市场数据（实时+K线+指标）

        Args:
            code: 股票代码

        Returns:
            包含realtime、kline、indicators的字典
        """
        pass

    @abstractmethod
    def get_auction_data(self, codes: List[str] = None) -> List[Dict]:
        """
        获取集合竞价数据

        Args:
            codes: 股票代码列表

        Returns:
            集合竞价数据列表
        """
        pass

    @abstractmethod
    def get_minute_data(self, code: str) -> List[Dict]:
        """
        获取分时数据

        Args:
            code: 股票代码

        Returns:
            分时数据列表
        """
        pass

    def get_last_error(self) -> str:
        """获取最后一次错误信息"""
        return self.last_error

    def set_error(self, msg: str):
        """设置错误信息"""
        self.last_error = msg

    def test_connection(self) -> Dict:
        """
        测试连接

        Returns:
            {'success': bool, 'message': str, 'latency': float}
        """
        import time
        start = time.time()
        try:
            ok = self.connect()
            latency = (time.time() - start) * 1000
            if ok:
                self.disconnect()
                return {
                    'success': True,
                    'message': f'{self.provider_desc}连接正常',
                    'latency': round(latency, 1)
                }
            else:
                return {
                    'success': False,
                    'message': f'{self.provider_desc}连接失败: {self.last_error}',
                    'latency': 0
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'{self.provider_desc}连接异常: {str(e)}',
                'latency': 0
            }
