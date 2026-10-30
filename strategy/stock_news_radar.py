"""
股票消息雷达
AI自动筛选股票相关消息，判断利好/利空，分级显示
"""
from datetime import datetime
import requests


class StockNewsRadar:
    """股票消息雷达"""

    # 消息等级
    LEVEL_MAJOR_POSITIVE = '重大利好'
    LEVEL_NORMAL_POSITIVE = '普通利好'
    LEVEL_NEUTRAL = '中性'
    LEVEL_RISK = '风险提示'
    LEVEL_MAJOR_NEGATIVE = '重大利空'

    # 等级颜色
    LEVEL_COLORS = {
        LEVEL_MAJOR_POSITIVE: '#ff1744',   # 红色
        LEVEL_NORMAL_POSITIVE: '#00e676',  # 绿色
        LEVEL_NEUTRAL: '#8b949e',          # 灰色
        LEVEL_RISK: '#ffea00',             # 黄色
        LEVEL_MAJOR_NEGATIVE: '#757575',   # 黑色/深灰
    }

    # 利好关键词
    POSITIVE_KEYWORDS = {
        '重大利好': ['签订重大合同', '重大资产重组', '业绩预增', '超预期', '获得大单', '战略合作', '技术突破', '获批', '中标'],
        '普通利好': ['增长', '提升', '利好', '增持', '回购', '分红', '创新高', '订单', '合作'],
    }

    # 利空关键词
    NEGATIVE_KEYWORDS = {
        '重大利空': ['退市', '重大违法', '财务造假', '被立案', '巨亏', '暂停上市', '强制退市'],
        '风险提示': ['下降', '亏损', '减持', '处罚', '监管', '诉讼', '风险', '警示', '下滑'],
    }

    def __init__(self):
        pass

    def get_stock_news(self, ts_code, stock_name='', limit=20):
        """获取个股相关新闻"""
        news_list = []

        # 尝试东方财富个股新闻API
        try:
            url = 'https://search-api-web.eastmoney.com/search/jsonp'
            params = {
                'cb': 'jQuery',
                'param': f'{{"uid":"","keyword":"{stock_name or ts_code}","type":["cmsArticleWebOld"],"client":"web","clientType":"web","clientVersion":"curr","param":{{"cmsArticleWebOld":{{"searchScope":"default","sort":"default","pageIndex":1,"pageSize":{limit},"preTag":"","postTag":""}}}}}}',
            }
            resp = requests.get(url, params=params, timeout=8)
            text = resp.text

            # 简单解析
            import json
            import re
            json_str = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
            if json_str:
                data = json.loads(json_str.group(1))
                if data.get('result') and data['result'].get('cmsArticleWebOld'):
                    for item in data['result']['cmsArticleWebOld']:
                        news_list.append({
                            'title': item.get('title', '').replace('<em>', '').replace('</em>', ''),
                            'content': item.get('content', '').replace('<em>', '').replace('</em>', ''),
                            'time': item.get('date', ''),
                            'source': item.get('mediaName', ''),
                            'url': item.get('url', ''),
                        })
        except Exception:
            pass

        # 如果API失败，使用7×24快讯筛选
        if not news_list:
            news_list = self._filter_from_7x24(stock_name, ts_code)

        # 分析每条消息
        analyzed = []
        for news in news_list:
            level, impact = self._analyze_news(news.get('title', '') + news.get('content', ''))
            news['level'] = level
            news['impact'] = impact
            news['level_color'] = self.LEVEL_COLORS.get(level, '#8b949e')
            analyzed.append(news)

        return analyzed

    def _filter_from_7x24(self, stock_name, ts_code):
        """从7×24快讯中筛选相关消息"""
        try:
            url = 'https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=50&zhibo_id=152&tag_id=0&dire=f&dpc=1'
            resp = requests.get(url, timeout=8)
            data = resp.json()

            news_list = []
            if data.get('result') and data['result'].get('data') and data['result']['data'].get('feed'):
                for item in data['result']['data']['feed'].get('list', []):
                    content = item.get('rich_text', '')
                    if stock_name and stock_name in content:
                        news_list.append({
                            'title': content[:50],
                            'content': content,
                            'time': datetime.fromtimestamp(item.get('create_time', 0)).strftime('%Y-%m-%d %H:%M'),
                            'source': '新浪7×24',
                            'url': '',
                        })

            return news_list
        except Exception:
            return []

    def _analyze_news(self, text):
        """分析消息利好/利空"""
        if not text:
            return self.LEVEL_NEUTRAL, '中性消息'

        # 检查重大利好
        for kw in self.POSITIVE_KEYWORDS['重大利好']:
            if kw in text:
                return self.LEVEL_MAJOR_POSITIVE, f'包含关键词：{kw}'

        # 检查重大利空
        for kw in self.NEGATIVE_KEYWORDS['重大利空']:
            if kw in text:
                return self.LEVEL_MAJOR_NEGATIVE, f'包含关键词：{kw}'

        # 检查普通利好
        positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS['普通利好'] if kw in text)
        # 检查风险
        negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS['风险提示'] if kw in text)

        if positive_count >= 2 and negative_count == 0:
            return self.LEVEL_NORMAL_POSITIVE, f'多个利好关键词'
        elif positive_count > 0 and negative_count == 0:
            return self.LEVEL_NORMAL_POSITIVE, '偏利好'
        elif negative_count >= 2:
            return self.LEVEL_RISK, f'多个风险关键词'
        elif negative_count > 0:
            return self.LEVEL_RISK, '偏利空'
        else:
            return self.LEVEL_NEUTRAL, '中性消息'

    def get_news_summary(self, ts_code, stock_name=''):
        """获取消息汇总"""
        news_list = self.get_stock_news(ts_code, stock_name, limit=30)

        major_positive = sum(1 for n in news_list if n['level'] == self.LEVEL_MAJOR_POSITIVE)
        normal_positive = sum(1 for n in news_list if n['level'] == self.LEVEL_NORMAL_POSITIVE)
        risk = sum(1 for n in news_list if n['level'] == self.LEVEL_RISK)
        major_negative = sum(1 for n in news_list if n['level'] == self.LEVEL_MAJOR_NEGATIVE)

        # 综合判断
        if major_positive > 0 and major_negative == 0:
            overall = '消息面利好'
            color = '#ff1744'
        elif major_negative > 0:
            overall = '消息面利空'
            color = '#757575'
        elif normal_positive > risk:
            overall = '消息面偏暖'
            color = '#00e676'
        elif risk > normal_positive:
            overall = '消息面偏空'
            color = '#ffea00'
        else:
            overall = '消息面中性'
            color = '#8b949e'

        return {
            'overall': overall,
            'overall_color': color,
            'major_positive': major_positive,
            'normal_positive': normal_positive,
            'risk': risk,
            'major_negative': major_negative,
            'total': len(news_list),
            'news_list': news_list[:10],
        }
