"""
AI量化选股策略识别引擎 V最新版
11个信号模型 + AI综合评分
所有参数后台可调整
"""
import numpy as np
from utils.indicators import calc_kdj_series, calc_macd_series, calc_ma_series


class SignalConfig:
    """信号参数配置（可调整）"""
    # 放量下跌筑底
    BUILDUP_LOOKBACK = 10          # 回看天数
    BUILDUP_VOL_RATIO = 1.5        # 放量倍数
    BUILDUP_MA5_DISTANCE = 1.0     # 距离MA5最大差值（元）
    BUILDUP_OSCILLATE_DAYS = 3     # 横盘天数

    # 均线锐角
    ANGLE_MIN_DIFF = 0.1           # MA20-MA5最小差值
    ANGLE_MAX_DIFF = 1.0           # MA20-MA5最大差值

    # 5日线贴合
    FIT_MIN_DIFF = 0.1             # 收盘价-MA5最小差值
    FIT_MAX_DIFF = 1.0             # 收盘价-MA5最大差值

    # 阳线突破
    BREAKOUT_MIN_PCT = 3.0         # 大阳线最小涨幅

    # 倍量
    DOUBLE_VOL_RATIO = 2.0         # 倍量倍数

    # 大阳回踩
    PULLBACK_LOOKBACK = 20         # 回看天数
    PULLBACK_MIN_PCT = 3.0         # 大阳最小涨幅
    PULLBACK_MAX_PCT = 7.0         # 大阳最大涨幅

    # KDJ参数
    KDJ_N = 13
    KDJ_M1 = 3
    KDJ_M2 = 3
    KDJ_J_NEG = -30                # 负J阈值
    KDJ_J_LOW = 8                  # J低位阈值
    KDJ_K_LOW = 15                 # K低位阈值
    KDJ_GOLDEN_LOW = 40            # 金叉区域下限
    KDJ_GOLDEN_HIGH = 60           # 金叉区域上限

    # MACD参数
    MACD_FAST = 8
    MACD_SLOW = 21
    MACD_SIGNAL = 5
    MACD_AXIS_LOW = -0.020         # 轴下金叉阈值
    MACD_AXIS_HIGH = 0.400         # 轴上金叉阈值


class AISignalEngine:
    """AI信号识别引擎"""

    def __init__(self, config=None):
        self.config = config or SignalConfig()

    def analyze(self, daily_data, stock_info=None):
        """
        分析股票，返回所有信号
        daily_data: 日线数据列表，每条含 open/close/high/low/volume
        返回: {'signals': [], 'scores': {}, 'total_score': 0, 'rating': ''}
        """
        if not daily_data or len(daily_data) < 30:
            return {'signals': [], 'scores': {}, 'total_score': 0, 'rating': '数据不足'}

        result = {
            'signals': [],
            'scores': {},
            'total_score': 0,
            'rating': '',
            'analysis': '',
        }

        closes = [d['close'] for d in daily_data]
        highs = [d['high'] for d in daily_data]
        lows = [d['low'] for d in daily_data]
        volumes = [d.get('volume', d.get('vol', 0)) for d in daily_data]

        # 计算均线
        ma5 = calc_ma_series(closes, 5)
        ma10 = calc_ma_series(closes, 10)
        ma20 = calc_ma_series(closes, 20)

        # 计算KDJ
        k_vals, d_vals, j_vals = calc_kdj_series(highs, lows, closes, self.config.KDJ_N, self.config.KDJ_M1, self.config.KDJ_M2)

        # 计算MACD
        dif, dea, macd_hist = calc_macd_series(closes, self.config.MACD_FAST, self.config.MACD_SLOW, self.config.MACD_SIGNAL)

        # 1. 放量下跌筑底模型
        sig = self._check_buildup(daily_data, closes, volumes, ma5)
        if sig:
            result['signals'].append(sig)
            result['scores']['buildup'] = 12

        # 2. 均线锐角模型
        sig = self._check_angle(ma5, ma20)
        if sig:
            result['signals'].append(sig)
            result['scores']['angle'] = 10

        # 3. 5日线贴合突破模型
        sig = self._check_ma5_fit(closes, ma5)
        if sig:
            result['signals'].append(sig)
            result['scores']['ma5_fit'] = 10

        # 4. 阳线突破模型
        sig = self._check_breakout(closes, ma5, ma10, ma20)
        if sig:
            result['signals'].append(sig)
            result['scores']['breakout'] = 12

        # 5. 倍量突破
        sig = self._check_double_volume(closes, volumes)
        if sig:
            result['signals'].append(sig)
            result['scores']['double_vol'] = 10

        # 6. 大阳回踩
        sig = self._check_pullback(daily_data, closes, volumes)
        if sig:
            result['signals'].append(sig)
            result['scores']['pullback'] = 10

        # 7. 均线买点
        sig = self._check_ma_buy(ma5, ma10, ma20, closes)
        if sig:
            result['signals'].append(sig)
            result['scores']['ma_buy'] = 12

        # 8. 主升回踩完整模型
        sig = self._check_main_rise(daily_data, closes, volumes, ma5, ma10)
        if sig:
            result['signals'].append(sig)
            result['scores']['main_rise'] = 15

        # 9. KDJ信号
        kdj_sigs = self._check_kdj(k_vals, d_vals, j_vals)
        result['signals'].extend(kdj_sigs)
        result['scores']['kdj'] = len(kdj_sigs) * 5

        # 10. MACD信号
        macd_sigs = self._check_macd(dif, dea, macd_hist)
        result['signals'].extend(macd_sigs)
        result['scores']['macd'] = len(macd_sigs) * 5

        # 计算总分
        total = sum(result['scores'].values())
        result['total_score'] = min(100, total)

        # 评级
        if total >= 90:
            result['rating'] = '强势买点'
        elif total >= 75:
            result['rating'] = '重点观察'
        elif total >= 60:
            result['rating'] = '等待确认'
        else:
            result['rating'] = '放弃'

        # 生成分析理由
        result['analysis'] = self._generate_analysis(result)

        return result

    def _check_buildup(self, daily_data, closes, volumes, ma5):
        """1. 放量下跌筑底模型"""
        cfg = self.config
        n = len(daily_data)
        if n < cfg.BUILDUP_LOOKBACK + cfg.BUILDUP_OSCILLATE_DAYS:
            return None

        # 最近10天内找放量下跌且跌破MA5
        lookback = daily_data[-cfg.BUILDUP_LOOKBACK:]
        has_volume_drop = False
        for i in range(1, len(lookback)):
            # 放量（成交量大于前日1.5倍）+ 阴线（下跌）
            if (lookback[i]['volume'] > lookback[i-1]['volume'] * cfg.BUILDUP_VOL_RATIO
                    and lookback[i]['close'] < lookback[i]['open']):
                # 跌破MA5
                ma5_val = ma5.iloc[-cfg.BUILDUP_LOOKBACK + i] if hasattr(ma5, 'iloc') else ma5[-cfg.BUILDUP_LOOKBACK + i]
                if lookback[i]['close'] < ma5_val:
                    has_volume_drop = True
                    break

        if not has_volume_drop:
            return None

        # 当前收盘价接近MA5（差价1元以内）
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        if abs(current_close - current_ma5) > cfg.BUILDUP_MA5_DISTANCE:
            return None

        # 连续≥3天在MA5附近震荡（差价1元以内）
        oscillate = True
        for i in range(-cfg.BUILDUP_OSCILLATE_DAYS, 0):
            c = closes[i]
            m = ma5.iloc[i] if hasattr(ma5, 'iloc') else ma5[i]
            if abs(c - m) > cfg.BUILDUP_MA5_DISTANCE:
                oscillate = False
                break

        if not oscillate:
            return None

        return {
            'type': 'buildup',
            'name': '横盘筑底',
            'color': '#00e676',
            'reason': f'10日内放量下跌跌破MA5，随后股价在MA5({current_ma5:.2f})附近横盘{cfg.BUILDUP_OSCILLATE_DAYS}天，当前价{current_close:.2f}，差价{abs(current_close-current_ma5):.2f}元',
        }

    def _check_angle(self, ma5, ma20):
        """2. 均线锐角模型"""
        cfg = self.config
        if len(ma5) < 5 or len(ma20) < 5:
            return None

        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        current_ma20 = ma20.iloc[-1] if hasattr(ma20, 'iloc') else ma20[-1]
        prev_ma5 = ma5.iloc[-2] if hasattr(ma5, 'iloc') else ma5[-2]

        # MA20 > MA5
        if current_ma20 <= current_ma5:
            return None

        diff = current_ma20 - current_ma5
        if not (cfg.ANGLE_MIN_DIFF <= diff <= cfg.ANGLE_MAX_DIFF):
            return None

        # MA5向上拐头
        if current_ma5 <= prev_ma5:
            return None

        return {
            'type': 'angle',
            'name': '锐角',
            'color': '#d500f9',
            'reason': f'MA20({current_ma20:.2f}) > MA5({current_ma5:.2f})，差值{diff:.2f}元，MA5开始向上拐头',
        }

    def _check_ma5_fit(self, closes, ma5):
        """3. 5日线贴合突破模型"""
        cfg = self.config
        if len(closes) < 4 or len(ma5) < 4:
            return None

        # 前两日收盘价一天比一天低（连续下跌）
        if not (closes[-3] > closes[-2]):
            return None

        # 前两日跌破MA5
        prev2_close = closes[-3]
        prev2_ma5 = ma5.iloc[-3] if hasattr(ma5, 'iloc') else ma5[-3]
        prev_close = closes[-2]
        prev_ma5 = ma5.iloc[-2] if hasattr(ma5, 'iloc') else ma5[-2]

        if prev2_close >= prev2_ma5 or prev_close >= prev_ma5:
            return None

        # 今日重新靠近MA5（收盘价在MA5上方0.1-1元）
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        diff = current_close - current_ma5
        if not (cfg.FIT_MIN_DIFF <= diff <= cfg.FIT_MAX_DIFF):
            return None

        return {
            'type': 'ma5_fit',
            'name': '五日线',
            'color': '#58a6ff',
            'reason': f'前两日连续下跌跌破MA5，今日收盘价{current_close:.2f}贴合MA5({current_ma5:.2f})上方，差值{diff:.2f}元',
        }

    def _check_breakout(self, closes, ma5, ma10, ma20):
        """4. 阳线突破模型"""
        cfg = self.config
        if len(closes) < 2:
            return None

        current_close = closes[-1]
        prev_close = closes[-2]
        pct = (current_close - prev_close) / prev_close * 100

        # 大阳线
        if pct < cfg.BREAKOUT_MIN_PCT:
            return None

        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        current_ma10 = ma10.iloc[-1] if hasattr(ma10, 'iloc') else ma10[-1]
        current_ma20 = ma20.iloc[-1] if hasattr(ma20, 'iloc') else ma20[-1]

        # 一阳穿三线
        if current_close > current_ma5 and current_close > current_ma10 and current_close > current_ma20:
            return {
                'type': 'breakout_three',
                'name': '一阳穿三线',
                'color': '#ff1744',
                'reason': f'大阳线涨幅{pct:.2f}%，收盘价{current_close:.2f}同时突破MA5({current_ma5:.2f})、MA10({current_ma10:.2f})、MA20({current_ma20:.2f})',
            }

        # 一阳穿5/10日线
        if current_close > current_ma5 and current_close > current_ma10:
            return {
                'type': 'breakout_two',
                'name': '一阳5/10日线',
                'color': '#ff9100',
                'reason': f'大阳线涨幅{pct:.2f}%，收盘价{current_close:.2f}突破MA5({current_ma5:.2f})和MA10({current_ma10:.2f})',
            }

        return None

    def _check_double_volume(self, closes, volumes):
        """5. 倍量突破"""
        cfg = self.config
        if len(volumes) < 2:
            return None

        current_vol = volumes[-1]
        prev_vol = volumes[-2]
        current_close = closes[-1]
        prev_close = closes[-2]

        # 大阳线（涨幅≥3%）+ 倍量
        pct = (current_close - prev_close) / prev_close * 100
        if pct < cfg.BREAKOUT_MIN_PCT:
            return None

        if current_vol < prev_vol * cfg.DOUBLE_VOL_RATIO:
            return None

        ratio = current_vol / prev_vol if prev_vol > 0 else 0
        return {
            'type': 'double_volume',
            'name': '倍量',
            'color': '#ffea00',
            'reason': f'大阳线涨幅{pct:.2f}%，成交量{current_vol:.0f}是前日{prev_vol:.0f}的{ratio:.1f}倍',
        }

    def _check_pullback(self, daily_data, closes, volumes):
        """6. 大阳回踩"""
        cfg = self.config
        n = len(daily_data)
        if n < cfg.PULLBACK_LOOKBACK:
            return None

        # 过去20天找放量大阳线
        lookback = daily_data[-cfg.PULLBACK_LOOKBACK:]
        big_yang = None
        big_yang_idx = -1

        for i, d in enumerate(lookback):
            if i == 0:
                continue
            pct = (d['close'] - lookback[i-1]['close']) / lookback[i-1]['close'] * 100
            if cfg.PULLBACK_MIN_PCT <= pct <= cfg.PULLBACK_MAX_PCT:
                if d['volume'] > lookback[i-1]['volume'] * 1.5:
                    big_yang = d
                    big_yang_idx = i

        if big_yang is None:
            return None

        # 当前价格回踩大阳线收盘价附近
        current_close = closes[-1]
        big_close = big_yang['close']
        distance = abs(current_close - big_close) / big_close * 100

        if distance > 3:  # 3%以内算回踩
            return None

        return {
            'type': 'pullback',
            'name': '回踩',
            'color': '#00e5ff',
            'reason': f'20日内出现放量大阳(收盘价{big_close:.2f})，当前价{current_close:.2f}回踩大阳收盘价附近，偏差{distance:.1f}%',
        }

    def _check_ma_buy(self, ma5, ma10, ma20, closes):
        """7. 均线买点模型"""
        if len(ma5) < 5 or len(ma20) < 5:
            return None

        # 检查MA5是否上穿MA20
        ma5_cross_ma20 = False
        cross_idx = -1
        for i in range(-5, 0):
            prev_ma5 = ma5.iloc[i-1] if hasattr(ma5, 'iloc') else ma5[i-1]
            prev_ma20 = ma20.iloc[i-1] if hasattr(ma20, 'iloc') else ma20[i-1]
            curr_ma5 = ma5.iloc[i] if hasattr(ma5, 'iloc') else ma5[i]
            curr_ma20 = ma20.iloc[i] if hasattr(ma20, 'iloc') else ma20[i]
            if prev_ma5 <= prev_ma20 and curr_ma5 > curr_ma20:
                ma5_cross_ma20 = True
                cross_idx = i
                break

        if not ma5_cross_ma20:
            return None

        # 之后回踩MA5或MA10
        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        current_ma10 = ma10.iloc[-1] if hasattr(ma10, 'iloc') else ma10[-1]

        near_ma5 = abs(current_close - current_ma5) / current_ma5 * 100 < 2
        near_ma10 = abs(current_close - current_ma10) / current_ma10 * 100 < 2

        if not (near_ma5 or near_ma10):
            return None

        return {
            'type': 'ma_buy',
            'name': '注意买点',
            'color': '#ff1744',
            'reason': f'MA5上穿MA20后回踩，当前价{current_close:.2f}接近MA5({current_ma5:.2f})或MA10({current_ma10:.2f})',
        }

    def _check_main_rise(self, daily_data, closes, volumes, ma5, ma10):
        """8. 主升回踩完整交易模型（重点）"""
        n = len(daily_data)
        if n < 20:
            return None

        current_close = closes[-1]
        current_ma5 = ma5.iloc[-1] if hasattr(ma5, 'iloc') else ma5[-1]
        current_ma10 = ma10.iloc[-1] if hasattr(ma10, 'iloc') else ma10[-1]

        # 第三阶段（当前）：放量阳线突破MA5和MA10
        if not (current_close > current_ma5 and current_close > current_ma10):
            return None
        if volumes[-1] <= volumes[-2]:
            return None
        if current_close <= closes[-2]:
            return None

        # 第二阶段：之前出现放量阳线站上MA5，随后缩量回踩
        # 寻找放量阳线（成交量大于前两日）
        has_vol_yang = False
        yang_low = 0
        yang_idx = -1

        # 在最近3-8天内找放量阳线
        for i in range(-8, -2):
            if (volumes[i] > volumes[i-1] and volumes[i] > volumes[i-2] and
                    closes[i] > closes[i-1]):
                c = closes[i]
                m = ma5.iloc[i] if hasattr(ma5, 'iloc') else ma5[i]
                if c > m:  # 站上MA5
                    has_vol_yang = True
                    yang_low = daily_data[i]['low']
                    yang_idx = i
                    break

        if not has_vol_yang:
            return None

        # 回踩阶段：放量阳之后到当前，股价缩量调整
        # 检查回踩期间没有跌破放量阳线最低价
        for i in range(yang_idx + 1, 0):
            if closes[i] < yang_low:
                return None
            # 缩量（成交量小于放量阳线当天）
            if volumes[i] > volumes[yang_idx]:
                return None

        # 第一阶段：放量阳线之前，股价在MA5下方调整并贴近MA5
        # 检查放量阳线前几天，股价在MA5下方且逐渐贴近
        first_stage_ok = False
        for i in range(yang_idx - 5, yang_idx):
            if i < -n:
                continue
            c = closes[i]
            m = ma5.iloc[i] if hasattr(ma5, 'iloc') else ma5[i]
            # 股价在MA5下方，且距离MA5在1元以内
            if c < m and abs(c - m) <= 1.0:
                first_stage_ok = True
                break

        if not first_stage_ok:
            return None

        return {
            'type': 'main_rise',
            'name': '买点',
            'color': '#ff1744',
            'reason': f'主升回踩完整形态：MA5下方调整贴近均线(差价≤1元)→放量阳站上MA5(最低价{yang_low:.2f})→缩量回踩不破低点→再次放量突破MA5({current_ma5:.2f})和MA10({current_ma10:.2f})',
        }

    def _check_kdj(self, k_vals, d_vals, j_vals):
        """9. KDJ智能提醒"""
        cfg = self.config
        signals = []

        if len(k_vals) == 0 or len(d_vals) == 0 or len(j_vals) == 0:
            return signals

        current_k = float(k_vals.iloc[-1]) if hasattr(k_vals, 'iloc') else k_vals[-1]
        current_d = float(d_vals.iloc[-1]) if hasattr(d_vals, 'iloc') else d_vals[-1]
        current_j = float(j_vals.iloc[-1]) if hasattr(j_vals, 'iloc') else j_vals[-1]

        # 负J
        if current_j <= cfg.KDJ_J_NEG or current_j < cfg.KDJ_J_LOW:
            signals.append({
                'type': 'kdj_neg_j',
                'name': '负J',
                'color': '#00e676',
                'reason': f'KDJ的J值={current_j:.1f}，超跌关注',
            })

        # J穿K（即将上穿）
        if len(j_vals) >= 2 and len(k_vals) >= 2:
            prev_j = float(j_vals.iloc[-2]) if hasattr(j_vals, 'iloc') else j_vals[-2]
            prev_k = float(k_vals.iloc[-2]) if hasattr(k_vals, 'iloc') else k_vals[-2]
            jk_diff = current_j - current_k
            prev_jk_diff = prev_j - prev_k
            if prev_jk_diff < 0 and 1 <= jk_diff <= 3:
                signals.append({
                    'type': 'kdj_j_cross_k',
                    'name': '穿K',
                    'color': '#58a6ff',
                    'reason': f'J值({current_j:.1f})即将上穿K值({current_k:.1f})，差值{jk_diff:.1f}',
                })

        # 15K
        if current_k <= cfg.KDJ_K_LOW:
            signals.append({
                'type': 'kdj_15k',
                'name': '15K',
                'color': '#d500f9',
                'reason': f'KDJ的K值={current_k:.1f}，处于超卖区域',
            })

        # 50附近金叉
        if len(k_vals) >= 2 and len(d_vals) >= 2:
            prev_k = float(k_vals.iloc[-2]) if hasattr(k_vals, 'iloc') else k_vals[-2]
            prev_d = float(d_vals.iloc[-2]) if hasattr(d_vals, 'iloc') else d_vals[-2]
            if (cfg.KDJ_GOLDEN_LOW <= current_k <= cfg.KDJ_GOLDEN_HIGH and
                    cfg.KDJ_GOLDEN_LOW <= current_d <= cfg.KDJ_GOLDEN_HIGH and
                    prev_k <= prev_d and current_k > current_d):
                signals.append({
                    'type': 'kdj_golden',
                    'name': 'KDJ金叉',
                    'color': '#ff1744',
                    'reason': f'KDJ在40-60区域金叉，K={current_k:.1f}, D={current_d:.1f}',
                })

        return signals

    def _check_macd(self, dif, dea, macd_hist):
        """10. MACD智能提醒"""
        cfg = self.config
        signals = []

        if len(dif) == 0 or len(dea) == 0 or len(macd_hist) == 0:
            return signals

        current_dif = float(dif.iloc[-1]) if hasattr(dif, 'iloc') else dif[-1]
        current_dea = float(dea.iloc[-1]) if hasattr(dea, 'iloc') else dea[-1]
        current_macd = float(macd_hist.iloc[-1]) if hasattr(macd_hist, 'iloc') else macd_hist[-1]

        # 轴下金叉
        if len(dif) >= 2 and len(dea) >= 2:
            prev_dif = float(dif.iloc[-2]) if hasattr(dif, 'iloc') else dif[-2]
            prev_dea = float(dea.iloc[-2]) if hasattr(dea, 'iloc') else dea[-2]
            if (current_macd <= cfg.MACD_AXIS_LOW and
                    prev_dif <= prev_dea and current_dif > current_dea):
                # 绿柱持续缩短
                if len(macd_hist) >= 3:
                    prev_macd2 = float(macd_hist.iloc[-3]) if hasattr(macd_hist, 'iloc') else macd_hist[-3]
                    prev_macd1 = float(macd_hist.iloc[-2]) if hasattr(macd_hist, 'iloc') else macd_hist[-2]
                    if prev_macd2 < prev_macd1 < current_macd:
                        signals.append({
                            'type': 'macd_axis_low_golden',
                            'name': '轴下金叉',
                            'color': '#00e676',
                            'reason': f'MACD={current_macd:.3f}≤-0.020，绿柱缩短后金叉，DIF={current_dif:.3f}, DEA={current_dea:.3f}',
                        })

        # 轴上金叉
        if len(dif) >= 2 and len(dea) >= 2:
            prev_dif = float(dif.iloc[-2]) if hasattr(dif, 'iloc') else dif[-2]
            prev_dea = float(dea.iloc[-2]) if hasattr(dea, 'iloc') else dea[-2]
            if (current_macd >= cfg.MACD_AXIS_HIGH and
                    prev_dif <= prev_dea and current_dif > current_dea):
                # 红柱缩短后再次金叉
                if len(macd_hist) >= 3:
                    prev_macd2 = float(macd_hist.iloc[-3]) if hasattr(macd_hist, 'iloc') else macd_hist[-3]
                    prev_macd1 = float(macd_hist.iloc[-2]) if hasattr(macd_hist, 'iloc') else macd_hist[-2]
                    if prev_macd2 > prev_macd1:
                        signals.append({
                            'type': 'macd_axis_high_golden',
                            'name': '轴上金叉',
                            'color': '#ff1744',
                            'reason': f'MACD={current_macd:.3f}≥0.400，红柱缩短后再次金叉，DIF={current_dif:.3f}, DEA={current_dea:.3f}',
                        })

        return signals

    def _generate_analysis(self, result):
        """生成AI分析理由"""
        if not result['signals']:
            return '未发现明显买入信号，建议观望。'

        parts = []
        for sig in result['signals']:
            parts.append(f"【{sig['name']}】{sig['reason']}")

        risk = self._get_risk_warning(result)
        if risk:
            parts.append(f"风险提示：{risk}")

        return '\n'.join(parts)

    def _get_risk_warning(self, result):
        """生成买入风险提示"""
        warnings = []
        total = result['total_score']

        if total < 60:
            warnings.append('综合评分较低，信号不足')
        if total >= 60 and total < 75:
            warnings.append('信号确认中，建议等待更明确买点')

        # 检查是否只有单一信号
        if len(result['signals']) == 1:
            warnings.append('仅单一信号，建议结合其他指标确认')

        return '；'.join(warnings) if warnings else ''
