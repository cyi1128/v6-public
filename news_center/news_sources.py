# -*- coding: utf-8 -*-
"""
实时新闻中心 - 多源新闻接入与统一格式化模块
接入数据源（按优先级）：
  P0: 巨潮资讯API（上市公司官方公告）
  P1: AkShare财经新闻接口、同花顺7x24快讯
  P2: 东方财富财经要闻、新浪财经新闻（保留原有源）
所有来源统一映射为标准格式，支持并行拉取+异常降级。
"""

import sys
import os
import time
import re
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_center.news_config import (
    SOURCE_CONFIG, get_enabled_sources, get_source_info,
    PERFORMANCE_CONFIG, STANDARD_NEWS_FIELDS,
)


# ============================================================
# 工具函数
# ============================================================
def _gen_news_id(source_key: str, raw_id: str = '', title: str = '') -> str:
    """生成新闻唯一ID：来源前缀 + 原始ID或标题哈希"""
    if raw_id:
        return f"{source_key}_{raw_id}"
    # 无原始ID时用标题哈希
    title_hash = hashlib.md5(title.strip().encode('utf-8')).hexdigest()[:12]
    return f"{source_key}_{title_hash}"


def _normalize_time(time_str) -> str:
    """统一时间格式为 YYYY-MM-DD HH:MM:SS（精确到秒）
    支持：数字/字符串时间戳（自动判断秒/毫秒）、多种日期时间字符串、纯日期（补当前时间）
    无法解析时返回当前时间，年份不在2020-2030范围内视为异常
    """
    now = datetime.now()
    if not time_str:
        return now.strftime('%Y-%m-%d %H:%M:%S')

    # 1. 处理数字时间戳（int/float）
    if isinstance(time_str, (int, float)):
        try:
            ts = float(time_str)
            # 自动判断秒/毫秒：>1e12 视为毫秒
            if ts > 1e12:
                ts = ts / 1000.0
            dt = datetime.fromtimestamp(ts)
            # 纯日期零点（00:00）：保留真实日期，不补全当前时间
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                # 零点时间：如果是未来日期，减1秒变为前一天23:59:59
                if dt > now:
                    dt = dt - timedelta(seconds=1)
                result = dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                result = dt.strftime('%Y-%m-%d %H:%M:%S')
            return _validate_time(result, dt)
        except Exception:
            pass

    # 2. 处理字符串
    time_str = str(time_str).strip()
    if not time_str:
        return now.strftime('%Y-%m-%d %H:%M:%S')

    # 2a. 字符串数字时间戳（如 '1788951422'）
    try:
        ts = float(time_str)
        if ts > 1e12:
            ts = ts / 1000.0
        dt = datetime.fromtimestamp(ts)
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            if dt > now:
                dt = dt - timedelta(seconds=1)
            result = dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            result = dt.strftime('%Y-%m-%d %H:%M:%S')
        return _validate_time(result, dt)
    except (ValueError, OverflowError, OSError):
        pass

    # 2b. 纯日期格式（无时间部分）：保留真实日期，不补全当前时间
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日'):
        try:
            dt = datetime.strptime(time_str, fmt)
            # 纯日期补当天23:59:59，避免零点排序问题
            dt = dt.replace(hour=23, minute=59, second=59)
            result = dt.strftime('%Y-%m-%d %H:%M:%S')
            return _validate_time(result, dt)
        except Exception:
            continue

    # 2c. 带时间的日期格式
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S',
                '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
                '%Y-%m-%d %H:%M:%S.%f', '%Y年%m月%d日 %H:%M:%S',
                '%Y年%m月%d日 %H:%M'):
        try:
            dt = datetime.strptime(time_str, fmt)
            result = dt.strftime('%Y-%m-%d %H:%M:%S')
            return _validate_time(result, dt)
        except Exception:
            continue

    # 2d. 纯时间格式（如 '18:27:03'、'18:27'），拼接当天日期
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            t = datetime.strptime(time_str, fmt)
            dt = now.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
            result = dt.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[时间校准] 纯时间'{time_str}'拼接当天日期为 {result}", flush=True)
            return _validate_time(result, dt)
        except Exception:
            continue

    # 3. 全部失败返回当前时间
    print(f"[时间校准] 无法解析时间值 '{time_str}'，使用当前时间替代", flush=True)
    return now.strftime('%Y-%m-%d %H:%M:%S')


def _validate_time(time_str: str, dt=None) -> str:
    """时间合理性校验
    - 年份不在2020-2030范围内 -> 用当前时间替代
    - 时间超出 2020-01-01 至 当前+1天 -> 用当前时间替代
    异常时打印警告日志
    """
    now = datetime.now()
    try:
        if dt is None:
            try:
                dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
        # 年份范围校验
        if dt.year < 2020 or dt.year > 2030:
            print(f"[时间校验] 年份异常 {dt.year}（{time_str}），用当前时间替代", flush=True)
            return now.strftime('%Y-%m-%d %H:%M:%S')
        # 时间范围校验：不早于2020-01-01，不晚于当前+1天
        min_dt = datetime(2020, 1, 1)
        max_dt = now + timedelta(days=1)
        if dt < min_dt or dt > max_dt:
            print(f"[时间校验] 时间超出合理范围 {time_str}，用当前时间替代", flush=True)
            return now.strftime('%Y-%m-%d %H:%M:%S')
        return time_str
    except Exception:
        print(f"[时间校验] 时间格式异常 '{time_str}'，用当前时间替代", flush=True)
        return now.strftime('%Y-%m-%d %H:%M:%S')


def _classify_news(text: str) -> str:
    """新闻业务分类（与现有NewsService保持一致）"""
    if any(k in text for k in ['涨停', '大涨', '利好', '业绩增长', '订单', '中标', '增持', '回购']):
        return '利好'
    if any(k in text for k in ['跌停', '大跌', '利空', '亏损', '处罚', '退市', '减持', '调查']):
        return '利空'
    if any(k in text for k in ['公告', '披露', '发布', '重组', '并购', '年报', '季报', '半年报']):
        return '公司公告'
    if any(k in text for k in ['资金', '流入', '主力', '大单', '北向', '融资']):
        return '资金'
    if any(k in text for k in ['行业', '产业', '政策', '监管', '规划', '板块']):
        return '行业'
    if any(k in text for k in ['国际', '美股', '美联储', '全球', '欧洲', '原油', '黄金']):
        return '国际'
    if any(k in text for k in ['风险', '警示', '异常', '退市风险', '违规']):
        return '风险'
    return '热门'


def _calc_hot_score(source_key: str, stocks: List, pub_time: str) -> int:
    """计算热度值（来源权重+股票关联度+时间新鲜度）"""
    info = get_source_info(source_key)
    score = 50
    score += info.get('authority', 50) // 5  # 权威度折算
    score += len(stocks) * 8
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
    return min(score, 100)


# ============================================================
# 股票名称→代码映射（模块级缓存，只加载一次）
# ============================================================
_STOCK_NAME_MAP_CACHE = None
_STOCK_NAME_MAP_LOAD_FAILED = False


def _load_stock_name_map() -> Dict[str, str]:
    """加载股票名称→代码映射表（模块级缓存，只加载一次）
    优先从 data/stock_names_cache.json 加载（已为名称→代码格式），
    失败则从 data/stock_names_full.json 加载（代码→名称，需反转）。
    返回空dict表示加载失败，调用方应回退到正则匹配。
    """
    global _STOCK_NAME_MAP_CACHE, _STOCK_NAME_MAP_LOAD_FAILED
    if _STOCK_NAME_MAP_CACHE is not None:
        return _STOCK_NAME_MAP_CACHE
    if _STOCK_NAME_MAP_LOAD_FAILED:
        return {}

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(project_root, 'data', 'stock_names_cache.json'),
        os.path.join(project_root, 'data', 'stock_names_full.json'),
    ]
    name_map = {}
    for path_c in candidates:
        if not os.path.exists(path_c):
            continue
        try:
            with open(path_c, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                # stock_names_cache.json: {"stock_names": {"名称": "代码", ...}}
                if 'stock_names' in d and isinstance(d['stock_names'], dict):
                    for name, code in d['stock_names'].items():
                        if name and isinstance(code, str) and len(code) >= 6:
                            name_map[name.strip()] = code.strip()[-6:]
                else:
                    # stock_names_full.json: {"代码": "名称", ...} → 反转
                    for code, name in d.items():
                        if isinstance(name, str) and name.strip():
                            c = str(code).strip()
                            if len(c) >= 6 and c[-6:].isdigit():
                                name_map[name.strip()] = c[-6:]
            if name_map:
                print(f"[新闻股票识别] 名称映射加载成功: {len(name_map)}条 ({os.path.basename(path_c)})", flush=True)
                break
        except Exception as e:
            print(f"[新闻股票识别] 加载名称映射失败 {path_c}: {e}", flush=True)
            continue

    if not name_map:
        _STOCK_NAME_MAP_LOAD_FAILED = True
        print("[新闻股票识别] 所有名称映射文件均加载失败，回退到6位数字正则匹配", flush=True)
    _STOCK_NAME_MAP_CACHE = name_map
    return name_map


def _extract_stock_codes(text: str) -> List[Dict]:
    """从文本中提取股票代码（6位数字 + 股票名称映射匹配）
    1. 保留原有的6位数字正则匹配
    2. 新增：使用股票名称映射表匹配（从data/stock_names_cache.json加载）
    3. 匹配结果去重，最多返回5个关联股票代码
    """
    stocks = []
    seen_codes = set()

    # 1. 6位数字正则匹配
    codes = re.findall(r'\b(\d{6})\b', text)
    for code in codes:
        if code.startswith(('60', '00', '30', '68', '8', '4')) and code not in seen_codes:
            stocks.append({'code': code, 'name': ''})
            seen_codes.add(code)

    # 2. 股票名称映射匹配
    name_map = _load_stock_name_map()
    if name_map:
        for name, code in name_map.items():
            if code in seen_codes:
                continue
            # 名称长度>=2才匹配，避免单字误匹配
            if len(name) >= 2 and name in text:
                stocks.append({'code': code, 'name': name})
                seen_codes.add(code)
                if len(stocks) >= 5:
                    break

    return stocks[:5]


def _build_standard_news(source_key: str, title: str, content: str,
                          pub_time, url: str = '', raw_id: str = '',
                          news_type: str = '', stocks: List = None) -> Dict:
    """构建标准格式新闻条目"""
    info = get_source_info(source_key)
    nid = _gen_news_id(source_key, raw_id, title)
    ptime = _normalize_time(pub_time)
    stock_list = stocks if stocks is not None else _extract_stock_codes(title + ' ' + content)
    category = _classify_news(title + ' ' + content)
    hot = _calc_hot_score(source_key, stock_list, ptime)

    return {
        'news_id': nid,
        'title': title.strip(),
        'content': content.strip() if content else '',
        'publish_time': ptime,
        'source': info.get('name', source_key),
        'source_tag': info.get('tag', source_key),
        'news_type': news_type or info.get('news_type', '资讯'),
        'category': category,
        'stock_codes': stock_list,
        'hot_score': hot,
        'url': url or '',
        'is_new': False,
        'multi_source': False,
        'extra_sources': [],
    }


# ============================================================
# 各数据源抓取器
# ============================================================
class BaseSourceFetcher:
    """数据源抓取器基类"""
    source_key = ''

    def fetch(self, limit: int = 50) -> List[Dict]:
        raise NotImplementedError

    def _safe_fetch(self, limit: int) -> List[Dict]:
        """带异常捕获的安全抓取"""
        try:
            result = self.fetch(limit)
            return result or []
        except Exception as e:
            print(f"[新闻源:{self.source_key}] 抓取失败: {e}", flush=True)
            return []


class JuchaoFetcher(BaseSourceFetcher):
    """巨潮资讯 - 上市公司官方公告（P0）"""
    source_key = 'juchao'

    def fetch(self, limit: int = 50) -> List[Dict]:
        import requests
        news = []
        url = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search',
        }
        data = {
            'pageNum': '1',
            'pageSize': str(min(limit, 50)),
            'column': 'szse',
            'tabName': 'fulltext',
            'plate': '',
            'stock': '',
            'searchkey': '',
            'secid': '',
            'category': '',
            'trade': '',
            'seDate': '',
            'sortName': '',
            'sortType': '',
            'isHLtitle': 'true',
        }
        try:
            resp = requests.post(url, data=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                announcements = result.get('announcements', [])
                for ann in announcements[:limit]:
                    title = ann.get('announcementTitle', '').replace('<em>', '').replace('</em>', '')
                    sec_name = ann.get('secName', '')
                    sec_code = ann.get('secCode', '')
                    content = f"{sec_name}({sec_code})发布公告：{title}"
                    # announcementTime 是毫秒级时间戳，但通常为当天零点（00:00:00）
                    # 巨潮公告时间戳常为次日零点（如盘后公告时间戳=次日00:00:00），
                    # 需调整为前一天23:59:59，避免次日零点时间排在实时新闻前面
                    pub_time = ann.get('announcementTime', '')
                    try:
                        if isinstance(pub_time, (int, float)) and pub_time > 0:
                            _ts = float(pub_time)
                            if _ts > 1e12:
                                _ts /= 1000.0
                            from datetime import datetime as _dt, timedelta as _td
                            _dt_obj = _dt.fromtimestamp(_ts)
                            # 如果是零点时间，减1秒变为前一天23:59:59
                            if _dt_obj.hour == 0 and _dt_obj.minute == 0 and _dt_obj.second == 0:
                                _dt_obj = _dt_obj - _td(hours=9)
                                pub_time = _dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                                print(f"[巨潮] 零点时间戳调整为: {pub_time}", flush=True)
                    except Exception as _te:
                        print(f"[巨潮] 时间调整异常: {_te}", flush=True)
                    # 同时检查是否有其他时间字段
                    if not pub_time:
                        pub_time = ann.get('announcementDate', ann.get('publishTime', ''))
                    print(f"[巨潮] 原始时间字段 announcementTime={repr(pub_time)} (type={type(pub_time).__name__})", flush=True)
                    ann_id = str(ann.get('announcementId', ''))
                    adj_url = ann.get('adjunctUrl', '')
                    link = f'http://static.cninfo.com.cn/{adj_url}' if adj_url else ''
                    stocks = [{'code': sec_code, 'name': sec_name}] if sec_code else []
                    news.append(_build_standard_news(
                        'juchao', title, content, pub_time, link,
                        raw_id=ann_id, news_type='公告', stocks=stocks
                    ))
        except Exception as e:
            print(f"[巨潮资讯] 请求异常: {e}", flush=True)
        return news


class AkShareFetcher(BaseSourceFetcher):
    """AkShare财经新闻接口（P1）- 财联社电报"""
    source_key = 'akshare'

    def fetch(self, limit: int = 50) -> List[Dict]:
        news = []
        try:
            import akshare as ak
            # 财联社电报
            try:
                df = ak.stock_info_global_cls(symbol="全部")
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        title = str(row.get('标题', row.get('title', ''))).strip()
                        content = str(row.get('内容', row.get('content', ''))).strip()
                        pub_time = str(row.get('发布时间', row.get('datetime', ''))).strip()
                        raw_id = str(row.get('id', ''))
                        if title or content:
                            news.append(_build_standard_news(
                                'akshare', title or content[:40], content, pub_time,
                                raw_id=raw_id, news_type='资讯'
                            ))
            except Exception as e1:
                print(f"[AkShare] 财联社电报失败: {e1}", flush=True)

            # 备用：东方财富全球财经快讯
            if not news:
                try:
                    df2 = ak.stock_info_global_em()
                    if df2 is not None and not df2.empty:
                        for _, row in df2.head(limit).iterrows():
                            title = str(row.get('标题', '')).strip()
                            content = str(row.get('内容', '')).strip()
                            pub_time = str(row.get('发布时间', '')).strip()
                            if title or content:
                                news.append(_build_standard_news(
                                    'akshare', title or content[:40], content, pub_time,
                                    raw_id='', news_type='资讯'
                                ))
                except Exception as e2:
                    print(f"[AkShare] 东财快讯失败: {e2}", flush=True)
        except ImportError:
            print("[AkShare] akshare未安装，跳过此源", flush=True)
        except Exception as e:
            print(f"[AkShare] 异常: {e}", flush=True)
        return news


class THSFetcher(BaseSourceFetcher):
    """同花顺7x24快讯（P1）"""
    source_key = 'ths'

    def fetch(self, limit: int = 50) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://news.10jqka.com.cn/tapp/news/push/stock/'
            params = {
                'page': '1',
                'tag': '',
                'track': 'website',
                'pagesize': str(min(limit, 50)),
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://news.10jqka.com.cn/',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('data', {}).get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('digest', item.get('content', ''))).strip()
                    # ctime 是字符串类型的秒级时间戳，如 '1788951422'
                    pub_time = item.get('ctime', item.get('publish_time', ''))
                    print(f"[同花顺] 原始时间 ctime={repr(pub_time)} (type={type(pub_time).__name__})", flush=True)
                    raw_id = str(item.get('id', ''))
                    link = item.get('url', item.get('app_url', ''))
                    if title:
                        news.append(_build_standard_news(
                            'ths', title, content, pub_time, link,
                            raw_id=raw_id, news_type='资讯'
                        ))
        except Exception as e:
            print(f"[同花顺] 请求异常: {e}", flush=True)
        return news


class EastMoneyFetcher(BaseSourceFetcher):
    """东方财富财经要闻（P2）"""
    source_key = 'eastmoney'

    def fetch(self, limit: int = 50) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web',
                'biz': 'web_news_col',
                'column': '350',
                'order': '1',
                'needInteractData': '0',
                'page_index': '1',
                'page_size': str(min(limit, 50)),
                'req_trace': str(int(time.time() * 1000)),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if not data or not isinstance(data, dict):
                    print("[东方财富] 返回数据为空或格式错误，跳过", flush=True)
                    return news
                # data 字段可能为 None（API错误时）
                resp_data = data.get('data')
                if not resp_data or not isinstance(resp_data, dict):
                    print(f"[东方财富] data字段为空: code={data.get('code')}, msg={data.get('message')}", flush=True)
                    return news
                items = resp_data.get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('summary', item.get('digest', ''))).strip()
                    # 注意：字段名是驼峰 showTime，不是小写 showtime
                    pub_time = item.get('showTime', item.get('post_time', item.get('showtime', '')))
                    print(f"[东方财富] 原始时间 showTime={repr(pub_time)} (type={type(pub_time).__name__})", flush=True)
                    raw_id = str(item.get('code', item.get('id', item.get('art_code', ''))))
                    link = item.get('uniqueUrl', item.get('url', ''))
                    if title:
                        news.append(_build_standard_news(
                            'eastmoney', title, content, pub_time, link,
                            raw_id=raw_id, news_type='行业'
                        ))
        except Exception as e:
            print(f"[东方财富] 请求异常: {e}", flush=True)
        return news




class EastMoneyMacroFetcher(BaseSourceFetcher):
    """东方财富 - 宏观经济 column=352"""
    source_key = 'em_macro'

    def fetch(self, limit: int = 30) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web', 'biz': 'web_news_col', 'column': '352',
                'order': '1', 'needInteractData': '0', 'page_index': '1',
                'page_size': str(min(limit, 30)), 'req_trace': str(int(time.time() * 1000)),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('summary', item.get('digest', ''))).strip()
                    pub_time = item.get('showTime', '')
                    raw_id = str(item.get('code', item.get('id', '')))
                    link = item.get('uniqueUrl', '')
                    if title:
                        news.append(_build_standard_news(
                            'em_macro', title, content, pub_time, link,
                            raw_id=raw_id, news_type='宏观'
                        ))
        except Exception as e:
            print(f"[东财宏观] 请求异常: {e}", flush=True)
        return news


class EastMoneyGlobalFetcher(BaseSourceFetcher):
    """东方财富 - 国际财经 column=351"""
    source_key = 'em_global'

    def fetch(self, limit: int = 30) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web', 'biz': 'web_news_col', 'column': '351',
                'order': '1', 'needInteractData': '0', 'page_index': '1',
                'page_size': str(min(limit, 30)), 'req_trace': str(int(time.time() * 1000)),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('summary', item.get('digest', ''))).strip()
                    pub_time = item.get('showTime', '')
                    raw_id = str(item.get('code', item.get('id', '')))
                    link = item.get('uniqueUrl', '')
                    if title:
                        news.append(_build_standard_news(
                            'em_global', title, content, pub_time, link,
                            raw_id=raw_id, news_type='国际'
                        ))
        except Exception as e:
            print(f"[东财国际] 请求异常: {e}", flush=True)
        return news


class EastMoneyMarketFetcher(BaseSourceFetcher):
    """东方财富 - A股市场 column=353"""
    source_key = 'em_market'

    def fetch(self, limit: int = 30) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web', 'biz': 'web_news_col', 'column': '353',
                'order': '1', 'needInteractData': '0', 'page_index': '1',
                'page_size': str(min(limit, 30)), 'req_trace': str(int(time.time() * 1000)),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('summary', item.get('digest', ''))).strip()
                    pub_time = item.get('showTime', '')
                    raw_id = str(item.get('code', item.get('id', '')))
                    link = item.get('uniqueUrl', '')
                    if title:
                        news.append(_build_standard_news(
                            'em_market', title, content, pub_time, link,
                            raw_id=raw_id, news_type='市场'
                        ))
        except Exception as e:
            print(f"[东财市场] 请求异常: {e}", flush=True)
        return news


class EastMoneyCommodityFetcher(BaseSourceFetcher):
    """东方财富 - 大宗商品 column=356"""
    source_key = 'em_commodity'

    def fetch(self, limit: int = 30) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
            params = {
                'client': 'web', 'biz': 'web_news_col', 'column': '356',
                'order': '1', 'needInteractData': '0', 'page_index': '1',
                'page_size': str(min(limit, 30)), 'req_trace': str(int(time.time() * 1000)),
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get('data') or {}).get('list', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('summary', item.get('digest', ''))).strip()
                    pub_time = item.get('showTime', '')
                    raw_id = str(item.get('code', item.get('id', '')))
                    link = item.get('uniqueUrl', '')
                    if title:
                        news.append(_build_standard_news(
                            'em_commodity', title, content, pub_time, link,
                            raw_id=raw_id, news_type='大宗'
                        ))
        except Exception as e:
            print(f"[东财大宗] 请求异常: {e}", flush=True)
        return news

class SinaFetcher(BaseSourceFetcher):
    """新浪财经新闻（P2）- 保留原有源"""
    source_key = 'sina'

    def fetch(self, limit: int = 50) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://feed.mix.sina.com.cn/api/roll/get'
            params = {
                'pageid': '153', 'lid': '2516', 'k': '',
                'num': str(min(limit, 50)), 'page': 1,
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('result', {}).get('data', [])
                for item in items[:limit]:
                    title = str(item.get('title', '')).strip()
                    content = str(item.get('intro', item.get('summary', ''))).strip()
                    # ctime 是字符串类型的秒级时间戳
                    pub_time = item.get('ctime', item.get('create_time', ''))
                    print(f"[新浪] 原始时间 ctime={repr(pub_time)} (type={type(pub_time).__name__})", flush=True)
                    raw_id = str(item.get('oid', item.get('id', '')))
                    link = item.get('url', '')
                    if title:
                        news.append(_build_standard_news(
                            'sina', title, content, pub_time, link,
                            raw_id=raw_id, news_type='资讯'
                        ))
        except Exception as e:
            print(f"[新浪财经] 请求异常: {e}", flush=True)
        return news


class Sina7x24Fetcher(BaseSourceFetcher):
    """新浪7x24实时新闻（P2）"""
    source_key = 'sina_7x24'

    def fetch(self, limit: int = 50) -> List[Dict]:
        import requests
        news = []
        try:
            url = 'https://zhibo.sina.com.cn/api/zhibo/feed'
            params = {
                'page': 1, 'page_size': str(min(limit, 100)),
                'zhibo_id': 152, 'tag_id': 0, 'dire': 'f', 'dpc': 1,
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code != 200:
                return news
            data = resp.json()
            feed_list = data.get('result', {}).get('data', {}).get('feed', {}).get('list', [])
            for item in feed_list[:limit]:
                if not item or not isinstance(item, dict):
                    continue
                rich_text = item.get('rich_text', '')
                if not rich_text:
                    continue
                clean_text = re.sub(r'<[^>]+>', '', rich_text).strip()
                title_match = re.match(r'^(.{10,60}?[。！？])', clean_text)
                title = title_match.group(1) if title_match else clean_text[:50]
                # create_time 是标准格式字符串 '2026-09-09 18:57:07'
                pub_time = item.get('create_time', item.get('publish_time', ''))
                print(f"[新浪7x24] 原始时间 create_time={repr(pub_time)} (type={type(pub_time).__name__})", flush=True)
                raw_id = str(item.get('id', ''))
                link = 'https://finance.sina.com.cn/7x24/'
                news.append(_build_standard_news(
                    'sina_7x24', title, clean_text, pub_time, link,
                    raw_id=raw_id, news_type='资讯'
                ))
        except Exception as e:
            print(f"[新浪7x24] 请求异常: {e}", flush=True)
        return news


# ============================================================
# 数据源注册表
# ============================================================
FETCHER_REGISTRY = {
    'juchao': JuchaoFetcher,
    'akshare': AkShareFetcher,
    'ths': THSFetcher,
    'eastmoney': EastMoneyFetcher,
    'em_macro': EastMoneyMacroFetcher,
    'em_global': EastMoneyGlobalFetcher,
    'em_market': EastMoneyMarketFetcher,
    'em_commodity': EastMoneyCommodityFetcher,
    'sina': SinaFetcher,
    'sina_7x24': Sina7x24Fetcher,
}


# ============================================================
# 多源聚合管理器（并行拉取 + 异常降级）
# ============================================================
class MultiSourceNewsManager:
    """
    多源新闻聚合管理器
    - 并行拉取多个数据源
    - 单源失败自动跳过，连续失败3次临时降级
    - 降级后下一轮自动重试恢复
    """

    def __init__(self):
        self._fetchers = {}
        self._fail_count = {}       # 各源连续失败次数
        self._cooldown = {}         # 各源冷却轮数
        self._news_cache = []       # 新闻池缓存（供search使用）
        self._news_cache_time = 0.0
        self._init_fetchers()

    def _init_fetchers(self):
        for key in get_enabled_sources():
            cls = FETCHER_REGISTRY.get(key)
            if cls:
                self._fetchers[key] = cls()
                self._fail_count[key] = 0
                self._cooldown[key] = 0

    def _fetch_one(self, source_key: str, limit: int) -> Tuple[str, List[Dict]]:
        """拉取单个数据源（带降级判断）"""
        # 冷却期跳过
        if self._cooldown.get(source_key, 0) > 0:
            self._cooldown[source_key] -= 1
            # 冷却结束，重置失败计数，允许重试
            if self._cooldown[source_key] == 0:
                self._fail_count[source_key] = 0
                print(f"[新闻源:{source_key}] 冷却结束，恢复拉取", flush=True)
            return source_key, []

        fetcher = self._fetchers.get(source_key)
        if not fetcher:
            return source_key, []

        info = get_source_info(source_key)
        timeout = info.get('timeout', 10)
        result = fetcher._safe_fetch(limit)

        if result:
            self._fail_count[source_key] = 0
            print(f"[新闻源:{source_key}] 成功获取 {len(result)} 条", flush=True)
        else:
            self._fail_count[source_key] = self._fail_count.get(source_key, 0) + 1
            threshold = PERFORMANCE_CONFIG.get('source_fail_threshold', 3)
            if self._fail_count[source_key] >= threshold:
                self._cooldown[source_key] = PERFORMANCE_CONFIG.get('source_cooldown_rounds', 1)
                print(f"[新闻源:{source_key}] 连续失败{self._fail_count[source_key]}次，临时降级停用", flush=True)
        return source_key, result

    def fetch_all(self, limit: int = 50) -> List[Dict]:
        """
        并行拉取所有启用的数据源，合并结果。
        单次全量刷新目标<=2秒（并行拉取）。
        """
        all_news = []
        enabled = [k for k in get_enabled_sources() if k in self._fetchers]
        if not enabled:
            return all_news

        workers = min(PERFORMANCE_CONFIG.get('parallel_fetch_workers', 5), len(enabled))
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._fetch_one, key, limit): key
                for key in enabled
            }
            for future in as_completed(futures, timeout=PERFORMANCE_CONFIG.get('max_refresh_duration_sec', 2) + 3):
                try:
                    source_key, news_list = future.result()
                    all_news.extend(news_list)
                except Exception as e:
                    key = futures.get(future, 'unknown')
                    print(f"[新闻源:{key}] 并行任务异常: {e}", flush=True)

        elapsed = time.time() - start_time
        print(f"[多源聚合] 完成: {len(all_news)}条，耗时{elapsed:.2f}秒，源数{len(enabled)}", flush=True)

        # 批量00:00可疑值检测：如果超过30%的新闻时间为00:00，打印警告
        zero_count = sum(1 for n in all_news if n.get('publish_time', '').endswith('00:00:00') or n.get('publish_time', '').endswith('00:00'))
        if all_news and zero_count / len(all_news) > 0.3:
            print(f"[时间校验警告] {zero_count}/{len(all_news)} 条新闻时间为00:00，可能存在字段映射错误", flush=True)

        # 按发布时间倒序：先尝试解析为datetime确保正确排序，解析失败的排最后
        def _sort_key(item):
            pt = item.get('publish_time', '')
            try:
                try:
                    return datetime.strptime(pt, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return datetime.strptime(pt, '%Y-%m-%d %H:%M')
            except Exception:
                return datetime(2000, 1, 1)
        all_news.sort(key=_sort_key, reverse=True)

        # 缓存新闻池供search使用
        self._news_cache = all_news
        self._news_cache_time = time.time()

        return all_news

    def get_source_status(self) -> Dict[str, Dict]:
        """获取各数据源状态（用于调试/监控）"""
        status = {}
        for key in get_enabled_sources():
            status[key] = {
                'name': get_source_info(key).get('name', key),
                'fail_count': self._fail_count.get(key, 0),
                'cooldown': self._cooldown.get(key, 0),
                'enabled': key in self._fetchers,
            }
        return status

    def search_news(self, keyword: str, limit: int = 50) -> List[Dict]:
        """
        新闻搜索：在已拉取的新闻池中按关键词过滤（增强版）
        匹配范围：标题(title)、正文(content/summary)、来源(source/source_tag)、
                 关联股票代码(stock_codes[].code)、关联股票名称(stock_codes[].name)、
                 所属行业(industry/sector/industry_name)
        股票代码智能匹配：支持 002395 和 sz002395 两种格式（去除前缀后匹配6位代码）
        股票名称匹配：从 stock_names_cache.json 查找对应代码后匹配 stock_codes 字段
        模糊匹配：关键词部分匹配即可（如"央行"匹配"央行开展逆回购"）
        排序：标题匹配优先，其次按发布时间倒序
        """
        if not keyword or not keyword.strip():
            return []

        kw_raw = keyword.strip()
        kw_lower = kw_raw.lower()

        # ===== 股票代码智能匹配：提取纯6位代码 =====
        search_codes = set()       # 需要匹配的纯6位股票代码集合
        stock_name_lookup = ''     # 如果输入是股票名称，记录原始名称

        # 1. 带前缀的股票代码（sz002395 / sh600000 / bj430047）
        m_prefix = re.match(r'^(sz|sh|bj)(\d{6})$', kw_lower)
        if m_prefix:
            search_codes.add(m_prefix.group(2))
        # 2. 纯6位数字
        elif re.match(r'^\d{6}$', kw_raw):
            search_codes.add(kw_raw)
        # 3. 可能是股票名称（2-4个中文字），从缓存查找代码
        elif re.match(r'^[\u4e00-\u9fa5]{2,4}$', kw_raw):
            try:
                _cache_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'data', 'stock_names_cache.json'
                )
                if os.path.exists(_cache_path):
                    with open(_cache_path, 'r', encoding='utf-8') as _f:
                        _cache_data = json.load(_f)
                    _stock_names = _cache_data.get('stock_names', {})
                    if kw_raw in _stock_names:
                        _found_code = str(_stock_names[kw_raw]).zfill(6)
                        search_codes.add(_found_code)
                        stock_name_lookup = kw_raw
                        print(f"[新闻搜索] 股票名称'{kw_raw}'匹配到代码{_found_code}", flush=True)
            except Exception as _e:
                print(f"[新闻搜索] 股票名称查找失败: {_e}", flush=True)

        # 使用缓存的新闻池，缓存超过5分钟则重新拉取
        now = time.time()
        if not self._news_cache or (now - self._news_cache_time > 300):
            try:
                self.fetch_all(limit=200)
            except Exception as e:
                print(f"[新闻搜索] 拉取新闻池失败: {e}", flush=True)

        pool = self._news_cache
        if not pool:
            return []

        def _normalize_code(code_str):
            """将股票代码规范化为纯6位数字（去除sz/sh/bj前缀，补零）"""
            if not code_str:
                return ''
            s = str(code_str).strip().lower()
            s = re.sub(r'^(sz|sh|bj)', '', s)
            if s.isdigit():
                return s.zfill(6)
            return s

        title_matched = []
        content_matched = []

        for item in pool:
            matched = False
            is_title_match = False

            # ===== 文本字段：标题 / 内容 / 来源 / 行业 =====
            title_text = str(item.get('title', ''))
            content_text = str(item.get('content', item.get('summary', '')))
            source_text = str(item.get('source', '')) + ' ' + str(item.get('source_tag', ''))

            # 行业字段（industry / sector / industry_name，支持列表和字符串）
            industry_text = ''
            for _ind_field in ['industry', 'sector', 'industry_name']:
                _iv = item.get(_ind_field)
                if _iv:
                    if isinstance(_iv, list):
                        industry_text += ' ' + ' '.join(str(x) for x in _iv)
                    else:
                        industry_text += ' ' + str(_iv)

            full_text = (title_text + ' ' + content_text + ' ' + source_text + ' ' + industry_text).lower()

            # 普通关键词模糊匹配（部分匹配即可）
            if kw_lower in full_text:
                matched = True
                if kw_lower in title_text.lower():
                    is_title_match = True

            # ===== 股票代码匹配（规范化后比对） =====
            if search_codes:
                item_codes = set()
                stock_codes = item.get('stock_codes', [])
                for sc in stock_codes:
                    if isinstance(sc, dict):
                        _c = _normalize_code(sc.get('code', ''))
                        if _c:
                            item_codes.add(_c)
                    else:
                        _c = _normalize_code(sc)
                        if _c:
                            item_codes.add(_c)
                # 从标题和内容中提取6位数字代码（0/3/6开头）
                for _mc in re.findall(r'(?<!\d)([036][0-9]{5})(?!\d)', title_text + ' ' + content_text):
                    item_codes.add(_mc)

                if search_codes & item_codes:
                    matched = True
                    for _sc in search_codes:
                        if _sc in title_text:
                            is_title_match = True
                            break

            # ===== 股票名称匹配（输入为股票名称时，在标题/内容中匹配名称） =====
            if stock_name_lookup and stock_name_lookup in (title_text + content_text):
                matched = True
                if stock_name_lookup in title_text:
                    is_title_match = True

            if matched:
                if is_title_match:
                    title_matched.append(item)
                else:
                    content_matched.append(item)

        # 排序：标题匹配组优先，组内按发布时间倒序
        def _sort_key(item):
            pt = item.get('publish_time', '')
            try:
                try:
                    return datetime.strptime(pt, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return datetime.strptime(pt, '%Y-%m-%d %H:%M')
            except Exception:
                return datetime(2000, 1, 1)

        title_matched.sort(key=_sort_key, reverse=True)
        content_matched.sort(key=_sort_key, reverse=True)
        matched = title_matched + content_matched

        print(f"[新闻搜索] 关键词'{keyword}'匹配到 {len(matched)} 条（标题匹配{len(title_matched)}条，内容匹配{len(content_matched)}条）", flush=True)
        return matched[:limit]

# ============================================================
# 单例
# ============================================================
_manager_instance = None

def get_multi_source_manager() -> MultiSourceNewsManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MultiSourceNewsManager()
    return _manager_instance
