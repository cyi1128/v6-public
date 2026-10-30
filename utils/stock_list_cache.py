"""
股票列表缓存模块
缓存股票基础信息（代码、名称、市值、行业等），避免每次扫描重新获取
"""
import time
from threading import Lock
from datetime import datetime


class StockListCache:
    """股票列表缓存管理器"""
    
    def __init__(self):
        self._cache = None  # 缓存数据（只存一份最大数量的）
        self._cache_count = 0  # 缓存的股票数量
        self._timestamp = 0  # 缓存时间戳
        self._lock = Lock()
        
        # 缓存有效期（秒）
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
    
    def is_expired(self):
        """判断缓存是否过期"""
        if not self._cache:
            return True
        
        expire_time = self._get_expire_time()
        return time.time() - self._timestamp > expire_time
    
    def get(self, count=None):
        """获取缓存的股票列表
        
        Args:
            count: 需要的股票数量，None表示返回全部
            
        Returns:
            list: 股票列表，过期或不存在返回None
        """
        with self._lock:
            self._stats['total_requests'] += 1
            
            if not self._cache:
                return None
            
            if self.is_expired():
                print(f"[股票列表缓存] 缓存已过期，重新获取")
                self._cache = None
                self._cache_count = 0
                return None
            
            # 如果需要的数量 <= 缓存数量，直接截取
            if count is None or count <= self._cache_count:
                self._stats['cache_hits'] += 1
                if count:
                    result = self._cache[:count].copy()
                    print(f"[股票列表缓存] 命中缓存，返回前{count}只 (缓存共{self._cache_count}只)")
                else:
                    result = self._cache.copy()
                    print(f"[股票列表缓存] 命中缓存，共{len(result)}只")
                return result
            else:
                # 需要的数量 > 缓存数量，需要重新获取
                print(f"[股票列表缓存] 需要{count}只，缓存只有{self._cache_count}只，需重新获取")
                return None
    
    def set(self, stock_list, count=None):
        """设置缓存的股票列表
        
        Args:
            stock_list: 股票列表
            count: 股票数量，None表示自动检测
        """
        with self._lock:
            self._stats['api_requests'] += 1
            
            if count is None:
                count = len(stock_list)
            
            # 只存数量更大的，或者缓存为空时
            if count >= self._cache_count or not self._cache:
                self._cache = stock_list.copy()
                self._cache_count = count
                self._timestamp = time.time()
                print(f"[股票列表缓存] 已更新缓存，共{count}只股票")
            else:
                print(f"[股票列表缓存] 新数据{count}只 < 缓存{self._cache_count}只，不更新缓存")
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache = None
            self._timestamp = 0
            print("[股票列表缓存] 缓存已清空")
    
    def get_stats(self):
        """获取缓存统计数据"""
        with self._lock:
            stats = self._stats.copy()
            if stats['total_requests'] > 0:
                stats['hit_rate'] = stats['cache_hits'] / stats['total_requests'] * 100
            else:
                stats['hit_rate'] = 0
            
            if self._cache:
                stats['cache_size'] = len(self._cache)
                stats['cache_age'] = time.time() - self._timestamp
            else:
                stats['cache_size'] = 0
                stats['cache_age'] = 0
            
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
        print(f"[股票列表缓存统计]")
        print(f"  总请求: {stats['total_requests']}")
        print(f"  缓存命中: {stats['cache_hits']}")
        print(f"  API请求: {stats['api_requests']}")
        print(f"  命中率: {stats['hit_rate']:.1f}%")
        print(f"  缓存大小: {stats['cache_size']}只")
        print(f"  缓存年龄: {stats['cache_age']:.1f}秒")


# 全局单例
_stock_list_cache = None


def get_stock_list_cache():
    """获取股票列表缓存单例"""
    global _stock_list_cache
    if not _stock_list_cache:
        _stock_list_cache = StockListCache()
    return _stock_list_cache
