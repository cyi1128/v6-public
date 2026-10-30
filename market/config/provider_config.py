"""
行情连接配置文件
所有行情数据源的连接配置都在这里管理
"""
import json
import os
from typing import Dict, Any


# 默认配置
DEFAULT_CONFIG = {
    # 当前使用的行情源
    'current_provider': 'tdx',

    # 通达信配置
    'tdx': {
        'enabled': True,
        'servers': [
            ['180.153.18.170', 7709],   # 上海联通（当前可用）
            ['119.147.212.81', 7709],   # 深圳行情主站1
            ['119.147.212.82', 7709],   # 深圳行情主站2
            ['218.108.98.244', 7709],   # 杭州电信
            ['218.108.47.69', 7709],    # 杭州联通
            ['124.160.88.183', 7709],   # 宁波电信
            ['60.12.136.250', 7709],    # 绍兴电信
            ['115.238.56.198', 7709],   # 台州电信
            ['218.75.126.9', 7709],     # 长沙电信
            ['124.74.236.94', 7709],    # 上海电信
        ],
        'timeout': 5,
        'auto_reconnect': True,
        'max_retry': 3,
    },

    # 东方财富配置
    'eastmoney': {
        'enabled': False,
        'api_key': '',
        'base_url': 'https://push2delay.eastmoney.com',
        'timeout': 10,
    },

    # 腾讯行情配置
    'tencent': {
        'enabled': False,
        'base_url': 'https://qt.gtimg.cn',
        'timeout': 10,
    },

    # 聚宽配置
    'joinquant': {
        'enabled': False,
        'username': '',
        'password': '',
        'timeout': 10,
    },

    # 米筐配置
    'ricequant': {
        'enabled': False,
        'username': '',
        'password': '',
        'timeout': 10,
    },

    # 通用配置
    'common': {
        'cache_enabled': True,
        'cache_ttl': 60,  # 缓存过期时间（秒）
        'max_concurrent': 10,
        'retry_on_fail': True,
        'failover_provider': 'tdx',  # 主源失败时切换到备用源
    }
}


class MarketConfig:
    """行情配置管理器"""

    _instance = None
    _config = None
    _config_file = None

    def __new__(cls, config_file: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config(config_file)
        return cls._instance

    def _init_config(self, config_file: str = None):
        """初始化配置"""
        if config_file:
            self._config_file = config_file
        else:
            # 默认配置文件路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._config_file = os.path.join(base_dir, 'config', 'market_config.json')

        # 加载配置
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        self._config = DEFAULT_CONFIG.copy()

        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 深度合并配置
                    self._deep_merge(self._config, user_config)
            except Exception as e:
                print(f"加载行情配置失败: {e}，使用默认配置")

    def _deep_merge(self, base: dict, override: dict):
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def save_config(self):
        """保存配置到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self._config_file), exist_ok=True)

            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存行情配置失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的路径"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        """设置配置项，支持点号分隔的路径"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def get_provider_config(self, provider_name: str) -> dict:
        """获取指定提供者的配置"""
        return self._config.get(provider_name, {})

    def get_current_provider(self) -> str:
        """获取当前使用的行情源"""
        return self._config.get('current_provider', 'tdx')

    def set_current_provider(self, provider_name: str):
        """设置当前使用的行情源"""
        self._config['current_provider'] = provider_name

    def get_available_providers(self) -> list:
        """获取可用的行情源列表"""
        providers = []
        for name, config in self._config.items():
            if isinstance(config, dict) and config.get('enabled', False):
                providers.append(name)
        return providers

    def add_tdx_server(self, host: str, port: int = 7709):
        """添加通达信服务器"""
        servers = self._config['tdx'].get('servers', [])
        servers.append([host, port])
        self._config['tdx']['servers'] = servers

    def remove_tdx_server(self, index: int):
        """移除通达信服务器"""
        servers = self._config['tdx'].get('servers', [])
        if 0 <= index < len(servers):
            servers.pop(index)
            self._config['tdx']['servers'] = servers

    def get_tdx_servers(self) -> list:
        """获取通达信服务器列表"""
        return self._config['tdx'].get('servers', [])

    def set_tdx_servers(self, servers: list):
        """设置通达信服务器列表"""
        self._config['tdx']['servers'] = servers

    def test_provider(self, provider_name: str) -> dict:
        """测试指定行情源连接"""
        try:
            from .providers import PROVIDER_REGISTRY
            if provider_name not in PROVIDER_REGISTRY:
                return {
                    'success': False,
                    'message': f'未知的行情源: {provider_name}'
                }

            provider_cls = PROVIDER_REGISTRY[provider_name]
            config = self.get_provider_config(provider_name)
            provider = provider_cls(config)
            return provider.test_connection()
        except Exception as e:
            return {
                'success': False,
                'message': f'测试失败: {str(e)}'
            }


def get_market_config() -> MarketConfig:
    """获取行情配置单例"""
    return MarketConfig()
