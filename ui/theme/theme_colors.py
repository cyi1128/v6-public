# -*- coding: utf-8 -*-
"""
量化交易系统全局颜色配置
参考专业量化交易终端UI风格
"""

# ===== 背景色 =====
BG_DARKEST = '#080C12'       # 主背景（最底层）
BG_WINDOW = '#0D1117'        # 窗口背景
BG_CARD = '#161B22'          # 卡片背景
BG_CARD_HOVER = '#1C2128'    # 卡片悬停
BG_CARD_ACTIVE = '#21262D'   # 卡片激活
BG_INPUT = '#0D1117'         # 输入框背景
BG_TABLE = '#0D1117'         # 表格背景
BG_TABLE_ALT = '#161B22'     # 表格交替行
BG_HEADER = '#161B22'        # 表头背景
BG_SIDEBAR = '#0D1117'       # 侧边栏背景
BG_SIDEBAR_ACTIVE = '#21262D' # 侧边栏选中
BG_STATUS_BAR = '#080C12'    # 状态栏背景
BG_POPUP = '#161B22'         # 弹窗背景
BG_TOOLTIP = '#161B22'       # 提示背景

# ===== 边框色 =====
BORDER_DEFAULT = '#30363D'   # 默认边框
BORDER_HOVER = '#484F58'     # 悬停边框
BORDER_ACTIVE = '#F85149'    # 激活边框（红色）
BORDER_FOCUS = '#F85149'     # 聚焦边框
BORDER_LIGHT = '#21262D'     # 浅边框

# ===== 文字色 =====
TEXT_PRIMARY = '#FFFFFF'     # 主要文字
TEXT_SECONDARY = '#8B949E'   # 辅助文字
TEXT_MUTED = '#6E7681'       # 弱化文字
TEXT_DISABLED = '#484F58'    # 禁用文字
TEXT_LINK = '#58A6FF'        # 链接文字

# ===== 涨跌色（A股规则） =====
UP_COLOR = '#F85149'         # 上涨 - 红色
DOWN_COLOR = '#3FB950'       # 下跌 - 绿色
LIMIT_UP_COLOR = '#FFD700'   # 涨停 - 金黄色
LIMIT_DOWN_COLOR = '#58A6FF' # 跌停 - 蓝色
FLAT_COLOR = '#8B949E'       # 平盘 - 灰色

# ===== AI评分色 =====
AI_SCORE_HIGH = '#F85149'    # 90-100 红色
AI_SCORE_MID_HIGH = '#FF8C00' # 80-90 橙色
AI_SCORE_MID = '#FFD700'     # 70-80 黄色
AI_SCORE_LOW = '#8B949E'     # <70 灰色

# ===== 强调色 =====
ACCENT_RED = '#F85149'       # 主强调色 - 红色（AI主题）
ACCENT_BLUE = '#58A6FF'      # 蓝色
ACCENT_GOLD = '#FFD700'      # 金色
ACCENT_GREEN = '#3FB950'     # 绿色
ACCENT_ORANGE = '#FF8C00'    # 橙色
ACCENT_CYAN = '#39C5CF'      # 青色
ACCENT_PURPLE = '#A371F7'    # 紫色

# ===== 状态色 =====
STATUS_SUCCESS = '#3FB950'   # 成功
STATUS_WARNING = '#FFD700'   # 警告
STATUS_ERROR = '#F85149'     # 错误
STATUS_INFO = '#58A6FF'      # 信息
STATUS_RISK_LOW = '#3FB950'  # 低风险
STATUS_RISK_MID = '#FFD700'  # 中风险
STATUS_RISK_HIGH = '#F85149' # 高风险

# ===== 渐变色 =====
GRADIENT_SIDEBAR_ACTIVE = 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #21262D,stop:1 #161B22)'
GRADIENT_CARD = 'qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1C2128,stop:1 #161B22)'
GRADIENT_BUTTON_PRIMARY = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #F85149,stop:1 #DA3633)'
GRADIENT_BUTTON_SUCCESS = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3FB950,stop:1 #2D9A3E)'
GRADIENT_HEADER = 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0D1117,stop:0.5 #161B22,stop:1 #0D1117)'

# ===== 侧边栏菜单 =====
SIDEBAR_WIDTH = 160
SIDEBAR_BG = '#0D1117'
SIDEBAR_ITEM_BG = 'transparent'
SIDEBAR_ITEM_HOVER = '#161B22'
SIDEBAR_ITEM_ACTIVE = '#21262D'
SIDEBAR_ITEM_TEXT = '#8B949E'
SIDEBAR_ITEM_TEXT_ACTIVE = '#FFFFFF'
SIDEBAR_ITEM_TEXT_HOVER = '#FFFFFF'
SIDEBAR_INDICATOR = '#F85149'


def get_ai_score_color(score):
    """根据AI评分返回对应颜色"""
    try:
        s = float(score)
        if s >= 90:
            return AI_SCORE_HIGH
        elif s >= 80:
            return AI_SCORE_MID_HIGH
        elif s >= 70:
            return AI_SCORE_MID
        else:
            return AI_SCORE_LOW
    except (ValueError, TypeError):
        return AI_SCORE_LOW


def get_change_color(change):
    """根据涨跌幅返回颜色"""
    try:
        c = float(change)
        if c > 0:
            return UP_COLOR
        elif c < 0:
            return DOWN_COLOR
        else:
            return FLAT_COLOR
    except (ValueError, TypeError):
        return FLAT_COLOR


def get_risk_color(level):
    """根据风险等级返回颜色"""
    level_str = str(level).lower()
    if '低' in level_str or 'low' in level_str or level_str in ('1', '2'):
        return STATUS_RISK_LOW
    elif '中' in level_str or 'mid' in level_str or level_str in ('3',):
        return STATUS_RISK_MID
    else:
        return STATUS_RISK_HIGH


def format_change(change, with_sign=True):
    """格式化涨跌幅"""
    try:
        c = float(change)
        if with_sign and c > 0:
            return f'+{c:.2f}%'
        return f'{c:.2f}%'
    except (ValueError, TypeError):
        return str(change)
