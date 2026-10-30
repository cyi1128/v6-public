# -*- coding: utf-8 -*-
"""
九重共振选股中心 - 九重过滤主引擎 V1.0

九重过滤体系：
  第1重：市场情绪周期（涨停数/跌停数/炸板率/连板高度/情绪温度）
  第2重：MA多头排列（MA5>MA10>MA20）
  第3重：首次突破60日线
  第4重：RPS20相对强度（全市场排名>=80）
  第5重：筹码峰分析（单峰密集+价格在峰上）
  第6重：量比过滤（近5日均量/前5日均量>=1.5）
  第7重：大单净量（连续为正，逐步放大）- 日K线代理：成交量递增+阳线
  第8重：活跃度过滤（涨跌幅0.5%-2.5%）+ 资金评分>=60
  第9重：分时执行标记（突破/回踩/放量/止损位）

数据来源：通达信本地.day文件（优先）+ 现有实时行情接口（增强）
缓存：扫描结果缓存30分钟
"""
import os
import json
import time
import threading
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

# 通达信数据引擎
try:
    from data.tdx_data_engine import get_tdx_data_engine
    TDX_AVAILABLE = True
except Exception as e:
    print(f"[NINE FILTER] 通达信引擎导入失败: {e}", flush=True)
    TDX_AVAILABLE = False

# 基础指标
from strategy.base import (
    TechnicalIndicators, VolumeAnalyzer, KlineDataParser,
    KlineBar, LIMIT_UP_THRESHOLD,
)

# 评分引擎
from strategy.nine_score_engine import (
    NineScoreEngine, NineScoreResult, get_nine_score_engine,
    GRADE_S_PLUS, GRADE_S, GRADE_A,
)

# 首板回调模型
from strategy.first_board_pullback import (
    FirstBoardPullbackModel, FirstBoardPullbackResult,
)

# 并行扫描器
try:
    from strategy.parallel_scanner import ParallelScanner, ScanProgress
    PARALLEL_AVAILABLE = True
except Exception as e:
    print(f"[NINE FILTER] 并行扫描器导入失败: {e}", flush=True)
    PARALLEL_AVAILABLE = False


# ============================================================
# 常量
# ============================================================
CACHE_TTL = 1800  # 缓存有效期30分钟（秒）
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "nine_filter_scan_cache.json")

# 市场情绪周期
CYCLE_RISING = "上升期"
CYCLE_CHAOS = "混沌期"
CYCLE_FALLING = "退潮期"
CYCLE_FREEZING = "冰点期"

# 九重名称
LAYER_NAMES = [
    "市场情绪周期",
    "MA多头排列",
    "突破60日线",
    "RPS20强度",
    "筹码峰分析",
    "量比过滤",
    "大单净量",
    "活跃度+资金评分",
    "分时执行标记",
]


@dataclass
class NineFilterStockResult:
    """单只股票九重过滤结果"""
    code: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    amount: float = 0.0
    volume: float = 0.0
    turnover_rate: float = 0.0
    volume_ratio: float = 1.0
    rps20: float = 50.0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    industry: str = ""
    # 九重通过状态
    layer_pass: List[bool] = field(default_factory=lambda: [False] * 9)
    pass_count: int = 0
    # 评分
    score: NineScoreResult = field(default_factory=NineScoreResult)
    # 首板回调
    first_board: FirstBoardPullbackResult = field(default_factory=FirstBoardPullbackResult)
    # 资金评分（第8重用，0-100）
    fund_score_100: float = 0.0
    # 筹码峰信息
    chip_peak_price: float = 0.0
    chip_peak_type: str = ""  # 单峰/多峰
    chip_position: str = ""   # 价格在峰上/峰中/峰下
    # 分时执行信号
    intraday_signal: str = ""
    support_price: float = 0.0
    pressure_price: float = 0.0
    # 其他
    scan_time: str = ""
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "price": round(self.price, 2),
            "change_pct": round(self.change_pct, 2),
            "amount": round(float(self.amount), 0),
            "volume": round(float(self.volume), 0),
            "turnover_rate": round(float(self.turnover_rate), 2),
            "volume_ratio": round(float(self.volume_ratio), 2),
            "rps20": round(float(self.rps20), 1),
            "ma5": round(float(self.ma5), 2),
            "ma10": round(float(self.ma10), 2),
            "ma20": round(float(self.ma20), 2),
            "ma60": round(float(self.ma60), 2),
            "industry": self.industry,
            "layer_pass": [bool(x) for x in self.layer_pass],
            "pass_count": int(self.pass_count),
            "score": self.score.to_dict(),
            "first_board": self.first_board.to_dict(),
            "fund_score_100": round(self.fund_score_100, 1),
            "chip_peak_price": round(self.chip_peak_price, 2),
            "chip_peak_type": self.chip_peak_type,
            "chip_position": self.chip_position,
            "intraday_signal": self.intraday_signal,
            "support_price": round(self.support_price, 2),
            "pressure_price": round(self.pressure_price, 2),
            "scan_time": self.scan_time,
            "reasons": self.reasons,
        }


@dataclass
class MarketSentiment:
    """市场情绪状态"""
    cycle: str = CYCLE_CHAOS
    limit_up_count: int = 0
    limit_down_count: int = 0
    broken_board_rate: float = 0.0  # 炸板率%
    max_consecutive_board: int = 0  # 最高连板高度
    sentiment_temperature: float = 50.0  # 情绪温度0-100
    up_count: int = 0
    down_count: int = 0
    total_count: int = 0
    calc_time: str = ""

    def to_dict(self) -> Dict:
        return {
            "cycle": self.cycle,
            "limit_up_count": self.limit_up_count,
            "limit_down_count": self.limit_down_count,
            "broken_board_rate": round(self.broken_board_rate, 1),
            "max_consecutive_board": self.max_consecutive_board,
            "sentiment_temperature": round(self.sentiment_temperature, 1),
            "up_count": self.up_count,
            "down_count": self.down_count,
            "total_count": self.total_count,
            "calc_time": self.calc_time,
        }


class NineFilterStrategy:
    """九重共振选股主引擎"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.tdx_engine = None
        self.score_engine = get_nine_score_engine()
        self.fb_model = FirstBoardPullbackModel()
        self.scanner = ParallelScanner(max_workers=8, throttle=0.0) if PARALLEL_AVAILABLE else None
        self._cache_lock = threading.Lock()
        self._scan_running = False
        self._funnel_stats = {}
        self._market_sentiment = MarketSentiment()
        self._rps20_map = {}  # RPS20全市场排名
        self._amount_rank_map = {}  # 成交额排名百分位
        self._init_data_engine()

    # ============================================================
    # 单例
    # ============================================================
    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _init_data_engine(self):
        """初始化数据引擎"""
        if TDX_AVAILABLE:
            try:
                self.tdx_engine = get_tdx_data_engine()
                if self.tdx_engine and self.tdx_engine.is_available():
                    print(f"[NINE FILTER] 通达信数据引擎就绪: {self.tdx_engine.get_tdx_path()}", flush=True)
                else:
                    print("[NINE FILTER] 通达信引擎不可用，将使用有限数据", flush=True)
            except Exception as e:
                print(f"[NINE FILTER] 数据引擎初始化失败: {e}", flush=True)

    # ============================================================
    # 第1重：市场情绪周期计算
    # ============================================================
    def calculate_market_sentiment(self, all_kline: Dict[str, List[Dict]]) -> MarketSentiment:
        """
        基于全市场K线数据计算市场情绪

        Args:
            all_kline: {code: kline_list} 全市场K线数据

        Returns:
            MarketSentiment
        """
        sentiment = MarketSentiment()
        sentiment.total_count = len(all_kline)
        sentiment.calc_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not all_kline:
            return sentiment

        limit_up_codes = []
        limit_down_codes = []
        up_codes = []
        down_codes = []
        consecutive_heights = []

        for code, kline in all_kline.items():
            if not kline or len(kline) < 2:
                continue
            latest = kline[-1]
            prev = kline[-2]
            change_pct = 0.0
            if prev.get('close', 0) > 0:
                change_pct = (latest['close'] - prev['close']) / prev['close'] * 100

            if change_pct > 0:
                up_codes.append(code)
            elif change_pct < 0:
                down_codes.append(code)

            # 涨停
            if change_pct >= LIMIT_UP_THRESHOLD:
                limit_up_codes.append(code)
                # 计算连板高度
                height = 1
                for i in range(len(kline) - 2, max(-1, len(kline) - 15), -1):
                    if i >= 1 and kline[i].get('close', 0) > 0:
                        prev_chg = (kline[i]['close'] - kline[i-1]['close']) / kline[i-1]['close'] * 100
                        if prev_chg >= LIMIT_UP_THRESHOLD:
                            height += 1
                        else:
                            break
                consecutive_heights.append(height)

            # 跌停
            if change_pct <= -9.5:
                limit_down_codes.append(code)

        sentiment.limit_up_count = len(limit_up_codes)
        sentiment.limit_down_count = len(limit_down_codes)
        sentiment.up_count = len(up_codes)
        sentiment.down_count = len(down_codes)
        sentiment.max_consecutive_board = max(consecutive_heights) if consecutive_heights else 0

        # 炸板率估算（涨停后次日低开比例，用近期数据估算）
        # 简化：用涨停数/上涨数的偏离度估算
        if sentiment.up_count > 0:
            lu_ratio = sentiment.limit_up_count / sentiment.up_count * 100
            # 正常炸板率约30-50%，这里用模型估算
            sentiment.broken_board_rate = min(60.0, max(10.0, 40.0 - lu_ratio * 2))

        # 情绪温度计算（0-100）
        temp = 50.0
        if sentiment.total_count > 0:
            up_ratio = sentiment.up_count / sentiment.total_count * 100
            temp = up_ratio * 0.5  # 涨跌比贡献50分
        # 涨停数贡献
        temp += min(25, sentiment.limit_up_count * 0.5)
        # 连板高度贡献
        temp += min(15, sentiment.max_consecutive_board * 3)
        # 跌停数惩罚
        temp -= min(20, sentiment.limit_down_count * 1.0)
        sentiment.sentiment_temperature = max(0, min(100, temp))

        # 判定周期
        if sentiment.sentiment_temperature >= 70 and sentiment.limit_up_count >= 30:
            sentiment.cycle = CYCLE_RISING
        elif sentiment.sentiment_temperature >= 45:
            sentiment.cycle = CYCLE_CHAOS
        elif sentiment.sentiment_temperature >= 25:
            sentiment.cycle = CYCLE_FALLING
        else:
            sentiment.cycle = CYCLE_FREEZING

        self._market_sentiment = sentiment
        print(f"[NINE FILTER] 市场情绪: {sentiment.cycle} | 涨停{sentiment.limit_up_count} "
              f"跌停{sentiment.limit_down_count} 连板高度{sentiment.max_consecutive_board} "
              f"温度{sentiment.sentiment_temperature:.0f}", flush=True)
        return sentiment

    # ============================================================
    # 第2-5重：单股技术过滤
    # ============================================================
    def _filter_technical(self, code: str, kline: List[Dict],
                           rps20: float) -> Tuple[List[bool], Dict]:
        """
        第2-5重技术过滤

        Returns:
            (layer_pass[1..4]对应第2-5重, info_dict)
        """
        layers = [False] * 4  # 索引0=第2重, 1=第3重, 2=第4重, 3=第5重
        info = {}

        if not kline or len(kline) < 60:
            return layers, info

        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
        except Exception:
            return layers, info

        last_idx = len(bars) - 1
        if last_idx < 60:
            return layers, info

        # 计算均线
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        ma60 = TechnicalIndicators.ma(closes, 60)

        info['ma5'] = ma5[last_idx] if not np.isnan(ma5[last_idx]) else 0
        info['ma10'] = ma10[last_idx] if not np.isnan(ma10[last_idx]) else 0
        info['ma20'] = ma20[last_idx] if not np.isnan(ma20[last_idx]) else 0
        info['ma60'] = ma60[last_idx] if not np.isnan(ma60[last_idx]) else 0

        # 第2重：MA5>MA10>MA20 多头排列
        if (not np.isnan(ma5[last_idx]) and not np.isnan(ma10[last_idx])
                and not np.isnan(ma20[last_idx])):
            if ma5[last_idx] > ma10[last_idx] > ma20[last_idx]:
                layers[0] = True

        # 第3重：首次突破60日线（今日收盘价>MA60，且昨日<=MA60）
        if not np.isnan(ma60[last_idx]) and last_idx >= 1 and not np.isnan(ma60[last_idx - 1]):
            if closes[last_idx] > ma60[last_idx] and closes[last_idx - 1] <= ma60[last_idx - 1]:
                layers[1] = True
            # 放宽：价格在MA60之上且MA60向上
            elif closes[last_idx] > ma60[last_idx] and ma60[last_idx] > ma60[last_idx - 5]:
                layers[1] = True
                info['ma60_uptrend'] = True

        # 第4重：RPS20 >= 80
        info['rps20'] = rps20
        if rps20 >= 80:
            layers[2] = True

        # 第5重：筹码峰分析
        chip_score, chip_info = self._analyze_chip_peak(bars, closes, volumes, last_idx)
        info.update(chip_info)
        info['chip_score'] = chip_score
        if chip_score >= 60:
            layers[3] = True

        return layers, info

    def _analyze_chip_peak(self, bars: List[KlineBar], closes: np.ndarray,
                             volumes: np.ndarray, last_idx: int) -> Tuple[float, Dict]:
        """
        筹码峰分析（基于近60日成交量加权价格分布）

        Returns:
            (chip_score 0-100, info_dict)
        """
        info = {}
        lookback = min(60, last_idx + 1)
        if lookback < 20:
            return 0, info

        start = last_idx - lookback + 1
        segment_closes = closes[start:last_idx + 1]
        segment_volumes = volumes[start:last_idx + 1]

        # 构建成交量加权价格分布
        price_min = np.min(segment_closes)
        price_max = np.max(segment_closes)
        if price_max <= price_min:
            return 0, info

        # 分10个价格区间
        bins = 10
        bin_width = (price_max - price_min) / bins
        volume_dist = np.zeros(bins)

        for i in range(lookback):
            price = segment_closes[i]
            vol = segment_volumes[i]
            bin_idx = min(bins - 1, int((price - price_min) / bin_width))
            volume_dist[bin_idx] += vol

        # 找到主峰
        peak_idx = np.argmax(volume_dist)
        peak_volume = volume_dist[peak_idx]
        total_volume = np.sum(volume_dist)
        peak_concentration = peak_volume / total_volume * 100 if total_volume > 0 else 0

        # 判断单峰/多峰（峰值数量）
        peak_count = 0
        threshold = np.max(volume_dist) * 0.5
        for i in range(bins):
            if volume_dist[i] >= threshold:
                peak_count += 1

        peak_type = "单峰" if peak_count <= 2 else "多峰"
        info['chip_peak_type'] = peak_type
        info['peak_concentration'] = round(peak_concentration, 1)

        # 主峰价格
        peak_price = price_min + (peak_idx + 0.5) * bin_width
        info['chip_peak_price'] = round(peak_price, 2)

        # 当前价格位置
        current_price = closes[last_idx]
        if current_price > peak_price * 1.03:
            position = "峰上"
        elif current_price < peak_price * 0.97:
            position = "峰下"
        else:
            position = "峰中"
        info['chip_position'] = position

        # 筹码评分
        score = 0.0
        # 单峰密集加分
        if peak_type == "单峰" and peak_concentration >= 30:
            score += 40.0
        elif peak_type == "单峰":
            score += 25.0
        else:
            score += 10.0
        # 价格在峰上加分
        if position == "峰上":
            score += 40.0
        elif position == "峰中":
            score += 25.0
        else:
            score += 10.0
        # 集中度加分
        score += min(20, peak_concentration * 0.5)

        return min(score, 100.0), info

    # ============================================================
    # 第6-8重：资金验证过滤
    # ============================================================
    def _filter_fund(self, code: str, kline: List[Dict],
                      amount_rank_pct: float) -> Tuple[List[bool], Dict]:
        """
        第6-8重资金验证

        Returns:
            (layer_pass[0..2]对应第6-8重, info_dict)
        """
        layers = [False] * 3
        info = {}

        if not kline or len(kline) < 15:
            return layers, info

        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
        except Exception:
            return layers, info

        last_idx = len(bars) - 1

        # 第6重：量比 >= 1.5（近5日均量/前5日均量）
        if last_idx >= 10:
            recent_vol = np.mean(volumes[-5:])
            prev_vol = np.mean(volumes[-10:-5])
            volume_ratio = recent_vol / prev_vol if prev_vol > 0 else 1.0
            info['volume_ratio'] = round(volume_ratio, 2)
            if volume_ratio >= 1.5:
                layers[0] = True

        # 第7重：大单净量代理（日K线：最近3日阳线+成交量递增）
        if last_idx >= 3:
            big_order_positive = True
            volume_increasing = True
            for i in range(last_idx - 2, last_idx + 1):
                if bars[i].close <= bars[i].open:
                    big_order_positive = False
                    break
            for i in range(last_idx - 2, last_idx):
                if volumes[i + 1] <= volumes[i]:
                    volume_increasing = False
                    break
            # 大单净量估算（用阳线实体*成交量代理）
            big_order_net = 0.0
            for i in range(max(0, last_idx - 4), last_idx + 1):
                if bars[i].close > bars[i].open:
                    big_order_net += (bars[i].close - bars[i].open) * volumes[i] / 1000.0
                else:
                    big_order_net += (bars[i].close - bars[i].open) * volumes[i] / 1000.0
            info['big_order_net_est'] = round(big_order_net, 1)

            if big_order_positive and volume_increasing:
                layers[1] = True
                info['big_order_trend'] = "连续为正且放大"
            elif big_order_positive:
                info['big_order_trend'] = "连续为正"

        # 第8重：活跃度过滤（涨跌幅0.5%-2.5%）+ 资金评分>=60
        latest = bars[last_idx]
        change_pct = latest.pct_chg
        info['change_pct'] = round(change_pct, 2)

        active_filter = 0.5 <= abs(change_pct) <= 2.5
        info['active_filter'] = active_filter

        # 资金评分（0-100）
        fund_score_100 = self._calc_fund_score_100(info, amount_rank_pct, latest)
        info['fund_score_100'] = round(fund_score_100, 1)

        if active_filter and fund_score_100 >= 60:
            layers[2] = True

        return layers, info

    def _calc_fund_score_100(self, info: Dict, amount_rank_pct: float,
                               latest_bar: KlineBar) -> float:
        """计算资金评分（0-100），用于第8重过滤"""
        score = 0.0
        # 量比 40分
        vr = info.get('volume_ratio', 1.0)
        if vr >= 2.0:
            score += 40.0
        elif vr >= 1.5:
            score += 30.0 + (vr - 1.5) * 20
        elif vr >= 1.0:
            score += 15.0 + (vr - 1.0) * 30
        else:
            score += vr * 15.0

        # 大单净量 25分
        bo = info.get('big_order_net_est', 0)
        if bo > 1000:
            score += 25.0
        elif bo > 0:
            score += 10.0 + min(15, bo / 1000 * 15)
        else:
            score += max(0, 10 + bo / 500)

        # 成交额排名 35分
        score += amount_rank_pct / 100.0 * 35.0

        return min(score, 100.0)

    # ============================================================
    # 第9重：分时执行标记
    # ============================================================
    def _mark_intraday_execution(self, code: str, kline: List[Dict],
                                   info: Dict) -> Dict:
        """
        第9重：分时执行标记（基于日K线标记关键价位和信号）

        Returns:
            {intraday_signal, support_price, pressure_price}
        """
        result = {
            'intraday_signal': '',
            'support_price': 0.0,
            'pressure_price': 0.0,
        }

        if not kline or len(kline) < 10:
            return result

        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline)
        except Exception:
            return result

        last_idx = len(bars) - 1
        current_price = closes[last_idx]

        # 支撑位：MA10或近期低点
        ma10 = TechnicalIndicators.ma(closes, 10)
        if not np.isnan(ma10[last_idx]):
            result['support_price'] = ma10[last_idx]
        else:
            result['support_price'] = np.min(lows[-10:])

        # 压力位：近期高点或涨停高点
        result['pressure_price'] = np.max(highs[-20:])

        # 标记信号
        signals = []
        # 突破信号：价格创近20日新高
        if last_idx >= 20 and current_price >= np.max(highs[-20:-1]) * 0.99:
            signals.append("突破")
        # 回踩信号：价格回踩MA10
        if not np.isnan(ma10[last_idx]) and abs(current_price - ma10[last_idx]) / ma10[last_idx] < 0.02:
            signals.append("回踩MA10")
        # 放量信号
        if last_idx >= 5 and volumes[last_idx] > np.mean(volumes[-5:-1]) * 1.5:
            signals.append("放量")
        # 止损位标记
        stop_loss = result['support_price'] * 0.97
        signals.append(f"止损{stop_loss:.2f}")

        result['intraday_signal'] = "|".join(signals)
        return result

    # ============================================================
    # RPS20全市场计算
    # ============================================================
    def _calculate_rps20(self, all_kline: Dict[str, List[Dict]]) -> Dict[str, float]:
        """计算全市场RPS20（20日涨幅排名百分位）"""
        rps_map = {}
        changes = {}

        for code, kline in all_kline.items():
            if not kline or len(kline) < 21:
                continue
            try:
                current = kline[-1]['close']
                prev_20 = kline[-21]['close']
                if prev_20 > 0:
                    changes[code] = (current - prev_20) / prev_20 * 100
            except Exception:
                continue

        if not changes:
            return rps_map

        # 按涨幅排序
        sorted_codes = sorted(changes.keys(), key=lambda c: changes[c])
        total = len(sorted_codes)
        for rank, code in enumerate(sorted_codes):
            rps_map[code] = (rank + 1) / total * 100.0

        print(f"[NINE FILTER] RPS20计算完成: {len(rps_map)}只股票", flush=True)
        return rps_map

    def _calculate_amount_rank(self, all_kline: Dict[str, List[Dict]]) -> Dict[str, float]:
        """计算成交额排名百分位"""
        amount_map = {}
        for code, kline in all_kline.items():
            if not kline:
                continue
            try:
                amount_map[code] = kline[-1].get('amount', 0)
            except Exception:
                continue

        if not amount_map:
            return {}

        sorted_codes = sorted(amount_map.keys(), key=lambda c: amount_map[c])
        total = len(sorted_codes)
        rank_map = {}
        for rank, code in enumerate(sorted_codes):
            rank_map[code] = (rank + 1) / total * 100.0
        return rank_map

    # ============================================================
    # 单股完整分析
    # ============================================================
    def analyze_stock(self, code: str, kline: List[Dict],
                       rps20: float = 50.0,
                       amount_rank_pct: float = 50.0,
                       name: str = "") -> NineFilterStockResult:
        """对单只股票执行九重过滤"""
        result = NineFilterStockResult(code=code, name=name)
        result.scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not kline or len(kline) < 2:
            return result

        # 基础数据
        latest = kline[-1]
        prev = kline[-2] if len(kline) >= 2 else latest
        result.price = latest.get('close', 0)
        result.amount = latest.get('amount', 0)
        result.volume = latest.get('volume', 0)
        if prev.get('close', 0) > 0:
            result.change_pct = (latest['close'] - prev['close']) / prev['close'] * 100

        # 换手率估算（成交额/市值，这里用成交额代理排名）
        result.turnover_rate = min(20, amount_rank_pct / 5)

        # 第1重：市场情绪（全局，所有股票共享）
        result.layer_pass[0] = True  # 市场情绪周期作为环境层，不单独过滤个股
        result.reasons.append(f"市场周期: {self._market_sentiment.cycle}")

        # 第2-5重：技术过滤
        tech_layers, tech_info = self._filter_technical(code, kline, rps20)
        for i, passed in enumerate(tech_layers):
            result.layer_pass[i + 1] = passed
        result.ma5 = tech_info.get('ma5', 0)
        result.ma10 = tech_info.get('ma10', 0)
        result.ma20 = tech_info.get('ma20', 0)
        result.ma60 = tech_info.get('ma60', 0)
        result.rps20 = rps20
        result.chip_peak_price = tech_info.get('chip_peak_price', 0)
        result.chip_peak_type = tech_info.get('chip_peak_type', '')
        result.chip_position = tech_info.get('chip_position', '')

        # 第6-8重：资金验证
        fund_layers, fund_info = self._filter_fund(code, kline, amount_rank_pct)
        for i, passed in enumerate(fund_layers):
            result.layer_pass[i + 5] = passed
        result.volume_ratio = fund_info.get('volume_ratio', 1.0)
        result.fund_score_100 = fund_info.get('fund_score_100', 0)

        # 第9重：分时执行标记（标记层，所有通过前8重的股票都标记）
        intraday = self._mark_intraday_execution(code, kline, tech_info)
        result.intraday_signal = intraday['intraday_signal']
        result.support_price = intraday['support_price']
        result.pressure_price = intraday['pressure_price']
        # 第9重标记为通过（有信号即通过）
        result.layer_pass[8] = bool(result.intraday_signal)

        # 统计通过数量
        result.pass_count = sum(result.layer_pass)

        # 首板回调模型分析
        try:
            result.first_board = self.fb_model.analyze(kline)
        except Exception as e:
            print(f"[NINE FILTER] 首板回调分析异常 {code}: {e}", flush=True)

        # 综合评分
        try:
            fund_params = {
                'volume_ratio': result.volume_ratio,
                'big_order_net': fund_info.get('big_order_net_est', 0),
                'amount': result.amount,
                'turnover_rate': result.turnover_rate,
                'amount_rank_pct': amount_rank_pct,
            }
            trend_params = {
                'ma_alignment': result.layer_pass[1],
                'break_ma60': result.layer_pass[2],
                'rps20': rps20,
                'chip_peak_score': tech_info.get('chip_score', 50),
                'ma5_above_ma10': result.ma5 > result.ma10 if result.ma10 > 0 else False,
                'price_above_ma20': result.price > result.ma20 if result.ma20 > 0 else False,
            }
            sentiment_params = {
                'market_cycle': self._market_sentiment.cycle,
                'limit_up_gene': result.first_board.matched or any(
                    b.get('pct_chg', 0) >= LIMIT_UP_THRESHOLD for b in kline[-10:]
                ),
                'consecutive_board_height': 0,
                'sentiment_temperature': self._market_sentiment.sentiment_temperature,
                'stock_in_hot_sector': False,
            }
            result.score = self.score_engine.calculate(
                fund_params=fund_params,
                trend_params=trend_params,
                sentiment_params=sentiment_params,
                nine_pass_count=result.pass_count,
            )
        except Exception as e:
            print(f"[NINE FILTER] 评分异常 {code}: {e}", flush=True)

        return result

    # ============================================================
    # 全市场扫描
    # ============================================================
    def scan(self, progress_callback=None, min_pass_count: int = 5,
             max_stocks: Optional[int] = None, scan_mode: str = "标准扫描") -> List[NineFilterStockResult]:
        """
        全市场九重过滤扫描

        Args:
            progress_callback: 进度回调函数(processed, total, current_code)
            min_pass_count: 最少通过九重数量（默认5重）
            max_stocks: 最大扫描股票数（None=全部）
            scan_mode: 扫描模式

        Returns:
            候选股票列表（按综合评分降序）
        """
        if self._scan_running:
            print("[NINE FILTER] 扫描已在运行中", flush=True)
            return []

        self._scan_running = True
        start_time = time.time()
        self._funnel_stats = {'扫描模式': scan_mode}

        try:
            # 1. 获取股票列表
            if self.tdx_engine and self.tdx_engine.is_available():
                codes = self.tdx_engine.get_all_main_board_codes()
            else:
                print("[NINE FILTER] 通达信不可用，尝试股票列表提供者", flush=True)
                codes = self._get_stock_codes_fallback()

            if max_stocks:
                codes = codes[:max_stocks]

            total = len(codes)
            self._funnel_stats['total_market'] = total
            print(f"[NINE FILTER] 开始扫描: {total}只股票, 模式={scan_mode}", flush=True)

            # 2. 批量读取K线（多线程）
            all_kline = self._batch_load_kline(codes, progress_callback, total)
            self._funnel_stats['kline_loaded'] = len(all_kline)
            print(f"[NINE FILTER] K线加载完成: {len(all_kline)}/{total}", flush=True)

            # 3. 计算市场情绪（第1重）
            sentiment = self.calculate_market_sentiment(all_kline)
            self._funnel_stats['market_cycle'] = sentiment.cycle
            self._funnel_stats['limit_up_count'] = sentiment.limit_up_count
            self._funnel_stats['limit_down_count'] = sentiment.limit_down_count

            # 4. 计算RPS20和成交额排名
            self._rps20_map = self._calculate_rps20(all_kline)
            self._amount_rank_map = self._calculate_amount_rank(all_kline)

            # 5. 逐股九重过滤
            results = []
            layer_counts = [0] * 9
            processed = 0

            for code, kline in all_kline.items():
                processed += 1
                if progress_callback and (processed % 20 == 0 or processed == len(all_kline)):
                    progress_callback(processed, len(all_kline), code)

                rps20 = self._rps20_map.get(code, 50.0)
                amount_rank = self._amount_rank_map.get(code, 50.0)
                name = self._get_stock_name(code)

                stock_result = self.analyze_stock(code, kline, rps20, amount_rank, name)

                # 统计每层通过数
                for i in range(9):
                    if stock_result.layer_pass[i]:
                        layer_counts[i] += 1

                # 筛选：通过>=min_pass_count重
                if stock_result.pass_count >= min_pass_count:
                    results.append(stock_result)

            # 6. 漏斗统计
            for i, name in enumerate(LAYER_NAMES):
                self._funnel_stats[f'layer{i+1}_{name}'] = layer_counts[i]
            self._funnel_stats[f'pass_{min_pass_count}+'] = len(results)

            # 7. 按综合评分降序
            results.sort(key=lambda r: r.score.total, reverse=True)

            elapsed = time.time() - start_time
            self._funnel_stats['time_total'] = round(elapsed, 1)
            print(f"[NINE FILTER] 扫描完成: 候选{len(results)}只, 耗时{elapsed:.1f}s", flush=True)

            # 8. 保存缓存
            self._save_cache(results)

            return results

        except Exception as e:
            print(f"[NINE FILTER] 扫描异常: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return []
        finally:
            self._scan_running = False

    def _batch_load_kline(self, codes: List[str],
                            progress_callback=None, total: int = 0) -> Dict[str, List[Dict]]:
        """批量加载K线数据"""
        all_kline = {}
        if not self.tdx_engine or not self.tdx_engine.is_available():
            return all_kline

        # 使用引擎的批量读取
        kline_dict = self.tdx_engine.get_kline_batch(codes, days=120, max_workers=8)
        all_kline.update(kline_dict)

        return all_kline

    def _get_stock_codes_fallback(self) -> List[str]:
        """备用股票列表获取"""
        try:
            from data.stock_list_provider import get_stock_list
            stock_list = get_stock_list()
            return [s.get('code', '') for s in stock_list if s.get('code')]
        except Exception:
            return []

    def _get_stock_name(self, code: str) -> str:
        """获取股票名称（从缓存）"""
        try:
            cache_path = os.path.join(CACHE_DIR, "stock_names.json")
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('names', {}).get(code, '')
        except Exception:
            pass
        return ''

    # ============================================================
    # 缓存管理
    # ============================================================
    def _save_cache(self, results: List[NineFilterStockResult]):
        """保存扫描结果缓存（30分钟TTL）"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            cache_data = {
                'save_time': time.time(),
                'save_time_str': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'ttl': CACHE_TTL,
                'result_count': len(results),
                'funnel_stats': self._funnel_stats,
                'market_sentiment': self._market_sentiment.to_dict(),
                'results': [r.to_dict() for r in results],
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
            print(f"[NINE FILTER] 缓存已保存: {len(results)}只 -> {CACHE_FILE}", flush=True)
        except Exception as e:
            print(f"[NINE FILTER] 缓存保存失败: {e}", flush=True)

    def load_cached_scan(self) -> Optional[List[NineFilterStockResult]]:
        """加载缓存的扫描结果（30分钟内有效）"""
        try:
            if not os.path.exists(CACHE_FILE):
                return None
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            save_time = cache_data.get('save_time', 0)
            if time.time() - save_time > CACHE_TTL:
                print("[NINE FILTER] 缓存已过期（>30分钟）", flush=True)
                return None

            # 恢复市场情绪
            sent_data = cache_data.get('market_sentiment', {})
            self._market_sentiment = MarketSentiment(
                cycle=sent_data.get('cycle', CYCLE_CHAOS),
                limit_up_count=sent_data.get('limit_up_count', 0),
                limit_down_count=sent_data.get('limit_down_count', 0),
                sentiment_temperature=sent_data.get('sentiment_temperature', 50),
                calc_time=sent_data.get('calc_time', ''),
            )
            self._funnel_stats = cache_data.get('funnel_stats', {})

            # 恢复结果
            results = []
            for r_dict in cache_data.get('results', []):
                r = NineFilterStockResult(
                    code=r_dict.get('code', ''),
                    name=r_dict.get('name', ''),
                    price=r_dict.get('price', 0),
                    change_pct=r_dict.get('change_pct', 0),
                    amount=r_dict.get('amount', 0),
                    volume=r_dict.get('volume', 0),
                    turnover_rate=r_dict.get('turnover_rate', 0),
                    volume_ratio=r_dict.get('volume_ratio', 1.0),
                    rps20=r_dict.get('rps20', 50),
                    pass_count=r_dict.get('pass_count', 0),
                    layer_pass=r_dict.get('layer_pass', [False] * 9),
                    fund_score_100=r_dict.get('fund_score_100', 0),
                    intraday_signal=r_dict.get('intraday_signal', ''),
                    support_price=r_dict.get('support_price', 0),
                    pressure_price=r_dict.get('pressure_price', 0),
                    scan_time=r_dict.get('scan_time', ''),
                )
                score_dict = r_dict.get('score', {})
                r.score = NineScoreResult(
                    total=score_dict.get('total', 0),
                    grade=score_dict.get('grade', 'C'),
                    fund_score=score_dict.get('fund_score', 0),
                    trend_score=score_dict.get('trend_score', 0),
                    sentiment_score=score_dict.get('sentiment_score', 0),
                    nine_pass_count=score_dict.get('nine_pass_count', 0),
                    reasons=score_dict.get('reasons', []),
                )
                results.append(r)

            print(f"[NINE FILTER] 缓存加载成功: {len(results)}只", flush=True)
            return results

        except Exception as e:
            print(f"[NINE FILTER] 缓存加载失败: {e}", flush=True)
            return None

    def get_cache_info(self) -> Dict:
        """获取缓存状态信息"""
        try:
            if not os.path.exists(CACHE_FILE):
                return {'exists': False, 'status': '无缓存'}
            mtime = os.path.getmtime(CACHE_FILE)
            age = time.time() - mtime
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = data.get('result_count', 0)
            scan_time = data.get('save_time_str', '')
            if age <= CACHE_TTL:
                status = '有效'
            else:
                status = '过期'
            return {
                'exists': True,
                'status': status,
                'result_count': count,
                'scan_time': scan_time,
                'age_seconds': round(age, 0),
                'ttl': CACHE_TTL,
            }
        except Exception as e:
            return {'exists': False, 'status': f'错误: {e}'}

    def clear_scan_cache(self):
        """清除扫描缓存"""
        try:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
                print("[NINE FILTER] 缓存已清除", flush=True)
        except Exception as e:
            print(f"[NINE FILTER] 缓存清除失败: {e}", flush=True)

    # ============================================================
    # 状态查询
    # ============================================================
    def get_funnel_stats(self) -> Dict:
        """获取漏斗统计"""
        return dict(self._funnel_stats)

    def get_market_sentiment(self) -> MarketSentiment:
        """获取市场情绪"""
        return self._market_sentiment

    def is_scanning(self) -> bool:
        return self._scan_running

    def get_kline_data(self, code: str, days: int = 120) -> Optional[Dict]:
        """获取K线数据（供UI K线图使用）

        修复说明：
        - 强制 use_cache=False，每次重新读取通达信.day文件，不使用扫描时的旧缓存
        - 增加腾讯实时行情兜底，补充当日最新K线
        - 打印调试日志：K线数量、首尾日期
        """
        if not (self.tdx_engine and self.tdx_engine.is_available()):
            return None

        # 1. 强制从通达信本地文件重新读取（use_cache=False）
        kline = self.tdx_engine.get_kline(code, days=days, use_cache=False)

        if not kline:
            print(f"[NINE KLINE] {code}: 通达信无K线数据", flush=True)
            return None

        first_date = kline[0].get('date', '')
        last_date = kline[-1].get('date', '')
        last_close = kline[-1].get('close', 0)
        print(f"[NINE KLINE] {code}: 通达信K线{len(kline)}根, "
              f"{first_date}~{last_date}, 最新价{last_close:.2f}", flush=True)

        # 2. 实时行情兜底：检查是否需要补充当日最新K线
        kline = self._append_realtime_kline(code, kline)

        # 3. 转换为ECharts格式
        result = {
            'dates': [b['date'] for b in kline],
            'open': [b['open'] for b in kline],
            'high': [b['high'] for b in kline],
            'low': [b['low'] for b in kline],
            'close': [b['close'] for b in kline],
            'volume': [b['volume'] for b in kline],
        }

        if len(kline) > 0:
            print(f"[NINE KLINE] {code}: 最终K线{len(kline)}根, "
                  f"最新日期{kline[-1].get('date', '')}, 最新价{kline[-1].get('close', 0):.2f}", flush=True)

        return result

    def _append_realtime_kline(self, code: str, kline: List[Dict]) -> List[Dict]:
        """从腾讯实时行情接口补充当日最新K线（如果通达信数据不是最新）

        Args:
            code: 股票代码
            kline: 通达信K线列表

        Returns:
            补充后的K线列表
        """
        try:
            from datetime import datetime
            today_str = datetime.now().strftime('%Y%m%d')
            last_date = kline[-1].get('date', '') if kline else ''

            # 如果通达信数据已经包含今天，不需要补充
            if last_date >= today_str:
                return kline

            # 从腾讯接口获取实时行情
            import requests
            if code.startswith('6'):
                tencent_code = f'sh{code}'
            else:
                tencent_code = f'sz{code}'

            url = f'https://qt.gtimg.cn/q={tencent_code}'
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return kline

            text = resp.content.decode('gbk', errors='ignore')
            if '=' not in text or '"' not in text:
                return kline

            data_str = text.split('"')[1]
            parts = data_str.split('~')
            if len(parts) < 50:
                return kline

            # 解析实时数据
            name = parts[1] if len(parts) > 1 else code
            price = float(parts[3]) if parts[3] else 0
            pre_close = float(parts[4]) if parts[4] else 0
            open_price = float(parts[5]) if parts[5] else 0
            volume = float(parts[6]) if parts[6] else 0  # 手
            high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
            low = float(parts[34]) if len(parts) > 34 and parts[34] else 0
            amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0  # 万

            if price <= 0 or open_price <= 0:
                return kline

            # 构造当日K线
            today_kline = {
                'date': today_str,
                'trade_date': today_str,
                'open': open_price,
                'high': high if high > 0 else max(price, open_price),
                'low': low if low > 0 else min(price, open_price),
                'close': price,
                'volume': volume * 100,  # 手转股
                'amount': amount * 10000,  # 万转元
            }

            # 如果最后一根已经是今天，替换；否则追加
            if last_date == today_str:
                kline[-1] = today_kline
            else:
                kline.append(today_kline)

            print(f"[NINE KLINE] {code} {name}: 已补充腾讯实时行情 {today_str} "
                  f"开{open_price:.2f} 高{today_kline['high']:.2f} "
                  f"低{today_kline['low']:.2f} 收{price:.2f}", flush=True)

        except Exception as e:
            print(f"[NINE KLINE] {code}: 实时行情补充失败: {e}", flush=True)

        return kline


# ============================================================
# 便捷函数
# ============================================================
def get_nine_filter_strategy() -> NineFilterStrategy:
    """获取九重过滤策略单例"""
    return NineFilterStrategy.instance()
