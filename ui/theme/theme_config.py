# -*- coding: utf-8 -*-
"""
量化交易系统全局UI颜色配置 V1.0
专业量化交易终端风格
所有页面必须引用此配置，禁止硬编码颜色
"""

# ===== 背景色 =====
BG_MAIN = '#0B0F14'           # 主背景（窗口）
BG_CARD = '#151B24'           # 卡片背景
BG_CARD_HOVER = '#1C2430'     # 卡片悬停
BG_INPUT = '#0E141C'          # 输入框背景
BG_TABLE = '#0F151D'          # 表格背景
BG_TABLE_ALT = '#131A24'      # 表格交替行
BG_HEADER = '#1A2230'         # 表头背景
BG_TAB = '#0B0F14'            # Tab背景
BG_TAB_ACTIVE = '#151B24'     # Tab激活
BG_STATUS_BAR = '#080C12'     # 状态栏背景
BG_POPUP = '#151B24'          # 弹窗背景

# ===== 边框色 =====
BORDER_DEFAULT = '#263241'    # 默认边框
BORDER_HOVER = '#3A4A5E'      # 悬停边框
BORDER_ACTIVE = '#F85149'     # 激活边框（红色）
BORDER_FOCUS = '#F85149'      # 聚焦边框

# ===== 文字色 =====
TEXT_PRIMARY = '#FFFFFF'      # 主要文字
TEXT_SECONDARY = '#8B949E'    # 辅助文字
TEXT_MUTED = '#5C6470'        # 弱化文字
TEXT_DISABLED = '#3D4450'     # 禁用文字

# ===== 涨跌色（A股规则） =====
UP_COLOR = '#F85149'          # 上涨 - 红色
DOWN_COLOR = '#3FB950'        # 下跌 - 绿色
LIMIT_UP_COLOR = '#FFD700'    # 涨停 - 金黄色
LIMIT_DOWN_COLOR = '#58A6FF'  # 跌停 - 蓝色
FLAT_COLOR = '#8B949E'        # 平盘 - 灰色

# ===== AI评分色 =====
AI_SCORE_HIGH = '#F85149'     # 90分以上 - 红色
AI_SCORE_MID_HIGH = '#FF8C00' # 80-90分 - 橙色
AI_SCORE_MID = '#FFD700'      # 70-80分 - 黄色
AI_SCORE_LOW = '#8B949E'      # 70分以下 - 灰色

# ===== 强调色 =====
ACCENT_RED = '#F85149'        # 主强调色 - 红色（AI主题）
ACCENT_BLUE = '#58A6FF'       # 蓝色
ACCENT_GOLD = '#FFD700'       # 金色
ACCENT_GREEN = '#3FB950'      # 绿色
ACCENT_ORANGE = '#FF8C00'     # 橙色
ACCENT_CYAN = '#39C5CF'       # 青色

# ===== 状态色 =====
STATUS_SUCCESS = '#3FB950'    # 成功
STATUS_WARNING = '#FFD700'    # 警告
STATUS_ERROR = '#F85149'      # 错误
STATUS_INFO = '#58A6FF'       # 信息

# ===== 渐变 =====
GRADIENT_HEADER = 'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0B0F14,stop:0.5 #151B24,stop:1 #0B0F14)'
GRADIENT_BUTTON_PRIMARY = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #F85149,stop:1 #D93630)'
GRADIENT_BUTTON_DANGER = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #58A6FF,stop:1 #3884E0)'
GRADIENT_BUTTON_SUCCESS = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3FB950,stop:1 #2D9A3E)'
GRADIENT_CARD = 'qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1A2230,stop:1 #151B24)'


def get_ai_score_color(score):
    """根据AI评分返回对应颜色"""
    if score >= 90:
        return AI_SCORE_HIGH
    elif score >= 80:
        return AI_SCORE_MID_HIGH
    elif score >= 70:
        return AI_SCORE_MID
    else:
        return AI_SCORE_LOW


def get_change_color(change):
    """根据涨跌幅返回颜色"""
    if change > 0:
        return UP_COLOR
    elif change < 0:
        return DOWN_COLOR
    else:
        return FLAT_COLOR


def get_change_text(change, with_sign=True):
    """格式化涨跌幅文字"""
    if with_sign and change > 0:
        return f'+{change:.2f}%'
    return f'{change:.2f}%'
