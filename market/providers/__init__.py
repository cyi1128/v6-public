"""
行情数据提供者模块
"""
from .base_provider import MarketDataProvider
from .tdx_provider import TDXProvider
from .eastmoney_provider import EastMoneyProvider
from .tencent_provider import TencentProvider
from .joinquant_provider import JoinQuantProvider
from .ricequant_provider import RiceQuantProvider

# 提供者注册表
PROVIDER_REGISTRY = {
    'tdx': TDXProvider,
    'eastmoney': EastMoneyProvider,
    'tencent': TencentProvider,
    'joinquant': JoinQuantProvider,
    'ricequant': RiceQuantProvider,
}

__all__ = [
    'MarketDataProvider',
    'TDXProvider',
    'EastMoneyProvider',
    'TencentProvider',
    'JoinQuantProvider',
    'RiceQuantProvider',
    'PROVIDER_REGISTRY',
]
