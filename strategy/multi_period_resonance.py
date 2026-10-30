# -*- coding: utf-8 -*-
"""
多周期共振评分模块
V1.2-A-3 新增

定位：
判断当前机会是否得到多个时间周期的同时确认。
不是买入评分，是"周期确认等级"。

原则：
- 只读取多周期分析结果，不修改任何冻结模块
- 独立模块，可删除
- 不修改AI评分、R2评级、B1-B6事件
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MultiPeriodResonance:
    """多周期共振分析器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 共振等级定义
        self.levels = {
            5: {'name': '完美共振', 'confidence': '极高', 'stars': '⭐⭐⭐⭐⭐'},
            4: {'name': '强共振', 'confidence': '高', 'stars': '⭐⭐⭐⭐'},
            3: {'name': '观察共振', 'confidence': '中', 'stars': '⭐⭐⭐'},
            2: {'name': '弱共振', 'confidence': '低', 'stars': '⭐⭐'},
            1: {'name': '无共振', 'confidence': '极低', 'stars': '⭐'},
        }

        print("[MultiPeriodResonance] 多周期共振分析器初始化完成")

    def analyze_resonance(self, code, period_analysis):
        """
        分析多周期共振等级

        参数：
            code: 股票代码
            period_analysis: 多周期分析结果（来自multi_period_analysis）

        返回：
            dict: 共振分析结果
        """
        result = {
            'code': code,
            'level': 1,
            'name': '无共振',
            'confidence': '极低',
            'stars': '⭐',
            'resonance_score': 0,  # 独立的共振评分，不影响原AI评分
            'summary': '',
            'period_confirmation': {},
            'risk_warning': [],
            'high_risk': False,  # 高位风险标记
            'conflict_level': 0,  # 周期冲突等级
        }

        if not period_analysis or len(period_analysis) == 0:
            result['summary'] = '数据不足，无法判断共振'
            return result

        # 1. 逐个周期确认
        week_confirm = self._check_week_period(period_analysis.get('week', {}))
        day_confirm = self._check_day_period(period_analysis.get('day', {}))
        min60_confirm = self._check_60min_period(period_analysis.get('60min', {}))
        min30_confirm = self._check_30min_period(period_analysis.get('30min', {}))

        result['period_confirmation'] = {
            'week': week_confirm,
            'day': day_confirm,
            '60min': min60_confirm,
            '30min': min30_confirm,
        }

        # 2. 计算共振得分
        score = 0
        confirm_count = 0

        if week_confirm['status'] == '确认':
            score += 25
            confirm_count += 1
        elif week_confirm['status'] == '部分确认':
            score += 10

        if day_confirm['status'] == '确认':
            score += 30
            confirm_count += 1
        elif day_confirm['status'] == '部分确认':
            score += 15

        if min60_confirm['status'] == '确认':
            score += 25
            confirm_count += 1
        elif min60_confirm['status'] == '部分确认':
            score += 10

        if min30_confirm['status'] == '确认':
            score += 20
            confirm_count += 1
        elif min30_confirm['status'] == '部分确认':
            score += 8

        result['resonance_score'] = min(100, score)

        # 3. 判断共振等级
        level = self._judge_level(score, confirm_count, period_analysis)
        level_info = self.levels.get(level, self.levels[1])

        result['level'] = level
        result['name'] = level_info['name']
        result['confidence'] = level_info['confidence']
        result['stars'] = level_info['stars']

        # 4. 检测高位风险
        day_analysis = period_analysis.get('day', {})
        if day_analysis and len(day_analysis.get('close', [])) >= 120:
            closes = day_analysis.get('close', [])
            current_price = closes[-1]
            lookback = min(160, len(closes))
            high_period = max(closes[-lookback:])
            if high_period > 0 and current_price / high_period >= 0.95:
                result['high_risk'] = True
                result['risk_warning'].append('⚠️ 价格处于近8个月高位，注意追高风险')

        # 5. 记录周期冲突等级
        week_trend = period_analysis.get('week', {}).get('trend', '')
        day_trend = period_analysis.get('day', {}).get('trend', '')
        if week_trend == '下跌趋势' and day_trend == '上涨趋势':
            result['conflict_level'] = 2
            result['risk_warning'].append('⚠️ 周线趋势向下，日线反弹，注意持续性')

        # 6. 生成总结
        result['summary'] = self._generate_summary(
            level, week_confirm, day_confirm, min60_confirm, min30_confirm, result['high_risk']
        )

        # 7. 生成风险提示
        base_warnings = self._generate_risk_warning(
            week_confirm, day_confirm, min60_confirm, min30_confirm
        )
        result['risk_warning'].extend(base_warnings)

        return result

    def _check_week_period(self, analysis):
        """
        检查周线周期

        返回：
            dict: {'status': '确认/部分确认/不确认', 'reason': '原因'}
        """
        if not analysis:
            return {'status': '不确认', 'reason': '无数据'}

        trend = analysis.get('trend', '')
        ma = analysis.get('ma', {})
        macd = analysis.get('macd', {})

        confirm_points = 0
        total_points = 3

        # 趋势向上
        if trend == '上涨趋势':
            confirm_points += 1
        elif trend == '震荡':
            confirm_points += 0.5

        # MA20向上（价格在MA20上方）
        if ma.get('price_above_ma20', False):
            confirm_points += 1

        # MACD零轴上方
        if macd.get('above_zero', False):
            confirm_points += 1

        ratio = confirm_points / total_points

        if ratio >= 0.8:
            status = '确认'
            reason = '周线趋势向上'
        elif ratio >= 0.5:
            status = '部分确认'
            reason = '周线震荡整理'
        else:
            status = '不确认'
            reason = '周线趋势向下'

        return {'status': status, 'reason': reason, 'score': confirm_points}

    def _check_day_period(self, analysis):
        """
        检查日线周期

        返回：
            dict: {'status': '确认/部分确认/不确认', 'reason': '原因'}
        """
        if not analysis:
            return {'status': '不确认', 'reason': '无数据'}

        ma = analysis.get('ma', {})
        macd = analysis.get('macd', {})
        kdj = analysis.get('kdj', {})
        status = analysis.get('status', '')

        confirm_points = 0
        total_points = 4

        # 均线多头排列
        if ma.get('arrangement') == '多头排列':
            confirm_points += 1.5
        elif ma.get('price_above_ma20', False):
            confirm_points += 0.5

        # MACD红柱扩大或金叉
        macd_signal = macd.get('signal', '')
        if macd_signal in ['红柱扩大', '金叉', '绿柱缩短']:
            confirm_points += 1
        elif macd.get('strength') == '强势':
            confirm_points += 0.5

        # KDJ低位修复或金叉
        kdj_signal = kdj.get('signal', '')
        if kdj_signal in ['低位金叉', '金叉']:
            confirm_points += 1
        elif kdj.get('zone') == '超卖':
            confirm_points += 0.5

        # 状态为买点附近
        if status == '买点附近':
            confirm_points += 0.5

        ratio = confirm_points / total_points

        if ratio >= 0.7:
            status_result = '确认'
            reason = '日线买点形成'
        elif ratio >= 0.4:
            status_result = '部分确认'
            reason = '日线机会初现'
        else:
            status_result = '不确认'
            reason = '日线无明显机会'

        return {'status': status_result, 'reason': reason, 'score': confirm_points}

    def _check_60min_period(self, analysis):
        """
        检查60分钟周期

        返回：
            dict: {'status': '确认/部分确认/不确认', 'reason': '原因'}
        """
        if not analysis:
            return {'status': '不确认', 'reason': '无数据'}

        ma = analysis.get('ma', {})
        macd = analysis.get('macd', {})
        kdj = analysis.get('kdj', {})
        trend = analysis.get('trend', '')

        confirm_points = 0
        total_points = 3

        # 回踩MA20附近（价格在MA20上方或附近）
        if ma.get('price_above_ma20', False):
            confirm_points += 1
        elif ma.get('ma20') and ma.get('ma20') > 0:
            current_price = analysis.get('current_price', 0)
            ma20 = ma.get('ma20', 1)
            distance = abs(current_price - ma20) / ma20 * 100
            if distance < 3:  # 距离MA20不到3%
                confirm_points += 0.5

        # MACD重新金叉或绿柱缩短
        macd_signal = macd.get('signal', '')
        if macd_signal in ['金叉', '绿柱缩短']:
            confirm_points += 1
        elif macd_signal == '红柱扩大':
            confirm_points += 0.5

        # KDJ低位修复
        kdj_signal = kdj.get('signal', '')
        if kdj_signal in ['低位金叉', '金叉']:
            confirm_points += 1
        elif kdj.get('zone') == '超卖':
            confirm_points += 0.5

        ratio = confirm_points / total_points

        if ratio >= 0.7:
            status = '确认'
            reason = '60分钟回踩完成'
        elif ratio >= 0.4:
            status = '部分确认'
            reason = '60分钟等待确认'
        else:
            status = '不确认'
            reason = '60分钟未确认'

        return {'status': status, 'reason': reason, 'score': confirm_points}

    def _check_30min_period(self, analysis):
        """
        检查30分钟周期

        返回：
            dict: {'status': '确认/部分确认/不确认', 'reason': '原因'}
        """
        if not analysis:
            return {'status': '不确认', 'reason': '无数据'}

        ma = analysis.get('ma', {})
        macd = analysis.get('macd', {})
        trend = analysis.get('trend', '')
        status = analysis.get('status', '')

        confirm_points = 0
        total_points = 3

        # 短线趋势向上
        if trend == '上涨趋势':
            confirm_points += 1
        elif ma.get('arrangement') == '多头排列':
            confirm_points += 0.5

        # MACD红柱扩大
        if macd.get('signal') == '红柱扩大':
            confirm_points += 1
        elif macd.get('strength') == '强势':
            confirm_points += 0.5

        # 状态为买点附近或启动
        if status == '买点附近':
            confirm_points += 1
        elif status == '正常' and trend != '下跌趋势':
            confirm_points += 0.5

        ratio = confirm_points / total_points

        if ratio >= 0.7:
            status_result = '确认'
            reason = '30分钟启动'
        elif ratio >= 0.4:
            status_result = '部分确认'
            reason = '30分钟准备中'
        else:
            status_result = '不确认'
            reason = '30分钟未启动'

        return {'status': status_result, 'reason': reason, 'score': confirm_points}

    def _judge_level(self, score, confirm_count, period_analysis):
        """
        判断共振等级

        参数：
            score: 得分（0-100）
            confirm_count: 确认的周期数量（不含30分钟，30分钟是增强项）
            period_analysis: 周期分析结果

        返回：
            int: 等级（1-5）
        """
        # ========== 1. 周期冲突检测 ==========
        week_trend = period_analysis.get('week', {}).get('trend', '')
        day_trend = period_analysis.get('day', {}).get('trend', '')
        min60_trend = period_analysis.get('60min', {}).get('trend', '')

        conflict_level = 0  # 0=无冲突, 1=轻微冲突, 2=明显冲突, 3=严重冲突

        # 情况3：周线下降，日线+60分钟都上涨 → 严重冲突（禁止高级共振）
        if week_trend == '下跌趋势' and day_trend == '上涨趋势' and min60_trend == '上涨趋势':
            conflict_level = 3
        # 情况1：周线上涨，日线下跌，60分钟反弹 → 轻微冲突
        elif week_trend == '上涨趋势' and day_trend == '下跌趋势' and min60_trend == '上涨趋势':
            conflict_level = 1
        # 周线下跌，日线上涨 → 明显冲突
        elif week_trend == '下跌趋势' and day_trend == '上涨趋势':
            conflict_level = 2
        # 周线上涨，日线上涨，但60分钟下跌 → 正常调整，不算冲突
        elif week_trend == '上涨趋势' and day_trend == '上涨趋势' and min60_trend == '下跌趋势':
            conflict_level = 0

        # ========== 2. 高位风险检测 ==========
        high_risk = False
        day_analysis = period_analysis.get('day', {})
        if day_analysis:
            closes = day_analysis.get('close', [])
            if len(closes) >= 120:  # 约6个月数据
                current_price = closes[-1]
                high_8m = max(closes[-160:]) if len(closes) >= 160 else max(closes)
                if high_8m > 0 and current_price / high_8m >= 0.95:
                    high_risk = True

        # ========== 3. 计算核心确认周期数（周+日+60分钟，30分钟是增强项） ==========
        # 30分钟不作为准入条件，只作为加分项
        core_confirm = 0
        week_analysis = period_analysis.get('week', {})
        day_analysis_data = period_analysis.get('day', {})
        min60_analysis = period_analysis.get('60min', {})

        if week_analysis.get('trend') == '上涨趋势':
            core_confirm += 1
        if day_analysis_data.get('status') == '买点附近' or day_analysis_data.get('ma', {}).get('arrangement') == '多头排列':
            core_confirm += 1
        if min60_analysis.get('macd', {}).get('signal') in ['金叉', '绿柱缩短']:
            core_confirm += 1

        # ========== 4. 基础等级判断 ==========
        base_level = 1

        # 完美共振：核心3周期全确认 + 得分>=80 + 无冲突 + 非高位
        if core_confirm >= 3 and score >= 80 and conflict_level == 0 and not high_risk:
            base_level = 5
        # 强共振：核心2-3周期确认 + 得分>=65 + 无严重冲突
        elif core_confirm >= 2 and score >= 65 and conflict_level <= 1:
            base_level = 4
        # 观察共振：核心2周期确认 + 得分>=50 + 冲突不严重
        elif core_confirm >= 2 and score >= 50 and conflict_level <= 2:
            base_level = 3
        # 弱共振：核心1周期确认 + 得分>=35
        elif core_confirm >= 1 and score >= 35:
            base_level = 2
        # 无共振
        else:
            base_level = 1

        # ========== 5. 30分钟增强（加分项，不是减分项） ==========
        min30_status = period_analysis.get('30min', {}).get('status', '')
        if min30_status == '买点附近' and base_level >= 3 and conflict_level == 0:
            # 30分钟确认，提升半级（最多到5级）
            if base_level < 5:
                base_level = min(5, base_level + 1)

        # ========== 6. 冲突降级 ==========
        if conflict_level == 3:
            # 严重冲突，最多到2级
            base_level = min(base_level, 2)
        elif conflict_level == 2:
            # 明显冲突，降1级
            base_level = max(1, base_level - 1)

        # ========== 7. 高位风险降级 ==========
        if high_risk and base_level >= 3:
            # 高位共振，降1级，加风险提示
            base_level = max(1, base_level - 1)

        return base_level

    def _generate_summary(self, level, week_confirm, day_confirm, min60_confirm, min30_confirm, high_risk=False):
        """生成共振总结"""
        base_summary = ""
        if level == 5:
            base_summary = "周线趋势向上，日线形成买点，60分钟回踩确认，30分钟启动，完美多周期共振"
        elif level == 4:
            base_summary = "周线趋势正常，日线买点形成，60分钟确认，强多周期共振"
        elif level == 3:
            base_summary = "日线出现机会，部分周期确认，等待更多周期同步"
        elif level == 2:
            base_summary = "单周期信号较强，其他周期未确认，共振较弱"
        else:
            base_summary = "周期方向不一致，无明显共振，需谨慎"

        if high_risk:
            base_summary += "（注意：价格处于高位，谨慎追涨）"

        return base_summary

    def _generate_risk_warning(self, week_confirm, day_confirm, min60_confirm, min30_confirm):
        """生成风险提示"""
        warnings = []

        if week_confirm['status'] == '不确认':
            warnings.append('周线趋势未确认，大方向需观察')
        elif week_confirm['status'] == '部分确认':
            warnings.append('周线震荡整理，趋势尚未明确')

        if day_confirm['status'] == '不确认':
            warnings.append('日线无明显买点，等待机会形成')
        elif day_confirm['status'] == '部分确认':
            warnings.append('日线机会初现，尚未完全确认')

        if min60_confirm['status'] == '不确认':
            warnings.append('60分钟未确认，不宜急于进场')
        elif min60_confirm['status'] == '部分确认':
            warnings.append('60分钟等待确认，注意回踩支撑')

        if min30_confirm['status'] == '不确认':
            warnings.append('30分钟未启动，短线时机未到')

        if not warnings:
            warnings.append('各周期共振良好，按计划执行')

        return warnings

    def analyze_stock(self, code):
        """
        分析单只股票的多周期共振

        参数：
            code: 股票代码

        返回：
            dict: 完整的共振分析结果
        """
        from strategy.multi_period_analysis import get_multi_period_analyzer
        analyzer = get_multi_period_analyzer()

        analysis_result = analyzer.analyze_all_periods(code)
        period_analysis = analysis_result.get('period_analysis', {})

        resonance = self.analyze_resonance(code, period_analysis)

        return resonance


# 单例获取函数
_multi_period_resonance = None


def get_multi_period_resonance():
    """获取多周期共振分析器单例"""
    global _multi_period_resonance
    if _multi_period_resonance is None:
        _multi_period_resonance = MultiPeriodResonance()
    return _multi_period_resonance
