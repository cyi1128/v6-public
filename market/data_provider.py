"""
DataProvider 统一数据提供层
主程序只调用此模块的统一接口，不直接绑定具体行情源

使用方式:
    from market.data_provider import get_data_provider

    provider = get_data_provider()
    quotes = provider.get_realtime_quotes()
    kline = provider.get_kline('000001.SZ')
    market_data = provider.get_market_data('000001.SZ')
"""
from typing import List, Dict, Optional
from .providers import PROVIDER_REGISTRY, MarketDataProvider
from .config import get_market_config


class DataProvider:
    """
    统一数据提供层
    封装所有行情数据源，对外提供统一接口
    """

    _instance = None

    def __init__(self, provider_name: str = None):
        """
        初始化数据提供者

        Args:
            provider_name: 指定行情源名称，None则使用配置中的默认源
        """
        self.config = get_market_config()
        self.provider_name = provider_name or self.config.get_current_provider()
        self._provider = None
        self._last_error = ""
        self._failover_count = 0

    @classmethod
    def instance(cls, provider_name: str = None) -> 'DataProvider':
        """获取单例"""
        if cls._instance is None or (provider_name and cls._instance.provider_name != provider_name):
            cls._instance = cls(provider_name)
        return cls._instance

    def _get_provider(self) -> Optional[MarketDataProvider]:
        """获取当前行情提供者实例"""
        if self._provider is None:
            self._init_provider()
        return self._provider

    def _init_provider(self):
        """初始化行情提供者"""
        provider_cls = PROVIDER_REGISTRY.get(self.provider_name)
        if not provider_cls:
            self._last_error = f"未知的行情源: {self.provider_name}"
            self._provider = None
            return

        provider_config = self.config.get_provider_config(self.provider_name)
        self._provider = provider_cls(provider_config)

    def _check_failover(self) -> bool:
        """
        检查是否需要故障转移

        Returns:
            True表示已切换到备用源，False表示不需要或无备用源
        """
        failover_provider = self.config.get('common.failover_provider')
        if not failover_provider or failover_provider == self.provider_name:
            return False

        if self._failover_count >= self.config.get('common.max_retry', 3):
            return False

        self._failover_count += 1
        print(f"行情源 {self.provider_name} 连接失败，切换到备用源 {failover_provider}")

        # 切换到备用源
        self.provider_name = failover_provider
        self._provider = None
        self._init_provider()

        return True

    def connect(self) -> bool:
        """
        连接行情服务器

        Returns:
            True连接成功，False连接失败
        """
        provider = self._get_provider()
        if not provider:
            return False

        if provider.connect():
            self._last_error = ""
            self._failover_count = 0
            return True

        self._last_error = provider.get_last_error()

        # 尝试故障转移
        if self.config.get('common.retry_on_fail', True):
            if self._check_failover():
                provider = self._get_provider()
                if provider and provider.connect():
                    self._last_error = ""
                    return True

        return False

    def disconnect(self):
        """断开连接"""
        if self._provider:
            self._provider.disconnect()

    def is_connected(self) -> bool:
        """检查是否已连接"""
        provider = self._get_provider()
        if not provider:
            return False
        return provider.is_connected()

    def get_last_error(self) -> str:
        """获取最后一次错误信息"""
        return self._last_error

    def get_provider_name(self) -> str:
        """获取当前行情源名称"""
        return self.provider_name

    def get_provider_desc(self) -> str:
        """获取当前行情源描述"""
        provider = self._get_provider()
        if provider:
            return provider.provider_desc
        return self.provider_name

    # ============================================================
    # 统一接口 - 主程序只调用以下方法
    # ============================================================

    def get_stock_list(self) -> List[Dict]:
        """
        获取股票列表

        Returns:
            股票列表，每项包含 ts_code, name, industry 等
        """
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return []

        if not provider.is_connected():
            if not self.connect():
                return []

        try:
            result = provider.get_stock_list()
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取股票列表异常: {str(e)}"
            return []

    def get_realtime_quotes(self, codes: List[str] = None) -> List[Dict]:
        """
        获取实时行情

        Args:
            codes: 股票代码列表，None表示全部

        Returns:
            实时行情列表
        """
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return []

        if not provider.is_connected():
            if not self.connect():
                return []

        try:
            result = provider.get_realtime_quotes(codes)
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取实时行情异常: {str(e)}"
            return []

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
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return []

        if not provider.is_connected():
            if not self.connect():
                return []

        try:
            result = provider.get_kline(code, period, count)
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取K线异常: {str(e)}"
            return []

    def get_market_data(self, code: str) -> Dict:
        """
        获取单只股票完整市场数据（实时+K线+指标）

        Args:
            code: 股票代码

        Returns:
            包含realtime、kline、indicators的字典
        """
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return {
                'ts_code': code,
                'realtime': None,
                'kline': [],
                'indicators': {},
                'error': '行情提供者未初始化',
            }

        if not provider.is_connected():
            if not self.connect():
                return {
                    'ts_code': code,
                    'realtime': None,
                    'kline': [],
                    'indicators': {},
                    'error': self._last_error,
                }

        try:
            result = provider.get_market_data(code)
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取市场数据异常: {str(e)}"
            return {
                'ts_code': code,
                'realtime': None,
                'kline': [],
                'indicators': {},
                'error': str(e),
            }

    def get_auction_data(self, codes: List[str] = None) -> List[Dict]:
        """
        获取集合竞价数据

        Args:
            codes: 股票代码列表

        Returns:
            集合竞价数据列表
        """
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return []

        if not provider.is_connected():
            if not self.connect():
                return []

        try:
            result = provider.get_auction_data(codes)
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取集合竞价数据异常: {str(e)}"
            return []

    def get_minute_data(self, code: str) -> List[Dict]:
        """
        获取分时数据

        Args:
            code: 股票代码

        Returns:
            分时数据列表
        """
        provider = self._get_provider()
        if not provider:
            self._last_error = "行情提供者未初始化"
            return []

        if not provider.is_connected():
            if not self.connect():
                return []

        try:
            result = provider.get_minute_data(code)
            self._last_error = provider.get_last_error()
            return result
        except Exception as e:
            self._last_error = f"获取分时数据异常: {str(e)}"
            return []

    def test_connection(self) -> Dict:
        """
        测试连接

        Returns:
            {'success': bool, 'message': str, 'latency': float}
        """
        provider = self._get_provider()
        if not provider:
            return {
                'success': False,
                'message': self._last_error or "行情提供者未初始化",
                'latency': 0
            }

        return provider.test_connection()

    def switch_provider(self, provider_name: str) -> bool:
        """
        切换行情源

        Args:
            provider_name: 行情源名称

        Returns:
            True切换成功，False切换失败
        """
        if provider_name not in PROVIDER_REGISTRY:
            self._last_error = f"未知的行情源: {provider_name}"
            return False

        # 断开当前连接
        if self._provider:
            self._provider.disconnect()

        # 切换到新源
        self.provider_name = provider_name
        self._provider = None
        self._failover_count = 0
        self._init_provider()

        # 更新配置
        self.config.set_current_provider(provider_name)
        self.config.save_config()

        return True

    def get_available_providers(self) -> List[Dict]:
        """
        获取所有可用的行情源

        Returns:
            [{'name': ..., 'desc': ..., 'enabled': ...}, ...]
        """
        result = []
        for name, cls in PROVIDER_REGISTRY.items():
            config = self.config.get_provider_config(name)
            enabled = config.get('enabled', False)
            result.append({
                'name': name,
                'desc': cls.provider_desc if hasattr(cls, 'provider_desc') else name,
                'enabled': enabled,
            })
        return result


def get_data_provider(provider_name: str = None) -> DataProvider:
    """
    获取数据提供者单例

    Args:
        provider_name: 指定行情源，None则使用默认

    Returns:
        DataProvider 实例
    """
    return DataProvider.instance(provider_name)
