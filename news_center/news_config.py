# -*- coding: utf-8 -*-
"""
实时新闻中心 - 全局配置模块
所有可调整参数集中在此，支持运行时读取与覆盖。
"""

import os
import json
from typing import Dict, List, Any

# ============================================================
# 项目路径
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_CACHE_DIR = os.path.join(BASE_DIR, 'cache', 'news_center')
os.makedirs(NEWS_CACHE_DIR, exist_ok=True)

# 配置文件路径（可选外部覆盖）
CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'news_center_config.json')


# ============================================================
# 标准新闻数据结构（所有来源统一映射为此格式）
# ============================================================
# {
#     'news_id':       str   新闻唯一ID（来源前缀+原始ID或哈希）
#     'title':         str   标题
#     'content':       str   内容摘要
#     'publish_time':  str   发布时间 'YYYY-MM-DD HH:MM'
#     'source':        str   来源名称（如 '巨潮资讯'）
#     'source_tag':    str   来源短标签（如 '巨潮'），用于UI前缀
#     'news_type':     str   新闻类型：公告/资讯/宏观/行业
#     'category':      str   业务分类：利好/利空/公司公告/资金/行业/国际/风险/热门
#     'stock_codes':   list  关联股票代码列表 [{'code':..., 'name':...}]
#     'hot_score':     int   热度值 0-100
#     'url':           str   原文链接
#     'is_new':        bool  是否为本次刷新新增（UI高亮用）
#     'multi_source':  bool  是否多源报道合并
#     'extra_sources': list  多源报道时的其他来源名称列表
# }

STANDARD_NEWS_FIELDS = [
    'news_id', 'title', 'content', 'publish_time', 'source', 'source_tag',
    'news_type', 'category', 'stock_codes', 'hot_score', 'url',
    'is_new', 'multi_source', 'extra_sources',
]


# ============================================================
# 数据源配置（按优先级排序）
# ============================================================
# priority: P0 > P1 > P2，数字越小优先级越高
# authority: 权威度评分，用于去重时保留权威来源
SOURCE_CONFIG = {
    'juchao': {
        'name': '巨潮资讯',
        'tag': '巨潮',
        'priority': 0,          # P0
        'authority': 100,       # 最高权威（官方公告）
        'news_type': '公告',
        'enabled': True,
        'timeout': 10,
        'max_retries': 2,
    },
    'akshare': {
        'name': 'AkShare财经',
        'tag': '财联社',
        'priority': 1,          # P1
        'authority': 80,
        'news_type': '资讯',
        'enabled': True,
        'timeout': 10,
        'max_retries': 2,
    },
    'ths': {
        'name': '同花顺7x24',
        'tag': '同花顺',
        'priority': 1,          # P1
        'authority': 75,
        'news_type': '资讯',
        'enabled': True,
        'timeout': 8,
        'max_retries': 2,
    },
    'eastmoney': {
        'name': '东方财富',
        'tag': '东财',
        'priority': 2,          # P2
        'authority': 70,
        'news_type': '行业',
        'enabled': True,
        'timeout': 10,
        'max_retries': 2,
    },
    'em_macro': {
        'name': '东财宏观',
        'tag': '东财宏观',
        'priority': 2,
        'authority': 70,
        'news_type': '宏观',
        'enabled': True,
        'timeout': 10,
        'max_retries': 1,
    },
    'em_global': {
        'name': '东财国际',
        'tag': '东财国际',
        'priority': 2,
        'authority': 70,
        'news_type': '国际',
        'enabled': True,
        'timeout': 10,
        'max_retries': 1,
    },
    'em_market': {
        'name': '东财市场',
        'tag': '东财市场',
        'priority': 2,
        'authority': 70,
        'news_type': '市场',
        'enabled': True,
        'timeout': 10,
        'max_retries': 1,
    },
    'em_commodity': {
        'name': '东财大宗',
        'tag': '东财大宗',
        'priority': 2,
        'authority': 70,
        'news_type': '大宗',
        'enabled': True,
        'timeout': 10,
        'max_retries': 1,
    },
    'sina': {
        'name': '新浪财经',
        'tag': '新浪',
        'priority': 2,          # P2
        'authority': 65,
        'news_type': '资讯',
        'enabled': True,
        'timeout': 10,
        'max_retries': 2,
    },
    'sina_7x24': {
        'name': '新浪7x24',
        'tag': '新浪7x24',
        'priority': 2,
        'authority': 60,
        'news_type': '资讯',
        'enabled': True,
        'timeout': 8,
        'max_retries': 2,
    },
}

# 来源权威度排序（去重时保留高权威来源）
AUTHORITY_ORDER = ['juchao', 'akshare', 'ths', 'eastmoney', 'em_macro', 'em_global', 'em_market', 'em_commodity', 'sina', 'sina_7x24']


# ============================================================
# 自动刷新配置
# ============================================================
REFRESH_CONFIG = {
    'active_interval': 60,        # 新闻页激活时刷新间隔（秒），默认1分钟
    'background_interval': 600,   # 切换到其他标签页时间隔（秒），默认10分钟
    'initial_delay': 2,           # 启动后首次刷新延迟（秒）
    'incremental_limit': 80,      # 每次增量刷新拉取条数
    'full_load_limit': 200,       # 首次全量加载条数
    'max_cached_news': 500,       # 内存最大保留新闻条数
    'cache_ttl_hours': 24,        # 已展示新闻缓存池有效期（小时）
    'new_highlight_duration': 8,  # 新增新闻高亮持续时间（秒）
    'request_timeout': 12,        # 单次全量刷新总超时（秒），目标≤2秒实际拉取
}


# ============================================================
# 去重配置
# ============================================================
DEDUP_CONFIG = {
    'similarity_threshold': 0.85,    # 标题相似度阈值（≥0.85判定重复）
    'keyword_match_min': 2,          # 关键词二次校验最小匹配数
    'event_window_minutes': 30,      # 事件级去重时间窗口（分钟）
    'enable_exact_dedup': True,      # 第一层：精确去重
    'enable_similarity_dedup': True, # 第二层：相似度去重
    'enable_event_dedup': True,      # 第三层：事件级去重
}


# ============================================================
# 投资日历配置
# ============================================================
CALENDAR_CONFIG = {
    'display_days': 7,               # 默认展示未来天数
    'auto_update_hour': 8,           # 每日自动更新时间（小时，开盘前）
    'enabled_types': ['新股', '解禁', '财报', '宏观', '事件'],
    'cache_file': os.path.join(NEWS_CACHE_DIR, 'calendar_cache.json'),
    'cache_ttl_hours': 12,
}

# 日历事件类型颜色映射（匹配浅色商务UI）
CALENDAR_TYPE_COLORS = {
    '新股': '#2563EB',    # 蓝
    '解禁': '#DC2626',    # 红
    '财报': '#7C3AED',    # 紫
    '宏观': '#0891B2',    # 青
    '事件': '#D97706',    # 橙
}

CALENDAR_TYPE_ICONS = {
    '新股': '🆕',
    '解禁': '🔓',
    '财报': '📊',
    '宏观': '📈',
    '事件': '📅',
}


# ============================================================
# 性能与内存约束
# ============================================================
PERFORMANCE_CONFIG = {
    'max_refresh_duration_sec': 2,   # 单次全量刷新耗时上限（秒）
    'max_daily_cache_mb': 50,        # 单日新闻缓存内存上限（MB）
    'parallel_fetch_workers': 5,     # 并行拉取线程数
    'source_fail_threshold': 3,      # 单源连续失败次数阈值（临时降级）
    'source_cooldown_rounds': 1,     # 降级后冷却轮数（下一轮自动重试）
}


# ============================================================
# 外部配置文件加载（可选覆盖）
# ============================================================
def load_external_config() -> Dict[str, Any]:
    """从 config/news_center_config.json 加载外部覆盖配置（如果存在）"""
    overrides = {}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
            print(f"[新闻中心] 已加载外部配置: {CONFIG_FILE}", flush=True)
    except Exception as e:
        print(f"[新闻中心] 外部配置加载失败（使用默认值）: {e}", flush=True)
    return overrides


def apply_overrides(module_dict: Dict, overrides: Dict, key: str):
    """将外部配置覆盖应用到指定配置字典，跳过以_开头的说明字段"""
    if key in overrides and isinstance(overrides[key], dict):
        for k, v in overrides[key].items():
            if k.startswith('_'):
                continue  # 跳过说明字段
            if isinstance(v, dict) and k in module_dict and isinstance(module_dict[k], dict):
                module_dict[k].update(v)
            else:
                module_dict[k] = v


# 启动时尝试加载外部覆盖
_external = load_external_config()
if _external:
    apply_overrides(SOURCE_CONFIG, _external, 'sources')
    apply_overrides(REFRESH_CONFIG, _external, 'refresh')
    apply_overrides(DEDUP_CONFIG, _external, 'dedup')
    apply_overrides(CALENDAR_CONFIG, _external, 'calendar')
    apply_overrides(PERFORMANCE_CONFIG, _external, 'performance')


def get_enabled_sources() -> List[str]:
    """获取当前启用的数据源key列表（按优先级排序）"""
    return [k for k, v in SOURCE_CONFIG.items()
            if isinstance(v, dict) and v.get('enabled', True)]


def get_source_info(source_key: str) -> Dict:
    """获取数据源配置"""
    return SOURCE_CONFIG.get(source_key, {})
