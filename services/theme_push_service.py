# -*- coding: utf-8 -*-
"""
题材新闻自动推送服务
- 实时新闻流接入
- 自动提取新闻题材，匹配涨停数据库相关股票
- 推送到企业微信
"""
import os
import sys
import time
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.theme_news_matcher import match_news_to_stocks, format_push_message
from utils.wechat_push import WechatPusher

# 去重：5分钟内同一新闻不重复推
DEDUP_WINDOW = 300
_pushed_news = {}  # {news_title: push_time}


def process_news(title, content=''):
    """处理一条新闻：匹配题材股票，推送到企业微信"""
    # 去重
    now = time.time()
    if title in _pushed_news:
        if now - _pushed_news[title] < DEDUP_WINDOW:
            return
    _pushed_news[title] = now
    
    # 匹配
    stocks, sentiment = match_news_to_stocks(title, content)
    
    # 只推利好/利空，中性不推
    if sentiment == 'neutral' or len(stocks) < 3:
        return
    
    # 只推前10只
    stocks = stocks[:10]
    
    # V3.0 推送重构：题材新闻命中真实股票，归为 📰【事件驱动】，走统一推送总线
    try:
        from services.wechat_bus import get_wechat_bus
        bus = get_wechat_bus()
        bus.send_event_driven(
            event=title,
            impact='题材/产业链相关新闻',
            direction=('利好' if sentiment == 'positive' else '利空'),
            chain='',
            stocks=list(stocks),
            market='',
            reason=f'新闻匹配到{len(stocks)}只关联股票',
            status=sentiment,
            risk='',
            event_id=title,
        )
        print(f"[{datetime.now()}] 事件驱动推送: {title}")
    except Exception as e:
        print(f"题材新闻推送异常: {e}")


if __name__ == '__main__':
    # 测试推送
    test_news = "光模块需求爆发，CPO技术突破，订单排到明年"
    process_news(test_news)
