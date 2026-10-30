"""
涨停次数缓存模块

预计算并缓存所有股票的年涨停次数，避免每次筛选都逐股重算K线。

使用方式：
    from strategy.limit_up_cache import get_limit_up_cache
    cache = get_limit_up_cache()
    count = cache.get_limit_up_count('600519')  # 快速查询
    cache.refresh_batch(['600519', '000001'])    # 批量刷新
"""
import os
import json
import time
from datetime import datetime


class LimitUpCache:
    """涨停次数缓存"""

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_file = os.path.join(cache_dir, 'limit_up_cache.json')
        self._cache = {}
        self._load()

    def _load(self):
        """加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._cache = data.get('stocks', {})
                self._last_update = data.get('last_update', '')
                print(f"[涨停缓存] 加载成功，共{len(self._cache)}只股票")
            except Exception as e:
                print(f"[涨停缓存] 加载失败: {e}")
                self._cache = {}
                self._last_update = ''
        else:
            self._cache = {}
            self._last_update = ''

    def _save(self):
        """保存缓存"""
        try:
            data = {
                'stocks': self._cache,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '1.0'
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[涨停缓存] 保存失败: {e}")

    def get_limit_up_count(self, code):
        """获取股票年涨停次数（快速查询）"""
        info = self._cache.get(code, {})
        return info.get('limit_up_1y', 0)

    def get_stock_info(self, code):
        """获取股票完整缓存信息"""
        return self._cache.get(code, {})

    def has_cache(self, code):
        """是否有缓存"""
        return code in self._cache

    def refresh_single(self, code, kline_data):
        """
        刷新单只股票的涨停次数

        Args:
            code: 股票代码
            kline_data: K线数据（dict格式，包含close和pct_chg）
        """
        if not kline_data:
            return 0

        closes = kline_data.get('close', [])
        pct_changes = kline_data.get('pct_chg', [])

        if not closes or not pct_changes:
            return 0

        # 计算近一年（252个交易日）涨停次数
        days = min(252, len(pct_changes))
        count = sum(1 for pct in pct_changes[-days:] if pct >= 9.8)

        # 计算近8个月高点
        highs = kline_data.get('high', [])
        high_8m = max(highs[-168:]) if len(highs) >= 168 else (max(highs) if highs else 0)

        self._cache[code] = {
            'limit_up_1y': count,
            'high_8m': round(high_8m, 2),
            'last_close': closes[-1] if closes else 0,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return count

    def refresh_batch(self, code_list, kline_provider, progress_callback=None):
        """
        批量刷新涨停次数

        Args:
            code_list: 股票代码列表
            kline_provider: K线获取函数 (code, count) -> kline_data
            progress_callback: 进度回调 (current, total, message)

        Returns:
            刷新数量
        """
        total = len(code_list)
        updated = 0
        start_time = time.time()

        for i, code in enumerate(code_list):
            try:
                kline = kline_provider(code, count=252)
                if kline:
                    self.refresh_single(code, kline)
                    updated += 1
            except Exception as e:
                print(f"[涨停缓存] {code}刷新失败: {e}")

            if progress_callback and (i + 1) % 50 == 0:
                elapsed = time.time() - start_time
                speed = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (total - i - 1) / speed if speed > 0 else 0
                progress_callback(i + 1, total, f'涨停次数缓存: {i+1}/{total}, 剩余约{remaining:.0f}秒')

        self._save()
        print(f"[涨停缓存] 批量刷新完成，更新{updated}/{total}只，耗时{time.time()-start_time:.1f}秒")
        return updated

    def get_all_codes(self):
        """获取所有有缓存的股票代码"""
        return list(self._cache.keys())

    def get_cache_size(self):
        """获取缓存数量"""
        return len(self._cache)

    def clear(self):
        """清空缓存"""
        self._cache = {}
        self._save()
        print("[涨停缓存] 已清空")


# 单例
_instance = None


def get_limit_up_cache():
    """获取涨停次数缓存单例"""
    global _instance
    if _instance is None:
        _instance = LimitUpCache()
    return _instance
