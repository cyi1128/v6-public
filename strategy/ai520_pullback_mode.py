# -*- coding: utf-8 -*-
"""
AI-520 回踩启动模式（生产版）

核心：MA5/MA20 金叉后，不追离均线太远的位置，等待价格回踩 MA5 或 MA20，
当天重新转强时才给出信号。全部指标由真实K线计算，不使用模拟数据。

适用：主板 600/601/603/605/000/001/002；排除ST。
"""
from typing import Dict, List, Optional, Tuple


class AI520PullbackMode:
    MAX_CROSS_AGE = 15
    MIN_PULLBACK_AGE = 1
    MAX_PULLBACK_AGE = 12

    def _ma(self, closes: List[float], n: int) -> List[Optional[float]]:
        out = [None] * len(closes)
        for i in range(n - 1, len(closes)):
            out[i] = sum(closes[i-n+1:i+1]) / n
        return out

    def _pct(self, a: float, b: float) -> float:
        return (a / b - 1) * 100 if b else 0.0

    def _is_limit_up(self, bar: Dict, prev_close: float, code: str) -> bool:
        if prev_close <= 0:
            return False
        pct = self._pct(float(bar.get('close', 0)), prev_close)
        return pct >= (9.5 if code.startswith(('60', '000', '001', '002')) else 19.5)

    def _cross_age(self, ma5: List[Optional[float]], ma20: List[Optional[float]]) -> int:
        last = len(ma5) - 1
        for i in range(last, max(20, last - 30), -1):
            if None in (ma5[i], ma20[i], ma5[i-1], ma20[i-1]):
                continue
            if ma5[i] > ma20[i] and ma5[i-1] <= ma20[i-1]:
                return last - i
        return -1

    def detect_pullback(self, kline: List[Dict]) -> Dict:
        """识别最近一次520金叉后的有效回踩，区分 MA5 / MA20。"""
        if len(kline) < 30:
            return {'valid': False, 'reason': 'K线不足'}
        closes = [float(x.get('close', 0)) for x in kline]
        highs = [float(x.get('high', 0)) for x in kline]
        lows = [float(x.get('low', 0)) for x in kline]
        opens = [float(x.get('open', 0)) for x in kline]
        vols = [float(x.get('volume', 0)) for x in kline]
        ma5, ma20 = self._ma(closes, 5), self._ma(closes, 20)
        age = self._cross_age(ma5, ma20)
        if age < 0 or age > self.MAX_CROSS_AGE:
            return {'valid': False, 'reason': f'520金叉不在{self.MAX_CROSS_AGE}日内', 'cross_age': age}

        end = len(kline) - 1
        start = max(0, end - age - self.MAX_PULLBACK_AGE)
        cross_idx = end - age
        touch5 = None
        touch20 = None
        # 金叉后到今天之前寻找“低点触线 + 收盘重新站回/接近”的回踩
        for i in range(cross_idx + self.MIN_PULLBACK_AGE, end):
            if ma5[i] and lows[i] <= ma5[i] * 1.015:
                if closes[i] >= ma5[i] * 0.985:
                    touch5 = i
            if ma20[i] and lows[i] <= ma20[i] * 1.02:
                if closes[i] >= ma20[i] * 0.975:
                    touch20 = i

        cur = closes[-1]
        cur_ma5 = ma5[-1] or 0
        cur_ma20 = ma20[-1] or 0
        prev = closes[-2]
        today_pct = self._pct(cur, prev)
        rebound = cur > opens[-1] and cur > prev
        dist5 = self._pct(cur, cur_ma5)
        dist20 = self._pct(cur, cur_ma20)
        vol_base = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else 0
        vol_ratio = vols[-1] / vol_base if vol_base > 0 else 0
        ma20_slope = self._pct(cur_ma20, ma20[-6] or cur_ma20) if len(ma20) >= 6 else 0

        mode = ''
        touch_idx = None
        if touch5 is not None:
            mode, touch_idx = '回踩MA5', touch5
        if touch20 is not None and (touch_idx is None or touch20 > touch_idx):
            mode, touch_idx = '回踩MA20', touch20
        if not mode:
            return {'valid': False, 'reason': '最近窗口没有有效回踩MA5/MA20', 'cross_age': age}

        touch_days = end - touch_idx
        # 今天必须重新转强，但不追太远
        if not (0.3 <= today_pct <= 7.0):
            return {'valid': False, 'reason': f'今日涨幅不在0.3%~7% ({today_pct:.2f}%)', 'cross_age': age}
        if not rebound:
            return {'valid': False, 'reason': '今日未出现阳线转强', 'cross_age': age}
        if dist5 > 3.5 and dist20 > 5.0:
            return {'valid': False, 'reason': '当前离MA5/MA20过远，疑似追高', 'cross_age': age}
        if ma20_slope < -1.0:
            return {'valid': False, 'reason': 'MA20明显向下', 'cross_age': age}

        # 评分：回踩质量 + 转强 + 量价 + 520结构
        score = 0
        reasons = []
        risks = []
        score += 25 if mode == '回踩MA5' else 23
        reasons.append(mode)
        if touch_days <= 3:
            score += 10; reasons.append(f'回踩{touch_days}日内反弹')
        elif touch_days <= 6:
            score += 7
        else:
            score += 3
        if dist5 <= 1.0:
            score += 12; reasons.append('价格贴近MA5')
        elif dist20 <= 1.5:
            score += 12; reasons.append('价格贴近MA20')
        elif dist5 <= 2.5 or dist20 <= 3:
            score += 7
        if 1.05 <= vol_ratio <= 2.5:
            score += 12; reasons.append(f'温和放量{vol_ratio:.2f}倍')
        elif vol_ratio >= 2.5:
            score += 5; risks.append('放量偏大')
        else:
            score += 6; risks.append('量能一般')
        if ma20_slope > 0.3:
            score += 10; reasons.append('MA20向上')
        elif ma20_slope >= -0.3:
            score += 7; reasons.append('MA20企稳')
        else:
            risks.append('MA20偏弱')
        if age <= 3:
            score += 12; reasons.append(f'520金叉{age}天')
        elif age <= 7:
            score += 9; reasons.append(f'520金叉{age}天')
        else:
            score += 5
        if 0.3 <= today_pct <= 3:
            score += 9; reasons.append('今日启动不追高')
        elif today_pct <= 5:
            score += 6
        else:
            score += 2; risks.append('今日涨幅偏大')

        # 20日涨停记忆作为加分，不作为硬条件，避免股票池过窄
        limit20 = 0
        for i in range(max(1, end - 20), end + 1):
            if self._is_limit_up(kline[i], closes[i-1], ''):
                limit20 += 1
        if limit20:
            score += min(10, 4 + limit20 * 2)
            reasons.append(f'20日涨停记忆{limit20}次')
        else:
            score += 3

        grade = 'S' if score >= 88 else 'A' if score >= 78 else 'B' if score >= 68 else 'C'
        return {
            'valid': True, 'mode': mode, 'score': min(100, round(score, 1)), 'grade': grade,
            'cross_age': age, 'touch_days': touch_days, 'touch_date': kline[touch_idx].get('date', ''),
            'ma5': round(cur_ma5, 3), 'ma20': round(cur_ma20, 3),
            'dist_ma5': round(dist5, 2), 'dist_ma20': round(dist20, 2),
            'today_pct': round(today_pct, 2), 'vol_ratio': round(vol_ratio, 2),
            'ma20_slope': round(ma20_slope, 2), 'limit20': limit20,
            'reasons': reasons[:8], 'risks': risks[:5],
        }

    def analyze(self, stock: Dict, kline: List[Dict]) -> Optional[Dict]:
        code = str(stock.get('code', ''))
        name = str(stock.get('name', ''))
        if not code.startswith(('600','601','603','605','000','001','002')):
            return None
        if 'ST' in name.upper() or '*ST' in name.upper():
            return None
        r = self.detect_pullback(kline)
        if not r.get('valid'):
            return None
        out = dict(r)
        out.update({'code': code, 'name': name, 'price': float(stock.get('price') or kline[-1].get('close', 0)),
                    'pct_chg': float(stock.get('pct_chg') or r['today_pct']),
                    'industry': stock.get('industry', ''), 'signal_source': 'AI-520回踩启动'})
        return out
