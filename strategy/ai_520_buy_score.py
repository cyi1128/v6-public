"""
V2.7 AI520买点评分模块
与AI520模式相似度评分分离：
- AI520相似度：回答"这只股票像不像我的520模式？"100分
- 买点评分：回答"它现在是不是处于比较好的介入位置？"单独计算0-100分

买点评分维度：
- MA5回踩 15分
- MA20回踩 15分
- 缩量 15分
- 阳线反转 15分
- 重新站MA5 10分
- 突破前高 10分
- KDJ转强 10分
- 量能恢复 10分
总分100分

分级：90-100优秀买点/80-89较好买点/70-79可关注/60-69一般/<60暂不介入
"""
from typing import Dict, List, Optional, Tuple


class AI520BuyScore:
    """AI520买点评分计算器"""

    def __init__(self):
        self.dimension_weights = {
            'ma5_pullback': 15,
            'ma20_pullback': 15,
            'shrink_volume': 15,
            'bullish_reversal': 15,
            'reclaim_ma5': 10,
            'break_previous_high': 10,
            'kdj_strong': 10,
            'volume_recovery': 10,
        }

    def calc_buy_score(self, stock_info: Dict, kline: List[Dict]) -> Dict:
        """
        计算买点评分（0-100分）
        Args:
            stock_info: 股票信息 {code, name, price, pct_chg, ...}
            kline: K线数据列表，按日期升序
        Returns:
            {
                'buy_score': 0-100,
                'buy_grade': '优秀买点'/'较好买点'/'可关注'/'一般'/'暂不介入',
                'dimension_scores': {各维度分数},
                'buy_signals': [触发的买点信号],
                'buy_risks': [风险提示],
            }
        """
        result = {
            'buy_score': 0,
            'buy_grade': '暂不介入',
            'dimension_scores': {},
            'buy_signals': [],
            'buy_risks': [],
        }

        if not kline or len(kline) < 20:
            result['buy_risks'].append('K线不足20根')
            return result

        try:
            # 计算均线
            closes = [float(k.get('close', 0)) for k in kline]
            volumes = [float(k.get('volume', 0)) for k in kline]
            highs = [float(k.get('high', 0)) for k in kline]
            lows = [float(k.get('low', 0)) for k in kline]
            opens = [float(k.get('open', 0)) for k in kline]

            current_close = closes[-1]
            current_open = opens[-1]
            current_high = highs[-1]
            current_low = lows[-1]
            current_vol = volumes[-1]
            prev_close = closes[-2] if len(closes) >= 2 else current_close
            prev_high = highs[-2] if len(highs) >= 2 else current_high

            # 计算MA5/MA10/MA20
            ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else current_close
            ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else current_close
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_close

            # 5日均量（不含当天）
            avg_vol_5 = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else current_vol
            vol_ratio = current_vol / avg_vol_5 if avg_vol_5 > 0 else 1.0

            # ========== 1. MA5回踩 15分 ==========
            ma5_score = 0
            dist_ma5 = abs(current_close - ma5) / ma5 if ma5 > 0 else 1
            if dist_ma5 <= 0.01:  # 1%以内
                ma5_score = 15
                result['buy_signals'].append(f'MA5回踩(距离{dist_ma5*100:.1f}%)')
            elif dist_ma5 <= 0.02:  # 2%以内
                ma5_score = 10
                result['buy_signals'].append(f'MA5接近(距离{dist_ma5*100:.1f}%)')
            elif dist_ma5 <= 0.03:
                ma5_score = 5
            result['dimension_scores']['ma5_pullback'] = ma5_score

            # ========== 2. MA20回踩 15分 ==========
            ma20_score = 0
            dist_ma20 = abs(current_close - ma20) / ma20 if ma20 > 0 else 1
            if dist_ma20 <= 0.01:
                ma20_score = 15
                result['buy_signals'].append(f'MA20回踩(距离{dist_ma20*100:.1f}%)')
            elif dist_ma20 <= 0.02:
                ma20_score = 10
                result['buy_signals'].append(f'MA20接近(距离{dist_ma20*100:.1f}%)')
            elif dist_ma20 <= 0.03:
                ma20_score = 5
            result['dimension_scores']['ma20_pullback'] = ma20_score

            # ========== 3. 缩量 15分 ==========
            shrink_score = 0
            if vol_ratio <= 0.6:
                shrink_score = 15
                result['buy_signals'].append(f'极度缩量(量比{vol_ratio:.2f})')
            elif vol_ratio <= 0.8:
                shrink_score = 12
                result['buy_signals'].append(f'明显缩量(量比{vol_ratio:.2f})')
            elif vol_ratio <= 1.0:
                shrink_score = 8
            elif vol_ratio <= 1.2:
                shrink_score = 4
            result['dimension_scores']['shrink_volume'] = shrink_score

            # ========== 4. 阳线反转 15分 ==========
            bullish_score = 0
            is_bullish = current_close > current_open
            body_ratio = (current_close - current_open) / current_open if current_open > 0 else 0
            if is_bullish and body_ratio >= 0.02:
                bullish_score = 15
                result['buy_signals'].append(f'中阳线(实体{body_ratio*100:.1f}%)')
            elif is_bullish and body_ratio >= 0.01:
                bullish_score = 10
                result['buy_signals'].append(f'小阳线(实体{body_ratio*100:.1f}%)')
            elif is_bullish:
                bullish_score = 5
            else:
                result['buy_risks'].append('当前阴线')
            result['dimension_scores']['bullish_reversal'] = bullish_score

            # ========== 5. 重新站MA5 10分 ==========
            reclaim_score = 0
            prev_close_2 = closes[-2] if len(closes) >= 2 else current_close
            ma5_prev = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else ma5
            if current_close > ma5 and prev_close_2 <= ma5_prev:
                reclaim_score = 10
                result['buy_signals'].append('重新站回MA5')
            elif current_close > ma5:
                reclaim_score = 5
            else:
                result['buy_risks'].append('收盘价低于MA5')
            result['dimension_scores']['reclaim_ma5'] = reclaim_score

            # ========== 6. 突破前高 10分 ==========
            break_score = 0
            if current_high > prev_high:
                break_score = 10
                result['buy_signals'].append('突破前一日高点')
            elif current_close > prev_close:
                break_score = 5
            result['dimension_scores']['break_previous_high'] = break_score

            # ========== 7. KDJ转强 10分 ==========
            kdj_score = 0
            try:
                kdj_result = self._calc_kdj_simple(kline)
                k_val = kdj_result.get('k', 50)
                d_val = kdj_result.get('d', 50)
                j_val = kdj_result.get('j', 50)
                k_prev = kdj_result.get('k_prev', 50)
                d_prev = kdj_result.get('d_prev', 50)

                # 金叉
                if k_val > d_val and k_prev <= d_prev:
                    kdj_score = 10
                    result['buy_signals'].append('KDJ金叉')
                elif k_val > d_val and k_val > k_prev:
                    kdj_score = 7
                    result['buy_signals'].append('KDJ向上')
                elif k_val > d_val:
                    kdj_score = 4
                elif j_val < 20:
                    kdj_score = 3
                    result['buy_signals'].append('KDJ超卖区')
            except Exception:
                kdj_score = 5
            result['dimension_scores']['kdj_strong'] = kdj_score

            # ========== 8. 量能恢复 10分 ==========
            volume_score = 0
            if vol_ratio >= 1.5 and is_bullish:
                volume_score = 10
                result['buy_signals'].append(f'放量上涨(量比{vol_ratio:.2f})')
            elif vol_ratio >= 1.2 and is_bullish:
                volume_score = 7
            elif vol_ratio >= 1.0:
                volume_score = 4
            result['dimension_scores']['volume_recovery'] = volume_score

            # ========== 汇总 ==========
            total = sum(result['dimension_scores'].values())
            total = min(total, 100)
            result['buy_score'] = total

            # 分级
            if total >= 90:
                result['buy_grade'] = '优秀买点'
            elif total >= 80:
                result['buy_grade'] = '较好买点'
            elif total >= 70:
                result['buy_grade'] = '可关注'
            elif total >= 60:
                result['buy_grade'] = '一般'
            else:
                result['buy_grade'] = '暂不介入'

            # 额外风险检查
            pct_chg = (current_close - prev_close) / prev_close * 100 if prev_close > 0 else 0
            if pct_chg > 7:
                result['buy_risks'].append(f'当日涨幅过大({pct_chg:.1f}%)，追高风险')
            if pct_chg < -5:
                result['buy_risks'].append(f'当日跌幅过大({pct_chg:.1f}%)')
            if ma20 < sum(closes[-25:-5]) / 20 if len(closes) >= 25 else ma20:
                result['buy_risks'].append('MA20趋势向下')

            # 保存关键数据
            result['ma5'] = round(ma5, 2)
            result['ma10'] = round(ma10, 2)
            result['ma20'] = round(ma20, 2)
            result['dist_ma5'] = round(dist_ma5 * 100, 2)
            result['dist_ma20'] = round(dist_ma20 * 100, 2)
            result['vol_ratio'] = round(vol_ratio, 2)
            result['pct_chg'] = round(pct_chg, 2)

        except Exception as e:
            result['buy_risks'].append(f'计算异常:{str(e)}')

        return result

    def _calc_kdj_simple(self, kline: List[Dict], n: int = 13, m1: int = 3, m2: int = 3) -> Dict:
        """简单KDJ计算，返回当前和前一日K/D/J"""
        result = {'k': 50, 'd': 50, 'j': 50, 'k_prev': 50, 'd_prev': 50}
        if not kline or len(kline) < n + 1:
            return result
        try:
            highs = [float(k.get('high', 0)) for k in kline]
            lows = [float(k.get('low', 0)) for k in kline]
            closes = [float(k.get('close', 0)) for k in kline]
            k_val = 50.0
            d_val = 50.0
            k_prev = 50.0
            d_prev = 50.0
            for i in range(len(kline)):
                if i < n - 1:
                    continue
                high_n = max(highs[i-n+1:i+1])
                low_n = min(lows[i-n+1:i+1])
                if high_n - low_n < 1e-8:
                    rsv = 50.0
                else:
                    rsv = (closes[i] - low_n) / (high_n - low_n) * 100
                k_prev = k_val
                d_prev = d_val
                k_val = (m1 - 1) / m1 * k_val + 1 / m1 * rsv
                d_val = (m2 - 1) / m2 * d_val + 1 / m2 * k_val
            j_val = 3 * k_val - 2 * d_val
            result = {
                'k': round(k_val, 2),
                'd': round(d_val, 2),
                'j': round(j_val, 2),
                'k_prev': round(k_prev, 2),
                'd_prev': round(d_prev, 2),
            }
        except Exception:
            pass
        return result


# 单例
_buy_score_instance = None

def get_buy_score() -> AI520BuyScore:
    global _buy_score_instance
    if _buy_score_instance is None:
        _buy_score_instance = AI520BuyScore()
    return _buy_score_instance
