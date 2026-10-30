# -*- coding: utf-8 -*-
"""
实时新闻中心模块
包含：定时刷新引擎、多源接入与统一格式化、智能去重算法、投资日历
"""

from news_center.news_config import (
    SOURCE_CONFIG, REFRESH_CONFIG, DEDUP_CONFIG, CALENDAR_CONFIG,
    PERFORMANCE_CONFIG, get_enabled_sources, get_source_info,
    CALENDAR_TYPE_COLORS, CALENDAR_TYPE_ICONS,
)
from news_center.news_sources import (
    MultiSourceNewsManager, get_multi_source_manager,
)
from news_center.news_dedup import (
    NewsDeduplicator, get_deduplicator,
)
from news_center.news_refresh_engine import (
    NewsRefreshEngine, RefreshResult, get_refresh_engine,
)
from news_center.investment_calendar import (
    CalendarDataProvider, get_calendar_provider,
)

__all__ = [
    'SOURCE_CONFIG', 'REFRESH_CONFIG', 'DEDUP_CONFIG', 'CALENDAR_CONFIG',
    'PERFORMANCE_CONFIG', 'get_enabled_sources', 'get_source_info',
    'CALENDAR_TYPE_COLORS', 'CALENDAR_TYPE_ICONS',
    'MultiSourceNewsManager', 'get_multi_source_manager',
    'NewsDeduplicator', 'get_deduplicator',
    'NewsRefreshEngine', 'RefreshResult', 'get_refresh_engine',
    'CalendarDataProvider', 'get_calendar_provider',
]
