# -*- coding: utf-8 -*-
"""
策略配置管理模块

支持：
- 预设策略（趋势突破、强势突破、稳健低吸）
- 用户自定义策略（自然语言创建）
- 策略条件编辑
- JSON持久化
"""
import json
import os
from copy import deepcopy


# 默认策略配置
DEFAULT_STRATEGIES = [
    {
        "id": "trend_breakout",
        "name": "趋势突破池",
        "description": "价格在8个月高点85%-130%区间 | 主板非ST | 市值>30亿且≤230亿 | 年涨停≥3次 | 前一天未涨停 | 排除地产/农业/酒/保险",
        "conditions": {
            "main_board_only": True,
            "exclude_st": True,
            "price_range": [5, 60],
            "market_cap_range": [30, 230],
            "limit_up_count_min": 3,
            "no_limit_up_yesterday": True,
            "high_ratio_range": [0.85, 1.30],
            "high_period_days": 160,
            "exclude_industries": ["地产", "农业", "酒", "保险"],
            "turnover_range": [0, 100],
            "volume_ratio_min": 0
        }
    },
    {
        "id": "strong_breakout",
        "name": "强势突破池",
        "description": "15日内连续4天站稳20日线 | 放量突破(>120日均量,换手>7%) | 7日内涨停或大涨 | 主板非ST",
        "conditions": {
            "main_board_only": True,
            "exclude_st": True,
            "price_range": [5, 60],
            "market_cap_range": [20, 500],
            "limit_up_count_min": 1,
            "ma20_above_days": 4,
            "lookback_days": 15,
            "volume_ratio_min": 1.5,
            "turnover_range": [7, 100],
            "exclude_industries": []
        }
    },
    {
        "id": "steady_pullback",
        "name": "稳健低吸池",
        "description": "主板非ST | 近2日涨幅<7%且当日<3% | 振幅<5% | 换手1%-7% | RSI 30-70 | 按量比降序",
        "conditions": {
            "main_board_only": True,
            "exclude_st": True,
            "price_range": [5, 60],
            "market_cap_range": [30, 500],
            "turnover_range": [1, 7],
            "amplitude_max": 5,
            "rsi_range": [30, 70],
            "pct_chg_2d_max": 7,
            "pct_chg_today_max": 3,
            "exclude_industries": []
        }
    }
]


class StrategyManager:
    """策略管理器（单例）"""
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
        self._config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config'
        )
        self._config_file = os.path.join(self._config_dir, 'strategies.json')
        self._strategies = []
        self._load()

    def _load(self):
        """加载策略配置"""
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    self._strategies = json.load(f)
                return
            except Exception:
                pass
        # 使用默认策略
        self._strategies = deepcopy(DEFAULT_STRATEGIES)
        self._save()

    def _save(self):
        """保存策略配置"""
        os.makedirs(self._config_dir, exist_ok=True)
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._strategies, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[StrategyManager] 保存失败: {e}")

    def get_all(self):
        """获取所有策略"""
        return deepcopy(self._strategies)

    def get_by_id(self, strategy_id):
        """根据ID获取策略"""
        for s in self._strategies:
            if s['id'] == strategy_id:
                return deepcopy(s)
        return None

    def get_by_name(self, name):
        """根据名称获取策略"""
        for s in self._strategies:
            if s['name'] == name:
                return deepcopy(s)
        return None

    def get_names(self):
        """获取所有策略名称列表"""
        return [s['name'] for s in self._strategies]

    def add_strategy(self, name, description, conditions):
        """添加新策略"""
        strategy_id = f"custom_{len(self._strategies)}_{int(__import__('time').time())}"
        new_strategy = {
            "id": strategy_id,
            "name": name,
            "description": description,
            "conditions": conditions
        }
        self._strategies.append(new_strategy)
        self._save()
        return strategy_id

    def update_strategy(self, strategy_id, name=None, description=None, conditions=None):
        """更新策略"""
        for s in self._strategies:
            if s['id'] == strategy_id:
                if name is not None:
                    s['name'] = name
                if description is not None:
                    s['description'] = description
                if conditions is not None:
                    s['conditions'] = conditions
                self._save()
                return True
        return False

    def delete_strategy(self, strategy_id):
        """删除策略（不允许删除默认策略）"""
        default_ids = [s['id'] for s in DEFAULT_STRATEGIES]
        if strategy_id in default_ids:
            return False
        for i, s in enumerate(self._strategies):
            if s['id'] == strategy_id:
                self._strategies.pop(i)
                self._save()
                return True
        return False

    def reset_to_default(self):
        """重置为默认策略"""
        self._strategies = deepcopy(DEFAULT_STRATEGIES)
        self._save()


def get_strategy_manager():
    """获取策略管理器单例"""
    return StrategyManager()
