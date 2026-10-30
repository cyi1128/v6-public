# -*- coding: utf-8 -*-
"""
新闻管理器（兼容层）
内部使用 news_center.MultiSourceNewsManager，提供与旧版 news_engine 兼容的接口
- get_news(code, name): 获取个股相关新闻（增强版：专属拉取+全量池匹配）
- get_stock_news(code, name): 个股专属新闻拉取
- get_stock_announcements(code, name): 个股专属公告拉取
- search_news(keyword): 新闻搜索
- 数据格式兼容旧版：title, time, url, source, content
"""
import os
import sys
import re
import json
from typing import List, Dict, Optional
from datetime import datetime

# 确保项目根目录在路径中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class NewsManager:
    """
    新闻管理器（兼容层）
    内部使用 news_center.MultiSourceNewsManager
    """

    def __init__(self):
        try:
            from news_center import get_multi_source_manager
            self._manager = get_multi_source_manager()
            self._cache = []
            self._cache_time = None
            print("[news_engine兼容层] MultiSourceNewsManager初始化成功", flush=True)
        except Exception as e:
            print(f"[news_engine兼容层] MultiSourceNewsManager初始化失败: {e}", flush=True)
            self._manager = None
            self._cache = []
            self._cache_time = None

    # ============================================================
    # 工具方法
    # ============================================================
    def _clean_code(self, code: str) -> str:
        """标准化股票代码为6位数字"""
        clean_code = code
        for prefix in ['sh', 'sz', 'bj', 'SH', 'SZ', 'BJ']:
            if clean_code.startswith(prefix):
                clean_code = clean_code[len(prefix):]
                break
        return clean_code

    def _to_sina_symbol(self, code: str) -> str:
        """转换为新浪symbol格式"""
        return ('sh' if code.startswith(('6', '9')) else 'sz') + code

    @staticmethod
    def _sort_by_time(news_list: List[Dict]) -> List[Dict]:
        """按发布时间倒序排序"""
        def _key(item):
            pt = str(item.get('publish_time') or item.get('time', ''))
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
                try:
                    return datetime.strptime(pt, fmt)
                except Exception:
                    continue
            return datetime(2000, 1, 1)
        return sorted(news_list, key=_key, reverse=True)

    @staticmethod
    def _dedup_by_title(news_list: List[Dict]) -> List[Dict]:
        """按标题去重"""
        seen = set()
        result = []
        for item in news_list:
            title = item.get('title', '').strip()
            if title and title not in seen:
                seen.add(title)
                result.append(item)
        return result

    # ============================================================
    # 全量新闻（带缓存）
    # ============================================================
    def _fetch_all_news(self, limit: int = 100) -> List[Dict]:
        """获取全量新闻（带缓存，避免频繁请求）"""
        import time
        # 缓存5分钟
        if self._cache and self._cache_time and (time.time() - self._cache_time < 300):
            return self._cache

        if self._manager is None:
            return []

        try:
            news_list = self._manager.fetch_all(limit=limit)
            # 转换为兼容格式
            compatible = []
            for item in news_list:
                compatible.append(self._convert_format(item))
            self._cache = compatible
            self._cache_time = time.time()
            return compatible
        except Exception as e:
            print(f"[news_engine兼容层] 获取全量新闻失败: {e}", flush=True)
            return []

    def _convert_format(self, item: Dict) -> Dict:
        """将 news_center 格式转换为旧版兼容格式"""
        return {
            'title': item.get('title', ''),
            'time': item.get('publish_time', item.get('time', '')),
            'date': item.get('publish_time', item.get('date', '')),
            'url': item.get('url', ''),
            'source': item.get('source', ''),
            'content': item.get('content', item.get('summary', '')),
            'stock_codes': item.get('stock_codes', []),
            'stock_names': item.get('stock_names', []),
            'original': item,
        }

    # ============================================================
    # 个股专属新闻拉取（内部数据源）
    # ============================================================
    def _fetch_em_stock_news(self, code: str, name: str, limit: int) -> List[Dict]:
        """东方财富个股新闻搜索（JSONP API）"""
        import requests
        news = []
        try:
            keyword = name if name else code
            param = {
                "uid": "",
                "keyword": keyword,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": limit,
                        "preTag": "",
                        "postTag": ""
                    }
                }
            }
            url = 'https://search-api-web.eastmoney.com/search/jsonp'
            params = {
                'cb': 'jQuery',
                'param': json.dumps(param, ensure_ascii=False)
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://so.eastmoney.com/',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                match = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    articles = data.get('result', {}).get('cmsArticleWebOld', [])
                    if not isinstance(articles, list):
                        articles = []
                    for art in articles[:limit]:
                        title = art.get('title', '').replace('<em>', '').replace('</em>', '')
                        content = art.get('content', '').replace('<em>', '').replace('</em>', '')
                        pub_time = art.get('date', art.get('showTime', ''))
                        link = art.get('url', '')
                        media = art.get('mediaName', '东方财富')
                        if title:
                            news.append({
                                'title': title,
                                'content': content,
                                'publish_time': pub_time,
                                'source': media,
                                'source_tag': 'eastmoney',
                                'news_type': '资讯',
                                'category': '热门',
                                'stock_codes': [{'code': code, 'name': name}],
                                'hot_score': 60,
                                'url': link,
                                'is_new': False,
                            })
        except Exception as e:
            print(f"[个股新闻] 东方财富搜索失败: {e}", flush=True)
        return news

    def _fetch_sina_stock_news(self, code: str, name: str, limit: int) -> List[Dict]:
        """新浪个股新闻页面抓取"""
        import requests
        news = []
        try:
            symbol = self._to_sina_symbol(code)
            url = f'https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{symbol}.phtml'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                resp.encoding = 'gbk'
                html = resp.text
                # 解析新闻列表：链接 + 标题 + 日期
                items = re.findall(
                    r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>\s*<span[^>]*>([^<]+)</span>',
                    html
                )
                if not items:
                    items = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{4,})</a>', html)
                for item in items[:limit]:
                    if len(item) >= 3:
                        link, title, pub_time = item[0], item[1].strip(), item[2].strip()
                    elif len(item) == 2:
                        link, title = item[0], item[1].strip()
                        pub_time = ''
                    else:
                        continue
                    if title and len(title) > 4:
                        full_link = link if link.startswith('http') else f'https://vip.stock.finance.sina.com.cn{link}'
                        news.append({
                            'title': title,
                            'content': '',
                            'publish_time': pub_time,
                            'source': '新浪财经',
                            'source_tag': 'sina',
                            'news_type': '资讯',
                            'category': '热门',
                            'stock_codes': [{'code': code, 'name': name}],
                            'hot_score': 55,
                            'url': full_link,
                            'is_new': False,
                        })
        except Exception as e:
            print(f"[个股新闻] 新浪抓取失败: {e}", flush=True)
        return news

    def _fetch_cninfo_announcements(self, code: str, name: str, limit: int) -> List[Dict]:
        """巨潮资讯个股公告（POST接口）"""
        import requests
        news = []
        try:
            url = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': 'http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search',
            }
            data = {
                'pageNum': '1',
                'pageSize': str(min(limit, 30)),
                'column': 'szse',
                'tabName': 'fulltext',
                'plate': '',
                'stock': code,
                'searchkey': '',
                'secid': '',
                'category': '',
                'trade': '',
                'seDate': '',
                'sortName': '',
                'sortType': '',
                'isHLtitle': 'true',
            }
            resp = requests.post(url, data=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                if result is None:
                    print(f"[个股公告] 巨潮资讯返回None，stock={code}", flush=True)
                    return news
                announcements = result.get('announcements', [])
                if announcements is None:
                    announcements = []
                for ann in announcements[:limit]:
                    title = ann.get('announcementTitle', '').replace('<em>', '').replace('</em>', '')
                    sec_name = ann.get('secName', '')
                    sec_code = ann.get('secCode', '')
                    content = f"{sec_name}({sec_code})发布公告：{title}"
                    pub_time = ann.get('announcementTime', '')
                    ann_id = str(ann.get('announcementId', ''))
                    adj_url = ann.get('adjunctUrl', '')
                    link = f'http://static.cninfo.com.cn/{adj_url}' if adj_url else ''
                    stocks = [{'code': sec_code or code, 'name': sec_name or name}]
                    news.append({
                        'title': title,
                        'content': content,
                        'publish_time': pub_time,
                        'source': '巨潮资讯',
                        'source_tag': 'juchao',
                        'news_type': '公告',
                        'category': '公告',
                        'stock_codes': stocks,
                        'hot_score': 70,
                        'url': link,
                        'is_new': False,
                    })
        except Exception as e:
            print(f"[个股公告] 巨潮资讯失败: {e}", flush=True)
        return news

    def _fetch_em_announcements(self, code: str, name: str, limit: int) -> List[Dict]:
        """东方财富个股公告（JSONP API）"""
        import requests
        news = []
        try:
            url = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
            params = {
                'cb': 'jQuery',
                'sr': '-1',
                'page_size': str(limit),
                'page_index': '1',
                'ann_type': 'A',
                'client_source': 'web',
                'stock_list': code,
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://data.eastmoney.com/',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                match = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    items = data.get('data', {}).get('list', [])
                    for item in items[:limit]:
                        title = item.get('title', '').replace('<em>', '').replace('</em>', '')
                        pub_time = item.get('notice_date', item.get('display_time', ''))
                        art_code = item.get('art_code', '')
                        link = f'https://data.eastmoney.com/notices/detail/{code}/{art_code}.html' if art_code else ''
                        if title:
                            news.append({
                                'title': title,
                                'content': f"{name}({code})发布公告：{title}",
                                'publish_time': pub_time,
                                'source': '东方财富',
                                'source_tag': 'eastmoney',
                                'news_type': '公告',
                                'category': '公告',
                                'stock_codes': [{'code': code, 'name': name}],
                                'hot_score': 65,
                                'url': link,
                                'is_new': False,
                            })
        except Exception as e:
            print(f"[个股公告] 东方财富失败: {e}", flush=True)
        return news

    # ============================================================
    # 公开接口：个股专属新闻/公告
    # ============================================================
    def get_stock_news(self, code: str, name: str = '', limit: int = 20) -> List[Dict]:
        """
        个股专属新闻拉取
        优先调用东方财富个股新闻搜索，备用新浪个股新闻页面，最后全量新闻池增强匹配
        返回统一格式：title, url, source, publish_time, summary, stock_codes, category, sentiment, hot_score
        """
        print(f"[个股新闻] 拉取 {code} {name} 专属新闻", flush=True)
        clean_code = self._clean_code(code)
        if not clean_code:
            return []

        all_results = []

        # 1. 东方财富个股新闻搜索
        try:
            em_news = self._fetch_em_stock_news(clean_code, name, limit)
            all_results.extend(em_news)
            print(f"[个股新闻] 东方财富获取 {len(em_news)} 条", flush=True)
        except Exception as e:
            print(f"[个股新闻] 东方财富异常: {e}", flush=True)

        # 2. 新浪个股新闻（东财结果不足时补充）
        if len(all_results) < limit // 2:
            try:
                sina_news = self._fetch_sina_stock_news(clean_code, name, limit)
                all_results.extend(sina_news)
                print(f"[个股新闻] 新浪获取 {len(sina_news)} 条", flush=True)
            except Exception as e:
                print(f"[个股新闻] 新浪异常: {e}", flush=True)

        # 3. 全量新闻池增强匹配
        try:
            pool_news = self._fetch_all_news(limit=200)
            matched = []
            for item in pool_news:
                if self._match_stock_in_news(item, clean_code, name):
                    matched.append(item)
            all_results.extend(matched)
            print(f"[个股新闻] 全量池匹配 {len(matched)} 条", flush=True)
        except Exception as e:
            print(f"[个股新闻] 全量池匹配异常: {e}", flush=True)

        # 去重 + 排序
        deduped = self._dedup_by_title(all_results)
        deduped = self._sort_by_time(deduped)
        print(f"[个股新闻] 总计 {len(deduped)} 条（去重后）", flush=True)
        return deduped[:limit]

    def get_stock_announcements(self, code: str, name: str = '', limit: int = 20) -> List[Dict]:
        """
        个股专属公告拉取
        优先调用巨潮资讯个股公告接口，备用东方财富公告接口
        返回统一格式，category标注为"公告"
        """
        print(f"[个股公告] 拉取 {code} {name} 专属公告", flush=True)
        clean_code = self._clean_code(code)
        if not clean_code:
            return []

        all_results = []

        # 1. 巨潮资讯个股公告
        try:
            cn_ann = self._fetch_cninfo_announcements(clean_code, name, limit)
            all_results.extend(cn_ann)
            print(f"[个股公告] 巨潮资讯获取 {len(cn_ann)} 条", flush=True)
        except Exception as e:
            print(f"[个股公告] 巨潮资讯异常: {e}", flush=True)

        # 2. 东方财富个股公告（巨潮结果不足时补充）
        if len(all_results) < limit // 2:
            try:
                em_ann = self._fetch_em_announcements(clean_code, name, limit)
                all_results.extend(em_ann)
                print(f"[个股公告] 东方财富获取 {len(em_ann)} 条", flush=True)
            except Exception as e:
                print(f"[个股公告] 东方财富异常: {e}", flush=True)

        # 去重 + 排序
        deduped = self._dedup_by_title(all_results)
        deduped = self._sort_by_time(deduped)
        print(f"[个股公告] 总计 {len(deduped)} 条（去重后）", flush=True)
        return deduped[:limit]

    def _match_stock_in_news(self, item: Dict, clean_code: str, name: str) -> bool:
        """检查新闻条目是否匹配指定个股（增强匹配）"""
        stock_codes = item.get('stock_codes', [])
        stock_names = item.get('stock_names', [])
        title = item.get('title', '')
        content = item.get('content', '')

        # 检查stock_codes字段（dict列表或字符串列表）
        for sc in stock_codes:
            if isinstance(sc, dict):
                if sc.get('code') == clean_code:
                    return True
            elif str(sc) == clean_code:
                return True

        # 标题/内容包含代码
        if clean_code and clean_code in (title + content):
            return True

        # 标题/内容包含名称
        if name and name in (title + content):
            return True

        # stock_names匹配
        if name and name in stock_names:
            return True

        return False

    # ============================================================
    # 公开接口：get_news（增强版）
    # ============================================================
    def get_news(self, code: str, name: str, limit: int = 20) -> List[Dict]:
        """
        获取个股相关新闻（增强版）
        优先调用个股专属新闻+公告拉取，再补充全量新闻池匹配结果，合并去重后返回
        """
        print(f"[news_engine兼容层] 获取个股新闻(增强): {code} {name}", flush=True)

        clean_code = self._clean_code(code)
        all_results = []

        # 1. 个股专属新闻拉取
        try:
            stock_news = self.get_stock_news(clean_code, name, limit=limit)
            all_results.extend(stock_news)
        except Exception as e:
            print(f"[news_engine兼容层] 个股专属新闻拉取失败: {e}", flush=True)

        # 2. 个股专属公告拉取
        try:
            stock_ann = self.get_stock_announcements(clean_code, name, limit=limit)
            all_results.extend(stock_ann)
        except Exception as e:
            print(f"[news_engine兼容层] 个股专属公告拉取失败: {e}", flush=True)

        # 3. 全量新闻池匹配（补充）
        try:
            pool_news = self._fetch_all_news(limit=200)
            for item in pool_news:
                if self._match_stock_in_news(item, clean_code, name):
                    all_results.append(item)
        except Exception as e:
            print(f"[news_engine兼容层] 全量池匹配失败: {e}", flush=True)

        # 去重（按title+日期）
        seen = set()
        deduped = []
        for item in all_results:
            key = (item.get('title', '').strip(), str(item.get('publish_time', ''))[:10])
            if key[0] and key not in seen:
                seen.add(key)
                deduped.append(item)

        # 按时间倒序
        deduped = self._sort_by_time(deduped)
        print(f"[news_engine兼容层] 个股新闻总计 {len(deduped)} 条（去重后）", flush=True)
        return deduped[:limit]

    # ============================================================
    # 公开接口：全量新闻 / 搜索 / 缓存
    # ============================================================
    def get_all_news(self, limit: int = 50) -> List[Dict]:
        """获取全量新闻"""
        return self._fetch_all_news(limit=limit)[:limit]

    def search_news(self, keyword: str, limit: int = 50) -> List[Dict]:
        """
        新闻搜索：委托给 MultiSourceNewsManager.search_news()
        在已拉取的新闻池中按关键词过滤（标题/摘要/来源/关联股票）
        """
        if not keyword or not keyword.strip():
            return []
        if self._manager is None:
            # 降级：在本地缓存中搜索
            pool = self._fetch_all_news(limit=500)
            kw = keyword.strip().lower()
            matched = []
            for item in pool:
                text = ' '.join([
                    str(item.get('title', '')),
                    str(item.get('content', '')),
                    str(item.get('source', '')),
                ]).lower()
                stock_codes = item.get('stock_codes', [])
                for sc in stock_codes:
                    if isinstance(sc, dict):
                        text += ' ' + str(sc.get('code', '')) + ' ' + str(sc.get('name', ''))
                    else:
                        text += ' ' + str(sc)
                if kw in text:
                    matched.append(item)
            return self._sort_by_time(matched)[:limit]
        try:
            return self._manager.search_news(keyword, limit=limit)
        except Exception as e:
            print(f"[news_engine兼容层] 搜索失败: {e}", flush=True)
            return []

    def clear_cache(self):
        """清除缓存"""
        self._cache = []
        self._cache_time = None


# 单例
_manager_instance = None


def get_news_manager() -> NewsManager:
    """获取新闻管理器单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = NewsManager()
    return _manager_instance
