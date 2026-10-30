# -*- coding: utf-8 -*-
"""
主升启动模型识别引擎
识别底部吸筹后的主升浪启动买点
"""
import pandas as pd
import numpy as np
from utils.indicators import calc_ma_series


class MainTrendScanner:
    """主升启动模型扫描器"""

    def scan(self, kline_data):
        """
        扫描主升启动买点

        Args:
            kline_data: dict，包含 'open', 'high', 'low', 'close', 'volume'

        Returns:
            dict or None: {'signal': 'main_trend_start', 'name': '主升启动买点', 'color': '#ff1744', 'desc': '', 'score': }
        """
        if not kline_data or len(kline_data.get('close', [])) < 40:
            return None

        closes = kline_data['close']
        highs = kline_data['high']
        lows = kline_data['low']
        opens = kline_data['open']
        volumes = kline_data['volume']

        ma5 = calc_ma_series(closes, 5)
        ma10 = calc_ma_series(closes, 10)

        score = 0
        conditions = []

        # 条件1：股价长期运行在5日线下方（最近20天中至少12天在5日线下）
        below_days = 0
        for i in range(-20, -5):
            if abs(i) >= len(closes):
                break
            m = ma5.iloc[i] if not pd.isna(ma5.iloc[i]) else closes[i]
            if closes[i] < m:
                below_days += 1
        if below_days >= 12:
            score += 15
            conditions.append(f'长期在5日线下({below_days}/20天)')

        # 条件2：调整过程中K线逐渐靠近5日均线
        recent_diff = abs(closes[-5] - (ma5.iloc[-5] if not pd.isna(ma5.iloc[-5]) else closes[-5]))
        early_diff = abs(closes[-15] - (ma5.iloc[-15] if not pd.isna(ma5.iloc[-15]) else closes[-15]))
        if recent_diff < early_diff:
            score += 10
            conditions.append('逐渐靠近5日线')

        # 条件3：成交量绿柱缩量，随后红柱逐渐放量
        # 简化：最近5天平均成交量 > 之前10天平均成交量
        recent_vol = np.mean(volumes[-5:]) if len(volumes) >= 5 else 0
        early_vol = np.mean(volumes[-15:-5]) if len(volumes) >= 15 else 0
        if early_vol > 0 and recent_vol > early_vol * 1.1:
            score += 15
            conditions.append('成交量逐渐放大')

        # 条件4：股价贴近5日线，价格差≤1元
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else current_close
        if abs(current_close - current_ma5) <= 1.0:
            score += 10
            conditions.append(f'贴近5日线(差{abs(current_close-current_ma5):.2f}元)')

        # 条件5：出现放量阳线，成交量大于前两日
        if len(closes) >= 3:
            is_yang = closes[-1] > opens[-1]
            vol_increase = volumes[-1] > max(volumes[-2], volumes[-3]) * 1.2 if len(volumes) >= 3 else False
            if is_yang and vol_increase:
                score += 15
                conditions.append('放量阳线')

        # 条件6：阳线站上5日线
        if current_close > current_ma5 and opens[-1] < current_ma5:
            score += 10
            conditions.append('站上5日线')

        # 条件7：随后缩量回踩，不跌破启动阳线最低价
        # 简化：最近3天内有缩量回踩，且最低价高于前一根阳线最低价
        if len(closes) >= 5:
            yang_low = lows[-3] if closes[-3] > opens[-3] else lows[-1]
            recent_low = min(lows[-3:])
            vol_shrink = volumes[-1] < volumes[-3] * 0.8 if len(volumes) >= 4 else False
            if recent_low >= yang_low * 0.98 and vol_shrink:
                score += 10
                conditions.append('缩量回踩不破低点')

        # 条件8：再次出现放量阳线，突破MA5和MA10
        current_ma10 = ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else current_close
        is_yang = closes[-1] > opens[-1]
        vol_increase = volumes[-1] > volumes[-2] * 1.2 if len(volumes) >= 2 else False
        break_ma5 = current_close > current_ma5
        break_ma10 = current_close > current_ma10

        if is_yang and vol_increase and break_ma5 and break_ma10:
            score += 15
            conditions.append('放量突破MA5/MA10')

        # 总分>=70分且满足至少5个条件，识别为主升启动
        if score >= 70 and len(conditions) >= 5:
            return {
                'signal': 'main_trend_start',
                'name': '主升启动买点',
                'color': '#ff1744',
                'desc': f'主升启动({score}分): {", ".join(conditions[:3])}',
                'score': score,
                'conditions': conditions
            }

        return None


_scanner = None


def get_main_trend_scanner():
    global _scanner
    if _scanner is None:
        _scanner = MainTrendScanner()
    return _scanner
