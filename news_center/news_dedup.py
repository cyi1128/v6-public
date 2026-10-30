# -*- coding: utf-8 -*-
"""
实时新闻中心 - 多源智能去重体系
三层去重规则：
  第一层：精确去重（标题+发布时间精确匹配 / 官方公告ID）
  第二层：相似度去重（编辑距离算法，相似度≥85% + 关键词二次校验）
  第三层：事件级去重（同一事件多源报道合并，保留最早最权威来源）
策略：
  - 维护本地24小时已展示新闻缓存池
  - 重复新闻优先保留权威来源（巨潮 > 官方媒体 > 资讯平台）
"""

import sys
import os
import re
import time
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_center.news_config import (
    DEDUP_CONFIG, SOURCE_CONFIG, AUTHORITY_ORDER,
    REFRESH_CONFIG, NEWS_CACHE_DIR,
)


# ============================================================
# 工具函数
# ============================================================
def _edit_distance(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离（Levenshtein Distance）"""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _title_similarity(title1: str, title2: str) -> float:
    """计算标题相似度（基于编辑距离的归一化相似度）"""
    if not title1 or not title2:
        return 0.0
    t1 = title1.strip()
    t2 = title2.strip()
    if t1 == t2:
        return 1.0
    max_len = max(len(t1), len(t2))
    if max_len == 0:
        return 0.0
    distance = _edit_distance(t1, t2)
    return 1.0 - (distance / max_len)


def _extract_keywords(text: str) -> Set[str]:
    """提取内容核心关键词（主体+事件），用于二次校验"""
    if not text:
        return set()
    # 去除来源标签前缀
    clean = re.sub(r'^【[^】]+】', '', text)
    # 提取中文词组（2-4字）和数字代码
    keywords = set()
    # 股票代码
    codes = re.findall(r'\b(\d{6})\b', clean)
    keywords.update(codes)
    # 中文关键词：常见财经主体词
    entity_patterns = [
        r'([\u4e00-\u9fa5]{2,6}(?:公司|集团|股份|银行|证券|科技|药业|能源|汽车|电子))',
        r'(证监会|央行|国务院|发改委|工信部|财政部|商务部|国资委)',
        r'(涨停|跌停|重组|并购|退市|上市|增发|回购|减持|增持|分红|配股)',
        r'(CPI|PMI|GDP|LPR|MLF|社融|降息|加息|降准|加息)',
    ]
    for pattern in entity_patterns:
        matches = re.findall(pattern, clean)
        keywords.update(matches)
    return keywords


def _get_authority_score(source_name: str) -> int:
    """获取来源权威度评分"""
    for key, info in SOURCE_CONFIG.items():
        if info.get('name') == source_name or info.get('tag') == source_name:
            return info.get('authority', 50)
    return 50


def _parse_time(time_str: str) -> Optional[datetime]:
    """解析时间字符串"""
    if not time_str:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(time_str, fmt)
        except Exception:
            continue
    return None


# ============================================================
# 24小时已展示新闻缓存池
# ============================================================
class NewsDisplayCache:
    """
    本地24小时已展示新闻缓存池
    已展示过的新闻无论是否重复拉取，均不再重复插入列表
    """

    def __init__(self, ttl_hours: int = 24):
        self.ttl_hours = ttl_hours
        self._cache: OrderedDict[str, float] = OrderedDict()  # news_id -> timestamp
        self._title_time_keys: Set[str] = set()  # 标题+时间的复合key
        self._title_set: Set[str] = set()  # 纯标题集合（跨源去重）
        self._load_from_disk()

    def _cache_file(self) -> str:
        return os.path.join(NEWS_CACHE_DIR, 'display_cache.json')

    def _load_from_disk(self):
        """从磁盘加载缓存（进程重启后保留）"""
        try:
            import json
            path = self._cache_file()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                now = time.time()
                for nid, ts in data.get('ids', {}).items():
                    if now - ts < self.ttl_hours * 3600:
                        self._cache[nid] = ts
                self._title_time_keys = set(data.get('title_time', []))
                print(f"[去重缓存] 加载: {len(self._cache)}条已展示新闻", flush=True)
        except Exception as e:
            print(f"[去重缓存] 加载失败: {e}", flush=True)

    def save_to_disk(self):
        """保存缓存到磁盘"""
        try:
            import json
            self._cleanup()
            path = self._cache_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {
                'ids': dict(self._cache),
                'title_time': list(self._title_time_keys),
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[去重缓存] 保存失败: {e}", flush=True)

    def _cleanup(self):
        """清理过期缓存"""
        now = time.time()
        expired = [nid for nid, ts in self._cache.items() if now - ts >= self.ttl_hours * 3600]
        for nid in expired:
            del self._cache[nid]

    def is_displayed(self, news: Dict) -> bool:
        """检查新闻是否已展示过"""
        nid = news.get('news_id', '')
        if nid and nid in self._cache:
            return True
        title = news.get('title', '').strip()
        if not title:
            return False
        # 标题完全匹配（不管时间）——跨源同标题
        if title in self._title_set:
            return True
        # 标题相似度匹配（>=95%）
        for t in self._title_set:
            if abs(len(t) - len(title)) > 5:
                continue
            sim = _title_similarity(title, t)
            if sim >= 0.95:
                return True
        return False

    def mark_displayed(self, news: Dict):
        """标记新闻为已展示"""
        nid = news.get('news_id', '')
        if nid:
            self._cache[nid] = time.time()
        title = news.get('title', '').strip()
        ptime = news.get('publish_time', '')[:16]
        if title and ptime:
            self._title_time_keys.add(f"{title}|{ptime}")
        if title:
            self._title_set.add(title)

    def mark_batch_displayed(self, news_list: List[Dict]):
        """批量标记"""
        for n in news_list:
            self.mark_displayed(n)


# ============================================================
# 三层去重引擎
# ============================================================
class NewsDeduplicator:
    """
    智能去重引擎
    第一层：精确去重
    第二层：相似度去重（编辑距离≥85% + 关键词校验）
    第三层：事件级去重（同一事件多源报道合并）
    """

    def __init__(self):
        self.config = DEDUP_CONFIG
        self.display_cache = NewsDisplayCache(
            ttl_hours=REFRESH_CONFIG.get('cache_ttl_hours', 24)
        )

    def deduplicate(self, new_news: List[Dict],
                     existing_news: List[Dict] = None) -> List[Dict]:
        """
        对新拉取的新闻进行去重，返回去重后的新闻列表。
        existing_news: 当前列表中已有的新闻（用于跨批次去重）
        """
        if not new_news:
            return []

        existing = existing_news or []
        result = []
        seen_exact = set()      # 本批次内精确去重
        seen_titles = []        # 已保留的标题（用于相似度比对）

        # 预构建已有新闻的索引
        existing_ids = {n.get('news_id', '') for n in existing if n.get('news_id')}
        existing_title_time = {
            f"{n.get('title','').strip()}|{n.get('publish_time','')[:16]}"
            for n in existing
        }

        for news in new_news:
            # ---- 第零层：已展示缓存过滤 ----
            if self.display_cache.is_displayed(news):
                continue

            # ---- 第一层：精确去重 ----
            if self.config.get('enable_exact_dedup', True):
                if not self._pass_exact_dedup(news, seen_exact, existing_ids, existing_title_time):
                    continue

            # ---- 第二层：相似度去重 ----
            if self.config.get('enable_similarity_dedup', True):
                dup_idx = self._find_similar_duplicate(news, seen_titles, result, existing)
                if dup_idx is not None:
                    # 与已保留的新闻相似，保留权威来源
                    self._merge_duplicate(result, dup_idx, news)
                    continue

            # ---- 第三层：事件级去重 ----
            if self.config.get('enable_event_dedup', True):
                event_idx = self._find_event_duplicate(news, result)
                if event_idx is not None:
                    self._merge_event(result, event_idx, news)
                    continue

            # 通过所有去重层，保留
            seen_exact.add(news.get('news_id', ''))
            seen_titles.append(news.get('title', '').strip())
            result.append(news)

        return result

    def _pass_exact_dedup(self, news: Dict, seen_exact: Set,
                          existing_ids: Set, existing_title_time: Set) -> bool:
        """第一层：精确去重"""
        nid = news.get('news_id', '')
        # 新闻ID精确匹配
        if nid and (nid in seen_exact or nid in existing_ids):
            return False
        # 标题+发布时间精确匹配
        title = news.get('title', '').strip()
        ptime = news.get('publish_time', '')[:16]
        composite = f"{title}|{ptime}"
        if composite in existing_title_time:
            return False
        # 官方公告ID去重
        if nid and nid.startswith('juchao_') and nid in seen_exact:
            return False
        return True

    def _find_similar_duplicate(self, news: Dict, seen_titles: List[str],
                                 result: List[Dict], existing: List[Dict]) -> Optional[int]:
        """
        第二层：相似度去重
        返回result中重复新闻的索引，None表示不重复
        """
        threshold = self.config.get('similarity_threshold', 0.85)
        title = news.get('title', '').strip()
        if not title:
            return None

        news_keywords = _extract_keywords(title + ' ' + news.get('content', ''))

        # 与本批次已保留的新闻比对
        for i, kept in enumerate(result):
            kept_title = kept.get('title', '').strip()
            if not kept_title:
                continue
            sim = _title_similarity(title, kept_title)
            if sim >= threshold:
                # 关键词二次校验
                kept_keywords = _extract_keywords(kept.get('title', '') + ' ' + kept.get('content', ''))
                common = news_keywords & kept_keywords
                if len(common) >= self.config.get('keyword_match_min', 2):
                    return i
                # 如果相似度极高（≥95%），即使关键词少也判定重复
                if sim >= 0.95:
                    return i

        # 与已有新闻比对（只检查最近的100条，避免性能问题）
        for i, kept in enumerate(existing[:100]):
            kept_title = kept.get('title', '').strip()
            if not kept_title:
                continue
            sim = _title_similarity(title, kept_title)
            # 相似度>=95%直接判重（跨源同标题不同时间）
            if sim >= 0.95:
                kept_keywords = _extract_keywords(kept.get('title', '') + ' ' + kept.get('content', ''))
                common = news_keywords & kept_keywords
                if len(common) >= self.config.get('keyword_match_min', 1):
                    # 与已有新闻重复，标记为已展示并不插入
                    self.display_cache.mark_displayed(news)
                    return -1  # -1表示与existing重复，不插入
                if sim >= 0.95:
                    self.display_cache.mark_displayed(news)
                    return -1

        return None

    def _merge_duplicate(self, result: List[Dict], idx: int, news: Dict):
        """合并重复新闻：保留权威来源，标注多源报道"""
        if idx < 0 or idx >= len(result):
            return
        kept = result[idx]
        kept_authority = _get_authority_score(kept.get('source', ''))
        new_authority = _get_authority_score(news.get('source', ''))

        if new_authority > kept_authority:
            # 新来源更权威，替换但保留旧来源信息
            old_source = kept.get('source', '')
            news['multi_source'] = True
            if old_source and old_source not in news.get('extra_sources', []):
                news.setdefault('extra_sources', []).append(old_source)
            news['extra_sources'].extend(kept.get('extra_sources', []))
            result[idx] = news
        else:
            # 保留原有，添加多源标记
            kept['multi_source'] = True
            new_source = news.get('source', '')
            if new_source and new_source not in kept.get('extra_sources', []):
                kept.setdefault('extra_sources', []).append(new_source)

    def _find_event_duplicate(self, news: Dict, result: List[Dict]) -> Optional[int]:
        """
        第三层：事件级去重
        同一事件（同一家公司的同一公告、同一政策）被多源报道时合并
        """
        window_minutes = self.config.get('event_window_minutes', 30)
        news_time = _parse_time(news.get('publish_time', ''))
        news_stocks = {s.get('code', '') for s in news.get('stock_codes', []) if s.get('code')}
        news_keywords = _extract_keywords(news.get('title', ''))

        if not news_time:
            return None

        for i, kept in enumerate(result):
            kept_time = _parse_time(kept.get('publish_time', ''))
            if not kept_time:
                continue
            # 时间窗口内
            time_diff = abs((news_time - kept_time).total_seconds()) / 60
            if time_diff > window_minutes:
                continue

            kept_stocks = {s.get('code', '') for s in kept.get('stock_codes', []) if s.get('code')}
            kept_keywords = _extract_keywords(kept.get('title', ''))

            # 同一公司 + 关键词重叠 → 同一事件
            common_stocks = news_stocks & kept_stocks
            common_keywords = news_keywords & kept_keywords

            if common_stocks and len(common_keywords) >= 1:
                return i
            # 同一政策/宏观事件（无股票但关键词高度重叠）
            if not news_stocks and not kept_stocks and len(common_keywords) >= 3:
                return i

        return None

    def _merge_event(self, result: List[Dict], idx: int, news: Dict):
        """合并事件级重复：保留发布时间最早、来源最权威的内容"""
        if idx < 0 or idx >= len(result):
            return
        kept = result[idx]

        kept_time = _parse_time(kept.get('publish_time', ''))
        new_time = _parse_time(news.get('publish_time', ''))
        kept_authority = _get_authority_score(kept.get('source', ''))
        new_authority = _get_authority_score(news.get('source', ''))

        # 保留最早发布的；时间相同则保留更权威的
        should_replace = False
        if new_time and kept_time:
            if new_time < kept_time:
                should_replace = True
            elif new_time == kept_time and new_authority > kept_authority:
                should_replace = True
        elif new_authority > kept_authority:
            should_replace = True

        if should_replace:
            old_source = kept.get('source', '')
            news['multi_source'] = True
            if old_source and old_source not in news.get('extra_sources', []):
                news.setdefault('extra_sources', []).append(old_source)
            news['extra_sources'].extend(kept.get('extra_sources', []))
            result[idx] = news
        else:
            kept['multi_source'] = True
            new_source = news.get('source', '')
            if new_source and new_source not in kept.get('extra_sources', []):
                kept.setdefault('extra_sources', []).append(new_source)

    def mark_as_displayed(self, news_list: List[Dict]):
        """标记一批新闻为已展示（插入列表后调用）"""
        self.display_cache.mark_batch_displayed(news_list)
        self.display_cache.save_to_disk()

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            'cached_count': len(self.display_cache._cache),
            'title_time_count': len(self.display_cache._title_time_keys),
        }


# ============================================================
# 单例
# ============================================================
_dedup_instance = None

def get_deduplicator() -> NewsDeduplicator:
    global _dedup_instance
    if _dedup_instance is None:
        _dedup_instance = NewsDeduplicator()
    return _dedup_instance
