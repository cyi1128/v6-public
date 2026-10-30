# -*- coding: utf-8 -*-
"""
量化终端统一颜色体系 V2.0
深色科技感主题，红涨绿跌（A股习惯）
卡片式布局 + 霓虹发光效果
"""

# ===== 背景色 =====
BG_DARKEST = '#0a0e17'       # 最深背景（窗口）
BG_DARK = '#0f172a'          # 深色背景（面板）
BG_CARD = '#131c2e'          # 卡片背景
BG_CARD_HOVER = '#1a2740'    # 卡片悬停
BG_CARD_GLOW = '#1e2d4a'     # 卡片发光态
BG_INPUT = '#0c1520'         # 输入框背景
BG_TABLE = '#101a2b'         # 表格背景
BG_TABLE_ALT = '#152033'     # 表格交替行
BG_HEADER = '#1a2740'        # 表头背景
BG_TAB = '#111c30'           # Tab背景
BG_TAB_ACTIVE = '#1a2b45'    # Tab激活
BG_STATUS_BAR = '#080e18'    # 状态栏背景

# ===== 渐变背景 =====
GRADIENT_HEADER = 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0a0e17,stop:0.5 #111827,stop:1 #0a0e17)'
GRADIENT_CARD = 'qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #162035,stop:1 #0f172a)'
GRADIENT_BUTTON_PRIMARY = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb)'
GRADIENT_BUTTON_DANGER = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ef4444,stop:1 #dc2626)'
GRADIENT_BUTTON_SUCCESS = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #10b981,stop:1 #059669)'

# ===== 文字色 =====
TEXT_PRIMARY = '#e8edf5'     # 主文字
TEXT_SECONDARY = '#8b9bb4'   # 次要文字
TEXT_MUTED = '#5a6a80'       # 弱化文字
TEXT_WHITE = '#ffffff'       # 白色
TEXT_GOLD = '#ffd700'        # 金色（标题）
TEXT_CYAN = '#00ffaa'        # 科技青（高亮数据）

# ===== 涨跌色（A股：红涨绿跌）=====
COLOR_UP = '#ef4444'         # 上涨红
COLOR_UP_LIGHT = '#f87171'   # 上涨浅红
COLOR_UP_BG = 'rgba(239,68,68,0.12)'  # 上涨背景
COLOR_UP_GLOW = 'rgba(239,68,68,0.4)' # 上涨发光
COLOR_DOWN = '#22c55e'       # 下跌绿
COLOR_DOWN_LIGHT = '#4ade80' # 下跌浅绿
COLOR_DOWN_BG = 'rgba(34,197,94,0.12)' # 下跌背景
COLOR_DOWN_GLOW = 'rgba(34,197,94,0.4)' # 下跌发光
COLOR_FLAT = '#94a3b8'       # 平盘灰

# ===== AI评分色（统一红色）=====
AI_SCORE_HIGH = '#ef4444'    # 高分红（90+）
AI_SCORE_HIGH_GLOW = 'rgba(239,68,68,0.5)'  # 高分发光
AI_SCORE_MID = '#f59e0b'     # 中分橙（70-89）
AI_SCORE_LOW = '#6b7280'     # 低分灰（<70）

# ===== 主题强调色 =====
ACCENT_PRIMARY = '#3b82f6'   # 主强调蓝
ACCENT_PRIMARY_HOVER = '#2563eb'
ACCENT_PRIMARY_GLOW = 'rgba(59,130,246,0.4)'  # 主色发光
ACCENT_CYAN = '#06b6d4'      # 青色
ACCENT_CYAN_GLOW = 'rgba(6,182,212,0.4)'      # 青色发光
ACCENT_TECH = '#00ffaa'      # 科技薄荷绿
ACCENT_TECH_GLOW = 'rgba(0,255,170,0.3)'      # 科技绿发光
ACCENT_PURPLE = '#8b5cf6'    # 紫色
ACCENT_PURPLE_GLOW = 'rgba(139,92,246,0.4)'   # 紫色发光
ACCENT_GREEN = '#10b981'     # 绿色
ACCENT_RED = '#ef4444'       # 红色
ACCENT_ORANGE = '#f59e0b'    # 橙色
ACCENT_YELLOW = '#eab308'    # 黄色
ACCENT_PINK = '#ec4899'      # 品红

# ===== 边框色 =====
BORDER_COLOR = '#253348'     # 边框
BORDER_LIGHT = '#33445d'     # 浅边框
BORDER_ACCENT = '#3b82f6'    # 强调边框
BORDER_GLOW = '#4a7fff'      # 发光边框

# ===== 信号标签色 =====
SIGNAL_BUY = '#ef4444'       # 买入信号
SIGNAL_SELL = '#22c55e'      # 卖出信号
SIGNAL_WATCH = '#f59e0b'     # 观察信号
SIGNAL_RISK = '#8b5cf6'      # 风险信号
SIGNAL_BREAK = '#06b6d4'     # 突破信号
SIGNAL_VOLUME = '#8b5cf6'    # 倍量信号

# ===== 状态色 =====
STATUS_SUCCESS = '#22c55e'
STATUS_WARNING = '#f59e0b'
STATUS_ERROR = '#ef4444'
STATUS_INFO = '#3b82f6'
STATUS_ONLINE = '#00ffaa'    # 在线状态绿

# ===== 发光阴影 =====
GLOW_BLUE = '0 0 10px rgba(59,130,246,0.3)'
GLOW_CYAN = '0 0 10px rgba(6,182,212,0.3)'
GLOW_RED = '0 0 10px rgba(239,68,68,0.3)'
GLOW_GREEN = '0 0 10px rgba(34,197,94,0.3)'
GLOW_PURPLE = '0 0 10px rgba(139,92,246,0.3)'
GLOW_TECH = '0 0 15px rgba(0,255,170,0.2)'


def get_ai_score_color(score: float) -> str:
    """根据AI评分获取颜色"""
    if score >= 90:
        return AI_SCORE_HIGH
    elif score >= 70:
        return AI_SCORE_MID
    else:
        return AI_SCORE_LOW


def get_change_color(change: float) -> str:
    """根据涨跌幅获取颜色"""
    if change > 0:
        return COLOR_UP
    elif change < 0:
        return COLOR_DOWN
    else:
        return COLOR_FLAT
