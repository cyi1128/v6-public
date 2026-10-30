# -*- coding: utf-8 -*-
"""
题材新闻匹配推送器
- 实时新闻进来，提取题材关键词
- 去涨停原因数据库找最近涨停过、题材匹配的股票
- 匹配到就推送到企业微信
"""
import os
import sys
import sqlite3
import re
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'limit_up_reason.db')

# 利好关键词
BULLISH = ['利好', '上涨', '涨停', '突破', '中标', '订单', '量产', '投产', '涨价', '业绩预增', '超预期', '新高']
# 利空关键词
BEARISH = ['利空', '下跌', '跌停', '减持', '处罚', '立案', '亏损', '暴雷', '风险']


def get_stocks_by_theme_keyword(keyword):
    """根据题材关键词，从涨停数据库找相关股票"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 找所有reason里包含这个关键词的股票
    c.execute('''
        SELECT code, name, reason, date FROM limit_up_reasons
        WHERE reason LIKE ?
        GROUP BY code
        ORDER BY date DESC
    ''', (f'%{keyword}%',))
    results = []
    for row in c.fetchall():
        results.append({
            'code': row[0],
            'name': row[1],
            'reason': row[2],
            'date': row[3]
        })
    conn.close()
    return results


def extract_theme_from_news(title, content=''):
    """从新闻标题/内容里提取题材关键词"""
    text = title + ' ' + content
    # 涨停题材数据库里所有的题材词
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT DISTINCT reason FROM limit_up_reasons WHERE source="ths"')
    all_reasons = [row[0] for row in c.fetchall()]
    conn.close()
    
    # 把所有reason拆成单个题材词
    all_themes = set()
    for r in all_reasons:
        if not r:
            continue
        for t in r.split('+'):
            t = t.strip()
            if len(t) >= 2:
                all_themes.add(t)
    
    # 找出新闻里提到的题材词
    matched_themes = []
    for theme in all_themes:
        if theme in text:
            matched_themes.append(theme)
    
    return matched_themes


def match_news_to_stocks(title, content=''):
    """新闻匹配股票：返回匹配到的股票列表"""
    # 先判断利好还是利空
    is_bullish = any(k in title for k in BULLISH)
    is_bearish = any(k in title for k in BEARISH)
    
    # 提取题材
    themes = extract_theme_from_news(title, content)
    if not themes:
        return [], 'neutral'
    
    # 找所有相关股票
    stocks = {}
    for theme in themes:
        related = get_stocks_by_theme_keyword(theme)
        for s in related:
            code = s['code']
            if code not in stocks:
                stocks[code] = s
                stocks[code]['matched_themes'] = []
            stocks[code]['matched_themes'].append(theme)
    
    # 按匹配题材数量排序
    result = sorted(stocks.values(), key=lambda x: len(x['matched_themes']), reverse=True)
    
    sentiment = 'bullish' if is_bullish else ('bearish' if is_bearish else 'neutral')
    return result, sentiment


def format_push_message(news_title, stocks, sentiment):
    """格式化推送消息"""
    sentiment_emoji = '📈 利好' if sentiment == 'bullish' else ('📉 利空' if sentiment == 'bearish' else '📊 中性')
    msg = f"【题材匹配】{sentiment_emoji}\n"
    msg += f"新闻：{news_title}\n"
    msg += f"匹配到{len(stocks)}只相关股票：\n"
    for s in stocks[:10]:  # 最多推10只
        themes_str = '+'.join(s['matched_themes'][:3])
        msg += f"  {s['code']} {s['name']} | {themes_str}\n"
    return msg


if __name__ == '__main__':
    # 测试
    test_news = "AI服务器PCB需求爆发，光模块订单大增"
    stocks, sentiment = match_news_to_stocks(test_news)
    print(f"新闻：{test_news}")
    print(f"情绪：{sentiment}")
    print(f"匹配到{len(stocks)}只股票：")
    for s in stocks[:10]:
        print(f"  {s['code']} {s['name']} - {s['matched_themes']}")
