# -*- coding: utf-8 -*-
"""
振幅行为模型 V1.0（STR-V3-002）
振幅=(最高价-最低价)/前收盘价×100%

五种形态：
1. 【振幅收缩】：今日振幅<5日平均振幅×0.75，且5日平均振幅正在下降
2. 【低位振幅抢筹】：距离20日低点<=10%+今日振幅>6%+今日阳线+成交量>5日均量×1.5+收盘位于当日振幅上方70%
3. 【振幅突破】：前5日平均振幅持续下降+今日振幅突然扩大+今日成交量放大+今日收盘>前5日最高价
4. 【高位放量巨震】（风险）：距离20日高点<=5%+振幅>8%+成交量>2倍+长上影或收盘明显弱
5. 【振幅陷阱】（风险）：突然放大振幅+成交量巨大+收盘接近最低位

评分100分：收缩10+低位15+缩量回调15+放量突破20+收盘强度10+量价关系10+20日趋势10+板块共振10
"""
import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class AmplitudeBehaviorStrategy:
    """振幅行为模型 V1.0"""

    STRATEGY_NAME = "振幅行为模型"
    STRATEGY_ID = "STR-V3-002"
    SIGNAL_SOURCE_TAG = "振幅行为"

    def __init__(self):
        self._scan_logs = []

    def _log(self, msg: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] [振幅模型] {msg}"
        self._scan_logs.append(log_msg)
        print(log_msg, flush=True)

    def calc_amplitude(self, kline: List[Dict]) -> List[float]:
        """计算每日振幅=(high-low)/pre_close×100%"""
        amplitudes = []
        for i in range(len(kline)):
            if i == 0:
                amplitudes.append(0.0)
            else:
                pre_close = float(kline[i - 1].get('close', 0))
                high = float(kline[i].get('high', 0))
                low = float(kline[i].get('low', 0))
                if pre_close > 0:
                    amplitudes.append((high - low) / pre_close * 100)
                else:
                    amplitudes.append(0.0)
        return amplitudes

    def calc_ma(self, values: List[float], period: int) -> List[float]:
        """计算移动平均"""
        result = []
        for i in range(len(values)):
            if i < period - 1:
                result.append(0.0)
            else:
                result.append(sum(values[i - period + 1:i + 1]) / period)
        return result

    def calc_pct_changes(self, kline: List[Dict]) -> List[float]:
        """计算每日涨跌幅"""
        pcts = []
        for i in range(len(kline)):
            if i == 0:
                pcts.append(0.0)
            else:
                prev_close = float(kline[i - 1].get('close', 0))
                curr_close = float(kline[i].get('close', 0))
                if prev_close > 0:
                    pcts.append((curr_close - prev_close) / prev_close)
                else:
                    pcts.append(0.0)
        return pcts

    def run_single_stock(self, kline: List[Dict], stock_code: str, stock_name: str,
                          sector_data: Optional[Dict] = None, verbose: bool = False) -> Optional[Dict]:
        """
        单只股票振幅行为计算。

        Returns:
            信号字典或None
        """
        if not kline or len(kline) < 25:
            if verbose:
                self._log(f"{stock_code} {stock_name} 跳过：K线不足25根")
            return None

        # 基础数据
        closes = [float(k.get('close', 0)) for k in kline]
        volumes = [float(k.get('volume', 0)) for k in kline]
        highs = [float(k.get('high', 0)) for k in kline]
        lows = [float(k.get('low', 0)) for k in kline]
        opens = [float(k.get('open', 0)) for k in kline]
        pcts = self.calc_pct_changes(kline)
        amplitudes = self.calc_amplitude(kline)

        # 均线
        ma5 = self.calc_ma(closes, 5)
        ma10 = self.calc_ma(closes, 10)
        ma20 = self.calc_ma(closes, 20)
        amp_ma5 = self.calc_ma(amplitudes, 5)
        amp_ma10 = self.calc_ma(amplitudes, 10)

        # 当前日
        t0_close = closes[-1]
        t0_open = opens[-1]
        t0_high = highs[-1]
        t0_low = lows[-1]
        t0_volume = volumes[-1]
        t0_pct = pcts[-1]
        t0_amplitude = amplitudes[-1]
        t0_amp_ma5 = amp_ma5[-1]
        t0_amp_ma10 = amp_ma10[-1]
        t0_ma5 = ma5[-1]
        t0_ma20 = ma20[-1]

        # 前5日振幅均值（不含今日）
        prev_5_amp = amplitudes[-6:-1] if len(amplitudes) >= 6 else amplitudes[:-1]
        prev_5_amp_avg = sum(prev_5_amp) / len(prev_5_amp) if prev_5_amp else 0

        # 前5日最高价
        prev_5_high = max(highs[-6:-1]) if len(highs) >= 6 else max(highs[:-1])

        # 20日高低点
        last_20_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        last_20_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)

        # 距离20日高低点
        dist_from_20_high = (last_20_high - t0_close) / last_20_high * 100 if last_20_high > 0 else 0
        dist_from_20_low = (t0_close - last_20_low) / last_20_low * 100 if last_20_low > 0 else 0

        # 5日均量（不含今日）
        vol_5ma = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else 0
        vol_multiple = t0_volume / vol_5ma if vol_5ma > 0 else 0

        # 收盘位置（0-1，0=最低，1=最高）
        close_position = (t0_close - t0_low) / (t0_high - t0_low) if (t0_high - t0_low) > 0 else 0.5

        # 上影线比例
        upper_shadow = (t0_high - max(t0_open, t0_close)) / (t0_high - t0_low) if (t0_high - t0_low) > 0 else 0

        # ===== 形态识别 =====
        patterns = []
        is_risk = False

        # 形态1：振幅收缩
        amp_shrink = False
        if t0_amplitude < t0_amp_ma5 * 0.75 and t0_amp_ma5 < amp_ma5[-6] * 0.9 if len(amp_ma5) >= 6 else False:
            amp_shrink = True
            patterns.append("振幅收缩")

        # 形态2：低位振幅抢筹
        low_amp_grab = False
        if (dist_from_20_low <= 10 and t0_amplitude > 6 and t0_close > t0_open and
                vol_multiple > 1.5 and close_position > 0.7):
            low_amp_grab = True
            patterns.append("低位振幅抢筹")

        # 形态3：振幅突破
        amp_breakout = False
        if (prev_5_amp_avg < amp_ma10[-6] * 0.9 if len(amp_ma10) >= 6 else False and
                t0_amplitude > prev_5_amp_avg * 1.5 and vol_multiple > 1.2 and
                t0_close > prev_5_high and t0_close > t0_open):
            amp_breakout = True
            patterns.append("振幅突破")

        # 形态4：高位放量巨震（风险）
        high_vol_shock = False
        if (dist_from_20_high <= 5 and t0_amplitude > 8 and vol_multiple > 2 and
                (upper_shadow > 0.4 or t0_close < t0_open)):
            high_vol_shock = True
            patterns.append("高位放量巨震")
            is_risk = True

        # 形态5：振幅陷阱（风险）
        amp_trap = False
        if (t0_amplitude > prev_5_amp_avg * 2 and vol_multiple > 2.5 and close_position < 0.3):
            amp_trap = True
            patterns.append("振幅陷阱")
            is_risk = True

        if verbose:
            self._log(f"{stock_code} 形态：{patterns}，风险={is_risk}")
            self._log(f"{stock_code} 今日振幅={t0_amplitude:.2f}% 5日均振幅={t0_amp_ma5:.2f}% 前5日均={prev_5_amp_avg:.2f}%")
            self._log(f"{stock_code} 距20日高={dist_from_20_high:.1f}% 距20日低={dist_from_20_low:.1f}% 收盘位置={close_position:.2f}")
            self._log(f"{stock_code} 放量倍数={vol_multiple:.2f} 上影线={upper_shadow:.2f}")

        # 风险形态不产生买入信号
        if is_risk:
            if verbose:
                self._log(f"{stock_code} {stock_name} 风险形态，不产生买入信号")
            return None

        # 无明确形态不触发
        if not patterns:
            if verbose:
                self._log(f"{stock_code} {stock_name} 无明确振幅形态")
            return None

        # ===== 评分（100分）=====
        # 1. 振幅收缩（10分）
        score_shrink = 10 if amp_shrink else 5 if t0_amplitude < t0_amp_ma5 else 0

        # 2. 低位（15分）
        score_low = 0
        if dist_from_20_low <= 5:
            score_low = 15
        elif dist_from_20_low <= 10:
            score_low = 12
        elif dist_from_20_low <= 15:
            score_low = 8
        elif dist_from_20_low <= 20:
            score_low = 4

        # 3. 缩量回调（15分）- 前5日成交量逐步缩小
        score_shrink_vol = 0
        if len(volumes) >= 7:
            v1, v2, v3 = volumes[-4], volumes[-3], volumes[-2]
            if v1 > v2 > v3 and v3 < v1 * 0.7:
                score_shrink_vol = 15
            elif v1 > v2 > v3:
                score_shrink_vol = 10
            elif v3 < v1 * 0.8:
                score_shrink_vol = 5

        # 4. 放量突破（20分）
        score_breakout = 0
        if amp_breakout:
            score_breakout = 20
        elif low_amp_grab:
            score_breakout = 15
        elif t0_close > prev_5_high and vol_multiple > 1.2:
            score_breakout = 12
        elif t0_close > t0_ma5 and vol_multiple > 1.0:
            score_breakout = 6

        # 5. 收盘强度（10分）
        score_close = 0
        if close_position > 0.8:
            score_close = 10
        elif close_position > 0.6:
            score_close = 7
        elif close_position > 0.4:
            score_close = 4
        elif close_position > 0.2:
            score_close = 2

        # 6. 量价关系（10分）
        score_vol_price = 0
        if t0_close > t0_open and vol_multiple > 1.5:
            score_vol_price = 10
        elif t0_close > t0_open and vol_multiple > 1.2:
            score_vol_price = 7
        elif t0_close > t0_open and vol_multiple > 1.0:
            score_vol_price = 4
        elif t0_close > t0_open:
            score_vol_price = 2

        # 7. 20日趋势（10分）
        score_trend = 0
        if t0_ma20 > 0 and len(ma20) >= 6:
            ma20_slope = (t0_ma20 - ma20[-6]) / ma20[-6] * 100 if ma20[-6] > 0 else 0
            if t0_close > t0_ma5 > t0_ma20 and ma20_slope > 0.5:
                score_trend = 10
            elif t0_close > t0_ma20 and ma20_slope > 0:
                score_trend = 7
            elif t0_close > t0_ma20:
                score_trend = 4
            elif t0_close > t0_ma20 * 0.97:
                score_trend = 2

        # 8. 板块共振（10分）
        score_sector = 0
        sector_name = ''
        sector_change = 0.0
        if sector_data:
            sector_name = sector_data.get('sector_name', sector_data.get('name', ''))
            sector_change = sector_data.get('sector_change', sector_data.get('change_pct', 0))
            sector_limit_up = sector_data.get('limit_up_count', 0)
            if sector_change > 2 and sector_limit_up >= 2:
                score_sector = 10
            elif sector_change > 1 and sector_limit_up >= 1:
                score_sector = 7
            elif sector_change > 0.5:
                score_sector = 4
            elif sector_change > 0:
                score_sector = 2

        total_score = (score_shrink + score_low + score_shrink_vol + score_breakout +
                       score_close + score_vol_price + score_trend + score_sector)

        if verbose:
            self._log(f"{stock_code} 评分：收缩{score_shrink}+低位{score_low}+缩量{score_shrink_vol}"
                      f"+突破{score_breakout}+收盘{score_close}+量价{score_vol_price}"
                      f"+趋势{score_trend}+板块{score_sector} = {total_score}/100")

        # 等级
        if total_score >= 75:
            grade = "★★★★强信号"
            grade_level = "S"
        elif total_score >= 65:
            grade = "★★★关注"
            grade_level = "A"
        elif total_score >= 55:
            grade = "★★观察"
            grade_level = "B"
        else:
            return None  # 低于55分不触发

        # 信号标签
        tags = list(patterns)
        if t0_close > t0_ma5:
            tags.append("站上MA5")
        if vol_multiple > 1.5:
            tags.append("放量")
        if t0_close > prev_5_high:
            tags.append("突破5日高")
        if score_trend >= 7:
            tags.append("趋势向上")

        # 风险标签
        risk_tags = []
        if dist_from_20_high < 5:
            risk_tags.append("接近20日高")
        if t0_amplitude > 8:
            risk_tags.append("振幅过大")
        if upper_shadow > 0.4:
            risk_tags.append("上影线明显")

        result = {
            'strategy_id': self.STRATEGY_ID,
            'strategy_name': self.STRATEGY_NAME,
            'signal_source': self.SIGNAL_SOURCE_TAG,
            'stock_code': stock_code,
            'stock_name': stock_name,
            'total_score': total_score,
            'grade': grade,
            'grade_level': grade_level,
            'patterns': patterns,
            'today_pct': round(t0_pct * 100, 2),
            'today_close': round(t0_close, 2),
            'today_open': round(t0_open, 2),
            'today_high': round(t0_high, 2),
            'today_low': round(t0_low, 2),
            'today_amplitude': round(t0_amplitude, 2),
            'amp_ma5': round(t0_amp_ma5, 2),
            'amp_ma10': round(t0_amp_ma10, 2),
            'vol_multiple': round(vol_multiple, 2),
            'close_position': round(close_position, 2),
            'dist_from_20_high': round(dist_from_20_high, 2),
            'dist_from_20_low': round(dist_from_20_low, 2),
            'ma5': round(t0_ma5, 2),
            'ma20': round(t0_ma20, 2),
            'sector_name': sector_name,
            'sector_change': round(sector_change, 2),
            'tags': tags,
            'risk_tags': risk_tags,
            'score_detail': {
                'shrink': score_shrink,
                'low': score_low,
                'shrink_vol': score_shrink_vol,
                'breakout': score_breakout,
                'close': score_close,
                'vol_price': score_vol_price,
                'trend': score_trend,
                'sector': score_sector,
            },
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'kline_date': kline[-1].get('date', ''),
        }

        self._log(f"✅ {stock_code} {stock_name} 振幅信号！{grade} {total_score}分 形态:{','.join(patterns)}")
        return result

    def scan_stock_list(self, stocks: List[Dict], kline_provider, days: int = 60,
                        sector_provider=None, verbose: bool = False) -> List[Dict]:
        """批量扫描"""
        signals = []
        total = len(stocks)
        self._log(f"开始批量扫描，共{total}只股票")

        for i, stock in enumerate(stocks):
            code = stock.get('code', '')
            name = stock.get('name', '')
            if not code:
                continue
            try:
                kline = kline_provider(code, days)
                if kline and len(kline) >= 25:
                    sector_data = None
                    if sector_provider:
                        try:
                            sector_data = sector_provider(code)
                        except Exception:
                            pass
                    result = self.run_single_stock(kline, code, name, sector_data=sector_data, verbose=verbose)
                    if result:
                        signals.append(result)
            except Exception as e:
                self._log(f"{code} {name} 扫描异常: {e}")

            if (i + 1) % 50 == 0:
                self._log(f"扫描进度 {i+1}/{total}，信号{len(signals)}只")

        signals.sort(key=lambda x: x.get('total_score', 0), reverse=True)
        self._log(f"扫描完成：{total}只，信号{len(signals)}只")
        return signals

    def get_scan_logs(self) -> List[str]:
        return self._scan_logs.copy()

    def clear_logs(self):
        self._scan_logs = []


def get_amplitude_strategy() -> AmplitudeBehaviorStrategy:
    return AmplitudeBehaviorStrategy()


if __name__ == '__main__':
    print("=" * 60)
    print("振幅行为模型 V1.0 自测")
    print("=" * 60)

    strategy = AmplitudeBehaviorStrategy()

    # 构造测试K线（振幅突破形态）
    test_kline = []
    base_price = 10.0
    for i in range(25):
        if i < 20:
            # 横盘缩量
            price = base_price + (i % 4) * 0.08
            vol = 60000 + (i % 3) * 5000
            test_kline.append({
                'date': f'2026-07-{15+i:02d}', 'open': price, 'high': price + 0.1,
                'low': price - 0.08, 'close': price + 0.03, 'volume': vol
            })
        elif i == 20:
            # 缩量回调1
            price = base_price - 0.1
            test_kline.append({
                'date': f'2026-08-{i-19:02d}', 'open': base_price + 0.05, 'high': base_price + 0.08,
                'low': price - 0.05, 'close': price, 'volume': 50000
            })
        elif i == 21:
            # 缩量回调2
            price = base_price - 0.15
            test_kline.append({
                'date': f'2026-08-{i-19:02d}', 'open': base_price - 0.05, 'high': base_price - 0.02,
                'low': price - 0.03, 'close': price, 'volume': 40000
            })
        elif i == 22:
            # 缩量回调3
            price = base_price - 0.12
            test_kline.append({
                'date': f'2026-08-{i-19:02d}', 'open': base_price - 0.13, 'high': base_price - 0.08,
                'low': price - 0.02, 'close': price, 'volume': 35000
            })
        elif i == 23:
            # 缩量回调4（振幅收缩）
            price = base_price - 0.08
            test_kline.append({
                'date': f'2026-08-{i-19:02d}', 'open': base_price - 0.1, 'high': base_price - 0.05,
                'low': price - 0.01, 'close': price, 'volume': 30000
            })
        elif i == 24:
            # 今天：振幅突破，放量阳线
            price = base_price + 0.15
            test_kline.append({
                'date': f'2026-08-{i-19:02d}', 'open': base_price - 0.05, 'high': price + 0.1,
                'low': base_price - 0.08, 'close': price, 'volume': 120000
            })

    print(f"\n测试K线：{len(test_kline)}根")
    print(f"前5日振幅均值：前4天缩量回调，振幅小")
    print(f"今天：开{test_kline[24]['open']} 高{test_kline[24]['high']} 低{test_kline[24]['low']} 收{test_kline[24]['close']} 量{test_kline[24]['volume']}")

    print("\n执行单股计算（verbose=True）：")
    result = strategy.run_single_stock(test_kline, '000001', '平安银行', verbose=True)

    print("\n计算结果：")
    if result:
        print(f"  股票：{result['stock_code']} {result['stock_name']}")
        print(f"  总分：{result['total_score']}/100")
        print(f"  等级：{result['grade']}")
        print(f"  形态：{result['patterns']}")
        print(f"  今日振幅：{result['today_amplitude']}%")
        print(f"  放量倍数：{result['vol_multiple']}")
        print(f"  收盘位置：{result['close_position']}")
        print(f"  标签：{result['tags']}")
        print(f"  评分明细：{result['score_detail']}")
    else:
        print("  无信号")

    print("\n振幅行为模型自测完成。")
