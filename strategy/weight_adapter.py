# -*- coding: utf-8 -*-
"""
V0.6.1 策略权重适配器

定位：
连接 V0.5.7.2 动态策略权重 → AI评分修正 → decision_engine

原则：
- 不修改核心策略逻辑
- 不改变原始买卖规则
- 默认兼容旧模式（默认关闭）
- AI权重只作为评分增强因子
- 支持开关控制
- 可回滚
"""
import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

# 动态导入learning层，避免循环依赖
_LEARNING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backtest')
if _LEARNING_PATH not in sys.path:
    sys.path.append(_LEARNING_PATH)


class WeightAdapter:
    """
    策略权重适配器

    用法：
        adapter = WeightAdapter(enable=True)
        adjusted = adapter.adjust_score('MACD金叉', 80)
        # 返回 80 × 1.18 = 94.4
    """

    # 默认配置
    DEFAULT_ENABLE = False          # 默认关闭，兼容旧模式
    MIN_SAMPLE_COUNT = 10           # 最小样本数
    MAX_SCORE = 100                 # 评分上限
    MIN_SCORE = 0                   # 评分下限
    DEFAULT_WEIGHT = 1.0            # 默认权重（无数据时）

    def __init__(self, enable: bool = None, weight_manager=None):
        """
        初始化

        参数：
            enable: 是否启用动态权重（None则使用默认）
            weight_manager: 外部传入的权重管理器（None则自动创建）
        """
        self.enable = self.DEFAULT_ENABLE if enable is None else enable
        self._weight_manager = weight_manager
        self._adjust_history: list = []

    @property
    def weight_manager(self):
        """懒加载权重管理器"""
        if self._weight_manager is None:
            try:
                from backtest.learning.strategy_weight import StrategyWeightManager
                self._weight_manager = StrategyWeightManager()
            except ImportError:
                self._weight_manager = None
        return self._weight_manager

    def get_strategy_weight(self, strategy_name: str) -> Dict:
        """
        读取策略动态权重

        参数：
            strategy_name: 策略名称（实时信号名或标准策略名均可）

        返回：
            {
                "strategy": "涨停突破",
                "original_name": "涨停异动信号",
                "weight": 1.18,
                "source": "learning",
                "sample": 50,
                "win_rate": 66.7,
                "adjusted": True
            }
        """
        # V0.6.1.1 策略名称映射：实时信号名 → 标准学习策略标签
        try:
            from backtest.learning.strategy_mapping import map_signal_to_strategy
            standard_name = map_signal_to_strategy(strategy_name)
        except ImportError:
            standard_name = strategy_name

        default_result = {
            'strategy': standard_name,
            'original_name': strategy_name,
            'weight': self.DEFAULT_WEIGHT,
            'source': 'default',
            'sample': 0,
            'win_rate': 0,
            'adjusted': False,
            'reason': '权重管理器不可用',
        }

        if not self.enable:
            default_result['reason'] = '动态权重未启用'
            return default_result

        wm = self.weight_manager
        if wm is None:
            return default_result

        try:
            weight_info = wm.calculate_dynamic_weight(standard_name)
            sample = weight_info.get('sample_count', 0)

            # 小样本保护
            if sample < self.MIN_SAMPLE_COUNT:
                return {
                    'strategy': standard_name,
                    'original_name': strategy_name,
                    'weight': self.DEFAULT_WEIGHT,
                    'source': 'learning',
                    'sample': sample,
                    'win_rate': weight_info.get('performance', {}).get('win_rate', 0),
                    'adjusted': False,
                    'reason': f'样本不足({sample}<{self.MIN_SAMPLE_COUNT})，保持默认权重',
                }

            return {
                'strategy': standard_name,
                'original_name': strategy_name,
                'weight': weight_info.get('dynamic_weight', self.DEFAULT_WEIGHT),
                'source': 'learning',
                'sample': sample,
                'win_rate': weight_info.get('performance', {}).get('win_rate', 0),
                'adjusted': weight_info.get('adjusted', False),
                'reason': weight_info.get('reason', ''),
            }
        except Exception as ex:
            default_result['reason'] = f'权重计算异常: {ex}'
            return default_result

    def adjust_score(self, strategy_name: str, original_score: float) -> Dict:
        """
        AI评分增强

        参数：
            strategy_name: 策略名称
            original_score: 原始评分（0-100）

        返回：
            {
                "strategy": "MACD金叉",
                "original_score": 80,
                "weight": 1.18,
                "adjusted_score": 94.4,
                "score_change": +14.4,
                "sample": 50,
                "enabled": True,
                "reason": "..."
            }
        """
        weight_info = self.get_strategy_weight(strategy_name)
        weight = weight_info['weight']

        # 评分修正：new_score = original_score × weight
        raw_adjusted = original_score * weight
        adjusted_score = max(self.MIN_SCORE, min(self.MAX_SCORE, round(raw_adjusted, 1)))
        score_change = round(adjusted_score - original_score, 1)

        result = {
            'strategy': weight_info.get('strategy', strategy_name),  # V0.6.1.1 映射后的标准策略名
            'original_name': strategy_name,  # V0.6.1.1 原始信号名
            'original_score': original_score,
            'weight': round(weight, 3),
            'adjusted_score': adjusted_score,
            'score_change': score_change,
            'sample': weight_info['sample'],
            'win_rate': weight_info['win_rate'],
            'enabled': self.enable and weight_info['adjusted'],
            'source': weight_info['source'],
            'reason': weight_info['reason'],
        }

        # 记录历史
        self._adjust_history.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategy': strategy_name,
            'original': original_score,
            'adjusted': adjusted_score,
            'weight': weight,
            'enabled': result['enabled'],
        })

        return result

    def adjust_decision(self, decision_data: Dict) -> Dict:
        """
        对完整决策数据应用权重修正

        参数：
            decision_data: 决策数据，需包含：
                - strategy: 策略名称
                - score: 原始评分
                （其他字段透传）

        返回：
            增强后的决策数据，新增：
                - original_score
                - dynamic_weight
                - adjusted_score
                - weight_enabled
        """
        result = dict(decision_data)
        strategy = decision_data.get('strategy', '')
        original_score = decision_data.get('score', 0)

        if not strategy:
            result['weight_enabled'] = False
            result['original_score'] = original_score
            result['dynamic_weight'] = 1.0
            result['adjusted_score'] = original_score
            return result

        adjusted = self.adjust_score(strategy, original_score)
        result['original_score'] = original_score
        result['dynamic_weight'] = adjusted['weight']
        result['adjusted_score'] = adjusted['adjusted_score']
        result['score_change'] = adjusted['score_change']
        result['weight_enabled'] = adjusted['enabled']
        result['weight_reason'] = adjusted['reason']

        # 如果启用了权重，用修正后的分数覆盖score
        if adjusted['enabled']:
            result['score'] = adjusted['adjusted_score']

        return result

    def batch_adjust(self, decisions: list) -> list:
        """
        批量调整决策列表

        参数：
            decisions: 决策数据列表

        返回：
            调整后的决策列表
        """
        return [self.adjust_decision(d) for d in decisions]

    def set_enable(self, enable: bool):
        """开关控制"""
        self.enable = enable

    def get_history(self) -> list:
        """获取调整历史"""
        return self._adjust_history

    def render_status(self) -> str:
        """渲染适配器状态"""
        lines = [
            "=" * 50,
            "策略权重适配器 (V0.6.1)",
            "=" * 50,
            f"启用状态: {'已启用' if self.enable else '已关闭(默认)'}",
            f"最小样本: {self.MIN_SAMPLE_COUNT}",
            f"评分范围: {self.MIN_SCORE}-{self.MAX_SCORE}",
            f"权重管理器: {'已加载' if self.weight_manager else '未加载'}",
            f"历史调整次数: {len(self._adjust_history)}",
            "=" * 50,
        ]
        return "\n".join(lines)


# 单例
_adapter_instance = None


def get_weight_adapter(enable: bool = None) -> WeightAdapter:
    """获取策略权重适配器单例"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = WeightAdapter(enable=enable)
    elif enable is not None:
        _adapter_instance.set_enable(enable)
    return _adapter_instance
