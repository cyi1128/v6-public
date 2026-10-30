# -*- coding: utf-8 -*-
"""
KDJ/MACD指标信号分析模块
KDJ参数: 13,3,3
MACD参数: 8,21,5
"""
import pandas as pd
import numpy as np
from utils.indicators import calc_kdj_series, calc_macd_series


class IndicatorSignalScanner:
    """技术指标信号扫描器"""

    KDJ_SIGNALS = {
        'neg_j': {'name': '负J', 'color': '#00e676'},
        'cross_k': {'name': '穿K', 'color': '#58a6ff'},
        'k_15': {'name': '15K', 'color': '#ff9100'},
        'kdj_golden': {'name': 'KDJ金叉', 'color': '#ff1744'},
    }

    MACD_SIGNALS = {
        'macd_golden_below': {'name': '轴下金叉', 'color': '#00e676'},
        'macd_golden_above': {'name': '轴上金叉', 'color': '#ff1744'},
    }

    def scan_kdj(self, kline_data):
        """扫描KDJ信号"""
        if not kline_data or len(kline_data.get('close', [])) < 20:
            return []

        highs = kline_data['high']
        lows = kline_data['low']
        closes = kline_data['close']

        k, d, j = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)

        signals = []
        current_k = k.iloc[-1] if not pd.isna(k.iloc[-1]) else 50
        current_d = d.iloc[-1] if not pd.isna(d.iloc[-1]) else 50
        current_j = j.iloc[-1] if not pd.isna(j.iloc[-1]) else 50

        # 负J：J值≤-30 或 J<8
        if current_j <= -30 or current_j < 8:
            signals.append({
                'signal': 'neg_j',
                'name': '负J',
                'color': '#00e676',
                'desc': f'J值={current_j:.1f}'
            })

        # 穿K：J即将上穿K，距离1-3个数值
        if len(k) >= 2 and len(j) >= 2:
            prev_k = k.iloc[-2] if not pd.isna(k.iloc[-2]) else current_k
            prev_j = j.iloc[-2] if not pd.isna(j.iloc[-2]) else current_j
            # J从下方接近K，距离1-3
            if prev_j < prev_k and current_j < current_k:
                diff = current_k - current_j
                if 1 <= diff <= 3:
                    signals.append({
                        'signal': 'cross_k',
                        'name': '穿K',
                        'color': '#58a6ff',
                        'desc': f'J距K仅{diff:.1f}'
                    })

        # 15K：K值≤15
        if current_k <= 15:
            signals.append({
                'signal': 'k_15',
                'name': '15K',
                'color': '#ff9100',
                'desc': f'K值={current_k:.1f}'
            })

        # KDJ金叉：50附近出现金叉
        if len(k) >= 2 and len(d) >= 2:
            prev_k = k.iloc[-2] if not pd.isna(k.iloc[-2]) else 50
            prev_d = d.iloc[-2] if not pd.isna(d.iloc[-2]) else 50
            if prev_k <= prev_d and current_k > current_d:
                # 50附近（30-70）
                if 30 <= current_k <= 70:
                    signals.append({
                        'signal': 'kdj_golden',
                        'name': 'KDJ金叉',
                        'color': '#ff1744',
                        'desc': f'K={current_k:.1f}, D={current_d:.1f}'
                    })

        return signals

    def scan_macd(self, kline_data):
        """扫描MACD信号"""
        if not kline_data or len(kline_data.get('close', [])) < 30:
            return []

        closes = kline_data['close']
        dif, dea, macd_hist = calc_macd_series(closes, fast=8, slow=21, signal=5)

        signals = []
        current_dif = dif.iloc[-1] if not pd.isna(dif.iloc[-1]) else 0
        current_dea = dea.iloc[-1] if not pd.isna(dea.iloc[-1]) else 0
        current_hist = macd_hist.iloc[-1] if not pd.isna(macd_hist.iloc[-1]) else 0

        # 判断金叉
        is_golden = False
        if len(dif) >= 2 and len(dea) >= 2:
            prev_dif = dif.iloc[-2] if not pd.isna(dif.iloc[-2]) else current_dif
            prev_dea = dea.iloc[-2] if not pd.isna(dea.iloc[-2]) else current_dea
            if prev_dif <= prev_dea and current_dif > current_dea:
                is_golden = True

        if is_golden:
            # 轴下金叉：MACD在-0.020以内，绿柱缩短
            if -0.020 <= current_dif <= 0 and current_hist > 0:
                # 绿柱缩短（前一根hist更负）
                prev_hist = macd_hist.iloc[-2] if not pd.isna(macd_hist.iloc[-2]) else current_hist
                if prev_hist < current_hist:
                    signals.append({
                        'signal': 'macd_golden_below',
                        'name': '轴下金叉',
                        'color': '#00e676',
                        'desc': f'DIF={current_dif:.4f}'
                    })

            # 轴上金叉：MACD在0.400以上，红柱缩量
            if current_dif >= 0.400 and current_hist > 0:
                prev_hist = macd_hist.iloc[-2] if not pd.isna(macd_hist.iloc[-2]) else current_hist
                # 红柱缩量（当前hist小于前一根）
                if current_hist < prev_hist:
                    signals.append({
                        'signal': 'macd_golden_above',
                        'name': '轴上金叉',
                        'color': '#ff1744',
                        'desc': f'DIF={current_dif:.4f}'
                    })

        return signals

    def scan_all(self, kline_data):
        """扫描所有指标信号"""
        signals = []
        signals.extend(self.scan_kdj(kline_data))
        signals.extend(self.scan_macd(kline_data))
        return signals


_scanner = None


def get_indicator_scanner():
    global _scanner
    if _scanner is None:
        _scanner = IndicatorSignalScanner()
    return _scanner
