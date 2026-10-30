# -*- coding: utf-8 -*-
"""
模型一：涨停回调模型（强势股低吸模型）V1.1

V1.1放宽：
- 原必须涨停后回调 → 允许近期涨幅超10% 或 出现强势大阳线
- 不要求完整结构，允许识别形成中阶段
- 模型独立评分0-100
- 增加支撑位/压力位字段
"""
import numpy as np
from typing import List, Dict, Optional
from strategy.base import (
    KlineBar, ModelMatch, TechnicalIndicators, VolumeAnalyzer,
    MODEL_LIMIT_PULLBACK, STAGE_LAUNCH, STAGE_PULLBACK, STAGE_SHRINK,
    STAGE_SUPPORT, STAGE_RELAUNCH, LIMIT_UP_THRESHOLD, BIG_YANG_THRESHOLD,
    STRONG_RISE_THRESHOLD,
)


class LimitUpPullbackModel:
    """涨停回调模型（V1.1放宽版）"""

    def __init__(self):
        self.name = MODEL_LIMIT_PULLBACK

    def analyze(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, volumes: np.ndarray) -> ModelMatch:
        result = ModelMatch(model_name=self.name, matched=False, stage="")
        if len(bars) < 30:
            result.stage = "数据不足"
            result.score = 0
            return result

        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        last_idx = len(bars) - 1
        last_bar = bars[-1]

        # 1. 寻找近期强势启动点（V1.1放宽：涨停/大阳/10日涨幅>10%）
        launch_idx = self._find_launch_point(bars, closes, lookback=30)
        if launch_idx is None:
            result.stage = "无强势启动"
            result.score = 10  # V1.1：即使不匹配也给基础分
            return result

        launch_bar = bars[launch_idx]
        launch_price = launch_bar.close

        # 2. 启动后状态判断
        if last_idx <= launch_idx:
            result.stage = STAGE_LAUNCH
            result.matched = True
            result.score = self._calc_score(bars, closes, volumes, launch_idx, ma5, ma10, result.stage)
            result.support = self._calc_support(last_bar, ma5[last_idx], ma10[last_idx], launch_price, lows, launch_idx)
            result.pressure = self._calc_pressure(highs, launch_idx, last_idx)
            result.tags = ["涨停回调", "缩量低吸", "强势洗盘"]
            return result

        # 调整区间
        adjust_closes = closes[launch_idx:]
        adjust_highs = highs[launch_idx:]
        adjust_lows = lows[launch_idx:]
        adjust_volumes = volumes[launch_idx:]

        peak_after = np.max(adjust_highs)
        current_price = closes[last_idx]
        drawdown = (peak_after - current_price) / peak_after * 100 if peak_after > 0 else 0

        is_shrinking = VolumeAnalyzer.is_volume_shrinking(volumes, period=5)
        vol_ratio = VolumeAnalyzer.volume_ratio(volumes, period=5)
        has_volume_drop = self._check_volume_drop(bars, launch_idx)

        support_info = self._check_support(last_bar, ma5[last_idx], ma10[last_idx], launch_price, adjust_lows)

        # 3. 阶段判断（V1.1：不要求完整结构，形成中也匹配）
        if drawdown < 2:
            stage = STAGE_LAUNCH
        elif is_shrinking and drawdown < 18:
            stage = STAGE_SHRINK
        elif drawdown >= 18:
            stage = STAGE_PULLBACK
        else:
            stage = STAGE_PULLBACK

        # V1.1：只要有启动点+有调整迹象就匹配（不要求缩量+支撑同时满足）
        matched = launch_idx is not None and drawdown > 0.5

        # 4. 买点信号
        buy_signals = []
        if is_shrinking and not np.isnan(ma5[last_idx]):
            if last_bar.close > ma5[last_idx] and bars[-2].close <= ma5[last_idx - 1]:
                buy_signals.append("重新站上5日线")
            if last_bar.low <= ma5[last_idx] * 1.01 and last_bar.close > ma5[last_idx]:
                buy_signals.append("5日线回踩低吸")
        if VolumeAnalyzer.is_volume_expanding(volumes[-3:], period=3) if len(volumes) >= 6 else False:
            if last_bar.pct_chg > 0:
                buy_signals.append("成交量重新放大")

        # 5. 风险
        risks = []
        if has_volume_drop:
            risks.append("调整中出现放量下跌")
        if current_price < launch_price * 0.95:
            risks.append("跌破启动位置")
        if last_bar.pct_chg < -3 and last_bar.volume > np.mean(volumes[-10:]) * 1.5:
            risks.append("当日放量下跌")

        # 6. 模型独立评分（V1.1新增）
        score = self._calc_score(bars, closes, volumes, launch_idx, ma5, ma10, stage,
                                  is_shrinking, support_info, drawdown)

        result.matched = matched
        result.stage = stage
        result.score = score
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["涨停回调", "缩量低吸", "强势洗盘"]
        result.support = self._calc_support(last_bar, ma5[last_idx], ma10[last_idx], launch_price, lows, launch_idx)
        result.pressure = self._calc_pressure(highs, launch_idx, last_idx)
        result.detail = {
            "launch_date": launch_bar.date,
            "launch_price": round(launch_price, 2),
            "launch_pct": round(launch_bar.pct_chg, 2),
            "drawdown_pct": round(drawdown, 2),
            "volume_ratio": round(vol_ratio, 2),
            "is_shrinking": is_shrinking,
            "support_info": support_info,
            "current_price": round(current_price, 2),
        }
        return result

    def _find_launch_point(self, bars, closes, lookback=30):
        """V1.1放宽：涨停/大阳/10日涨幅>10% 都算启动"""
        start = max(0, len(bars) - lookback)
        # 优先找涨停
        for i in range(len(bars) - 1, start - 1, -1):
            if bars[i].pct_chg >= LIMIT_UP_THRESHOLD:
                if i == 0 or bars[i - 1].pct_chg < 3:
                    return i
        # 其次找大阳线
        for i in range(len(bars) - 1, start - 1, -1):
            if bars[i].pct_chg >= BIG_YANG_THRESHOLD:
                if i == 0 or bars[i - 1].pct_chg < 3:
                    return i
        # V1.1新增：10日涨幅>10%
        last_idx = len(bars) - 1
        if last_idx >= 10 and closes[last_idx - 10] > 0:
            rise = (closes[last_idx] - closes[last_idx - 10]) / closes[last_idx - 10] * 100
            if rise >= STRONG_RISE_THRESHOLD:
                return last_idx - 10  # 启动点为10日前
        return None

    def _check_volume_drop(self, bars, launch_idx):
        count = 0
        for i in range(launch_idx + 1, len(bars)):
            avg_vol = np.mean([b.volume for b in bars[max(0, i - 5):i]]) if i > 0 else bars[i].volume
            if bars[i].pct_chg < -2 and bars[i].volume > avg_vol * 1.3:
                count += 1
                if count >= 2:
                    return True
            else:
                count = 0
        return False

    def _check_support(self, bar, ma5_val, ma10_val, launch_price, adjust_lows):
        price = bar.close
        info = {"near_ma5": False, "near_ma10": False, "near_launch": False,
                "near_box_bottom": False, "near_support": False}
        tol = 0.025  # V1.1放宽2%→2.5%
        if not np.isnan(ma5_val) and ma5_val > 0 and abs(price - ma5_val) / ma5_val < tol:
            info["near_ma5"] = True
        if not np.isnan(ma10_val) and ma10_val > 0 and abs(price - ma10_val) / ma10_val < tol:
            info["near_ma10"] = True
        if launch_price > 0 and abs(price - launch_price) / launch_price < tol:
            info["near_launch"] = True
        if len(adjust_lows) > 3:
            box_bottom = np.min(adjust_lows[:-1]) if len(adjust_lows) > 1 else adjust_lows[0]
            if box_bottom > 0 and abs(price - box_bottom) / box_bottom < tol:
                info["near_box_bottom"] = True
        info["near_support"] = any([info["near_ma5"], info["near_ma10"], info["near_launch"], info["near_box_bottom"]])
        return info

    def _calc_support(self, bar, ma5, ma10, launch_price, lows, launch_idx):
        """计算支撑位（取最近的有效支撑）"""
        candidates = []
        if not np.isnan(ma5) and ma5 > 0 and bar.close >= ma5 * 0.95:
            candidates.append(ma5)
        if not np.isnan(ma10) and ma10 > 0 and bar.close >= ma10 * 0.95:
            candidates.append(ma10)
        if launch_price > 0 and bar.close >= launch_price * 0.95:
            candidates.append(launch_price)
        if len(lows) > launch_idx + 3:
            box_bottom = np.min(lows[launch_idx + 1:-1]) if len(lows) > launch_idx + 2 else lows[launch_idx]
            if box_bottom > 0:
                candidates.append(box_bottom)
        return round(min(candidates), 2) if candidates else round(bar.low, 2)

    def _calc_pressure(self, highs, launch_idx, last_idx):
        """计算压力位（近期高点）"""
        if last_idx > launch_idx:
            return round(np.max(highs[launch_idx:]), 2)
        return round(highs[-1] * 1.03, 2)

    def _calc_score(self, bars, closes, volumes, launch_idx, ma5, ma10, stage,
                     is_shrinking=False, support_info=None, drawdown=0):
        """模型独立评分0-100"""
        score = 30.0  # V1.1基础分
        # 启动强度
        launch_pct = abs(bars[launch_idx].pct_chg)
        score += min(launch_pct * 1.5, 20)
        # 缩量
        if is_shrinking:
            score += 15
        # 支撑
        if support_info and support_info.get('near_support'):
            score += 15
        # 阶段加分
        if stage == STAGE_SHRINK:
            score += 10
        elif stage == STAGE_RELAUNCH:
            score += 12
        elif stage == STAGE_LAUNCH:
            score += 5
        # 回撤合理（5-15%最佳）
        if 5 <= drawdown <= 15:
            score += 10
        elif 2 <= drawdown < 5 or 15 < drawdown <= 20:
            score += 5
        return min(round(score, 1), 100)
