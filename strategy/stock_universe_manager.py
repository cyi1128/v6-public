# -*- coding: utf-8 -*-
"""
V6.1 阶段1：统一股票池过滤器 StockUniverseManager

所有选股、扫描、AI分析、回测模块统一使用本过滤器获取股票池。

过滤规则（严格执行）：
  ✅ 沪深主板股票（600/601/603/605/000/001开头）
  ❌ ST股票
  ❌ *ST股票
  ❌ 退市整理股票
  ❌ 停牌股票
  ❌ 五元以下股票

即：market == 主板 and price >= 5 and not ST and not delisting and not suspended

设计原则：
  - 单例模式，全局共享
  - 基于真实数据（通达信本地K线 + 股票名称缓存），不使用模拟数据
  - 最小化对现有代码的修改，只在入口处集成
  - 提供详细的过滤统计
"""
import os
import json
import time
import threading
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# ============================================================
# 常量
# ============================================================

# 主板代码前缀
SH_MAIN_PREFIXES = ('600', '601', '603', '605')
SZ_MAIN_PREFIXES = ('000', '001')
ALL_MAIN_PREFIXES = SH_MAIN_PREFIXES + SZ_MAIN_PREFIXES

# 最低价格
MIN_PRICE = 5.0

# 股票名称缓存文件路径
_STOCK_NAMES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'stock_names_full.json'
)

# 缓存有效期（秒）：5分钟
CACHE_TTL = 300


# ============================================================
# 过滤统计数据类
# ============================================================

class UniverseFilterStats:
    """股票池过滤统计"""

    def __init__(self):
        self.total_scanned = 0          # 扫描总数（通达信本地.day文件）
        self.main_board = 0             # 主板数量
        self.non_st = 0                 # 非ST数量
        self.price_qualified = 0        # 价格≥5数量
        self.not_suspended = 0          # 非停牌数量
        self.final_passed = 0           # 最终通过数量
        self.filter_time = 0.0          # 过滤耗时（秒）
        self.filter_date = ''           # 过滤日期
        self.latest_trade_date = ''     # 最新交易日

    def to_dict(self) -> Dict:
        return {
            'total_scanned': self.total_scanned,
            'main_board': self.main_board,
            'non_st': self.non_st,
            'price_qualified': self.price_qualified,
            'not_suspended': self.not_suspended,
            'final_passed': self.final_passed,
            'filter_time_seconds': round(self.filter_time, 2),
            'filter_date': self.filter_date,
            'latest_trade_date': self.latest_trade_date,
        }

    def __repr__(self):
        d = self.to_dict()
        return (f"UniverseFilterStats(total={d['total_scanned']}, "
                f"main_board={d['main_board']}, non_st={d['non_st']}, "
                f"price>={MIN_PRICE}={d['price_qualified']}, "
                f"not_suspended={d['not_suspended']}, "
                f"final={d['final_passed']})")


# ============================================================
# 统一股票池管理器
# ============================================================

class StockUniverseManager:
    """
    V6.1 统一股票池过滤器（单例）

    所有选股模块统一调用本类获取过滤后的股票池。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True

        # 数据引擎（延迟加载）
        self._tdx_engine = None

        # 股票名称缓存 {code: name}
        self._stock_names: Dict[str, str] = {}
        self._names_loaded = False

        # 过滤结果缓存
        self._cached_universe: List[str] = []
        self._cached_stats: Optional[UniverseFilterStats] = None
        self._cache_timestamp = 0.0

        # 单只股票详情缓存 {code: {price, name, suspended, ...}}
        self._stock_detail_cache: Dict[str, Dict] = {}

    # ============================================================
    # 数据引擎懒加载
    # ============================================================

    def _get_tdx_engine(self):
        """获取通达信数据引擎（延迟加载，避免循环导入）"""
        if self._tdx_engine is None:
            try:
                from data.tdx_data_engine import get_tdx_data_engine
                self._tdx_engine = get_tdx_data_engine()
            except Exception as e:
                print(f"[StockUniverse] 加载通达信引擎失败: {e}", flush=True)
                self._tdx_engine = None
        return self._tdx_engine

    # ============================================================
    # 股票名称加载
    # ============================================================

    def _load_stock_names(self):
        """从本地JSON加载股票名称映射"""
        if self._names_loaded:
            return

        try:
            if os.path.exists(_STOCK_NAMES_FILE):
                with open(_STOCK_NAMES_FILE, 'r', encoding='utf-8') as f:
                    self._stock_names = json.load(f)
                print(f"[StockUniverse] 加载股票名称缓存: {len(self._stock_names)}只", flush=True)
            else:
                print(f"[StockUniverse] 股票名称文件不存在: {_STOCK_NAMES_FILE}", flush=True)
        except Exception as e:
            print(f"[StockUniverse] 加载股票名称失败: {e}", flush=True)

        self._names_loaded = True

    def get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        self._load_stock_names()
        return self._stock_names.get(code, '')

    # ============================================================
    # 基础判断方法
    # ============================================================

    @staticmethod
    def is_main_board(code: str) -> bool:
        """判断是否沪深主板"""
        if not code or len(code) != 6:
            return False
        return code.startswith(ALL_MAIN_PREFIXES)

    def is_st_stock(self, code: str, name: Optional[str] = None) -> bool:
        """
        判断是否ST/*ST/退市整理股票

        判断依据：股票名称中包含 ST、*ST、退 等关键字
        """
        if name is None:
            name = self.get_stock_name(code)

        if not name:
            return False  # 名称未知时不剔除，避免误杀

        name_upper = name.upper().replace(' ', '')

        # ST / *ST
        if 'ST' in name_upper:
            return True

        # 退市整理（名称中含"退"字，如"退市XX"、"XX退"）
        if '退' in name:
            return True

        return False

    def get_latest_price(self, code: str) -> Tuple[float, str, bool]:
        """
        获取股票最新价格

        Returns:
            (price, latest_date, is_suspended)
            price: 最新收盘价
            latest_date: 最新K线日期 YYYYMMDD
            is_suspended: 是否停牌（成交量为0或数据异常）
        """
        engine = self._get_tdx_engine()
        if engine is None or not engine.is_available():
            return 0.0, '', False

        try:
            kline = engine.get_kline(code, days=5)
            if not kline or len(kline) == 0:
                return 0.0, '', True  # 无数据视为停牌

            latest = kline[-1]
            price = float(latest.get('close', 0))
            latest_date = str(latest.get('date', ''))
            volume = float(latest.get('volume', 0))

            # 停牌判断：成交量为0 或 价格为0
            is_suspended = (volume == 0 or price <= 0)

            return price, latest_date, is_suspended

        except Exception as e:
            print(f"[StockUniverse] 获取{code}价格失败: {e}", flush=True)
            return 0.0, '', True

    # ============================================================
    # 单只股票资格判断
    # ============================================================

    def is_qualified(self, code: str, use_cache: bool = True) -> bool:
        """
        判断单只股票是否通过统一过滤

        过滤规则：
          1. 沪深主板
          2. 非ST/*ST/退市
          3. 价格 >= 5元
          4. 非停牌

        Args:
            code: 股票代码
            use_cache: 是否使用缓存

        Returns:
            bool: 是否通过
        """
        if not code:
            return False

        # 1. 主板判断（最快，先做）
        if not self.is_main_board(code):
            return False

        # 2. ST判断
        name = self.get_stock_name(code)
        if self.is_st_stock(code, name):
            return False

        # 3. 价格和停牌判断
        if use_cache and code in self._stock_detail_cache:
            detail = self._stock_detail_cache[code]
            price = detail.get('price', 0)
            is_suspended = detail.get('suspended', False)
        else:
            price, _, is_suspended = self.get_latest_price(code)
            self._stock_detail_cache[code] = {
                'price': price,
                'suspended': is_suspended,
                'name': name,
            }

        if is_suspended:
            return False

        if price < MIN_PRICE:
            return False

        return True

    def get_stock_detail(self, code: str) -> Dict:
        """获取单只股票的详细过滤信息"""
        name = self.get_stock_name(code)
        price, latest_date, is_suspended = self.get_latest_price(code)

        return {
            'code': code,
            'name': name,
            'price': round(price, 2),
            'latest_date': latest_date,
            'is_main_board': self.is_main_board(code),
            'is_st': self.is_st_stock(code, name),
            'is_suspended': is_suspended,
            'price_qualified': price >= MIN_PRICE,
            'qualified': (
                self.is_main_board(code)
                and not self.is_st_stock(code, name)
                and not is_suspended
                and price >= MIN_PRICE
            ),
        }

    # ============================================================
    # 全市场过滤（核心方法）
    # ============================================================

    def get_universe(self, force_refresh: bool = False,
                     progress_callback=None) -> List[str]:
        """
        获取过滤后的统一股票池

        Args:
            force_refresh: 是否强制刷新缓存
            progress_callback: 进度回调函数(current, total)

        Returns:
            过滤通过的股票代码列表
        """
        # 缓存检查
        if (not force_refresh
                and self._cached_universe
                and (time.time() - self._cache_timestamp) < CACHE_TTL):
            return list(self._cached_universe)

        start_time = time.time()
        stats = UniverseFilterStats()
        stats.filter_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        engine = self._get_tdx_engine()
        if engine is None or not engine.is_available():
            print("[StockUniverse] 通达信引擎不可用，返回空列表", flush=True)
            self._cached_stats = stats
            return []

        # 1. 获取所有主板股票代码（通达信本地已过滤为主板）
        all_codes = engine.get_all_main_board_codes()
        stats.total_scanned = len(all_codes)
        stats.main_board = len(all_codes)  # get_all_main_board_codes已返回主板

        print(f"[StockUniverse] 开始过滤: 主板{stats.main_board}只", flush=True)

        # 2. 加载股票名称
        self._load_stock_names()

        # 3. 逐只过滤
        passed = []
        st_count = 0
        low_price_count = 0
        suspended_count = 0
        latest_date_global = ''

        total = len(all_codes)
        for i, code in enumerate(all_codes):
            try:
                # 名称判断（ST）
                name = self._stock_names.get(code, '')
                if self.is_st_stock(code, name):
                    st_count += 1
                    continue

                # 价格和停牌判断
                price, latest_date, is_suspended = self.get_latest_price(code)

                if latest_date and latest_date > latest_date_global:
                    latest_date_global = latest_date

                if is_suspended:
                    suspended_count += 1
                    continue

                if price < MIN_PRICE:
                    low_price_count += 1
                    continue

                # 通过
                passed.append(code)
                self._stock_detail_cache[code] = {
                    'price': price,
                    'suspended': False,
                    'name': name,
                }

            except Exception as e:
                print(f"[StockUniverse] 过滤{code}异常: {e}", flush=True)

            # 进度回调
            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total)

        if progress_callback:
            progress_callback(total, total)

        # 4. 统计
        stats.non_st = stats.main_board - st_count
        stats.not_suspended = stats.non_st - suspended_count
        stats.price_qualified = stats.not_suspended - low_price_count
        stats.final_passed = len(passed)
        stats.latest_trade_date = latest_date_global
        stats.filter_time = time.time() - start_time

        # 5. 缓存
        self._cached_universe = sorted(passed)
        self._cached_stats = stats
        self._cache_timestamp = time.time()

        print(f"[StockUniverse] 过滤完成: {stats}", flush=True)
        print(f"[StockUniverse]   ST剔除: {st_count}, 停牌剔除: {suspended_count}, "
              f"低价剔除: {low_price_count}", flush=True)

        return list(self._cached_universe)

    # ============================================================
    # 统计信息
    # ============================================================

    def get_stats(self) -> Optional[UniverseFilterStats]:
        """获取最近一次过滤的统计信息"""
        return self._cached_stats

    def get_stats_dict(self) -> Dict:
        """获取统计信息字典"""
        if self._cached_stats:
            return self._cached_stats.to_dict()
        return {}

    def get_cached_universe(self) -> List[str]:
        """获取缓存的股票池（不触发刷新）"""
        return list(self._cached_universe)

    def clear_cache(self):
        """清除缓存"""
        self._cached_universe = []
        self._cached_stats = None
        self._cache_timestamp = 0.0
        self._stock_detail_cache.clear()

    # ============================================================
    # 便捷方法：在现有股票列表基础上过滤
    # ============================================================

    def filter_codes(self, codes: List[str]) -> List[str]:
        """
        在给定股票代码列表基础上应用统一过滤

        用于集成到现有选股模块入口：
          原有模块获取自己的股票列表后，调用本方法进一步过滤。

        Args:
            codes: 原始股票代码列表

        Returns:
            过滤通过的股票代码列表
        """
        if not codes:
            return []

        result = []
        for code in codes:
            if self.is_qualified(code, use_cache=True):
                result.append(code)
        return result

    def filter_stock_dicts(self, stock_list: List[Dict],
                           code_key: str = 'code') -> List[Dict]:
        """
        在给定股票字典列表基础上应用统一过滤

        Args:
            stock_list: 股票字典列表
            code_key: 代码字段名

        Returns:
            过滤通过的股票字典列表
        """
        if not stock_list:
            return []

        result = []
        for stock in stock_list:
            code = stock.get(code_key, '')
            if self.is_qualified(code, use_cache=True):
                result.append(stock)
        return result


# ============================================================
# 单例获取函数
# ============================================================

_default_manager: Optional[StockUniverseManager] = None


def get_stock_universe_manager() -> StockUniverseManager:
    """获取统一股票池管理器单例"""
    global _default_manager
    if _default_manager is None:
        with StockUniverseManager._lock:
            if _default_manager is None:
                _default_manager = StockUniverseManager()
    return _default_manager


# ============================================================
# 便捷函数（供现有模块快速调用）
# ============================================================

def get_universe(force_refresh: bool = False) -> List[str]:
    """获取过滤后的统一股票池（便捷函数）"""
    return get_stock_universe_manager().get_universe(force_refresh=force_refresh)


def is_qualified(code: str) -> bool:
    """判断单只股票是否通过统一过滤（便捷函数）"""
    return get_stock_universe_manager().is_qualified(code)


def filter_codes(codes: List[str]) -> List[str]:
    """在给定代码列表基础上过滤（便捷函数）"""
    return get_stock_universe_manager().filter_codes(codes)
