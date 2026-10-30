# -*- coding: utf-8 -*-
"""
K线形态智能扫描引擎
8个标签：横盘筑底、锐角、五日线、一阳穿5/10日线、一阳穿三线、倍量、回踩、注意买点
"""
import pandas as pd
import numpy as np
from utils.indicators import (
    calc_ma_series, calc_kdj_series, calc_macd_series,
    calc_avg_volume, is_ma_golden_cross
)


class KlineScanner:
    """K线形态扫描器"""

    # 信号标签定义
    SIGNALS = {
        'horizontal_base': {'name': '横盘筑底', 'color': '#00e676'},
        'sharp_angle': {'name': '锐角', 'color': '#d500f9'},
        'ma5_touch': {'name': '五日线', 'color': '#58a6ff'},
        'cross_5_10': {'name': '一阳穿5/10', 'color': '#ff9100'},
        'cross_three': {'name': '一阳穿三线', 'color': '#ff1744'},
        'double_volume': {'name': '倍量', 'color': '#ffea00'},
        'pullback': {'name': '回踩', 'color': '#00e5ff'},
        'buy_point': {'name': '注意买点', 'color': '#ff1744'},
        # V0.4.3 新增：五九回踩精准距离信号
        'low_5k': {'name': '低价5k', 'color': '#69f0ae'},
        'low_9k': {'name': '低价9k', 'color': '#69f0ae'},
        'close_5k': {'name': '收盘5k', 'color': '#40c4ff'},
        'close_9k': {'name': '收盘9k', 'color': '#40c4ff'},
        # V0.4.3 新增：五九回踩策略信号
        'line_59': {'name': '59线', 'color': '#ffab40'},
        'parallel_5': {'name': '平行5', 'color': '#b388ff'},
        'buy_confirm': {'name': '买入', 'color': '#00e676'},
    }

    def __init__(self):
        self._config_cache = None
        self._config_cache_time = 0

    def _load_config_cache(self):
        """加载信号配置缓存（每次扫描调用一次）"""
        import time
        now = time.time()
        # 缓存5秒，避免频繁读取文件
        if self._config_cache is None or (now - self._config_cache_time) > 5:
            from strategy.signal_config import SignalConfig
            self._config_cache = SignalConfig().get_all()
            self._config_cache_time = now
        return self._config_cache

    def _is_signal_enabled(self, signal_key):
        """检查信号是否启用（使用缓存）"""
        if self._config_cache is None:
            self._load_config_cache()
        sig = self._config_cache.get(signal_key, {})
        return sig.get('enabled', True)

    def _get_signal_params(self, signal_key):
        """获取信号参数（使用缓存）"""
        if self._config_cache is None:
            self._load_config_cache()
        sig = self._config_cache.get(signal_key, {})
        return sig.get('params', {})

    def scan(self, kline_data, turnover: float = 0):
        """
        扫描单只股票的K线形态

        Args:
            kline_data: dict，包含 'open', 'high', 'low', 'close', 'volume' 列表
            turnover: 换手率（可选，>0时检查换手率条件）

        Returns:
            list: 识别到的信号列表 [{'signal':, 'name':, 'color':, 'desc':}, ...]
        """
        if not kline_data or len(kline_data.get('close', [])) < 30:
            return []

        # 加载配置缓存（每次扫描只加载一次）
        self._load_config_cache()

        closes = kline_data['close']
        highs = kline_data['high']
        lows = kline_data['low']
        opens = kline_data['open']
        volumes = kline_data['volume']

        signals = []

        # 计算均线
        ma5 = calc_ma_series(closes, 5)
        ma9 = calc_ma_series(closes, 9)
        ma10 = calc_ma_series(closes, 10)
        ma20 = calc_ma_series(closes, 20)

        # 标签1：横盘筑底
        sig = self._check_horizontal_base(closes, lows, volumes, ma5)
        if sig:
            signals.append(sig)

        # 标签2：锐角
        sig = self._check_sharp_angle(ma5, ma20)
        if sig:
            signals.append(sig)

        # 标签3：五日线贴合
        sig = self._check_ma5_touch(closes, ma5)
        if sig:
            signals.append(sig)

        # 标签4：一阳穿5/10日线
        sig = self._check_cross_5_10(opens, closes, ma5, ma10)
        if sig:
            signals.append(sig)

        # 标签5：一阳穿三线
        sig = self._check_cross_three(opens, closes, ma5, ma10, ma20)
        if sig:
            signals.append(sig)

        # 标签6：倍量
        sig = self._check_double_volume(volumes)
        if sig:
            signals.append(sig)

        # 标签7：回踩
        sig = self._check_pullback(closes, highs, volumes, ma20)
        if sig:
            signals.append(sig)

        # 标签8：注意买点
        sig = self._check_buy_point(closes, ma5, ma10, ma20)
        if sig:
            signals.append(sig)

        # 标签9：低价5k（最低价距离MA5 0.03~0.3元）
        sig = self._check_low_5k(lows, ma5)
        if sig:
            signals.append(sig)

        # 标签10：低价9k（最低价距离MA9 0.1~0.4元）
        sig = self._check_low_9k(lows, ma9)
        if sig:
            signals.append(sig)

        # 标签11：收盘5k（收盘价距离MA5 -0.5~-0.1元）
        sig = self._check_close_5k(closes, ma5)
        if sig:
            signals.append(sig)

        # 标签12：收盘9k（收盘价距离MA9 -0.3~0.01元）
        sig = self._check_close_9k(closes, ma9)
        if sig:
            signals.append(sig)

        # 标签13：59线（连续温和调整+放量+一阳穿五九）
        sig = self._check_59_line(opens, closes, lows, volumes, ma5, ma9, turnover)
        if sig:
            signals.append(sig)

        # 标签14：平行5（次日回踩MA5附近）
        sig = self._check_parallel_5(closes, ma5)
        if sig:
            signals.append(sig)

        # 标签15：买入（长下影线后次日确认上涨且未破前低）
        sig = self._check_buy_confirm(closes, lows)
        if sig:
            signals.append(sig)

        return signals

    def _check_horizontal_base(self, closes, lows, volumes, ma5):
        """标签1：横盘筑底"""
        if len(closes) < 15:
            return None

        # 10个交易日内出现一次放量下跌跌破5日均线
        found_break = False
        break_idx = -1
        for i in range(-10, -1):
            if i + 1 < -len(closes):
                break
            # 放量下跌
            vol_increase = volumes[i] > volumes[i - 1] * 1.3 if volumes[i - 1] > 0 else False
            price_drop = closes[i] < closes[i - 1]
            below_ma5 = closes[i] < ma5.iloc[i] if not pd.isna(ma5.iloc[i]) else False
            if vol_increase and price_drop and below_ma5:
                found_break = True
                break_idx = i
                break

        if not found_break:
            return None

        # 之后当前股价低于5日均线，但距离≤1元
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1]
        if pd.isna(current_ma5):
            return None

        below_ma5 = current_close < current_ma5
        near_ma5 = abs(current_close - current_ma5) <= 1.0

        if not (below_ma5 and near_ma5):
            return None

        # 连续保持≥3个交易日（股价在5日线下方且距离≤1元）
        keep_days = 0
        for i in range(-3, 0):
            if abs(i) > len(closes):
                break
            c = closes[i]
            m = ma5.iloc[i] if not pd.isna(ma5.iloc[i]) else c
            if c < m and abs(c - m) <= 1.0:
                keep_days += 1

        if keep_days < 3:
            return None

        return {
            'signal': 'horizontal_base',
            'name': '横盘筑底',
            'color': '#00e676',
            'desc': f'放量下跌后横盘，距5日线{abs(current_close - current_ma5):.2f}元'
        }

    def _check_sharp_angle(self, ma5, ma20):
        """标签2：锐角"""
        if len(ma5) < 5 or len(ma20) < 5:
            return None

        current_ma5 = ma5.iloc[-1]
        current_ma20 = ma20.iloc[-1]
        if pd.isna(current_ma5) or pd.isna(current_ma20):
            return None

        # 20日均线在5日均线上方
        ma20_above = current_ma20 > current_ma5
        # 两条均线距离 > 0.1元 且 < 1元
        diff = current_ma20 - current_ma5
        in_range = 0.1 < diff < 1.0

        if ma20_above and in_range:
            return {
                'signal': 'sharp_angle',
                'name': '锐角',
                'color': '#d500f9',
                'desc': f'MA20({current_ma20:.2f})在MA5({current_ma5:.2f})上方，距{diff:.2f}元'
            }
        return None

    def _check_ma5_touch(self, closes, ma5):
        """标签3：五日线贴合"""
        if len(closes) < 5:
            return None

        # 前两天收盘价连续下降，跌破5日均线
        prev2_close = closes[-3]
        prev1_close = closes[-2]
        current_close = closes[-1]

        prev2_ma5 = ma5.iloc[-3] if not pd.isna(ma5.iloc[-3]) else prev2_close
        prev1_ma5 = ma5.iloc[-2] if not pd.isna(ma5.iloc[-2]) else prev1_close

        consecutive_down = prev1_close < prev2_close
        below_ma5_prev = prev1_close < prev1_ma5

        if not (consecutive_down and below_ma5_prev):
            return None

        # 当天价格重新靠近5日均线，距离0.1-1元
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else current_close
        diff = abs(current_close - current_ma5)
        near_ma5 = 0.1 <= diff <= 1.0

        if near_ma5:
            return {
                'signal': 'ma5_touch',
                'name': '五日线',
                'color': '#58a6ff',
                'desc': f'连续下跌后靠近5日线，距{diff:.2f}元'
            }
        return None

    def _check_cross_5_10(self, opens, closes, ma5, ma10):
        """标签4：一阳穿5/10日线"""
        if len(closes) < 3:
            return None

        current_open = opens[-1]
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else 0
        current_ma10 = ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else 0

        # 大阳线（涨幅>3%）
        is_big_yang = (current_close - current_open) / current_open > 0.03 if current_open > 0 else False

        # 收盘价突破5日和10日均线
        cross_ma5 = current_close > current_ma5 and current_open < current_ma5
        cross_ma10 = current_close > current_ma10 and current_open < current_ma10

        if is_big_yang and cross_ma5 and cross_ma10:
            return {
                'signal': 'cross_5_10',
                'name': '一阳穿5/10',
                'color': '#ff9100',
                'desc': f'大阳线突破MA5({current_ma5:.2f})和MA10({current_ma10:.2f})'
            }
        return None

    def _check_cross_three(self, opens, closes, ma5, ma10, ma20):
        """标签5：一阳穿三线"""
        if len(closes) < 3:
            return None

        current_open = opens[-1]
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else 0
        current_ma10 = ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else 0
        current_ma20 = ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else 0

        # 大阳线
        is_big_yang = (current_close - current_open) / current_open > 0.03 if current_open > 0 else False

        # 收盘价同时突破MA5、MA10、MA20
        cross_ma5 = current_close > current_ma5 and current_open < current_ma5
        cross_ma10 = current_close > current_ma10 and current_open < current_ma10
        cross_ma20 = current_close > current_ma20 and current_open < current_ma20

        if is_big_yang and cross_ma5 and cross_ma10 and cross_ma20:
            return {
                'signal': 'cross_three',
                'name': '一阳穿三线',
                'color': '#ff1744',
                'desc': f'大阳线突破MA5/MA10/MA20'
            }
        return None

    def _check_double_volume(self, volumes):
        """标签6：倍量"""
        if len(volumes) < 2:
            return None

        if not self._is_signal_enabled('double_volume'):
            return None
        params = self._get_signal_params('double_volume')
        ratio_min = params.get('ratio_min', 2.0)

        current_vol = volumes[-1]
        prev_vol = volumes[-2]

        if prev_vol > 0 and current_vol >= prev_vol * ratio_min:
            ratio = current_vol / prev_vol
            return {
                'signal': 'double_volume',
                'name': '倍量',
                'color': '#ffea00',
                'desc': f'成交量是前一日{ratio:.1f}倍'
            }
        return None

    def _check_pullback(self, closes, highs, volumes, ma20):
        """标签7：回踩"""
        if len(closes) < 25:
            return None

        if not self._is_signal_enabled('pullback'):
            return None
        params = self._get_signal_params('pullback')
        lookback_days = int(params.get('lookback_days', 20))
        big_yang_min = params.get('big_yang_min', 3)
        big_yang_max = params.get('big_yang_max', 7)
        vol_increase_ratio = params.get('vol_increase', 1.3)
        pullback_dist = params.get('pullback_dist', 3)

        # N日内出现放量大阳线
        found_big_yang = False
        big_yang_close = 0
        big_yang_idx = -1

        for i in range(-lookback_days, -2):
            if abs(i) > len(closes) - 1:
                break
            pct = (closes[i] - closes[i - 1]) / closes[i - 1] * 100 if closes[i - 1] > 0 else 0
            vol_increase = volumes[i] > volumes[i - 1] * vol_increase_ratio if volumes[i - 1] > 0 else False
            if big_yang_min <= pct <= big_yang_max and vol_increase:
                found_big_yang = True
                big_yang_close = closes[i]
                big_yang_idx = i
                break

        if not found_big_yang:
            return None

        # 后续股价回踩靠近该大阳线收盘价
        current_close = closes[-1]
        diff_ratio = abs(current_close - big_yang_close) / big_yang_close if big_yang_close > 0 else 1

        if diff_ratio <= pullback_dist / 100:
            return {
                'signal': 'pullback',
                'name': '回踩',
                'color': '#00e5ff',
                'desc': f'回踩大阳线收盘价{big_yang_close:.2f}，距{diff_ratio*100:.1f}%'
            }
        return None

    def _check_buy_point(self, closes, ma5, ma10, ma20):
        """标签8：注意买点"""
        if len(closes) < 10:
            return None

        if not self._is_signal_enabled('buy_point'):
            return None
        params = self._get_signal_params('buy_point')
        golden_lookback = params.get('golden_lookback', 3)
        near_ma_pct = params.get('near_ma_pct', 2)

        # 5日均线上穿20日均线（金叉）
        golden_cross = is_ma_golden_cross(ma5, ma20)

        # 检测最近N天内是否出现金叉
        golden_in_days = False
        for i in range(-golden_lookback, 0):
            if abs(i) + 1 >= len(ma5):
                break
            s_prev = ma5.iloc[i - 1]
            s_curr = ma5.iloc[i]
            l_prev = ma20.iloc[i - 1]
            l_curr = ma20.iloc[i]
            if pd.isna(s_prev) or pd.isna(s_curr) or pd.isna(l_prev) or pd.isna(l_curr):
                continue
            if s_prev <= l_prev and s_curr > l_curr:
                golden_in_days = True
                break

        if not (golden_cross or golden_in_days):
            return None

        # 第二天股价回踩MA5或MA10附近
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else 0
        current_ma10 = ma10.iloc[-1] if not pd.isna(ma10.iloc[-1]) else 0

        near_ma5 = abs(current_close - current_ma5) / current_ma5 <= near_ma_pct / 100 if current_ma5 > 0 else False
        near_ma10 = abs(current_close - current_ma10) / current_ma10 <= near_ma_pct / 100 if current_ma10 > 0 else False

        if near_ma5 or near_ma10:
            return {
                'signal': 'buy_point',
                'name': '注意买点',
                'color': '#ff1744',
                'desc': '5日金叉20日后回踩均线'
            }
        return None

    def _check_low_5k(self, lows, ma5):
        """标签9：低价5k - 最低价距离MA5"""
        if len(lows) < 5:
            return None

        if not self._is_signal_enabled('low_5k'):
            return None
        params = self._get_signal_params('low_5k')
        diff_min = params.get('diff_min', 0.03)
        diff_max = params.get('diff_max', 0.3)

        current_low = lows[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else None
        if current_ma5 is None:
            return None
        diff = current_low - current_ma5
        if diff_min < diff < diff_max:
            return {
                'signal': 'low_5k',
                'name': '低价5k',
                'color': '#69f0ae',
                'desc': f'最低价{current_low:.2f}距MA5({current_ma5:.2f}){diff:.2f}元'
            }
        return None

    def _check_low_9k(self, lows, ma9):
        """标签10：低价9k - 最低价距离MA9"""
        if len(lows) < 9:
            return None

        if not self._is_signal_enabled('low_9k'):
            return None
        params = self._get_signal_params('low_9k')
        diff_min = params.get('diff_min', 0.1)
        diff_max = params.get('diff_max', 0.4)

        current_low = lows[-1]
        current_ma9 = ma9.iloc[-1] if not pd.isna(ma9.iloc[-1]) else None
        if current_ma9 is None:
            return None
        diff = current_low - current_ma9
        if diff_min < diff < diff_max:
            return {
                'signal': 'low_9k',
                'name': '低价9k',
                'color': '#69f0ae',
                'desc': f'最低价{current_low:.2f}距MA9({current_ma9:.2f}){diff:.2f}元'
            }
        return None

    def _check_close_5k(self, closes, ma5):
        """标签11：收盘5k - 收盘价距离MA5"""
        if len(closes) < 5:
            return None

        if not self._is_signal_enabled('close_5k'):
            return None
        params = self._get_signal_params('close_5k')
        diff_min = params.get('diff_min', -0.5)
        diff_max = params.get('diff_max', -0.1)

        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else None
        if current_ma5 is None:
            return None
        diff = current_close - current_ma5
        if diff_min < diff < diff_max:
            return {
                'signal': 'close_5k',
                'name': '收盘5k',
                'color': '#40c4ff',
                'desc': f'收盘价{current_close:.2f}距MA5({current_ma5:.2f}){diff:.2f}元'
            }
        return None

    def _check_close_9k(self, closes, ma9):
        """标签12：收盘9k - 收盘价距离MA9"""
        if len(closes) < 9:
            return None

        if not self._is_signal_enabled('close_9k'):
            return None
        params = self._get_signal_params('close_9k')
        diff_min = params.get('diff_min', -0.3)
        diff_max = params.get('diff_max', 0.01)

        current_close = closes[-1]
        current_ma9 = ma9.iloc[-1] if not pd.isna(ma9.iloc[-1]) else None
        if current_ma9 is None:
            return None
        diff = current_close - current_ma9
        if diff_min < diff < diff_max:
            return {
                'signal': 'close_9k',
                'name': '收盘9k',
                'color': '#40c4ff',
                'desc': f'收盘价{current_close:.2f}距MA9({current_ma9:.2f}){diff:.2f}元'
            }
        return None

    def _check_59_line(self, opens, closes, lows, volumes, ma5, ma9, turnover=0):
        """标签13：59线 - 连续温和调整+放量+一阳穿五九均线"""
        if len(closes) < 7 or len(volumes) < 6:
            return None

        if not self._is_signal_enabled('line_59'):
            return None
        params = self._get_signal_params('line_59')
        adjust_days = params.get('adjust_days', 2)
        mild_drop_max = params.get('mild_drop_max', 0.5)
        turnover_min = params.get('turnover_min', 0.4)
        turnover_max = params.get('turnover_max', 2.7)

        current_close = closes[-1]
        current_open = opens[-1]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else None
        current_ma9 = ma9.iloc[-1] if not pd.isna(ma9.iloc[-1]) else None

        if current_ma5 is None or current_ma9 is None:
            return None

        # 条件4：一阳上穿MA5和MA9（阳线，收盘价>MA5且>MA9）
        is_yang = current_close > current_open
        cross_ma5 = current_close > current_ma5
        cross_ma9 = current_close > current_ma9
        if not (is_yang and cross_ma5 and cross_ma9):
            return None

        # 条件1：连续N个交易日温和调整（跌幅≤mild_drop_max元）
        mild_adjust = True
        for i in range(-adjust_days - 1, -1):
            if abs(i) >= len(closes):
                mild_adjust = False
                break
            daily_change = closes[i] - closes[i - 1]
            if daily_change < -mild_drop_max:
                mild_adjust = False
                break
        if not mild_adjust:
            return None

        # 条件2：今日成交量 > 昨日 或 > 前4天中任一天
        current_vol = volumes[-1]
        vol_increase = False
        if current_vol > volumes[-2]:
            vol_increase = True
        else:
            for i in range(-5, -1):
                if abs(i) < len(volumes) and current_vol > volumes[i]:
                    vol_increase = True
                    break
        if not vol_increase:
            return None

        # 条件3：换手率范围（仅当turnover>0时检查）
        if turnover > 0 and not (turnover_min <= turnover <= turnover_max):
            return None

        turnover_text = f'换手{turnover:.1f}%' if turnover > 0 else '换手未提供'
        return {
            'signal': 'line_59',
            'name': '59线',
            'color': '#ffab40',
            'desc': f'连续温和调整后一阳穿MA5/MA9，放量，{turnover_text}'
        }

    def _check_parallel_5(self, closes, ma5):
        """标签14：平行5 - 次日回踩MA5附近"""
        if len(closes) < 3:
            return None

        if not self._is_signal_enabled('parallel_5'):
            return None
        params = self._get_signal_params('parallel_5')
        dist_min = params.get('dist_min', -0.1)
        dist_max = params.get('dist_max', 0.1)

        current_close = closes[-1]
        prev_close = closes[-2]
        current_ma5 = ma5.iloc[-1] if not pd.isna(ma5.iloc[-1]) else None

        if current_ma5 is None:
            return None

        # 条件1：小幅回调（前一天收盘价 > 今日收盘价）
        if not (prev_close > current_close):
            return None

        # 条件2：收盘价接近MA5
        diff = current_close - current_ma5
        if dist_min <= diff <= dist_max:
            return {
                'signal': 'parallel_5',
                'name': '平行5',
                'color': '#b388ff',
                'desc': f'回调后收盘{current_close:.2f}平行MA5({current_ma5:.2f})，差{diff:.2f}元'
            }
        return None

    def _check_buy_confirm(self, closes, lows):
        """标签15：买入 - 长下影线后次日确认上涨且未破前低"""
        if len(closes) < 3 or len(lows) < 3:
            return None

        if not self._is_signal_enabled('buy_confirm'):
            return None
        params = self._get_signal_params('buy_confirm')
        lower_shadow_min = params.get('lower_shadow_min', 0.3)

        prev_close = closes[-2]
        prev_low = lows[-2]
        current_close = closes[-1]
        current_low = lows[-1]

        # 条件1：前一天长下影线
        lower_shadow = prev_close - prev_low
        if lower_shadow <= lower_shadow_min:
            return None

        # 条件2：今日收盘价 > 前一天收盘价
        if not (current_close > prev_close):
            return None

        # 条件3：今日最低价 >= 前一天最低价（未破前低）
        if current_low < prev_low:
            return None

        return {
            'signal': 'buy_confirm',
            'name': '买入',
            'color': '#00e676',
            'desc': f'前日长下影{lower_shadow:.2f}元，今收{current_close:.2f}>{prev_close:.2f}且未破前低{prev_low:.2f}'
        }


# 单例
_scanner = None


def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = KlineScanner()
    return _scanner


if __name__ == '__main__':
    # 测试
    print("K线形态扫描引擎测试")
    scanner = KlineScanner()
    print(f"支持信号: {list(scanner.SIGNALS.keys())}")
