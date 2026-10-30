# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.2 - 缓存管理器

三层缓存：
1. 行情缓存：当天不重复请求同一股票行情
2. K线缓存：同一股票同一周期只请求一次
3. 评分缓存：扫描期间保存已评分股票，避免重复计算
"""
import os
import json
import time
from typing import Dict, Optional, Any
from datetime import datetime


class CacheManager:
    """三层缓存管理器"""

    def __init__(self, cache_dir: str = "cache", ttl: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl  # 缓存有效期（秒），默认1小时
        os.makedirs(cache_dir, exist_ok=True)

        # 内存缓存
        self._quote_cache: Dict[str, Dict] = {}      # 行情缓存
        self._kline_cache: Dict[str, Any] = {}        # K线缓存
        self._score_cache: Dict[str, Dict] = {}        # 评分缓存
        self._cache_times: Dict[str, float] = {}       # 缓存时间戳

    # ============================================================
    # 行情缓存
    # ============================================================

    def get_quote(self, code: str, date: str = None) -> Optional[Dict]:
        """获取行情缓存"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        key = f"quote_{date}_{code}"
        if key in self._quote_cache:
            if time.time() - self._cache_times.get(key, 0) < self.ttl:
                return self._quote_cache[key]
        return None

    def set_quote(self, code: str, quote: Dict, date: str = None):
        """设置行情缓存"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        key = f"quote_{date}_{code}"
        self._quote_cache[key] = quote
        self._cache_times[key] = time.time()

    def get_quotes_batch(self, codes: list, date: str = None) -> Dict[str, Dict]:
        """批量获取行情缓存，返回命中的"""
        result = {}
        for code in codes:
            q = self.get_quote(code, date)
            if q is not None:
                result[code] = q
        return result

    def set_quotes_batch(self, quotes: Dict[str, Dict], date: str = None):
        """批量设置行情缓存"""
        for code, quote in quotes.items():
            self.set_quote(code, quote, date)

    # ============================================================
    # K线缓存
    # ============================================================

    def get_kline(self, code: str, days: int = 120, period: str = 'daily') -> Optional[Any]:
        """获取K线缓存"""
        key = f"kline_{period}_{days}_{code}"
        if key in self._kline_cache:
            if time.time() - self._cache_times.get(key, 0) < self.ttl:
                return self._kline_cache[key]
        return None

    def set_kline(self, code: str, kline_data: Any, days: int = 120, period: str = 'daily'):
        """设置K线缓存 - V1.2.1：不缓存空数据"""
        # 空数据防护：不缓存None或空列表
        if kline_data is None:
            return
        if isinstance(kline_data, (list, dict)) and len(kline_data) == 0:
            return
        key = f"kline_{period}_{days}_{code}"
        self._kline_cache[key] = kline_data
        self._cache_times[key] = time.time()

    # ============================================================
    # 评分缓存
    # ============================================================

    def get_score(self, code: str) -> Optional[Dict]:
        """获取评分缓存"""
        key = f"score_{code}"
        if key in self._score_cache:
            if time.time() - self._cache_times.get(key, 0) < self.ttl:
                return self._score_cache[key]
        return None

    def set_score(self, code: str, score_data: Dict):
        """设置评分缓存"""
        key = f"score_{code}"
        self._score_cache[key] = score_data
        self._cache_times[key] = time.time()

    # ============================================================
    # 缓存统计
    # ============================================================

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            'quote_cache_count': len(self._quote_cache),
            'kline_cache_count': len(self._kline_cache),
            'score_cache_count': len(self._score_cache),
            'total_cache_entries': len(self._cache_times),
        }

    def clear_expired(self):
        """清理过期缓存"""
        now = time.time()
        expired_keys = [k for k, t in self._cache_times.items() if now - t > self.ttl]
        for key in expired_keys:
            self._cache_times.pop(key, None)
            if key.startswith('quote_'):
                self._quote_cache.pop(key, None)
            elif key.startswith('kline_'):
                self._kline_cache.pop(key, None)
            elif key.startswith('score_'):
                self._score_cache.pop(key, None)
        return len(expired_keys)

    def clear_all(self):
        """清空所有缓存"""
        self._quote_cache.clear()
        self._kline_cache.clear()
        self._score_cache.clear()
        self._cache_times.clear()

    # ============================================================
    # 磁盘持久化
    # ============================================================

    def save_to_disk(self, filename: str = None):
        """保存缓存到磁盘（仅保存元数据统计，不保存大量K线数据）"""
        if filename is None:
            filename = os.path.join(self.cache_dir, f"force_scan_cache_{datetime.now().strftime('%Y%m%d')}.json")
        try:
            data = {
                'save_time': datetime.now().isoformat(),
                'stats': self.get_stats(),
                'quote_codes': list(self._quote_cache.keys())[:100],  # 只保存前100个key
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load_from_disk(self, filename: str = None) -> bool:
        """从磁盘加载缓存元数据"""
        if filename is None:
            filename = os.path.join(self.cache_dir, f"force_scan_cache_{datetime.now().strftime('%Y%m%d')}.json")
        if not os.path.exists(filename):
            return False
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 仅恢复统计信息，K线数据需要重新请求
            return True
        except Exception:
            return False


# ============================================================
# 便捷函数
# ============================================================

_default_cache = None

def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器单例"""
    global _default_cache
    if _default_cache is None:
        _default_cache = CacheManager()
    return _default_cache
