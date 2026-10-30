# -*- coding: utf-8 -*-
"""
AI六维度评分系统 V1.1

总分100：
主力行为结构40 + 量价关系20 + 趋势均线15 + 涨停强势基因10 + 技术指标确认10 + 市场环境5

V1.1调整：
- 评分等级改为：启动候选(90-100)/强势候选(80-90)/重点观察(70-80)/观察池(60-70)/低关注(60以下)
- 取消70分硬过滤，60分以上均显示
- 评分用于排序，不是大量删除
"""
import numpy as np
from typing import List, Dict, Optional
from strategy.base import (
    KlineBar, ModelMatch, AIScore, TechnicalIndicators,
    SCORE_LAUNCH_CANDIDATE, SCORE_STRONG_CANDIDATE, SCORE_KEY_WATCH,
    SCORE_WATCH, SCORE_LOW,
)


class AIScoringSystem:
    """AI六维度评分系统"""

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
        result = AIScore()
        if len(bars) < 20:
            result.reason = "数据不足"
            return result

        result.main_force_structure = self._score_main_force(matches, bars, volumes)
        result.breakdown['主力行为结构'] = result.main_force_structure

        result.volume_price = self._score_volume_price(bars, closes, volumes)
        result.breakdown['量价关系'] = result.volume_price

        result.trend_ma = self._score_trend_ma(closes)
        result.breakdown['趋势均线'] = result.trend_ma

        result.limit_up_gene = self._score_limit_up_gene(bars)
        result.breakdown['涨停强势基因'] = result.limit_up_gene

        result.tech_indicator = self._score_tech_indicator(highs, lows, closes)
        result.breakdown['技术指标确认'] = result.tech_indicator

        result.market_env = self._score_market_env(market_data)
        result.breakdown['市场环境'] = result.market_env

        result.total = round(
            result.main_force_structure + result.volume_price + result.trend_ma +
            result.limit_up_gene + result.tech_indicator + result.market_env, 2
        )

        # V1.1新等级
        if result.total >= 90:
            result.level = SCORE_LAUNCH_CANDIDATE
        elif result.total >= 80:
            result.level = SCORE_STRONG_CANDIDATE
        elif result.total >= 70:
            result.level = SCORE_KEY_WATCH
        elif result.total >= 60:
            result.level = SCORE_WATCH
        else:
            result.level = SCORE_LOW

        result.reason = self._generate_reason(result, matches)
        return result

    def _score_main_force(self, matches, bars, volumes):
        score = 10.0  # V1.1基础分（原0）
        matched = [m for m in matches if m.matched]
        # 匹配模型数量
        score += min(len(matched) * 12, 24)  # V1.1放宽
        # 模型阶段质量
        for m in matched:
            if m.stage in ['突破区域', '回踩确认', '再次放量突破']:
                score += 10
                break
            elif m.stage in ['量价齐升', '再次启动']:
                score += 7
                break
            elif m.stage in ['缩量洗盘', '平台蓄势', '极限缩量筑底']:
                score += 5
                break
        # 模型最高分（V1.1新增）
        if matched:
            best_score = max(m.score for m in matched)
            score += best_score * 0.06  # 模型分贡献
        # 主力资金痕迹
        if len(bars) >= 10:
            recent = bars[-10:]
            avg_vol = np.mean(volumes[-10:])
            vol_up = sum(1 for b in recent if b.pct_chg > 2 and b.volume > avg_vol * 1.1)
            shrink_down = sum(1 for b in recent if b.pct_chg < 0 and b.volume < avg_vol * 0.9)
            score += min(vol_up * 1.5, 5)
            score += min(shrink_down * 1.0, 5)
        return min(round(score, 2), 40)

    def _score_volume_price(self, bars, closes, volumes):
        score = 8.0  # V1.1基础分
        if len(bars) < 10:
            return score
        last_bar = bars[-1]
        vol_ratio = 1.0
        if len(volumes) >= 10:
            prev = np.mean(volumes[-10:-5])
            recent = np.mean(volumes[-5:])
            vol_ratio = recent / prev if prev > 0 else 1.0
        # 量价配合
        if last_bar.pct_chg > 0 and vol_ratio > 1.1:
            score += 8
        elif last_bar.pct_chg > 0 and vol_ratio > 0.9:
            score += 6
        elif last_bar.pct_chg < 0 and vol_ratio < 0.85:
            score += 5
        elif last_bar.pct_chg < 0 and vol_ratio > 1.2:
            score += 0
        else:
            score += 3
        # 近10日量能比
        up_vol = sum(b.volume for b in bars[-10:] if b.pct_chg > 0)
        down_vol = sum(b.volume for b in bars[-10:] if b.pct_chg <= 0)
        if down_vol > 0:
            ratio = up_vol / down_vol
            if ratio > 1.5:
                score += 8
            elif ratio > 1.2:
                score += 6
            elif ratio > 1.0:
                score += 4
            else:
                score += 2
        else:
            score += 4
        return min(round(score, 2), 20)

    def _score_trend_ma(self, closes):
        score = 5.0  # V1.1基础分
        if len(closes) < 20:
            return score
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)
        ma20 = TechnicalIndicators.ma(closes, 20)
        last = closes[-1]
        # 多头排列
        if not np.isnan(ma5[-1]) and not np.isnan(ma10[-1]) and not np.isnan(ma20[-1]):
            if ma5[-1] > ma10[-1] > ma20[-1]:
                score += 8
            elif ma5[-1] > ma10[-1]:
                score += 5
            else:
                score += 2
        # 价格位置
        if not np.isnan(ma20[-1]) and ma20[-1] > 0:
            if last > ma20[-1]:
                score += 4
            elif last > ma20[-1] * 0.97:
                score += 2
        # 均线方向
        if not np.isnan(ma20[-1]) and not np.isnan(ma20[-6]) and ma20[-6] > 0:
            if ma20[-1] > ma20[-6]:
                score += 3
        return min(round(score, 2), 15)

    def _score_limit_up_gene(self, bars):
        score = 3.0  # V1.1基础分
        if len(bars) < 30:
            return score
        from strategy.base import LIMIT_UP_THRESHOLD, BIG_YANG_THRESHOLD
        limit_count = sum(1 for b in bars[-60:] if b.pct_chg >= LIMIT_UP_THRESHOLD) if len(bars) >= 60 else 0
        score += min(limit_count * 2, 6)
        big_yang = sum(1 for b in bars[-30:] if b.pct_chg >= BIG_YANG_THRESHOLD)
        score += min(big_yang * 1.0, 4)
        return min(round(score, 2), 10)

    def _score_tech_indicator(self, highs, lows, closes):
        score = 3.0  # V1.1基础分
        if len(closes) < 20:
            return score
        k, d, j = TechnicalIndicators.kdj(highs, lows, closes)
        dif, dea, hist = TechnicalIndicators.macd(closes)
        if not np.isnan(k[-1]) and not np.isnan(d[-1]):
            if TechnicalIndicators.is_kdj_golden(k, d):
                score += 5
            elif k[-1] > d[-1] and j[-1] < 85:
                score += 3
            elif k[-1] < d[-1] and j[-1] > 15:
                score += 1
        if not np.isnan(dif[-1]) and not np.isnan(dea[-1]):
            if TechnicalIndicators.is_macd_golden(dif, dea):
                score += 5
            elif dif[-1] > dea[-1] and dif[-1] > 0:
                score += 3
            elif dif[-1] > dea[-1]:
                score += 2
        return min(round(score, 2), 10)

    def _score_market_env(self, market_data):
        if not market_data:
            return 2.5
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

    def _generate_reason(self, score, matches):
        reasons = []
        matched = [m for m in matches if m.matched]
        if matched:
            names = "、".join(m.model_name for m in matched)
            stages = "、".join(set(m.stage for m in matched))
            reasons.append(f"匹配模型：{names}（阶段：{stages}）")
        if score.main_force_structure >= 25:
            reasons.append("主力行为结构清晰")
        if score.volume_price >= 14:
            reasons.append("量价配合良好")
        elif score.volume_price < 8:
            reasons.append("量价配合欠佳")
        if score.trend_ma >= 10:
            reasons.append("均线多头排列")
        return "；".join(reasons) if reasons else "数据计算完成"
