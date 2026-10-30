# -*- coding: utf-8 -*-
"""
策略模块

V0.6.1 新增: weight_adapter - 策略权重适配器
V0.7   新增: factor_score / factor_config - 8因子综合评分引擎
"""
from strategy.weight_adapter import WeightAdapter, get_weight_adapter
from strategy.factor_score import FactorScorer, score_stock, score_stock_from_duckdb
from strategy.factor_config import SCORE_WEIGHTS, get_score_level

__all__ = [
    'WeightAdapter',
    'get_weight_adapter',
    'FactorScorer',
    'score_stock',
    'score_stock_from_duckdb',
    'SCORE_WEIGHTS',
    'get_score_level',
]
