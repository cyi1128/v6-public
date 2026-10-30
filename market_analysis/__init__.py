# -*- coding: utf-8 -*-
"""
V2.8 市场分析独立包
包含：竞价强度、板块强度、个股深度资金面、实时市场情绪、板块异动监控
所有模块独立封装，通过配置开关控制，默认关闭，不影响原有业务逻辑
"""
from config.market_analysis_config import is_module_enabled

__all__ = [
    'auction_strength',
    'sector_strength',
    'deep_fund_flow',
    'market_sentiment',
    'sector_anomaly',
    'policy_matcher',
]
