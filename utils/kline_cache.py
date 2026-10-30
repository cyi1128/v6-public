# -*- coding: utf-8 -*-
"""
K线缓存模块
缓存K线数据，避免重复API请求
"""
import time
from threading import Lock
from datetime import datetime


class KlineCache:
    """K线缓存管理器"""
    
    def __init__(self):
        self._cache = {}  # {code_period: {data, timestamp}}
        self._lock = Lock()
        
        # 缓存过期时间（秒）
        self._trading_day_expire = 30 * 60  # 交易日：30分钟
        self._non_trading_day_expire = 24 * 60 * 60  # 非交易日：24小时
        
        # 统计数据
        self._stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'api_requests': 0,
        }
    
    def _is_trading_day(self):
        """判断是否是交易日（简化版，只判断周一至周五）"""
        now = datetime.now()
        return now.weekday() < 5  # 周一=0, 周五=4
    
    def _get_expire_time(self):
        """获取缓存有效期"""
        if self._is_trading_day():
            return self._trading_day_expire
        else:
            return self._non_trading_day_expire
    
    def set_expire_time(self, seconds):
        """设置缓存过期时间"""
        self._trading_day_expire = seconds
    
    def _get_cache_key(self, code, period='day'):
        """获取缓存键"""
        return f"{code}_{period}"
    
    def get_stats(self):
        """获取缓存统计数据"""
        with self._lock:
            stats = self._stats.copy()
            if stats['total_requests'] > 0:
                stats['hit_rate'] = stats['cache_hits'] / stats['total_requests'] * 100
            else:
                stats['hit_rate'] = 0
            return stats
    
    def reset_stats(self):
        """重置统计数据"""
        with self._lock:
            self._stats = {
                'total_requests': 0,
                'cache_hits': 0,
                'api_requests': 0,
            }
    
    def print_stats(self):
        """打印缓存统计"""
        stats = self.get_stats()
        print(f"[K线缓存统计]")
        print(f"  总请求: {stats['total_requests']}")
        print(f"  缓存命中: {stats['cache_hits']}")
        print(f"  API请求: {stats['api_requests']}")
        print(f"  命中率: {stats['hit_rate']:.1f}%")
        print(f"  缓存大小: {self.size()}只")
    
    def get(self, code, count=None, period='day'):
        """获取缓存的K线数据
        
        Args:
            code: 股票代码
            count: 需要的K线数量，None表示不检查数量
            period: 周期（day/week/month等）
            
        Returns:
            dict: K线数据，过期或不存在返回None
        """
        key = self._get_cache_key(code, period)
        
        with self._lock:
            self._stats['total_requests'] += 1
            
            item = self._cache.get(key)
            if not item:
                return None
            
            # 检查是否过期
            expire_time = self._get_expire_time()
            if time.time() - item['timestamp'] > expire_time:
                del self._cache[key]
                return None
            
            # 检查K线数量是否足够
            data = item['data']
            if count is not None:
                close_len = len(data.get('close', []))
                if close_len < count:
                    # 缓存的K线数量不够，不能用
                    return None
            
            self._stats['cache_hits'] += 1
            return data
    
    def set(self, code, data, count=None, period='day'):
        """设置缓存的K线数据
        
        Args:
            code: 股票代码
            data: K线数据
            count: K线数量，None表示自动检测
            period: 周期（day/week/month等）
        """
        key = self._get_cache_key(code, period)
        
        with self._lock:
            self._stats['api_requests'] += 1
            
            # 简单的LRU：超过最大数量时删除最早的
            if len(self._cache) >= 5000:
                # 找最早的一个删除
                oldest_key = None
                oldest_time = float('inf')
                for k, v in self._cache.items():
                    if v['timestamp'] < oldest_time:
                        oldest_time = v['timestamp']
                        oldest_key = k
                if oldest_key:
                    del self._cache[oldest_key]
            
            self._cache[key] = {
                'data': data,
                'timestamp': time.time()
            }
    
    def size(self):
        """获取缓存大小"""
        with self._lock:
            return len(self._cache)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = {
                'total_requests': 0,
                'cache_hits': 0,
                'api_requests': 0,
            }


# 单例模式
_kline_cache = None


def get_kline_cache():
    """获取K线缓存单例"""
    global _kline_cache
    if _kline_cache is None:
        _kline_cache = KlineCache()
    return _kline_cache
