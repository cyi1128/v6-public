# -*- coding: utf-8 -*-
"""
任务二：政策与事件驱动匹配
数据来源：AkShare财经新闻 + 行业政策接口（不可用时用现有数据源或接口抽象层）
匹配逻辑：自动抓取当日国家级/行业级重要政策新闻，匹配持仓/信号股所属行业，标注利好/利空
在个股推送中追加政策催化字段
输出格式：📰政策催化：商务部发布消费提振政策 零售板块直接受益 该股为区域龙头
"""
import os
import sys
import time
import logging
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import POLICY_MATCHER_CONFIG, GENERAL_CONFIG, DATA_SOURCE_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[政策匹配] {msg}", flush=True)


class PolicyMatcher:
    """政策与事件驱动匹配器"""

    def __init__(self):
        self.config = POLICY_MATCHER_CONFIG
        self._policy_cache: List[Dict] = []
        self._last_fetch = 0
        self._akshare_available = self._check_akshare()

    def _check_akshare(self) -> bool:
        """检查AkShare是否可用"""
        try:
            import akshare
            return True
        except ImportError:
            _log("AkShare不可用，将使用备用数据源", 'WARN')
            return False

    def fetch_policies(self, force_refresh: bool = False) -> List[Dict]:
        """
        抓取当日重要政策新闻
        Returns: [{title, content, industry, sentiment, source, time}]
        sentiment: positive(利好) / negative(利空) / neutral
        """
        if not self.config.get('enabled', False):
            return []

        cache_hours = self.config.get('cache_hours', 6)
        now = time.time()
        if not force_refresh and self._policy_cache and (now - self._last_fetch) < cache_hours * 3600:
            return self._policy_cache

        start_time = time.time()
        policies = []

        try:
            if self._akshare_available:
                policies = self._fetch_from_akshare()
            else:
                policies = self._fetch_from_eastmoney()

            self._policy_cache = policies
            self._last_fetch = now

            elapsed = time.time() - start_time
            if GENERAL_CONFIG.get('log_performance', True):
                _log(f"抓取{len(policies)}条政策新闻 耗时{elapsed:.2f}s")

            return policies

        except Exception as e:
            _log(f"政策新闻抓取异常: {e}", 'ERROR')
            return self._policy_cache

    def _fetch_from_akshare(self) -> List[Dict]:
        """从AkShare抓取政策新闻"""
        try:
            import akshare as ak
            # 财经新闻
            news_df = ak.news_cctv(date=time.strftime('%Y%m%d'))
            policies = []
            if news_df is not None and len(news_df) > 0:
                for _, row in news_df.head(20).iterrows():
                    title = str(row.get('title', ''))
                    content = str(row.get('content', ''))
                    industry = self._extract_industry(title + content)
                    sentiment = self._analyze_sentiment(title + content)
                    policies.append({
                        'title': title,
                        'content': content[:100],
                        'industry': industry,
                        'sentiment': sentiment,
                        'source': 'AkShare',
                        'time': time.strftime('%Y-%m-%d'),
                    })
            return policies
        except Exception as e:
            _log(f"AkShare抓取失败: {e}", 'WARN')
            return []

    def _fetch_from_eastmoney(self) -> List[Dict]:
        """从东方财富抓取政策新闻（备用数据源）"""
        timeout = self.config.get('timeout', 3)
        try:
            import requests
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web',
                'biz': 'web_news_col',
                'column': '350',
                'order': '1',
                'needInteractData': '0',
                'page_index': '1',
                'page_size': '20',
            }
            resp = requests.get(url, params=params, timeout=timeout)
            data = resp.json()
            policies = []
            if data.get('data') and data['data'].get('list'):
                for item in data['data']['list'][:15]:
                    title = item.get('title', '')
                    digest = item.get('digest', '')
                    industry = self._extract_industry(title + digest)
                    sentiment = self._analyze_sentiment(title + digest)
                    policies.append({
                        'title': title,
                        'content': digest[:100],
                        'industry': industry,
                        'sentiment': sentiment,
                        'source': '东方财富',
                        'time': item.get('showtime', ''),
                    })
            return policies
        except Exception as e:
            _log(f"东方财富抓取失败: {e}", 'WARN')
            return []

    def _extract_industry(self, text: str) -> str:
        """从政策文本中提取相关行业"""
        industry_keywords = {
            '消费': ['消费', '零售', '百货', '电商', '免税', '餐饮', '旅游'],
            '科技': ['科技', '芯片', '半导体', '人工智能', 'AI', '软件', '数字经济'],
            '新能源': ['新能源', '光伏', '锂电', '储能', '风电', '新能源车'],
            '医药': ['医药', '医疗', '创新药', '集采', '医保'],
            '房地产': ['房地产', '楼市', '住房', '保障房'],
            '金融': ['金融', '银行', '证券', '保险', '资本市场'],
            '基建': ['基建', '建筑', '水利', '交通', '铁路'],
            '军工': ['军工', '国防', '航天', '航空'],
            '农业': ['农业', '乡村振兴', '粮食', '种业'],
            '环保': ['环保', '碳中和', '碳达峰', '绿色'],
        }
        for industry, keywords in industry_keywords.items():
            for kw in keywords:
                if kw in text:
                    return industry
        return ''

    def _analyze_sentiment(self, text: str) -> str:
        """分析政策情绪（利好/利空/中性）"""
        positive_words = ['支持', '鼓励', '促进', '利好', '扶持', '补贴', '减税', '放宽', '推动', '发展']
        negative_words = ['限制', '禁止', '收紧', '利空', '处罚', '监管', '打压', '整顿', '风险']

        pos_count = sum(1 for w in positive_words if w in text)
        neg_count = sum(1 for w in negative_words if w in text)

        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        else:
            return 'neutral'

    def match_policy(self, industry: str, stock_name: str = '') -> Optional[Dict]:
        """
        匹配个股所属行业的政策
        Returns: {title, industry, sentiment, formatted_text} 或 None
        """
        if not self.config.get('enabled', False):
            return None

        policies = self.fetch_policies()
        if not policies:
            return None

        # 匹配相关行业政策
        matched = None
        for p in policies:
            p_industry = p.get('industry', '')
            if p_industry and (p_industry in industry or industry in p_industry):
                matched = p
                break

        if not matched:
            return None

        # 格式化输出
        sentiment_text = '直接受益' if matched['sentiment'] == 'positive' else \
                         '承压' if matched['sentiment'] == 'negative' else '影响中性'
        title_short = matched['title'][:30] if len(matched['title']) > 30 else matched['title']

        formatted = f"📰政策催化：{title_short} {matched.get('industry', '')}板块{sentiment_text}"
        if stock_name:
            formatted += f" 该股为{stock_name[:4]}"

        return {
            'title': matched['title'],
            'industry': matched.get('industry', ''),
            'sentiment': matched['sentiment'],
            'formatted_text': formatted,
        }


_matcher: Optional[PolicyMatcher] = None


def get_policy_matcher() -> PolicyMatcher:
    global _matcher
    if _matcher is None:
        _matcher = PolicyMatcher()
    return _matcher


def match_policy_for_stock(industry: str, stock_name: str = '') -> Optional[Dict]:
    return get_policy_matcher().match_policy(industry, stock_name)
