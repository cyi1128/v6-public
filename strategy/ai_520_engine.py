# -*- coding: utf-8 -*-
"""
AI-520动态选股雷达核心引擎
5日均线上穿20日均线金叉 + AI评分 + 股票池过滤
严格T+1，无未来函数
"""
import os
import sys
import time
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class AI520Engine:
    """AI-520动态选股雷达核心引擎"""

    # 行业排除列表（V2.7增强：白酒/啤酒/黄酒/葡萄酒/酒类/饮料/酒水）
    EXCLUDE_INDUSTRIES = ['房地产', '农业', '白酒', '啤酒', '黄酒', '葡萄酒', '酒类', '饮料', '酒水', '保险']

    # ============================================================
    # AI520_CONFIG 统一参数字典（V2.3 43条规范）
    # 所有参数集中管理，禁止魔法数字
    # ============================================================
    AI520_CONFIG = {
        # 一、时间窗口
        'START_CANDLE_LOOKBACK_MIN': 2,      # 启动阳线最早T-2
        'START_CANDLE_LOOKBACK_MAX': 8,      # 启动阳线最晚T-8
        'DEATH_CROSS_WINDOW': 5,              # 高位死叉观察窗口T-5~T
        'MIN_VALID_BARS': 20,                 # 最少有效交易日
        'EPS': 1e-8,                          # 浮点误差

        # 二、启动阳线
        'START_GAIN_MIN': 0.02,               # 启动阳线最低涨幅2.00%（包含）
        'START_GAIN_MAX': 0.09,               # 启动阳线最高涨幅9.00%（不包含）
        'START_BODY_MIN': 0.01,               # 启动阳线实体最低1.00%（包含）
        'UPPER_SHADOW_WARN': 0.40,            # 上影线警戒40%
        'UPPER_SHADOW_EXCLUDE': 0.50,         # 上影线排除50%（超过才排除）

        # 三、启动后表现
        'POST_START_GAIN_MAX': 0.25,          # 启动后累计涨幅上限25.00%（包含）
        'MAX_DRAWDOWN_MIN': -0.12,            # 启动后最大回撤下限-12.00%（包含）

        # 四、均线排列
        'MA_BULLISH_THRESHOLD': 0.002,        # 均线多头排列阈值0.20%（包含）

        # 五、均线斜率（3日变化率）
        'MA5_SLOPE_MIN': 0.005,               # MA5斜率最低0.50%（包含）
        'MA10_SLOPE_MIN': 0.003,              # MA10斜率最低0.30%（包含）
        'MA20_SLOPE_MIN': 0.002,              # MA20斜率最低0.20%（包含）
        'MA5_MA20_SLOPE_RATIO_MAX': 4.0,     # MA5/MA20斜率比上限4.0（包含）
        'MA10_MA20_SLOPE_RATIO_MAX': 3.0,    # MA13/MA20斜率比上限3.0（包含）

        # 六、回踩距离
        'PULLBACK_DIST_MAX': 0.015,            # 回踩距离上限2.00%（包含）
        'BREAKDOWN_THRESHOLD': 0.02,          # 跌破均线阈值5.00%（超过排除）

        # 七、回踩成交量
        'VOL_SHRINK_MAX': 0.80,                # 缩量回踩上限0.80倍（包含）
        'VOL_NORMAL_MAX': 1.20,                # 正常回踩上限1.20倍（包含）
        'VOL_EXPAND_MAX': 1.80,                # 放量回踩上限1.80倍（包含）

        # 八、单日跌幅
        'DAILY_DROP_EXCLUDE': -0.07,           # 单日跌幅排除-7.00%（包含）
        'DAILY_DROP_WARN': -0.05,              # 单日跌幅警戒-5.00%（包含）

        # 九、高位滞涨
        'STAGNATION_GAIN_MIN': 0.01,           # 滞涨累计涨幅上限1.00%
        'STAGNATION_VOL_RATIO': 1.50,          # 滞涨成交量倍数1.50

        # 十、评分等级
        'SCORE_S_MIN': 90,                      # S级最低90分
        'SCORE_A_MIN': 80,                      # A级最低80分
        'SCORE_B_MIN': 70,                      # B级最低70分
        'SCORE_C_MIN': 60,                      # C级最低60分

        # 十一、评分项
        'SCORE_START_CANDLE': 15,               # 非涨停放量阳启动基础分
        'SCORE_VOL_15_19': 5,                   # 放量1.50-1.99倍
        'SCORE_VOL_20_24': 8,                   # 放量2.00-2.49倍
        'SCORE_VOL_25_PLUS': 10,                # 放量>=2.50倍
        'SCORE_MA_BULLISH': 15,                 # MA5>MA13>MA20
        'SCORE_MA5_UP': 5,                       # MA5向上
        'SCORE_MA10_UP': 5,                      # MA10向上
        'SCORE_MA20_UP': 5,                      # MA20向上
        'SCORE_MA_PARALLEL': 10,                # 均线平行向上
        'SCORE_PULLBACK_MA5': 10,                # MA5回踩
        'SCORE_PULLBACK_MA20': 15,               # MA20回踩
        'SCORE_SHRINK_VOL': 10,                  # 缩量回踩
        'SCORE_RECLAIM_MA': 10,                  # 重新站稳均线
    }

    def __init__(self):
        pass

    # ==================== 均线计算 ====================

    def calc_ma(self, closes: List[float], period: int) -> List[Optional[float]]:
        """计算移动平均线，无未来函数"""
        result = []
        for i in range(len(closes)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(closes[i - period + 1:i + 1]) / period)
        return result

    def calc_ma_slope(self, ma_values: List[Optional[float]], periods: int = 5) -> Optional[float]:
        """计算MA斜率（最近periods天的变化率）"""
        valid = [(i, v) for i, v in enumerate(ma_values) if v is not None]
        if len(valid) < periods + 1:
            return None
        recent = valid[-periods:]
        first_val = recent[0][1]
        last_val = recent[-1][1]
        if first_val == 0:
            return None
        return (last_val - first_val) / first_val * 100

    # ==================== 520金叉判断 ====================

    def check_520_golden_cross(self, kline: List[Dict]) -> Dict:
        """
        判断520金叉状态
        严格定义：MA5 > MA20 AND REF(MA5,1) <= REF(MA20,1)

        Returns:
            {
                'has_cross': bool,           # 是否发生过金叉
                'cross_days_ago': int,       # 金叉发生在几天前（0=今天刚金叉）
                'ma5': float,                 # 当前MA5
                'ma20': float,                # 当前MA20
                'ma13': float,                # 当前MA10
                'ma5_prev': float,            # 昨日MA5
                'ma20_prev': float,           # 昨日MA20
                'ma5_slope': float,           # MA5斜率
                'ma20_slope': float,          # MA20斜率
                'ma20_trend': str,            # MA20趋势：向上/走平/下降
                'price_above_ma20': bool,     # 价格在MA20上方
                'cross_strength': float,      # 金叉强度（0-1）
            }
        """
        if len(kline) < 25:
            return {'has_cross': False, 'cross_days_ago': -1}

        closes = [k['close'] for k in kline]
        ma5 = self.calc_ma(closes, 5)
        ma13 = self.calc_ma(closes, 13)
        ma20 = self.calc_ma(closes, 20)

        # 找最近一次金叉
        cross_days_ago = -1
        for i in range(len(kline) - 1, max(20, len(kline) - 30), -1):
            if ma5[i] is None or ma20[i] is None or ma5[i-1] is None or ma20[i-1] is None:
                continue
            if ma5[i] > ma20[i] and ma5[i-1] <= ma20[i-1]:
                cross_days_ago = len(kline) - 1 - i
                break

        # 当前值
        cur_ma5 = ma5[-1] if ma5[-1] is not None else 0
        cur_ma10 = ma13[-1] if ma13[-1] is not None else 0
        cur_ma20 = ma20[-1] if ma20[-1] is not None else 0
        prev_ma5 = ma5[-2] if len(ma5) > 1 and ma5[-2] is not None else 0
        prev_ma20 = ma20[-2] if len(ma20) > 1 and ma20[-2] is not None else 0

        # MA斜率
        ma5_slope = self.calc_ma_slope(ma5, 5) or 0
        ma20_slope = self.calc_ma_slope(ma20, 5) or 0

        # MA20趋势
        if ma20_slope > 0.5:
            ma20_trend = '向上'
        elif ma20_slope < -0.5:
            ma20_trend = '下降'
        else:
            ma20_trend = '走平'

        # 价格在MA20上方
        price_above_ma20 = closes[-1] > cur_ma20 if cur_ma20 > 0 else False

        # 金叉强度
        cross_strength = 0
        if cur_ma5 > 0 and cur_ma20 > 0:
            cross_strength = min(1.0, (cur_ma5 - cur_ma20) / cur_ma20 * 100 / 3)  # 3%偏离为满分

        # 今天是否刚金叉
        today_cross = (cur_ma5 > cur_ma20 and prev_ma5 <= prev_ma20) if (cur_ma5 > 0 and cur_ma20 > 0 and prev_ma5 > 0 and prev_ma20 > 0) else False

        return {
            'has_cross': cross_days_ago >= 0 or today_cross,
            'cross_days_ago': 0 if today_cross else cross_days_ago,
            'today_cross': today_cross,
            'ma5': round(cur_ma5, 3),
            'ma13': round(cur_ma10, 3),
            'ma20': round(cur_ma20, 3),
            'ma5_prev': round(prev_ma5, 3),
            'ma20_prev': round(prev_ma20, 3),
            'ma5_slope': round(ma5_slope, 2),
            'ma20_slope': round(ma20_slope, 2),
            'ma20_trend': ma20_trend,
            'price_above_ma20': price_above_ma20,
            'cross_strength': round(cross_strength, 3),
        }

    # ==================== 涨停判断 ====================

    def count_limit_up(self, kline: List[Dict], days: int = 250) -> Tuple[int, List[str]]:
        """
        统计最近days天的涨停次数
        主板涨停约10%，考虑ST 5%
        """
        if len(kline) < 2:
            return 0, []

        limit_up_dates = []
        check_days = min(days, len(kline) - 1)
        for i in range(len(kline) - check_days, len(kline)):
            if kline[i-1]['close'] <= 0:
                continue
            pct = (kline[i]['close'] - kline[i-1]['close']) / kline[i-1]['close'] * 100
            # 主板涨停>=9.8%（考虑四舍五入）
            if pct >= 9.8:
                limit_up_dates.append(kline[i]['date'])

        return len(limit_up_dates), limit_up_dates

    def check_prev_day_limit_up(self, kline: List[Dict]) -> bool:
        """前一个交易日是否涨停"""
        if len(kline) < 2:
            return False
        prev = kline[-2]
        prev_prev = kline[-3] if len(kline) >= 3 else None
        if not prev_prev or prev_prev['close'] <= 0:
            return False
        pct = (prev['close'] - prev_prev['close']) / prev_prev['close'] * 100
        return pct >= 9.8

    # ==================== 价格位置计算 ====================

    def calc_price_position(self, kline: List[Dict]) -> Dict:
        """
        计算价格位置：距8个月最高价、距20日高点、10日新高
        K线不足时动态调整高点计算周期
        """
        if len(kline) < 20:
            return {}

        closes = [k['close'] for k in kline]
        highs = [k['high'] for k in kline]
        current_price = closes[-1]

        # 近8个月最高价（约160个交易日），K线不足时用可用最大周期
        months_8 = min(160, len(kline))
        high_8m = max(highs[-months_8:])
        dist_from_8m_high = (current_price / high_8m - 1) * 100 if high_8m > 0 else 0

        # 近20日最高价
        high_20d = max(highs[-20:])
        dist_from_20d_high = (current_price / high_20d - 1) * 100 if high_20d > 0 else 0

        # 10日新高（当前收盘价 > 过去10日最高收盘价）
        if len(closes) >= 11:
            high_10d_close = max(closes[-11:-1])  # 不含今天
            break_10d_high = current_price > high_10d_close
        else:
            break_10d_high = False

        return {
            'current_price': current_price,
            'high_8m': round(high_8m, 3),
            'high_8m_period': months_8,
            'dist_from_8m_high': round(dist_from_8m_high, 2),
            'high_20d': round(high_20d, 3),
            'dist_from_20d_high': round(dist_from_20d_high, 2),
            'break_10d_high': break_10d_high,
        }

    # ==================== 成交量分析 ====================

    def analyze_volume(self, kline: List[Dict]) -> Dict:
        """
        成交量分析：成交量比、健康放量/巨量冲高/放量滞涨
        """
        if len(kline) < 6:
            return {}

        volumes = [k['volume'] for k in kline]
        current_vol = volumes[-1]
        avg_vol_5 = sum(volumes[-6:-1]) / 5  # 不含今天
        vol_ratio = current_vol / avg_vol_5 if avg_vol_5 > 0 else 0

        # 成交量状态判断
        closes = [k['close'] for k in kline]
        current_close = closes[-1]
        prev_close = closes[-2]
        current_pct = (current_close - prev_close) / prev_close * 100 if prev_close > 0 else 0

        if vol_ratio >= 3 and current_pct < 2:
            vol_status = '放量滞涨'
        elif vol_ratio >= 2.5 and current_pct >= 5:
            vol_status = '巨量冲高'
        elif vol_ratio >= 1.2:
            vol_status = '健康放量'
        elif vol_ratio >= 0.8:
            vol_status = '正常'
        else:
            vol_status = '缩量'

        return {
            'current_vol': current_vol,
            'avg_vol_5': round(avg_vol_5, 0),
            'vol_ratio': round(vol_ratio, 2),
            'vol_status': vol_status,
        }

    # ==================== 股票池过滤 ====================

    def filter_stock_pool(self, stock_info: Dict, kline: List[Dict]) -> Tuple[bool, str]:
        """
        股票池过滤（全部真实数据计算）
        Returns: (是否通过, 失败原因)
        """
        code = stock_info.get('code', '')
        name = stock_info.get('name', '')
        price = stock_info.get('price', 0)
        industry = stock_info.get('industry', '')
        market_cap = stock_info.get('market_cap', 0)

        # 1. 主板过滤
        if not (code.startswith('60') or code.startswith('00')):
            return False, '非主板'

        # 2. ST过滤
        if 'ST' in name.upper() or '*ST' in name:
            return False, 'ST股票'

        # 3. 行业排除
        for excl in self.EXCLUDE_INDUSTRIES:
            if excl in industry:
                return False, f'排除行业:{industry}'

        # 4. 市值过滤（>=30亿，无上限）
        if market_cap > 0 and market_cap < 30:
            return False, f'市值不足30亿:{market_cap}亿'

        # 5. 价格过滤（V2.7：>=6元允许，<6元淘汰；<=60元避免高价股）
        if price < 6 or price >= 60:
            return False, f'价格不在6~60元:{price}'

        # 6. K线长度检查
        if len(kline) < 30:
            return False, f'K线不足30根:{len(kline)}'

        # 7. 8个月高点位置过滤（距离最高价在-15%以内，且不超过最高价5%）
        # K线不足时用可用最大周期计算
        pos = self.calc_price_position(kline)
        if pos:
            dist = pos.get('dist_from_8m_high', 0)
            if dist < -15 or dist > 5:
                return False, f'距高点不在-15%~+5%:{dist}%'

        # 8. 涨停次数>=3（用可用K线范围计算，至少需要60根K线）
        limit_days = min(250, len(kline))
        limit_count_1y, _ = self.count_limit_up(kline, limit_days)
        # 动态调整阈值：K线越少，阈值越低
        if limit_days >= 200:
            min_limit = 3
        elif limit_days >= 120:
            min_limit = 2
        else:
            min_limit = 1
        if limit_count_1y < min_limit:
            return False, f'涨停不足{min_limit}次({limit_days}天内{limit_count_1y}次)'

        # 9. 前一个交易日不能涨停
        if self.check_prev_day_limit_up(kline):
            return False, '前一日涨停'

        # 10. 520金叉检查（必须有金叉）
        cross = self.check_520_golden_cross(kline)
        if not cross.get('has_cross', False):
            return False, '无520金叉'

        # 11. 金叉发生在最近10个交易日内
        if cross.get('cross_days_ago', -1) > 10:
            return False, f'金叉发生过久:{cross["cross_days_ago"]}天前'

        return True, '通过'

    # ==================== AI评分模型 ====================

    def calc_ai_score(self, stock_info: Dict, kline: List[Dict],
                      sector_data: Optional[Dict] = None,
                      news_data: Optional[Dict] = None) -> Dict:
        """
        AI-520评分模型（满分100）
        1. 520金叉强度 20分
        2. 趋势 15分
        3. 价格位置 15分
        4. 成交量 15分
        5. 涨停记忆 10分
        6. 板块强度 15分
        7. 短线启动 10分
        """
        score_details = []
        total_score = 0
        reasons = []
        risks = []

        code = stock_info.get('code', '')
        price = stock_info.get('price', 0)
        pct_chg = stock_info.get('pct_chg', 0)

        # 1. 520金叉强度（20分）
        cross = self.check_520_golden_cross(kline)
        cross_score = 0
        if cross.get('today_cross', False):
            cross_score = 20  # 今天刚金叉满分
            reasons.append('520今日金叉')
        elif cross.get('cross_days_ago', -1) <= 3:
            cross_score = 15 + cross.get('cross_strength', 0) * 5
            reasons.append(f'520金叉{cross["cross_days_ago"]}天')
        elif cross.get('cross_days_ago', -1) <= 7:
            cross_score = 10 + cross.get('cross_strength', 0) * 5
        else:
            cross_score = 5
        cross_score = min(20, cross_score)
        total_score += cross_score
        score_details.append(f'520金叉:{cross_score:.0f}')

        # MA5/MA20斜率加分
        if cross.get('ma5_slope', 0) > 1:
            reasons.append('MA5向上')
        if cross.get('ma20_trend') == '向上':
            reasons.append('MA20向上')
        elif cross.get('ma20_trend') == '下降':
            risks.append('MA20下降')

        # 2. 趋势（15分）
        trend_score = 0
        ma5 = cross.get('ma5', 0)
        ma13 = cross.get('ma13', 0)
        ma20 = cross.get('ma20', 0)
        if ma5 > ma13 > ma20:
            trend_score = 15
            reasons.append('MA5>MA13>MA20多头')
        elif ma5 > ma13 and ma13 > ma20 * 0.99:
            trend_score = 12
        elif ma5 > ma20:
            trend_score = 8
        else:
            trend_score = 3
            risks.append('均线未多头')
        total_score += trend_score
        score_details.append(f'趋势:{trend_score:.0f}')

        # 3. 价格位置（15分）
        pos = self.calc_price_position(kline)
        pos_score = 0
        dist_8m = pos.get('dist_from_8m_high', 0)
        if -10 <= dist_8m <= 0:
            pos_score = 15
            reasons.append('位置合理(距高点-10%内)')
        elif -15 <= dist_8m < -10:
            pos_score = 10
        elif 0 < dist_8m <= 5:
            pos_score = 8
            risks.append('接近8个月高点')
        else:
            pos_score = 3
        total_score += pos_score
        score_details.append(f'位置:{pos_score:.0f}')

        # 4. 成交量（15分）
        vol = self.analyze_volume(kline)
        vol_score = 0
        vol_ratio = vol.get('vol_ratio', 0)
        vol_status = vol.get('vol_status', '')
        if vol_status == '健康放量':
            vol_score = 15
            reasons.append(f'健康放量({vol_ratio}倍)')
        elif vol_status == '正常':
            vol_score = 10
        elif vol_status == '缩量':
            vol_score = 6
            risks.append('缩量')
        elif vol_status == '巨量冲高':
            vol_score = 5
            risks.append('巨量冲高风险')
        elif vol_status == '放量滞涨':
            vol_score = 3
            risks.append('放量滞涨')
        total_score += vol_score
        score_details.append(f'成交量:{vol_score:.0f}')

        # 5. 涨停记忆（10分）
        limit_count_1y, _ = self.count_limit_up(kline, 250)
        limit_count_20d, limit_dates_20d = self.count_limit_up(kline, 20)
        limit_score = 0
        if limit_count_1y >= 10:
            limit_score = 10
        elif limit_count_1y >= 5:
            limit_score = 8
        elif limit_count_1y >= 3:
            limit_score = 6
        else:
            limit_score = 2
        # 近20日涨停加分
        if limit_count_20d >= 1:
            limit_score = min(10, limit_score + 2)
            reasons.append(f'近20日涨停{limit_count_20d}次')
        total_score += limit_score
        score_details.append(f'涨停记忆:{limit_score:.0f}')

        # 6. 板块强度（15分）
        sector_score = 0
        if sector_data:
            sector_pct = sector_data.get('sector_pct', 0)
            sector_rank = sector_data.get('sector_rank', 0)
            sector_limit_up = sector_data.get('sector_limit_up', 0)
            sector_fund_flow = sector_data.get('sector_fund_flow', 0)

            if sector_pct > 2:
                sector_score += 5
                reasons.append(f'板块强势({sector_pct:.1f}%)')
            elif sector_pct > 0:
                sector_score += 3

            if sector_rank > 0 and sector_rank <= 10:
                sector_score += 4
                reasons.append('板块排名前10')
            elif sector_rank > 0 and sector_rank <= 30:
                sector_score += 2

            if sector_limit_up >= 3:
                sector_score += 3
                reasons.append(f'板块涨停{sector_limit_up}家')
            elif sector_limit_up >= 1:
                sector_score += 1

            if sector_fund_flow > 0:
                sector_score += 3
                reasons.append('板块资金流入')
        else:
            sector_score = 5  # 无板块数据时给基础分
        sector_score = min(15, sector_score)
        total_score += sector_score
        score_details.append(f'板块:{sector_score:.0f}')

        # 7. 短线启动（10分）
        start_score = 0
        # 重新站上MA5
        if cross.get('ma5', 0) > 0 and price >= cross['ma5']:
            start_score += 3
            reasons.append('站上MA5')
        # 10日新高
        if pos.get('break_10d_high', False):
            start_score += 4
            reasons.append('创10日新高')
        # 阳线
        if len(kline) >= 2 and kline[-1]['close'] > kline[-1]['open']:
            start_score += 2
        # 涨幅合理（0.3%~7%）
        if 0.3 <= pct_chg <= 7:
            start_score += 1
            reasons.append(f'涨幅合理({pct_chg:.1f}%)')
        elif pct_chg > 7:
            risks.append(f'涨幅偏高({pct_chg:.1f}%)')
            start_score -= 1
        start_score = max(0, min(10, start_score))
        total_score += start_score
        score_details.append(f'短线启动:{start_score:.0f}')

        # 风险扣分
        risk_deduction = 0
        if pct_chg > 7:
            risk_deduction += 3
        if dist_8m > 0:
            risk_deduction += 2
        if vol_status == '巨量冲高':
            risk_deduction += 3
        if vol_status == '放量滞涨':
            risk_deduction += 2
        total_score = max(0, total_score - risk_deduction)

        # 信号等级
        if total_score >= 85:
            grade = 'S'
            grade_name = '重点启动'
        elif total_score >= 75:
            grade = 'A'
            grade_name = '启动确认'
        elif total_score >= 65:
            grade = 'B'
            grade_name = '观察'
        elif total_score >= 55:
            grade = 'C'
            grade_name = '低优先级观察'
        else:
            grade = 'D'
            grade_name = '不推送'

        return {
            'total_score': round(total_score, 1),
            'grade': grade,
            'grade_name': grade_name,
            'score_details': score_details,
            'reasons': reasons[:8],
            'risks': risks[:5],
            'cross_info': cross,
            'position_info': pos,
            'volume_info': vol,
            'limit_count_1y': limit_count_1y,
            'limit_count_20d': limit_count_20d,
            'risk_deduction': risk_deduction,
        }

    # ==================== MA5/MA20回踩启动模型 ====================

    def check_pullback_start(self, kline: List[Dict]) -> Dict:
        """
        AI-520回踩启动模型：MA5上穿MA20→温和上涨→回踩MA5/MA20→再启动
        Returns: {
            'has_pullback': bool,           # 是否发生有效回踩
            'pullback_type': str,            # MA5回踩/MA20回踩/无
            'cross_date': str,               # 金叉日期
            'cross_days_ago': int,           # 金叉发生在几天前
            'cross_gain_pct': float,         # 金叉后累计涨幅%
            'is_gentle_rise': bool,          # 是否温和上涨
            'has_extreme_rise': bool,        # 是否有连续暴涨
            'today_low': float,               # 今日最低价
            'today_close': float,             # 今日收盘价
            'ma5': float,                     # 当前MA5
            'ma20': float,                    # 当前MA20
            'dist_ma5_pct': float,            # 距离MA5%
            'dist_ma20_pct': float,           # 距离MA20%
            'reclaim_ma5': bool,              # 是否重新站回MA5
            'reclaim_ma20': bool,             # 是否重新站回MA20
            'is_shrink_volume': bool,         # 是否缩量回踩
            'vol_ratio': float,                # 今日量/5日均量
            'is_bullish_candle': bool,        # 是否止跌阳线
            'trend_intact': bool,              # 趋势是否未破坏（收盘>MA20）
            'pullback_score': float,           # 回踩质量评分0-100
            'pullback_grade': str,             # S/A/B/C
            'pullback_reasons': List[str],     # 回踩判断原因
        }
        """
        result = {
            'has_pullback': False, 'pullback_type': '无',
            'cross_date': '', 'cross_days_ago': -1, 'cross_gain_pct': 0,
            'is_gentle_rise': False, 'has_extreme_rise': False,
            'today_low': 0, 'today_close': 0, 'ma5': 0, 'ma20': 0,
            'dist_ma5_pct': 0, 'dist_ma20_pct': 0,
            'reclaim_ma5': False, 'reclaim_ma20': False,
            'is_shrink_volume': False, 'vol_ratio': 0,
            'is_bullish_candle': False, 'trend_intact': False,
            'pullback_score': 0, 'pullback_grade': 'D',
            'pullback_reasons': [],
        }

        if len(kline) < 25:
            return result

        try:
            # 1. 检查520金叉
            cross = self.check_520_golden_cross(kline)
            if not cross.get('has_cross'):
                result['pullback_reasons'].append('无520金叉')
                return result

            result['cross_days_ago'] = cross.get('cross_days_ago', -1)
            result['ma5'] = cross.get('ma5', 0)
            result['ma20'] = cross.get('ma20', 0)

            # 金叉必须发生在3-10天前（今天刚金叉不算回踩）
            if result['cross_days_ago'] < 2 or result['cross_days_ago'] > 10:
                result['pullback_reasons'].append(f'金叉时间不合适:{result["cross_days_ago"]}天前')
                return result

            # 2. 计算金叉后累计涨幅
            closes = [float(k.get('close', 0)) for k in kline]
            cross_idx = len(kline) - 1 - result['cross_days_ago']
            if cross_idx >= 0 and cross_idx < len(closes):
                cross_price = closes[cross_idx]
                current_price = closes[-1]
                if cross_price > 0:
                    result['cross_gain_pct'] = round((current_price - cross_price) / cross_price * 100, 2)

            # 3. 判断温和上涨（3%-15%）
            result['is_gentle_rise'] = 3 <= result['cross_gain_pct'] <= 15

            # 4. 检查是否有连续暴涨（金叉后任意3天内累计涨幅>20%或单日>9%连续2天）
            has_extreme = False
            for i in range(cross_idx, len(kline) - 1):
                if i + 2 < len(kline):
                    pct1 = (closes[i+1] - closes[i]) / closes[i] * 100 if closes[i] > 0 else 0
                    pct2 = (closes[i+2] - closes[i+1]) / closes[i+1] * 100 if closes[i+1] > 0 else 0
                    if pct1 > 9 and pct2 > 9:
                        has_extreme = True
                        break
            result['has_extreme_rise'] = has_extreme

            # 5. 今日回踩判断
            today = kline[-1]
            result['today_low'] = float(today.get('low', 0))
            result['today_close'] = float(today.get('close', 0))
            ma5 = result['ma5']
            ma20 = result['ma20']

            if ma5 > 0:
                result['dist_ma5_pct'] = round((result['today_low'] - ma5) / ma5 * 100, 2)
            if ma20 > 0:
                result['dist_ma20_pct'] = round((result['today_low'] - ma20) / ma20 * 100, 2)

            # 回踩MA5：最低价接近MA5（±1%）
            pullback_ma5 = ma5 > 0 and abs(result['dist_ma5_pct']) <= 1.0
            # 回踩MA20：最低价接近MA20（±1.5%）
            pullback_ma20 = ma20 > 0 and abs(result['dist_ma20_pct']) <= 1.5

            if not pullback_ma5 and not pullback_ma20:
                result['pullback_reasons'].append(f'未回踩均线(距MA5:{result["dist_ma5_pct"]}%, 距MA20:{result["dist_ma20_pct"]}%)')
                return result

            result['pullback_type'] = 'MA5回踩' if pullback_ma5 else 'MA20回踩'

            # 6. 趋势未破坏：收盘>MA20
            result['trend_intact'] = result['today_close'] > ma20 if ma20 > 0 else False
            if not result['trend_intact']:
                result['pullback_reasons'].append('跌破MA20，趋势破坏')
                return result

            # 7. 重新站回均线
            result['reclaim_ma5'] = result['today_close'] > ma5 if ma5 > 0 else False
            result['reclaim_ma20'] = result['today_close'] > ma20 if ma20 > 0 else False

            # 8. 缩量回踩
            volumes = [float(k.get('volume', 0)) for k in kline[-6:-1]]
            vol_5ma = sum(volumes) / len(volumes) if volumes else 0
            today_vol = float(today.get('volume', 0))
            result['vol_ratio'] = round(today_vol / vol_5ma, 2) if vol_5ma > 0 else 0
            result['is_shrink_volume'] = result['vol_ratio'] < 1.0

            # 9. 止跌阳线
            open_price = float(today.get('open', 0))
            result['is_bullish_candle'] = result['today_close'] > open_price

            # 10. 回踩质量评分
            score = 0
            reasons = []
            # MA5>MA20 (10分)
            if ma5 > ma20:
                score += 10
                reasons.append('MA5>MA20')
            # 金叉时间合理3-7天 (10分)
            if 2 <= result['cross_days_ago'] <= 7:
                score += 10
                reasons.append(f'金叉{result["cross_days_ago"]}天')
            # 温和上涨 (10分)
            if result['is_gentle_rise']:
                score += 10
                reasons.append(f'温和上涨{result["cross_gain_pct"]}%')
            # 无连续暴涨 (10分)
            if not result['has_extreme_rise']:
                score += 10
                reasons.append('无连续暴涨')
            # 回踩MA5精准 (10分)
            if pullback_ma5 and abs(result['dist_ma5_pct']) <= 0.5:
                score += 10
                reasons.append('精准回踩MA5')
            elif pullback_ma5:
                score += 7
                reasons.append('回踩MA5')
            # 回踩MA20 (10分)
            if pullback_ma20:
                score += 8
                reasons.append('回踩MA20')
            # 重新站回均线 (10分)
            if result['reclaim_ma5']:
                score += 10
                reasons.append('重新站回MA5')
            elif result['reclaim_ma20']:
                score += 6
                reasons.append('站回MA20')
            # 缩量回踩 (10分)
            if result['is_shrink_volume']:
                score += 10
                reasons.append(f'缩量回踩({result["vol_ratio"]})')
            # 止跌阳线 (10分)
            if result['is_bullish_candle']:
                score += 10
                reasons.append('止跌阳线')
            # 趋势完整 (10分)
            if result['trend_intact']:
                score += 10
                reasons.append('趋势未破')

            result['pullback_score'] = round(score, 1)
            result['pullback_reasons'] = reasons

            # 评级
            if score >= 85:
                result['pullback_grade'] = 'S'
            elif score >= 70:
                result['pullback_grade'] = 'A'
            elif score >= 55:
                result['pullback_grade'] = 'B'
            else:
                result['pullback_grade'] = 'C'

            # 有效回踩：至少B级且重新站回均线
            result['has_pullback'] = score >= 55 and (result['reclaim_ma5'] or result['reclaim_ma20'])

            return result

        except Exception as e:
            print(f"[AI520] 回踩启动模型计算失败: {e}")
            return result

    # ==================== 单只股票完整分析 ====================

    def analyze_stock(self, stock_info: Dict, kline: List[Dict],
                      sector_data: Optional[Dict] = None,
                      news_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        V2.6 单只股票完整分析：硬过滤 + AI520相似度评分
        取消强制全通过状态机，改为相似模式识别+综合评分
        Returns: 分析结果或None（未通过硬过滤）
        """
        # 硬过滤（ST/创业板/科创板/北交所/停牌/价格<6/一字板/极端暴涨/放量大跌/MA20严重向下等）
        passed, reason = self.filter_stock_pool(stock_info, kline)
        if not passed:
            return None

        # V2.6 AI520相似度评分（8个维度100分制，取消强制全通过）
        similarity = self.calc_ai520_similarity_score(stock_info, kline)

        # V2.7 买点评分（与AI520相似度分离，关注当前交易位置）
        try:
            from strategy.ai_520_buy_score import get_buy_score
            buy_score_result = get_buy_score().calc_buy_score(stock_info, kline)
        except Exception:
            buy_score_result = {'buy_score': 0, 'buy_grade': '暂不介入', 'dimension_scores': {}, 'buy_signals': [], 'buy_risks': []}

        # V2.4 AI520历史记忆状态机（作为参考信息，不作为准入条件）
        state_machine = self.analyze_state_machine(stock_info, kline)

        # V2.3 AI-520回踩启动模型（作为参考信息）
        ai520_v23 = self.check_ai520_v23(kline)

        # 合并结果
        result = {
            'code': stock_info.get('code', ''),
            'name': stock_info.get('name', ''),
            'price': stock_info.get('price', 0),
            'pct_chg': stock_info.get('pct_chg', 0),
            'industry': stock_info.get('industry', ''),
            'market_cap': stock_info.get('market_cap', 0),
            'filter_reason': reason,
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            # V2.6相似度评分（主评分）
            'ai520_score': similarity['total_score'],
            'ai520_grade': similarity['grade'],
            'ai520_similarity': similarity['similarity'],
            'ai520_dimension_scores': similarity['dimension_scores'],
            'ai520_matched_conditions': similarity['matched_conditions'],
            'ai520_missing_conditions': similarity['missing_conditions'],
            'ai520_risk_items': similarity['risk_items'],
            'trend_score': similarity['trend_score'],
            'memory_score': similarity['memory_score'],
            'gentle_score': similarity['gentle_score'],
            'pullback_score': similarity['pullback_score'],
            'strength_score': similarity['strength_score'],
            'kdj_score': similarity['kdj_score'],
            'position_score': similarity['position_score'],
            'volume_price_score': similarity['volume_price_score'],
            'ma5': similarity.get('ma5', 0),
            'ma13': similarity.get('ma13', 0),
            'ma20': similarity.get('ma20', 0),
            'dist_ma5': similarity.get('dist_ma5', 0),
            'dist_ma20': similarity.get('dist_ma20', 0),
            'vol_ratio': similarity.get('vol_ratio', 0),
            'kdj_k': similarity.get('kdj_k', 0),
            'kdj_d': similarity.get('kdj_d', 0),
            'kdj_j': similarity.get('kdj_j', 0),
            'limit_up_20d': similarity.get('limit_up_20d', 0),
            'limit_up_1y': similarity.get('limit_up_1y', 0),
            # V2.4状态机结果（参考信息）
            'ai520_state': state_machine.get('state', 'NONE'),
            'ai520_state_chain': state_machine.get('state_chain', []),
            'ai520_buy_point': state_machine.get('buy_point', False),
            'ai520_state_score': state_machine.get('state_score', 0),
            'ai520_state_grade': state_machine.get('state_grade', 'D'),
            'kdj_memory': state_machine.get('kdj_memory', {}),
            'limit_up_memory': state_machine.get('limit_up_memory', {}),
            'shrink_pullback': state_machine.get('shrink_pullback', {}),
            'bottom_fractal': state_machine.get('bottom_fractal', {}),
            'ma5_reclaim': state_machine.get('ma5_reclaim', {}),
            # V2.7买点评分（与AI520相似度分离）
            'buy_score': buy_score_result.get('buy_score', 0),
            'buy_grade': buy_score_result.get('buy_grade', '暂不介入'),
            'buy_dimension_scores': buy_score_result.get('dimension_scores', {}),
            'buy_signals': buy_score_result.get('buy_signals', []),
            'buy_risks': buy_score_result.get('buy_risks', []),
            # 兼容旧字段
            'total_score': similarity['total_score'],
            'score': similarity['total_score'],
            'grade': similarity['grade'],
        }
        # 合并V2.3 AI-520回踩启动模型结果
        result['ai520_v23'] = ai520_v23
        result['is_ai520_v23'] = ai520_v23.get('is_ai520', False)
        result['ai520_v23_type'] = ai520_v23.get('pullback_type', '无')
        result['ai520_v23_score'] = ai520_v23.get('score', 0)
        result['ai520_v23_grade'] = ai520_v23.get('grade', 'D')
        return result

    # ============================================================
    # V2.3 AI-520回踩启动模型（43条统一口径规范）
    # 放量阳线启动→温和上涨→均线平行向上→回踩MA5/MA20
    # ============================================================

    def _get_config(self, key: str):
        """获取AI520_CONFIG参数"""
        return self.AI520_CONFIG.get(key)

    def _calc_ma_v23(self, closes: List[float], period: int) -> List[Optional[float]]:
        """统一均线计算：收盘价简单移动平均SMA，无未来函数"""
        return self.calc_ma(closes, period)

    def _calc_vol_ratio_v23(self, volumes: List[float], idx: int) -> float:
        """统一成交量倍数：VOL(T)/平均VOL(T-1至T-5)，5日均量不含当天"""
        cfg = self.AI520_CONFIG
        if idx < 5:
            return 0
        # T-1至T-5共5天
        vol_5 = volumes[idx-5:idx]
        avg_vol = sum(vol_5) / 5 if len(vol_5) == 5 else 0
        if avg_vol <= cfg['EPS']:
            return 0  # 零成交量排除
        return volumes[idx] / avg_vol

    def _find_start_candle(self, kline: List[Dict]) -> Dict:
        """
        寻找启动阳线（T-2~T-8窗口，共7个交易日）
        条件：CLOSE>OPEN, 2.00%<=start_gain<9.00%, BODY>=1.00%, 上影线<=50%, 非涨停
        多根时：距离T最近>成交量倍数最高>start_gain最高
        Returns: {'found': bool, 'idx': int, 'date': str, 'start_gain': float, 'body_ratio': float, 'vol_ratio': float, 'is_limit_up': bool, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {'found': False, 'idx': -1, 'date': '', 'start_gain': 0, 'body_ratio': 0, 'vol_ratio': 0, 'is_limit_up': False, 'reject_reason': ''}

        n = len(kline)
        if n < cfg['MIN_VALID_BARS']:
            result['reject_reason'] = f'K线不足{cfg["MIN_VALID_BARS"]}根'
            return result

        closes = [float(k.get('close', 0)) for k in kline]
        volumes = [float(k.get('volume', 0)) for k in kline]
        t_idx = n - 1  # 当前交易日T

        candidates = []
        # T-2~T-8窗口
        for offset in range(cfg['START_CANDLE_LOOKBACK_MIN'], cfg['START_CANDLE_LOOKBACK_MAX'] + 1):
            idx = t_idx - offset
            if idx < 1:
                continue
            bar = kline[idx]
            open_p = float(bar.get('open', 0))
            high_p = float(bar.get('high', 0))
            low_p = float(bar.get('low', 0))
            close_p = float(bar.get('close', 0))
            pre_close = closes[idx - 1] if idx > 0 else 0

            if pre_close <= cfg['EPS'] or open_p <= cfg['EPS']:
                continue

            # 涨跌幅：CLOSE/PRE_CLOSE-1
            start_gain = close_p / pre_close - 1
            # 实体：(CLOSE-OPEN)/OPEN
            body_ratio = (close_p - open_p) / open_p
            # 振幅
            range_p = high_p - low_p
            if range_p <= cfg['EPS']:
                continue
            # 上影线占比
            upper_shadow = high_p - max(open_p, close_p)
            upper_shadow_ratio = upper_shadow / range_p

            # 是否涨停：CLOSE>=LIMIT_UP（优先使用真实涨停价）
            limit_up = float(bar.get('limit_up', 0))
            is_limit_up = False
            if limit_up > 0:
                is_limit_up = close_p >= limit_up - cfg['EPS']
            else:
                # fallback：涨幅>=9.8%视为涨停（主板10%）
                is_limit_up = start_gain >= 0.098

            # 启动阳线条件
            if (close_p > open_p and
                start_gain >= cfg['START_GAIN_MIN'] - cfg['EPS'] and
                start_gain < cfg['START_GAIN_MAX'] - cfg['EPS'] and
                body_ratio >= cfg['START_BODY_MIN'] - cfg['EPS'] and
                upper_shadow_ratio <= cfg['UPPER_SHADOW_EXCLUDE'] + cfg['EPS'] and
                not is_limit_up):

                vol_ratio = self._calc_vol_ratio_v23(volumes, idx)
                candidates.append({
                    'idx': idx,
                    'date': bar.get('date', ''),
                    'start_gain': start_gain,
                    'body_ratio': body_ratio,
                    'vol_ratio': vol_ratio,
                    'is_limit_up': is_limit_up,
                    'offset': offset,
                })

        if not candidates:
            result['reject_reason'] = 'T-2~T-8无合格启动阳线'
            return result

        # 多根选择：距离T最近(offset最小)>成交量倍数最高>start_gain最高
        candidates.sort(key=lambda x: (x['offset'], -x['vol_ratio'], -x['start_gain']))
        best = candidates[0]
        result.update({
            'found': True,
            'idx': best['idx'],
            'date': best['date'],
            'start_gain': best['start_gain'],
            'body_ratio': best['body_ratio'],
            'vol_ratio': best['vol_ratio'],
            'is_limit_up': best['is_limit_up'],
        })
        return result

    def _check_post_start_performance(self, kline: List[Dict], start_idx: int) -> Dict:
        """
        检查启动后表现：累计涨幅<=25%, 最大回撤>=-12%
        Returns: {'post_start_gain': float, 'max_drawdown': float, 'passed': bool, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {'post_start_gain': 0, 'max_drawdown': 0, 'passed': False, 'reject_reason': ''}

        if start_idx < 0 or start_idx >= len(kline) - 1:
            result['reject_reason'] = '启动阳线索引无效'
            return result

        start_close = float(kline[start_idx].get('close', 0))
        if start_close <= cfg['EPS']:
            result['reject_reason'] = '启动阳线收盘价无效'
            return result

        # 启动后到T日
        max_drawdown = 0
        for i in range(start_idx + 1, len(kline)):
            close_i = float(kline[i].get('close', 0))
            drawdown_i = close_i / start_close - 1
            if drawdown_i < max_drawdown:
                max_drawdown = drawdown_i

        current_close = float(kline[-1].get('close', 0))
        post_start_gain = current_close / start_close - 1

        result['post_start_gain'] = post_start_gain
        result['max_drawdown'] = max_drawdown

        # 硬性条件
        if post_start_gain > cfg['POST_START_GAIN_MAX'] + cfg['EPS']:
            result['reject_reason'] = f'启动后累计涨幅{post_start_gain*100:.2f}%>25%'
            return result
        if max_drawdown < cfg['MAX_DRAWDOWN_MIN'] - cfg['EPS']:
            result['reject_reason'] = f'启动后最大回撤{max_drawdown*100:.2f}%<-12%'
            return result

        result['passed'] = True
        return result

    def _check_death_cross(self, ma5: List[Optional[float]], ma13: List[Optional[float]], ma20: List[Optional[float]]) -> Dict:
        """
        检查高位死叉：T-5~T最近5个交易日，任意MA5死叉MA10/MA5死叉MA20/MA10死叉MA20
        死叉定义：前一日>=，当日<
        Returns: {'has_death_cross': bool, 'death_cross_type': str}
        """
        cfg = self.AI520_CONFIG
        result = {'has_death_cross': False, 'death_cross_type': ''}

        n = len(ma5)
        if n < 2:
            return result

        window = cfg['DEATH_CROSS_WINDOW']
        start = max(1, n - window)

        for i in range(start, n):
            # MA5死叉MA10
            if (ma5[i-1] is not None and ma13[i-1] is not None and
                ma5[i] is not None and ma13[i] is not None):
                if ma5[i-1] >= ma13[i-1] - cfg['EPS'] and ma5[i] < ma13[i] - cfg['EPS']:
                    result['has_death_cross'] = True
                    result['death_cross_type'] = 'MA5死叉MA10'
                    return result

            # MA5死叉MA20
            if (ma5[i-1] is not None and ma20[i-1] is not None and
                ma5[i] is not None and ma20[i] is not None):
                if ma5[i-1] >= ma20[i-1] - cfg['EPS'] and ma5[i] < ma20[i] - cfg['EPS']:
                    result['has_death_cross'] = True
                    result['death_cross_type'] = 'MA5死叉MA20'
                    return result

            # MA10死叉MA20
            if (ma13[i-1] is not None and ma20[i-1] is not None and
                ma13[i] is not None and ma20[i] is not None):
                if ma13[i-1] >= ma20[i-1] - cfg['EPS'] and ma13[i] < ma20[i] - cfg['EPS']:
                    result['has_death_cross'] = True
                    result['death_cross_type'] = 'MA10死叉MA20'
                    return result

        return result

    def _check_ma_trend(self, ma5: List[Optional[float]], ma13: List[Optional[float]], ma20: List[Optional[float]]) -> Dict:
        """
        检查均线趋势：多头排列+3日斜率+平行向上
        Returns: {'ma_bullish': bool, 'ma5_slope': float, 'ma10_slope': float, 'ma20_slope': float, 'parallel_up': bool, 'passed': bool, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {'ma_bullish': False, 'ma5_slope': 0, 'ma10_slope': 0, 'ma20_slope': 0, 'parallel_up': False, 'passed': False, 'reject_reason': ''}

        n = len(ma5)
        if n < 4:
            result['reject_reason'] = '均线数据不足'
            return result

        # 当前均线值
        ma5_t = ma5[-1]
        ma10_t = ma13[-1]
        ma20_t = ma20[-1]
        if ma5_t is None or ma10_t is None or ma20_t is None:
            result['reject_reason'] = '当前均线值无效'
            return result

        # 多头排列：MA5>=MA13*1.002 且 MA13>=MA20*1.002
        ma_bullish = (ma5_t >= ma10_t * (1 + cfg['MA_BULLISH_THRESHOLD']) - cfg['EPS'] and
                      ma10_t >= ma20_t * (1 + cfg['MA_BULLISH_THRESHOLD']) - cfg['EPS'])
        result['ma_bullish'] = ma_bullish

        # 3日斜率：MA(T)/MA(T-3)-1
        def calc_slope_3day(ma_list):
            if len(ma_list) < 4 or ma_list[-1] is None or ma_list[-4] is None:
                return 0
            if ma_list[-4] <= cfg['EPS']:
                return 0
            return ma_list[-1] / ma_list[-4] - 1

        ma5_slope = calc_slope_3day(ma5)
        ma10_slope = calc_slope_3day(ma13)
        ma20_slope = calc_slope_3day(ma20)
        result['ma5_slope'] = ma5_slope
        result['ma10_slope'] = ma10_slope
        result['ma20_slope'] = ma20_slope

        # 斜率条件
        if ma5_slope < cfg['MA5_SLOPE_MIN'] - cfg['EPS']:
            result['reject_reason'] = f'MA5斜率{ma5_slope*100:.2f}%<0.50%'
            return result
        if ma10_slope < cfg['MA10_SLOPE_MIN'] - cfg['EPS']:
            result['reject_reason'] = f'MA10斜率{ma10_slope*100:.2f}%<0.30%'
            return result
        if ma20_slope < cfg['MA20_SLOPE_MIN'] - cfg['EPS']:
            result['reject_reason'] = f'MA20斜率{ma20_slope*100:.2f}%<0.20%'
            return result

        # 平行向上：MA5/MA20斜率比<=4.0, MA13/MA20斜率比<=3.0
        if ma20_slope <= cfg['EPS']:
            result['reject_reason'] = 'MA20斜率<=0，非平行向上'
            return result
        ratio_5_20 = ma5_slope / ma20_slope if ma20_slope > 0 else 999
        ratio_10_20 = ma10_slope / ma20_slope if ma20_slope > 0 else 999
        parallel_up = (ratio_5_20 <= cfg['MA5_MA20_SLOPE_RATIO_MAX'] + cfg['EPS'] and
                       ratio_10_20 <= cfg['MA10_MA20_SLOPE_RATIO_MAX'] + cfg['EPS'])
        result['parallel_up'] = parallel_up

        if not parallel_up:
            result['reject_reason'] = f'均线非平行向上(5/20={ratio_5_20:.2f},10/20={ratio_10_20:.2f})'
            return result

        result['passed'] = True
        return result

    def _check_pullback_v23(self, kline: List[Dict], ma5: List[Optional[float]], ma20: List[Optional[float]]) -> Dict:
        """
        检查回踩：MA5回踩或MA20回踩，距离<=2%，收盘>=均线*0.95
        同时满足时优先级MA20>MA5
        Returns: {'pullback_type': str, 'dist_ma5': float, 'dist_ma20': float, 'reclaim_ma5': bool, 'reclaim_ma20': bool, 'vol_ratio': float, 'is_shrink': bool, 'passed': bool, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {'pullback_type': '无', 'dist_ma5': 0, 'dist_ma20': 0, 'reclaim_ma5': False, 'reclaim_ma20': False, 'vol_ratio': 0, 'is_shrink': False, 'passed': False, 'reject_reason': ''}

        if not kline or not ma5 or not ma20:
            result['reject_reason'] = '数据无效'
            return result

        today = kline[-1]
        close_t = float(today.get('close', 0))
        low_t = float(today.get('low', 0))
        open_t = float(today.get('open', 0))
        ma5_t = ma5[-1]
        ma20_t = ma20[-1]

        if ma5_t is None or ma20_t is None or close_t <= cfg['EPS']:
            result['reject_reason'] = '均线或收盘价无效'
            return result

        # 距离：abs(CLOSE-MA)/MA
        dist_ma5 = abs(close_t - ma5_t) / ma5_t
        dist_ma20 = abs(close_t - ma20_t) / ma20_t
        result['dist_ma5'] = dist_ma5
        result['dist_ma20'] = dist_ma20

        # 重新站回：CLOSE>=MA 且 CLOSE>=OPEN
        reclaim_ma5 = close_t >= ma5_t - cfg['EPS'] and close_t >= open_t - cfg['EPS']
        reclaim_ma20 = close_t >= ma20_t - cfg['EPS'] and close_t >= open_t - cfg['EPS']
        result['reclaim_ma5'] = reclaim_ma5
        result['reclaim_ma20'] = reclaim_ma20

        # 成交量倍数
        volumes = [float(k.get('volume', 0)) for k in kline]
        vol_ratio = self._calc_vol_ratio_v23(volumes, len(kline) - 1)
        result['vol_ratio'] = vol_ratio
        result['is_shrink'] = vol_ratio > 0 and vol_ratio <= cfg['VOL_SHRINK_MAX'] + cfg['EPS']

        # MA5回踩：距离<=2% 且 收盘>=MA5*0.95
        pullback_ma5 = (dist_ma5 <= cfg['PULLBACK_DIST_MAX'] + cfg['EPS'] and
                        close_t >= ma5_t * (1 - cfg['BREAKDOWN_THRESHOLD']) - cfg['EPS'])
        # MA20回踩：距离<=2% 且 收盘>=MA20*0.95
        pullback_ma20 = (dist_ma20 <= cfg['PULLBACK_DIST_MAX'] + cfg['EPS'] and
                         close_t >= ma20_t * (1 - cfg['BREAKDOWN_THRESHOLD']) - cfg['EPS'])

        if not pullback_ma5 and not pullback_ma20:
            result['reject_reason'] = f'未回踩MA5/MA20(距MA5={dist_ma5*100:.2f}%,距MA20={dist_ma20*100:.2f}%)'
            return result

        # 同时满足时优先级MA20>MA5
        if pullback_ma20:
            result['pullback_type'] = 'MA20回踩'
        else:
            result['pullback_type'] = 'MA5回踩'

        # 放量下杀排除：VOL_RATIO>1.80 且 CLOSE<OPEN
        if vol_ratio > cfg['VOL_EXPAND_MAX'] + cfg['EPS'] and close_t < open_t - cfg['EPS']:
            result['reject_reason'] = f'放量下杀(量比{vol_ratio:.2f}>1.80且收阴)'
            return result

        result['passed'] = True
        return result

    def _check_daily_drop(self, kline: List[Dict]) -> Dict:
        """
        检查当前单日跌幅：<=-7%排除，-7%~-5%且放量>1.8排除
        Returns: {'daily_change': float, 'passed': bool, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {'daily_change': 0, 'passed': False, 'reject_reason': ''}

        if len(kline) < 2:
            result['reject_reason'] = 'K线不足'
            return result

        close_t = float(kline[-1].get('close', 0))
        pre_close = float(kline[-2].get('close', 0))
        if pre_close <= cfg['EPS']:
            result['reject_reason'] = '前收盘价无效'
            return result

        daily_change = close_t / pre_close - 1
        result['daily_change'] = daily_change

        if daily_change <= cfg['DAILY_DROP_EXCLUDE'] - cfg['EPS']:
            result['reject_reason'] = f'单日跌幅{daily_change*100:.2f}%<=-7%'
            return result

        # -7%~-5%且放量>1.8排除
        if (daily_change > cfg['DAILY_DROP_EXCLUDE'] and
            daily_change <= cfg['DAILY_DROP_WARN'] - cfg['EPS']):
            volumes = [float(k.get('volume', 0)) for k in kline]
            vol_ratio = self._calc_vol_ratio_v23(volumes, len(kline) - 1)
            if vol_ratio > cfg['VOL_EXPAND_MAX'] + cfg['EPS']:
                result['reject_reason'] = f'单日跌幅{daily_change*100:.2f}%且放量{vol_ratio:.2f}>1.8'
                return result

        result['passed'] = True
        return result

    def _calc_ai520_score_v23(self, kline: List[Dict], start_result: Dict, ma_trend: Dict, pullback: Dict) -> Dict:
        """
        V2.3评分标准固定化
        基础分：非涨停放量阳启动15分
        放量倍数：1.50-1.99+5, 2.00-2.49+8, >=2.50+10
        均线：MA5>MA13>MA20+15, MA5向上+5, MA10向上+5, MA20向上+5, 平行向上+10
        回踩：MA5回踩+10, MA20回踩+15, 缩量回踩+10, 重新站稳+10
        总分100封顶
        Returns: {'score': float, 'grade': str, 'score_details': Dict}
        """
        cfg = self.AI520_CONFIG
        score = 0
        details = {}

        # 1. 非涨停放量阳启动基础分
        if start_result.get('found'):
            score += cfg['SCORE_START_CANDLE']
            details['启动阳线'] = cfg['SCORE_START_CANDLE']

            # 2. 放量倍数
            vol_ratio = start_result.get('vol_ratio', 0)
            if vol_ratio >= 2.50:
                score += cfg['SCORE_VOL_25_PLUS']
                details['放量>=2.5倍'] = cfg['SCORE_VOL_25_PLUS']
            elif vol_ratio >= 2.00:
                score += cfg['SCORE_VOL_20_24']
                details['放量2.0-2.49倍'] = cfg['SCORE_VOL_20_24']
            elif vol_ratio >= 1.50:
                score += cfg['SCORE_VOL_15_19']
                details['放量1.5-1.99倍'] = cfg['SCORE_VOL_15_19']

        # 3. 均线
        if ma_trend.get('ma_bullish'):
            score += cfg['SCORE_MA_BULLISH']
            details['MA5>MA13>MA20'] = cfg['SCORE_MA_BULLISH']
        if ma_trend.get('ma5_slope', 0) > 0:
            score += cfg['SCORE_MA5_UP']
            details['MA5向上'] = cfg['SCORE_MA5_UP']
        if ma_trend.get('ma10_slope', 0) > 0:
            score += cfg['SCORE_MA10_UP']
            details['MA10向上'] = cfg['SCORE_MA10_UP']
        if ma_trend.get('ma20_slope', 0) > 0:
            score += cfg['SCORE_MA20_UP']
            details['MA20向上'] = cfg['SCORE_MA20_UP']
        if ma_trend.get('parallel_up'):
            score += cfg['SCORE_MA_PARALLEL']
            details['均线平行向上'] = cfg['SCORE_MA_PARALLEL']

        # 4. 回踩
        pullback_type = pullback.get('pullback_type', '无')
        if pullback_type == 'MA5回踩':
            score += cfg['SCORE_PULLBACK_MA5']
            details['MA5回踩'] = cfg['SCORE_PULLBACK_MA5']
        elif pullback_type == 'MA20回踩':
            score += cfg['SCORE_PULLBACK_MA20']
            details['MA20回踩'] = cfg['SCORE_PULLBACK_MA20']

        if pullback.get('is_shrink'):
            score += cfg['SCORE_SHRINK_VOL']
            details['缩量回踩'] = cfg['SCORE_SHRINK_VOL']

        if pullback_type == 'MA5回踩' and pullback.get('reclaim_ma5'):
            score += cfg['SCORE_RECLAIM_MA']
            details['重新站稳MA5'] = cfg['SCORE_RECLAIM_MA']
        elif pullback_type == 'MA20回踩' and pullback.get('reclaim_ma20'):
            score += cfg['SCORE_RECLAIM_MA']
            details['重新站稳MA20'] = cfg['SCORE_RECLAIM_MA']

        # 总分100封顶
        score = min(score, 100)

        # 等级
        if score >= cfg['SCORE_S_MIN']:
            grade = 'S'
        elif score >= cfg['SCORE_A_MIN']:
            grade = 'A'
        elif score >= cfg['SCORE_B_MIN']:
            grade = 'B'
        elif score >= cfg['SCORE_C_MIN']:
            grade = 'C'
        else:
            grade = 'D'

        return {'score': round(score, 1), 'grade': grade, 'score_details': details}

    def check_ai520_v23(self, kline: List[Dict]) -> Dict:
        """
        V2.3 AI-520回踩启动模型主入口（43条统一口径规范）
        流程：数据有效性→硬性排除→启动阳线→启动后表现→均线趋势→高位死叉→单日跌幅→回踩→评分
        Returns: {'is_ai520': bool, 'pullback_type': str, 'score': float, 'grade': str, 'start_candle': Dict, 'post_start': Dict, 'ma_trend': Dict, 'pullback': Dict, 'score_details': Dict, 'reject_reason': str}
        """
        cfg = self.AI520_CONFIG
        result = {
            'is_ai520': False, 'pullback_type': '无', 'score': 0, 'grade': 'D',
            'start_candle': {}, 'post_start': {}, 'ma_trend': {}, 'pullback': {},
            'score_details': {}, 'reject_reason': '',
        }

        # 0. 数据有效性
        if not kline or len(kline) < cfg['MIN_VALID_BARS']:
            result['reject_reason'] = f'有效K线不足{cfg["MIN_VALID_BARS"]}根'
            return result

        closes = [float(k.get('close', 0)) for k in kline]
        # 检查必要数据
        for k in kline[-20:]:
            if (float(k.get('open', 0)) <= 0 or float(k.get('high', 0)) <= 0 or
                float(k.get('low', 0)) <= 0 or float(k.get('close', 0)) <= 0 or
                float(k.get('volume', 0)) <= 0):
                result['reject_reason'] = '最近20根K线存在缺失数据'
                return result

        # 计算均线
        ma5 = self._calc_ma_v23(closes, 5)
        ma13 = self._calc_ma_v23(closes, 13)
        ma20 = self._calc_ma_v23(closes, 20)

        # 1. 单日跌幅硬性排除
        daily_drop = self._check_daily_drop(kline)
        if not daily_drop['passed']:
            result['reject_reason'] = daily_drop['reject_reason']
            return result

        # 2. 高位死叉硬性排除
        death_cross = self._check_death_cross(ma5, ma13, ma20)
        if death_cross['has_death_cross']:
            result['reject_reason'] = f'高位死叉:{death_cross["death_cross_type"]}'
            return result

        # 3. 寻找启动阳线
        start_result = self._find_start_candle(kline)
        if not start_result['found']:
            result['reject_reason'] = start_result['reject_reason']
            return result
        result['start_candle'] = start_result

        # 4. 启动后表现（累计涨幅<=25%, 最大回撤>=-12%）
        post_start = self._check_post_start_performance(kline, start_result['idx'])
        if not post_start['passed']:
            result['reject_reason'] = post_start['reject_reason']
            return result
        result['post_start'] = post_start

        # 5. 均线趋势（多头排列+3日斜率+平行向上）
        ma_trend = self._check_ma_trend(ma5, ma13, ma20)
        if not ma_trend['passed']:
            result['reject_reason'] = ma_trend['reject_reason']
            return result
        result['ma_trend'] = ma_trend

        # 6. 回踩检查（MA5/MA20）
        pullback = self._check_pullback_v23(kline, ma5, ma20)
        if not pullback['passed']:
            result['reject_reason'] = pullback['reject_reason']
            return result
        result['pullback'] = pullback

        # 7. 评分
        score_result = self._calc_ai520_score_v23(kline, start_result, ma_trend, pullback)
        result['score'] = score_result['score']
        result['grade'] = score_result['grade']
        result['score_details'] = score_result['score_details']
        result['pullback_type'] = pullback['pullback_type']

        # 8. 等级过滤：>=B级(70分)才产生信号
        if result['score'] < cfg['SCORE_B_MIN']:
            result['reject_reason'] = f'评分{result["score"]}<70分'
            return result

        result['is_ai520'] = True
        return result

    # ============================================================
    # V2.4 AI520历史记忆状态机
    # KDJ低位记忆→20日涨停记忆→倍量启动→温和上涨→缩量回踩→MA5/MA20→底分型→重新站MA5→买点
    # ============================================================

    def calc_kdj(self, kline: List[Dict], n: int = 13, m1: int = 3, m2: int = 3) -> Dict:
        """
        计算KDJ(13,3,3)，返回每根K线的K/D/J值数组
        标准KDJ算法：RSV=(CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100
        K=SMA(RSV,M1,1), D=SMA(K,M2,1), J=3*K-2*D
        """
        result = {'k': [], 'd': [], 'j': [], 'current_k': 50, 'current_d': 50, 'current_j': 50}
        if not kline or len(kline) < n:
            return result
        try:
            highs = [float(k.get('high', 0)) for k in kline]
            lows = [float(k.get('low', 0)) for k in kline]
            closes = [float(k.get('close', 0)) for k in kline]
            k_val = 50.0
            d_val = 50.0
            for i in range(len(kline)):
                if i < n - 1:
                    result['k'].append(50.0)
                    result['d'].append(50.0)
                    result['j'].append(50.0)
                    continue
                # 计算RSV
                high_n = max(highs[i-n+1:i+1])
                low_n = min(lows[i-n+1:i+1])
                if high_n - low_n < 1e-8:
                    rsv = 50.0
                else:
                    rsv = (closes[i] - low_n) / (high_n - low_n) * 100
                # K = (M1-1)/M1 * 前K + 1/M1 * RSV (SMA(M1,1))
                k_val = (m1 - 1) / m1 * k_val + 1 / m1 * rsv
                # D = (M2-1)/M2 * 前D + 1/M2 * K
                d_val = (m2 - 1) / m2 * d_val + 1 / m2 * k_val
                j_val = 3 * k_val - 2 * d_val
                result['k'].append(round(k_val, 2))
                result['d'].append(round(d_val, 2))
                result['j'].append(round(j_val, 2))
            if result['k']:
                result['current_k'] = result['k'][-1]
                result['current_d'] = result['d'][-1]
                result['current_j'] = result['j'][-1]
        except Exception as e:
            print(f"[AI520_STATE] KDJ计算异常: {e}", flush=True)
        return result

    def check_kdj_memory(self, kline: List[Dict], lookback_days: int = 10, j_threshold: float = 15.0) -> Dict:
        """
        KDJ历史低位记忆：过去5~10个交易日曾经出现J<=15
        不要求今天J<=15，只要历史出现过就形成LOW_KDJ_MEMORY
        Returns: {'has_memory': bool, 'memory_date': str, 'lowest_j': float, 'days_ago': int, 'current_j': float}
        """
        result = {'has_memory': False, 'memory_date': '', 'lowest_j': 100.0, 'days_ago': 0, 'current_j': 50.0}
        try:
            kdj = self.calc_kdj(kline, n=13, m1=3, m2=3)
            result['current_j'] = kdj.get('current_j', 50.0)
            j_vals = kdj.get('j', [])
            if not j_vals or len(j_vals) < 5:
                return result
            # 检查过去lookback_days天（不含今天）
            start_idx = max(0, len(j_vals) - lookback_days - 1)
            end_idx = len(j_vals) - 1  # 不含今天
            lowest_j = 100.0
            lowest_idx = -1
            for i in range(start_idx, end_idx):
                if j_vals[i] < lowest_j:
                    lowest_j = j_vals[i]
                    lowest_idx = i
            if lowest_idx >= 0 and lowest_j <= j_threshold:
                result['has_memory'] = True
                result['lowest_j'] = round(lowest_j, 2)
                result['days_ago'] = len(j_vals) - 1 - lowest_idx
                if lowest_idx < len(kline):
                    result['memory_date'] = kline[lowest_idx].get('date', '')
                print(f"[AI520_STATE] KDJ低位记忆: J={lowest_j:.1f} ({result['days_ago']}天前), 当前J={result['current_j']:.1f}", flush=True)
        except Exception as e:
            print(f"[AI520_STATE] KDJ记忆检查异常: {e}", flush=True)
        return result

    def check_limit_up_memory(self, kline: List[Dict], days: int = 20) -> Dict:
        """
        20日涨停记忆：过去20个交易日内曾出现涨停
        Returns: {'has_memory': bool, 'limit_up_date': str, 'days_ago': int, 'count_20d': int}
        """
        result = {'has_memory': False, 'limit_up_date': '', 'days_ago': 0, 'count_20d': 0}
        try:
            count, dates = self.count_limit_up(kline, days)
            result['count_20d'] = count
            if count > 0 and dates:
                result['has_memory'] = True
                result['limit_up_date'] = dates[-1] if dates else ''
                # 计算days_ago
                for i, k in enumerate(reversed(kline)):
                    if k.get('date', '') == result['limit_up_date']:
                        result['days_ago'] = i
                        break
                print(f"[AI520_STATE] 20日涨停记忆: {count}次, 最近{result['days_ago']}天前 {result['limit_up_date']}", flush=True)
        except Exception as e:
            print(f"[AI520_STATE] 涨停记忆检查异常: {e}", flush=True)
        return result

    def check_shrink_pullback(self, kline: List[Dict], start_idx: int = -1) -> Dict:
        """
        缩量回踩核心定义：当前回踩成交量 < V0（倍量启动前一天成交量）
        不是简单"当前成交量<5日均量"，而是与启动基准量V0比较
        Args:
            start_idx: 倍量启动K线索引，-1表示自动查找
        Returns: {'is_shrink': bool, 'current_volume': float, 'baseline_v0': float, 'volume_vs_v0': float}
        """
        result = {'is_shrink': False, 'current_volume': 0, 'baseline_v0': 0, 'volume_vs_v0': 0}
        try:
            volumes = [float(k.get('volume', 0)) for k in kline]
            if len(volumes) < 3:
                return result
            result['current_volume'] = volumes[-1]
            # 查找V0：如果有启动索引，V0=启动前一天成交量；否则自动找近期最大成交量前一天
            if start_idx > 0 and start_idx < len(volumes):
                result['baseline_v0'] = volumes[start_idx - 1] if start_idx > 0 else volumes[0]
            else:
                # 自动查找：最近10天内最大成交量的前一天作为V0参考
                recent_vols = volumes[-10:] if len(volumes) >= 10 else volumes
                max_idx = recent_vols.index(max(recent_vols))
                v0_idx = len(volumes) - len(recent_vols) + max_idx - 1
                if v0_idx >= 0:
                    result['baseline_v0'] = volumes[v0_idx]
                else:
                    result['baseline_v0'] = volumes[0]
            if result['baseline_v0'] > 0:
                result['volume_vs_v0'] = round(result['current_volume'] / result['baseline_v0'], 3)
                result['is_shrink'] = result['current_volume'] < result['baseline_v0']
                if result['is_shrink']:
                    print(f"[AI520_STATE] 缩量回踩: 当前量={result['current_volume']:.0f} < V0={result['baseline_v0']:.0f} (比值{result['volume_vs_v0']:.2f})", flush=True)
        except Exception as e:
            print(f"[AI520_STATE] 缩量回踩检查异常: {e}", flush=True)
        return result

    def check_bottom_fractal(self, kline: List[Dict]) -> Dict:
        """
        底分型识别（与MA20分开，不能碰MA20就叫底分型）
        底分型候选：Low[i-1] > Low[i] < Low[i+1]（中间低点）
        底分型确认：右侧收盘回升/重新站上MA5/右侧高点抬高
        Returns: {'candidate': bool, 'confirmed': bool, 'fractal_date': str, 'fractal_low': float, 'days_ago': int}
        """
        result = {'candidate': False, 'confirmed': False, 'fractal_date': '', 'fractal_low': 0, 'days_ago': 0}
        try:
            if len(kline) < 5:
                return result
            lows = [float(k.get('low', 0)) for k in kline]
            closes = [float(k.get('close', 0)) for k in kline]
            # 从最近往前找底分型候选（中间低点，i从倒数第2根开始往前）
            for i in range(len(kline) - 2, max(1, len(kline) - 10), -1):
                if lows[i-1] > lows[i] and lows[i] < lows[i+1]:
                    result['candidate'] = True
                    result['fractal_date'] = kline[i].get('date', '')
                    result['fractal_low'] = lows[i]
                    result['days_ago'] = len(kline) - 1 - i
                    # 确认：底分型之后（i+1及以后）收盘回升，且最后收盘价 > 底分型低点
                    post_closes = closes[i+1:]
                    if post_closes and closes[-1] > lows[i] and max(post_closes) > lows[i]:
                        # 进一步确认：最后收盘价 > MA5（如果能计算）
                        ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else 0
                        if ma5 > 0 and closes[-1] > ma5:
                            result['confirmed'] = True
                    print(f"[AI520_STATE] 底分型: 候选={result['candidate']} 确认={result['confirmed']} 低点={lows[i]:.2f} ({result['days_ago']}天前 {result['fractal_date']})", flush=True)
                    break
        except Exception as e:
            print(f"[AI520_STATE] 底分型检查异常: {e}", flush=True)
        return result

    def check_ma5_reclaim(self, kline: List[Dict]) -> Dict:
        """
        重新站回MA5：收盘价>MA5，且MA5向上，MA20非明显下降
        这是核心买点确认条件之一
        Returns: {'reclaimed': bool, 'close': float, 'ma5': float, 'ma5_up': bool, 'ma20_up': bool}
        """
        result = {'reclaimed': False, 'close': 0, 'ma5': 0, 'ma5_up': False, 'ma20_up': False}
        try:
            closes = [float(k.get('close', 0)) for k in kline]
            if len(closes) < 20:
                return result
            result['close'] = closes[-1]
            result['ma5'] = sum(closes[-5:]) / 5
            ma5_prev = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else result['ma5']
            result['ma5_up'] = result['ma5'] >= ma5_prev
            ma20 = sum(closes[-20:]) / 20
            ma20_prev = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else ma20
            result['ma20_up'] = ma20 >= ma20_prev
            # 重新站回MA5：收盘价>MA5 且 MA5向上 且 MA20非明显下降
            if result['close'] > result['ma5'] and result['ma5_up'] and not (ma20 < ma20_prev * 0.99):
                result['reclaimed'] = True
                print(f"[AI520_STATE] 重新站回MA5: 收盘={result['close']:.2f} > MA5={result['ma5']:.2f}, MA5向上={result['ma5_up']}", flush=True)
        except Exception as e:
            print(f"[AI520_STATE] MA5重新站回检查异常: {e}", flush=True)
        return result

    def analyze_state_machine(self, stock_info: Dict, kline: List[Dict]) -> Dict:
        """
        AI520历史记忆状态机完整分析
        状态链：LOW_KDJ_MEMORY→LIMIT_UP_MEMORY→VOLUME_STARTUP→GENTLE_RISE→SHRINK_PULLBACK→MA5_SUPPORT/MA20_SUPPORT→BOTTOM_FRACTAL→MA5_RECLAIM→BUY_POINT
        Returns: {
            'state': str, 'state_chain': List[str], 'buy_point': bool,
            'kdj_memory': Dict, 'limit_up_memory': Dict,
            'shrink_pullback': Dict, 'bottom_fractal': Dict, 'ma5_reclaim': Dict,
            'score_breakdown': Dict, 'state_score': float, 'state_grade': str
        }
        """
        result = {
            'state': 'NONE', 'state_chain': [], 'buy_point': False,
            'kdj_memory': {}, 'limit_up_memory': {},
            'shrink_pullback': {}, 'bottom_fractal': {}, 'ma5_reclaim': {},
            'score_breakdown': {}, 'state_score': 0, 'state_grade': 'D',
        }
        try:
            code = stock_info.get('code', '')
            name = stock_info.get('name', '')
            chain = []
            score = 0
            breakdown = {}

            # 1. KDJ低位记忆（过去5-10日J<=15）
            kdj_mem = self.check_kdj_memory(kline, lookback_days=10, j_threshold=15.0)
            result['kdj_memory'] = kdj_mem
            if kdj_mem.get('has_memory'):
                chain.append('LOW_KDJ_MEMORY')
                score += 10
                breakdown['kdj_memory'] = 10

            # 2. 20日涨停记忆
            lu_mem = self.check_limit_up_memory(kline, days=20)
            result['limit_up_memory'] = lu_mem
            if lu_mem.get('has_memory'):
                chain.append('LIMIT_UP_MEMORY')
                score += 5
                breakdown['limit_up_memory'] = 5

            # 3. 倍量启动（使用V2.3已有的_find_start_candle）
            start_result = self._find_start_candle(kline)
            if start_result.get('found'):
                chain.append('VOLUME_STARTUP')
                vol_ratio = start_result.get('vol_ratio', 0)
                startup_score = 10 if vol_ratio >= 2.0 else 8 if vol_ratio >= 1.8 else 5
                score += startup_score
                breakdown['volume_startup'] = startup_score
                print(f"[AI520_STATE] {code} {name} 倍量启动: V0={start_result.get('vol_ratio',0):.2f}倍, 涨幅={start_result.get('start_gain',0)*100:.2f}%", flush=True)

                # 4. 温和上涨（启动后累计涨幅-5%~+18%）
                post_start = self._check_post_start_performance(kline, start_result.get('idx', -1))
                post_gain = post_start.get('post_start_gain', 0)
                if -0.05 <= post_gain <= 0.18:
                    chain.append('GENTLE_RISE')
                    score += 8
                    breakdown['gentle_rise'] = 8
                    print(f"[AI520_STATE] {code} 温和上涨: 启动后涨幅={post_gain*100:.2f}%", flush=True)

                # 5. 缩量回踩（当前成交量 < V0）
                shrink = self.check_shrink_pullback(kline, start_idx=start_result.get('idx', -1))
                result['shrink_pullback'] = shrink
                if shrink.get('is_shrink'):
                    chain.append('SHRINK_PULLBACK')
                    score += 15
                    breakdown['shrink_pullback'] = 15

            # 6. MA5/MA20支撑（使用V2.3回踩检查）
            closes = [float(k.get('close', 0)) for k in kline]
            if len(closes) >= 20:
                ma5 = sum(closes[-5:]) / 5
                ma20 = sum(closes[-20:]) / 20
                low_today = float(kline[-1].get('low', 0))
                # MA5支撑：最低价<=MA5*1.015
                if low_today <= ma5 * 1.015:
                    chain.append('MA5_SUPPORT')
                    score += 10
                    breakdown['ma5_support'] = 10
                # MA20支撑：最低价<=MA20*1.02 且 MA20非明显向下
                ma20_prev = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else ma20
                if low_today <= ma20 * 1.02 and ma20 >= ma20_prev * 0.995:
                    chain.append('MA20_SUPPORT')
                    score += 15
                    breakdown['ma20_support'] = 15

            # 7. 底分型
            fractal = self.check_bottom_fractal(kline)
            result['bottom_fractal'] = fractal
            if fractal.get('candidate'):
                chain.append('BOTTOM_FRACTAL_CANDIDATE')
                score += 5
                breakdown['bottom_fractal_candidate'] = 5
            if fractal.get('confirmed'):
                chain.append('BOTTOM_FRACTAL_CONFIRMED')
                score += 5
                breakdown['bottom_fractal_confirmed'] = 5

            # 8. 重新站回MA5
            reclaim = self.check_ma5_reclaim(kline)
            result['ma5_reclaim'] = reclaim
            if reclaim.get('reclaimed'):
                chain.append('MA5_RECLAIM')
                score += 15
                breakdown['ma5_reclaim'] = 15

            # 9. 买点确认：重新站回MA5 + 当前涨幅0.3%~7% + 之前有启动+回踩历史
            pct_chg = stock_info.get('pct_chg', 0)
            has_startup_history = 'VOLUME_STARTUP' in chain
            has_pullback = 'SHRINK_PULLBACK' in chain or 'MA5_SUPPORT' in chain or 'MA20_SUPPORT' in chain
            if reclaim.get('reclaimed') and 0.3 <= abs(pct_chg) <= 7.0 and has_startup_history and has_pullback:
                chain.append('BUY_POINT')
                result['buy_point'] = True
                score += 10
                breakdown['buy_point'] = 10
                print(f"[AI520_BUY] {code} {name} BUY_POINT确认! 状态链={'→'.join(chain)}, 评分={score}", flush=True)

            # 确定当前状态（状态链最后一个）
            result['state'] = chain[-1] if chain else 'NONE'
            result['state_chain'] = chain
            result['state_score'] = min(score, 100)
            result['score_breakdown'] = breakdown

            # 等级
            if result['state_score'] >= 85:
                result['state_grade'] = 'S'
            elif result['state_score'] >= 75:
                result['state_grade'] = 'A'
            elif result['state_score'] >= 65:
                result['state_grade'] = 'B'
            elif result['state_score'] >= 55:
                result['state_grade'] = 'C'
            else:
                result['state_grade'] = 'D'

            if chain:
                print(f"[AI520_STATE] {code} {name} 状态链: {'→'.join(chain)}, 状态评分={result['state_score']}, 等级={result['state_grade']}", flush=True)

        except Exception as e:
            print(f"[AI520_STATE] 状态机分析异常: {e}", flush=True)
            import traceback; traceback.print_exc()
        return result

    # ============================================================
    # V2.6 AI520相似度评分引擎（8个维度100分制）
    # 取消强制全通过，改为相似模式识别+综合评分
    # ============================================================

    def calc_ai520_similarity_score(self, stock_info: Dict, kline: List[Dict]) -> Dict:
        """
        V2.7.1兼容层：统一调用AI520Strategy唯一核心策略
        不再使用旧的独立评分逻辑，所有AI520评分走strategy/ai520_strategy.py
        """
        try:
            from strategy.ai520_strategy import get_ai520_strategy
            strategy = get_ai520_strategy()
            ai520_result = strategy.score_stock(kline, stock_info)
            
            # 适配旧接口返回字段
            result = {
                'total_score': ai520_result.get('score', 0),
                'score': ai520_result.get('score', 0),
                'dimension_scores': {
                    'trend': ai520_result.get('trend_score', 0),
                    'strength_memory': ai520_result.get('strength_memory_score', 0),
                    'moderate_rise': ai520_result.get('moderate_rise_score', 0),
                    'pullback': ai520_result.get('pullback_score', 0),
                    'recovery': ai520_result.get('recovery_score', 0),
                    'kdj': ai520_result.get('kdj_score', 0),
                    'position': ai520_result.get('position_score', 0),
                    'volume_price': ai520_result.get('volume_price_score', 0),
                },
                'matched_conditions': ai520_result.get('matched_conditions', []),
                'missing_conditions': ai520_result.get('missing_conditions', []),
                'risk_items': ai520_result.get('risk_items', []),
                'grade': ai520_result.get('grade', 'D'),
                'similarity': ai520_result.get('similarity', '不相似'),
                'trend_score': ai520_result.get('trend_score', 0),
                'memory_score': ai520_result.get('strength_memory_score', 0),
                'gentle_score': ai520_result.get('moderate_rise_score', 0),
                'pullback_score': ai520_result.get('pullback_score', 0),
                'strength_score': ai520_result.get('recovery_score', 0),
                'kdj_score': ai520_result.get('kdj_score', 0),
                'position_score': ai520_result.get('position_score', 0),
                'volume_price_score': ai520_result.get('volume_price_score', 0),
                'pullback_type': ai520_result.get('pullback_type', 'NONE'),
                'status': ai520_result.get('status', 'OK'),
                'strategy_version': ai520_result.get('strategy_version', 'AI520-1.0'),
            }
            return result
        except Exception as e:
            return {
                'total_score': 0, 'score': 0, 'dimension_scores': {},
                'matched_conditions': [], 'missing_conditions': [],
                'risk_items': [f'AI520Strategy调用异常: {str(e)}'],
                'grade': 'D', 'similarity': '不相似',
                'trend_score': 0, 'memory_score': 0, 'gentle_score': 0,
                'pullback_score': 0, 'strength_score': 0, 'kdj_score': 0,
                'position_score': 0, 'volume_price_score': 0,
                'pullback_type': 'NONE', 'status': 'ERROR',
            }

