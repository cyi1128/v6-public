# -*- coding: utf-8 -*-
"""
news_engine 兼容模块
内部使用 news_center 多源新闻聚合管理器，提供与旧版 news_engine 兼容的接口
"""
from news_engine.news_manager import get_news_manager, NewsManager

__all__ = ['get_news_manager', 'NewsManager']
