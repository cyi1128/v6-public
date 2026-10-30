"""
行情缓存模块
缓存实时行情数据，避免重复API请求
"""
import time
from threading import Lock


class MarketCache:
    """行情缓存管理器"""
    
    def __init__(self):
        self._cache = {}  # {code: {data, timestamp}}
        self._lock = Lock()
        self._expire_time = 10  # 缓存过期时间（秒）
    
    def set_expire_time(self, seconds):
        """设置缓存过期时间"""
        self._expire_time = seconds
    
    def get(self, code):
        """获取缓存的行情数据
        
        Args:
            code: 股票代码
            
        Returns:
            dict: 行情数据，过期或不存在返回None
        """
        with self._lock:
            item = self._cache.get(code)
            if not item:
                return None
            
            # 检查是否过期
            if time.time() - item['timestamp'] > self._expire_time:
                del self._cache[code]
                return None
            
            return item['data']
    
    def set(self, code, data):
        """设置缓存的行情数据
        
        Args:
            code: 股票代码
            data: 行情数据
        """
        with self._lock:
            self._cache[code] = {
                'data': data,
                'timestamp': time.time()
            }
    
    def set_batch(self, quotes_dict):
        """批量设置缓存
        
        Args:
            quotes_dict: {code: data} 字典
        """
        with self._lock:
            now = time.time()
            for code, data in quotes_dict.items():
                self._cache[code] = {
                    'data': data,
                    'timestamp': now
                }
    
    def get_batch(self, codes):
        """批量获取缓存
        
        Args:
            codes: 股票代码列表
            
        Returns:
            tuple: (cached_dict, missing_codes)
                cached_dict: 已缓存的 {code: data}
                missing_codes: 未缓存的代码列表
        """
        cached = {}
        missing = []
        now = time.time()
        
        with self._lock:
            for code in codes:
                item = self._cache.get(code)
                if item and now - item['timestamp'] <= self._expire_time:
                    cached[code] = item['data']
                else:
                    missing.append(code)
                    if code in self._cache:
                        del self._cache[code]
        
        return cached, missing
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def size(self):
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)
    
    def cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            now = time.time()
            expired_codes = [
                code for code, item in self._cache.items()
                if now - item['timestamp'] > self._expire_time
            ]
            for code in expired_codes:
                del self._cache[code]
            return len(expired_codes)


# 全局单例
_market_cache = None


def get_market_cache():
    """获取行情缓存单例"""
    global _market_cache
    if not _market_cache:
        _market_cache = MarketCache()
    return _market_cache
