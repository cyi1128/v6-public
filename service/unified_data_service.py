# -*- coding: utf-8 -*-
"""
V2.2 统一数据服务层
新闻服务、资金流向服务、板块数据服务
所有数据来自真实接口，无mock/fake/random数据。
"""

import sys
import os
import time
import re
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 新闻服务 - 整合新浪财经/东方财富/网易财经/同花顺
# ============================================================
class NewsService:
    """统一新闻服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = {}
        self._cache_time = {}
        self._stock_name_map = {}  # 股票名称→代码映射
        self._load_stock_names()

    def _load_stock_names(self):
        """加载股票名称映射用于新闻股票识别
        优化：只获取code/name列表，不获取全市场行情+财务信息（原get_full_market_quotes需3-5分钟）
        """
        try:
            from utils.tdx_stock_list import get_stock_list_tdx
            stocks = get_stock_list_tdx()  # 只返回code/name/market，<1秒
            if stocks:
                for s in stocks:
                    name = s.get('name', '')
                    code = s.get('code', '')
                    if name and code:
                        self._stock_name_map[name] = code
            print(f"[新闻服务] 股票名称映射加载: {len(self._stock_name_map)}只（优化版，仅code/name）", flush=True)
        except Exception as e:
            print(f"[新闻服务] 股票名称映射加载失败: {e}", flush=True)

    def get_news(self, source: str = 'all', limit: int = 50) -> List[Dict]:
        """
        获取新闻，统一格式返回。
        source: all/sina/eastmoney/163/ths
        返回: [{title, content, source, publish_time, url, hot_score, stocks, industry, concept, category}]
        """
        cache_key = f"{source}_{limit}"
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 60:
            return self._cache[cache_key]

        all_news = []

        # 新浪财经
        if source in ('all', 'sina'):
            try:
                sina_news = self._get_sina_news(limit)
                all_news.extend(sina_news)
            except Exception as e:
                print(f"[新闻服务] 新浪财经失败: {e}", flush=True)

        # 新浪7x24实时新闻（V2.4新增，优先使用）
        if source in ('all', 'sina', '7x24'):
            try:
                sina_7x24 = self._get_sina_7x24(limit)
                all_news.extend(sina_7x24)
            except Exception as e:
                print(f"[新闻服务] 新浪7x24失败: {e}", flush=True)

        # 东方财富
        if source in ('all', 'eastmoney'):
            try:
                em_news = self._get_eastmoney_news(limit)
                all_news.extend(em_news)
            except Exception as e:
                print(f"[新闻服务] 东方财富失败: {e}", flush=True)

        # 网易财经
        if source in ('all', '163'):
            try:
                wy_news = self._get_163_news(limit)
                all_news.extend(wy_news)
            except Exception as e:
                print(f"[新闻服务] 网易财经失败: {e}", flush=True)

        # 按时间排序
        all_news.sort(key=lambda x: x.get('publish_time', ''), reverse=True)
        result = all_news[:limit]

        self._cache[cache_key] = result
        self._cache_time[cache_key] = time.time()
        return result

    def _get_sina_news(self, limit: int = 30) -> List[Dict]:
        """新浪财经新闻"""
        news = []
        try:
            import requests
            url = 'https://feed.mix.sina.com.cn/api/roll/get'
            params = {
                'pageid': '153',
                'lid': '2516',
                'k': '',
                'num': limit,
                'page': 1,
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('result', {}).get('data', [])
                for item in items:
                    title = item.get('title', '')
                    content = item.get('intro', item.get('summary', ''))
                    pub_time = item.get('ctime', '')
                    if pub_time:
                        try:
                            pub_time = datetime.fromtimestamp(int(pub_time)).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            pass
                    url_link = item.get('url', '')
                    news.append(self._format_news(title, content, '新浪财经', pub_time, url_link))
        except Exception as e:
            print(f"[新闻服务] 新浪请求异常: {e}", flush=True)
        return news

    def _get_sina_7x24(self, limit: int = 100) -> List[Dict]:
        """新浪财经7×24小时实时新闻（V2.4新增）"""
        news = []
        try:
            import requests
            url = 'https://zhibo.sina.com.cn/api/zhibo/feed'
            params = {
                'page': 1, 'page_size': str(limit), 'zhibo_id': 152,
                'tag_id': 0, 'dire': 'f', 'dpc': 1,
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return news
            data = resp.json()
            feed_list = data.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
            if not feed_list:
                return news
            for item in feed_list:
                if not item or not isinstance(item, dict):
                    continue
                news_id = str(item.get('id', ''))
                rich_text = item.get('rich_text', '')
                if not rich_text:
                    continue
                # 提取标题（第一句或前50字）和正文
                import re as _re
                # 去掉HTML标签
                clean_text = _re.sub(r'<[^>]+>', '', rich_text).strip()
                # 标题：取第一句（。！？结尾）或前40字
                title_match = _re.match(r'^(.{10,60}?[。！？])', clean_text)
                title = title_match.group(1) if title_match else clean_text[:50]
                content = clean_text
                pub_time = item.get('create_time', '')
                if pub_time and isinstance(pub_time, (int, float)):
                    try:
                        pub_time = datetime.fromtimestamp(int(pub_time)).strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        pass
                url_link = f'https://finance.sina.com.cn/7x24/'
                formatted = self._format_news(title, content, '新浪7x24', pub_time, url_link)
                formatted['news_id'] = news_id
                formatted['category'] = '实时'
                news.append(formatted)
        except Exception as e:
            print(f"[新闻服务] 新浪7x24异常: {e}", flush=True)
        return news

    def _get_eastmoney_news(self, limit: int = 30) -> List[Dict]:
        """东方财富新闻"""
        news = []
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
                'page_size': str(limit),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if not data or not isinstance(data, dict):
                    return news
                items = data.get('data', {}).get('list', [])
                if not items:
                    return news
                for item in items:
                    if not item or not isinstance(item, dict):
                        continue
                    title = item.get('title', '')
                    content = item.get('digest', '')
                    pub_time = item.get('showtime', item.get('post_time', ''))
                    url_link = item.get('url', '')
                    news.append(self._format_news(title, content, '东方财富', pub_time, url_link))
        except Exception as e:
            print(f"[新闻服务] 东方财富请求异常: {e}", flush=True)
        return news

    def _get_163_news(self, limit: int = 30) -> List[Dict]:
        """网易财经新闻"""
        news = []
        try:
            import requests
            url = 'https://money.163.com/special/00259BVP/news_flow_index.js'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                # 解析JSONP
                match = re.search(r'data_callback\((.*)\)', text, re.DOTALL)
                if match:
                    import json
                    items = json.loads(match.group(1))
                    for item in items[:limit]:
                        title = item.get('title', '')
                        content = item.get('digest', '')
                        pub_time = item.get('ptime', '')
                        url_link = item.get('docurl', '')
                        news.append(self._format_news(title, content, '网易财经', pub_time, url_link))
        except Exception as e:
            print(f"[新闻服务] 网易请求异常: {e}", flush=True)
        return news

    def _format_news(self, title: str, content: str, source: str,
                      pub_time: str, url: str) -> Dict:
        """格式化新闻，自动识别股票和分类"""
        # 识别股票
        stocks = self._extract_stocks(title + ' ' + content)
        # 分类
        category = self._classify_news(title + ' ' + content)
        # 热度计算（基于来源权重+股票关联度+时间新鲜度）
        hot_score = self._calc_hot_score(source, stocks, pub_time)

        return {
            'title': title,
            'content': content,
            'source': source,
            'publish_time': pub_time,
            'url': url,
            'hot_score': hot_score,
            'stocks': stocks,
            'industry': [],
            'concept': [],
            'category': category,
        }

    def _extract_stocks(self, text: str) -> List[Dict]:
        """从新闻文本中识别股票"""
        stocks = []
        # 1. 识别股票代码（6位数字）
        codes = re.findall(r'\b(\d{6})\b', text)
        for code in codes:
            if code.startswith(('60', '00', '30', '68')):
                stocks.append({'code': code, 'name': ''})
        # 2. 识别股票名称
        for name, code in self._stock_name_map.items():
            if len(name) >= 2 and name in text:
                if not any(s['code'] == code for s in stocks):
                    stocks.append({'code': code, 'name': name})
        return stocks[:5]  # 最多识别5只

    def _classify_news(self, text: str) -> str:
        """新闻分类"""
        text_lower = text.lower()
        if any(k in text for k in ['涨停', '大涨', '利好', '业绩增长', '订单', '中标']):
            return '利好'
        if any(k in text for k in ['跌停', '大跌', '利空', '亏损', '处罚', '退市']):
            return '利空'
        if any(k in text for k in ['公告', '披露', '发布', '重组', '并购']):
            return '公司公告'
        if any(k in text for k in ['资金', '流入', '主力', '大单', '北向']):
            return '资金'
        if any(k in text for k in ['行业', '产业', '政策', '监管', '规划']):
            return '行业'
        if any(k in text for k in ['国际', '美股', '美联储', '全球', '欧洲']):
            return '国际'
        if any(k in text for k in ['风险', '警示', '异常', '调查']):
            return '风险'
        return '热门'

    def _calc_hot_score(self, source: str, stocks: List, pub_time: str) -> int:
        """计算新闻热度（真实字段计算，不伪造阅读量）"""
        score = 50
        # 来源权重
        source_weights = {'新浪财经': 15, '东方财富': 15, '网易财经': 10, '同花顺': 12}
        score += source_weights.get(source, 5)
        # 股票关联度
        score += len(stocks) * 8
        # 时间新鲜度（2小时内+20，6小时内+10，24小时内+5）
        try:
            if pub_time:
                pub_dt = datetime.strptime(pub_time, '%Y-%m-%d %H:%M')
                hours_ago = (datetime.now() - pub_dt).total_seconds() / 3600
                if hours_ago < 2:
                    score += 20
                elif hours_ago < 6:
                    score += 10
                elif hours_ago < 24:
                    score += 5
        except Exception:
            pass
        return min(100, score)


# ============================================================
# 资金流向服务
# ============================================================
# 东财源熔断状态（模块级）
_EM_FUND_FAIL_COUNT = 0
_EM_FUND_COOLDOWN_UNTIL = 0.0
_EM_FUND_FAIL_THRESHOLD = 3
_EM_FUND_COOLDOWN_SECONDS = 60
_EM_FUND_CB_LOGGED = False

class FundFlowService:
    """资金流向服务 - 板块资金/个股资金"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = {}
        self._cache_time = {}

    def get_sector_fund_flow(self, limit: int = 15) -> List[Dict]:
        """
        获取板块资金流入TOP。
        返回: [{name, net_inflow(亿), change_pct, up_count, down_count, limit_up_count, leader}]
        """
        cache_key = f'sector_fund_{limit}'
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 30:
            return self._cache[cache_key]

        global _EM_FUND_FAIL_COUNT, _EM_FUND_COOLDOWN_UNTIL, _EM_FUND_CB_LOGGED
        sectors = []
        now = time.time()
        # 熔断检查：冷却期内直接走新浪
        em_circuit_open = (_EM_FUND_COOLDOWN_UNTIL > 0 and now < _EM_FUND_COOLDOWN_UNTIL)
        if em_circuit_open:
            if not _EM_FUND_CB_LOGGED:
                print('[资金服务] 东财源熔断，直接使用新浪', flush=True)
                _EM_FUND_CB_LOGGED = True
        else:
            # 冷却期结束，重置熔断日志标记
            if _EM_FUND_COOLDOWN_UNTIL > 0 and now >= _EM_FUND_COOLDOWN_UNTIL:
                _EM_FUND_COOLDOWN_UNTIL = 0.0
                _EM_FUND_FAIL_COUNT = 0
                _EM_FUND_CB_LOGGED = False
            # 优先东方财富
            try:
                sectors = self._get_eastmoney_fund_flow(limit * 2)
                if sectors:
                    # 成功，重置失败计数
                    _EM_FUND_FAIL_COUNT = 0
                    _EM_FUND_CB_LOGGED = False
            except Exception as e:
                _EM_FUND_FAIL_COUNT += 1
                if _EM_FUND_FAIL_COUNT >= _EM_FUND_FAIL_THRESHOLD:
                    _EM_FUND_COOLDOWN_UNTIL = now + _EM_FUND_COOLDOWN_SECONDS
                    print(f'[资金服务] 东财源连续失败{_EM_FUND_FAIL_COUNT}次，触发熔断({_EM_FUND_COOLDOWN_SECONDS}s)', flush=True)
                else:
                    print(f'[资金服务] 东方财富失败({_EM_FUND_FAIL_COUNT}/{_EM_FUND_FAIL_THRESHOLD})，尝试新浪: {e}', flush=True)

        # 东方财富失败/熔断时用新浪板块行情备用
        if not sectors:
            try:
                sectors = self._get_sina_sector_data(limit * 2)
            except Exception as e:
                print(f"[资金服务] 新浪板块也失败: {e}", flush=True)

        # 按净流入排序取TOP
        sectors.sort(key=lambda x: x['net_inflow'] if x['net_inflow'] is not None else (x.get('turnover') or 0), reverse=True)
        result = sectors[:limit]

        self._cache[cache_key] = result
        self._cache_time[cache_key] = time.time()
        return result

    def _get_eastmoney_fund_flow(self, limit: int) -> List[Dict]:
        """东方财富板块资金流向（push2delay，eastmoney_request统一函数）"""
        from utils.http_market_data import eastmoney_request
        params = {
            'pn': '1', 'pz': str(limit), 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f62',
            'fs': 'm:90+t:2',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f104,f105,f128',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=10)
        if not data or not isinstance(data, dict):
            raise Exception('返回数据格式错误')
        items = data.get('data', {}).get('diff', [])
        if not items:
            raise Exception('无数据')
        sectors = []
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            name = item.get('f14', '')
            if not name:
                continue
            net_inflow = item.get('f62', 0) / 100000000 if item.get('f62') else 0
            change_pct = round(float(item.get('f3', 0) or 0), 2)
            up_count = item.get('f104', 0)
            down_count = item.get('f105', 0)
            limit_up = item.get('f128', 0)
            leader = item.get('f207', '')
            # 尝试从API返回数据中提取交易日期，否则用当前日期
            trade_date = ''
            try:
                # 东财clist接口可能在data中包含日期信息
                raw_date = data.get('data', {}).get('date', '') or data.get('data', {}).get('trade_date', '')
                if raw_date:
                    if isinstance(raw_date, (int, float)):
                        from datetime import datetime as _dt
                        trade_date = _dt.fromtimestamp(float(raw_date)).strftime('%Y-%m-%d')
                    else:
                        trade_date = str(raw_date)[:10]
            except Exception:
                pass
            if not trade_date:
                from datetime import datetime as _dt
                trade_date = _dt.now().strftime('%Y-%m-%d')
            sectors.append({
                'name': name, 'net_inflow': round(net_inflow, 2),
                'change_pct': change_pct, 'up_count': up_count,
                'down_count': down_count, 'limit_up_count': limit_up,
                'leader': leader, 'data_source': 'eastmoney',
                'trade_date': trade_date,
            })
        return sectors

    def _get_sina_sector_data(self, limit: int) -> List[Dict]:
        """新浪板块行情（备用数据源）"""
        sectors = []
        import requests
        url = 'https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise Exception(f'HTTP {resp.status_code}')
        text = resp.text
        # 解析 var S_Finance_bankuai_sinaindustry = {...}
        import re
        match = re.search(r'=\s*(\{.*\})', text, re.DOTALL)
        if not match:
            raise Exception('无法解析新浪板块数据')
        import json
        data = json.loads(match.group(1))
        for key, value in data.items():
            parts = value.split(',')
            if len(parts) < 13:
                continue
            # 0:代码 1:名称 2:股票数 3:均价 4:涨跌额 5:涨跌幅 6:成交量(手) 7:成交额(元) 8:龙头代码 9:龙头价 10:龙头涨跌额 11:龙头涨跌幅 12:龙头名称
            name = parts[1]
            change_pct = float(parts[5]) if parts[5] else 0
            amount = float(parts[7]) / 100000000 if parts[7] else 0  # 成交额(亿)
            leader = parts[12] if len(parts) > 12 else ''
            leader_code_raw = parts[8] if len(parts) > 8 else ''
            # 提取纯数字代码（sh600293 -> 600293）
            import re as _re
            leader_code_match = _re.search(r'(\d{6})', leader_code_raw)
            leader_code = leader_code_match.group(1) if leader_code_match else ''
            # 新浪无主力净流入，成交额存入turnover字段，net_inflow设为None
            # 新浪接口不返回日期，使用当前日期
            from datetime import datetime as _dt
            sina_trade_date = _dt.now().strftime('%Y-%m-%d')
            sectors.append({
                'name': name,
                'net_inflow': None,  # 新浪无主力净流入数据
                'turnover': round(amount, 2),  # 成交额(亿)
                'change_pct': round(change_pct, 2),
                'up_count': None, 'down_count': None,
                'limit_up_count': None,
                'leader': leader,
                'leader_code': leader_code,
                'data_source': 'sina_turnover',
                'trade_date': sina_trade_date,
            })
        sectors.sort(key=lambda x: x['change_pct'], reverse=True)
        return sectors[:limit]

    def get_sector_fund_outflow(self, limit: int = 15) -> List[Dict]:
        """获取板块资金流出TOP"""
        all_sectors = self.get_sector_fund_flow(limit=50)
        outflow = sorted(all_sectors, key=lambda x: x['net_inflow'] if x['net_inflow'] is not None else (x.get('turnover') or 0))
        return outflow[:limit]


# ============================================================
# 板块数据服务 - 热门题材/板块热点/板块异动
# ============================================================
class SectorDataService:
    """板块数据服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = {}
        self._cache_time = {}

    def get_hot_sectors(self, limit: int = 20) -> List[Dict]:
        """
        获取热门板块（按涨幅+涨停数+资金综合排序）。
        返回: [{name, change_pct, limit_up_count, up_count, down_count, net_inflow, leader, hot_score}]
        """
        cache_key = f'hot_sectors_{limit}'
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 20:
            return self._cache[cache_key]

        sectors = []
        # 优先东方财富
        try:
            sectors = self._get_eastmoney_hot_sectors(50)
        except Exception as e:
            print(f"[板块服务] 东方财富热门板块失败，尝试新浪: {e}", flush=True)

        # 东方财富失败时用新浪
        if not sectors:
            try:
                fund_service = get_fund_flow_service()
                sectors = fund_service._get_sina_sector_data(50)
                # 补充热度评分
                for s in sectors:
                    change_pct = s.get('change_pct', 0)
                    net_inflow = s.get('net_inflow', 0)
                    s['hot_score'] = round(min(100, change_pct * 5 + max(0, net_inflow) * 0.5), 1)
            except Exception as e:
                print(f"[板块服务] 新浪热门板块也失败: {e}", flush=True)

        # 按热度排序
        sectors.sort(key=lambda x: x.get('hot_score', 0), reverse=True)
        result = sectors[:limit]

        self._cache[cache_key] = result
        self._cache_time[cache_key] = time.time()
        return result

    def _get_eastmoney_hot_sectors(self, limit: int) -> List[Dict]:
        """东方财富热门板块（push2delay，eastmoney_request统一函数）"""
        from utils.http_market_data import eastmoney_request
        params = {
            'pn': '1', 'pz': str(limit), 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:90+t:2',
            'fields': 'f12,f14,f2,f3,f62,f104,f105,f128,f207',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=10)
        if not data or not isinstance(data, dict):
            raise Exception('返回数据格式错误')
        items = data.get('data', {}).get('diff', [])
        if not items:
            raise Exception('无数据')
        sectors = []
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            name = item.get('f14', '')
            if not name:
                continue
            change_pct = round(float(item.get('f3', 0) or 0), 2)
            net_inflow = item.get('f62', 0) / 100000000 if item.get('f62') else 0
            up_count = item.get('f104', 0)
            down_count = item.get('f105', 0)
            limit_up = item.get('f128', 0)
            leader = item.get('f207', '')
            hot_score = min(100, change_pct * 5 + limit_up * 10 + max(0, net_inflow) * 2)
            sectors.append({
                'name': name, 'change_pct': change_pct,
                'net_inflow': round(net_inflow, 2),
                'up_count': up_count, 'down_count': down_count,
                'limit_up_count': limit_up, 'leader': leader,
                'hot_score': round(hot_score, 1), 'data_source': 'eastmoney',
            })
        return sectors

    def get_hot_concepts(self, limit: int = 20) -> List[Dict]:
        """获取热门概念题材"""
        cache_key = f'hot_concepts_{limit}'
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 20:
            return self._cache[cache_key]

        concepts = []
        # 优先东方财富概念板块
        try:
            concepts = self._get_eastmoney_concepts(50)
        except Exception as e:
            print(f"[板块服务] 东方财富概念失败，用行业板块代替: {e}", flush=True)

        # 东方财富失败时用新浪行业板块代替
        if not concepts:
            try:
                fund_service = get_fund_flow_service()
                concepts = fund_service._get_sina_sector_data(50)
                for c in concepts:
                    c['hot_score'] = round(min(100, c.get('change_pct', 0) * 5 + max(0, c.get('net_inflow', 0)) * 0.5), 1)
            except Exception as e:
                print(f"[板块服务] 新浪概念也失败: {e}", flush=True)

        concepts.sort(key=lambda x: x.get('hot_score', 0), reverse=True)
        result = concepts[:limit]

        self._cache[cache_key] = result
        self._cache_time[cache_key] = time.time()
        return result

    def _get_eastmoney_concepts(self, limit: int) -> List[Dict]:
        """东方财富概念板块（push2delay，eastmoney_request统一函数）"""
        from utils.http_market_data import eastmoney_request
        params = {
            'pn': '1', 'pz': str(limit), 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:90+t:3',
            'fields': 'f12,f14,f2,f3,f62,f104,f105,f128,f207',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=10)
        if not data or not isinstance(data, dict):
            raise Exception('返回数据格式错误')
        items = data.get('data', {}).get('diff', [])
        if not items:
            raise Exception('无数据')
        concepts = []
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            name = item.get('f14', '')
            if not name:
                continue
            change_pct = round(float(item.get('f3', 0) or 0), 2)
            net_inflow = item.get('f62', 0) / 100000000 if item.get('f62') else 0
            up_count = item.get('f104', 0)
            down_count = item.get('f105', 0)
            limit_up = item.get('f128', 0)
            leader = item.get('f207', '')
            hot_score = min(100, change_pct * 5 + limit_up * 10 + max(0, net_inflow) * 2)
            concepts.append({
                'name': name, 'change_pct': change_pct,
                'net_inflow': round(net_inflow, 2),
                'up_count': up_count, 'down_count': down_count,
                'limit_up_count': limit_up, 'leader': leader,
                'hot_score': round(hot_score, 1), 'data_source': 'eastmoney',
            })
        return concepts

    def get_new_launch_sectors(self) -> List[Dict]:
        """
        获取新启动板块（10:00以后涨停数快速增加的板块）。
        核心条件：板块涨停数>=2，且涨幅同步扩大。
        """
        cache_key = 'new_launch'
        if cache_key in self._cache and time.time() - self._cache_time.get(cache_key, 0) < 15:
            return self._cache[cache_key]

        new_launches = []
        try:
            hot_sectors = self.get_hot_sectors(limit=50)
            for sector in hot_sectors:
                # 新启动条件：涨停>=2 + 涨幅>1% + 资金流入
                if (sector.get('limit_up_count', 0) >= 2 and
                    sector.get('change_pct', 0) > 1.0 and
                    sector.get('net_inflow', 0) > 0):
                    # 启动评分
                    launch_score = self._calc_launch_score(sector)
                    sector['launch_score'] = launch_score
                    if launch_score >= 60:
                        sector['launch_level'] = 'S级启动' if launch_score >= 80 else ('A级启动' if launch_score >= 70 else 'B级启动')
                    else:
                        sector['launch_level'] = '观察'
                    new_launches.append(sector)
        except Exception as e:
            print(f"[板块服务] 新启动板块失败: {e}", flush=True)

        new_launches.sort(key=lambda x: x.get('launch_score', 0), reverse=True)
        self._cache[cache_key] = new_launches
        self._cache_time[cache_key] = time.time()
        return new_launches

    def _calc_launch_score(self, sector: Dict) -> int:
        """计算板块启动评分0-100"""
        score = 0
        # 涨停数量25分
        lu = sector.get('limit_up_count', 0)
        score += min(25, lu * 8)
        # 涨停速度（简化：用涨幅代理）20分
        change = sector.get('change_pct', 0)
        score += min(20, max(0, change) * 4)
        # 资金净流入20分
        fund = sector.get('net_inflow', 0)
        score += min(20, max(0, fund) * 2)
        # 板块涨幅15分
        score += min(15, max(0, change) * 3)
        # 上涨家数占比10分
        up = sector.get('up_count', 0)
        down = sector.get('down_count', 0)
        total = up + down
        if total > 0:
            score += min(10, (up / total) * 10)
        # 龙头强度5分
        if sector.get('leader'):
            score += 5
        return min(100, int(score))

    def get_sector_stocks(self, sector_code: str, limit: int = 20) -> List[Dict]:
        """获取板块成分股（push2delay，eastmoney_request统一函数）"""
        stocks = []
        try:
            from utils.http_market_data import eastmoney_request
            params = {
                'pn': '1',
                'pz': str(limit),
                'po': '1',
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'fid': 'f3',
                'fs': f'b:{sector_code}',
                'fields': 'f12,f14,f2,f3,f62',
            }
            data = eastmoney_request('/api/qt/clist/get', params, timeout=10)
            if data:
                items = data.get('data', {}).get('diff', [])
                for item in items:
                    stocks.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0),
                        'change_pct': round(float(item.get('f3', 0) or 0), 2),
                        'net_inflow': item.get('f62', 0) / 100000000 if item.get('f62') else 0,
                    })
        except Exception as e:
            print(f"[板块服务] 板块成分股失败: {e}", flush=True)
        return stocks


# ============================================================
# 单例获取函数
# ============================================================
def get_news_service() -> NewsService:
    return NewsService()

def get_fund_flow_service() -> FundFlowService:
    return FundFlowService()

def get_sector_data_service() -> SectorDataService:
    return SectorDataService()
