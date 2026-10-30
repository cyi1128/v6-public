# -*- coding: utf-8 -*-
"""
模型三：极限缩量量价突破模型（主力启动模型）V1.1

V1.1放宽：
- 原必须五阶段全部完成 → 允许筑底/启动/突破/回踩各阶段，增加当前阶段字段
- 不要求完整结构，识别形成中阶段也匹配
- 模型独立评分0-100
- 增加支撑位/压力位字段
"""
import numpy as np
from typing import List, Dict
from strategy.base import (
    KlineBar, ModelMatch, TechnicalIndicators, VolumeAnalyzer,
    MODEL_VOLUME_BREAKOUT, STAGE_BOTTOM, STAGE_VOL_PRICE_UP, STAGE_BREAKOUT,
    STAGE_CONFIRM,
)


class VolumeBreakoutModel:
    """极限缩量量价突破模型（V1.1放宽版）"""

    def __init__(self):
        self.name = MODEL_VOLUME_BREAKOUT

    def analyze(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, volumes: np.ndarray) -> ModelMatch:
        result = ModelMatch(model_name=self.name, matched=False, stage="")
        if len(bars) < 30:
            result.stage = "数据不足"
            result.score = 0
            return result

        last_idx = len(bars) - 1
        last_bar = bars[-1]
        current_price = closes[last_idx]

        # 1. 寻找极限缩量筑底（V1.1放宽条件）
        shrink_idx = VolumeAnalyzer.find_extreme_shrink(volumes, lookback=60)

        # V1.1：如果没找到极限缩量，用近20日最低量代替
        if shrink_idx is None and len(volumes) >= 20:
            recent_min = np.argmin(volumes[-20:]) + len(volumes) - 20
            local_avg = np.mean(volumes[max(0, recent_min - 5):recent_min + 5])
            if local_avg > 0 and volumes[recent_min] < local_avg * 0.7:
                shrink_idx = recent_min

        if shrink_idx is None:
            # V1.1：即使没有极限缩量，有量价转强也匹配
            if VolumeAnalyzer.volume_ratio(volumes, period=5) > 1.1 and last_bar.pct_chg > 0:
                result.stage = STAGE_VOL_PRICE_UP
                result.matched = True
                result.score = 30
                result.support = round(np.min(lows[-10:]), 2)
                result.pressure = round(np.max(highs[-10:]) * 1.02, 2)
                result.tags = ["量价突破", "主力启动", "二次确认"]
                return result
            result.stage = "无量价特征"
            result.score = 5
            return result

        # 2. 筑底确认（V1.1放宽：波动<15%，原10%）
        bottom_start = max(0, shrink_idx - 5)
        bottom_end = min(len(bars) - 1, shrink_idx + 5)
        bottom_closes = closes[bottom_start:bottom_end + 1]
        bottom_min = np.min(bottom_closes)
        # V1.3.4：修复除以0，bottom_min<=0时跳过波动率计算
        if bottom_min > 0:
            bottom_volatility = (np.max(bottom_closes) - bottom_min) / bottom_min * 100
        else:
            bottom_volatility = 100  # 默认值大，不认为是筑底
        is_bottom = bottom_volatility < 15  # V1.1放宽

        # 3. 量价齐升
        vp_up_start = shrink_idx + 1
        vp_up_end = None
        if vp_up_start < last_idx:
            for i in range(vp_up_start, min(vp_up_start + 15, last_idx + 1)):
                if closes[i] > closes[shrink_idx] * 1.03:  # V1.1放宽1.05→1.03
                    avg_vol_before = np.mean(volumes[max(0, i - 5):i])
                    if volumes[i] > avg_vol_before * 1.2:  # V1.1放宽1.3→1.2
                        vp_up_end = i
                        break
        is_vp_up = vp_up_end is not None

        # 4. 突破压力
        breakout_level = None
        breakout_idx = None
        if is_vp_up:
            pressure_start = max(0, shrink_idx - 20)
            pressure_high = np.max(highs[pressure_start:shrink_idx + 1])
            for i in range(vp_up_end, last_idx + 1):
                if closes[i] > pressure_high * 0.995 and volumes[i] > np.mean(volumes[max(0, i - 5):i]) * 1.1:
                    breakout_level = pressure_high
                    breakout_idx = i
                    break
        is_breaking = breakout_idx is not None

        # 5. 回踩确认
        is_confirm = False
        if is_breaking and breakout_idx < last_idx:
            min_after = np.min(lows[breakout_idx:])
            vol_after = np.mean(volumes[breakout_idx:])
            vol_before = np.mean(volumes[max(0, breakout_idx - 5):breakout_idx])
            if min_after >= breakout_level * 0.96 and vol_after < vol_before * 0.95:  # V1.1放宽
                is_confirm = True

        # 6. 再次放量突破
        is_re_break = False
        if is_confirm:
            if last_bar.close > breakout_level * 1.01 and last_bar.volume > np.mean(volumes[-5:]) * 1.2:
                is_re_break = True

        # 7. 阶段判断（V1.1：允许各阶段）
        if is_re_break:
            stage = "再次放量突破"
        elif is_confirm:
            stage = STAGE_CONFIRM
        elif is_breaking:
            stage = STAGE_BREAKOUT
        elif is_vp_up:
            stage = STAGE_VOL_PRICE_UP
        elif is_bottom:
            stage = STAGE_BOTTOM
        else:
            stage = STAGE_BOTTOM

        # V1.1：只要有缩量筑底或量价转强就匹配
        matched = is_bottom or is_vp_up or is_breaking or is_confirm

        # 8. 买点
        buy_signals = []
        if is_vp_up and not is_breaking:
            buy_signals.append("量价齐升初期介入")
        if is_breaking:
            buy_signals.append("放量突破压力位")
        if is_confirm:
            buy_signals.append("回踩确认低吸")
        if is_re_break:
            buy_signals.append("再次放量突破加仓")

        # 9. 风险
        risks = []
        if current_price < closes[shrink_idx] * 0.93:
            risks.append("跌破筑底位置")
        if is_breaking and current_price < breakout_level * 0.96:
            risks.append("突破后跌破突破位")
        if last_bar.pct_chg < -3 and last_bar.volume > np.mean(volumes[-10:]) * 1.5:
            risks.append("放量下跌")

        # 10. 模型独立评分
        score = self._calc_score(is_bottom, is_vp_up, is_breaking, is_confirm, is_re_break,
                                  bottom_volatility, stage)

        # 支撑/压力
        support = round(closes[shrink_idx], 2)
        pressure = round(breakout_level, 2) if breakout_level else round(np.max(highs[-20:]), 2)

        result.matched = matched
        result.stage = stage
        result.score = score
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["量价突破", "主力启动", "二次确认"]
        result.support = support
        result.pressure = pressure
        result.detail = {
            "shrink_date": bars[shrink_idx].date,
            "shrink_volume": round(volumes[shrink_idx], 0),
            "bottom_volatility_pct": round(bottom_volatility, 2),
            "is_bottom": is_bottom,
            "is_vp_up": is_vp_up,
            "is_breaking": is_breaking,
            "breakout_level": round(breakout_level, 2) if breakout_level else 0,
            "is_confirm": is_confirm,
            "is_re_break": is_re_break,
            "current_price": round(current_price, 2),
        }
        return result

    def _calc_score(self, is_bottom, is_vp_up, is_breaking, is_confirm, is_re_break,
                     bottom_volatility, stage):
        score = 25.0  # V1.1基础分
        if is_bottom:
            score += 15
            if bottom_volatility < 8:
                score += 5
        if is_vp_up:
            score += 15
        if is_breaking:
            score += 20
        if is_confirm:
            score += 15
        if is_re_break:
            score += 10
        # 阶段加分
        if stage == STAGE_BREAKOUT:
            score += 8
        elif stage == STAGE_CONFIRM:
            score += 6
        elif stage == STAGE_VOL_PRICE_UP:
            score += 4
        return min(round(score, 1), 100)
