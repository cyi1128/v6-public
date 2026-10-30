# -*- coding: utf-8 -*-
"""
信号参数配置管理
支持每个信号的参数手动配置和持久化
"""
import os
import json
import copy


# 默认信号参数配置
DEFAULT_SIGNAL_PARAMS = {
    # ===== 基础信号 =====
    'horizontal_base': {
        'name': '横盘筑底',
        'enabled': True,
        'params': {
            'days': 20,           # 横盘天数
            'amplitude_max': 15, # 最大振幅%
            'vol_shrink': 0.7,   # 成交量萎缩比例
        }
    },
    'sharp_angle': {
        'name': '锐角',
        'enabled': True,
        'params': {
            'angle_min': 30,     # MA5/MA20角度最小值
        }
    },
    'ma5_touch': {
        'name': '五日线',
        'enabled': True,
        'params': {
            'distance_pct': 2,   # 收盘价距MA5百分比%
        }
    },
    'cross_5_10': {
        'name': '一阳穿5/10',
        'enabled': True,
        'params': {
            'yang_min_pct': 1,   # 阳线最小涨幅%
        }
    },
    'cross_three': {
        'name': '一阳穿三线',
        'enabled': True,
        'params': {
            'yang_min_pct': 2,   # 阳线最小涨幅%
        }
    },
    'double_volume': {
        'name': '倍量',
        'enabled': True,
        'params': {
            'ratio_min': 2.0,    # 成交量倍数最小值
        }
    },
    'pullback': {
        'name': '回踩',
        'enabled': True,
        'params': {
            'lookback_days': 20, # 回看天数
            'big_yang_min': 3,   # 大阳线最小涨幅%
            'big_yang_max': 7,   # 大阳线最大涨幅%
            'vol_increase': 1.3, # 放量倍数
            'pullback_dist': 3,  # 回踩距离%
        }
    },
    'buy_point': {
        'name': '注意买点',
        'enabled': True,
        'params': {
            'golden_lookback': 3, # 金叉回看天数
            'near_ma_pct': 2,     # 接近均线百分比%
        }
    },

    # ===== 五九回踩精准信号 =====
    'low_5k': {
        'name': '低价5k',
        'enabled': True,
        'params': {
            'diff_min': 0.03,    # 最低价距MA5最小值(元)
            'diff_max': 0.3,     # 最低价距MA5最大值(元)
        }
    },
    'low_9k': {
        'name': '低价9k',
        'enabled': True,
        'params': {
            'diff_min': 0.1,     # 最低价距MA9最小值(元)
            'diff_max': 0.4,     # 最低价距MA9最大值(元)
        }
    },
    'close_5k': {
        'name': '收盘5k',
        'enabled': True,
        'params': {
            'diff_min': -0.5,    # 收盘价距MA5最小值(元)
            'diff_max': -0.1,    # 收盘价距MA5最大值(元)
        }
    },
    'close_9k': {
        'name': '收盘9k',
        'enabled': True,
        'params': {
            'diff_min': -0.3,    # 收盘价距MA9最小值(元)
            'diff_max': 0.01,    # 收盘价距MA9最大值(元)
        }
    },

    # ===== 五九策略信号 =====
    'line_59': {
        'name': '59线',
        'enabled': True,
        'params': {
            'adjust_days': 2,    # 连续调整天数
            'mild_drop_max': 0.5,# 温和调整最大跌幅(元)
            'turnover_min': 0.4, # 最小换手率%
            'turnover_max': 2.7, # 最大换手率%
        }
    },
    'parallel_5': {
        'name': '平行5',
        'enabled': True,
        'params': {
            'dist_min': -0.1,    # 收盘价距MA5最小值(元)
            'dist_max': 0.1,     # 收盘价距MA5最大值(元)
        }
    },
    'buy_confirm': {
        'name': '买入',
        'enabled': True,
        'params': {
            'lower_shadow_min': 0.3, # 长下影线最小值(元)
        }
    },
}


class SignalConfig:
    """信号参数配置管理"""

    _instance = None
    _config = None
    _config_path = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'signal_params.json'
            )
            self._load()

    def _load(self):
        """加载配置"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                # 合并默认配置和保存的配置
                self._config = copy.deepcopy(DEFAULT_SIGNAL_PARAMS)
                for key, value in saved.items():
                    if key in self._config:
                        if 'params' in value:
                            self._config[key]['params'].update(value.get('params', {}))
                        if 'enabled' in value:
                            self._config[key]['enabled'] = value['enabled']
            except Exception as e:
                print(f"加载信号配置失败: {e}，使用默认配置")
                self._config = copy.deepcopy(DEFAULT_SIGNAL_PARAMS)
        else:
            self._config = copy.deepcopy(DEFAULT_SIGNAL_PARAMS)
            self.save()

    def save(self):
        """保存配置"""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def get_all(self):
        """获取所有信号配置"""
        return copy.deepcopy(self._config)

    def get_signal(self, signal_key):
        """获取单个信号配置"""
        return copy.deepcopy(self._config.get(signal_key, {}))

    def get_params(self, signal_key):
        """获取单个信号的参数"""
        sig = self._config.get(signal_key, {})
        return copy.deepcopy(sig.get('params', {}))

    def is_enabled(self, signal_key):
        """检查信号是否启用"""
        sig = self._config.get(signal_key, {})
        return sig.get('enabled', True)

    def set_param(self, signal_key, param_name, value):
        """设置单个参数"""
        if signal_key in self._config:
            if 'params' not in self._config[signal_key]:
                self._config[signal_key]['params'] = {}
            self._config[signal_key]['params'][param_name] = value
            self.save()

    def set_enabled(self, signal_key, enabled):
        """设置信号启用状态"""
        if signal_key in self._config:
            self._config[signal_key]['enabled'] = enabled
            self.save()

    def set_signal_config(self, signal_key, config):
        """设置整个信号配置"""
        if signal_key in self._config:
            self._config[signal_key].update(config)
            self.save()

    def reset_to_default(self, signal_key=None):
        """重置为默认配置"""
        if signal_key:
            if signal_key in DEFAULT_SIGNAL_PARAMS:
                self._config[signal_key] = copy.deepcopy(DEFAULT_SIGNAL_PARAMS[signal_key])
                self.save()
        else:
            self._config = copy.deepcopy(DEFAULT_SIGNAL_PARAMS)
            self.save()

    def get_signal_list(self):
        """获取信号列表（key, name, enabled）"""
        result = []
        for key, cfg in self._config.items():
            result.append({
                'key': key,
                'name': cfg.get('name', key),
                'enabled': cfg.get('enabled', True),
            })
        return result


# 便捷函数
def get_signal_params(signal_key):
    """获取信号参数（便捷函数）"""
    return SignalConfig().get_params(signal_key)

def is_signal_enabled(signal_key):
    """检查信号是否启用（便捷函数）"""
    return SignalConfig().is_enabled(signal_key)
