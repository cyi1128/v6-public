# -*- coding: utf-8 -*-
"""
AI缠论多周期分析核心模块
基于缠中说禅理论：分型、笔、线段、中枢、背驰、买卖点
独立模块，只读取K线数据，不修改核心逻辑
"""
import numpy as np


class ChanlunCore:
    """缠论分析核心"""

    def __init__(self):
        # ========== 可调参数 ==========
        # 分型过滤参数
        self.fractal_min_body_ratio = 0.3  # 最小实体比例（实体/高低点差）
        self.fractal_min_volume_ratio = 0.5  # 最小成交量比例

        # 笔过滤参数
        self.stroke_min_kline = 3  # 笔之间最小K线数
        self.stroke_min_amplitude = 2.5  # 笔最小幅度（%）

        # 中枢过滤参数
        self.zhongshu_min_strokes = 3  # 中枢最小笔数
        self.zhongshu_min_amplitude = 3.0  # 中枢最小幅度（%）
        self.zhongsu_min_overlap = 0.3  # 最小重叠比例

        # 背驰过滤参数
        self.beichi_min_area_ratio = 0.8  # 背驰最大面积比
        self.beichi_min_strokes = 2  # 最少比较笔数

        # 买卖点过滤参数
        self.signal_require_strong_fractal = True  # 买卖点需要有效分型
        self.signal_require_volume_confirm = False  # 需要成交量确认
        # ================================

    def analyze(self, kline_data, period='day'):
        """
        单周期缠论分析
        Args:
            kline_data: dict, K线数据 {'close':[], 'high':[], 'low':[], 'open':[], 'volume':[], 'dates':[]}
            period: str, 周期 'day' 'week' '60min' '30min' '5min'
        Returns:
            dict: 分析结果
        """
        if not kline_data or len(kline_data.get('close', [])) < 30:
            return {
                'status': '数据不足',
                'period': period,
                'suggestion': '需要至少30根K线才能分析',
                'score': 0,
                'level': '无',
            }

        high = np.array(kline_data['high'])
        low = np.array(kline_data['low'])
        close = np.array(kline_data['close'])
        open_list = np.array(kline_data.get('open', close))  # 没有open就用close代替
        volume = np.array(kline_data['volume'])
        dates = kline_data['dates']

        # 1. 识别分型
        fractals = self._find_fractals(high, low, dates, open_list, close, volume)

        # 2. 识别笔
        strokes = self._find_strokes(fractals)

        # 3. 识别线段
        segments = self._find_segments(strokes)

        # 4. 识别中枢
        zhongshu = self._find_zhongshu(strokes)

        # 5. 计算MACD（用于背驰判断）
        macd = self._calc_macd(close)

        # 6. 判断背驰
        beichi = self._check_beichi(strokes, zhongshu, macd)

        # 7. 判断趋势
        trend = self._judge_trend(strokes, zhongshu, close[-1])

        # 8. 识别买卖点
        signals = self._find_signals(strokes, zhongshu, beichi, close[-1], macd)

        # 9. 计算价格点位
        price_levels = self._calc_price_levels(strokes, zhongshu, beichi, fractals, close[-1])

        # 10. 综合评分
        score, level = self._calc_score(trend, zhongshu, beichi, signals, macd, volume, close)

        # 11. 生成操作建议
        suggestion = self._generate_suggestion(trend, zhongshu, beichi, signals, price_levels, score, level)

        return {
            'status': '分析完成',
            'period': period,
            'trend': trend,
            'fractals': fractals,
            'strokes': strokes,
            'segments': segments,
            'zhongshu': zhongshu,
            'beichi': beichi,
            'signals': signals,
            'price_levels': price_levels,
            'macd': macd,
            'score': score,
            'level': level,
            'suggestion': suggestion,
            'current_price': close[-1],
            'fractal_count': len(fractals),
            'stroke_count': len(strokes),
            'segment_count': len(segments),
        }

    def analyze_multi_period(self, kline_dict):
        """
        多周期缠论分析
        Args:
            kline_dict: dict, 各周期K线数据 {'day': {...}, 'week': {...}, '60min': {...}, ...}
        Returns:
            dict: 多周期分析结果
        """
        results = {}
        for period, kline in kline_dict.items():
            results[period] = self.analyze(kline, period)

        # 多周期综合判断
        overall = self._multi_period_overall(results)

        return {
            'periods': results,
            'overall': overall,
        }

    # ============================================================
    # 1. 分型识别
    # ============================================================
    def _find_fractals(self, high, low, dates, opens=None, closes=None, volumes=None):
        """识别分型（顶分型、底分型），增加有效性过滤"""
        fractals = []
        n = len(high)

        for i in range(1, n - 1):
            # 基础条件：中间K线最高/最低
            is_top = high[i] > high[i-1] and high[i] > high[i+1]
            is_bottom = low[i] < low[i-1] and low[i] < low[i+1]

            if not is_top and not is_bottom:
                continue

            # 有效性评分
            validity = 1.0
            validity_level = 'normal'  # normal / strong

            # 1. 实体过滤
            if opens is not None and closes is not None:
                body = abs(closes[i] - opens[i])
                range_ = high[i] - low[i]
                if range_ > 0:
                    body_ratio = body / range_
                    # 实体太小的分型有效性降低
                    if body_ratio < self.fractal_min_body_ratio:
                        validity *= 0.7

            # 2. 成交量过滤
            if volumes is not None and i > 0:
                avg_vol = sum(volumes[max(0, i-5):i]) / min(5, i) if i > 0 else volumes[i]
                if avg_vol > 0:
                    vol_ratio = volumes[i] / avg_vol
                    # 极端缩量的分型有效性降低
                    if vol_ratio < self.fractal_min_volume_ratio:
                        validity *= 0.8

            # 3. 影线过滤（长影线假分型）
            if opens is not None and closes is not None:
                body_high = max(opens[i], closes[i])
                body_low = min(opens[i], closes[i])
                upper_shadow = high[i] - body_high
                lower_shadow = body_low - low[i]
                body = body_high - body_low

                if body > 0:
                    # 顶分型：上影线太长有效性降低
                    if is_top and upper_shadow > body * 2:
                        validity *= 0.75
                    # 底分型：下影线太长有效性降低
                    if is_bottom and lower_shadow > body * 2:
                        validity *= 0.75

            # 判断是否为有效分型
            if validity >= 0.8:
                validity_level = 'strong'
            elif validity >= 0.5:
                validity_level = 'normal'
            else:
                validity_level = 'weak'

            if is_top:
                fractals.append({
                    'type': 'top',
                    'index': i,
                    'price': high[i],
                    'date': dates[i],
                    'validity': validity,
                    'validity_level': validity_level,
                })
            elif is_bottom:
                fractals.append({
                    'type': 'bottom',
                    'index': i,
                    'price': low[i],
                    'date': dates[i],
                    'validity': validity,
                    'validity_level': validity_level,
                })

        return fractals

    # ============================================================
    # 2. 笔识别
    # ============================================================
    def _find_strokes(self, fractals):
        """识别笔（相邻顶底分型之间的连线），增加过滤条件"""
        strokes = []

        if len(fractals) < 2:
            return strokes

        # 优化的笔识别：
        # 1. 先过滤弱有效性分型
        # 2. 同方向分型取极值（顶取最高，底取最低）
        # 3. 顶底交替形成笔
        # 4. 笔之间至少N根K线
        # 5. 幅度达到最小阈值

        # 第一步：过滤弱有效性分型
        min_validity = 0.6  # 有效性低于0.6的分型不参与笔的形成
        filtered_fractals = [f for f in fractals if f.get('validity', 1.0) >= min_validity]

        if len(filtered_fractals) < 2:
            return strokes

        # 第二步：同方向分型合并，保留极值
        filtered = []
        for f in filtered_fractals:
            if not filtered:
                filtered.append(f)
                continue

            last = filtered[-1]
            if f['type'] == last['type']:
                # 同方向，取极值
                if f['type'] == 'top' and f['price'] > last['price']:
                    filtered[-1] = f
                elif f['type'] == 'bottom' and f['price'] < last['price']:
                    filtered[-1] = f
            else:
                # 不同方向，检查K线间隔
                kline_gap = abs(f['index'] - last['index'])
                if kline_gap >= self.stroke_min_kline:
                    filtered.append(f)
                # 间隔不够，跳过这个分型

        # 第三步：生成笔，增加幅度过滤
        for i in range(1, len(filtered)):
            prev = filtered[i-1]
            curr = filtered[i]

            if curr['type'] == 'top':
                direction = 'up'
                amplitude = (curr['price'] - prev['price']) / prev['price'] * 100
            else:
                direction = 'down'
                amplitude = (prev['price'] - curr['price']) / prev['price'] * 100

            # 幅度过滤
            if amplitude < self.stroke_min_amplitude:
                continue

            # 有效性：取两个分型中较低的有效性
            validity = min(prev.get('validity', 1.0), curr.get('validity', 1.0))

            strokes.append({
                'direction': direction,
                'start_price': prev['price'],
                'end_price': curr['price'],
                'start_date': prev['date'],
                'end_date': curr['date'],
                'amplitude': amplitude,
                'start_index': prev['index'],
                'end_index': curr['index'],
                'start_fractal': prev,
                'end_fractal': curr,
                'validity': validity,
                'kline_count': abs(curr['index'] - prev['index']),
            })

        return strokes

    # ============================================================
    # 3. 线段识别
    # ============================================================
    def _find_segments(self, strokes):
        """识别线段（至少三笔组成，且有重叠）"""
        segments = []

        if len(strokes) < 3:
            return segments

        i = 0
        while i < len(strokes) - 2:
            s1 = strokes[i]
            s2 = strokes[i+1]
            s3 = strokes[i+2]

            # 前三笔有重叠，形成线段雏形
            if self._strokes_overlap(s1, s3):
                # 线段方向：与第一笔相同
                direction = s1['direction']
                start_price = s1['start_price']
                end_price = s3['end_price']

                # 继续往后找，直到线段被破坏
                j = i + 3
                while j < len(strokes):
                    # 检查是否破坏线段
                    if strokes[j]['direction'] != direction:
                        # 反向笔突破前高/前低，线段结束
                        if direction == 'up' and strokes[j]['end_price'] < s1['start_price']:
                            break
                        elif direction == 'down' and strokes[j]['end_price'] > s1['start_price']:
                            break
                    j += 1

                # 计算线段高低点
                segment_strokes = strokes[i:j]
                if segment_strokes:
                    high = max(s['end_price'] for s in segment_strokes)
                    low = min(s['start_price'] for s in segment_strokes)

                    segments.append({
                        'direction': direction,
                        'start_price': start_price,
                        'end_price': end_price,
                        'high': high,
                        'low': low,
                        'stroke_count': len(segment_strokes),
                        'start_date': s1['start_date'],
                        'end_date': strokes[j-1]['end_date'] if j > i else s3['end_date'],
                    })

                i = j - 1
            else:
                i += 1

        return segments

    def _strokes_overlap(self, s1, s2):
        """判断两笔是否有价格重叠"""
        s1_high = max(s1['start_price'], s1['end_price'])
        s1_low = min(s1['start_price'], s1['end_price'])
        s2_high = max(s2['start_price'], s2['end_price'])
        s2_low = min(s2['start_price'], s2['end_price'])

        return s1_low < s2_high and s2_low < s1_high

    # ============================================================
    # 4. 中枢识别
    # ============================================================
    def _find_zhongshu(self, strokes):
        """识别中枢（至少三段重叠区域），增加过滤条件"""
        if len(strokes) < self.zhongshu_min_strokes:
            return None

        # 找最近的有效中枢
        for i in range(len(strokes) - self.zhongshu_min_strokes, -1, -1):
            s1 = strokes[i]
            s2 = strokes[i+1]
            s3 = strokes[i+2]

            # 三段重叠区域
            if s1['direction'] == 'up' and s2['direction'] == 'down' and s3['direction'] == 'up':
                # 上涨中枢
                zg = min(s1['end_price'], s3['end_price'])  # 中枢上沿
                zd = max(s1['start_price'], s3['start_price'])  # 中枢下沿
                if zg > zd:
                    amplitude = (zg - zd) / zd * 100

                    # 幅度过滤：太小的不是有效中枢
                    if amplitude < self.zhongshu_min_amplitude:
                        continue

                    # 检查是否有离开段
                    leave_stroke = strokes[i+3] if i+3 < len(strokes) else None

                    return {
                        'type': 'up',
                        'zg': zg,
                        'zd': zd,
                        'start_date': s1['start_date'],
                        'end_date': s3['end_date'],
                        'amplitude': amplitude,
                        'zg_index': s1['end_index'],
                        'zd_index': s3['start_index'],
                        'leave_stroke': leave_stroke,
                        'stroke_count': 3,
                        'validity': 'strong' if amplitude > 5 else 'normal',
                    }
            elif s1['direction'] == 'down' and s2['direction'] == 'up' and s3['direction'] == 'down':
                # 下跌中枢
                zg = min(s1['start_price'], s3['start_price'])
                zd = max(s1['end_price'], s3['end_price'])
                if zg > zd:
                    amplitude = (zg - zd) / zd * 100

                    # 幅度过滤
                    if amplitude < self.zhongshu_min_amplitude:
                        continue

                    leave_stroke = strokes[i+3] if i+3 < len(strokes) else None

                    return {
                        'type': 'down',
                        'zg': zg,
                        'zd': zd,
                        'start_date': s1['start_date'],
                        'end_date': s3['end_date'],
                        'amplitude': amplitude,
                        'zg_index': s1['start_index'],
                        'zd_index': s3['end_index'],
                        'leave_stroke': leave_stroke,
                        'stroke_count': 3,
                        'validity': 'strong' if amplitude > 5 else 'normal',
                    }

        return None

    # ============================================================
    # 5. MACD计算
    # ============================================================
    def _calc_macd(self, close, fast=8, slow=21, signal=5):
        """计算MACD（参数8,21,5，与程序一致）"""
        n = len(close)
        if n < slow + signal:
            return {'dif': [], 'dea': [], 'macd': []}

        # EMA计算
        def ema(data, period):
            result = []
            multiplier = 2 / (period + 1)
            result.append(data[0])
            for i in range(1, len(data)):
                result.append(data[i] * multiplier + result[-1] * (1 - multiplier))
            return result

        ema_fast = ema(close, fast)
        ema_slow = ema(close, slow)

        dif = [ema_fast[i] - ema_slow[i] for i in range(n)]
        dea = ema(dif, signal)
        macd = [(dif[i] - dea[i]) * 2 for i in range(n)]  # 红绿柱

        return {
            'dif': dif,
            'dea': dea,
            'macd': macd,  # 红绿柱
        }

    # ============================================================
    # 6. 背驰判断
    # ============================================================
    def _check_beichi(self, strokes, zhongshu, macd):
        """判断背驰（MACD辅助），增加确认条件"""
        if not zhongshu or len(strokes) < 4 or not macd.get('macd'):
            return None

        macd_bars = macd['macd']
        if len(macd_bars) < 20:
            return None

        # 找中枢前后的两段同方向笔
        last_stroke = strokes[-1]
        prev_stroke = None

        # 找中枢离开段和进入段（至少两段比较）
        for i in range(len(strokes) - 2, -1, -1):
            if strokes[i]['direction'] == last_stroke['direction']:
                prev_stroke = strokes[i]
                break

        if not prev_stroke:
            return None

        # 确保索引在范围内
        last_start = last_stroke['start_index']
        last_end = last_stroke['end_index']
        prev_start = prev_stroke['start_index']
        prev_end = prev_stroke['end_index']

        if last_end >= len(macd_bars) or prev_end >= len(macd_bars):
            return None

        # 计算两段的MACD柱面积（绝对值之和）
        last_area = sum(abs(macd_bars[i]) for i in range(last_start, last_end+1) if i < len(macd_bars))
        prev_area = sum(abs(macd_bars[i]) for i in range(prev_start, prev_end+1) if i < len(macd_bars))

        if prev_area == 0:
            return None

        # 比较最高点/最低点的MACD柱高度
        last_peak = max(abs(macd_bars[i]) for i in range(last_start, last_end+1) if i < len(macd_bars)) if last_end < len(macd_bars) else 0
        prev_peak = max(abs(macd_bars[i]) for i in range(prev_start, prev_end+1) if i < len(macd_bars)) if prev_end < len(macd_bars) else 0

        # 面积比和峰值比
        area_ratio = last_area / prev_area
        peak_ratio = last_peak / prev_peak if prev_peak > 0 else 1

        # 背驰判断
        if last_stroke['direction'] == 'up':
            # 顶背驰：价格创新高，MACD力度减弱
            if last_stroke['end_price'] > prev_stroke['end_price'] and area_ratio < self.beichi_min_area_ratio:
                # 强度分级
                if area_ratio < 0.5 and peak_ratio < 0.6:
                    level = '强'
                elif area_ratio < 0.7:
                    level = '中'
                else:
                    level = '弱'

                return {
                    'type': 'top_beichi',
                    'position': '高位',
                    'description': '顶背驰，上涨动能衰竭',
                    'area_ratio': area_ratio,
                    'peak_ratio': peak_ratio,
                    'level': level,
                }
        else:
            # 底背驰：价格创新低，MACD力度减弱
            if last_stroke['end_price'] < prev_stroke['end_price'] and area_ratio < self.beichi_min_area_ratio:
                if area_ratio < 0.5 and peak_ratio < 0.6:
                    level = '强'
                elif area_ratio < 0.7:
                    level = '中'
                else:
                    level = '弱'

                return {
                    'type': 'bottom_beichi',
                    'position': '低位',
                    'description': '底背驰，下跌动能衰竭',
                    'area_ratio': area_ratio,
                    'peak_ratio': peak_ratio,
                    'level': level,
                }

        return None

    # ============================================================
    # 7. 趋势判断
    # ============================================================
    def _judge_trend(self, strokes, zhongshu, current_price):
        """判断当前趋势"""
        if not strokes:
            return {'direction': 'unknown', 'status': '无法判断', 'description': '数据不足'}

        last_stroke = strokes[-1]

        if zhongshu:
            if current_price > zhongshu['zg']:
                if last_stroke['direction'] == 'up':
                    return {
                        'direction': 'up',
                        'status': '上涨趋势',
                        'description': '突破中枢上沿，处于上涨趋势中',
                    }
                else:
                    return {
                        'direction': 'up',
                        'status': '上涨调整',
                        'description': '上涨趋势中的回调',
                    }
            elif current_price < zhongshu['zd']:
                if last_stroke['direction'] == 'down':
                    return {
                        'direction': 'down',
                        'status': '下跌趋势',
                        'description': '跌破中枢下沿，处于下跌趋势中',
                    }
                else:
                    return {
                        'direction': 'down',
                        'status': '下跌反弹',
                        'description': '下跌趋势中的反弹',
                    }
            else:
                return {
                    'direction': 'sideways',
                    'status': '中枢震荡',
                    'description': '在中枢区间内震荡整理',
                }
        else:
            # 没有中枢，看最近几笔方向
            up_count = sum(1 for s in strokes[-5:] if s['direction'] == 'up')
            down_count = sum(1 for s in strokes[-5:] if s['direction'] == 'down')

            if up_count > down_count:
                return {
                    'direction': 'up',
                    'status': '上涨趋势',
                    'description': '近期上涨笔居多，趋势向上',
                }
            elif down_count > up_count:
                return {
                    'direction': 'down',
                    'status': '下跌趋势',
                    'description': '近期下跌笔居多，趋势向下',
                }
            else:
                return {
                    'direction': 'sideways',
                    'status': '盘整',
                    'description': '多空平衡，处于盘整阶段',
                }

    # ============================================================
    # 8. 买卖点识别
    # ============================================================
    def _find_signals(self, strokes, zhongshu, beichi, current_price, macd):
        """识别买卖点（一买、二买、三买、一卖、二卖、三卖），增加确认条件"""
        signals = []

        if not strokes:
            return signals

        last_stroke = strokes[-1]

        # 一买：底背驰 + 有效底分型
        if beichi and beichi['type'] == 'bottom_beichi':
            # 检查最后一个分型是否是有效底分型
            end_fractal = last_stroke.get('end_fractal', {})
            is_strong = end_fractal.get('validity_level', 'normal') == 'strong' or not self.signal_require_strong_fractal

            if is_strong:
                signals.append({
                    'name': '一买',
                    'type': 'buy',
                    'level': beichi.get('level', '强'),
                    'description': '底背驰，下跌动能衰竭，第一类买点',
                    'position': '低位',
                    'confidence': '高' if beichi.get('level') == '强' else '中',
                })

        # 一卖：顶背驰 + 有效顶分型
        if beichi and beichi['type'] == 'top_beichi':
            end_fractal = last_stroke.get('end_fractal', {})
            is_strong = end_fractal.get('validity_level', 'normal') == 'strong' or not self.signal_require_strong_fractal

            if is_strong:
                signals.append({
                    'name': '一卖',
                    'type': 'sell',
                    'level': beichi.get('level', '强'),
                    'description': '顶背驰，上涨动能衰竭，第一类卖点',
                    'position': '高位',
                    'confidence': '高' if beichi.get('level') == '强' else '中',
                })

        # 二买：一买后回调不创新低
        if beichi and beichi['type'] == 'bottom_beichi' and len(strokes) >= 3:
            # 底背驰后反弹，再回调不跌破前低
            if last_stroke['direction'] == 'down' and last_stroke['end_price'] > strokes[-3]['start_price']:
                signals.append({
                    'name': '二买',
                    'type': 'buy',
                    'level': '中',
                    'description': '回调不创新低，第二类买点',
                    'position': '中低位',
                    'confidence': '中',
                })

        # 二卖：一卖后反弹不创新高
        if beichi and beichi['type'] == 'top_beichi' and len(strokes) >= 3:
            if last_stroke['direction'] == 'up' and last_stroke['end_price'] < strokes[-3]['start_price']:
                signals.append({
                    'name': '二卖',
                    'type': 'sell',
                    'level': '中',
                    'description': '反弹不创新高，第二类卖点',
                    'position': '中高位',
                    'confidence': '中',
                })

        # 三买：突破中枢后回踩不进中枢
        if zhongshu and zhongshu['type'] == 'up':
            # 计算价格距离中枢的距离
            distance_pct = (current_price - zhongshu['zg']) / zhongshu['zg'] * 100

            # 中枢有效性判断：离开太远的中枢已经失效（超过50%视为失效）
            if distance_pct > 50:
                # 价格远离中枢，原中枢失效，不判断三买
                pass
            elif current_price > zhongshu['zg'] and last_stroke['direction'] == 'down':
                # 回踩但不跌破中枢上沿（允许1%误差）
                if last_stroke['end_price'] >= zhongshu['zg'] * 0.99:
                    # 回踩幅度不能太小（至少3%），否则不算有效回踩
                    pullback_pct = (last_stroke['start_price'] - last_stroke['end_price']) / last_stroke['start_price'] * 100
                    if pullback_pct >= 3:
                        signals.append({
                            'name': '三买',
                            'type': 'buy',
                            'level': '中',
                            'description': '突破中枢后回踩确认，第三类买点',
                            'position': '中枢上方',
                            'confidence': '中',
                        })
            elif current_price > zhongshu['zg'] and distance_pct <= 20:
                # 刚突破中枢不久（离开<20%），才算三买候选
                signals.append({
                    'name': '三买候选',
                    'type': 'buy',
                    'level': '弱',
                    'description': '刚突破中枢，等待回踩确认三买',
                    'position': '中枢上方',
                    'confidence': '低',
                })

        # 三卖：跌破中枢后反抽不进中枢
        if zhongshu and zhongshu['type'] == 'down':
            # 计算价格距离中枢的距离
            distance_pct = (zhongshu['zd'] - current_price) / zhongshu['zd'] * 100

            # 中枢有效性判断：离开太远的中枢已经失效（超过50%视为失效）
            if distance_pct > 50:
                # 价格远离中枢，原中枢失效，不判断三卖
                pass
            elif current_price < zhongshu['zd'] and last_stroke['direction'] == 'up':
                # 反抽但不突破中枢下沿（允许1%误差）
                if last_stroke['end_price'] <= zhongshu['zd'] * 1.01:
                    # 反抽幅度不能太小（至少3%），否则不算有效反抽
                    rebound_pct = (last_stroke['end_price'] - last_stroke['start_price']) / last_stroke['start_price'] * 100
                    if rebound_pct >= 3:
                        signals.append({
                            'name': '三卖',
                            'type': 'sell',
                            'level': '中',
                            'description': '跌破中枢后反抽确认，第三类卖点',
                            'position': '中枢下方',
                            'confidence': '中',
                        })
            elif current_price < zhongshu['zd'] and distance_pct <= 20:
                # 刚跌破中枢不久（离开<20%），才算三卖候选
                signals.append({
                    'name': '三卖候选',
                    'type': 'sell',
                    'level': '弱',
                    'description': '刚跌破中枢，等待反抽确认三卖',
                    'position': '中枢下方',
                    'confidence': '低',
                })

        # 中枢震荡操作建议（弱信号）
        if zhongshu and not any(s['level'] in ['强', '中'] for s in signals):
            if current_price <= zhongshu['zd'] * 1.02:
                signals.append({
                    'name': '中枢下沿',
                    'type': 'buy',
                    'level': '弱',
                    'description': '接近中枢下沿，震荡低吸',
                    'position': '中枢下沿',
                    'confidence': '低',
                })
            elif current_price >= zhongshu['zg'] * 0.98:
                signals.append({
                    'name': '中枢上沿',
                    'type': 'sell',
                    'level': '弱',
                    'description': '接近中枢上沿，震荡高抛',
                    'position': '中枢上沿',
                    'confidence': '低',
                })

        return signals

    # ============================================================
    # 9. 价格点位计算
    # ============================================================
    def _calc_price_levels(self, strokes, zhongshu, beichi, fractals, current_price):
        """计算价格点位"""
        price_levels = {
            'buy_price': None,
            'sell_price': None,
            'support': None,
            'resistance': None,
            'stop_loss': None,
            'take_profit': None,
        }

        # 找最近的顶底分型
        latest_top = None
        latest_bottom = None
        for f in reversed(fractals):
            if f['type'] == 'top' and latest_top is None:
                latest_top = f['price']
            if f['type'] == 'bottom' and latest_bottom is None:
                latest_bottom = f['price']
            if latest_top and latest_bottom:
                break

        # 中枢相关
        if zhongshu:
            zg = zhongshu['zg']
            zd = zhongshu['zd']
            amplitude = zg - zd

            price_levels['support'] = zd
            price_levels['resistance'] = zg
            price_levels['stop_loss'] = zd * 0.98
            price_levels['take_profit'] = zg + amplitude

            # 三买
            if current_price > zg:
                price_levels['buy_price'] = zg * 1.01
                price_levels['sell_price'] = price_levels['take_profit']
            # 三卖
            elif current_price < zd:
                price_levels['sell_price'] = zd * 0.99
            # 中枢震荡
            else:
                price_levels['buy_price'] = zd * 1.01
                price_levels['sell_price'] = zg * 0.99

        # 背驰相关
        if beichi:
            if beichi['type'] == 'bottom_beichi' and latest_bottom:
                price_levels['buy_price'] = latest_bottom * 1.02
                price_levels['stop_loss'] = latest_bottom * 0.97
                if latest_top:
                    price_levels['sell_price'] = latest_top
                    price_levels['take_profit'] = latest_top

            elif beichi['type'] == 'top_beichi' and latest_top:
                price_levels['sell_price'] = latest_top * 0.98
                if latest_bottom:
                    price_levels['buy_price'] = latest_bottom

        # 无中枢无背驰
        if not zhongshu and not beichi and strokes:
            last_stroke = strokes[-1]
            if latest_bottom:
                price_levels['support'] = latest_bottom
            if latest_top:
                price_levels['resistance'] = latest_top

            if last_stroke['direction'] == 'up':
                price_levels['buy_price'] = last_stroke['start_price'] * 1.01
                price_levels['sell_price'] = last_stroke['end_price'] * 0.99
            else:
                price_levels['sell_price'] = last_stroke['start_price'] * 0.99
                price_levels['buy_price'] = last_stroke['end_price'] * 1.01

        return price_levels

    # ============================================================
    # 10. 综合评分
    # ============================================================
    def _calc_score(self, trend, zhongshu, beichi, signals, macd, volume, close):
        """缠论综合评分（0-100分）"""
        score = 50  # 基础分

        # 1. 趋势评分（30分）
        trend_score = 15
        if trend['direction'] == 'up':
            trend_score = 25
            if trend['status'] == '上涨趋势':
                trend_score = 30
        elif trend['direction'] == 'down':
            trend_score = 10
            if trend['status'] == '下跌趋势':
                trend_score = 5
        else:
            trend_score = 15

        score += trend_score - 15  # 基准15分，上下浮动

        # 2. 缠论结构评分（30分）
        structure_score = 15

        # 中枢
        if zhongshu:
            structure_score += 5
            if zhongshu['type'] == 'up':
                structure_score += 5

        # 背驰
        if beichi:
            if beichi['type'] == 'bottom_beichi':
                structure_score += 10
                if beichi.get('level') == '强':
                    structure_score += 5
            elif beichi['type'] == 'top_beichi':
                structure_score -= 10
                if beichi.get('level') == '强':
                    structure_score -= 5

        # 买卖点
        buy_signals = [s for s in signals if s['type'] == 'buy']
        sell_signals = [s for s in signals if s['type'] == 'sell']

        if buy_signals:
            max_level = max({'强': 3, '中': 2, '弱': 1}[s['level']] for s in buy_signals)
            structure_score += max_level * 3

        if sell_signals:
            max_level = max({'强': 3, '中': 2, '弱': 1}[s['level']] for s in sell_signals)
            structure_score -= max_level * 3

        score += structure_score - 15

        # 3. 技术指标评分（20分）
        indicator_score = 10

        if macd.get('dif') and len(macd['dif']) > 2:
            dif = macd['dif'][-1]
            dea = macd['dea'][-1] if macd.get('dea') else 0

            if dif > dea:
                indicator_score += 5
                if dif > 0:
                    indicator_score += 5
            else:
                indicator_score -= 3
                if dif < 0:
                    indicator_score -= 2

        score += indicator_score - 10

        # 4. 量价评分（20分）
        volume_score = 10

        if len(volume) >= 5 and len(close) >= 5:
            avg_vol_5 = sum(volume[-6:-1]) / 5
            current_vol = volume[-1]
            vol_ratio = current_vol / avg_vol_5 if avg_vol_5 > 0 else 1

            pct_chg = (close[-1] - close[-2]) / close[-2] * 100 if close[-2] > 0 else 0

            # 放量上涨
            if pct_chg > 0 and vol_ratio > 1.5:
                volume_score += 10
            # 缩量上涨
            elif pct_chg > 0 and vol_ratio < 0.8:
                volume_score += 3
            # 放量下跌
            elif pct_chg < 0 and vol_ratio > 1.5:
                volume_score -= 8
            # 缩量下跌
            elif pct_chg < 0 and vol_ratio < 0.8:
                volume_score -= 2

        score += volume_score - 10

        # 限制在0-100分
        score = max(0, min(100, int(score)))

        # 评级
        if score >= 80:
            level = '强势关注'
        elif score >= 60:
            level = '谨慎参与'
        elif score >= 40:
            level = '观望为主'
        elif score >= 20:
            level = '风险较高'
        else:
            level = '回避'

        return score, level

    # ============================================================
    # 11. 生成操作建议
    # ============================================================
    def _generate_suggestion(self, trend, zhongshu, beichi, signals, price_levels, score, level):
        """生成操作建议"""
        lines = []

        # 趋势判断
        lines.append(f"【趋势判断】{trend['description']}")

        # 缠论结构
        if zhongshu:
            lines.append(f"【缠论结构】{zhongshu['type']}中枢，幅度{zhongshu['amplitude']:.1f}%")
        else:
            lines.append("【缠论结构】暂无明显中枢")

        # 背驰
        if beichi:
            lines.append(f"【背驰】{beichi['description']}")

        # 买卖点
        if signals:
            signal_text = "、".join(s['name'] for s in signals if s['level'] in ['强', '中'])
            if signal_text:
                lines.append(f"【买卖点】{signal_text}")

        # 价格点位
        price_info = []
        if price_levels.get('buy_price'):
            price_info.append(f"买入{price_levels['buy_price']:.2f}")
        if price_levels.get('sell_price'):
            price_info.append(f"卖出{price_levels['sell_price']:.2f}")
        if price_levels.get('support'):
            price_info.append(f"支撑{price_levels['support']:.2f}")
        if price_levels.get('resistance'):
            price_info.append(f"压力{price_levels['resistance']:.2f}")
        if price_levels.get('stop_loss'):
            price_info.append(f"止损{price_levels['stop_loss']:.2f}")

        if price_info:
            lines.append("【价格点位】" + " | ".join(price_info))

        # 操作建议
        lines.append(f"【综合评分】{score}分 - {level}")

        return "\n".join(lines)

    # ============================================================
    # 12. 多周期综合判断
    # ============================================================
    def _multi_period_overall(self, results):
        """多周期综合判断"""
        overall_score = 0
        weight = {'week': 0.4, 'day': 0.3, '60min': 0.2, '30min': 0.08, '5min': 0.02}

        for period, result in results.items():
            w = weight.get(period, 0.1)
            overall_score += result.get('score', 50) * w

        overall_score = int(overall_score)

        if overall_score >= 70:
            suggestion = "多周期共振向上，可重点关注"
            level = "强势"
        elif overall_score >= 55:
            suggestion = "大周期向好，小周期可择机参与"
            level = "偏强"
        elif overall_score >= 45:
            suggestion = "多周期分歧，观望为主"
            level = "中性"
        elif overall_score >= 30:
            suggestion = "大周期偏弱，谨慎操作"
            level = "偏弱"
        else:
            suggestion = "多周期共振向下，回避风险"
            level = "弱势"

        return {
            'overall_score': overall_score,
            'overall_level': level,
            'overall_suggestion': suggestion,
        }


# 单例
_core = None

def get_chanlun_core():
    global _core
    if _core is None:
        _core = ChanlunCore()
    return _core
