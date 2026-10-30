# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.1 - 统一入口

V1.1核心修复：
- 三层筛选结构（候选池→模型评分→买点确认）
- 取消70分硬过滤，60分以上均显示
- 放宽模型条件，OR逻辑独立评分
- 漏斗统计输出
- 代码模块化拆分

目录结构：
  strategy/
    main_force_behavior.py          # 本文件：统一入口
    base.py                          # 公共基础（指标/数据结构/候选池检测）
    models/
      limit_up_pullback.py           # 涨停回调模型
      box_breakout.py                # 箱体突破模型
      volume_breakout.py             # 量价突破模型
    scoring/
      ai_score.py                    # AI六维度评分
    signals/
      buy_sell_signal.py             # 买卖点确认(B1-B3/S1-S4)
    annotation/
      kline_annotator.py             # K线6色标注
"""
import os
import json
import time
import logging
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from strategy.base import (
    KlineBar, ModelMatch, AIScore, BuySellSignal, KlineAnnotation, StockScanResult,
    KlineDataParser, BehaviorCandidateDetector, TechnicalIndicators, VolumeAnalyzer,
    MODEL_LIMIT_PULLBACK, MODEL_BOX_BREAKOUT, MODEL_VOLUME_BREAKOUT,
    SCORE_LAUNCH_CANDIDATE, SCORE_STRONG_CANDIDATE, SCORE_KEY_WATCH, SCORE_WATCH, SCORE_LOW,
    BUY_B1, BUY_B2, BUY_B3, LIMIT_UP_THRESHOLD, BIG_YANG_THRESHOLD,
)
from strategy.models.limit_up_pullback import LimitUpPullbackModel
from strategy.models.box_breakout import BoxBreakoutModel
from strategy.models.volume_breakout import VolumeBreakoutModel
from strategy.scoring.ai_score import AIScoringSystem
from strategy.signals.buy_sell_signal import BuySellSignalDetector
from strategy.annotation.kline_annotator import KlineAnnotationGenerator
from strategy.cache_manager import CacheManager, get_cache_manager
from strategy.parallel_scanner import ParallelScanner, ScanProgress


# ============================================================
# 扫描日志器
# ============================================================

class ScanLogger:
    """扫描日志器 - 同时输出到控制台和日志文件"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"force_scan_{datetime.now().strftime('%Y%m%d')}.log")
        self._start_time = time.time()

    def log(self, msg: str):
        """输出日志到控制台和文件"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        line = f"[{timestamp}] {msg}"
        print(line, flush=True)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception:
            pass

    def step(self, step_num: int, name: str, count: int, note: str = ""):
        """输出步骤统计"""
        elapsed = time.time() - self._start_time
        note_str = f" ({note})" if note else ""
        self.log(f"步骤{step_num:2d} | {name:20s} | 数量: {count:6d} | 耗时: {elapsed:6.1f}s{note_str}")

    def error(self, msg: str):
        self.log(f"[ERROR] {msg}")

    def warn(self, msg: str):
        self.log(f"[WARN] {msg}")

    def summary(self, funnel):
        """输出扫描总结"""
        self.log("=" * 70)
        self.log("扫描完成 - 漏斗统计总结")
        self.log("=" * 70)
        for k, v in funnel.to_dict().items():
            self.log(f"  {k:20s}: {v}")
        self.log("=" * 70)


# ============================================================
# 漏斗统计
# ============================================================

@dataclass
class FunnelStats:
    """扫描漏斗统计 - V1.2 增加三层扫描统计和耗时"""
    # 市场范围
    total_market: int = 0          # 全市场股票
    main_board_count: int = 0       # 主板股票（过滤后）
    # 数据链路
    data_provider_ok: int = 0       # 数据提供者正常
    kline_fetch_ok: int = 0         # K线数据获取成功
    kline_parse_ok: int = 0         # K线解析成功（bars>=10）
    basic_data_ok: int = 0           # 满足基础数据要求（bars>=20）
    # 三层扫描
    layer1_basic_filter: int = 0     # 第一层：基础筛选通过（行情数据）
    layer2_behavior_prescreen: int = 0  # 第二层：行为预筛通过（30日K线）
    layer3_deep_analysis: int = 0    # 第三层：深度分析完成（120日K线）
    # 筛选链路
    passed_prefilter: int = 0      # 通过初筛
    behavior_candidates: int = 0    # 第一层：行为候选
    model_limit_up: int = 0         # 涨停回调匹配
    model_box: int = 0              # 箱体突破匹配
    model_volume: int = 0           # 量价突破匹配
    score_60_plus: int = 0          # 评分60以上
    score_70_plus: int = 0          # 评分70以上
    score_80_plus: int = 0          # 评分80以上
    score_90_plus: int = 0          # 评分90以上
    buy_b1: int = 0                  # B1观察买点
    buy_b2: int = 0                  # B2确认买点
    buy_b3: int = 0                  # B3强势买点
    final_pool: int = 0              # 最终股票池
    # 异常统计
    error_count: int = 0             # 异常数量
    data_insufficient: int = 0       # 数据不足数量
    kline_empty: int = 0             # K线为空数量
    kline_failed: int = 0            # V1.2.1：K线获取失败数量
    no_candidate: int = 0            # 非候选数量
    # L1细分统计（V1.2.1）
    l1_price_abnormal: int = 0       # L1价格异常
    l1_no_volume: int = 0            # L1无成交
    l1_big_drop: int = 0             # L1跌幅过大
    # L2条件统计（V1.3.5）
    l2_cond_rise: int = 0            # L2条件1：近期涨幅
    l2_cond_volume: int = 0          # L2条件2：成交量变化
    l2_cond_big_yang: int = 0        # L2条件3：大阳线
    l2_cond_sideways: int = 0        # L2条件4：横盘整理
    l2_cond_breakout: int = 0        # L2条件5：突破迹象
    # L2细粒度条件（V1.3.6）
    l2_cond_rise_10d: int = 0       # 近10日涨幅>8%
    l2_cond_rise_20d: int = 0       # 近20日涨幅>15%
    l2_cond_shrink: int = 0          # 缩量(5日<20日×0.7)
    l2_cond_expand: int = 0          # 放量(5日>20日×1.5)
    # 数据健康检查（V1.3.5）
    health_total: int = 0             # 待检查股票数
    health_valid: int = 0             # K线有效（close>0且open>0且high>0且low>0）
    health_price_abnormal: int = 0    # 价格异常(close<=0)
    health_volume_abnormal: int = 0   # 成交量异常(volume<=0)
    health_insufficient: int = 0      # 缺少K线(根数<20)
    health_latest_date: str = ""      # 最新K线日期
    # 模型评分分布（V1.3.5）
    model_limit_up_scores: list = None  # 涨停回调匹配的分数列表
    model_box_scores: list = None       # 箱体突破匹配的分数列表
    model_volume_scores: list = None    # 量价突破匹配的分数列表
    l3_abnormal_data: int = 0           # L3异常：数据不足
    l3_abnormal_divzero: int = 0        # L3异常：除以0
    l3_abnormal_other: int = 0          # L3异常：其他
    # 耗时统计（秒）
    time_total: float = 0.0          # 总耗时
    time_layer1: float = 0.0         # 第一层耗时
    time_layer2: float = 0.0         # 第二层耗时
    time_layer3: float = 0.0         # 第三层耗时
    # 扫描模式
    scan_mode: str = "快速扫描"       # 快速扫描/标准扫描/深度扫描

    def to_dict(self) -> Dict:
        return {
            '全市场股票': self.total_market,
            '主板股票': self.main_board_count,
            '数据提供者正常': self.data_provider_ok,
            'K线获取成功': self.kline_fetch_ok,
            'K线解析成功': self.kline_parse_ok,
            '基础数据满足': self.basic_data_ok,
            '第一层基础筛选': self.layer1_basic_filter,
            '第二层行为预筛': self.layer2_behavior_prescreen,
            '第三层深度分析': self.layer3_deep_analysis,
            '通过初筛': self.passed_prefilter,
            '行为候选': self.behavior_candidates,
            '涨停回调匹配': self.model_limit_up,
            '箱体突破匹配': self.model_box,
            '量价突破匹配': self.model_volume,
            '评分60以上': self.score_60_plus,
            '评分70以上': self.score_70_plus,
            '评分80以上': self.score_80_plus,
            '评分90以上': self.score_90_plus,
            'B1观察买点': self.buy_b1,
            'B2确认买点': self.buy_b2,
            'B3强势买点': self.buy_b3,
            '最终股票池': self.final_pool,
            '异常数量': self.error_count,
            '数据不足': self.data_insufficient,
            'K线为空': self.kline_empty,
            'K线失败': self.kline_failed,
            'L1价格异常': self.l1_price_abnormal,
            'L1无成交': self.l1_no_volume,
            'L1跌幅过大': self.l1_big_drop,
            '非候选': self.no_candidate,
            '总耗时(秒)': round(self.time_total, 1),
            '第一层耗时(秒)': round(self.time_layer1, 1),
            '第二层耗时(秒)': round(self.time_layer2, 1),
            '第三层耗时(秒)': round(self.time_layer3, 1),
            '扫描模式': self.scan_mode,
        }

    def summary(self) -> str:
        d = self.to_dict()
        lines = [f"  {k}: {v}" for k, v in d.items()]
        return "扫描漏斗统计:\n" + "\n".join(lines)


# ============================================================
# 全市场扫描引擎（三层筛选）
# ============================================================

class MarketScanner:
    """全市场扫描引擎 - V1.2 三层扫描流程 + 并行 + 缓存"""

    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.model_limit = LimitUpPullbackModel()
        self.model_box = BoxBreakoutModel()
        self.model_volume = VolumeBreakoutModel()
        self.scoring = AIScoringSystem()
        self.signal_detector = BuySellSignalDetector()
        self.annotation_gen = KlineAnnotationGenerator()
        self.candidate_detector = BehaviorCandidateDetector()
        self._cache = {}
        self._cache_ttl = 300
        self.funnel = FunnelStats()
        self.scan_logger = ScanLogger()
        self._last_diagnostics = []  # 最近扫描的诊断信息
        # V1.2：缓存管理器和并行扫描器
        self.cache_mgr = get_cache_manager()
        self.parallel_scanner = ParallelScanner(max_workers=8, throttle=0.02)
        # V1.2.1：聚宽数据源（首选，失败自动降级）
        self.jq_provider = None
        self._init_jqdata()
        # V1.2.3：智能扫描缓存
        from strategy.scan_cache_manager import get_scan_cache_manager
        self.scan_cache = get_scan_cache_manager()
        self.scan_cache.clear_expired_score_cache()
        # V1.2.4：本地K线持久化缓存（DuckDB）
        from strategy.kline_cache_db import get_kline_cache_db
        self.kline_db = get_kline_cache_db()
        self._kline_cache_hits = 0
        self._kline_cache_misses = 0
        # V1.3：通达信本地高速行情数据引擎（第一优先级）
        self.tdx_engine = None
        self._tdx_preloaded = False
        self._init_tdx_engine()
        # V1.2：扫描模式配置
        self.scan_mode = "快速扫描"  # 快速扫描/标准扫描
        self.mode_config = {
            "快速扫描": {"prescreen_days": 30, "deep_days": 120, "use_parallel": True},
            "标准扫描": {"prescreen_days": 60, "deep_days": 120, "use_parallel": True},
            "深度扫描": {"prescreen_days": 120, "deep_days": 250, "use_parallel": False},
        }

    def set_data_provider(self, provider):
        self.data_provider = provider

    def _init_jqdata(self):
        """V1.2.1：初始化聚宽数据源，失败静默降级"""
        try:
            from data.jqdata_provider import get_jqdata_provider
            self.jq_provider = get_jqdata_provider()
            if self.jq_provider and self.jq_provider.authenticated:
                print("[SCANNER] 聚宽数据源已启用，作为首选K线/行情数据源")
            else:
                print("[SCANNER] 聚宽数据源不可用，使用现有K线接口")
        except Exception as e:
            print(f"[SCANNER] 聚宽数据源初始化失败，降级到现有接口: {e}")
            self.jq_provider = None

    def _init_tdx_engine(self):
        """V1.3：初始化通达信本地数据引擎，失败静默降级"""
        try:
            from data.tdx_data_engine import get_tdx_data_engine
            self.tdx_engine = get_tdx_data_engine()
            if self.tdx_engine and self.tdx_engine.is_available():
                stats = self.tdx_engine.get_memory_cache_stats()
                print(f"[SCANNER] 通达信本地数据引擎已启用: {stats['tdx_path']}")
            else:
                print("[SCANNER] 通达信本地数据不可用，将使用网络API")
        except Exception as e:
            print(f"[SCANNER] 通达信引擎初始化失败: {e}")
            self.tdx_engine = None

    def _get_kline_with_fallback(self, code: str, days: int = 120) -> Optional[List[Dict]]:
        """V1.3：获取K线数据，全部使用在线接口，不使用通达信本地数据文件

        数据源优先级：
        1. 在线接口（pytdx在线→腾讯财经→新浪财经→东方财富，统一fetch_kline入口）
        2. DuckDB本地缓存（仅在线失败时，且缓存日期在7天内）
        3. 内存缓存
        4. 都失败 → 返回空列表（不返回通达信本地旧数据）

        Returns:
            K线数据（List[Dict]格式），失败返回空列表
        """
        # 1. 首选在线接口（pytdx在线→腾讯→新浪→东方财富）
        try:
            from utils.kline_fetcher import fetch_kline
            online_kline = fetch_kline(code, days=days)
            if online_kline and len(online_kline) >= min(days, 20):
                # 保存到DuckDB缓存和内存缓存
                try:
                    self.kline_db.save_kline(code, online_kline)
                except Exception:
                    pass
                try:
                    self.cache_mgr.set_kline(code, online_kline, days=days)
                except Exception:
                    pass
                self._kline_cache_misses += 1
                print(f"[KLINE ONLINE] {code} 在线获取成功: {len(online_kline)}根, 最新={online_kline[-1].get('date','')}", flush=True)
                return online_kline
        except Exception as e:
            print(f"[KLINE ONLINE] {code} 在线接口异常: {e}", flush=True)

        # 2. 在线失败时，检查DuckDB缓存（仅返回7天内的较新缓存）
        from datetime import datetime as _dt, timedelta as _td
        try:
            cached_last = self.kline_db.get_last_date(code)
            if cached_last:
                last_date = _dt.strptime(str(cached_last)[:8], '%Y%m%d').date()
                days_diff = (_dt.now().date() - last_date).days
                if days_diff <= 7:
                    cached_kline = self.kline_db.get_kline(code, days=days)
                    if cached_kline and len(cached_kline) >= min(days, 20):
                        self._kline_cache_hits += 1
                        print(f"[KLINE CACHE] {code} 使用DuckDB缓存({days_diff}天前): {len(cached_kline)}根", flush=True)
                        return cached_kline
        except Exception:
            pass

        # 3. 检查内存缓存
        try:
            cached = self.cache_mgr.get_kline(code, days=days)
            if cached is not None and len(cached) >= min(days, 20):
                self._kline_cache_hits += 1
                return cached
        except Exception:
            pass

        # 4. 都失败，返回空列表（不返回通达信本地旧数据）
        self.funnel.kline_failed += 1
        print(f"[KLINE FAIL] {code} 所有在线接口均失败，返回空列表", flush=True)
        return []

    def scan_full_market(self, progress_callback=None, min_score: float = 60.0,
                         max_stocks: Optional[int] = None, scan_mode: str = "快速扫描") -> List[StockScanResult]:
        """
        V1.2全市场扫描 - 三层扫描流程 + 并行 + 缓存

        第一层：主板基础筛选（只用行情数据，不加载K线）
        第二层：快速行为预筛（只加载30日K线，轻量计算）
        第三层：深度模型分析（只对预筛通过的股票，加载120日K线）
        """
        self.funnel = FunnelStats()
        self.funnel.scan_mode = scan_mode
        self.scan_mode = scan_mode
        mode_cfg = self.mode_config.get(scan_mode, self.mode_config["快速扫描"])
        prescreen_days = mode_cfg['prescreen_days']
        deep_days = mode_cfg['deep_days']
        use_parallel = mode_cfg['use_parallel']

        self._last_diagnostics = []
        logger = self.scan_logger
        # V1.2.2：重置扫描计时器（修复步骤1显示123秒的问题）
        logger._start_time = time.time()
        total_start = time.time()
        logger.log("=" * 70)
        logger.log(f"强势主力行为选股系统 V1.2 - {scan_mode}开始")
        logger.log(f"配置: 预筛{prescreen_days}日 / 深度{deep_days}日 / 并行={'是' if use_parallel else '否'}")
        logger.log("=" * 70)

        # 步骤1：检查数据提供者（V1.2.2：增加健康检查和重连，超时保护）
        if self.data_provider is None:
            logger.error("步骤1 | 数据提供者未初始化")
            return []
        # 健康检查：测试连接，失败时尝试重连（最多5秒）
        try:
            if not hasattr(self.data_provider, 'is_connected') or not self.data_provider.is_connected():
                logger.log("  数据提供者未连接，尝试重连...")
                import threading
                connect_result = [False]
                def _do_connect():
                    try:
                        connect_result[0] = self.data_provider.connect()
                    except Exception:
                        connect_result[0] = False
                t = threading.Thread(target=_do_connect)
                t.daemon = True
                t.start()
                t.join(timeout=8)  # 最多等8秒
                if not connect_result[0]:
                    logger.warn("  数据提供者重连超时或失败，将使用备用股票列表")
        except Exception as e:
            logger.warn(f"  数据提供者健康检查异常: {e}")
        self.funnel.data_provider_ok = 1
        logger.step(1, "数据提供者检查", 1, "正常")

        # 步骤2：获取全市场股票列表（V1.3：优先通达信本地，零网络扫描）
        stock_list = []
        self._stock_list_has_quotes = False  # V1.2.5：标记股票列表是否自带行情
        self._using_tdx_local = False  # V1.3：标记是否使用通达信本地数据

        # V1.3：第一优先 - 通达信本地数据引擎（零网络请求）
        if self.tdx_engine and self.tdx_engine.is_available():
            try:
                print("[SCAN] V1.3 通达信本地数据引擎可用，尝试零网络扫描...", flush=True)
                # 从本地文件目录获取主板股票列表
                tdx_codes = self.tdx_engine.get_all_main_board_codes()
                print(f"[SCAN DEBUG] 步骤2 通达信get_all_main_board_codes返回: {len(tdx_codes)}只", flush=True)
                if tdx_codes:
                    print(f"[SCAN] 通达信本地扫描到 {len(tdx_codes)} 只主板股票.day文件", flush=True)
                    # 预加载所有主板K线到内存（8线程并行）
                    preload_result = self.tdx_engine.preload_to_memory(tdx_codes, days=120, max_workers=8)
                    print(f"[SCAN] 通达信预加载完成: {preload_result['success']}/{preload_result['total']}只, "
                          f"耗时{preload_result['elapsed_seconds']}秒", flush=True)
                    # 从内存K线构建股票列表（含最新行情）
                    stock_list = []
                    kline_ok = 0
                    kline_fail = 0
                    for idx, code in enumerate(tdx_codes):
                        kline = self.tdx_engine.get_kline(code, days=2)
                        if not kline or len(kline) < 1:
                            kline_fail += 1
                            continue
                        kline_ok += 1
                        latest = kline[-1]
                        # V1.3.3 字段名兼容：支持close/收盘价/close_price等多种命名
                        close_price = latest.get('close', latest.get('收盘价', latest.get('close_price', 0)))
                        open_price = latest.get('open', latest.get('开盘价', latest.get('open_price', 0)))
                        vol = latest.get('volume', latest.get('成交量', latest.get('vol', 0)))
                        amt = latest.get('amount', latest.get('成交额', latest.get('money', 0)))
                        prev_close = kline[-2].get('close', kline[-2].get('收盘价', 0)) if len(kline) >= 2 else open_price
                        change_pct = 0
                        if prev_close and prev_close > 0 and close_price and close_price > 0:
                            change_pct = (close_price - prev_close) / prev_close * 100
                        # V1.3.3 调试：打印前3只股票的K线内容
                        if idx < 3:
                            print(f"[SCAN DEBUG] 股票{code} K线最后1根: {latest}", flush=True)
                            print(f"[SCAN DEBUG]   close={close_price}, open={open_price}, volume={vol}, amount={amt}, prev_close={prev_close}, change={change_pct:.2f}%", flush=True)
                        stock_list.append({
                            'code': code,
                            'ts_code': code,
                            'name': '',  # 本地文件无名称，后续从网络补充
                            'price': close_price if close_price > 0 else 0,
                            'change_pct': round(change_pct, 2),
                            'volume': vol if vol > 0 else 0,
                            'amount': amt if amt > 0 else 0,
                            'industry': '',
                            'market': 'SH' if code.startswith('6') else 'SZ',
                        })
                    print(f"[SCAN DEBUG] 通达信股票列表构建: K线成功{kline_ok}只, 失败{kline_fail}只, "
                          f"最终stock_list={len(stock_list)}只", flush=True)
                    if stock_list:
                        self._stock_list_has_quotes = True
                        self._using_tdx_local = True
                        self._tdx_preloaded = True
                        print(f"[SCAN] 通达信本地股票列表: {len(stock_list)}只（自带行情，零网络请求）", flush=True)

                        # V1.3.7：名称缓存优先 + 后台异步补充（省13.7秒）
                        name_cache = self._load_name_cache()
                        cache_hit = 0
                        need_fetch = []
                        for s in stock_list:
                            cached_name = name_cache.get(s['code'])
                            if cached_name:
                                s['name'] = cached_name
                                cache_hit += 1
                            else:
                                need_fetch.append(s['code'])
                        print(f"[SCAN] 名称缓存: 命中{cache_hit}/{len(stock_list)}只, 需补充{len(need_fetch)}只", flush=True)

                        if need_fetch:
                            # 后台异步补充名称，不阻塞扫描
                            def _async_fetch_names(codes, stock_list_ref, name_cache_ref):
                                try:
                                    from data.tencent_quote import get_batch_quotes
                                    quotes = get_batch_quotes(codes)
                                    if quotes:
                                        new_names = {}
                                        for s in stock_list_ref:
                                            q = quotes.get(s['code'])
                                            if q and q.get('name'):
                                                s['name'] = q['name']
                                                new_names[s['code']] = q['name']
                                                # 同时更新价格/涨跌幅
                                                if q.get('price') and q['price'] > 0:
                                                    s['price'] = q['price']
                                                if q.get('change_pct') is not None:
                                                    s['change_pct'] = q['change_pct']
                                        # 更新并保存缓存
                                        name_cache_ref.update(new_names)
                                        self._save_name_cache(name_cache_ref)
                                        print(f"[SCAN] 后台名称补充完成: {len(new_names)}只新名称已缓存", flush=True)
                                except Exception as e:
                                    print(f"[SCAN WARN] 后台名称补充失败: {e}", flush=True)

                            import threading
                            name_thread = threading.Thread(target=_async_fetch_names,
                                                            args=(need_fetch, stock_list, name_cache))
                            name_thread.daemon = True
                            name_thread.start()
                            self._name_fetch_thread = name_thread
                        else:
                            print(f"[SCAN] 名称全部命中缓存，跳过腾讯请求", flush=True)

                        # V1.3.1：通达信数据不足100只时，用网络API补充完整主板列表
                        if len(stock_list) < 100:
                            print(f"[SCAN WARN] 通达信本地只有{len(stock_list)}只股票数据，"
                                  f"建议在通达信软件中执行「盘后数据下载」下载全部主板数据", flush=True)
                            print(f"[SCAN] 尝试用网络API补充完整主板股票列表...", flush=True)
                            try:
                                from data.stock_list_provider import get_cached_main_board_stocks
                                net_stocks = get_cached_main_board_stocks()
                                if net_stocks:
                                    # 合并：网络列表为主，通达信本地数据补充行情
                                    tdx_code_map = {s['code']: s for s in stock_list}
                                    merged = []
                                    for ns in net_stocks:
                                        code = ns.get('code', ns.get('ts_code', ''))
                                        if code in tdx_code_map:
                                            # 用通达信本地行情数据（更准）
                                            merged.append(tdx_code_map[code])
                                        else:
                                            # 网络补充的股票，标记需要K线从网络获取
                                            merged.append(ns)
                                    stock_list = merged
                                    self._stock_list_has_quotes = True
                                    self._using_tdx_local = False  # 混合模式
                                    print(f"[SCAN] 网络补充完成: 合并后{len(stock_list)}只主板股票", flush=True)
                                else:
                                    print(f"[SCAN WARN] 网络API补充失败，仅使用通达信本地{len(stock_list)}只", flush=True)
                            except Exception as e:
                                print(f"[SCAN WARN] 网络API补充异常: {e}，仅使用通达信本地{len(stock_list)}只", flush=True)
            except Exception as e:
                import traceback
                print(f"[SCAN ERROR] 通达信本地扫描异常: {e}", flush=True)
                traceback.print_exc()
                print(f"[SCAN] 降级到网络API", flush=True)
                stock_list = []

        # V1.2.5：通达信本地不可用或失败，降级东方财富真实主板股票列表（含最新行情）
        if not stock_list:
            try:
                from data.stock_list_provider import get_cached_main_board_stocks
                stock_list = get_cached_main_board_stocks()
                if stock_list:
                    if stock_list[0].get('price', 0) > 0 or stock_list[0].get('change_pct', 0) != 0:
                        self._stock_list_has_quotes = True
                        print(f"[SCAN] 东方财富真实股票列表: {len(stock_list)}只（自带行情数据，L1零额外请求）", flush=True)
                    else:
                        print(f"[SCAN] 东方财富真实股票列表: {len(stock_list)}只（无行情数据，L1需补充）", flush=True)
            except Exception as e:
                print(f"[SCAN] 东方财富股票列表获取异常: {e}", flush=True)

        # 东方财富失败，降级通达信网络接口
        if not stock_list and self.data_provider:
            try:
                import threading
                result_holder = [None]
                def _do_get_stocks():
                    try:
                        result_holder[0] = self.data_provider.get_stock_list()
                    except Exception as e:
                        result_holder[0] = []
                        print(f"[SCAN] 通达信股票列表异常: {e}", flush=True)
                t = threading.Thread(target=_do_get_stocks)
                t.daemon = True
                t.start()
                t.join(timeout=15)
                if result_holder[0] is not None:
                    stock_list = result_holder[0]
                    from data.stock_list_provider import _is_main_board_code, _is_st_stock
                    stock_list = [s for s in stock_list
                                  if _is_main_board_code(s.get('ts_code') or s.get('code', ''))
                                  and not _is_st_stock(s.get('name', ''))]
                    print(f"[SCAN] 通达信网络降级股票列表: {len(stock_list)}只主板", flush=True)
            except Exception as e:
                print(f"[SCAN] 通达信股票列表超时: {e}", flush=True)

        # V1.2.5：都失败则终止扫描，不再用虚拟7000列表
        if not stock_list:
            logger.error("步骤2 | 无法获取真实股票列表（通达信本地+东方财富+通达信网络均失败）")
            print("[ERROR] 无法获取真实股票列表，请检查通达信安装或网络连接后重试", flush=True)
            return []
        self.funnel.total_market = len(stock_list)
        logger.step(2, "全市场股票", len(stock_list))
        # V1.3.2 精确定位：打印前3只股票，确认是真实股票
        print(f"[SCAN STEP 2] 全市场股票: {len(stock_list)}只", flush=True)
        for i, s in enumerate(stock_list[:3]):
            code = s.get('ts_code', s.get('code', ''))
            name = s.get('name', '')
            price = s.get('price', s.get('current_price', 0))
            print(f"[SCAN STEP 2]   前3只[{i}]: code={code}, name={name}, price={price}", flush=True)

        # V1.3.15：通用行业信息获取（从DuckDB stock_basic表，适用于所有数据源）
        try:
            from data.duckdb_adapter import DuckDBAdapter
            _db = DuckDBAdapter()
            _basic_df = _db.get_stock_basic()
            if _basic_df is not None and len(_basic_df) > 0:
                _industry_map = {}
                for _, _row in _basic_df.iterrows():
                    _ts = str(_row.get('ts_code', ''))
                    _code = _ts.split('.')[0] if '.' in _ts else _ts
                    _ind = _row.get('industry', '')
                    if _code and _ind and str(_ind) != 'nan':
                        _industry_map[_code] = str(_ind)
                _ind_hit = 0
                for s in stock_list:
                    _c = s.get('code', s.get('ts_code', ''))
                    if _c in _industry_map and (not s.get('industry')):
                        s['industry'] = _industry_map[_c]
                        _ind_hit += 1
                print(f"[SCAN] 行业信息: DuckDB获取{len(_industry_map)}个行业, 补充{_ind_hit}/{len(stock_list)}只", flush=True)
                # 打印前3只的行业值
                for i, s in enumerate(stock_list[:3]):
                    print(f"[SCAN]   行业[{i}]: code={s.get('code')}, industry={s.get('industry', '-')}", flush=True)
            else:
                print(f"[SCAN WARN] DuckDB stock_basic表无数据，行业信息将显示'-'", flush=True)
        except Exception as e:
            print(f"[SCAN WARN] 从DuckDB获取行业信息失败: {e}，行业信息将显示'-'", flush=True)

        # V1.3.5：数据健康检查（扫描前自动执行）
        if not self._data_health_check(stock_list):
            logger.error("数据健康检查失败：K线数据全部异常，终止扫描")
            print("[ERROR] 数据健康检查失败：K线数据全部异常，请检查通达信盘后数据下载", flush=True)
            return []

        # 步骤3：主板过滤（V1.2新增）
        main_board = self._filter_board(stock_list)
        self.funnel.main_board_count = len(main_board)
        logger.step(3, "主板过滤", len(main_board),
                    f"排除{len(stock_list) - len(main_board)}只(创业板/科创板/北交所/ST)")
        # V1.3.2 精确定位
        print(f"[SCAN STEP 3] 主板过滤: 通过={len(main_board)}, 过滤={len(stock_list) - len(main_board)}", flush=True)
        if len(main_board) == 0:
            print(f"[SCAN STEP 3] 警告: 主板过滤后为0！检查_filter_board逻辑", flush=True)

        if max_stocks:
            main_board = main_board[:max_stocks]
            logger.log(f"  限制扫描数量: {max_stocks}")

        # ============================================================
        # 第一层：基础筛选（V1.2.5：只用行情数据，不获取K线）
        # ============================================================
        logger.log("-" * 50)
        logger.log("第一层：基础筛选（行情数据过滤，不获取K线）")
        layer1_start = time.time()

        layer1_passed = self._layer1_basic_filter(
            main_board, progress_callback=progress_callback,
            prescreen_days=prescreen_days)
        self.funnel.layer1_basic_filter = len(layer1_passed)
        self.funnel.time_layer1 = time.time() - layer1_start
        logger.step(4, "第一层基础筛选", len(layer1_passed),
                    f"耗时{self.funnel.time_layer1:.1f}s, 过滤{len(main_board) - len(layer1_passed)}只")
        # V1.2.1：L1细分统计
        logger.log(f"  L1细分: 价格异常={self.funnel.l1_price_abnormal}, "
                   f"无成交={self.funnel.l1_no_volume}, "
                   f"跌幅过大={self.funnel.l1_big_drop}, "
                   f"K线失败={self.funnel.kline_failed}")
        # V1.3.2 精确定位
        l1_avg = self.funnel.time_layer1 / len(main_board) if main_board else 0
        print(f"[SCAN STEP 4] L1基础筛选: 通过={len(layer1_passed)}, 过滤={len(main_board) - len(layer1_passed)}, "
              f"耗时={self.funnel.time_layer1:.1f}s, 每只平均={l1_avg:.3f}s", flush=True)
        print(f"[SCAN STEP 4]   细分: 价格异常={self.funnel.l1_price_abnormal}, "
              f"无成交={self.funnel.l1_no_volume}, 大跌={self.funnel.l1_big_drop}, "
              f"K线失败={self.funnel.kline_failed}", flush=True)
        if len(layer1_passed) == 0:
            print(f"[SCAN STEP 4] 警告: L1过滤后为0！检查行情数据（价格/成交量是否为0或None）", flush=True)
            # 打印一只股票的L1数据
            if main_board:
                s = main_board[0]
                print(f"[SCAN STEP 4]   样本股票: code={s.get('code')}, price={s.get('price')}, "
                      f"volume={s.get('volume')}, change_pct={s.get('change_pct')}", flush=True)

        if not layer1_passed:
            logger.warn("第一层筛选后无股票，扫描结束")
            self.funnel.time_total = time.time() - total_start
            logger.summary(self.funnel)
            return []

        # ============================================================
        # 第二层：行为预筛（30日K线轻量计算）
        # ============================================================
        logger.log("-" * 50)
        logger.log(f"第二层：行为预筛（{prescreen_days}日K线）")
        layer2_start = time.time()

        def prescreen_worker(stock_info):
            """第二层工作函数：行为预筛 - V1.2.1增加失败统计"""
            code = stock_info.get('ts_code', stock_info.get('code', ''))
            try:
                if self._layer2_behavior_prescreen(stock_info, days=prescreen_days):
                    return stock_info
            except Exception as e:
                print(f"[PRESCREEN ERROR] {code}预筛异常: {e}", flush=True)
                self.funnel.error_count += 1
            return None

        if use_parallel and len(layer1_passed) > 20:
            # 并行预筛
            def progress_wrapper(progress: ScanProgress):
                if progress_callback:
                    progress_callback(progress.processed, progress.total,
                                      f"预筛:{progress.current_code}")

            layer2_passed = self.parallel_scanner.scan_parallel(
                layer1_passed, prescreen_worker,
                stage="行为预筛", progress_callback=progress_wrapper,
                batch_size=100, throttle=0)  # V1.3.3：L2从内存缓存读取，无需节流
        else:
            # 串行预筛
            layer2_passed = []
            for i, stock in enumerate(layer1_passed):
                if prescreen_worker(stock):
                    layer2_passed.append(stock)
                if progress_callback and (i % 50 == 0 or i == len(layer1_passed) - 1):
                    progress_callback(i + 1, len(layer1_passed), "行为预筛")

        self.funnel.layer2_behavior_prescreen = len(layer2_passed)
        self.funnel.time_layer2 = time.time() - layer2_start
        logger.step(5, "第二层行为预筛", len(layer2_passed),
                    f"耗时{self.funnel.time_layer2:.1f}s, 过滤{len(layer1_passed) - len(layer2_passed)}只")
        # V1.3.2 精确定位：L2每只平均耗时 + 单只预筛详情
        l2_avg = self.funnel.time_layer2 / len(layer1_passed) if layer1_passed else 0
        print(f"[SCAN STEP 5] L2行为预筛: 通过={len(layer2_passed)}, 过滤={len(layer1_passed) - len(layer2_passed)}, "
              f"耗时={self.funnel.time_layer2:.1f}s, 每只平均={l2_avg:.3f}s", flush=True)
        if len(layer2_passed) == 0:
            print(f"[SCAN STEP 5] 警告: L2预筛后为0！检查预筛条件是否太严", flush=True)
            # 打印一只股票的L2预筛详细结果（5个条件各自是否通过）
            if layer1_passed:
                sample = layer1_passed[0]
                code = sample.get('ts_code', sample.get('code', ''))
                print(f"[SCAN STEP 5]   样本股票L2诊断: code={code}", flush=True)
                self._debug_layer2_prescreen(code, days=prescreen_days)

        # V1.3.6：L2预筛条件通过数统计（全部统计，不是抽样）
        l2_cond_stats = {
            'rise_10d': 0, 'rise_20d': 0,
            'shrink': 0, 'expand': 0,
            'big_yang': 0, 'sideways': 0, 'breakout': 0,
            'rise': 0, 'volume': 0
        }
        l2_total = len(layer1_passed)
        if l2_total > 0:
            for stock in layer1_passed:
                code = stock.get('ts_code', stock.get('code', ''))
                cond = self._layer2_check_conditions(code, days=prescreen_days)
                for k in l2_cond_stats:
                    if cond.get(k):
                        l2_cond_stats[k] += 1
            # 更新FunnelStats
            self.funnel.l2_cond_rise = l2_cond_stats['rise']
            self.funnel.l2_cond_volume = l2_cond_stats['volume']
            self.funnel.l2_cond_big_yang = l2_cond_stats['big_yang']
            self.funnel.l2_cond_sideways = l2_cond_stats['sideways']
            self.funnel.l2_cond_breakout = l2_cond_stats['breakout']
            self.funnel.l2_cond_rise_10d = l2_cond_stats['rise_10d']
            self.funnel.l2_cond_rise_20d = l2_cond_stats['rise_20d']
            self.funnel.l2_cond_shrink = l2_cond_stats['shrink']
            self.funnel.l2_cond_expand = l2_cond_stats['expand']
            print(f"[L2] 条件统计(全部{l2_total}只):", flush=True)
            print(f"[L2]   近10日涨幅>12%: {l2_cond_stats['rise_10d']}只", flush=True)
            print(f"[L2]   近20日涨幅>20%: {l2_cond_stats['rise_20d']}只", flush=True)
            print(f"[L2]   缩量(5日<20日×0.5+连续3日): {l2_cond_stats['shrink']}只", flush=True)
            print(f"[L2]   放量(5日>20日×2.0+当日>1.5倍): {l2_cond_stats['expand']}只", flush=True)
            print(f"[L2]   近5日大阳线>9%: {l2_cond_stats['big_yang']}只", flush=True)
            print(f"[L2]   横盘(15日振幅<6%+CV<2.5%+均线粘合<2%): {l2_cond_stats['sideways']}只", flush=True)
            print(f"[L2]   真突破(收盘>20日高×1.0+放量>1.5倍): {l2_cond_stats['breakout']}只", flush=True)
            print(f"[L2]   OR逻辑总通过: {len(layer2_passed)}只", flush=True)

        if not layer2_passed:
            logger.warn("第二层预筛后无股票，扫描结束")
            self.funnel.time_total = time.time() - total_start
            logger.summary(self.funnel)
            return []

        # ============================================================
        # 第三层：深度模型分析（120日K线）
        # ============================================================
        logger.log("-" * 50)
        logger.log(f"第三层：深度分析（{deep_days}日K线 + 三模型 + AI评分）")
        layer3_start = time.time()
        # V1.3.7：L3并行配置检查
        l3_workers = self.parallel_scanner.max_workers if hasattr(self.parallel_scanner, 'max_workers') else 8
        print(f"[L3] 并行配置: workers={l3_workers}, throttle=0(内存读取), 待处理={len(layer2_passed)}只", flush=True)

        def deep_worker(stock_info):
            """第三层工作函数：深度分析 - V1.2.1增加异常统计"""
            code = stock_info.get('ts_code', stock_info.get('code', ''))
            name = stock_info.get('name', '')
            industry = stock_info.get('industry', stock_info.get('sector', ''))
            try:
                result, diag = self.scan_single_stock_with_diag(code, name, industry, days=deep_days)
            except Exception as e:
                print(f"[DEEP ERROR] {code}深度分析异常: {e}", flush=True)
                self.funnel.error_count += 1
                # V1.3.5：异常原因分类
                err_str = str(e).lower()
                if 'divide' in err_str or 'zero' in err_str or 'nan' in err_str:
                    self.funnel.l3_abnormal_divzero += 1
                elif 'kline' in err_str or 'data' in err_str or 'empty' in err_str or '不足' in err_str:
                    self.funnel.l3_abnormal_data += 1
                else:
                    self.funnel.l3_abnormal_other += 1
                return None
            if result is not None and result.score.total >= min_score:
                return result
            if diag.get('error') or diag.get('kline_empty'):
                self.funnel.error_count += 1
                if diag.get('kline_empty'):
                    self.funnel.kline_empty += 1
                    self.funnel.l3_abnormal_data += 1
                self._last_diagnostics.append(diag)
                if len(self._last_diagnostics) > 50:
                    self._last_diagnostics.pop(0)
            return None

        if use_parallel and len(layer2_passed) > 10:
            # 并行深度分析
            def progress_wrapper3(progress: ScanProgress):
                if progress_callback:
                    progress_callback(progress.processed, progress.total,
                                      f"深度:{progress.current_code}")

            results = self.parallel_scanner.scan_parallel(
                layer2_passed, deep_worker,
                stage="深度分析", progress_callback=progress_wrapper3,
                batch_size=50, throttle=0)  # V1.3.3：L3从内存缓存读取，无需节流
        else:
            # 串行深度分析
            results = []
            for i, stock in enumerate(layer2_passed):
                r = deep_worker(stock)
                if r:
                    results.append(r)
                if progress_callback and (i % 20 == 0 or i == len(layer2_passed) - 1):
                    progress_callback(i + 1, len(layer2_passed), "深度分析")

        self.funnel.layer3_deep_analysis = len(results)
        self.funnel.time_layer3 = time.time() - layer3_start
        # V1.3.2 精确定位：L3评分分布
        score_dist = {'0-60': 0, '60-70': 0, '70-80': 0, '80-90': 0, '90-100': 0}
        l3_total = len(layer2_passed)
        l3_abnormal = self.funnel.error_count
        for r in results:
            s = r.score.total
            if s < 60: score_dist['0-60'] += 1
            elif s < 70: score_dist['60-70'] += 1
            elif s < 80: score_dist['70-80'] += 1
            elif s < 90: score_dist['80-90'] += 1
            else: score_dist['90-100'] += 1
        l3_avg = self.funnel.time_layer3 / l3_total if l3_total else 0
        print(f"[SCAN STEP 6] L3深度分析: 完成={len(results)}, 异常={l3_abnormal}, "
              f"耗时={self.funnel.time_layer3:.1f}s, 每只平均={l3_avg:.3f}s", flush=True)
        print(f"[SCAN STEP 6]   评分分布: 0-60={score_dist['0-60']}, 60-70={score_dist['60-70']}, "
              f"70-80={score_dist['70-80']}, 80-90={score_dist['80-90']}, 90-100={score_dist['90-100']}", flush=True)
        if len(results) == 0:
            print(f"[SCAN STEP 6] 警告: L3深度分析后为0！检查评分计算是否有异常（数据格式/字段缺失）", flush=True)

        # ============================================================
        # 漏斗统计
        # ============================================================
        # V1.3.5：初始化模型分数列表
        self.funnel.model_limit_up_scores = []
        self.funnel.model_box_scores = []
        self.funnel.model_volume_scores = []
        for result in results:
            if result.kline_data.get('_is_candidate', False):
                self.funnel.behavior_candidates += 1
            for m in result.matched_models:
                if m.matched:
                    if m.model_name == MODEL_LIMIT_PULLBACK:
                        self.funnel.model_limit_up += 1
                        self.funnel.model_limit_up_scores.append(m.score)
                    elif m.model_name == MODEL_BOX_BREAKOUT:
                        self.funnel.model_box += 1
                        self.funnel.model_box_scores.append(m.score)
                    elif m.model_name == MODEL_VOLUME_BREAKOUT:
                        self.funnel.model_volume += 1
                        self.funnel.model_volume_scores.append(m.score)
            if result.score.total >= 60:
                self.funnel.score_60_plus += 1
            if result.score.total >= 70:
                self.funnel.score_70_plus += 1
            if result.score.total >= 80:
                self.funnel.score_80_plus += 1
            if result.score.total >= 90:
                self.funnel.score_90_plus += 1
            if result.buy_signal.buy_level == BUY_B1:
                self.funnel.buy_b1 += 1
            elif result.buy_signal.buy_level == BUY_B2:
                self.funnel.buy_b2 += 1
            elif result.buy_signal.buy_level == BUY_B3:
                self.funnel.buy_b3 += 1

        # 排序
        results.sort(key=lambda x: x.score.total, reverse=True)
        self.funnel.final_pool = len(results)
        self.funnel.time_total = time.time() - total_start

        # V1.3.2 精确定位：步骤7-8
        print(f"[SCAN STEP 7] 评分60以上: {self.funnel.score_60_plus}只 "
              f"(70+:{self.funnel.score_70_plus} 80+:{self.funnel.score_80_plus} 90+:{self.funnel.score_90_plus})", flush=True)
        print(f"[SCAN STEP 8] 最终股票池: {len(results)}只 "
              f"(B1:{self.funnel.buy_b1} B2:{self.funnel.buy_b2} B3:{self.funnel.buy_b3})", flush=True)

        # V1.3.5：完整9步漏斗统计
        self._last_results = results
        self._print_funnel_summary()

        if results:
            print(f"[SCAN RESULT] 前5只股票:", flush=True)
            for i, r in enumerate(results[:5]):
                matched = r.matched_models[0].model_name if r.matched_models else '无'
                print(f"[SCAN RESULT]   [{i+1}] code={r.code}, name={r.name}, "
                      f"score={r.score.total:.1f}, model={matched}, buy={r.buy_signal.buy_level}", flush=True)
        else:
            print(f"[SCAN RESULT] 最终股票池为空！请检查上方各步骤日志定位问题", flush=True)
            if self.funnel.score_60_plus > 0:
                print(f"[SCAN RESULT] 注意: 评分60+有{self.funnel.score_60_plus}只但最终池为0，检查结果过滤逻辑", flush=True)

        # 输出日志
        logger.step(6, "第三层深度分析", len(results),
                    f"耗时{self.funnel.time_layer3:.1f}s")
        logger.step(7, "评分60以上", self.funnel.score_60_plus,
                    f"70+:{self.funnel.score_70_plus} 80+:{self.funnel.score_80_plus} 90+:{self.funnel.score_90_plus}")
        logger.step(8, "最终股票池", self.funnel.final_pool,
                    f"B1:{self.funnel.buy_b1} B2:{self.funnel.buy_b2} B3:{self.funnel.buy_b3}")
        logger.log(f"总耗时: {self.funnel.time_total:.1f}秒 "
                   f"(L1:{self.funnel.time_layer1:.1f}s L2:{self.funnel.time_layer2:.1f}s L3:{self.funnel.time_layer3:.1f}s)")

        if self.funnel.error_count > 0:
            logger.warn(f"异常股票: {self.funnel.error_count}只")
        if self.funnel.kline_empty > 0:
            logger.warn(f"K线为空: {self.funnel.kline_empty}只")

        logger.summary(self.funnel)

        # V1.2.1：调试日志 - 打印最终结果数量和前3只关键字段
        print(f"[SCAN DEBUG] 最终结果数量: {len(results)}", flush=True)
        for i, r in enumerate(results[:3]):
            print(f"[SCAN DEBUG] 结果[{i}]: code={r.code}, name={r.name}, "
                  f"score={r.score.total}, model={r.best_model}, "
                  f"stage={r.current_stage}, buy={r.buy_signal.buy_level}", flush=True)
        if len(results) == 0:
            print(f"[SCAN DEBUG] 结果为空！漏斗: 主板={self.funnel.main_board_count} "
                  f"L1={self.funnel.layer1_basic_filter} L2={self.funnel.layer2_behavior_prescreen} "
                  f"L3={self.funnel.layer3_deep_analysis} 异常={self.funnel.error_count} "
                  f"K线空={self.funnel.kline_empty}", flush=True)

        # V1.2.3：自动保存扫描结果到缓存
        if results:
            self.scan_cache.save_scan_result(results, self.funnel, scan_mode)

        # V1.2.4：K线缓存统计和清理
        stats = self.kline_db.cache_stats()
        if stats.get('available'):
            print(f"[KLINE CACHE] 本次扫描: 命中{self._kline_cache_hits}次, "
                  f"未命中{self._kline_cache_misses}次 | "
                  f"已缓存{stats['stock_count']}只股票, 共{stats['kline_count']}根K线, "
                  f"占用{stats['file_size_mb']}MB", flush=True)
        # 清理过期缓存
        self.kline_db.clean_expired(days=30)
        # 重置计数器
        self._kline_cache_hits = 0
        self._kline_cache_misses = 0

        return results

    def load_cached_scan(self) -> Optional[List]:
        """V1.2.3：加载缓存的扫描结果，有效则直接返回，无效返回None"""
        results, cache_info, is_valid = self.scan_cache.load_scan_result()
        if is_valid and results:
            # 恢复漏斗统计
            self._last_results = results
            return results
        return None

    def get_cache_info(self) -> Dict:
        """V1.2.3：获取缓存信息"""
        return self.scan_cache.get_cache_info()

    def clear_scan_cache(self):
        """V1.2.3：清除扫描缓存"""
        self.scan_cache.clear_cache()

    def scan_single_stock_with_diag(self, code: str, name: str = "", industry: str = "",
                                      days: int = 120):
        """扫描单只股票 - 返回(result, diagnostic)
        V1.2：增加days参数，支持30日预筛和120日深度分析
        """
        diag = {'code': code, 'name': name, 'error': None,
                'kline_empty': False, 'data_insufficient': False, 'no_candidate': False,
                'bars_count': 0, 'behaviors': [], 'matched_models': [],
                'score': 0, 'buy_level': ''}

        # V1.3.12：data_provider为None时不直接返回，尝试通过通达信等备用接口获取K线
        if self.data_provider is None:
            print(f"[DIAG] {code} 数据提供者未初始化，尝试通过通达信/备用接口获取K线", flush=True)

        # 步骤4：获取K线（V1.2.1：使用_get_kline_with_fallback，优先聚宽降级现有接口）
        try:
            kline_data = self._get_kline_with_fallback(code, days=days)
        except Exception as e:
            diag['error'] = f'K线获取异常: {e}'
            return None, diag

        if not kline_data:
            diag['kline_empty'] = True
            return None, diag
        self.funnel.kline_fetch_ok += 1

        # 步骤5：解析K线（兼容List[Dict]和Dict格式）
        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        except Exception as e:
            diag['error'] = f'K线解析异常: {e}'
            return None, diag

        diag['bars_count'] = len(bars)
        if len(bars) < 10:
            diag['data_insufficient'] = True
            diag['error'] = f'K线根数不足: {len(bars)}<10'
            return None, diag
        self.funnel.kline_parse_ok += 1

        if len(bars) < 20:
            diag['data_insufficient'] = True
            # 不直接返回，继续尝试分析（数据少也可能有信号）
        else:
            self.funnel.basic_data_ok += 1

        # 步骤6：第一层候选检测
        try:
            candidate = self.candidate_detector.detect(bars, closes, highs, lows, volumes)
        except Exception as e:
            diag['error'] = f'候选检测异常: {e}'
            return None, diag

        # V1.1.1修复：kline_data可能是List[Dict]，不能用字符串索引
        # 用独立metadata存储候选信息
        kline_metadata = {
            '_is_candidate': candidate['is_candidate'],
            '_behaviors': candidate['behaviors'],
        }
        diag['behaviors'] = candidate['behaviors']

        if not candidate['is_candidate']:
            diag['no_candidate'] = True
            return None, diag

        # 实时行情
        price = closes[-1]
        pct_chg = bars[-1].pct_chg
        try:
            realtime = self.data_provider.get_realtime_quotes([code])
            if realtime and len(realtime) > 0:
                rt = realtime[0]
                price = rt.get('price', rt.get('close', price))
                pct_chg = rt.get('pct_chg', rt.get('change_percent', pct_chg))
        except Exception:
            pass

        # 步骤7-9：三个模型独立评分（OR逻辑）
        try:
            matches = [
                self.model_limit.analyze(bars, closes, highs, lows, volumes),
                self.model_box.analyze(bars, closes, highs, lows, volumes),
                self.model_volume.analyze(bars, closes, highs, lows, volumes),
            ]
        except Exception as e:
            diag['error'] = f'模型分析异常: {e}'
            return None, diag

        matched_models = [m for m in matches if m.matched]
        best_model = max(matched_models, key=lambda m: m.score) if matched_models else None
        best_model_name = best_model.model_name if best_model else ""
        best_model_score = best_model.score if best_model else 0
        diag['matched_models'] = [m.model_name for m in matched_models]

        # 步骤10：AI综合评分
        try:
            score = self.scoring.score(bars, closes, highs, lows, volumes, matches)
        except Exception as e:
            diag['error'] = f'AI评分异常: {e}'
            score = AIScore(total=30.0, level=SCORE_LOW, reason=f'评分异常: {e}')
        diag['score'] = score.total

        # 步骤11：买点确认
        try:
            buy_sell = self.signal_detector.detect(bars, closes, highs, lows, volumes, matches)
        except Exception as e:
            diag['error'] = f'买卖点检测异常: {e}'
            buy_sell = BuySellSignal()
        diag['buy_level'] = buy_sell.buy_level

        # K线6色标注
        try:
            annotation = self.annotation_gen.generate(bars, closes, highs, lows, volumes, matches, buy_sell)
        except Exception:
            annotation = KlineAnnotation()

        # 支撑/压力位
        support = min((m.support for m in matched_models if m.support > 0), default=bars[-1].low)
        pressure = max((m.pressure for m in matched_models if m.pressure > 0), default=bars[-1].high)

        # 汇总
        current_stage = best_model.stage if best_model else (candidate['behaviors'][0] if candidate['behaviors'] else "")
        buy_signals = list(dict.fromkeys(s for m in matched_models for s in m.signals))
        risk_warnings = list(dict.fromkeys(r for m in matched_models for r in m.risks))

        result = StockScanResult(
            code=code, name=name,
            price=round(float(price), 2), pct_chg=round(float(pct_chg), 2),
            industry=industry, matched_models=matches,
            best_model=best_model_name, best_model_score=best_model_score,
            current_stage=current_stage, buy_signal=buy_sell,
            risk_warnings=risk_warnings,
            support=round(float(support), 2), pressure=round(float(pressure), 2),
            score=score, annotation=annotation, kline_data=kline_metadata,
            scan_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            funnel_stage='行为候选' if candidate['is_candidate'] else '过滤',
        )

        self._cache[code] = {'result': result, 'time': time.time()}
        return result, diag

    def scan_single_stock(self, code: str, name: str = "", industry: str = "") -> Optional[StockScanResult]:
        """扫描单只股票 - 兼容旧接口"""
        result, _ = self.scan_single_stock_with_diag(code, name, industry)
        return result

    def diagnose_stock(self, code: str, name: str = "", industry: str = "") -> Dict:
        """单股票完整诊断 - 用于测试按钮"""
        result, diag = self.scan_single_stock_with_diag(code, name, industry)
        if result:
            diag['result'] = '成功'
            diag['best_model'] = result.best_model
            diag['best_model_score'] = result.best_model_score
            diag['score_level'] = result.score.level
            diag['score_breakdown'] = result.score.breakdown
            diag['buy_level'] = result.buy_signal.buy_level
            diag['buy_reasons'] = result.buy_signal.buy_reasons
            diag['sell_level'] = result.buy_signal.sell_level
            diag['risk_level'] = result.buy_signal.risk_level
            diag['support'] = result.support
            diag['pressure'] = result.pressure
            diag['current_stage'] = result.current_stage
            # V1.3.12：添加K线标注数据
            if result.annotation:
                diag['annotation_regions'] = result.annotation.regions
                diag['annotation_markers'] = result.annotation.markers
        else:
            diag['result'] = '失败'
        return diag

    def get_diagnostics(self) -> List[Dict]:
        return self._last_diagnostics

    def _pre_filter(self, stock_info: Dict) -> bool:
        """初筛：排除ST/退市/价格异常"""
        name = stock_info.get('name', '')
        if 'ST' in name or 'st' in name or '*ST' in name or '退' in name:
            return False
        # V1.1.1修复：价格字段缺失时跳过检查，不用0作为默认值
        price_raw = stock_info.get('price', stock_info.get('close', None))
        if price_raw is not None:
            try:
                price = float(price_raw)
                if price > 0 and (price < 1.5 or price > 300):
                    return False
            except (ValueError, TypeError):
                pass
        return True

    # ============================================================
    # V1.2：市场范围过滤
    # ============================================================

    def _get_fallback_stock_list(self) -> List[Dict]:
        """V1.2.2：备用股票列表 - 当数据提供者get_stock_list失败时使用

        生成主板股票代码范围列表，L1会用K线数据过滤掉不存在的股票。
        上海主板：600000-603999
        深圳主板：000001-002999
        """
        stock_list = []
        # 上海主板 600000-603999
        for i in range(0, 4000):
            code = f"60{i:04d}" if i < 1000 else f"60{i:04d}"
            # 修正：600000-603999
            code = f"60{i:04d}"
            stock_list.append({'ts_code': code, 'code': code, 'name': f'沪市{code}', 'industry': '', 'market': 'SH'})
        # 深圳主板 000001-002999
        for i in range(1, 3000):
            code = f"00{i:04d}"
            stock_list.append({'ts_code': code, 'code': code, 'name': f'深市{code}', 'industry': '', 'market': 'SZ'})
        print(f"[FALLBACK] 生成备用股票列表: {len(stock_list)}只（沪市4000+深市2999）", flush=True)
        return stock_list

    def _filter_board(self, stock_list: List[Dict]) -> List[Dict]:
        """
        主板过滤：只保留上海主板(60xxxx)和深圳主板(000xxx)
        排除：创业板(300xxx)、科创板(688xxx)、北交所(8xxxx/4xxxx)、ST
        """
        main_board = []
        for stock in stock_list:
            code = stock.get('ts_code', stock.get('code', ''))
            name = stock.get('name', '')
            # ST排除
            if 'ST' in name or 'st' in name or '*ST' in name or '退' in name:
                continue
            # 主板判断：60开头(沪市主板) 或 000/001开头(深市主板)
            code_clean = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            if code_clean.startswith('60') or code_clean.startswith('000') or code_clean.startswith('001'):
                main_board.append(stock)
        return main_board

    # ============================================================
    # V1.2.1：第一层基础筛选（聚宽批量行情优先，K线最新值降级）
    # ============================================================

    def _layer1_basic_filter(self, stock_list: List[Dict],
                              progress_callback=None,
                              prescreen_days: int = 30) -> List[Dict]:
        """
        V1.2.5：第一层基础筛选（只用行情数据，不获取K线）

        数据源策略：
        1. 股票列表自带行情（东方财富返回）→ 直接过滤，零额外网络请求
        2. 股票列表无行情 → 腾讯批量行情补充（一次50只，约10-20秒）
        3. 都失败 → L1不做过滤，全部通过，让L2用K线数据过滤

        过滤条件（只用行情数据）：
        1. 价格异常排除（<1元 或 >500元）
        2. 无成交排除（成交量=0 且 成交额=0）
        3. 单日跌幅>9.5%排除（大跌股）
        4. ST股票排除（名称含ST）

        Args:
            stock_list: 主板股票列表
            progress_callback: 进度回调
            prescreen_days: 保留参数兼容（V1.2.5不再使用）

        Returns:
            通过筛选的股票列表
        """
        total = len(stock_list)
        if total == 0:
            return []

        # 重置L1细分统计
        self.funnel.l1_price_abnormal = 0
        self.funnel.l1_no_volume = 0
        self.funnel.l1_big_drop = 0

        # ============================================================
        # 策略1：股票列表自带行情数据（东方财富返回）→ 零额外请求
        # ============================================================
        if getattr(self, '_stock_list_has_quotes', False):
            print(f"[L1] 股票列表自带行情数据，直接过滤（零额外网络请求）", flush=True)
            passed = []
            for i, stock in enumerate(stock_list):
                code = stock.get('ts_code', stock.get('code', ''))
                name = stock.get('name', '')
                price = float(stock.get('price', 0))
                change_pct = float(stock.get('change_pct', 0))
                volume = float(stock.get('volume', 0))
                amount = float(stock.get('amount', 0))

                # V1.3.3 价格异常：price<=0 或 <1元 或 >500元都过滤
                if price <= 0 or price < 1.0 or price > 500:
                    self.funnel.l1_price_abnormal += 1
                    if self.funnel.l1_price_abnormal <= 10:
                        print(f"[L1 FILTER] 价格异常过滤: code={code}, price={price}", flush=True)
                    continue
                # 无成交（成交量=0 且 成交额=0）
                if (volume is None or volume <= 0) and (amount is None or amount <= 0):
                    self.funnel.l1_no_volume += 1
                    continue
                # 单日跌幅>9.5%
                if change_pct < -9.5:
                    self.funnel.l1_big_drop += 1
                    continue
                # ST股票
                if 'ST' in name.upper() or '*ST' in name.upper():
                    continue

                passed.append(stock)
                if progress_callback and (i % 100 == 0 or i == total - 1):
                    progress_callback(i + 1, total, f"L1基础筛选:{code}")

            if progress_callback:
                progress_callback(total, total, "L1基础筛选完成")
            print(f"[L1] 自带行情过滤完成: {total}→{len(passed)}只 "
                  f"(价格异常{self.funnel.l1_price_abnormal} 无成交{self.funnel.l1_no_volume} "
                  f"大跌{self.funnel.l1_big_drop})", flush=True)
            return passed

        # ============================================================
        # 策略2：腾讯批量行情补充（股票列表无行情数据时）
        # ============================================================
        print(f"[L1] 股票列表无行情数据，使用腾讯批量行情补充: {total}只...", flush=True)
        try:
            from data.tencent_quote import get_batch_quotes
            codes = [s.get('ts_code', s.get('code', '')) for s in stock_list]
            quotes = get_batch_quotes(codes)
            if quotes:
                print(f"[L1] 腾讯批量行情获取成功: {len(quotes)}/{total}只", flush=True)
                passed = []
                for i, stock in enumerate(stock_list):
                    code = stock.get('ts_code', stock.get('code', ''))
                    name = stock.get('name', '')
                    q = quotes.get(code, {})
                    price = float(q.get('price', 0))
                    change_pct = float(q.get('change_pct', 0))
                    volume = float(q.get('volume', 0))
                    amount = float(q.get('amount', 0))

                    # 行情获取失败的股票也通过（让L2用K线过滤）
                    if not q:
                        passed.append(stock)
                        continue

                    # 价格异常
                    if price > 0 and (price < 1.0 or price > 500):
                        self.funnel.l1_price_abnormal += 1
                        continue
                    # 无成交
                    if volume == 0 and amount == 0:
                        self.funnel.l1_no_volume += 1
                        continue
                    # 单日跌幅>9.5%
                    if change_pct < -9.5:
                        self.funnel.l1_big_drop += 1
                        continue
                    # ST
                    if 'ST' in name.upper():
                        continue

                    passed.append(stock)
                    if progress_callback and (i % 100 == 0 or i == total - 1):
                        progress_callback(i + 1, total, f"L1基础筛选:{code}")

                if progress_callback:
                    progress_callback(total, total, "L1基础筛选完成")
                print(f"[L1] 腾讯行情过滤完成: {total}→{len(passed)}只", flush=True)
                return passed
            else:
                print("[L1 WARN] 腾讯批量行情获取失败，跳过L1过滤，全部通过", flush=True)
        except Exception as e:
            print(f"[L1 WARN] 腾讯批量行情异常: {e}，跳过L1过滤，全部通过", flush=True)

        # ============================================================
        # 策略3：都失败 → L1不做过滤，全部通过，让L2用K线数据过滤
        # ============================================================
        if progress_callback:
            progress_callback(total, total, "L1基础筛选完成（跳过）")
        return stock_list

    # ============================================================
    # V1.2：第二层行为预筛（只加载近30日K线，轻量计算）
    # ============================================================

    def _print_funnel_summary(self):
        """V1.3.5：打印完整9步筛选漏斗统计"""
        f = self.funnel
        print(f"\n{'='*70}", flush=True)
        print(f"[SCAN FUNNEL] 强势主力行为选股 - 筛选漏斗统计", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"[步骤1] 全市场股票:              {f.total_market}只", flush=True)
        print(f"[步骤2] 主板/ST过滤:             {f.main_board_count}只 "
              f"(过滤{f.total_market - f.main_board_count}只: 创业板/科创板/北交所/ST)", flush=True)
        print(f"[步骤3] L1基础筛选(行情):        {f.layer1_basic_filter}只 "
              f"(过滤{f.main_board_count - f.layer1_basic_filter}只: "
              f"价格异常{f.l1_price_abnormal}/无成交{f.l1_no_volume}/大跌{f.l1_big_drop})", flush=True)
        print(f"[步骤4] L2行为预筛({30}日K线):    {f.layer2_behavior_prescreen}只 "
              f"(过滤{f.layer1_basic_filter - f.layer2_behavior_prescreen}只)", flush=True)
        print(f"         条件统计(全部): 10日涨幅>8%={f.l2_cond_rise_10d}/"
              f"20日涨幅>15%={f.l2_cond_rise_20d}/"
              f"缩量={f.l2_cond_shrink}/放量={f.l2_cond_expand}/"
              f"大阳线>7%={f.l2_cond_big_yang}/"
              f"横盘={f.l2_cond_sideways}/突破={f.l2_cond_breakout}", flush=True)
        print(f"[步骤5] L3深度分析(120日K线):   {f.layer3_deep_analysis}只 "
              f"(完成{f.layer3_deep_analysis}, 异常{f.error_count}: "
              f"数据不足{f.l3_abnormal_data}/除以0{f.l3_abnormal_divzero}/其他{f.l3_abnormal_other})", flush=True)
        # 模型评分分布
        lu_avg = np.mean(f.model_limit_up_scores) if f.model_limit_up_scores else 0
        box_avg = np.mean(f.model_box_scores) if f.model_box_scores else 0
        vol_avg = np.mean(f.model_volume_scores) if f.model_volume_scores else 0
        print(f"[步骤6] 模型评分分布:", flush=True)
        print(f"         涨停回调匹配: {f.model_limit_up}只 (平均{lu_avg:.1f}分)", flush=True)
        print(f"         箱体突破匹配: {f.model_box}只 (平均{box_avg:.1f}分)", flush=True)
        print(f"         量价突破匹配: {f.model_volume}只 (平均{vol_avg:.1f}分)", flush=True)
        # AI综合评分分布
        print(f"[步骤7] AI综合评分分布:", flush=True)
        print(f"         90-100分: {f.score_90_plus}只 (强势启动候选)", flush=True)
        print(f"         80-90分:  {f.score_80_plus - f.score_90_plus}只 (重点观察)", flush=True)
        print(f"         70-80分:  {f.score_70_plus - f.score_80_plus}只 (普通观察)", flush=True)
        print(f"         60-70分:  {f.score_60_plus - f.score_70_plus}只 (观察池)", flush=True)
        print(f"         <60分:    {f.layer3_deep_analysis - f.score_60_plus}只 (过滤)", flush=True)
        # 买点分布
        no_buy = f.layer3_deep_analysis - f.buy_b1 - f.buy_b2 - f.buy_b3
        print(f"[步骤8] 买点分布:", flush=True)
        print(f"         B3强势: {f.buy_b3}只", flush=True)
        print(f"         B2确认: {f.buy_b2}只", flush=True)
        print(f"         B1观察: {f.buy_b1}只", flush=True)
        print(f"         无买点: {max(0, no_buy)}只", flush=True)
        # 最终股票池
        results = getattr(self, '_last_results', [])
        avg_score = np.mean([r.score.total for r in results]) if results else 0
        print(f"[步骤9] 最终股票池:              {f.final_pool}只 (平均{avg_score:.1f}分)", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"[SCAN FUNNEL] 总耗时: {f.time_total:.1f}秒 "
              f"(L1:{f.time_layer1:.1f}s L2:{f.time_layer2:.1f}s L3:{f.time_layer3:.1f}s)", flush=True)
        print(f"{'='*70}\n", flush=True)

        # V1.3.5：某一步过滤后=0的警告
        if f.main_board_count == 0:
            print(f"[SCAN WARN] 步骤2主板过滤后为0！检查_filter_board逻辑（是否过滤了001开头等）", flush=True)
        if f.layer1_basic_filter == 0:
            print(f"[SCAN WARN] 步骤3 L1过滤后为0！检查行情数据（价格/成交量是否为0或None）", flush=True)
        if f.layer2_behavior_prescreen == 0:
            print(f"[SCAN WARN] 步骤4 L2预筛后为0！检查预筛条件是否太严（5个条件OR逻辑）", flush=True)
        if f.layer3_deep_analysis == 0:
            print(f"[SCAN WARN] 步骤5 L3深度分析后为0！检查评分计算是否有异常（数据格式/字段缺失）", flush=True)
        if f.final_pool == 0 and f.layer3_deep_analysis > 0:
            print(f"[SCAN WARN] 步骤9最终池为0但L3有{f.layer3_deep_analysis}只！检查min_score阈值（当前{60}分）", flush=True)

    def _load_name_cache(self) -> Dict[str, str]:
        """V1.3.7：加载股票名称缓存（7天有效）"""
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cache', 'stock_names.json')
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # V1.3.7补充：7天有效期（7×24×3600秒）
                update_time = data.get('update_time', 0)
                now = time.time()
                if now - update_time < 7 * 24 * 3600:
                    names = data.get('names', {})
                    print(f"[SCAN] 名称缓存: 有效({len(names)}只), 更新于{time.strftime('%Y-%m-%d', time.localtime(update_time))}, 剩余{int((7*24*3600 - (now-update_time))/3600)}小时", flush=True)
                    return names
                else:
                    print(f"[SCAN] 名称缓存已过期(超过7天)，重新获取", flush=True)
                    return {}
        except Exception as e:
            print(f"[SCAN WARN] 名称缓存加载失败: {e}", flush=True)
        return {}

    def _save_name_cache(self, name_map: Dict[str, str]):
        """V1.3.7：保存股票名称缓存（记录update_time时间戳）"""
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'stock_names.json')
        try:
            data = {
                'update_time': time.time(),
                'update_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(name_map),
                'names': name_map
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SCAN WARN] 名称缓存保存失败: {e}", flush=True)

    def _data_health_check(self, stock_list: List[Dict]) -> bool:
        """V1.3.5：扫描前数据健康检查，检查K线数据有效性

        Returns:
            True表示可继续扫描，False表示数据全部异常应终止
        """
        print(f"\n[DATA HEALTH] {'='*10} 数据健康检查 {'='*10}", flush=True)
        total = len(stock_list)
        self.funnel.health_total = total
        valid = 0
        price_abnormal = 0
        vol_abnormal = 0
        insufficient = 0
        latest_dates = []

        # 抽样检查（最多200只，避免太慢）
        sample_size = min(200, total)
        sample_indices = list(range(sample_size)) if total <= 200 else \
            [int(i * total / sample_size) for i in range(sample_size)]

        for idx in sample_indices:
            stock = stock_list[idx]
            code = stock.get('ts_code', stock.get('code', ''))
            try:
                kline = self._get_kline_with_fallback(code, days=30)
                if not kline or len(kline) < 20:
                    insufficient += 1
                    continue
                latest = kline[-1]
                close_p = latest.get('close', latest.get('收盘价', 0))
                open_p = latest.get('open', latest.get('开盘价', 0))
                high_p = latest.get('high', latest.get('最高价', 0))
                low_p = latest.get('low', latest.get('最低价', 0))
                vol = latest.get('volume', latest.get('成交量', 0))

                if close_p <= 0 or open_p <= 0 or high_p <= 0 or low_p <= 0:
                    price_abnormal += 1
                    continue
                if vol <= 0:
                    vol_abnormal += 1
                    # 成交量异常但价格正常，仍算有效
                    valid += 1
                else:
                    valid += 1

                date_str = latest.get('date', latest.get('trade_date', ''))
                if date_str:
                    latest_dates.append(str(date_str))
            except Exception:
                insufficient += 1

        self.funnel.health_valid = valid
        self.funnel.health_price_abnormal = price_abnormal
        self.funnel.health_volume_abnormal = vol_abnormal
        self.funnel.health_insufficient = insufficient
        if latest_dates:
            self.funnel.health_latest_date = max(latest_dates)

        print(f"[DATA HEALTH] 待扫描股票: {total}只 (抽样检查{sample_size}只)", flush=True)
        print(f"[DATA HEALTH] K线数据有效: {valid}只 (close>0 且 open>0 且 high>0 且 low>0)", flush=True)
        print(f"[DATA HEALTH] 价格异常(close<=0): {price_abnormal}只", flush=True)
        print(f"[DATA HEALTH] 成交量异常(volume<=0): {vol_abnormal}只", flush=True)
        print(f"[DATA HEALTH] 缺少K线(根数<20): {insufficient}只", flush=True)
        print(f"[DATA HEALTH] 最新K线日期: {self.funnel.health_latest_date}", flush=True)
        print(f"[DATA HEALTH] 可参与筛选: {valid}只", flush=True)
        print(f"[DATA HEALTH] {'='*30}\n", flush=True)

        if valid == 0:
            print(f"[DATA HEALTH] 错误: K线数据全部异常！请检查通达信数据下载（盘后数据下载→日线数据）", flush=True)
            return False
        if valid < sample_size * 0.1:
            print(f"[DATA HEALTH] 警告: 有效K线比例过低({valid}/{sample_size})，扫描结果可能不准确", flush=True)
        return True

    def _layer2_check_conditions(self, code: str, days: int = 30) -> Dict:
        """V1.3.7：L2预筛条件详细检查（进一步收紧版，目标通过300-500只）

        新条件（OR逻辑，满足任意1个即通过）：
        1. 近10日涨幅>12% 或 近20日涨幅>20%
        2. 缩量：5日均量<20日均量×0.5 且 近3日连续缩量
        3. 放量：5日均量>20日均量×2.0 且 当日放量>1.5倍
        4. 近5日涨幅>9%的阳线(close>open)
        5. 横盘：15日振幅<6% 且 CV<2.5% 且 均线粘合(MA5/MA10/MA20偏差<2%)
        6. 突破：收盘>20日高×1.0(真突破) 且 放量>1.5倍

        Returns:
            详细条件字典
        """
        cond = {
            'rise_10d': False, 'rise_20d': False,
            'shrink': False, 'expand': False,
            'big_yang': False, 'sideways': False, 'breakout': False,
            'rise': False, 'volume': False, 'passed': False
        }
        kline_data = self._get_kline_with_fallback(code, days=days)
        if not kline_data:
            return cond
        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        except Exception:
            return cond
        if len(bars) < 20:
            return cond
        last_idx = len(bars) - 1

        # 条件1：近10日涨幅>12% 或 近20日涨幅>20%
        if last_idx >= 10 and closes[last_idx - 10] > 0:
            rise_10 = (closes[last_idx] - closes[last_idx - 10]) / closes[last_idx - 10] * 100
            if rise_10 > 12:
                cond['rise_10d'] = True
        if last_idx >= 20 and closes[last_idx - 20] > 0:
            rise_20 = (closes[last_idx] - closes[last_idx - 20]) / closes[last_idx - 20] * 100
            if rise_20 > 20:
                cond['rise_20d'] = True
        cond['rise'] = cond['rise_10d'] or cond['rise_20d']

        # 条件2：缩量：5日均量<20日均量×0.5 且 近3日连续缩量
        if len(volumes) >= 20:
            recent_5_vol = np.mean(volumes[-5:])
            prev_20_vol = np.mean(volumes[-25:-5]) if len(volumes) >= 25 else np.mean(volumes[:-5])
            if prev_20_vol > 0 and recent_5_vol < prev_20_vol * 0.5:
                # 近3日连续缩量：vol[-1] < vol[-2] < vol[-3]
                if (volumes[last_idx] < volumes[last_idx - 1] and
                        volumes[last_idx - 1] < volumes[last_idx - 2]):
                    cond['shrink'] = True

            # 条件3：放量：5日均量>20日均量×2.0 且 当日放量>1.5倍
            avg_5_vol = np.mean(volumes[-5:])
            if prev_20_vol > 0 and avg_5_vol > prev_20_vol * 2.0:
                if volumes[last_idx] > avg_5_vol * 1.5:
                    cond['expand'] = True
        cond['volume'] = cond['shrink'] or cond['expand']

        # 条件4：近5日涨幅>9%的阳线(close>open)
        if last_idx >= 5:
            for i in range(max(0, last_idx - 4), last_idx + 1):
                if closes[i] > opens[i] and opens[i] > 0:
                    pct = (closes[i] - opens[i]) / opens[i] * 100
                    if pct > 9:
                        cond['big_yang'] = True
                        break

        # 条件5：横盘：15日振幅<6% 且 CV<2.5% 且 均线粘合(MA5/MA10/MA20偏差<2%)（V1.3.7收紧）
        if last_idx >= 20:
            seg_15_high = np.max(highs[-15:])
            seg_15_low = np.min(lows[-15:])
            if seg_15_low > 0:
                amp_15 = (seg_15_high - seg_15_low) / seg_15_low * 100
                close_mean = np.mean(closes[-15:])
                close_std = np.std(closes[-15:])
                cv = close_std / close_mean * 100 if close_mean > 0 else 100
                # 均线粘合：MA5/MA10/MA20 偏差<2%
                ma5 = np.mean(closes[-5:])
                ma10 = np.mean(closes[-10:])
                ma20 = np.mean(closes[-20:])
                ma_avg = (ma5 + ma10 + ma20) / 3
                ma_dev = max(abs(ma5 - ma_avg), abs(ma10 - ma_avg), abs(ma20 - ma_avg)) / ma_avg * 100 if ma_avg > 0 else 100
                if amp_15 < 6 and cv < 2.5 and ma_dev < 2:
                    cond['sideways'] = True

        # 条件6：突破：收盘>20日高×1.0(真突破) 且 放量>1.5倍
        if last_idx >= 20:
            recent_20_high = np.max(highs[-20:-1])
            avg_5_vol = np.mean(volumes[-5:])
            if closes[last_idx] > recent_20_high * 1.0 and avg_5_vol > 0:
                if volumes[last_idx] > avg_5_vol * 1.5:
                    cond['breakout'] = True

        cond['passed'] = any([cond['rise'], cond['volume'], cond['big_yang'],
                               cond['sideways'], cond['breakout']])
        return cond

    def _layer2_behavior_prescreen(self, stock_info: Dict, days: int = 30) -> bool:
        """
        V1.3.6优化：第二层行为预筛（更严格条件，目标通过300-600只）

        新条件（OR逻辑，满足任意1个即通过）：
        1. 近10日涨幅>8% 或 近20日涨幅>15%
        2. 缩量(5日均量<20日均量×0.7) 或 放量(5日均量>20日均量×1.5)
        3. 近10日内有涨幅>7%的阳线(close>open)
        4. 近20日振幅<12% 且 收盘价标准差/均值<4%
        5. 收盘价>近20日最高价×0.98 且 当日成交量>5日均量×1.2
        """
        code = stock_info.get('ts_code', stock_info.get('code', ''))
        cond = self._layer2_check_conditions(code, days=days)
        return cond.get('passed', False)

    def _debug_layer2_prescreen(self, code: str, days: int = 30):
        """V1.3.2 调试：打印单只股票L2预筛5个条件详情 + K线数据格式检查"""
        print(f"[L2 DEBUG] ===== 股票{code} L2预筛诊断 =====", flush=True)
        kline_data = self._get_kline_with_fallback(code, days=days)
        if not kline_data:
            print(f"[L2 DEBUG] K线数据获取失败！", flush=True)
            return
        print(f"[L2 DEBUG] K线数据: {len(kline_data)}根", flush=True)
        # 数据格式检查：打印前1根和最后1根
        if kline_data:
            first = kline_data[0]
            last = kline_data[-1]
            print(f"[L2 DEBUG] 第1根: {first}", flush=True)
            print(f"[L2 DEBUG] 最后1根: {last}", flush=True)
            print(f"[L2 DEBUG] 字段名: {list(first.keys()) if isinstance(first, dict) else type(first)}", flush=True)

        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        except Exception as e:
            print(f"[L2 DEBUG] K线解析失败: {e}", flush=True)
            return

        print(f"[L2 DEBUG] 解析后: bars={len(bars)}, closes={len(closes)}, volumes={len(volumes)}", flush=True)
        if len(bars) < 10:
            print(f"[L2 DEBUG] K线不足10根，无法预筛", flush=True)
            return

        last_idx = len(bars) - 1

        # 条件1：近期涨幅
        cond1 = False
        if len(closes) >= 10:
            min_close = np.min(closes)
            max_close = np.max(closes)
            pct = (max_close - min_close) / min_close * 100 if min_close > 0 else 0
            cond1 = pct > 10
            print(f"[L2 DEBUG] 条件1-近期涨幅: min={min_close:.2f}, max={max_close:.2f}, 涨幅={pct:.1f}%, 通过={cond1}", flush=True)

        # 条件2：成交量变化
        cond2 = False
        if len(volumes) >= 10:
            recent_vol = np.mean(volumes[-5:])
            prev_vol = np.mean(volumes[:-5]) if len(volumes) > 5 else recent_vol
            vol_ratio = recent_vol / prev_vol if prev_vol > 0 else 1
            cond2 = vol_ratio < 0.8 or vol_ratio > 1.3
            print(f"[L2 DEBUG] 条件2-成交量: 近5日均量={recent_vol:.0f}, 前均量={prev_vol:.0f}, 比值={vol_ratio:.2f}, 通过={cond2}", flush=True)

        # 条件3：大阳线
        cond3 = False
        big_yang_count = 0
        for bar in bars:
            if bar.pct_chg >= BIG_YANG_THRESHOLD:
                big_yang_count += 1
                cond3 = True
        print(f"[L2 DEBUG] 条件3-大阳线: 大阳数量={big_yang_count}, 阈值={BIG_YANG_THRESHOLD}%, 通过={cond3}", flush=True)

        # 条件4：横盘
        cond4 = False
        if last_idx >= 10:
            seg_high = np.max(highs[-10:])
            seg_low = np.min(lows[-10:])
            amp = (seg_high - seg_low) / seg_low * 100 if seg_low > 0 else 100
            cond4 = amp < 8
            print(f"[L2 DEBUG] 条件4-横盘: 近10日高={seg_high:.2f}, 低={seg_low:.2f}, 振幅={amp:.1f}%, 通过={cond4}", flush=True)

        # 条件5：突破
        cond5 = False
        if last_idx >= 10:
            recent_10_high = np.max(highs[-10:-1]) if last_idx >= 11 else np.max(highs[:-1])
            cond5 = closes[last_idx] > recent_10_high * 0.98
            print(f"[L2 DEBUG] 条件5-突破: 最新收盘={closes[last_idx]:.2f}, 近10日高={recent_10_high:.2f}, 通过={cond5}", flush=True)

        final = cond1 or cond2 or cond3 or cond4 or cond5
        print(f"[L2 DEBUG] 最终结果: 通过={final} (cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}, cond5={cond5})", flush=True)

    def get_funnel(self) -> FunnelStats:
        return self.funnel


# ============================================================
# 主入口类
# ============================================================

class ForceBehaviorStrategy:
    """强势主力行为选股系统 V1.1 - 主入口"""

    _instance = None

    def __init__(self):
        self.scanner = MarketScanner()
        self._last_results: List[StockScanResult] = []
        self._last_funnel: FunnelStats = FunnelStats()
        self.version = "1.1.0"
        self.system_name = "强势主力行为选股系统"
        # V1.2.4：预加载状态
        self._preloading = False
        self._preload_finished = False

    @classmethod
    def instance(cls) -> 'ForceBehaviorStrategy':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # V1.2.4：预加载相关方法
    def is_preloading(self) -> bool:
        """是否正在预加载"""
        return self._preloading

    def is_preload_finished(self) -> bool:
        """预加载是否完成"""
        return self._preload_finished

    def quick_scan(self) -> List[StockScanResult]:
        """V1.2.4：快速扫描（用于后台预加载）"""
        self._preloading = True
        self._preload_finished = False
        try:
            results = self.scanner.scan_full_market(
                progress_callback=None, min_score=60.0, scan_mode="快速扫描"
            )
            self._last_results = results
            self._last_funnel = self.scanner.get_funnel()
            print(f"[PRELOAD] 强势主力行为选股预加载完成, {len(results)}只候选股", flush=True)
            return results
        except Exception as e:
            print(f"[PRELOAD] 预加载失败: {e}", flush=True)
            return []
        finally:
            self._preloading = False
            self._preload_finished = True

    def set_data_provider(self, provider):
        self.scanner.set_data_provider(provider)

    def scan(self, progress_callback=None, min_score: float = 60.0,
             max_stocks: Optional[int] = None, scan_mode: str = "快速扫描") -> List[StockScanResult]:
        """V1.2：三层扫描流程，支持快速/标准/深度模式"""
        self._last_results = self.scanner.scan_full_market(
            progress_callback=progress_callback, min_score=min_score,
            max_stocks=max_stocks, scan_mode=scan_mode)
        self._last_funnel = self.scanner.get_funnel()
        return self._last_results

    def analyze_stock(self, code: str, name: str = "", industry: str = "") -> Optional[StockScanResult]:
        return self.scanner.scan_single_stock(code, name, industry)

    def diagnose_stock(self, code: str, name: str = "", industry: str = "") -> Dict:
        """单股票完整诊断 - 用于测试按钮"""
        return self.scanner.diagnose_stock(code, name, industry)

    def get_diagnostics(self) -> List[Dict]:
        return self.scanner.get_diagnostics()

    def get_stock_pool(self) -> List[Dict]:
        """V1.1股票池：包含全部新增字段"""
        pool = []
        for r in self._last_results:
            matched_names = [m.model_name for m in r.matched_models if m.matched]
            model_scores = {m.model_name: m.score for m in r.matched_models if m.matched}
            pool.append({
                'name': r.name, 'code': r.code,
                'price': r.price, 'pct_chg': r.pct_chg,
                'industry': r.industry,
                'matched_models': matched_names,
                'model_scores': model_scores,
                'best_model': r.best_model,
                'best_model_score': r.best_model_score,
                'composite_score': r.score.total,
                'current_stage': r.current_stage,
                'buy_level': r.buy_signal.buy_level,
                'buy_reasons': r.buy_signal.buy_reasons,
                'sell_level': r.buy_signal.sell_level,
                'sell_reasons': r.buy_signal.sell_reasons,
                'risk_level': r.buy_signal.risk_level,
                'risk_warnings': r.risk_warnings,
                'support': r.support, 'pressure': r.pressure,
                'score_level': r.score.level,
                'score_breakdown': r.score.breakdown,
                'score_reason': r.score.reason,
            })
        return pool

    def get_funnel_stats(self) -> Dict:
        return self._last_funnel.to_dict()

    def get_funnel_summary(self) -> str:
        return self._last_funnel.summary()

    # V1.2.3：缓存相关方法
    def load_cached_scan(self) -> Optional[List[StockScanResult]]:
        """加载缓存的扫描结果，有效则返回，无效返回None"""
        results = self.scanner.load_cached_scan()
        if results:
            self._last_results = results
            self._last_funnel = self.scanner.get_funnel()
        return results

    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        return self.scanner.get_cache_info()

    def clear_scan_cache(self):
        """清除扫描缓存"""
        self.scanner.clear_scan_cache()

    def refresh_quotes(self, results: List[StockScanResult] = None) -> int:
        """V1.2.3：刷新当前股票池行情（不重新扫描）

        Args:
            results: 要刷新的股票列表，None则刷新_last_results

        Returns:
            成功刷新的股票数量
        """
        if results is None:
            results = self._last_results
        if not results:
            return 0
        count = 0
        codes = [r.code for r in results]
        try:
            # V1.2.4：优先使用腾讯批量行情（一次请求多只股票，1-2秒完成）
            tencent_quotes = None
            try:
                from data.tencent_quote import get_batch_quotes
                tencent_quotes = get_batch_quotes(codes)
            except Exception as e:
                print(f"[REFRESH] 腾讯批量行情失败: {e}, 降级到现有接口", flush=True)

            if tencent_quotes:
                # 腾讯批量行情成功
                for r in results:
                    q = tencent_quotes.get(r.code, {})
                    if q:
                        new_price = float(q.get('price', 0))
                        if new_price > 0:
                            r.price = new_price
                            r.pct_chg = float(q.get('change_pct', r.pct_chg))
                        count += 1
            else:
                # 降级：批量获取最新行情（现有接口）
                quotes = self.scanner.data_provider.get_realtime_quotes(codes)
                if quotes:
                    quotes_map = {}
                    for q in quotes:
                        code = q.get('code', q.get('ts_code', ''))
                        quotes_map[code] = q
                    for r in results:
                        q = quotes_map.get(r.code, {})
                        if q:
                            old_price = r.price
                            new_price = float(q.get('price', q.get('close', old_price)))
                            if new_price > 0:
                                r.price = new_price
                                if old_price > 0:
                                    r.pct_chg = (new_price - old_price) / old_price * 100
                            count += 1
                else:
                    # 批量行情失败，逐只获取K线最新价
                    for r in results:
                        try:
                            kline = self.scanner._get_kline_with_fallback(r.code, days=5)
                            if kline:
                                from strategy.base import KlineDataParser
                                bars, _, _, _, closes, volumes = KlineDataParser.parse(kline)
                                if closes:
                                    r.price = float(closes[-1])
                                    if len(closes) >= 2 and closes[-2] > 0:
                                        r.pct_chg = (closes[-1] - closes[-2]) / closes[-2] * 100
                                    count += 1
                        except Exception:
                            continue
        except Exception as e:
            print(f"[REFRESH] 刷新行情异常: {e}", flush=True)
        print(f"[REFRESH] 刷新行情完成: {count}/{len(results)}只", flush=True)
        return count

    def get_kline_annotation(self, code: str) -> Optional[KlineAnnotation]:
        for r in self._last_results:
            if r.code == code:
                return r.annotation
        result = self.analyze_stock(code)
        return result.annotation if result else None

    def get_kline_data(self, code: str, days: int = 120) -> Optional[Dict]:
        """V1.3.8：获取K线数据供ECharts渲染"""
        try:
            kline = self.scanner._get_kline_with_fallback(code, days=days)
            if not kline:
                return None
            from strategy.base import KlineDataParser
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
            dates = [b.date for b in bars]
            return {
                'dates': dates,
                'open': opens.tolist(),
                'high': highs.tolist(),
                'low': lows.tolist(),
                'close': closes.tolist(),
                'volume': volumes.tolist(),
            }
        except Exception as e:
            print(f"[KLINE DATA] 获取{code}K线数据失败: {e}", flush=True)
            return None

    def export_results(self, filepath: str) -> bool:
        try:
            data = {
                'system': self.system_name, 'version': self.version,
                'export_time': datetime.now().isoformat(),
                'funnel': self._last_funnel.to_dict(),
                'results': [r.to_dict() for r in self._last_results],
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False

    def get_model_info(self) -> List[Dict]:
        return [
            {'name': MODEL_LIMIT_PULLBACK, 'logic': '涨停/大阳→回调→缩量洗盘→支撑→再次启动',
             'tags': ['涨停回调', '缩量低吸', '强势洗盘']},
            {'name': MODEL_BOX_BREAKOUT, 'logic': '上涨→横盘→缩量筑平台→突破箱体→第二波',
             'tags': ['箱体突破', '二次启动', '平台蓄势']},
            {'name': MODEL_VOLUME_BREAKOUT, 'logic': '极限缩量筑底→量价齐升→突破→回踩→再次放量',
             'tags': ['量价突破', '主力启动', '二次确认']},
        ]

    def get_scoring_info(self) -> Dict:
        return {
            'total': 100,
            'dimensions': [
                {'name': '主力行为结构', 'weight': 40},
                {'name': '量价关系', 'weight': 20},
                {'name': '趋势均线', 'weight': 15},
                {'name': '涨停强势基因', 'weight': 10},
                {'name': '技术指标确认', 'weight': 10},
                {'name': '市场环境', 'weight': 5},
            ],
            'levels': [
                {'range': '90-100', 'level': SCORE_LAUNCH_CANDIDATE},
                {'range': '80-90', 'level': SCORE_STRONG_CANDIDATE},
                {'range': '70-80', 'level': SCORE_KEY_WATCH},
                {'range': '60-70', 'level': SCORE_WATCH},
                {'range': '60以下', 'level': SCORE_LOW},
            ],
        }


# ============================================================
# 便捷函数
# ============================================================

def get_force_behavior_strategy() -> ForceBehaviorStrategy:
    return ForceBehaviorStrategy.instance()


def analyze_kline(kline_data: Dict, name: str = "", code: str = "") -> Dict:
    """独立分析K线数据（V1.1：三层筛选）"""
    from dataclasses import asdict
    bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
    if len(bars) < 20:
        return {'error': '数据不足', 'bars_count': len(bars)}

    # 第一层：候选检测
    candidate = BehaviorCandidateDetector().detect(bars, closes, highs, lows, volumes)

    # 第二层：模型评分
    model_limit = LimitUpPullbackModel()
    model_box = BoxBreakoutModel()
    model_volume = VolumeBreakoutModel()
    matches = [
        model_limit.analyze(bars, closes, highs, lows, volumes),
        model_box.analyze(bars, closes, highs, lows, volumes),
        model_volume.analyze(bars, closes, highs, lows, volumes),
    ]

    # AI评分
    score = AIScoringSystem().score(bars, closes, highs, lows, volumes, matches)

    # 第三层：买卖点
    buy_sell = BuySellSignalDetector().detect(bars, closes, highs, lows, volumes, matches)

    # K线标注
    annotation = KlineAnnotationGenerator().generate(bars, closes, highs, lows, volumes, matches, buy_sell)

    matched = [m for m in matches if m.matched]
    best = max(matched, key=lambda m: m.score) if matched else None

    return {
        'code': code, 'name': name,
        'price': round(float(closes[-1]), 2),
        'pct_chg': round(float(bars[-1].pct_chg), 2),
        'is_candidate': candidate['is_candidate'],
        'behaviors': candidate['behaviors'],
        'matched_models': [asdict(m) for m in matches],
        'matched_count': len(matched),
        'best_model': best.model_name if best else '',
        'best_model_score': best.score if best else 0,
        'current_stage': best.stage if best else '',
        'buy_signal': asdict(buy_sell),
        'risk_warnings': list(dict.fromkeys(r for m in matched for r in m.risks)),
        'support': best.support if best else 0,
        'pressure': best.pressure if best else 0,
        'score': asdict(score),
        'annotation': asdict(annotation),
        'bars_count': len(bars),
    }


# ============================================================
# 独立运行入口
# ============================================================

if __name__ == '__main__':
    import numpy as np
    print("=" * 60)
    print("强势主力行为选股系统 V1.1 - 自检")
    print("=" * 60)

    strategy = ForceBehaviorStrategy()
    print(f"\n系统: {strategy.system_name} v{strategy.version}")
    print(f"模型: {[m['name'] for m in strategy.get_model_info()]}")
    print(f"评分等级: {[l['level'] for l in strategy.get_scoring_info()['levels']]}")

    # 模拟数据测试
    np.random.seed(42)
    n = 100
    base = 10.0
    closes = [base]
    for i in range(1, n):
        change = np.random.normal(0.002, 0.025)
        if i == 25:
            change = 0.099
        closes.append(closes[-1] * (1 + change))
    opens = [c * (1 + np.random.uniform(-0.01, 0.01)) for c in closes]
    highs = [max(o, c) * (1 + np.random.uniform(0, 0.015)) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1 - np.random.uniform(0, 0.015)) for o, c in zip(opens, closes)]
    volumes = [np.random.randint(50000, 200000) for _ in range(n)]
    for i in range(35, 50):
        volumes[i] = int(volumes[i] * 0.4)
    dates = [f"2026-{(i // 21 + 1):02d}-{(i % 21 + 1):02d}" for i in range(n)]

    test_kline = {'dates': dates, 'open': opens, 'high': highs, 'low': lows,
                  'close': closes, 'volume': volumes}
    result = analyze_kline(test_kline, name="测试股票", code="TEST001")
    print(f"\n模拟分析结果:")
    print(f"  候选: {result['is_candidate']}, 行为: {result['behaviors']}")
    print(f"  匹配模型: {result['matched_count']}, 最佳: {result['best_model']}({result['best_model_score']}分)")
    print(f"  综合评分: {result['score']['total']} ({result['score']['level']})")
    print(f"  买点: {result['buy_signal']['buy_level']}, 卖点: {result['buy_signal']['sell_level']}")
    print(f"  风险等级: {result['buy_signal']['risk_level']}")
    print(f"  支撑: {result['support']}, 压力: {result['pressure']}")
    print(f"  K线标注区域: {len(result['annotation']['regions'])}, 标记: {len(result['annotation']['markers'])}")

    print("\n" + "=" * 60)
    print("V1.1自检完成 OK")
    print("=" * 60)
