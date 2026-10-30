# -*- coding: utf-8 -*-
"""
V6.2 阶段3：全市场分层扫描器

四层逐级过滤扫描架构，解决当前固定500只扫描限制：

  L1 全市场基础过滤（2200+ → 主板/非ST/股价≥5/非停牌）
      ↓
  L2 技术过滤（MA趋势/成交量/KDJ/MACD/涨停历史，满足≥2项）
      ↓
  L3 多因子评分（技术面+资金面+趋势面，保留Top 200-500）
      ↓
  L4 AI深度分析（Top 50-100，三模型+六维+综合评分）

设计原则：
  - 独立模块，不修改现有策略核心逻辑
  - L1/L2使用通达信本地数据快速过滤
  - L3并行计算（8线程）
  - L4只对Top N做深度分析，避免全市场AI分析
  - 总扫描时间目标 <3分钟
"""

import os
import sys
import time
import json
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.tdx_data_engine import get_tdx_data_engine
from strategy.base import (
    TechnicalIndicators, KlineDataParser, KlineBar,
)
from strategy.ai_composite_score import AICompositeScoreEngine

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

# L1 基础过滤阈值
L1_MIN_PRICE = 5.0          # 最低股价
L1_MIN_VOLUME = 0           # 成交量>0（非停牌）

# L2 技术过滤通过条件数
L2_MIN_PASS_CONDITIONS = 2  # 至少满足2项技术条件

# L3 保留数量
L3_KEEP_COUNT = 300         # L3保留Top 300只

# L4 深度分析数量
L4_DEEP_COUNT = 80          # L4对Top 80只做深度分析

# 并行线程数
DEFAULT_WORKERS = 8

# K线读取天数
KLAY_DAYS_L2 = 60           # L2技术过滤用60天
KLAY_DAYS_L3 = 60           # L3多因子用60天
KLAY_DAYS_L4 = 120          # L4深度分析用120天


# ============================================================
# 扫描结果数据类
# ============================================================

@dataclass
class LayerStats:
    """单层扫描统计"""
    layer_name: str = ""
    input_count: int = 0
    pass_count: int = 0
    filter_count: int = 0
    elapsed_seconds: float = 0.0
    filter_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "layer_name": self.layer_name,
            "input_count": self.input_count,
            "pass_count": self.pass_count,
            "filter_count": self.filter_count,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "filter_reasons": dict(self.filter_reasons),
        }


@dataclass
class LayeredScanResult:
    """分层扫描最终结果"""
    code: str = ""
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    # L2 技术指标
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    volume_ratio: float = 0.0
    rps20: float = 0.0
    kdj_k: float = 0.0
    kdj_d: float = 0.0
    macd_dif: float = 0.0
    macd_dea: float = 0.0
    macd_hist: float = 0.0
    # L3 多因子评分
    factor_score: float = 0.0
    factor_technical: float = 0.0
    factor_fund: float = 0.0
    factor_trend: float = 0.0
    # L4 深度分析
    model_scores: Dict = field(default_factory=dict)
    best_model: str = ""
    best_model_score: float = 0.0
    composite_score: float = 0.0
    composite_grade: str = ""
    trading_advice: str = ""
    # 通用
    industry: str = ""
    scan_time: str = ""

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "price": round(self.price, 2),
            "change_pct": round(self.change_pct, 2),
            "ma5": round(self.ma5, 2),
            "ma10": round(self.ma10, 2),
            "ma20": round(self.ma20, 2),
            "ma60": round(self.ma60, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "rps20": round(self.rps20, 1),
            "kdj_k": round(self.kdj_k, 1),
            "kdj_d": round(self.kdj_d, 1),
            "macd_dif": round(self.macd_dif, 4),
            "macd_dea": round(self.macd_dea, 4),
            "macd_hist": round(self.macd_hist, 4),
            "factor_score": round(self.factor_score, 1),
            "factor_technical": round(self.factor_technical, 1),
            "factor_fund": round(self.factor_fund, 1),
            "factor_trend": round(self.factor_trend, 1),
            "model_scores": dict(self.model_scores),
            "best_model": self.best_model,
            "best_model_score": round(self.best_model_score, 1),
            "composite_score": round(self.composite_score, 1),
            "composite_grade": self.composite_grade,
            "trading_advice": self.trading_advice,
            "industry": self.industry,
            "scan_time": self.scan_time,
        }


# ============================================================
# 分层扫描器
# ============================================================

class LayeredScanner:
    """
    V6.2 全市场分层扫描器

    四层逐级过滤：L1基础过滤 → L2技术过滤 → L3多因子评分 → L4 AI深度分析
    """

    def __init__(self, max_workers: int = DEFAULT_WORKERS,
                 l3_keep: int = L3_KEEP_COUNT,
                 l4_deep: int = L4_DEEP_COUNT):
        """
        Args:
            max_workers: 并行线程数，默认8
            l3_keep: L3保留的股票数量，默认300
            l4_deep: L4深度分析的股票数量，默认80
        """
        self.max_workers = max_workers
        self.l3_keep = l3_keep
        self.l4_deep = l4_deep
        self.tdx = get_tdx_data_engine()
        self.composite_engine = AICompositeScoreEngine()
        self._stock_names: Dict[str, str] = {}
        self._load_stock_names()
        # 三模型（延迟初始化，避免L1/L2阶段不必要的导入开销）
        self._models = None

    def _load_stock_names(self):
        """加载股票名称映射（code -> name）"""
        path = os.path.join(PROJECT_ROOT, "data", "stock_names_full.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._stock_names = json.load(f)
                logger.info(f"[LayeredScanner] 加载股票名称: {len(self._stock_names)} 只")
        except Exception as e:
            logger.warning(f"[LayeredScanner] 加载股票名称失败: {e}")

    def _get_name(self, code: str) -> str:
        return self._stock_names.get(code, "")

    @staticmethod
    def _is_st_stock(name: str) -> bool:
        """判断是否为ST股票"""
        if not name:
            return False
        name_upper = name.upper()
        return "ST" in name_upper

    def _get_models(self):
        """延迟初始化三模型"""
        if self._models is None:
            from strategy.models.limit_up_pullback import LimitUpPullbackModel
            from strategy.models.box_breakout import BoxBreakoutModel
            from strategy.models.volume_breakout import VolumeBreakoutModel
            self._models = [
                LimitUpPullbackModel(),
                BoxBreakoutModel(),
                VolumeBreakoutModel(),
            ]
        return self._models

    # ============================================================
    # 主入口：四层全市场扫描
    # ============================================================

    def scan_full_market(self, progress_callback=None) -> Dict:
        """
        执行四层全市场扫描。

        Returns:
            {
                "final_candidates": [LayeredScanResult, ...],
                "layer_stats": [LayerStats, ...],
                "total_elapsed": float,
                "l2_stocks": [...],  # L2通过的股票（含技术指标）
                "l3_stocks": [...],  # L3评分后的股票
            }
        """
        total_start = time.time()
        all_stats = []

        print("=" * 60, flush=True)
        print("V6.2 全市场分层扫描 启动", flush=True)
        print("=" * 60, flush=True)

        # ---- L1 基础过滤 ----
        l1_stocks, l1_stats = self._layer1_basic_filter()
        all_stats.append(l1_stats)
        self._print_stats(l1_stats)

        if not l1_stocks:
            print("[ERROR] L1过滤后无股票，扫描终止", flush=True)
            return self._build_result([], all_stats, total_start)

        # ---- L2 技术过滤 ----
        l2_stocks, l2_stats = self._layer2_technical_filter(l1_stocks)
        all_stats.append(l2_stats)
        self._print_stats(l2_stats)

        if not l2_stocks:
            print("[ERROR] L2过滤后无股票，扫描终止", flush=True)
            return self._build_result([], all_stats, total_start)

        # ---- L3 多因子评分 ----
        l3_stocks, l3_stats = self._layer3_multi_factor_score(l2_stocks)
        all_stats.append(l3_stats)
        self._print_stats(l3_stats)

        if not l3_stocks:
            print("[ERROR] L3评分后无股票，扫描终止", flush=True)
            return self._build_result([], all_stats, total_start)

        # ---- L4 AI深度分析 ----
        l4_stocks, l4_stats = self._layer4_ai_deep_analysis(l3_stocks)
        all_stats.append(l4_stats)
        self._print_stats(l4_stats)

        total_elapsed = time.time() - total_start
        print("=" * 60, flush=True)
        print(f"扫描完成！最终候选: {len(l4_stocks)} 只, "
              f"总耗时: {total_elapsed:.1f}秒", flush=True)
        print("=" * 60, flush=True)

        return {
            "final_candidates": [s.to_dict() for s in l4_stocks],
            "layer_stats": [s.to_dict() for s in all_stats],
            "total_elapsed": round(total_elapsed, 2),
            "l2_count": len(l2_stocks),
            "l3_count": len(l3_stocks),
            "l4_count": len(l4_stocks),
        }

    # ============================================================
    # L1 全市场基础过滤
    # ============================================================

    def _layer1_basic_filter(self) -> Tuple[List[Dict], LayerStats]:
        """
        L1 全市场基础过滤：
          - 沪深主板（60开头 / 000/001开头）
          - 非ST / *ST
          - 股价 ≥ 5元
          - 非停牌（成交量 > 0）
          - 非退市（有最新K线数据）
        """
        stats = LayerStats(layer_name="L1_基础过滤")
        start = time.time()

        # 获取所有主板代码
        all_codes = self.tdx.get_all_main_board_codes()
        stats.input_count = len(all_codes)

        passed = []
        reasons = {"非主板": 0, "ST": 0, "价格<5": 0, "停牌/无数据": 0}

        for code in all_codes:
            name = self._get_name(code)

            # ST过滤
            if self._is_st_stock(name):
                reasons["ST"] += 1
                continue

            # 获取最新价格（从最近2根K线）
            latest = self.tdx.get_latest_price(code)
            if not latest or latest.get("price", 0) <= 0:
                reasons["停牌/无数据"] += 1
                continue

            price = latest["price"]
            volume = latest.get("volume", 0)

            # 股价过滤
            if price < L1_MIN_PRICE:
                reasons["价格<5"] += 1
                continue

            # 成交量过滤（非停牌）
            if volume <= L1_MIN_VOLUME:
                reasons["停牌/无数据"] += 1
                continue

            passed.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": latest.get("change_pct", 0),
                "volume": volume,
                "amount": latest.get("amount", 0),
            })

        stats.pass_count = len(passed)
        stats.filter_count = stats.input_count - stats.pass_count
        stats.elapsed_seconds = time.time() - start
        stats.filter_reasons = reasons

        return passed, stats

    # ============================================================
    # L2 技术过滤
    # ============================================================

    def _layer2_technical_filter(
        self, stocks: List[Dict]
    ) -> Tuple[List[LayeredScanResult], LayerStats]:
        """
        L2 技术过滤：
          - MA趋势：MA5>MA10>MA20 或 短期均线向上
          - 成交量：近5日均量 > 0 且 量比 >= 0.8
          - KDJ：金叉 或 K值在低位（<30）
          - MACD：金叉 或 红柱（DIF>DEA）
          - 涨停历史：近60日内有涨停（涨幅>=9.5%）

        满足任意 >= 2 个条件即通过。
        """
        stats = LayerStats(layer_name="L2_技术过滤")
        start = time.time()
        stats.input_count = len(stocks)

        passed = []
        reasons = {
            "MA趋势": 0, "成交量": 0, "KDJ": 0, "MACD": 0,
            "涨停历史": 0, "条件不足": 0, "数据不足": 0,
        }

        def _worker(stock: Dict) -> Optional[LayeredScanResult]:
            code = stock["code"]
            kline = self.tdx.get_kline(code, days=KLAY_DAYS_L2)
            if not kline or len(kline) < 20:
                return None

            try:
                bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
            except Exception:
                return None

            if len(closes) < 20:
                return None

            result = LayeredScanResult(
                code=code,
                name=stock.get("name", ""),
                price=stock.get("price", 0),
                change_pct=stock.get("change_pct", 0),
            )

            last_idx = len(closes) - 1
            pass_count = 0
            cond_detail = {}

            # 1. MA趋势
            ma5 = TechnicalIndicators.ma(closes, 5)
            ma10 = TechnicalIndicators.ma(closes, 10)
            ma20 = TechnicalIndicators.ma(closes, 20)
            ma60 = TechnicalIndicators.ma(closes, 60) if len(closes) >= 60 else ma20

            result.ma5 = float(ma5[last_idx]) if not np.isnan(ma5[last_idx]) else 0
            result.ma10 = float(ma10[last_idx]) if not np.isnan(ma10[last_idx]) else 0
            result.ma20 = float(ma20[last_idx]) if not np.isnan(ma20[last_idx]) else 0
            result.ma60 = float(ma60[last_idx]) if not np.isnan(ma60[last_idx]) else 0

            ma_bullish = (
                not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx])
                and not np.isnan(ma20[last_idx])
                and ma5[last_idx] > ma10[last_idx] > ma20[last_idx]
            )
            # 短期均线向上（MA5 > MA5_5日前）
            ma_trending_up = False
            if last_idx >= 5 and not np.isnan(ma5[last_idx]) and not np.isnan(ma5[last_idx - 5]):
                ma_trending_up = ma5[last_idx] > ma5[last_idx - 5]

            if ma_bullish or ma_trending_up:
                pass_count += 1
                cond_detail["MA趋势"] = True
            else:
                cond_detail["MA趋势"] = False

            # 2. 成交量
            vol_arr = np.array(volumes, dtype=float)
            avg_vol_5 = float(np.mean(vol_arr[-5:])) if len(vol_arr) >= 5 else 0
            avg_vol_20 = float(np.mean(vol_arr[-20:])) if len(vol_arr) >= 20 else 0
            volume_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1.0
            result.volume_ratio = round(volume_ratio, 2)

            if avg_vol_5 > 0 and volume_ratio >= 0.8:
                pass_count += 1
                cond_detail["成交量"] = True
            else:
                cond_detail["成交量"] = False

            # 3. KDJ
            k, d, j = TechnicalIndicators.kdj(highs, lows, closes)
            if not np.isnan(k[last_idx]) and not np.isnan(d[last_idx]):
                result.kdj_k = float(k[last_idx])
                result.kdj_d = float(d[last_idx])
                kdj_golden = TechnicalIndicators.is_kdj_golden(k, d, last_idx)
                kdj_low = k[last_idx] < 30
                if kdj_golden or kdj_low:
                    pass_count += 1
                    cond_detail["KDJ"] = True
                else:
                    cond_detail["KDJ"] = False
            else:
                cond_detail["KDJ"] = False

            # 4. MACD
            dif, dea, hist = TechnicalIndicators.macd(closes)
            if not np.isnan(dif[last_idx]) and not np.isnan(dea[last_idx]):
                result.macd_dif = float(dif[last_idx])
                result.macd_dea = float(dea[last_idx])
                result.macd_hist = float(hist[last_idx])
                macd_golden = TechnicalIndicators.is_macd_golden(dif, dea, last_idx)
                macd_red = dif[last_idx] > dea[last_idx]
                if macd_golden or macd_red:
                    pass_count += 1
                    cond_detail["MACD"] = True
                else:
                    cond_detail["MACD"] = False
            else:
                cond_detail["MACD"] = False

            # 5. 涨停历史（近60日内涨幅>=9.5%）
            has_limit_up = False
            lookback = min(60, len(closes))
            for i in range(len(closes) - lookback, len(closes)):
                if i > 0 and closes[i - 1] > 0:
                    pct = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                    if pct >= 9.5:
                        has_limit_up = True
                        break
            if has_limit_up:
                pass_count += 1
                cond_detail["涨停历史"] = True
            else:
                cond_detail["涨停历史"] = False

            # 判断是否通过
            if pass_count >= L2_MIN_PASS_CONDITIONS:
                # 计算RPS20（简单近似：20日涨幅排名，这里用20日涨幅分位）
                if len(closes) >= 20 and closes[-20] > 0:
                    result.rps20 = min(100, max(0,
                        (closes[-1] - closes[-20]) / closes[-20] * 100 + 50))
                return result
            else:
                return None

        # 并行处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_worker, s): s for s in stocks}
            for future in as_completed(futures):
                r = future.result()
                if r is not None:
                    passed.append(r)

        # 统计过滤原因（近似：基于通过条件的反向统计）
        stats.pass_count = len(passed)
        stats.filter_count = stats.input_count - stats.pass_count
        stats.elapsed_seconds = time.time() - start
        # 过滤原因无法精确统计（并行中未收集），给出通过数估算
        stats.filter_reasons = {
            "通过(≥2条件)": len(passed),
            "未通过(<2条件)": stats.filter_count,
        }

        return passed, stats

    # ============================================================
    # L3 多因子评分
    # ============================================================

    def _layer3_multi_factor_score(
        self, stocks: List[LayeredScanResult]
    ) -> Tuple[List[LayeredScanResult], LayerStats]:
        """
        L3 多因子评分：
          - 技术面因子（40%）：MA趋势、量价配合、突破信号
          - 资金面因子（30%）：量比、换手率、成交额
          - 趋势面因子（30%）：RPS20、均线多头、突破60日线

        计算综合评分（0-100），保留评分最高的 l3_keep 只。
        """
        stats = LayerStats(layer_name="L3_多因子评分")
        start = time.time()
        stats.input_count = len(stocks)

        scored = []

        def _worker(stock: LayeredScanResult) -> LayeredScanResult:
            code = stock.code
            kline = self.tdx.get_kline(code, days=KLAY_DAYS_L3)
            if not kline or len(kline) < 20:
                stock.factor_score = 0
                return stock

            try:
                bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
            except Exception:
                stock.factor_score = 0
                return stock

            last_idx = len(closes) - 1
            vol_arr = np.array(volumes, dtype=float)
            price = closes[last_idx]

            # ===== 技术面因子（0-40分）=====
            tech_score = 0.0

            # MA多头排列（15分）
            ma5 = TechnicalIndicators.ma(closes, 5)
            ma10 = TechnicalIndicators.ma(closes, 10)
            ma20 = TechnicalIndicators.ma(closes, 20)
            if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx])
                    and not np.isnan(ma20[last_idx])):
                if ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                    tech_score += 15
                elif ma5[last_idx] > ma10[last_idx]:
                    tech_score += 8

            # 量价配合（10分）：上涨+放量
            if len(closes) >= 2 and closes[-1] > closes[-2]:
                avg5 = np.mean(vol_arr[-5:]) if len(vol_arr) >= 5 else vol_arr[-1]
                avg20 = np.mean(vol_arr[-20:]) if len(vol_arr) >= 20 else avg5
                if avg20 > 0 and avg5 / avg20 >= 1.2:
                    tech_score += 10
                elif avg20 > 0 and avg5 / avg20 >= 1.0:
                    tech_score += 5

            # 突破信号（15分）：价格突破近20日高点
            if len(closes) >= 20:
                high_20 = np.max(highs[-20:])
                if price >= high_20 * 0.98:
                    tech_score += 15
                elif price >= high_20 * 0.95:
                    tech_score += 7

            stock.factor_technical = min(40, tech_score)

            # ===== 资金面因子（0-30分）=====
            fund_score = 0.0

            # 量比（10分）
            avg5 = np.mean(vol_arr[-5:]) if len(vol_arr) >= 5 else 0
            avg20 = np.mean(vol_arr[-20:]) if len(vol_arr) >= 20 else avg5
            if avg20 > 0:
                vr = avg5 / avg20
                if vr >= 2.0:
                    fund_score += 10
                elif vr >= 1.5:
                    fund_score += 7
                elif vr >= 1.2:
                    fund_score += 4

            # 换手率近似（10分）：成交额/价格 作为活跃度
            amount = float(kline[-1].get("amount", 0)) if kline else 0
            if amount > 0 and price > 0:
                turnover_approx = amount / price / 10000  # 近似万手
                if turnover_approx >= 50:
                    fund_score += 10
                elif turnover_approx >= 20:
                    fund_score += 7
                elif turnover_approx >= 10:
                    fund_score += 4

            # 大单资金（10分）：近3日量能递增
            if len(vol_arr) >= 3:
                if vol_arr[-1] > vol_arr[-2] > vol_arr[-3]:
                    fund_score += 10
                elif vol_arr[-1] > vol_arr[-2]:
                    fund_score += 5

            stock.factor_fund = min(30, fund_score)

            # ===== 趋势面因子（0-30分）=====
            trend_score = 0.0

            # RPS20（10分）
            rps = stock.rps20
            if rps >= 90:
                trend_score += 10
            elif rps >= 80:
                trend_score += 7
            elif rps >= 70:
                trend_score += 4

            # 均线多头+价格在MA60之上（10分）
            ma60 = TechnicalIndicators.ma(closes, 60) if len(closes) >= 60 else ma20
            if (not np.isnan(ma60[last_idx]) and ma60[last_idx] > 0
                    and price > ma60[last_idx]):
                trend_score += 10
            elif not np.isnan(ma60[last_idx]) and price > ma60[last_idx] * 0.97:
                trend_score += 5

            # 突破60日线（10分）
            if len(closes) >= 60 and not np.isnan(ma60[last_idx]):
                if last_idx >= 1 and not np.isnan(ma60[last_idx - 1]):
                    if (closes[last_idx - 1] <= ma60[last_idx - 1]
                            and closes[last_idx] > ma60[last_idx]):
                        trend_score += 10  # 刚突破
                    elif closes[last_idx] > ma60[last_idx]:
                        trend_score += 5  # 已在上方

            stock.factor_trend = min(30, trend_score)

            # 综合评分
            stock.factor_score = round(
                stock.factor_technical + stock.factor_fund + stock.factor_trend, 1
            )

            return stock

        # 并行计算
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(_worker, s) for s in stocks]
            for future in as_completed(futures):
                scored.append(future.result())

        # 按评分降序，保留Top N
        scored.sort(key=lambda s: s.factor_score, reverse=True)
        kept = scored[:self.l3_keep]

        stats.pass_count = len(kept)
        stats.filter_count = stats.input_count - stats.pass_count
        stats.elapsed_seconds = time.time() - start
        # 评分分布
        score_dist = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
        for s in kept:
            fs = s.factor_score
            if fs >= 90:
                score_dist["90-100"] += 1
            elif fs >= 80:
                score_dist["80-89"] += 1
            elif fs >= 70:
                score_dist["70-79"] += 1
            elif fs >= 60:
                score_dist["60-69"] += 1
            else:
                score_dist["<60"] += 1
        stats.filter_reasons = score_dist

        return kept, stats

    # ============================================================
    # L4 AI深度分析
    # ============================================================

    def _layer4_ai_deep_analysis(
        self, stocks: List[LayeredScanResult]
    ) -> Tuple[List[LayeredScanResult], LayerStats]:
        """
        L4 AI深度分析（只对Top N只）：
          - 三模型分析（涨停回调/箱体突破/量价突破）
          - AI综合评分（调用阶段2的AICompositeScoreEngine）
          - 输出最终候选股票列表（带完整评分和信号）
        """
        stats = LayerStats(layer_name="L4_AI深度分析")
        start = time.time()

        # 只取Top N
        top_stocks = stocks[:self.l4_deep]
        stats.input_count = len(top_stocks)

        models = self._get_models()
        results = []

        def _worker(stock: LayeredScanResult) -> LayeredScanResult:
            code = stock.code
            kline = self.tdx.get_kline(code, days=KLAY_DAYS_L4)
            if not kline or len(kline) < 30:
                stock.composite_score = stock.factor_score * 0.6
                stock.composite_grade = self.composite_engine.get_grade(
                    stock.composite_score)
                stock.trading_advice = self.composite_engine.get_trading_advice(
                    stock.composite_score, stock.composite_grade)
                return stock

            try:
                bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
            except Exception:
                return stock

            # 三模型分析
            model_scores = {}
            best_score = 0
            best_model = ""
            for model in models:
                try:
                    match = model.analyze(bars, closes, highs, lows, volumes)
                    model_scores[model.name] = {
                        "matched": match.matched,
                        "score": round(match.score, 1),
                        "stage": match.stage,
                        "signals": list(match.signals),
                        "support": round(match.support, 2),
                        "pressure": round(match.pressure, 2),
                    }
                    if match.score > best_score:
                        best_score = match.score
                        best_model = model.name
                except Exception as e:
                    logger.debug(f"[L4] {code} 模型{model.name}异常: {e}")
                    model_scores[getattr(model, 'name', 'unknown')] = {
                        "matched": False, "score": 0, "stage": "异常",
                    }

            stock.model_scores = model_scores
            stock.best_model = best_model
            stock.best_model_score = round(best_score, 1)

            # 构建综合评分输入
            avg_model_score = (
                sum(m.get("score", 0) for m in model_scores.values()) / len(model_scores)
                if model_scores else 0
            )

            composite_input = {
                "code": code,
                "name": stock.name,
                "force_behavior_score": round(avg_model_score, 1) if avg_model_score > 0 else None,
                "nine_filter_score": stock.factor_score,
                "ai_six_dim_score": None,  # 六维评分需要更多数据，暂留空
                "price": stock.price,
                "change_pct": stock.change_pct,
                "ma5": stock.ma5,
                "ma10": stock.ma10,
                "ma20": stock.ma20,
                "ma60": stock.ma60,
                "volume_ratio": stock.volume_ratio,
                "rps20": stock.rps20,
            }

            composite_result = self.composite_engine.calculate(composite_input)
            stock.composite_score = composite_result.get("composite_score", 0)
            stock.composite_grade = composite_result.get("grade", "")
            stock.trading_advice = composite_result.get("trading_advice", "")

            return stock

        # 并行处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(_worker, s) for s in top_stocks]
            for future in as_completed(futures):
                results.append(future.result())

        # 按综合评分降序
        results.sort(key=lambda s: s.composite_score, reverse=True)

        stats.pass_count = len(results)
        stats.filter_count = 0  # L4不做过滤，只做深度分析
        stats.elapsed_seconds = time.time() - start
        stats.filter_reasons = {
            "深度分析完成": len(results),
            "三模型匹配数": sum(
                1 for r in results
                if any(m.get("matched", False) for m in r.model_scores.values())
            ),
        }

        return results, stats

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _print_stats(stats: LayerStats):
        """打印单层统计"""
        print(f"\n[{stats.layer_name}]", flush=True)
        print(f"  输入: {stats.input_count} 只", flush=True)
        print(f"  通过: {stats.pass_count} 只", flush=True)
        print(f"  过滤: {stats.filter_count} 只", flush=True)
        print(f"  耗时: {stats.elapsed_seconds:.1f} 秒", flush=True)
        if stats.filter_reasons:
            reasons_str = ", ".join(
                f"{k}={v}" for k, v in stats.filter_reasons.items()
            )
            print(f"  分布: {reasons_str}", flush=True)

    @staticmethod
    def _build_result(
        final: List, stats: List[LayerStats], start_time: float
    ) -> Dict:
        """构建返回结果"""
        return {
            "final_candidates": [s.to_dict() if hasattr(s, 'to_dict') else s for s in final],
            "layer_stats": [s.to_dict() for s in stats],
            "total_elapsed": round(time.time() - start_time, 2),
            "l2_count": 0,
            "l3_count": 0,
            "l4_count": len(final),
        }


# ============================================================
# 便捷函数
# ============================================================

_default_scanner = None


def get_layered_scanner(**kwargs) -> LayeredScanner:
    """获取分层扫描器单例"""
    global _default_scanner
    if _default_scanner is None:
        _default_scanner = LayeredScanner(**kwargs)
    return _default_scanner


def run_layered_scan(**kwargs) -> Dict:
    """便捷函数：执行全市场分层扫描"""
    return get_layered_scanner(**kwargs).scan_full_market()
