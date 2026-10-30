"""
行情数据模块

使用方式:
    from market import get_data_provider

    provider = get_data_provider()
    quotes = provider.get_realtime_quotes()
    kline = provider.get_kline('000001.SZ')
    market_data = provider.get_market_data('000001.SZ')
"""
from .data_provider import DataProvider, get_data_provider
from .config import get_market_config, MarketConfig
from .providers import PROVIDER_REGISTRY

__all__ = [
    'DataProvider',
    'get_data_provider',
    'get_market_config',
    'MarketConfig',
    'PROVIDER_REGISTRY',
]
