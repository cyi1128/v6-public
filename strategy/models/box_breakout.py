# -*- coding: utf-8 -*-
"""
模型二：横盘箱体突破模型（二波启动模型）V1.1

V1.1放宽：
- 原必须完整箱体 → 允许5-30交易日整理，允许平台雏形
- 不要求完整结构，允许识别形成中阶段
- 模型独立评分0-100
- 增加支撑位/压力位字段
"""
import numpy as np
from typing import List, Dict
from strategy.base import (
    KlineBar, ModelMatch, TechnicalIndicators, VolumeAnalyzer,
    MODEL_BOX_BREAKOUT, STAGE_PLATFORM, STAGE_BREAKOUT, STAGE_CONFIRM,
    STAGE_PULLBACK,
)


class BoxBreakoutModel:
    """横盘箱体突破模型（V1.1放宽版）"""

    def __init__(self):
        self.name = MODEL_BOX_BREAKOUT

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

        # 1. 寻找前期上涨（V1.1放宽：近40日涨幅>10%即可，原15%）
        uptrend_end = self._find_uptrend(closes, lookback=40)
        if uptrend_end is None:
            # V1.1放宽：即使没有明显上涨，只要有横盘也匹配
            uptrend_end = max(0, last_idx - 20)

        # 2. 检测箱体/平台（V1.1放宽：5-30天，允许雏形）
        box_info = self._detect_box(bars, closes, highs, lows, volumes, uptrend_end)

        if not box_info.get('is_box', False):
            # V1.1放宽：没有完整箱体也给基础分，标记为平台雏形
            result.stage = STAGE_PLATFORM
            result.matched = True
            result.score = 25
            result.support = round(np.min(lows[-10:]), 2) if len(lows) >= 10 else round(last_bar.low, 2)
            result.pressure = round(np.max(highs[-10:]), 2) if len(highs) >= 10 else round(last_bar.high, 2)
            result.tags = ["箱体突破", "平台蓄势", "二次启动"]
            return result

        box_top = box_info['box_top']
        box_bottom = box_info['box_bottom']
        box_start = box_info['box_start']
        box_end = box_info['box_end']
        is_shrinking = box_info.get('is_shrinking', False)
        current_price = closes[last_idx]

        # 3. 突破/回踩判断
        is_breaking_out = (current_price > box_top * 1.005 and  # V1.1放宽1.01→1.005
                           last_bar.volume > np.mean(volumes[box_start:box_end + 1]) * 1.1)  # V1.1放宽1.2→1.1

        is_pullback_confirm = False
        if box_end < last_idx - 1:
            breakout_idx = None
            for i in range(box_end + 1, last_idx + 1):
                if closes[i] > box_top * 1.005:
                    breakout_idx = i
                    break
            if breakout_idx is not None and breakout_idx < last_idx:
                min_after = np.min(lows[breakout_idx:])
                if min_after >= box_top * 0.97:
                    is_pullback_confirm = True

        # 4. 阶段
        if is_breaking_out:
            stage = STAGE_BREAKOUT
        elif is_pullback_confirm:
            stage = STAGE_CONFIRM
        elif is_shrinking:
            stage = STAGE_PLATFORM
        else:
            stage = STAGE_PULLBACK

        # V1.1：只要有箱体/平台就匹配
        matched = box_info.get('is_box', False)

        # 5. 三买点
        buy_signals = []
        if is_shrinking and not np.isnan(ma5[last_idx]):
            if last_bar.close > ma5[last_idx] and bars[-2].close <= ma5[last_idx - 1]:
                buy_signals.append("第一买点：缩量结束站上MA5")
        if is_breaking_out:
            buy_signals.append("第二买点：放量突破箱体")
        if is_pullback_confirm and last_bar.close > box_top:
            buy_signals.append("第三买点：回踩箱体顶部不破")

        # 6. 风险
        risks = []
        if current_price < box_bottom * 0.97:
            risks.append("跌破箱体底部")
        if box_end < last_idx - 2:
            for i in range(box_end + 1, last_idx + 1):
                if closes[i] > box_top * 1.005 and i < last_idx and closes[last_idx] < box_top:
                    risks.append("突破失败重新进入箱体")
                    break

        # 7. 模型独立评分
        score = self._calc_score(box_info, is_shrinking, is_breaking_out, is_pullback_confirm, stage)

        result.matched = matched
        result.stage = stage
        result.score = score
        result.signals = buy_signals
        result.risks = risks
        result.tags = ["箱体突破", "二次启动", "平台蓄势"]
        result.support = round(box_bottom, 2)
        result.pressure = round(box_top, 2)
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

    def _find_uptrend(self, closes, lookback=40):
        if len(closes) < lookback:
            lookback = len(closes)
        start = len(closes) - lookback
        segment = closes[start:]
        if len(segment) < 8:
            return None
        peak_idx = np.argmax(segment) + start
        if peak_idx > start + 3 and closes[start] > 0:
            rise = (closes[peak_idx] - closes[start]) / closes[start] * 100
            if rise > 10:  # V1.1放宽15%→10%
                return peak_idx
        return None

    def _detect_box(self, bars, closes, highs, lows, volumes, uptrend_end):
        result = {'is_box': False}
        box_start = uptrend_end + 1
        if box_start >= len(bars) - 3:
            return result

        # V1.1放宽：5-30天（原10-30天）
        for box_end in range(min(box_start + 4, len(bars) - 1),
                              min(box_start + 29, len(bars) - 1)):
            box_highs = highs[box_start:box_end + 1]
            box_lows = lows[box_start:box_end + 1]
            box_top = np.max(box_highs)
            box_bottom = np.min(box_lows)
            if box_bottom <= 0:
                continue
            height_pct = (box_top - box_bottom) / box_bottom * 100
            # V1.1放宽：2%-30%（原3%-25%）
            if height_pct < 2 or height_pct > 30:
                continue

            # V1.1放宽波动收窄条件（原后半段<前半段1.2倍，改为不强制）
            mid = (box_start + box_end) // 2
            if mid > box_start and box_end - mid > 2:
                first_amp = np.max(highs[box_start:mid + 1]) - np.min(lows[box_start:mid + 1])
                second_amp = np.max(highs[mid:box_end + 1]) - np.min(lows[mid:box_end + 1])
                if second_amp > first_amp * 1.5:  # V1.1放宽1.2→1.5
                    continue

            # 均线粘合（V1.1放宽：差距<8%，原5%）
            ma5 = TechnicalIndicators.ma(closes, 5)
            ma10 = TechnicalIndicators.ma(closes, 10)
            if not np.isnan(ma5[box_end]) and not np.isnan(ma10[box_end]) and ma10[box_end] > 0:
                ma_gap = abs(ma5[box_end] - ma10[box_end]) / ma10[box_end] * 100
                if ma_gap > 8:
                    continue

            # 缩量（V1.1放宽：<前期90%，原80%）
            box_volumes = volumes[box_start:box_end + 1]
            prev_volumes = volumes[max(0, box_start - 10):box_start]
            is_shrinking = (np.mean(box_volumes) < np.mean(prev_volumes) * 0.9
                           if len(prev_volumes) > 0 else False)

            return {
                'is_box': True, 'box_top': box_top, 'box_bottom': box_bottom,
                'box_start': box_start, 'box_end': box_end,
                'is_shrinking': is_shrinking, 'height_pct': height_pct,
            }
        return result

    def _calc_score(self, box_info, is_shrinking, is_breaking, is_confirm, stage):
        score = 35.0  # V1.1基础分
        # 箱体质量
        days = box_info.get('box_days', 0)
        if 8 <= days <= 20:
            score += 15
        elif 5 <= days < 8 or 20 < days <= 30:
            score += 8
        # 缩量
        if is_shrinking:
            score += 15
        # 突破/回踩
        if is_breaking:
            score += 20
        if is_confirm:
            score += 15
        # 阶段
        if stage == STAGE_BREAKOUT:
            score += 10
        elif stage == STAGE_CONFIRM:
            score += 8
        elif stage == STAGE_PLATFORM:
            score += 5
        return min(round(score, 1), 100)
