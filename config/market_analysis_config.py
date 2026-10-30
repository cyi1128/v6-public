# -*- coding: utf-8 -*-
"""
V2.8 市场分析与推送增强配置
所有功能默认关闭，通过开关控制，不影响原有推送逻辑
"""
import os

# ============================================================
# 总开关
# ============================================================
ENABLE_MARKET_ANALYSIS = False  # 市场分析总开关（关闭时所有子模块均不执行）

# ============================================================
# 模块1：竞价强度 auction_strength
# ============================================================
AUCTION_STRENGTH_CONFIG = {
    'enabled': False,
    'data_source': 'pytdx',  # pytdx / akshare
    'auction_volume_ratio_threshold': 3.0,  # 竞价量比≥3倍标注主力抢筹
    'virtual_rally_pct': 2.0,  # 高开≥2%但无量标注无量虚拉
    'timeout': 3,  # 接口超时秒数
    'retry': 1,  # 失败重试次数
}

# ============================================================
# 模块2：板块强度评级 sector_strength
# ============================================================
SECTOR_STRENGTH_CONFIG = {
    'enabled': False,
    'weights': {
        'sector_pct': 30,      # 板块涨跌幅
        'advance_decline': 20,  # 涨跌家数比
        'limit_up_count': 20,   # 涨停家数
        'main_net_inflow': 20,  # 主力净流入
        'ma20_trend': 10,       # MA20趋势位置
    },
    'grade_thresholds': {'S': 90, 'A': 80, 'B': 70, 'C': 60},  # 60以下D
    'timeout': 3,
    'retry': 1,
}

# ============================================================
# 模块3：个股深度资金面 deep_fund_flow
# ============================================================
DEEP_FUND_FLOW_CONFIG = {
    'enabled': False,
    'data_source': 'eastmoney',  # eastmoney / akshare
    'show_dragon_tiger': True,   # 龙虎榜数据（未上榜自动隐藏）
    'show_northbound': True,      # 北向资金（无数据自动隐藏）
    'northbound_days': 3,         # 北向资金近N日
    'timeout': 3,
    'retry': 1,
}

# ============================================================
# 模块4：实时市场情绪 market_sentiment
# ============================================================
MARKET_SENTIMENT_CONFIG = {
    'enabled': False,
    'update_interval': 3600,  # 每小时更新一次（秒）
    'sentiment_levels': {
        'big_profit': {'advance_ratio': 0.7, 'limit_up': 50},   # 大赚
        'small_profit': {'advance_ratio': 0.55, 'limit_up': 30}, # 小赚
        'balance': {'advance_ratio': 0.45, 'limit_up': 15},      # 平衡
        'small_loss': {'advance_ratio': 0.35, 'limit_up': 10},    # 小亏
        # 以下为大亏
    },
    'timeout': 3,
    'retry': 1,
}

# ============================================================
# 模块5：板块异动监控 sector_anomaly
# ============================================================
SECTOR_ANOMALY_CONFIG = {
    'enabled': False,
    'surge_threshold': 1.5,    # 5分钟涨幅≥1.5%触发拉升异动
    'drop_threshold': 1.5,     # 5分钟跌幅≥1.5%触发跳水异动
    'check_interval': 300,     # 检查间隔（秒），默认5分钟
    'dedup_minutes': 30,       # 同一板块30分钟内不重复推送
    'independent_push': True,   # 独立推送不占用个股信号通道
    'timeout': 3,
    'retry': 1,
}

# ============================================================
# 任务二：政策与事件驱动匹配 policy_matcher
# ============================================================
POLICY_MATCHER_CONFIG = {
    'enabled': False,
    'data_source': 'akshare',  # akshare / eastmoney / local
    'match_industries': True,   # 匹配持仓/信号股所属行业
    'cache_hours': 6,           # 政策新闻缓存小时数
    'timeout': 3,
    'retry': 1,
}

# ============================================================
# 任务三：定时简报 timed_report
# ============================================================
TIMED_REPORT_CONFIG = {
    'enabled': False,
    'premarket': {
        'enabled': False,
        'time': '08:50',       # 盘前策略简报时间
        'include_overnight': True,   # 隔夜外围
        'include_today_focus': True, # 今日重点
        'include_main_line': True,   # 今日主线关注
        'include_risk': True,        # 今日风险
        'include_position': True,     # 仓位建议
    },
    'intraday': {
        'enabled': False,
        'times': ['10:30', '14:00'],  # 盘中动态简报时间
        'include_market': True,         # 大盘表现
        'include_top_sectors': True,    # 领涨板块
        'include_sentiment': True,      # 市场情绪
        'include_advice': True,          # 操作提示
    },
    'postmarket': {
        'enabled': False,
        'time': '15:30',          # 盘后总结报告时间
        'prefer_image': True,      # 优先生成PNG图片推送
        'image_fallback': True,    # 图片失败自动降级Markdown长文
        'include_full_review': True,    # 全天行情复盘
        'include_sector_rotation': True, # 板块轮动图谱
        'include_all_signals': True,     # AI520全部信号汇总
        'include_dragon_tiger': True,    # 龙虎榜解读
        'include_fund_flow': True,        # 资金流向总结
        'include_outlook': True,          # 明日展望
        'include_position': True,          # 仓位建议
    },
    'timeout': 5,
    'retry': 1,
}

# ============================================================
# 推送层扩展配置
# ============================================================
PUSH_EXTENSION_CONFIG = {
    'enabled': False,  # 推送扩展总开关
    'embed_auction_strength': False,    # 个股推送嵌入竞价强度
    'embed_sector_strength': False,     # 个股推送嵌入板块强度
    'embed_deep_fund_flow': False,      # 个股推送嵌入深度资金面
    'embed_market_sentiment': False,     # 个股推送嵌入市场情绪
    'embed_policy_catalyst': False,      # 个股推送嵌入政策催化
    'sector_anomaly_push': False,        # 板块异动独立推送
    'timed_report_push': False,          # 定时简报推送
    'field_order': ['auction', 'sector', 'fund', 'policy', 'risk'],  # 新增字段顺序
}

# ============================================================
# 数据源配置
# ============================================================
DATA_SOURCE_CONFIG = {
    'kline': 'duckdb_cache',    # K线数据源：duckdb_cache / pytdx
    'realtime_quote': 'pytdx',  # 实时行情：pytdx / eastmoney
    'sector_data': 'eastmoney',  # 板块数据：eastmoney / akshare
    'fund_flow': 'eastmoney',    # 资金流向：eastmoney
    'news': 'akshare',           # 新闻政策：akshare / eastmoney
    'akshare_available': False,  # AkShare是否可用（运行时自动检测）
}

# ============================================================
# 通用配置
# ============================================================
GENERAL_CONFIG = {
    'request_timeout': 3,        # 所有接口请求超时（秒）
    'max_retry': 1,              # 失败重试次数
    'log_enabled': True,         # 模块日志开关
    'log_performance': True,     # 记录计算耗时
    'background_thread': True,   # 数据计算在独立后台线程
    'fail_silent': True,         # 异常仅记录日志不弹窗不中断
    'auto_degrade': True,        # 新增模块异常时自动降级为原有推送逻辑
    'hide_empty_fields': True,   # 数据缺失时自动隐藏对应字段
}


def get_config():
    """获取完整配置（运行时可动态修改）"""
    return {
        'enable_market_analysis': ENABLE_MARKET_ANALYSIS,
        'auction': AUCTION_STRENGTH_CONFIG,
        'sector': SECTOR_STRENGTH_CONFIG,
        'deep_fund': DEEP_FUND_FLOW_CONFIG,
        'sentiment': MARKET_SENTIMENT_CONFIG,
        'sector_anomaly': SECTOR_ANOMALY_CONFIG,
        'policy': POLICY_MATCHER_CONFIG,
        'timed_report': TIMED_REPORT_CONFIG,
        'push_extension': PUSH_EXTENSION_CONFIG,
        'data_source': DATA_SOURCE_CONFIG,
        'general': GENERAL_CONFIG,
    }


def is_module_enabled(module_name: str) -> bool:
    """检查指定模块是否启用（受总开关控制）"""
    if not ENABLE_MARKET_ANALYSIS:
        return False
    config_map = {
        'auction': AUCTION_STRENGTH_CONFIG,
        'sector': SECTOR_STRENGTH_CONFIG,
        'deep_fund': DEEP_FUND_FLOW_CONFIG,
        'sentiment': MARKET_SENTIMENT_CONFIG,
        'sector_anomaly': SECTOR_ANOMALY_CONFIG,
        'policy': POLICY_MATCHER_CONFIG,
    }
    if module_name in config_map:
        return config_map[module_name].get('enabled', False)
    if module_name == 'timed_report':
        return TIMED_REPORT_CONFIG.get('enabled', False)
    if module_name == 'push_extension':
        return PUSH_EXTENSION_CONFIG.get('enabled', False)
    return False
