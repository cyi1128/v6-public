# -*- coding: utf-8 -*-
"""
K线AI模式标注生成器 V1.1

6色区域：
- 绿色=缩量区域
- 黄色=箱体区域
- 红色=突破区域
- 蓝色=回踩确认区域
- 紫色=主力吸筹区域（V1.1新增）
- 橙色=风险区域（V1.1新增）

标记：B1/B2/B3买点，S1/S2/S3/S4卖点，风险位置
"""
import numpy as np
from typing import List, Dict
from strategy.base import (
    KlineBar, KlineAnnotation, ModelMatch, BuySellSignal, VolumeAnalyzer,
    REGION_SHRINK, REGION_BOX, REGION_BREAKOUT, REGION_CONFIRM,
    REGION_ACCUMULATION, REGION_RISK, REGION_COLORS, REGION_NAMES,
)


class KlineAnnotationGenerator:
    """K线6色区域标注生成器"""

    def generate(self, bars: List[KlineBar], closes: np.ndarray, highs: np.ndarray,
                 lows: np.ndarray, volumes: np.ndarray, matches: List[ModelMatch],
                 buy_sell: BuySellSignal = None) -> KlineAnnotation:
        annotation = KlineAnnotation()
        if len(bars) < 20:
            return annotation

        # 1. 缩量区域（绿色）
        for region in self._detect_shrink_regions(volumes):
            annotation.regions.append(self._make_region(REGION_SHRINK, region, bars))

        # 2. 箱体区域（黄色）
        for m in matches:
            if m.matched and m.model_name == "箱体突破" and 'box_top' in m.detail:
                box_start = m.detail.get('box_start', 0)
                box_end = m.detail.get('box_end', len(bars) - 1)
                if isinstance(box_start, int) and isinstance(box_end, int):
                    region = {'start': box_start, 'end': box_end,
                              'top': m.detail.get('box_top'), 'bottom': m.detail.get('box_bottom')}
                    annotation.regions.append(self._make_region(REGION_BOX, region, bars))

        # 3. 突破区域（红色）
        for m in matches:
            if m.matched and m.stage in ['突破区域', '再次放量突破']:
                end_idx = len(bars) - 1
                start_idx = max(0, end_idx - 4)
                annotation.regions.append(self._make_region(
                    REGION_BREAKOUT, {'start': start_idx, 'end': end_idx}, bars,
                    label=f'突破-{m.model_name}'))

        # 4. 回踩确认区域（蓝色）
        for m in matches:
            if m.matched and m.stage == '回踩确认':
                end_idx = len(bars) - 1
                start_idx = max(0, end_idx - 3)
                annotation.regions.append(self._make_region(
                    REGION_CONFIRM, {'start': start_idx, 'end': end_idx}, bars,
                    label=f'回踩确认-{m.model_name}'))

        # 5. 主力吸筹区域（紫色）V1.1新增
        for region in self._detect_accumulation_regions(bars, closes, volumes):
            annotation.regions.append(self._make_region(REGION_ACCUMULATION, region, bars))

        # 6. 风险区域（橙色）V1.1新增
        for region in self._detect_risk_regions(bars, volumes):
            annotation.regions.append(self._make_region(REGION_RISK, region, bars))

        # 7. 买卖点标记
        if buy_sell:
            if buy_sell.buy_level:
                annotation.markers.append({
                    'type': 'buy', 'level': buy_sell.buy_level,
                    'idx': len(bars) - 1, 'date': bars[-1].date,
                    'price': bars[-1].close,
                    'label': f"{buy_sell.buy_level}: {'；'.join(buy_sell.buy_reasons[:2])}",
                })
            if buy_sell.sell_level:
                annotation.markers.append({
                    'type': 'sell', 'level': buy_sell.sell_level,
                    'idx': len(bars) - 1, 'date': bars[-1].date,
                    'price': bars[-1].close,
                    'label': f"{buy_sell.sell_level}: {'；'.join(buy_sell.sell_reasons[:2])}",
                })

        # 模型信号标记
        for m in matches:
            if not m.matched:
                continue
            for sig in m.signals:
                annotation.markers.append({
                    'type': 'signal', 'idx': len(bars) - 1,
                    'date': bars[-1].date, 'price': bars[-1].close,
                    'label': sig, 'model': m.model_name,
                })
            for risk in m.risks:
                annotation.markers.append({
                    'type': 'risk', 'idx': len(bars) - 1,
                    'date': bars[-1].date, 'price': bars[-1].close,
                    'label': risk, 'model': m.model_name,
                })

        # 模型标签
        for m in matches:
            if m.matched:
                annotation.model_labels.append({
                    'model': m.model_name, 'stage': m.stage,
                    'tags': m.tags, 'score': m.score,
                    'idx': len(bars) - 1,
                })

        return annotation

    def _make_region(self, region_type, region, bars, label=None):
        start = region['start']
        end = region['end']
        return {
            'type': region_type,
            'color': REGION_COLORS.get(region_type, '#888'),
            'start_idx': start, 'end_idx': end,
            'start_date': bars[start].date if start < len(bars) else '',
            'end_date': bars[end].date if end < len(bars) else '',
            'top': region.get('top'), 'bottom': region.get('bottom'),
            'label': label or REGION_NAMES.get(region_type, region_type),
        }

    def _detect_shrink_regions(self, volumes):
        regions = []
        if len(volumes) < 15:
            return regions
        avg_vol = np.mean(volumes)
        in_shrink = False
        start = 0
        for i in range(len(volumes)):
            if volumes[i] < avg_vol * 0.75:
                if not in_shrink:
                    in_shrink = True
                    start = i
            else:
                if in_shrink:
                    in_shrink = False
                    if i - start >= 3:
                        regions.append({'start': start, 'end': i - 1})
        if in_shrink and len(volumes) - start >= 3:
            regions.append({'start': start, 'end': len(volumes) - 1})
        return regions[-3:]

    def _detect_accumulation_regions(self, bars, closes, volumes):
        """V1.1新增：检测主力吸筹区域（缩量+小阴小阳+价格横盘）"""
        regions = []
        if len(bars) < 15:
            return regions
        i = 5
        while i < len(bars) - 5:
            found = False
            for length in range(15, 4, -1):
                if i + length >= len(bars):
                    continue
                seg_closes = closes[i:i + length]
                seg_volumes = volumes[i:i + length]
                if min(seg_closes) <= 0:
                    continue
                volatility = (max(seg_closes) - min(seg_closes)) / min(seg_closes) * 100
                if volatility > 12:
                    continue
                avg_vol = np.mean(volumes[max(0, i - 10):i]) if i > 0 else np.mean(seg_volumes)
                if avg_vol <= 0 or np.mean(seg_volumes) > avg_vol * 0.85:
                    continue
                seg = bars[i:i + length]
                big_moves = sum(1 for b in seg if abs(b.pct_chg) > 4)
                if big_moves > length * 0.2:
                    continue
                regions.append({'start': i, 'end': i + length - 1})
                i = i + length
                found = True
                break
            if not found:
                i += 1
        return regions[-2:]

    def _detect_risk_regions(self, bars, volumes):
        """V1.1新增：检测风险区域（放量下跌/放量滞涨）"""
        regions = []
        if len(bars) < 10:
            return regions
        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        in_risk = False
        start = 0
        for i in range(max(0, len(bars) - 30), len(bars)):
            bar = bars[i]
            is_risk = False
            if bar.volume > avg_vol * 1.4:
                if bar.pct_chg < -2:
                    is_risk = True
                elif bar.pct_chg < 1 and bar.high > max(bar.open, bar.close) * 1.02:
                    is_risk = True
            if is_risk:
                if not in_risk:
                    in_risk = True
                    start = i
            else:
                if in_risk:
                    in_risk = False
                    if i - start >= 1:
                        regions.append({'start': start, 'end': i - 1})
        if in_risk and len(bars) - start >= 1:
            regions.append({'start': start, 'end': len(bars) - 1})
        return regions[-2:]
