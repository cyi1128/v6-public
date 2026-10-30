# -*- coding: utf-8 -*-
"""
多维度确认引擎
V1.2-B-2 新增

定位：
交易辅助确认层。
只汇总已有结果，输出综合确认强度。

原则：
- 不修改AI评分
- 不修改R2评级
- 不修改B1-B6事件
- 不修改缠论核心
- 不修改多周期共振
- 只汇总，不计算新的策略
- 独立模块，可删除
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MultiConfirmationEngine:
    """多维度确认引擎"""

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

        # 权重配置
        self.ai_weight = 0.40        # AI评分权重
        self.resonance_weight = 0.35  # 多周期共振权重
        self.chan_weight = 0.25       # 缠论确认度权重

        # 等级阈值
        self.level_thresholds = [
            (90, 5, '极强确认'),
            (80, 4, '强确认'),
            (65, 3, '中等确认'),
            (50, 2, '弱确认'),
            (0, 1, '无确认'),
        ]

        print("[MultiConfirmationEngine] 多维度确认引擎初始化完成")

    def calculate_confirmation(self, ai_result=None, resonance_result=None, chan_result=None):
        """
        计算综合确认度

        参数：
            ai_result: AI评分结果（可选）
                {
                    'score': 82,
                    'rating': '强关注',
                    ...
                }
            resonance_result: 多周期共振结果（可选）
                {
                    'resonance_score': 90,
                    'level': 4,
                    'name': '强共振',
                    ...
                }
            chan_result: 缠论适配结果（可选）
                {
                    'chan_summary': {
                        'chan_confirmation_score': 85,
                        ...
                    },
                    ...
                }

        返回：
            dict: 综合确认结果
        """
        # 提取各维度分数
        ai_score = self._extract_ai_score(ai_result)
        resonance_score = self._extract_resonance_score(resonance_result)
        chan_score = self._extract_chan_score(chan_result)

        # 计算加权综合分
        confirmation_score = self._calc_weighted_score(ai_score, resonance_score, chan_score)

        # 判断等级
        level, stars, level_name = self._judge_level(confirmation_score)

        # 生成组件详情
        components = self._build_components(ai_score, resonance_score, chan_score)

        # 生成总结
        summary = self._generate_summary(ai_score, resonance_score, chan_score, level)

        # 生成风险提示
        warnings = self._generate_warnings(ai_result, resonance_result, chan_result)

        # 保存原始分数（用于验证隔离）
        original_scores = {
            'ai_score': ai_score,
            'resonance_score': resonance_score,
            'chan_score': chan_score,
        }

        return {
            'confirmation_score': confirmation_score,
            'level': level,
            'stars': stars,
            'level_name': level_name,
            'components': components,
            'summary': summary,
            'warnings': warnings,
            'original_scores': original_scores,  # 用于验证隔离
        }

    def _extract_ai_score(self, ai_result):
        """提取AI评分"""
        if not ai_result:
            return 0
        if isinstance(ai_result, dict):
            return ai_result.get('score', 0)
        return 0

    def _extract_resonance_score(self, resonance_result):
        """提取多周期共振评分"""
        if not resonance_result:
            return 0
        if isinstance(resonance_result, dict):
            return resonance_result.get('resonance_score', 0)
        return 0

    def _extract_chan_score(self, chan_result):
        """提取缠论确认度"""
        if not chan_result:
            return 0
        if isinstance(chan_result, dict):
            summary = chan_result.get('chan_summary', {})
            return summary.get('chan_confirmation_score', 0)
        return 0

    def _calc_weighted_score(self, ai_score, resonance_score, chan_score):
        """计算加权综合分"""
        # 计算实际有效权重（缺失维度按比例分配）
        has_ai = ai_score > 0
        has_resonance = resonance_score > 0
        has_chan = chan_score > 0

        total_weight = 0
        if has_ai:
            total_weight += self.ai_weight
        if has_resonance:
            total_weight += self.resonance_weight
        if has_chan:
            total_weight += self.chan_weight

        if total_weight == 0:
            return 0

        # 按比例归一化权重
        weighted_score = 0
        if has_ai:
            adjusted_weight = self.ai_weight / total_weight
            weighted_score += ai_score * adjusted_weight
        if has_resonance:
            adjusted_weight = self.resonance_weight / total_weight
            weighted_score += resonance_score * adjusted_weight
        if has_chan:
            adjusted_weight = self.chan_weight / total_weight
            weighted_score += chan_score * adjusted_weight

        return round(weighted_score, 1)

    def _judge_level(self, score):
        """判断确认等级"""
        for threshold, level, name in self.level_thresholds:
            if score >= threshold:
                stars = '★' * level
                return level, stars, name
        return 1, '★', '无确认'

    def _build_components(self, ai_score, resonance_score, chan_score):
        """构建组件详情"""
        components = {}

        # AI评分组件
        components['ai_score'] = {
            'value': ai_score,
            'weight': int(self.ai_weight * 100),
            'description': self._describe_ai(ai_score),
        }

        # 多周期共振组件
        components['resonance'] = {
            'value': resonance_score,
            'weight': int(self.resonance_weight * 100),
            'description': self._describe_resonance(resonance_score),
        }

        # 缠论确认组件
        components['chan'] = {
            'value': chan_score,
            'weight': int(self.chan_weight * 100),
            'description': self._describe_chan(chan_score),
        }

        return components

    def _describe_ai(self, score):
        """描述AI评分"""
        if score >= 80:
            return '事件催化较强'
        elif score >= 65:
            return '有一定事件支撑'
        elif score >= 50:
            return '事件催化一般'
        else:
            return '事件催化不足'

    def _describe_resonance(self, score):
        """描述多周期共振"""
        if score >= 80:
            return '多周期共振较强'
        elif score >= 65:
            return '部分周期确认'
        elif score >= 50:
            return '周期确认一般'
        else:
            return '周期共振不足'

    def _describe_chan(self, score):
        """描述缠论确认度"""
        if score >= 80:
            return '缠论结构清晰'
        elif score >= 65:
            return '有一定结构支撑'
        elif score >= 50:
            return '结构确认一般'
        else:
            return '结构确认不足'

    def _generate_summary(self, ai_score, resonance_score, chan_score, level):
        """生成总结"""
        strong_dims = []
        if ai_score >= 75:
            strong_dims.append('事件')
        if resonance_score >= 75:
            strong_dims.append('周期')
        if chan_score >= 75:
            strong_dims.append('结构')

        if len(strong_dims) >= 3:
            return '事件、周期、结构形成共振'
        elif len(strong_dims) == 2:
            return f"{strong_dims[0]}与{strong_dims[1]}形成双确认"
        elif len(strong_dims) == 1:
            return f"{strong_dims[0]}维度较强，等待其他确认"
        else:
            return '各维度确认度均不足'

    def _generate_warnings(self, ai_result, resonance_result, chan_result):
        """生成风险提示"""
        warnings = []

        # 多周期风险
        if resonance_result and isinstance(resonance_result, dict):
            risk_warnings = resonance_result.get('risk_warning', [])
            if risk_warnings:
                warnings.extend(risk_warnings)

            # 高位风险
            if resonance_result.get('high_risk', False):
                warnings.append('高位风险，谨慎追涨')

            # 周期冲突
            conflict_level = resonance_result.get('conflict_level', 0)
            if conflict_level >= 2:
                warnings.append('周期存在冲突，注意方向风险')

        # 缠论风险
        if chan_result and isinstance(chan_result, dict):
            summary = chan_result.get('chan_summary', {})
            risk_points = summary.get('risk_points', [])
            if risk_points:
                warnings.extend(risk_points)

        return warnings

    def analyze_stock(self, code):
        """
        分析单只股票的综合确认度

        参数：
            code: 股票代码

        返回：
            dict: 综合确认结果
        """
        # 获取AI评分结果
        ai_result = self._get_ai_result(code)

        # 获取多周期共振结果
        resonance_result = self._get_resonance_result(code)

        # 获取缠论适配结果
        chan_result = self._get_chan_result(code)

        # 计算综合确认度
        return self.calculate_confirmation(ai_result, resonance_result, chan_result)

    def _get_ai_result(self, code):
        """获取AI评分结果（模拟，实际接入时替换）"""
        # TODO: 实际接入时调用AI买入信号引擎
        # 这里返回空，由外部传入完整结果
        return None

    def _get_resonance_result(self, code):
        """获取多周期共振结果"""
        try:
            from strategy.multi_period_resonance import get_multi_period_resonance
            resonance = get_multi_period_resonance()
            return resonance.analyze_stock(code)
        except Exception as e:
            print(f"[MultiConfirmation] 获取多周期共振失败: {e}")
            return None

    def _get_chan_result(self, code):
        """获取缠论适配结果"""
        try:
            from strategy.multi_period_chan_adapter import get_multi_period_chan_adapter
            adapter = get_multi_period_chan_adapter()
            return adapter.analyze_stock(code)
        except Exception as e:
            print(f"[MultiConfirmation] 获取缠论适配失败: {e}")
            return None


# 单例获取函数
_multi_confirmation_engine = None


def get_multi_confirmation_engine():
    """获取多维度确认引擎单例"""
    global _multi_confirmation_engine
    if _multi_confirmation_engine is None:
        _multi_confirmation_engine = MultiConfirmationEngine()
    return _multi_confirmation_engine
