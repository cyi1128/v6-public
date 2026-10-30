"""
量化盯盘 V6.0 - 全局配置
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'quant_monitor.db')

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# ========== 行情数据源配置 ==========
# 行情源类型: tdx(通达信) / eastmoney(东方财富) / tencent(腾讯) / joinquant(聚宽) / ricequant(米筐)
# 详细连接配置见 market/config/provider_config.py 或 data/market_config.json
MARKET_DATA = {
    'provider': 'tencent',                    # 默认使用腾讯HTTP行情（pytdx已完全失效）
    'refresh_interval': 3,                    # 刷新间隔（秒）
    'auto_reconnect': True,                   # 自动重连
    'max_retry': 3,                           # 最大重试次数
    'failover_provider': 'eastmoney_delay',   # 故障转移备用源（东方财富push2delay）
}

# 通达信服务器列表（也可在 data/market_config.json 中配置）
TDX_SERVERS = [
    ('119.147.212.81', 7709),   # 深圳行情主站1
    ('119.147.212.82', 7709),   # 深圳行情主站2
    ('218.108.98.244', 7709),   # 杭州电信
    ('218.108.47.69', 7709),    # 杭州联通
    ('124.160.88.183', 7709),   # 宁波电信
    ('60.12.136.250', 7709),    # 绍兴电信
    ('115.238.56.198', 7709),   # 台州电信
    ('218.75.126.9', 7709),     # 长沙电信
    ('124.74.236.94', 7709),    # 上海电信
    ('180.153.18.170', 7709),   # 上海联通
]

# ========== 股票池过滤参数 ==========
# 严格按照交易系统的10个筛选条件
FILTER_CONFIG = {
    # 条件7: 排除行业
    'exclude_industries': ['房地产', '农业', '白酒', '保险'],
    # 条件6: 排除ST
    'exclude_st': True,
    # 条件8: 总市值范围(亿)
    'min_market_cap': 30,   # 大于30亿
    'max_market_cap': 230,  # 小于等于230亿
    # 条件9: 价格范围
    'min_price': 5.0,   # 低于5元剔除
    'max_price': 60.0,  # 超过60元剔除
    # 条件1: 当前价格 > 近8个月最高价 × 70%
    'high_price_ratio': 0.70,
    # 条件2: 当前价格 < 近8个月最高价 × 105%
    'max_price_ratio': 1.05,
    # 条件10: 距离近8个月最高价涨幅 < 15%
    'max_gain_from_high': 0.15,
    # 条件4: 一年内涨停次数 >= 3次
    'min_limit_up_count': 3,
    # 8个月约168个交易日
    'high_period_days': 168,
}

# ========== 量化评分权重 ==========
SCORING_CONFIG = {
    'trend_position': 30,    # 趋势位置
    'limit_up_gene': 20,     # 涨停基因
    'volume_ratio': 15,      # 成交量
    'ma_trend': 15,          # 均线趋势
    'macd': 10,              # MACD
    'kdj': 10,               # KDJ
}

# ========== 集合竞价评分 ==========
AUCTION_CONFIG = {
    'gap_up_min': 0.02,    # 高开2%
    'gap_up_max': 0.05,    # 高开5%
    'gap_up_score': 20,
    'volume_ratio_score': 25,
    'turnover_score': 20,
    'sector_strength_score': 20,
    'yesterday_strength_score': 15,
}

# ========== 主力吸筹识别 ==========
ACCUMULATION_CONFIG = {
    'first_volume_ratio': 2.0,   # 首次放量倍数
    'pullback_days_min': 3,      # 回调最少天数
    'pullback_days_max': 10,     # 回调最多天数
    'pullback_volume_ratio': 0.6,  # 缩量比例
    'second_volume_ratio': 1.8,  # 二次放量倍数
}

# ========== 实时监控 ==========
REALTIME_CONFIG = {
    'refresh_seconds': 3,
    'price_above_avg_vol_increase': 1.2,  # 站上均价线且量增倍数
}

# ========== 信号阈值 ==========
SIGNAL_CONFIG = {
    'buy_score_threshold': 90,     # 买入评分阈值
    'sell_ma_break': True,         # 跌破MA5卖出
    'sell_volume_increase': 1.5,   # 放量下跌倍数
    'sell_macd_weak': True,        # MACD转弱
}

# ========== 界面配置 ==========
UI_CONFIG = {
    'window_title': '量化盯盘 V6.0 主升龙头全自动系统',
    'window_width': 1400,
    'window_height': 900,
    'refresh_interval': 3000,  # 毫秒
}
