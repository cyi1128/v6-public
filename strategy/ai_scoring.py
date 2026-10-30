"""
AI综合评分系统（100分）
趋势25分 + 量能25分 + 技术25分 + 资金25分
评级：90-100强烈关注，80-90重点观察，70-80等待确认，70以下过滤
"""
import numpy as np
from utils.indicators import (
    calc_kdj, calc_macd, calc_ma, calc_ma_series,
    is_kdj_golden_cross, calc_kdj_series, calc_macd_series,
    is_macd_golden_cross, calc_avg_volume
)


class AIScoringSystem:
    """AI综合评分系统"""

    def __init__(self):
        pass

    def score(self, daily_data, stock_info=None):
        """
        综合评分（4×25分体系）
        返回: 评分字典
        """
        result = {
            'total_score': 0,
            'trend_score': 0,      # 趋势25分
            'volume_score': 0,     # 量能25分
            'technical_score': 0,  # 技术25分
            'fund_score': 0,       # 资金25分
            # 趋势细分
            'ma_bullish': 0,       # MA5>MA10>MA20
            'above_ma20': 0,       # 站上20日线
            'ma120_up': 0,         # 120日线向上
            # 量能细分
            'triple_volume': 0,    # 三倍量阳线
            'shrink_pullback': 0,  # 缩量回踩
            'breakout_volume': 0,  # 突破放量
            # 技术细分
            'macd_golden': 0,      # MACD金叉
            'kdj_golden': 0,       # KDJ金叉
            'rsi_strong': 0,       # RSI强势
            # 资金细分
            'turnover_ok': 0,      # 换手率合理
            'fund_inflow': 0,      # 资金流入
            'sector_strong': 0,    # 板块强
            # 状态
            'trend_status': '未知',
            'chan_status': '无信号',
            'tv_status': '无信号',
            'rating': '过滤',
            'risk_level': '低',
            'suggestion': '观望',
            'catalysts': [],
            'signals': [],
            'stage': '观察',  # 观察/回踩/突破/买入/风险
        }

        if not daily_data or len(daily_data) < 30:
            return result

        close_prices = [d['close'] for d in daily_data]
        high_prices = [d['high'] for d in daily_data]
        low_prices = [d['low'] for d in daily_data]
        volumes = [d.get('volume', d.get('vol', 0)) for d in daily_data]

        # ========== 1. 趋势评分 (25分) ==========
        trend_score, trend_details = self._score_trend(close_prices)
        result['trend_score'] = trend_score
        result.update(trend_details)

        # ========== 2. 量能评分 (25分) ==========
        volume_score, vol_details, tv_signals = self._score_volume(daily_data, volumes, close_prices)
        result['volume_score'] = volume_score
        result.update(vol_details)
        if tv_signals:
            result['signals'].extend(tv_signals)
            best_tv = max(tv_signals, key=lambda x: x.get('score', 0))
            result['tv_status'] = best_tv['name']

        # ========== 3. 技术评分 (25分) ==========
        tech_score, tech_details = self._score_technical(high_prices, low_prices, close_prices)
        result['technical_score'] = tech_score
        result.update(tech_details)

        # ========== 4. 资金评分 (25分) ==========
        fund_score, fund_details = self._score_fund(stock_info, daily_data, volumes)
        result['fund_score'] = fund_score
        result.update(fund_details)

        # ========== 总分 ==========
        total = trend_score + volume_score + tech_score + fund_score
        result['total_score'] = min(100, total)

        # ========== 评级 ==========
        if total >= 90:
            result['rating'] = '强烈关注'
        elif total >= 80:
            result['rating'] = '重点观察'
        elif total >= 70:
            result['rating'] = '等待确认'
        else:
            result['rating'] = '过滤'

        # ========== 趋势状态 ==========
        result['trend_status'] = self._get_trend_status(close_prices)

        # ========== 阶段判断 ==========
        result['stage'] = self._get_stage(result)

        # ========== 风险等级 ==========
        result['risk_level'] = self._get_risk_level(result, close_prices, volumes)

        # ========== 操作建议 ==========
        result['suggestion'] = self._get_suggestion(result)

        # ========== 催化因素 ==========
        result['catalysts'] = self._get_catalysts(result)

        # ========== 买卖位置 ==========
        result['buy_price'] = close_prices[-1]
        result['stop_loss'] = self._calc_stop_loss(close_prices, low_prices)
        result['target_price'] = self._calc_target(close_prices, result)

        return result

    def _score_trend(self, close):
        """趋势评分 (25分)"""
        details = {}
        score = 0

        ma5 = calc_ma(close, 5)
        ma10 = calc_ma(close, 10)
        ma20 = calc_ma(close, 20)

        # MA5>MA10>MA20：+10分
        if ma5 > ma10 > ma20:
            score += 10
            details['ma_bullish'] = 10
        else:
            details['ma_bullish'] = 0

        # 站上20日线：+10分
        if close[-1] > ma20:
            score += 10
            details['above_ma20'] = 10
        else:
            details['above_ma20'] = 0

        # 120日线向上：+5分
        if len(close) >= 120:
            ma120 = calc_ma(close, 120)
            ma120_series = calc_ma_series(close, 120)
            if ma120_series.iloc[-1] > ma120_series.iloc[-5]:
                score += 5
                details['ma120_up'] = 5
            else:
                details['ma120_up'] = 0
        else:
            details['ma120_up'] = 0

        return min(score, 25), details

    def _score_volume(self, daily_data, volumes, close):
        """量能评分 (25分)"""
        details = {}
        score = 0

        # 放量上涨：+15分（成交量超过5日均量2倍且上涨）
        if len(volumes) >= 6 and len(close) >= 2:
            avg_vol_5 = np.mean(volumes[-6:-1])
            if avg_vol_5 > 0 and volumes[-1] > avg_vol_5 * 2 and close[-1] > close[-2]:
                score += 15
                details['volume_surge'] = 15
            else:
                details['volume_surge'] = 0
        else:
            details['volume_surge'] = 0

        # 缩量回踩：+5分
        if len(volumes) >= 6 and len(close) >= 2:
            avg_vol_5 = np.mean(volumes[-6:-1])
            if avg_vol_5 > 0 and volumes[-1] < avg_vol_5 * 0.7 and close[-1] < close[-2]:
                score += 5
                details['shrink_pullback'] = 5
            else:
                details['shrink_pullback'] = 0
        else:
            details['shrink_pullback'] = 0

        # 突破放量：+5分
        if len(volumes) >= 6 and len(close) >= 2:
            avg_vol_5 = np.mean(volumes[-6:-1])
            if avg_vol_5 > 0 and volumes[-1] > avg_vol_5 * 1.5 and close[-1] > close[-2]:
                score += 5
                details['breakout_volume'] = 5
            else:
                details['breakout_volume'] = 0
        else:
            details['breakout_volume'] = 0

        return min(score, 25), details, []

    def _score_technical(self, high, low, close):
        """技术评分 (25分)"""
        details = {}
        score = 0

        # MACD金叉：+10分
        dif_series, dea_series, hist_series = calc_macd_series(close)
        if is_macd_golden_cross(dif_series, dea_series):
            score += 10
            details['macd_golden'] = 10
        else:
            # MACD在零轴上方且DIF>DEA给5分
            last_idx = len(close) - 1
            if dif_series.iloc[last_idx] > dea_series.iloc[last_idx] and dif_series.iloc[last_idx] > 0:
                score += 5
                details['macd_golden'] = 5
            else:
                details['macd_golden'] = 0

        # KDJ(13,3,3)金叉：+10分
        k_series, d_series, j_series = calc_kdj_series(high, low, close)
        if is_kdj_golden_cross(k_series, d_series):
            score += 10
            details['kdj_golden'] = 10
        else:
            # KDJ在50以下且K>D给5分
            last_idx = len(close) - 1
            if k_series.iloc[last_idx] > d_series.iloc[last_idx] and k_series.iloc[last_idx] < 50:
                score += 5
                details['kdj_golden'] = 5
            else:
                details['kdj_golden'] = 0

        # RSI强势：+5分
        rsi = self._calc_rsi(close, 14)
        if 50 <= rsi <= 70:
            score += 5
            details['rsi_strong'] = 5
        elif rsi > 70:
            details['rsi_strong'] = 0  # 超买不加分
        else:
            details['rsi_strong'] = 0

        return min(score, 25), details

    def _score_fund(self, stock_info, daily_data, volumes):
        """资金评分 (25分)"""
        details = {}
        score = 0

        # 换手率合理：+10分（5%-20%）
        turnover_rate = 0
        if stock_info:
            turnover_rate = stock_info.get('turnover_rate', 0)
        if not turnover_rate and daily_data:
            turnover_rate = daily_data[-1].get('turnover_rate', 0)

        if 5 <= turnover_rate <= 20:
            score += 10
            details['turnover_ok'] = 10
        elif 3 <= turnover_rate < 5 or 20 < turnover_rate <= 30:
            score += 5
            details['turnover_ok'] = 5
        else:
            details['turnover_ok'] = 0

        # 资金流入：+10分
        fund_inflow = 0
        if stock_info:
            fund_inflow = stock_info.get('main_fund_inflow', 0)
        if fund_inflow > 0:
            score += 10
            details['fund_inflow'] = 10
        elif fund_inflow == 0:
            # 用成交量和价格判断资金方向
            if len(volumes) >= 3 and len(daily_data) >= 3:
                recent_up = sum(1 for i in range(-3, 0) if daily_data[i]['close'] > daily_data[i]['open'])
                if recent_up >= 2:
                    score += 5
                    details['fund_inflow'] = 5
                else:
                    details['fund_inflow'] = 0
            else:
                details['fund_inflow'] = 0
        else:
            details['fund_inflow'] = 0

        # 板块强：+5分
        sector_strong = False
        if stock_info:
            sector_strong = stock_info.get('sector_strong', False)
        if sector_strong:
            score += 5
            details['sector_strong'] = 5
        else:
            details['sector_strong'] = 0

        return min(score, 25), details

    def _calc_rsi(self, close, period=14):
        """计算RSI"""
        if len(close) < period + 1:
            return 50

        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _get_trend_status(self, close):
        """获取趋势状态"""
        if len(close) < 20:
            return '数据不足'

        ma5 = calc_ma(close, 5)
        ma20 = calc_ma(close, 20)

        if close[-1] > ma5 > ma20:
            return '强势上涨'
        elif close[-1] > ma20:
            return '震荡偏多'
        elif close[-1] < ma5 < ma20:
            return '弱势下跌'
        else:
            return '震荡整理'

    def _get_stage(self, result):
        """获取阶段：观察/回踩/突破/买入/风险"""
        if result['risk_level'] == '高':
            return '风险'
        if result['tv_status'] == '三倍量二次启动买点':
            return '买入'
        if result['breakout_volume'] > 0:
            return '突破'
        if result['shrink_pullback'] > 0:
            return '回踩'
        return '观察'

    def _get_risk_level(self, result, close, volumes):
        """获取风险等级"""
        risk_score = 0

        # 高位放巨量
        if len(volumes) >= 6:
            avg_vol = np.mean(volumes[-6:-1])
            if avg_vol > 0 and volumes[-1] / avg_vol > 3 and len(close) >= 10 and close[-1] > close[-10]:
                risk_score += 2

        # 技术面弱
        if result['technical_score'] < 10:
            risk_score += 1

        # 跌破MA20
        ma20 = calc_ma(close, 20)
        if close[-1] < ma20:
            risk_score += 2

        # 趋势弱
        if result['trend_score'] < 10:
            risk_score += 1

        if risk_score >= 4:
            return '高'
        elif risk_score >= 2:
            return '中'
        else:
            return '低'

    def _get_suggestion(self, result):
        """获取操作建议"""
        score = result['total_score']
        stage = result['stage']

        if score >= 90:
            if stage == '买入':
                return '强烈关注，二次启动买点形成，可考虑介入'
            return '强烈关注，综合评分极高，重点跟踪'
        elif score >= 80:
            if stage == '突破':
                return '重点观察，突破信号出现，等待确认'
            return '重点观察，评分较高，可加入自选跟踪'
        elif score >= 70:
            return '等待确认，评分中等，需更多信号配合'
        else:
            return '过滤，评分较低，暂不关注'

    def _get_catalysts(self, result):
        """获取催化因素"""
        catalysts = []

        if result['triple_volume'] > 0:
            catalysts.append('三倍量阳线启动')
        if result['shrink_pullback'] > 0:
            catalysts.append('缩量回踩确认')
        if result['breakout_volume'] > 0:
            catalysts.append('突破放量')
        if result['macd_golden'] >= 10:
            catalysts.append('MACD金叉')
        if result['kdj_golden'] >= 10:
            catalysts.append('KDJ金叉')
        if result['ma_bullish'] > 0:
            catalysts.append('均线多头排列')
        if result['above_ma20'] > 0:
            catalysts.append('站上20日线')
        if result['turnover_ok'] >= 10:
            catalysts.append('换手率活跃')
        if result['fund_inflow'] >= 10:
            catalysts.append('主力资金流入')
        if result['sector_strong'] > 0:
            catalysts.append('板块强势')
        if result['chan_status'] != '无信号':
            catalysts.append(f'缠论{result["chan_status"]}')

        return catalysts

    def _calc_stop_loss(self, close, low):
        """计算止损位"""
        if len(low) < 10:
            return close[-1] * 0.95

        recent_low = min(low[-10:])
        return recent_low * 0.98

    def _calc_target(self, close, result):
        """计算目标位"""
        current = close[-1]

        if result['total_score'] >= 90:
            return current * 1.25
        elif result['total_score'] >= 80:
            return current * 1.20
        elif result['total_score'] >= 70:
            return current * 1.15
        else:
            return current * 1.10
