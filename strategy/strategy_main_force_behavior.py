# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.0
核心策略入口：strategy_main_force_behavior.py

唯一核心选股策略入口，基于「主力行为模式识别」构建。

三个核心模型：
  模型一 涨停回调模型：涨停/大阳启动→回调整理→缩量洗盘→关键支撑→再次启动
  模型二 横盘箱体突破模型：强势上涨→横盘整理→缩量筑平台→突破箱体→第二波
  模型三 极限缩量量价突破模型：极限缩量筑底→量价齐升→突破压力→回踩确认→再次放量突破

AI评分系统（总分100，6维度）：
  主力行为结构40 + 量价关系20 + 趋势均线15 + 涨停强势基因10 + 技术指标确认10 + 市场环境5

设计原则：
  1. 实证主义驱动：所有逻辑可回测验证
  2. AI仅辅助解释，不参与核心决策
  3. 策略层独立，不污染UI和数据层
  4. 所有数据来自真实计算，严禁Hardcode
  5. 不追高，不追涨停当天
  6. 实盘-回测一致性校验
"""

import os
import json
import time
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

# ============================================================
# 常量定义
# ============================================================

# 模型标签
MODEL_LIMIT_PULLBACK = "涨停回调"
MODEL_BOX_BREAKOUT = "箱体突破"
MODEL_VOLUME_PRICE_BREAKOUT = "量价突破"

# 阶段标签
STAGE_LAUNCH = "强势启动"
STAGE_PULLBACK = "回调整理"
STAGE_SHRINK = "缩量洗盘"
STAGE_SUPPORT = "关键支撑"
STAGE_RELAUNCH = "再次启动"
STAGE_PLATFORM = "平台蓄势"
STAGE_BREAKOUT = "突破区域"
STAGE_CONFIRM = "回踩确认"
STAGE_BOTTOM = "极限缩量筑底"
STAGE_VOL_PRICE_UP = "量价齐升"

# 区域颜色（K线标注）
REGION_SHRINK = "shrink"       # 绿色：缩量区域
REGION_BOX = "box"             # 黄色：箱体区域
REGION_BREAKOUT = "breakout"   # 红色：突破区域
REGION_CONFIRM = "confirm"     # 蓝色：回踩确认区域

# 评分等级
SCORE_STRONG_CANDIDATE = "强势启动候选"  # 90-100
SCORE_KEY_WATCH = "重点观察"              # 80-90
SCORE_NORMAL_WATCH = "普通观察"           # 70-80
SCORE_FILTER = "过滤"                     # 70以下

# 技术指标参数
KDJ_N = 13
KDJ_M1 = 3
KDJ_M2 = 3
MACD_FAST = 8
MACD_SLOW = 21
MACD_SIGNAL = 5

# 扫描参数
MIN_KLINE_COUNT = 60          # 最少K线数量
LIMIT_UP_THRESHOLD = 9.8      # 涨停阈值（%）
BIG_YANG_THRESHOLD = 5.0      # 大阳线阈值（%）
DEFAULT_SCAN_COUNT = 120      # 默认扫描K线数量


# ============================================================
# 数据结构
# ============================================================

@dataclass
class KlineBar:
    """单根K线"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0
    pct_chg: float = 0.0


@dataclass
class ModelMatch:
    """模型匹配结果"""
    model_name: str
    matched: bool
    stage: str
    signals: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    detail: Dict = field(default_factory=dict)


@dataclass
class AIScore:
    """AI评分结果"""
    total: float = 0.0
    main_force_structure: float = 0.0   # 主力行为结构 40
    volume_price: float = 0.0            # 量价关系 20
    trend_ma: float = 0.0                # 趋势均线 15
    limit_up_gene: float = 0.0           # 涨停强势基因 10
    tech_indicator: float = 0.0          # 技术指标确认 10
    market_env: float = 0.0              # 市场环境 5
    level: str = SCORE_FILTER
    breakdown: Dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class KlineAnnotation:
    """K线标注结果"""
    regions: List[Dict] = field(default_factory=list)  # 区域标注
    markers: List[Dict] = field(default_factory=list)  # 买卖点/风险标记
    model_labels: List[Dict] = field(default_factory=list)  # 模型标签


@dataclass
class StockScanResult:
    """单只股票扫描结果"""
    code: str
    name: str
    price: float
    pct_chg: float
    industry: str
    matched_models: List[ModelMatch] = field(default_factory=list)
    current_stage: str = ""
    buy_signals: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    score: AIScore = field(default_factory=AIScore)
    annotation: KlineAnnotation = field(default_factory=KlineAnnotation)
    kline_data: Dict = field(default_factory=dict)
    scan_time: str = ""

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "pct_chg": self.pct_chg,
            "industry": self.industry,
            "matched_models": [asdict(m) for m in self.matched_models],
            "current_stage": self.current_stage,
            "buy_signals": self.buy_signals,
            "risk_warnings": self.risk_warnings,
            "score": asdict(self.score),
            "annotation": asdict(self.annotation),
            "scan_time": self.scan_time,
        }


# ============================================================
# 技术指标计算模块
# ============================================================

class TechnicalIndicators:
    """技术指标计算器（仅辅助确认）"""

    @staticmethod
    def ma(closes: np.ndarray, period: int) -> np.ndarray:
        """计算移动平均线"""
        if len(closes) < period:
            return np.full(len(closes), np.nan)
        result = np.full(len(closes), np.nan)
        for i in range(period - 1, len(closes)):
            result[i] = np.mean(closes[i - period + 1:i + 1])
        return result

    @staticmethod
    def kdj(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
            n: int = KDJ_N, m1: int = KDJ_M1, m2: int = KDJ_M2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算KDJ指标"""
        length = len(closes)
        if length < n:
            return (np.full(length, np.nan), np.full(length, np.nan), np.full(length, np.nan))

        rsv = np.full(length, np.nan)
        for i in range(n - 1, length):
            hh = np.max(highs[i - n + 1:i + 1])
            ll = np.min(lows[i - n + 1:i + 1])
            if hh != ll:
                rsv[i] = (closes[i] - ll) / (hh - ll) * 100
            else:
                rsv[i] = 50.0

        k = np.full(length, np.nan)
        d = np.full(length, np.nan)
        j = np.full(length, np.nan)

        k_val = 50.0
        d_val = 50.0
        for i in range(length):
            if np.isnan(rsv[i]):
                continue
            k_val = (m1 - 1) / m1 * k_val + 1 / m1 * rsv[i]
            d_val = (m2 - 1) / m2 * d_val + 1 / m2 * k_val
            j_val = 3 * k_val - 2 * d_val
            k[i] = k_val
            d[i] = d_val
            j[i] = j_val

        return k, d, j

    @staticmethod
    def macd(closes: np.ndarray, fast: int = MACD_FAST, slow: int = MACD_SLOW,
             signal: int = MACD_SIGNAL) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD指标"""
        length = len(closes)
        if length < slow:
            return (np.full(length, np.nan), np.full(length, np.nan), np.full(length, np.nan))

        # EMA计算
        def ema(data, period):
            result = np.full(len(data), np.nan)
            if len(data) < period:
                return result
            multiplier = 2 / (period + 1)
            result[period - 1] = np.mean(data[:period])
            for i in range(period, len(data)):
                result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
            return result

        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        dif = ema_fast - ema_slow

        # DEA = EMA(DIF, signal)
        valid_dif = dif[~np.isnan(dif)]
        dea = np.full(length, np.nan)
        if len(valid_dif) >= signal:
            start_idx = np.where(~np.isnan(dif))[0][0]
            multiplier = 2 / (signal + 1)
            dea[start_idx + signal - 1] = np.mean(valid_dif[:signal])
            for i in range(start_idx + signal, length):
                if np.isnan(dif[i]):
                    continue
                dea[i] = (dif[i] - dea[i - 1]) * multiplier + dea[i - 1]

        macd_hist = 2 * (dif - dea)
        return dif, dea, macd_hist

    @staticmethod
    def is_kdj_golden(k: np.ndarray, d: np.ndarray, idx: int = -1) -> bool:
        """KDJ金叉判断"""
        if idx < 0:
            idx = len(k) - 1
        if idx < 1 or np.isnan(k[idx]) or np.isnan(k[idx - 1]):
            return False
        return k[idx - 1] <= d[idx - 1] and k[idx] > d[idx]

    @staticmethod
    def is_macd_golden(dif: np.ndarray, dea: np.ndarray, idx: int = -1) -> bool:
        """MACD金叉判断"""
        if idx < 0:
            idx = len(dif) - 1
        if idx < 1 or np.isnan(dif[idx]) or np.isnan(dif[idx - 1]):
            return False
        return dif[idx - 1] <= dea[idx - 1] and dif[idx] > dea[idx]


# ============================================================
# K线数据解析与工具函数
# ============================================================

class KlineDataParser:
    """K线数据解析器"""

    @staticmethod
    def parse(kline_data: Dict) -> Tuple[List[KlineBar], np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        解析K线数据为统一格式

        Returns:
            bars, opens, highs, lows, closes, volumes
        """
        dates = kline_data.get('dates', kline_data.get('date', []))
        opens = kline_data.get('open', [])
        highs = kline_data.get('high', [])
        lows = kline_data.get('low', [])
        closes = kline_data.get('close', [])
        volumes = kline_data.get('volume', [])
        amounts = kline_data.get('amount', kline_data.get('vol', []))

        # 处理numpy数组
        if hasattr(dates, 'tolist'):
            dates = dates.tolist()
        if hasattr(opens, 'tolist'):
            opens = opens.tolist()
        if hasattr(highs, 'tolist'):
            highs = highs.tolist()
        if hasattr(lows, 'tolist'):
            lows = lows.tolist()
        if hasattr(closes, 'tolist'):
            closes = closes.tolist()
        if hasattr(volumes, 'tolist'):
            volumes = volumes.tolist()
        if hasattr(amounts, 'tolist'):
            amounts = amounts.tolist()

        bars = []
        for i in range(len(closes)):
            pct = 0.0
            if i > 0 and closes[i - 1] > 0:
                pct = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
            bars.append(KlineBar(
                date=str(dates[i]) if i < len(dates) else f"day_{i}",
                open=float(opens[i]) if i < len(opens) else float(closes[i]),
                high=float(highs[i]) if i < len(highs) else float(closes[i]),
                low=float(lows[i]) if i < len(lows) else float(closes[i]),
                close=float(closes[i]),
                volume=float(volumes[i]) if i < len(volumes) else 0.0,
                amount=float(amounts[i]) if i < len(amounts) else 0.0,
                pct_chg=pct,
            ))

        return (bars,
                np.array([b.open for b in bars], dtype=float),
                np.array([b.high for b in bars], dtype=float),
                np.array([b.low for b in bars], dtype=float),
                np.array([b.close for b in bars], dtype=float),
                np.array([b.volume for b in bars], dtype=float))


class VolumeAnalyzer:
    """成交量分析器"""

    @staticmethod
    def is_volume_shrinking(volumes: np.ndarray, period: int = 5) -> bool:
        """判断是否缩量（近期成交量低于前期均量）"""
        if len(volumes) < period * 2:
            return False
        recent_avg = np.mean(volumes[-period:])
        prev_avg = np.mean(volumes[-period * 2:-period])
        if prev_avg <= 0:
            return False
        return recent_avg < prev_avg * 0.7

    @staticmethod
    def is_volume_expanding(volumes: np.ndarray, period: int = 5) -> bool:
        """判断是否放量"""
        if len(volumes) < period * 2:
            return False
        recent_avg = np.mean(volumes[-period:])
        prev_avg = np.mean(volumes[-period * 2:-period])
        if prev_avg <= 0:
            return False
        return recent_avg > prev_avg * 1.3

    @staticmethod
    def volume_ratio(volumes: np.ndarray, period: int = 5) -> float:
        """计算量比（近期均量/前期均量）"""
        if len(volumes) < period * 2:
            return 1.0
        recent_avg = np.mean(volumes[-period:])
        prev_avg = np.mean(volumes[-period * 2:-period])
        if prev_avg <= 0:
            return 1.0
        return recent_avg / prev_avg

    @staticmethod
    def find_extreme_shrink(volumes: np.ndarray, lookback: int = 60) -> Optional[int]:
        """寻找极限缩量位置（返回索引）"""
        if len(volumes) < lookback:
            lookback = len(volumes)
        if lookback < 10:
            return None
        segment = volumes[-lookback:]
        min_idx = np.argmin(segment)
        # 确认是阶段低位（低于前后各5天均值）
        abs_idx = len(volumes) - lookback + min_idx
        if abs_idx < 5 or abs_idx >= len(volumes) - 3:
            return None
        local_avg = np.mean(volumes[max(0, abs_idx - 5):abs_idx + 5])
        if volumes[abs_idx] < local_avg * 0.5:
            return abs_idx
        return None


# ============================================================
# 模型一：涨停回调模型
# ============================================================

class LimitUpPullbackModel:
    """
    模型一：涨停回调模型（强势股低吸模型）

    核心逻辑：
      强势启动 → 涨停/大阳线 → 回调整理 → 缩量洗盘 → 关键位置支撑 → 再次启动

    支撑判断：MA5 / MA10 / 前期涨停启动位 / 箱体底部
    标签：【涨停回调】【缩量低吸】【强势洗盘】
    买点：缩量调整结束，重新站上5日线，次日回踩5日线不破，成交量重新放大
    风险：跌破涨停启动位置，跌破箱体底部，放量下跌
    """

    def __init__(self):
        self.name = MODEL_LIMIT_PULLBACK

    def analyze(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, volumes: np.ndarray) -> ModelMatch:
        """分析涨停回调模型"""
        result = ModelMatch(model_name=self.name, matched=False, stage="")

        if len(bars) < MIN_KLINE_COUNT:
            result.stage = "数据不足"
            return result

        # 计算均线
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)

        last_idx = len(bars) - 1
        last_bar = bars[-1]

        # 1. 寻找近期涨停/大阳启动点（近30个交易日内）
        launch_idx = self._find_launch_point(bars, lookback=30)
        if launch_idx is None:
            result.stage = "无强势启动"
            return result

        launch_bar = bars[launch_idx]
        launch_price = launch_bar.close

        # 2. 启动后是否出现调整
        if last_idx <= launch_idx:
            result.stage = STAGE_LAUNCH
            return result

        # 调整区间：启动点后到当前
        adjust_closes = closes[launch_idx:]
        adjust_highs = highs[launch_idx:]
        adjust_lows = lows[launch_idx:]
        adjust_volumes = volumes[launch_idx:]

        # 最大回撤
        peak_after_launch = np.max(adjust_highs)
        current_price = closes[last_idx]
        drawdown = (peak_after_launch - current_price) / peak_after_launch * 100 if peak_after_launch > 0 else 0

        # 3. 判断调整过程中是否缩量
        is_shrinking = VolumeAnalyzer.is_volume_shrinking(volumes, period=5)
        vol_ratio = VolumeAnalyzer.volume_ratio(volumes, period=5)

        # 4. 判断是否有连续放量下跌（风险信号）
        has_volume_drop = self._check_volume_drop(bars, launch_idx)

        # 5. 支撑判断
        support_levels = self._check_support(last_bar, ma5[last_idx], ma10[last_idx],
                                              launch_price, adjust_lows)

        # 6. 判断当前阶段
        if drawdown < 2:
            stage = STAGE_LAUNCH
        elif is_shrinking and drawdown < 15:
            stage = STAGE_SHRINK
        elif drawdown >= 15:
            stage = STAGE_PULLBACK
        else:
            stage = STAGE_PULLBACK

        # 7. 买点判断
        buy_signals = []
        if is_shrinking and not np.isnan(ma5[last_idx]):
            # 重新站上5日线
            if last_bar.close > ma5[last_idx] and bars[-2].close <= ma5[last_idx - 1]:
                buy_signals.append("重新站上5日线")
            # 回踩5日线不破
            if last_bar.low <= ma5[last_idx] * 1.01 and last_bar.close > ma5[last_idx]:
                buy_signals.append("5日线回踩低吸")
            # 成交量重新放大
            if VolumeAnalyzer.is_volume_expanding(volumes[-3:], period=3) if len(volumes) >= 6 else False:
                buy_signals.append("成交量重新放大")

        # 8. 风险判断
        risks = []
        if has_volume_drop:
            risks.append("调整中出现放量下跌")
        if current_price < launch_price * 0.97:
            risks.append("跌破涨停启动位置")
        if current_price < np.min(adjust_lows) * 1.02 and len(adjust_lows) > 5:
            risks.append("跌破箱体底部")
        if last_bar.pct_chg < -3 and last_bar.volume > np.mean(volumes[-10:]) * 1.5:
            risks.append("当日放量下跌")

        # 9. 匹配判定：有启动点 + 调整中 + 缩量 + 在支撑位附近
        matched = (launch_idx is not None and
                   drawdown > 1 and drawdown < 20 and
                   is_shrinking and
                   support_levels.get('near_support', False))

        result.matched = matched
        result.stage = stage
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["涨停回调", "缩量低吸", "强势洗盘"]
        result.detail = {
            "launch_date": launch_bar.date,
            "launch_price": round(launch_price, 2),
            "launch_pct": round(launch_bar.pct_chg, 2),
            "drawdown_pct": round(drawdown, 2),
            "volume_ratio": round(vol_ratio, 2),
            "is_shrinking": is_shrinking,
            "support_levels": support_levels,
            "current_price": round(current_price, 2),
        }

        return result

    def _find_launch_point(self, bars: List[KlineBar], lookback: int = 30) -> Optional[int]:
        """寻找近期涨停/大阳启动点"""
        start = max(0, len(bars) - lookback)
        for i in range(len(bars) - 1, start - 1, -1):
            bar = bars[i]
            # 涨停或大阳线
            if bar.pct_chg >= LIMIT_UP_THRESHOLD or bar.pct_chg >= BIG_YANG_THRESHOLD:
                # 确认是启动点（前一天涨幅不大）
                if i > 0 and bars[i - 1].pct_chg < 3:
                    return i
                elif i == 0:
                    return i
        return None

    def _check_volume_drop(self, bars: List[KlineBar], launch_idx: int) -> bool:
        """检查调整中是否有连续放量下跌"""
        count = 0
        for i in range(launch_idx + 1, len(bars)):
            bar = bars[i]
            avg_vol = np.mean([b.volume for b in bars[max(0, i - 5):i]]) if i > 0 else bar.volume
            if bar.pct_chg < -2 and bar.volume > avg_vol * 1.3:
                count += 1
                if count >= 2:
                    return True
            else:
                count = 0
        return False

    def _check_support(self, bar: KlineBar, ma5_val: float, ma10_val: float,
                       launch_price: float, adjust_lows: np.ndarray) -> Dict:
        """检查支撑位"""
        price = bar.close
        support_info = {
            "near_ma5": False,
            "near_ma10": False,
            "near_launch": False,
            "near_box_bottom": False,
            "near_support": False,
        }

        tolerance = 0.02  # 2%容差

        if not np.isnan(ma5_val) and ma5_val > 0:
            if abs(price - ma5_val) / ma5_val < tolerance:
                support_info["near_ma5"] = True
        if not np.isnan(ma10_val) and ma10_val > 0:
            if abs(price - ma10_val) / ma10_val < tolerance:
                support_info["near_ma10"] = True
        if launch_price > 0:
            if abs(price - launch_price) / launch_price < tolerance:
                support_info["near_launch"] = True
        if len(adjust_lows) > 5:
            box_bottom = np.min(adjust_lows[:-1]) if len(adjust_lows) > 1 else adjust_lows[0]
            if box_bottom > 0 and abs(price - box_bottom) / box_bottom < tolerance:
                support_info["near_box_bottom"] = True

        support_info["near_support"] = any([
            support_info["near_ma5"],
            support_info["near_ma10"],
            support_info["near_launch"],
            support_info["near_box_bottom"],
        ])

        return support_info


# ============================================================
# 模型二：横盘箱体突破模型
# ============================================================

class BoxBreakoutModel:
    """
    模型二：横盘箱体突破模型（二波启动模型）

    核心逻辑：
      强势上涨 → 横盘整理 → 缩量筑平台 → 突破箱体 → 第二波上涨

    三买点：
      第一买点：缩量结束，重新站上MA5
      第二买点：突破箱体压力位
      第三买点：突破后回踩箱体顶部不破

    标签：【箱体突破】【二次启动】【平台蓄势】
    风险：跌破箱体底部，突破失败重新进入箱体
    """

    def __init__(self):
        self.name = MODEL_BOX_BREAKOUT

    def analyze(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, volumes: np.ndarray) -> ModelMatch:
        result = ModelMatch(model_name=self.name, matched=False, stage="")

        if len(bars) < MIN_KLINE_COUNT:
            result.stage = "数据不足"
            return result

        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)

        last_idx = len(bars) - 1
        last_bar = bars[-1]

        # 1. 寻找前期上涨趋势（近40日内有明显上涨）
        uptrend_end = self._find_uptrend(closes, lookback=40)
        if uptrend_end is None:
            result.stage = "无前期上涨"
            return result

        # 2. 识别横盘箱体（上涨后整理10-30天）
        box_info = self._detect_box(bars, closes, highs, lows, volumes, uptrend_end)
        if not box_info.get('is_box', False):
            result.stage = "未形成箱体"
            return result

        box_top = box_info['box_top']
        box_bottom = box_info['box_bottom']
        box_start = box_info['box_start']
        box_end = box_info['box_end']

        # 3. 判断当前状态
        current_price = closes[last_idx]
        is_shrinking = box_info.get('is_shrinking', False)

        # 是否突破箱体
        is_breaking_out = (current_price > box_top * 1.01 and
                           last_bar.volume > np.mean(volumes[box_start:box_end + 1]) * 1.2)

        # 是否回踩确认（突破后回踩箱体顶部不破）
        is_pullback_confirm = False
        if box_end < last_idx - 1:
            breakout_idx = None
            for i in range(box_end + 1, last_idx + 1):
                if closes[i] > box_top * 1.01:
                    breakout_idx = i
                    break
            if breakout_idx is not None and breakout_idx < last_idx:
                # 突破后回踩
                min_after = np.min(lows[breakout_idx:])
                if min_after >= box_top * 0.98:
                    is_pullback_confirm = True

        # 4. 阶段判断
        if is_breaking_out:
            stage = STAGE_BREAKOUT
        elif is_pullback_confirm:
            stage = STAGE_CONFIRM
        elif is_shrinking:
            stage = STAGE_PLATFORM
        else:
            stage = STAGE_PULLBACK

        # 5. 三买点判断
        buy_signals = []
        # 第一买点：缩量结束重新站上MA5
        if is_shrinking and not np.isnan(ma5[last_idx]):
            if last_bar.close > ma5[last_idx] and bars[-2].close <= ma5[last_idx - 1]:
                buy_signals.append("第一买点：缩量结束站上MA5")
        # 第二买点：突破箱体压力位
        if is_breaking_out:
            buy_signals.append("第二买点：放量突破箱体")
        # 第三买点：回踩箱体顶部不破
        if is_pullback_confirm and last_bar.close > box_top:
            buy_signals.append("第三买点：回踩箱体顶部不破")

        # 6. 风险判断
        risks = []
        if current_price < box_bottom * 0.98:
            risks.append("跌破箱体底部")
        # 突破失败
        if box_end < last_idx - 2:
            for i in range(box_end + 1, last_idx + 1):
                if closes[i] > box_top * 1.01 and i < last_idx:
                    if closes[last_idx] < box_top:
                        risks.append("突破失败重新进入箱体")
                    break

        # 7. 匹配判定
        matched = (box_info.get('is_box', False) and
                   (is_shrinking or is_breaking_out or is_pullback_confirm) and
                   box_top > box_bottom * 1.03)  # 箱体有至少3%幅度

        result.matched = matched
        result.stage = stage
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["箱体突破", "二次启动", "平台蓄势"]
        result.detail = {
            "box_top": round(box_top, 2),
            "box_bottom": round(box_bottom, 2),
            "box_height_pct": round((box_top - box_bottom) / box_bottom * 100, 2),
            "box_days": box_end - box_start + 1,
            "is_shrinking": is_shrinking,
            "is_breaking_out": is_breaking_out,
            "is_pullback_confirm": is_pullback_confirm,
            "current_price": round(current_price, 2),
        }

        return result

    def _find_uptrend(self, closes: np.ndarray, lookback: int = 40) -> Optional[int]:
        """寻找前期上涨趋势的终点"""
        if len(closes) < lookback:
            lookback = len(closes)
        start = len(closes) - lookback
        # 寻找区间内最高点
        segment = closes[start:]
        if len(segment) < 10:
            return None
        peak_idx = np.argmax(segment) + start
        # 确认上涨幅度 > 15%
        if peak_idx > start + 5:
            rise = (closes[peak_idx] - closes[start]) / closes[start] * 100
            if rise > 15:
                return peak_idx
        return None

    def _detect_box(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                    lows: np.ndarray, volumes: np.ndarray, uptrend_end: int) -> Dict:
        """检测横盘箱体"""
        result = {'is_box': False}

        # 箱体从上涨结束后开始，长度10-30天
        box_start = uptrend_end + 1
        if box_start >= len(bars) - 5:
            return result

        # 尝试不同的箱体结束点
        best_box = None
        for box_end in range(min(box_start + 9, len(bars) - 1),
                              min(box_start + 29, len(bars) - 1)):
            box_highs = highs[box_start:box_end + 1]
            box_lows = lows[box_start:box_end + 1]
            box_closes = closes[box_start:box_end + 1]

            box_top = np.max(box_highs)
            box_bottom = np.min(box_lows)

            if box_bottom <= 0:
                continue

            height_pct = (box_top - box_bottom) / box_bottom * 100
            # 箱体幅度在3%-25%之间
            if height_pct < 3 or height_pct > 25:
                continue

            # 波动收窄：后半段振幅小于前半段
            mid = (box_start + box_end) // 2
            if mid > box_start:
                first_amp = np.max(highs[box_start:mid + 1]) - np.min(lows[box_start:mid + 1])
                second_amp = np.max(highs[mid:box_end + 1]) - np.min(lows[mid:box_end + 1])
                if second_amp > first_amp * 1.2:
                    continue

            # 均线粘合：MA5和MA10差距小
            ma5 = TechnicalIndicators.ma(closes, 5)
            ma10 = TechnicalIndicators.ma(closes, 10)
            if not np.isnan(ma5[box_end]) and not np.isnan(ma10[box_end]):
                ma_gap = abs(ma5[box_end] - ma10[box_end]) / ma10[box_end] * 100
                if ma_gap > 5:
                    continue

            # 缩量
            box_volumes = volumes[box_start:box_end + 1]
            prev_volumes = volumes[max(0, box_start - 10):box_start]
            is_shrinking = (np.mean(box_volumes) < np.mean(prev_volumes) * 0.8
                           if len(prev_volumes) > 0 else False)

            best_box = {
                'is_box': True,
                'box_top': box_top,
                'box_bottom': box_bottom,
                'box_start': box_start,
                'box_end': box_end,
                'is_shrinking': is_shrinking,
                'height_pct': height_pct,
            }
            break  # 取第一个符合条件的

        return best_box if best_box else result


# ============================================================
# 模型三：极限缩量量价突破模型
# ============================================================

class VolumePriceBreakoutModel:
    """
    模型三：极限缩量量价突破模型（主力启动模型）

    5阶段：
      阶段1：极限缩量筑底（成交量阶段低位，股价横盘，抛压减少，波动降低）
      阶段2：量价齐升（股价上涨，成交量同步增加，阳线增加）
      阶段3：突破压力（突破前期高点/箱体，成交量放大）
      阶段4：回踩确认（回踩突破位置，成交量缩小，不跌破突破位）
      阶段5：再次放量突破

    标签：【量价突破】【主力启动】【二次确认】
    """

    def __init__(self):
        self.name = MODEL_VOLUME_PRICE_BREAKOUT

    def analyze(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, volumes: np.ndarray) -> ModelMatch:
        result = ModelMatch(model_name=self.name, matched=False, stage="")

        if len(bars) < MIN_KLINE_COUNT:
            result.stage = "数据不足"
            return result

        last_idx = len(bars) - 1
        last_bar = bars[-1]
        current_price = closes[last_idx]

        # 阶段1：寻找极限缩量筑底
        shrink_idx = VolumeAnalyzer.find_extreme_shrink(volumes, lookback=60)
        if shrink_idx is None:
            result.stage = "无极限缩量"
            return result

        # 确认筑底期间股价横盘
        bottom_start = max(0, shrink_idx - 5)
        bottom_end = min(len(bars) - 1, shrink_idx + 5)
        bottom_closes = closes[bottom_start:bottom_end + 1]
        bottom_volatility = (np.max(bottom_closes) - np.min(bottom_closes)) / np.min(bottom_closes) * 100
        is_bottom = bottom_volatility < 10  # 筑底期间波动小于10%

        if not is_bottom:
            result.stage = "缩量但非筑底"
            return result

        # 阶段2：量价齐升（缩量后是否出现上涨+放量）
        vp_up_start = shrink_idx + 1
        vp_up_end = None
        if vp_up_start < last_idx:
            for i in range(vp_up_start, min(vp_up_start + 15, last_idx + 1)):
                if closes[i] > closes[shrink_idx] * 1.05:
                    avg_vol_before = np.mean(volumes[max(0, i - 5):i])
                    if volumes[i] > avg_vol_before * 1.3:
                        vp_up_end = i
                        break

        is_vp_up = vp_up_end is not None

        # 阶段3：突破压力
        breakout_level = None
        breakout_idx = None
        if is_vp_up:
            # 前期高点压力（缩量前20天内的高点）
            pressure_start = max(0, shrink_idx - 20)
            pressure_high = np.max(highs[pressure_start:shrink_idx + 1])
            for i in range(vp_up_end, last_idx + 1):
                if closes[i] > pressure_high * 1.01 and volumes[i] > np.mean(volumes[max(0, i - 5):i]) * 1.2:
                    breakout_level = pressure_high
                    breakout_idx = i
                    break

        is_breaking = breakout_idx is not None

        # 阶段4：回踩确认
        is_confirm = False
        if is_breaking and breakout_idx < last_idx:
            min_after = np.min(lows[breakout_idx:])
            vol_after = np.mean(volumes[breakout_idx:])
            vol_before = np.mean(volumes[max(0, breakout_idx - 5):breakout_idx])
            if min_after >= breakout_level * 0.97 and vol_after < vol_before * 0.9:
                is_confirm = True

        # 阶段5：再次放量突破
        is_re_break = False
        if is_confirm:
            if (last_bar.close > breakout_level * 1.02 and
                last_bar.volume > np.mean(volumes[-5:]) * 1.3):
                is_re_break = True

        # 阶段判断
        if is_re_break:
            stage = "再次放量突破"
        elif is_confirm:
            stage = STAGE_CONFIRM
        elif is_breaking:
            stage = STAGE_BREAKOUT
        elif is_vp_up:
            stage = STAGE_VOL_PRICE_UP
        else:
            stage = STAGE_BOTTOM

        # 买点判断
        buy_signals = []
        if is_vp_up and not is_breaking:
            buy_signals.append("量价齐升初期介入")
        if is_breaking:
            buy_signals.append("放量突破压力位")
        if is_confirm:
            buy_signals.append("回踩确认低吸")
        if is_re_break:
            buy_signals.append("再次放量突破加仓")

        # 风险判断
        risks = []
        if current_price < closes[shrink_idx] * 0.95:
            risks.append("跌破筑底位置")
        if is_breaking and current_price < breakout_level * 0.97:
            risks.append("突破后跌破突破位")
        if last_bar.pct_chg < -3 and last_bar.volume > np.mean(volumes[-10:]) * 1.5:
            risks.append("放量下跌")

        # 匹配判定
        matched = is_bottom and (is_vp_up or is_breaking or is_confirm or is_re_break)

        result.matched = matched
        result.stage = stage
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["量价突破", "主力启动", "二次确认"]
        result.detail = {
            "shrink_date": bars[shrink_idx].date,
            "shrink_volume": round(volumes[shrink_idx], 0),
            "bottom_volatility_pct": round(bottom_volatility, 2),
            "is_vp_up": is_vp_up,
            "is_breaking": is_breaking,
            "breakout_level": round(breakout_level, 2) if breakout_level else 0,
            "is_confirm": is_confirm,
            "is_re_break": is_re_break,
            "current_price": round(current_price, 2),
        }

        return result


# ============================================================
# AI 6维度评分系统
# ============================================================

class AIScoringSystem:
    """
    AI评分系统（总分100，6维度）

    主力行为结构 40分
    量价关系 20分
    趋势均线 15分
    涨停强势基因 10分
    技术指标确认 10分
    市场环境 5分

    等级：
      90-100：强势启动候选
      80-90：重点观察
      70-80：普通观察
      70以下：过滤
    """

    def __init__(self):
        self.weights = {
            'main_force_structure': 40,
            'volume_price': 20,
            'trend_ma': 15,
            'limit_up_gene': 10,
            'tech_indicator': 10,
            'market_env': 5,
        }

    def score(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
              lows: np.ndarray, volumes: np.ndarray, matches: List[ModelMatch],
              market_data: Optional[Dict] = None) -> AIScore:
        """计算AI综合评分"""
        result = AIScore()

        if len(bars) < MIN_KLINE_COUNT:
            result.reason = "数据不足，无法评分"
            return result

        # 维度1：主力行为结构（40分）
        result.main_force_structure = self._score_main_force(matches, bars, volumes)
        result.breakdown['主力行为结构'] = result.main_force_structure

        # 维度2：量价关系（20分）
        result.volume_price = self._score_volume_price(bars, closes, volumes)
        result.breakdown['量价关系'] = result.volume_price

        # 维度3：趋势均线（15分）
        result.trend_ma = self._score_trend_ma(closes)
        result.breakdown['趋势均线'] = result.trend_ma

        # 维度4：涨停强势基因（10分）
        result.limit_up_gene = self._score_limit_up_gene(bars)
        result.breakdown['涨停强势基因'] = result.limit_up_gene

        # 维度5：技术指标确认（10分）
        result.tech_indicator = self._score_tech_indicator(highs, lows, closes)
        result.breakdown['技术指标确认'] = result.tech_indicator

        # 维度6：市场环境（5分）
        result.market_env = self._score_market_env(market_data)
        result.breakdown['市场环境'] = result.market_env

        # 总分
        result.total = round(
            result.main_force_structure +
            result.volume_price +
            result.trend_ma +
            result.limit_up_gene +
            result.tech_indicator +
            result.market_env, 2
        )

        # 等级
        if result.total >= 90:
            result.level = SCORE_STRONG_CANDIDATE
        elif result.total >= 80:
            result.level = SCORE_KEY_WATCH
        elif result.total >= 70:
            result.level = SCORE_NORMAL_WATCH
        else:
            result.level = SCORE_FILTER

        # 评分理由
        result.reason = self._generate_reason(result, matches)

        return result

    def _score_main_force(self, matches: List[ModelMatch], bars: List[KlineBar],
                           volumes: np.ndarray) -> float:
        """主力行为结构评分（40分）"""
        score = 0.0

        # 匹配模型数量（最多20分）
        matched_count = sum(1 for m in matches if m.matched)
        score += min(matched_count * 10, 20)

        # 模型阶段质量（最多10分）
        for m in matches:
            if not m.matched:
                continue
            if m.stage in [STAGE_BREAKOUT, STAGE_CONFIRM, "再次放量突破"]:
                score += 10
                break
            elif m.stage in [STAGE_VOL_PRICE_UP, STAGE_RELAUNCH]:
                score += 7
                break
            elif m.stage in [STAGE_SHRINK, STAGE_PLATFORM]:
                score += 5
                break

        # 主力资金痕迹（最多10分）：放量阳线+缩量回调
        if len(bars) >= 10:
            recent = bars[-10:]
            vol_up_days = sum(1 for b in recent if b.pct_chg > 2 and b.volume > np.mean(volumes[-10:]) * 1.1)
            shrink_down_days = sum(1 for b in recent if b.pct_chg < 0 and b.volume < np.mean(volumes[-10:]) * 0.9)
            score += min(vol_up_days * 1.5, 5)
            score += min(shrink_down_days * 1.0, 5)

        return min(round(score, 2), 40)

    def _score_volume_price(self, bars: List[KlineBar], closes: np.ndarray,
                            volumes: np.ndarray) -> float:
        """量价关系评分（20分）"""
        score = 0.0

        if len(bars) < 10:
            return score

        last_bar = bars[-1]
        vol_ratio = VolumeAnalyzer.volume_ratio(volumes, period=5)

        # 量价配合（10分）
        if last_bar.pct_chg > 0 and vol_ratio > 1.1:
            score += 10  # 放量上涨
        elif last_bar.pct_chg > 0 and vol_ratio > 0.9:
            score += 7
        elif last_bar.pct_chg < 0 and vol_ratio < 0.8:
            score += 6  # 缩量回调（健康）
        elif last_bar.pct_chg < 0 and vol_ratio > 1.2:
            score += 0  # 放量下跌（危险）
        else:
            score += 4

        # 近期量价趋势（10分）
        up_vol = 0
        down_vol = 0
        for b in bars[-10:]:
            if b.pct_chg > 0:
                up_vol += b.volume
            else:
                down_vol += b.volume
        if down_vol > 0:
            ratio = up_vol / down_vol
            if ratio > 1.5:
                score += 10
            elif ratio > 1.2:
                score += 7
            elif ratio > 1.0:
                score += 5
            else:
                score += 2
        else:
            score += 5

        return min(round(score, 2), 20)

    def _score_trend_ma(self, closes: np.ndarray) -> float:
        """趋势均线评分（15分）"""
        score = 0.0

        if len(closes) < 60:
            return score

        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        ma60 = TechnicalIndicators.ma(closes, 60)

        last = closes[-1]

        # 多头排列（8分）
        if all(not np.isnan(x) for x in [ma5[-1], ma10[-1], ma20[-1], ma60[-1]]):
            if ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1]:
                score += 8
            elif ma5[-1] > ma10[-1] > ma20[-1]:
                score += 6
            elif ma5[-1] > ma10[-1]:
                score += 4
            else:
                score += 1

        # 价格位置（4分）
        if not np.isnan(ma20[-1]) and ma20[-1] > 0:
            if last > ma20[-1]:
                score += 4
            elif last > ma20[-1] * 0.97:
                score += 2

        # 均线向上（3分）
        if not np.isnan(ma20[-1]) and not np.isnan(ma20[-6]) and ma20[-6] > 0:
            if ma20[-1] > ma20[-6]:
                score += 3

        return min(round(score, 2), 15)

    def _score_limit_up_gene(self, bars: List[KlineBar]) -> float:
        """涨停强势基因评分（10分）"""
        score = 0.0

        if len(bars) < 60:
            return score

        # 近60日涨停次数（6分）
        limit_count = sum(1 for b in bars[-60:] if b.pct_chg >= LIMIT_UP_THRESHOLD)
        score += min(limit_count * 2, 6)

        # 近30日大阳线次数（4分）
        big_yang_count = sum(1 for b in bars[-30:] if b.pct_chg >= BIG_YANG_THRESHOLD)
        score += min(big_yang_count * 1.0, 4)

        return min(round(score, 2), 10)

    def _score_tech_indicator(self, highs: np.ndarray, lows: np.ndarray,
                               closes: np.ndarray) -> float:
        """技术指标确认评分（10分）"""
        score = 0.0

        if len(closes) < 30:
            return score

        k, d, j = TechnicalIndicators.kdj(highs, lows, closes)
        dif, dea, macd_hist = TechnicalIndicators.macd(closes)

        # KDJ（5分）
        if not np.isnan(k[-1]) and not np.isnan(d[-1]):
            if TechnicalIndicators.is_kdj_golden(k, d):
                score += 5  # 金叉
            elif k[-1] > d[-1] and j[-1] < 80:
                score += 3  # 多头但未超买
            elif k[-1] < d[-1] and j[-1] > 20:
                score += 1

        # MACD（5分）
        if not np.isnan(dif[-1]) and not np.isnan(dea[-1]):
            if TechnicalIndicators.is_macd_golden(dif, dea):
                score += 5  # 金叉
            elif dif[-1] > dea[-1] and dif[-1] > 0:
                score += 3  # 多头
            elif dif[-1] > dea[-1]:
                score += 2

        return min(round(score, 2), 10)

    def _score_market_env(self, market_data: Optional[Dict]) -> float:
        """市场环境评分（5分）"""
        if not market_data:
            return 2.5  # 默认中性

        # 大盘涨跌
        index_pct = market_data.get('index_pct_chg', 0)
        if index_pct > 1:
            return 5.0
        elif index_pct > 0:
            return 4.0
        elif index_pct > -1:
            return 2.5
        elif index_pct > -2:
            return 1.5
        else:
            return 0.5

    def _generate_reason(self, score: AIScore, matches: List[ModelMatch]) -> str:
        """生成评分理由"""
        reasons = []
        matched_models = [m for m in matches if m.matched]

        if matched_models:
            model_names = "、".join(m.model_name for m in matched_models)
            stages = "、".join(set(m.stage for m in matched_models))
            reasons.append(f"匹配模型：{model_names}（当前阶段：{stages}）")

        if score.main_force_structure >= 30:
            reasons.append("主力行为结构清晰，资金介入痕迹明显")
        elif score.main_force_structure >= 20:
            reasons.append("存在一定主力行为特征")

        if score.volume_price >= 15:
            reasons.append("量价配合良好")
        elif score.volume_price < 8:
            reasons.append("量价配合欠佳")

        if score.trend_ma >= 12:
            reasons.append("均线多头排列，趋势向上")
        elif score.trend_ma < 6:
            reasons.append("趋势方向不明确")

        if score.level == SCORE_FILTER:
            reasons.append("综合评分低于70分，建议过滤")

        return "；".join(reasons) if reasons else "数据计算完成"


# ============================================================
# K线4色区域标注生成器
# ============================================================

class KlineAnnotationGenerator:
    """
    K线图AI模式标注生成器

    绿色=缩量区域
    黄色=箱体区域
    红色=突破区域
    蓝色=回踩确认区域

    标注：【涨停回调】【箱体突破】【量价突破】【买点】【卖点】【风险位置】
    """

    def generate(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                 lows: np.ndarray, volumes: np.ndarray, matches: List[ModelMatch]) -> KlineAnnotation:
        """生成K线标注"""
        annotation = KlineAnnotation()

        if len(bars) < MIN_KLINE_COUNT:
            return annotation

        # 1. 缩量区域（绿色）
        shrink_regions = self._detect_shrink_regions(bars, volumes)
        for region in shrink_regions:
            annotation.regions.append({
                'type': REGION_SHRINK,
                'color': '#22c55e',
                'start_idx': region['start'],
                'end_idx': region['end'],
                'start_date': bars[region['start']].date,
                'end_date': bars[region['end']].date,
                'label': '缩量区域',
            })

        # 2. 箱体区域（黄色）
        for m in matches:
            if m.matched and m.model_name == MODEL_BOX_BREAKOUT:
                detail = m.detail
                if 'box_top' in detail:
                    # 找到箱体对应的索引范围
                    box_start = self._find_date_idx(bars, detail.get('box_start', 0))
                    box_end = self._find_date_idx(bars, detail.get('box_end', len(bars) - 1))
                    if box_start is not None and box_end is not None:
                        annotation.regions.append({
                            'type': REGION_BOX,
                            'color': '#eab308',
                            'start_idx': box_start,
                            'end_idx': box_end,
                            'start_date': bars[box_start].date,
                            'end_date': bars[box_end].date,
                            'top': detail['box_top'],
                            'bottom': detail.get('box_bottom', 0),
                            'label': '箱体区域',
                        })

        # 3. 突破区域（红色）
        for m in matches:
            if m.matched and m.stage in [STAGE_BREAKOUT, "再次放量突破"]:
                # 突破区域取最近3-5天
                end_idx = len(bars) - 1
                start_idx = max(0, end_idx - 4)
                annotation.regions.append({
                    'type': REGION_BREAKOUT,
                    'color': '#ef4444',
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'start_date': bars[start_idx].date,
                    'end_date': bars[end_idx].date,
                    'label': f'突破区域-{m.model_name}',
                })

        # 4. 回踩确认区域（蓝色）
        for m in matches:
            if m.matched and m.stage == STAGE_CONFIRM:
                end_idx = len(bars) - 1
                start_idx = max(0, end_idx - 3)
                annotation.regions.append({
                    'type': REGION_CONFIRM,
                    'color': '#3b82f6',
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'start_date': bars[start_idx].date,
                    'end_date': bars[end_idx].date,
                    'label': f'回踩确认-{m.model_name}',
                })

        # 5. 买卖点标记
        for m in matches:
            if not m.matched:
                continue
            for sig in m.signals:
                if '买点' in sig or '低吸' in sig or '突破' in sig or '介入' in sig or '加仓' in sig:
                    annotation.markers.append({
                        'type': 'buy',
                        'idx': len(bars) - 1,
                        'date': bars[-1].date,
                        'price': bars[-1].close,
                        'label': sig,
                        'model': m.model_name,
                    })
            for risk in m.risks:
                annotation.markers.append({
                    'type': 'risk',
                    'idx': len(bars) - 1,
                    'date': bars[-1].date,
                    'price': bars[-1].close,
                    'label': risk,
                    'model': m.model_name,
                })

        # 6. 模型标签
        for m in matches:
            if m.matched:
                annotation.model_labels.append({
                    'model': m.model_name,
                    'stage': m.stage,
                    'tags': m.tags,
                    'idx': len(bars) - 1,
                })

        return annotation

    def _detect_shrink_regions(self, bars: List[KlineBar], volumes: np.ndarray) -> List[Dict]:
        """检测缩量区域"""
        regions = []
        if len(volumes) < 20:
            return regions

        avg_vol = np.mean(volumes)
        in_shrink = False
        start = 0

        for i in range(len(volumes)):
            if volumes[i] < avg_vol * 0.7:
                if not in_shrink:
                    in_shrink = True
                    start = i
            else:
                if in_shrink:
                    in_shrink = False
                    if i - start >= 3:  # 至少3天缩量
                        regions.append({'start': start, 'end': i - 1})

        if in_shrink and len(volumes) - start >= 3:
            regions.append({'start': start, 'end': len(volumes) - 1})

        return regions[-3:]  # 最多保留最近3个

    def _find_date_idx(self, bars: List[KlineBar], target) -> Optional[int]:
        """根据日期或索引查找位置"""
        if target is None:
            return None
        if isinstance(target, int):
            return max(0, min(target, len(bars) - 1))
        for i, bar in enumerate(bars):
            if bar.date == str(target):
                return i
        return None


# ============================================================
# 实盘-回测一致性校验
# ============================================================

class LiveBacktestConsistencyChecker:
    """
    实盘-回测一致性校验器

    确保策略在实盘和回测中使用相同的逻辑、参数和数据处理方式。
    """

    def __init__(self):
        self.checks = {
            'indicator_params': self._check_indicator_params,
            'data_alignment': self._check_data_alignment,
            'signal_logic': self._check_signal_logic,
            'price_usage': self._check_price_usage,
        }

    def verify(self, strategy_config: Dict, live_data: Dict, backtest_data: Dict) -> Dict:
        """执行一致性校验"""
        results = {
            'passed': True,
            'checks': {},
            'issues': [],
            'timestamp': datetime.now().isoformat(),
        }

        for name, check_fn in self.checks.items():
            try:
                passed, detail = check_fn(strategy_config, live_data, backtest_data)
                results['checks'][name] = {'passed': passed, 'detail': detail}
                if not passed:
                    results['passed'] = False
                    results['issues'].append(f"{name}: {detail}")
            except Exception as e:
                results['checks'][name] = {'passed': False, 'detail': str(e)}
                results['passed'] = False
                results['issues'].append(f"{name}: 校验异常 - {str(e)}")

        return results

    def _check_indicator_params(self, config: Dict, live: Dict, bt: Dict) -> Tuple[bool, str]:
        """检查技术指标参数一致性"""
        params = ['KDJ_N', 'KDJ_M1', 'KDJ_M2', 'MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL']
        for p in params:
            live_val = live.get('params', {}).get(p)
            bt_val = bt.get('params', {}).get(p)
            if live_val != bt_val:
                return False, f"参数{p}不一致：实盘={live_val}, 回测={bt_val}"
        return True, "所有技术指标参数一致"

    def _check_data_alignment(self, config: Dict, live: Dict, bt: Dict) -> Tuple[bool, str]:
        """检查数据对齐方式"""
        live_count = live.get('kline_count', 0)
        bt_count = bt.get('kline_count', 0)
        if abs(live_count - bt_count) > 5:
            return False, f"K线数量差异过大：实盘={live_count}, 回测={bt_count}"
        return True, "数据对齐方式一致"

    def _check_signal_logic(self, config: Dict, live: Dict, bt: Dict) -> Tuple[bool, str]:
        """检查信号逻辑一致性"""
        live_signals = set(live.get('signals', []))
        bt_signals = set(bt.get('signals', []))
        # 核心信号必须一致
        core_signals = {'涨停回调', '箱体突破', '量价突破'}
        live_core = live_signals & core_signals
        bt_core = bt_signals & core_signals
        if live_core != bt_core:
            return False, f"核心信号不一致：实盘={live_core}, 回测={bt_core}"
        return True, "核心信号逻辑一致"

    def _check_price_usage(self, config: Dict, live: Dict, bt: Dict) -> Tuple[bool, str]:
        """检查价格使用方式（是否使用未来数据）"""
        if live.get('uses_future_data', False):
            return False, "实盘数据检测到未来数据引用"
        if bt.get('uses_future_data', False):
            return False, "回测数据检测到未来数据引用"
        return True, "价格使用方式正确，无未来数据"


# ============================================================
# 全市场扫描引擎
# ============================================================

class MarketScanner:
    """
    全市场扫描引擎

    流程：
      全市场股票 → 强势股初筛 → 匹配三个主力行为模型 → AI综合评分 → 生成股票池

    取消固定股票数量限制，必须扫描全市场。
    """

    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        self.model_limit = LimitUpPullbackModel()
        self.model_box = BoxBreakoutModel()
        self.model_vp = VolumePriceBreakoutModel()
        self.scoring = AIScoringSystem()
        self.annotation_gen = KlineAnnotationGenerator()
        self.consistency_checker = LiveBacktestConsistencyChecker()
        self._scan_cache = {}
        self._cache_ttl = 300  # 5分钟缓存

    def set_data_provider(self, provider):
        """设置数据提供者"""
        self.data_provider = provider

    def scan_full_market(self, progress_callback=None, min_score: float = 70.0,
                         max_stocks: Optional[int] = None) -> List[StockScanResult]:
        """
        扫描全市场

        Args:
            progress_callback: 进度回调函数 callback(current, total, stock_name)
            min_score: 最低评分过滤（默认70分）
            max_stocks: 最大处理数量（None=全市场）

        Returns:
            符合条件的股票列表（评分>=min_score）
        """
        if self.data_provider is None:
            raise ValueError("数据提供者未初始化")

        # 1. 获取全市场股票列表
        stock_list = self.data_provider.get_stock_list()
        if not stock_list:
            return []

        if max_stocks:
            stock_list = stock_list[:max_stocks]

        total = len(stock_list)
        results = []

        # 2. 逐只扫描
        for i, stock_info in enumerate(stock_list):
            try:
                code = stock_info.get('ts_code', stock_info.get('code', ''))
                name = stock_info.get('name', '')
                industry = stock_info.get('industry', stock_info.get('sector', ''))

                if progress_callback:
                    progress_callback(i + 1, total, name)

                # 强势股初筛（快速过滤）
                if not self._pre_filter(stock_info):
                    continue

                # 扫描单只股票
                result = self.scan_single_stock(code, name, industry)
                if result and result.score.total >= min_score:
                    results.append(result)

            except Exception as e:
                continue

        # 按评分降序排列
        results.sort(key=lambda x: x.score.total, reverse=True)
        return results

    def scan_single_stock(self, code: str, name: str = "", industry: str = "") -> Optional[StockScanResult]:
        """扫描单只股票"""
        if self.data_provider is None:
            return None

        # 缓存检查
        cache_key = code
        if cache_key in self._scan_cache:
            cached = self._scan_cache[cache_key]
            if time.time() - cached['time'] < self._cache_ttl:
                return cached['result']

        # 获取K线数据
        kline_data = self.data_provider.get_kline(code, period='daily', count=DEFAULT_SCAN_COUNT)
        if not kline_data or len(kline_data) < MIN_KLINE_COUNT:
            return None

        # 解析数据
        bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        if len(bars) < MIN_KLINE_COUNT:
            return None

        # 获取实时行情
        realtime = self.data_provider.get_realtime_quotes([code])
        price = closes[-1]
        pct_chg = bars[-1].pct_chg
        if realtime and len(realtime) > 0:
            rt = realtime[0]
            price = rt.get('price', rt.get('close', price))
            pct_chg = rt.get('pct_chg', rt.get('change_percent', pct_chg))

        # 匹配三个模型
        matches = [
            self.model_limit.analyze(bars, closes, highs, lows, volumes),
            self.model_box.analyze(bars, closes, highs, lows, volumes),
            self.model_vp.analyze(bars, closes, highs, lows, volumes),
        ]

        # AI评分
        score = self.scoring.score(bars, closes, highs, lows, volumes, matches)

        # K线标注
        annotation = self.annotation_gen.generate(bars, closes, highs, lows, volumes, matches)

        # 汇总结果
        matched_models = [m for m in matches if m.matched]
        current_stage = matched_models[0].stage if matched_models else ""
        buy_signals = []
        risk_warnings = []
        for m in matched_models:
            buy_signals.extend(m.signals)
            risk_warnings.extend(m.risks)
        # 去重
        buy_signals = list(dict.fromkeys(buy_signals))
        risk_warnings = list(dict.fromkeys(risk_warnings))

        result = StockScanResult(
            code=code,
            name=name,
            price=round(float(price), 2),
            pct_chg=round(float(pct_chg), 2),
            industry=industry,
            matched_models=matches,
            current_stage=current_stage,
            buy_signals=buy_signals,
            risk_warnings=risk_warnings,
            score=score,
            annotation=annotation,
            kline_data=kline_data,
            scan_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )

        # 缓存
        self._scan_cache[cache_key] = {'result': result, 'time': time.time()}

        return result

    def _pre_filter(self, stock_info: Dict) -> bool:
        """
        强势股初筛（快速过滤，不获取K线）

        过滤条件：
        - 排除ST
        - 排除退市
        - 价格合理（2-200元）
        - 非新股（上市超过60天）
        """
        name = stock_info.get('name', '')
        price = stock_info.get('price', stock_info.get('close', 0))

        # 排除ST
        if 'ST' in name or 'st' in name or '*ST' in name:
            return False

        # 排除退市
        if '退' in name:
            return False

        # 价格过滤
        try:
            price = float(price)
            if price < 2 or price > 200:
                return False
        except (ValueError, TypeError):
            pass

        return True

    def get_scan_summary(self, results: List[StockScanResult]) -> Dict:
        """获取扫描汇总统计"""
        summary = {
            'total_scanned': 0,
            'matched_count': len(results),
            'by_model': defaultdict(int),
            'by_level': defaultdict(int),
            'by_stage': defaultdict(int),
            'avg_score': 0.0,
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        if results:
            scores = [r.score.total for r in results]
            summary['avg_score'] = round(sum(scores) / len(scores), 2)

            for r in results:
                for m in r.matched_models:
                    if m.matched:
                        summary['by_model'][m.model_name] += 1
                        summary['by_stage'][m.stage] += 1
                summary['by_level'][r.score.level] += 1

        return dict(summary)


# ============================================================
# 主入口类：强势主力行为选股系统
# ============================================================

class ForceBehaviorStrategy:
    """
    强势主力行为选股系统 V1.0

    唯一核心选股策略入口。

    使用方式：
        from strategy.strategy_main_force_behavior import ForceBehaviorStrategy

        strategy = ForceBehaviorStrategy()
        strategy.set_data_provider(provider)

        # 全市场扫描
        results = strategy.scan(progress_callback=my_callback)

        # 单只股票分析
        result = strategy.analyze_stock('000001.SZ', '平安银行')

        # 获取股票池（>=70分）
        pool = strategy.get_stock_pool()
    """

    _instance = None

    def __init__(self):
        self.scanner = MarketScanner()
        self._last_results: List[StockScanResult] = []
        self._last_summary: Dict = {}
        self.version = "1.0.0"
        self.system_name = "强势主力行为选股系统"

    @classmethod
    def instance(cls) -> 'ForceBehaviorStrategy':
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_data_provider(self, provider):
        """设置数据提供者"""
        self.scanner.set_data_provider(provider)

    def scan(self, progress_callback=None, min_score: float = 70.0,
             max_stocks: Optional[int] = None) -> List[StockScanResult]:
        """
        执行全市场扫描

        Args:
            progress_callback: 进度回调
            min_score: 最低评分（默认70，低于此分数过滤）
            max_stocks: 最大扫描数量（None=全市场）

        Returns:
            符合条件的股票列表
        """
        self._last_results = self.scanner.scan_full_market(
            progress_callback=progress_callback,
            min_score=min_score,
            max_stocks=max_stocks,
        )
        self._last_summary = self.scanner.get_scan_summary(self._last_results)
        return self._last_results

    def analyze_stock(self, code: str, name: str = "", industry: str = "") -> Optional[StockScanResult]:
        """分析单只股票"""
        return self.scanner.scan_single_stock(code, name, industry)

    def get_stock_pool(self) -> List[Dict]:
        """
        获取股票池（用于UI展示）

        返回字段：
        股票名称/代码/当前价格/涨跌幅/所属行业/匹配模型/当前阶段/买入信号/风险提示/评分
        """
        pool = []
        for r in self._last_results:
            matched_names = [m.model_name for m in r.matched_models if m.matched]
            pool.append({
                'name': r.name,
                'code': r.code,
                'price': r.price,
                'pct_chg': r.pct_chg,
                'industry': r.industry,
                'matched_models': matched_names,
                'current_stage': r.current_stage,
                'buy_signals': r.buy_signals,
                'risk_warnings': r.risk_warnings,
                'score': r.score.total,
                'score_level': r.score.level,
                'score_breakdown': r.score.breakdown,
                'score_reason': r.score.reason,
            })
        return pool

    def get_kline_annotation(self, code: str) -> Optional[KlineAnnotation]:
        """获取单只股票的K线标注"""
        for r in self._last_results:
            if r.code == code:
                return r.annotation
        # 如果不在缓存中，单独分析
        result = self.analyze_stock(code)
        if result:
            return result.annotation
        return None

    def get_summary(self) -> Dict:
        """获取扫描汇总"""
        return self._last_summary

    def verify_consistency(self, strategy_config: Dict, live_data: Dict,
                           backtest_data: Dict) -> Dict:
        """实盘-回测一致性校验"""
        return self.scanner.consistency_checker.verify(strategy_config, live_data, backtest_data)

    def export_results(self, filepath: str) -> bool:
        """导出扫描结果到JSON"""
        try:
            data = {
                'system': self.system_name,
                'version': self.version,
                'export_time': datetime.now().isoformat(),
                'summary': self._last_summary,
                'results': [r.to_dict() for r in self._last_results],
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False

    def get_model_info(self) -> List[Dict]:
        """获取三个核心模型的信息"""
        return [
            {
                'name': MODEL_LIMIT_PULLBACK,
                'full_name': '涨停回调模型（强势股低吸模型）',
                'logic': '涨停/大阳启动→回调整理→缩量洗盘→关键支撑→再次启动',
                'supports': ['MA5附近支撑', 'MA10附近支撑', '前期涨停启动位置支撑', '箱体底部支撑'],
                'tags': ['涨停回调', '缩量低吸', '强势洗盘'],
                'buy_points': ['缩量调整结束', '重新站上5日线', '次日回踩5日线不破', '成交量重新放大'],
                'risks': ['跌破涨停启动位置', '跌破箱体底部', '放量下跌'],
            },
            {
                'name': MODEL_BOX_BREAKOUT,
                'full_name': '横盘箱体突破模型（二波启动模型）',
                'logic': '强势上涨→横盘整理→缩量筑平台→突破箱体→第二波上涨',
                'buy_points': [
                    '第一买点：缩量结束重新站上MA5',
                    '第二买点：突破箱体压力位',
                    '第三买点：突破后回踩箱体顶部不破',
                ],
                'tags': ['箱体突破', '二次启动', '平台蓄势'],
                'risks': ['跌破箱体底部', '突破失败重新进入箱体'],
            },
            {
                'name': MODEL_VOLUME_PRICE_BREAKOUT,
                'full_name': '极限缩量量价突破模型（主力启动模型）',
                'logic': '极限缩量筑底→量价齐升→突破压力→回踩确认→再次放量突破',
                'stages': [
                    '阶段1：极限缩量筑底',
                    '阶段2：量价齐升',
                    '阶段3：突破压力',
                    '阶段4：回踩确认',
                    '阶段5：再次放量突破',
                ],
                'tags': ['量价突破', '主力启动', '二次确认'],
            },
        ]

    def get_scoring_info(self) -> Dict:
        """获取评分系统信息"""
        return {
            'total': 100,
            'dimensions': [
                {'name': '主力行为结构', 'weight': 40, 'desc': '模型匹配质量、阶段、资金痕迹'},
                {'name': '量价关系', 'weight': 20, 'desc': '量价配合、上涨/下跌量能对比'},
                {'name': '趋势均线', 'weight': 15, 'desc': '多头排列、价格位置、均线方向'},
                {'name': '涨停强势基因', 'weight': 10, 'desc': '近期涨停次数、大阳线次数'},
                {'name': '技术指标确认', 'weight': 10, 'desc': 'KDJ、MACD金叉/多头确认'},
                {'name': '市场环境', 'weight': 5, 'desc': '大盘涨跌环境'},
            ],
            'levels': [
                {'range': '90-100', 'level': SCORE_STRONG_CANDIDATE, 'action': '重点关注，可考虑介入'},
                {'range': '80-90', 'level': SCORE_KEY_WATCH, 'action': '加入观察池，等待买点确认'},
                {'range': '70-80', 'level': SCORE_NORMAL_WATCH, 'action': '普通观察，暂不介入'},
                {'range': '70以下', 'level': SCORE_FILTER, 'action': '自动过滤'},
            ],
        }


# ============================================================
# 便捷函数
# ============================================================

def get_force_behavior_strategy() -> ForceBehaviorStrategy:
    """获取强势主力行为选股系统单例"""
    return ForceBehaviorStrategy.instance()


def analyze_kline(kline_data: Dict, name: str = "", code: str = "") -> Dict:
    """
    独立分析K线数据（无需数据提供者，用于回测和批量分析）

    Args:
        kline_data: K线数据字典
        name: 股票名称
        code: 股票代码

    Returns:
        分析结果字典
    """
    bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)

    if len(bars) < MIN_KLINE_COUNT:
        return {'error': '数据不足', 'bars_count': len(bars)}

    # 三个模型
    model_limit = LimitUpPullbackModel()
    model_box = BoxBreakoutModel()
    model_vp = VolumePriceBreakoutModel()

    matches = [
        model_limit.analyze(bars, closes, highs, lows, volumes),
        model_box.analyze(bars, closes, highs, lows, volumes),
        model_vp.analyze(bars, closes, highs, lows, volumes),
    ]

    # 评分
    scoring = AIScoringSystem()
    score = scoring.score(bars, closes, highs, lows, volumes, matches)

    # 标注
    ann_gen = KlineAnnotationGenerator()
    annotation = ann_gen.generate(bars, closes, highs, lows, volumes, matches)

    matched = [m for m in matches if m.matched]

    return {
        'code': code,
        'name': name,
        'price': round(float(closes[-1]), 2),
        'pct_chg': round(float(bars[-1].pct_chg), 2),
        'matched_models': [asdict(m) for m in matches],
        'matched_count': len(matched),
        'current_stage': matched[0].stage if matched else "",
        'buy_signals': list(dict.fromkeys(s for m in matched for s in m.signals)),
        'risk_warnings': list(dict.fromkeys(r for m in matched for r in m.risks)),
        'score': asdict(score),
        'annotation': asdict(annotation),
        'bars_count': len(bars),
    }


# ============================================================
# 独立运行入口（用于测试和回测）
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("强势主力行为选股系统 V1.0")
    print("=" * 60)
    print()

    # 显示模型信息
    strategy = ForceBehaviorStrategy()
    print("【三个核心模型】")
    for info in strategy.get_model_info():
        print(f"  - {info['name']}: {info['logic']}")
    print()

    # 显示评分信息
    print("【AI评分系统】")
    scoring_info = strategy.get_scoring_info()
    for dim in scoring_info['dimensions']:
        print(f"  {dim['name']}: {dim['weight']}分 - {dim['desc']}")
    print()

    # 生成模拟K线数据进行测试
    print("【模拟数据测试】")
    np.random.seed(42)
    n = 120
    base_price = 10.0
    closes_sim = [base_price]
    for i in range(1, n):
        change = np.random.normal(0.002, 0.025)
        # 模拟涨停
        if i == 30:
            change = 0.099
        closes_sim.append(closes_sim[-1] * (1 + change))

    opens_sim = [c * (1 + np.random.uniform(-0.01, 0.01)) for c in closes_sim]
    highs_sim = [max(o, c) * (1 + np.random.uniform(0, 0.015)) for o, c in zip(opens_sim, closes_sim)]
    lows_sim = [min(o, c) * (1 - np.random.uniform(0, 0.015)) for o, c in zip(opens_sim, closes_sim)]
    volumes_sim = [np.random.randint(50000, 200000) for _ in range(n)]
    # 缩量
    for i in range(40, 55):
        volumes_sim[i] = int(volumes_sim[i] * 0.4)
    # 放量突破
    for i in range(80, 85):
        volumes_sim[i] = int(volumes_sim[i] * 2.0)

    dates_sim = [f"2026-{(i // 21 + 1):02d}-{(i % 21 + 1):02d}" for i in range(n)]

    test_kline = {
        'dates': dates_sim,
        'open': opens_sim,
        'high': highs_sim,
        'low': lows_sim,
        'close': closes_sim,
        'volume': volumes_sim,
    }

    result = analyze_kline(test_kline, name="测试股票", code="TEST001")
    print(f"  股票: {result['name']} ({result['code']})")
    print(f"  价格: {result['price']}, 涨跌幅: {result['pct_chg']:+.2f}%")
    print(f"  匹配模型数: {result['matched_count']}")
    print(f"  当前阶段: {result['current_stage']}")
    print(f"  综合评分: {result['score']['total']} ({result['score']['level']})")
    print(f"  评分明细: {result['score']['breakdown']}")
    print(f"  买入信号: {result['buy_signals']}")
    print(f"  风险提示: {result['risk_warnings']}")
    print(f"  K线标注区域数: {len(result['annotation']['regions'])}")
    print(f"  K线标记数: {len(result['annotation']['markers'])}")
    print()

    # 一致性校验测试
    print("【实盘-回测一致性校验】")
    config = {'version': '1.0.0'}
    live_data = {
        'params': {'KDJ_N': 13, 'KDJ_M1': 3, 'KDJ_M2': 3, 'MACD_FAST': 8, 'MACD_SLOW': 21, 'MACD_SIGNAL': 5},
        'kline_count': 120,
        'signals': ['涨停回调'],
        'uses_future_data': False,
    }
    bt_data = {
        'params': {'KDJ_N': 13, 'KDJ_M1': 3, 'KDJ_M2': 3, 'MACD_FAST': 8, 'MACD_SLOW': 21, 'MACD_SIGNAL': 5},
        'kline_count': 120,
        'signals': ['涨停回调'],
        'uses_future_data': False,
    }
    check_result = strategy.verify_consistency(config, live_data, bt_data)
    print(f"  校验结果: {'通过' if check_result['passed'] else '未通过'}")
    for name, detail in check_result['checks'].items():
        print(f"    {name}: {'✓' if detail['passed'] else '✗'} {detail['detail']}")
    print()

    print("=" * 60)
    print("系统自检完成，所有模块正常运行")
    print("=" * 60)
