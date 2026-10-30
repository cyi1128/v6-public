# -*- coding: utf-8 -*-
"""
九重共振选股中心 - 首板回调模型 V1.0

模型逻辑（全部基于真实日K线数据）：
  1. 10日内出现涨停（涨幅>=9.5%）
  2. 涨停后缩量回调（成交量递减）
  3. 10日线企稳（价格回踩MA10不破，或跌破后快速收回）
  4. 重新站上5日线（收盘价>MA5）
  5. 两阳缩量确认（最近两根阳线，成交量逐步缩小）

输出：买入信号 + 信号强度 + 关键价位
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from strategy.base import (
    TechnicalIndicators, VolumeAnalyzer, KlineDataParser,
    KlineBar, LIMIT_UP_THRESHOLD,
)


@dataclass
class FirstBoardPullbackResult:
    """首板回调模型结果"""
    matched: bool = False
    signal_strength: float = 0.0  # 0-100
    signal_type: str = ""          # 买入信号类型
    limit_up_date: str = ""        # 涨停日期
    limit_up_price: float = 0.0    # 涨停价
    pullback_days: int = 0         # 回调天数
    current_price: float = 0.0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    support_price: float = 0.0     # 支撑位（MA10或涨停启动位）
    pressure_price: float = 0.0    # 压力位（涨停高点）
    volume_shrink_ratio: float = 0.0  # 缩量比例（回调期均量/涨停日均量）
    two_yang_confirm: bool = False    # 两阳缩量确认
    reasons: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "matched": bool(self.matched),
            "signal_strength": round(float(self.signal_strength), 1),
            "signal_type": self.signal_type,
            "limit_up_date": self.limit_up_date,
            "limit_up_price": round(float(self.limit_up_price), 2),
            "pullback_days": int(self.pullback_days),
            "current_price": round(float(self.current_price), 2),
            "ma5": round(float(self.ma5), 2),
            "ma10": round(float(self.ma10), 2),
            "ma20": round(float(self.ma20), 2),
            "support_price": round(float(self.support_price), 2),
            "pressure_price": round(float(self.pressure_price), 2),
            "volume_shrink_ratio": round(float(self.volume_shrink_ratio), 3),
            "two_yang_confirm": bool(self.two_yang_confirm),
            "reasons": list(self.reasons),
            "risks": list(self.risks),
        }


class FirstBoardPullbackModel:
    """首板回调模型"""

    def __init__(self, lookback_days: int = 10,
                 limit_up_threshold: float = LIMIT_UP_THRESHOLD):
        """
        Args:
            lookback_days: 涨停回看天数（默认10日）
            limit_up_threshold: 涨停阈值（默认9.5%）
        """
        self.lookback_days = lookback_days
        self.limit_up_threshold = limit_up_threshold

    def analyze(self, kline_data) -> FirstBoardPullbackResult:
        """
        分析首板回调信号

        Args:
            kline_data: K线数据（List[Dict] 或 Dict格式）

        Returns:
            FirstBoardPullbackResult
        """
        result = FirstBoardPullbackResult()

        # 解析K线数据
        try:
            bars, opens, highs, lows, closes, volumes = KlineDataParser.parse(kline_data)
        except Exception as e:
            result.risks.append(f"K线数据解析失败: {e}")
            return result

        if len(bars) < 20:
            result.risks.append(f"数据不足({len(bars)}根<20根)")
            return result

        last_idx = len(bars) - 1
        result.current_price = closes[last_idx]

        # 计算均线
        ma5_arr = TechnicalIndicators.ma(closes, 5)
        ma10_arr = TechnicalIndicators.ma(closes, 10)
        ma20_arr = TechnicalIndicators.ma(closes, 20)

        if np.isnan(ma5_arr[last_idx]) or np.isnan(ma10_arr[last_idx]):
            result.risks.append("均线数据不足")
            return result

        result.ma5 = ma5_arr[last_idx]
        result.ma10 = ma10_arr[last_idx]
        result.ma20 = ma20_arr[last_idx] if not np.isnan(ma20_arr[last_idx]) else 0

        # ============================================================
        # 条件1：10日内出现涨停
        # ============================================================
        limit_up_idx = self._find_recent_limit_up(bars, last_idx)
        if limit_up_idx is None:
            result.risks.append("近10日无涨停")
            return result

        result.limit_up_date = bars[limit_up_idx].date
        result.limit_up_price = closes[limit_up_idx]
        result.pressure_price = highs[limit_up_idx]
        result.reasons.append(f"涨停日: {bars[limit_up_idx].date} 涨幅{bars[limit_up_idx].pct_chg:.1f}%")

        # ============================================================
        # 条件2：涨停后缩量回调
        # ============================================================
        pullback_start = limit_up_idx + 1
        if pullback_start > last_idx:
            result.risks.append("涨停后无回调数据")
            return result

        # 找到回调最低点（涨停后到当前）
        pullback_segment = list(range(pullback_start, last_idx + 1))
        if not pullback_segment:
            result.risks.append("回调段为空")
            return result

        min_idx_in_pullback = min(pullback_segment, key=lambda i: lows[i])
        result.pullback_days = last_idx - limit_up_idx

        # 计算缩量比例（回调期均量 / 涨停日及前2日均量）
        limit_up_vol_avg = np.mean(volumes[max(0, limit_up_idx - 2):limit_up_idx + 1])
        pullback_vol_avg = np.mean(volumes[pullback_start:last_idx + 1])
        if limit_up_vol_avg > 0:
            result.volume_shrink_ratio = pullback_vol_avg / limit_up_vol_avg
        else:
            result.volume_shrink_ratio = 1.0

        is_shrinking = result.volume_shrink_ratio < 0.8
        if is_shrinking:
            result.reasons.append(f"缩量回调: 均量比{result.volume_shrink_ratio:.2f}")
        else:
            result.risks.append(f"回调未明显缩量(均量比{result.volume_shrink_ratio:.2f})")

        # ============================================================
        # 条件3：10日线企稳
        # ============================================================
        ma10_stable = self._check_ma10_support(bars, closes, ma10_arr,
                                                  min_idx_in_pullback, last_idx)
        if ma10_stable:
            result.reasons.append("MA10企稳")
            result.support_price = ma10_arr[last_idx]
        else:
            # 检查是否在涨停启动位获得支撑
            launch_support = closes[max(0, limit_up_idx - 1)]
            if lows[min_idx_in_pullback] >= launch_support * 0.97:
                result.reasons.append(f"涨停启动位企稳({launch_support:.2f})")
                result.support_price = launch_support
                ma10_stable = True
            else:
                result.risks.append("未在MA10或启动位企稳")

        # ============================================================
        # 条件4：重新站上5日线
        # ============================================================
        above_ma5 = closes[last_idx] > ma5_arr[last_idx]
        # 确认是重新站上（前一日在MA5下方或刚突破）
        if last_idx >= 1 and closes[last_idx - 1] <= ma5_arr[last_idx - 1] and above_ma5:
            result.reasons.append("今日重新站上MA5")
        elif above_ma5:
            result.reasons.append("价格在MA5之上")
        else:
            result.risks.append("尚未站上MA5")

        # ============================================================
        # 条件5：两阳缩量确认
        # ============================================================
        result.two_yang_confirm = self._check_two_yang_shrink(bars, volumes, last_idx)
        if result.two_yang_confirm:
            result.reasons.append("两阳缩量确认")

        # ============================================================
        # 综合判定
        # ============================================================
        conditions_met = sum([
            True,  # 条件1已满足（涨停）
            is_shrinking,
            ma10_stable,
            above_ma5,
            result.two_yang_confirm,
        ])

        # 信号强度计算
        strength = 0.0
        strength += 20.0  # 有涨停基因基础分
        if is_shrinking:
            strength += 20.0 * (1 - min(result.volume_shrink_ratio, 1.0))
        if ma10_stable:
            strength += 20.0
        if above_ma5:
            strength += 20.0
        if result.two_yang_confirm:
            strength += 20.0

        # 回调幅度适中加分（10%-25%最佳）
        if result.limit_up_price > 0:
            pullback_pct = (result.limit_up_price - lows[min_idx_in_pullback]) / result.limit_up_price * 100
            if 8 <= pullback_pct <= 25:
                strength += 5.0
                result.reasons.append(f"回调幅度适中({pullback_pct:.1f}%)")

        result.signal_strength = min(strength, 100.0)

        # 判定匹配
        # 必须满足：涨停 + 缩量 + (MA10企稳或启动位企稳) + 站上MA5
        core_conditions = is_shrinking and ma10_stable and above_ma5
        result.matched = core_conditions

        if result.matched:
            if result.two_yang_confirm:
                result.signal_type = "首板回调-两阳确认买入"
            else:
                result.signal_type = "首板回调-站上MA5买入"
        elif conditions_met >= 3:
            result.signal_type = "首板回调-观察中"

        return result

    # ============================================================
    # 辅助方法
    # ============================================================
    def _find_recent_limit_up(self, bars: List[KlineBar],
                                last_idx: int) -> Optional[int]:
        """查找最近lookback_days内的涨停日索引（取最近的一个）"""
        start = max(0, last_idx - self.lookback_days + 1)
        for i in range(last_idx, start - 1, -1):
            if bars[i].pct_chg >= self.limit_up_threshold:
                # 确认是首板（前一日未涨停）
                if i == 0 or bars[i - 1].pct_chg < self.limit_up_threshold:
                    return i
        return None

    @staticmethod
    def _check_ma10_support(bars: List[KlineBar], closes: np.ndarray,
                              ma10_arr: np.ndarray, min_idx: int,
                              last_idx: int) -> bool:
        """检查10日线企稳：回调最低点未有效跌破MA10，或跌破后快速收回"""
        if np.isnan(ma10_arr[min_idx]):
            return False

        ma10_at_min = ma10_arr[min_idx]
        low_at_min = bars[min_idx].low

        # 情况1：最低点未跌破MA10（或跌破不超过2%）
        if low_at_min >= ma10_at_min * 0.98:
            return True

        # 情况2：跌破后3日内收回MA10
        recover_idx = None
        for i in range(min_idx + 1, min(last_idx + 1, min_idx + 4)):
            if not np.isnan(ma10_arr[i]) and closes[i] > ma10_arr[i]:
                recover_idx = i
                break
        if recover_idx is not None:
            return True

        return False

    @staticmethod
    def _check_two_yang_shrink(bars: List[KlineBar], volumes: np.ndarray,
                                 last_idx: int) -> bool:
        """检查两阳缩量确认：最近两根阳线，成交量逐步缩小"""
        if last_idx < 2:
            return False

        # 最近两根K线
        bar1 = bars[last_idx - 1]  # 倒数第二根
        bar2 = bars[last_idx]       # 最后一根

        # 两根都是阳线（收盘价>开盘价）
        is_yang1 = bar1.close > bar1.open
        is_yang2 = bar2.close > bar2.open

        if not (is_yang1 and is_yang2):
            return False

        # 成交量逐步缩小
        vol_shrink = volumes[last_idx] < volumes[last_idx - 1]

        return vol_shrink


# ============================================================
# 便捷函数
# ============================================================
def analyze_first_board_pullback(kline_data) -> FirstBoardPullbackResult:
    """便捷函数：分析首板回调信号"""
    model = FirstBoardPullbackModel()
    return model.analyze(kline_data)
