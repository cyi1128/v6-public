# -*- coding: utf-8 -*-
"""
买卖点确认系统 V1.1

买点B1-B3：
- B1观察买点：模型形成中
- B2确认买点：缩量回踩5日线 或 突破确认
- B3强势买点：三个模型出现共振

卖点S1-S4：
- S1跌破MA5
- S2跌破箱体
- S3放量滞涨
- S4突破失败

V1.1核心：没有B级买点的股票也要进入观察池。
"""
import numpy as np
from typing import List, Dict
from strategy.base import (
    KlineBar, ModelMatch, BuySellSignal, TechnicalIndicators, VolumeAnalyzer,
    BUY_B1, BUY_B2, BUY_B3, SELL_S1, SELL_S2, SELL_S3, SELL_S4,
)


class BuySellSignalDetector:
    """买卖点确认检测器"""

    def detect(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
               lows: np.ndarray, volumes: np.ndarray, matches: List[ModelMatch]) -> BuySellSignal:
        result = BuySellSignal()
        if len(bars) < 10:
            return result

        last_bar = bars[-1]
        ma5 = TechnicalIndicators.ma(closes, 5)
        ma10 = TechnicalIndicators.ma(closes, 10)

        matched = [m for m in matches if m.matched]

        # ===== 买点判断 =====
        buy_reasons = []

        # B3强势买点：三个模型共振（至少2个模型匹配且都有信号）
        models_with_signal = [m for m in matched if m.signals]
        if len(models_with_signal) >= 2:
            result.buy_level = BUY_B3
            buy_reasons.append(f"模型共振：{'、'.join(m.model_name for m in models_with_signal[:2])}")
        # B2确认买点：缩量回踩5日线 或 突破确认
        elif self._check_b2(last_bar, ma5, volumes, matched):
            result.buy_level = BUY_B2
            if self._check_pullback_ma5(last_bar, ma5, volumes):
                buy_reasons.append("缩量回踩5日线不破")
            if self._check_breakout_confirm(matched):
                buy_reasons.append("突破确认")
        # B1观察买点：模型形成中（只要有匹配模型就是B1）
        elif matched:
            result.buy_level = BUY_B1
            stages = set(m.stage for m in matched)
            buy_reasons.append(f"模型形成中：{'、'.join(list(stages)[:2])}")

        result.buy_reasons = buy_reasons

        # ===== 卖点判断 =====
        sell_reasons = []

        # S1跌破MA5
        if not np.isnan(ma5[-1]) and last_bar.close < ma5[-1] * 0.99:
            result.sell_level = SELL_S1
            sell_reasons.append(f"跌破MA5({ma5[-1]:.2f})")

        # S2跌破箱体/支撑
        for m in matched:
            if m.support > 0 and last_bar.close < m.support * 0.97:
                if not result.sell_level or result.sell_level == SELL_S1:
                    result.sell_level = SELL_S2
                sell_reasons.append(f"跌破{m.model_name}支撑位({m.support:.2f})")
                break

        # S3放量滞涨
        if self._check_volume_stagnation(last_bar, volumes, closes):
            if not result.sell_level or result.sell_level in [SELL_S1, SELL_S2]:
                result.sell_level = SELL_S3
            sell_reasons.append("放量滞涨")

        # S4突破失败
        for m in matched:
            if '突破失败' in str(m.risks):
                if not result.sell_level:
                    result.sell_level = SELL_S4
                sell_reasons.append("突破失败")
                break

        result.sell_reasons = sell_reasons

        # ===== 风险等级 =====
        risk_count = len(sell_reasons)
        has_volume_drop = any('放量下跌' in str(m.risks) for m in matched)
        if risk_count >= 2 or has_volume_drop:
            result.risk_level = "高"
        elif risk_count == 1:
            result.risk_level = "中"
        else:
            result.risk_level = "低"

        return result

    def _check_b2(self, last_bar, ma5, volumes, matched):
        """B2确认买点：缩量回踩5日线 或 突破确认"""
        return self._check_pullback_ma5(last_bar, ma5, volumes) or self._check_breakout_confirm(matched)

    def _check_pullback_ma5(self, last_bar, ma5, volumes):
        """缩量回踩5日线不破"""
        if np.isnan(ma5[-1]) or ma5[-1] <= 0:
            return False
        # 最低价触及5日线但收盘价在5日线上方
        touched = last_bar.low <= ma5[-1] * 1.01
        held = last_bar.close > ma5[-1] * 0.995
        # 缩量
        shrinking = VolumeAnalyzer.is_volume_shrinking(volumes, period=3) if len(volumes) >= 6 else False
        return touched and held and shrinking

    def _check_breakout_confirm(self, matched):
        """突破确认"""
        for m in matched:
            if m.stage in ['回踩确认', '突破区域'] and m.signals:
                return True
            if '突破' in str(m.signals) or '回踩' in str(m.signals):
                return True
        return False

    def _check_volume_stagnation(self, last_bar, volumes, closes):
        """放量滞涨：成交量放大但涨幅很小"""
        if len(volumes) < 10:
            return False
        avg_vol = np.mean(volumes[-10:])
        vol_expanded = last_bar.volume > avg_vol * 1.5
        small_gain = abs(last_bar.pct_chg) < 1.5
        # 上影线长
        upper_shadow = (last_bar.high - max(last_bar.open, last_bar.close)) / last_bar.close
        long_upper = upper_shadow > 0.02
        return vol_expanded and (small_gain or long_upper) and last_bar.pct_chg <= 0.5
