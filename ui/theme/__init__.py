# -*- coding: utf-8 -*-
"""
量化交易系统全局UI主题包
专业量化交易终端深色卡片风格
所有页面必须引用此包的组件
"""

# 主题管理器
from ui.theme.theme_manager import ThemeManager, apply_global_theme
from ui.theme.skin_manager import SkinManager, SKINS, DEFAULT_SKIN

# 颜色配置
from ui.theme.theme_colors import (
    BG_DARKEST, BG_WINDOW, BG_CARD, BG_CARD_HOVER, BG_CARD_ACTIVE,
    BG_INPUT, BG_TABLE, BG_TABLE_ALT, BG_HEADER, BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE, BG_STATUS_BAR, BG_POPUP, BG_TOOLTIP,
    BORDER_DEFAULT, BORDER_HOVER, BORDER_ACTIVE, BORDER_FOCUS, BORDER_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_DISABLED, TEXT_LINK,
    UP_COLOR, DOWN_COLOR, FLAT_COLOR,
    LIMIT_UP_COLOR, LIMIT_DOWN_COLOR,
    AI_SCORE_HIGH, AI_SCORE_MID_HIGH, AI_SCORE_MID, AI_SCORE_LOW,
    ACCENT_RED, ACCENT_BLUE, ACCENT_GOLD, ACCENT_GREEN, ACCENT_ORANGE, ACCENT_CYAN, ACCENT_PURPLE,
    STATUS_SUCCESS, STATUS_WARNING, STATUS_ERROR, STATUS_INFO,
    STATUS_RISK_LOW, STATUS_RISK_MID, STATUS_RISK_HIGH,
    SIDEBAR_WIDTH, SIDEBAR_BG, SIDEBAR_ITEM_BG, SIDEBAR_ITEM_HOVER,
    SIDEBAR_ITEM_ACTIVE, SIDEBAR_ITEM_TEXT, SIDEBAR_ITEM_TEXT_ACTIVE,
    SIDEBAR_ITEM_TEXT_HOVER, SIDEBAR_INDICATOR,
    get_ai_score_color, get_change_color, get_risk_color, format_change
)

# 卡片组件
from ui.theme.card_widgets import (
    CardWidget, MetricCard, AIScoreCard, StockInfoCard, IndexCard,
    CardRow, SectionTitle, Divider
)

# 仪表盘组件
from ui.theme.dashboard_widgets import (
    GaugeWidget, RiskLevelCard, PositionRingCard, PositionRing, MarketSentimentCard
)

# 表格组件
from ui.theme.table_theme import StyledTableWidget

# 兼容旧组件
from ui.theme.cards import PriceZoneCard, SignalCard, StockCard
from ui.theme.badge_widget import BadgeWidget, BadgeRow, SignalBadgeGroup

__all__ = [
    # 管理器
    'ThemeManager', 'apply_global_theme',
    # 颜色
    'BG_DARKEST', 'BG_WINDOW', 'BG_CARD', 'BG_CARD_HOVER', 'BG_CARD_ACTIVE',
    'BG_INPUT', 'BG_TABLE', 'BG_TABLE_ALT', 'BG_HEADER', 'BG_SIDEBAR',
    'BG_SIDEBAR_ACTIVE', 'BG_STATUS_BAR', 'BG_POPUP', 'BG_TOOLTIP',
    'BORDER_DEFAULT', 'BORDER_HOVER', 'BORDER_ACTIVE', 'BORDER_FOCUS', 'BORDER_LIGHT',
    'TEXT_PRIMARY', 'TEXT_SECONDARY', 'TEXT_MUTED', 'TEXT_DISABLED', 'TEXT_LINK',
    'UP_COLOR', 'DOWN_COLOR', 'FLAT_COLOR',
    'LIMIT_UP_COLOR', 'LIMIT_DOWN_COLOR',
    'AI_SCORE_HIGH', 'AI_SCORE_MID_HIGH', 'AI_SCORE_MID', 'AI_SCORE_LOW',
    'ACCENT_RED', 'ACCENT_BLUE', 'ACCENT_GOLD', 'ACCENT_GREEN', 'ACCENT_ORANGE', 'ACCENT_CYAN', 'ACCENT_PURPLE',
    'STATUS_SUCCESS', 'STATUS_WARNING', 'STATUS_ERROR', 'STATUS_INFO',
    'STATUS_RISK_LOW', 'STATUS_RISK_MID', 'STATUS_RISK_HIGH',
    'SIDEBAR_WIDTH', 'SIDEBAR_BG', 'SIDEBAR_ITEM_BG', 'SIDEBAR_ITEM_HOVER',
    'SIDEBAR_ITEM_ACTIVE', 'SIDEBAR_ITEM_TEXT', 'SIDEBAR_ITEM_TEXT_ACTIVE',
    'SIDEBAR_ITEM_TEXT_HOVER', 'SIDEBAR_INDICATOR',
    'get_ai_score_color', 'get_change_color', 'get_risk_color', 'format_change',
    # 卡片
    'CardWidget', 'MetricCard', 'AIScoreCard', 'StockInfoCard', 'IndexCard',
    'CardRow', 'SectionTitle', 'Divider',
    # 仪表盘
    'GaugeWidget', 'RiskLevelCard', 'PositionRingCard', 'PositionRing', 'MarketSentimentCard',
    # 表格
    'StyledTableWidget',
    # 兼容
    'PriceZoneCard', 'SignalCard', 'StockCard',
    'BadgeWidget', 'BadgeRow', 'SignalBadgeGroup',
]
