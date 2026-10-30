# -*- coding: utf-8 -*-
"""
通用卡片组件
参考专业量化交易终端卡片风格
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget
)
from PyQt6.QtCore import Qt
from ui.theme.design_tokens import (
    BG_CARD, BG_CARD_HOVER, BG_PANEL_ALT, BG_WINDOW,
    BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    UP, DOWN, FLAT,
    AI_SCORE_HIGH, AI_SCORE_MID_HIGH, AI_SCORE_MID, AI_SCORE_LOW,
    ACCENT_RED, ACCENT_BLUE, ACCENT_GOLD, ACCENT_GREEN, ACCENT_ORANGE,
    get_ai_score_color, get_change_color,
)
from ui.theme.theme_colors import format_change


class CardWidget(QFrame):
    """基础卡片 - 圆角边框+悬停效果"""

    def __init__(self, title='', accent_color=None, parent=None):
        super().__init__(parent)
        self.accent_color = accent_color or BORDER_STRONG
        self._setup_style()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)

        if title:
            self._title_label = QLabel(title)
            self._title_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;"
            )
            self._layout.addWidget(self._title_label)

    def _setup_style(self):
        self.setStyleSheet(f"""
            CardWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD},
                    stop:1 {BG_PANEL_ALT});
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            CardWidget:hover {{
                border: 1px solid {self.accent_color};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD_HOVER},
                    stop:1 {BG_PANEL_ALT});
            }}
        """)

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_layout(self, layout):
        self._layout.addLayout(layout)

    def add_stretch(self):
        self._layout.addStretch()

    def set_content_margins(self, left, top, right, bottom):
        self._layout.setContentsMargins(left, top, right, bottom)


class MetricCard(QFrame):
    """指标卡片 - 标签+大数值+单位+变化"""

    def __init__(self, label, value, unit='', change=None,
                 accent='red', parent=None):
        super().__init__(parent)
        self.accent = accent
        accent_colors = {
            'red': ACCENT_RED, 'blue': ACCENT_BLUE, 'gold': ACCENT_GOLD,
            'green': ACCENT_GREEN, 'orange': ACCENT_ORANGE, 'gray': TEXT_SECONDARY,
        }
        self.accent_color = accent_colors.get(accent, ACCENT_RED)

        self.setStyleSheet(f"""
            MetricCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD},
                    stop:1 {BG_PANEL_ALT});
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            MetricCard:hover {{
                border: 1px solid {self.accent_color};
            }}
        """)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # 标签
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self.label)

        # 数值行
        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            f"color: {self.accent_color}; font-size: 26px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        value_row.addWidget(self.value_label)

        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
            value_row.addWidget(self.unit_label)

        value_row.addStretch()
        layout.addLayout(value_row)

        # 变化值
        if change is not None:
            if change > 0:
                c_color = UP
                c_text = f'↑{change:.2f}%'
            elif change < 0:
                c_color = DOWN
                c_text = f'↓{abs(change):.2f}%'
            else:
                c_color = FLAT
                c_text = '0.00%'
            self.change_label = QLabel(c_text)
            self.change_label.setStyleSheet(f"color: {c_color}; font-size: 11px; font-weight: 600;")
            layout.addWidget(self.change_label)

    def update_value(self, value, change=None):
        self.value_label.setText(str(value))
        if change is not None and hasattr(self, 'change_label'):
            if change > 0:
                c_color = UP
                c_text = f'↑{change:.2f}%'
            elif change < 0:
                c_color = DOWN
                c_text = f'↓{abs(change):.2f}%'
            else:
                c_color = FLAT
                c_text = '0.00%'
            self.change_label.setText(c_text)
            self.change_label.setStyleSheet(f"color: {c_color}; font-size: 11px; font-weight: 600;")


class AIScoreCard(QFrame):
    """AI评分卡片 - 大数字+评级+趋势"""

    def __init__(self, score=0, suggestion='', trend=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            AIScoreCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD},
                    stop:1 {BG_PANEL_ALT});
                border: 1px solid {ACCENT_RED};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # 左侧：评分
        left = QVBoxLayout()
        left.setSpacing(2)

        score_color = get_ai_score_color(score)
        self.score_label = QLabel(str(score))
        self.score_label.setStyleSheet(
            f"color: {score_color}; font-size: 40px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        left.addWidget(self.score_label)

        self.suggestion_label = QLabel(suggestion)
        self.suggestion_label.setStyleSheet(f"color: {score_color}; font-size: 12px; font-weight: 600;")
        left.addWidget(self.suggestion_label)

        layout.addLayout(left)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER}; background-color: {BORDER};")
        layout.addWidget(sep)

        # 右侧：趋势
        right = QVBoxLayout()
        right.setSpacing(4)

        title = QLabel('AI综合评分')
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        right.addWidget(title)

        if trend != 0:
            trend_color = UP if trend > 0 else DOWN
            trend_text = f'较昨日 {"+" if trend > 0 else ""}{trend:.1f}'
            self.trend_label = QLabel(trend_text)
            self.trend_label.setStyleSheet(f"color: {trend_color}; font-size: 13px; font-weight: 600;")
            right.addWidget(self.trend_label)

        right.addStretch()
        layout.addLayout(right, 1)

    def update_score(self, score, suggestion=None, trend=None):
        color = get_ai_score_color(score)
        self.score_label.setText(str(score))
        self.score_label.setStyleSheet(
            f"color: {color}; font-size: 40px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        if suggestion:
            self.suggestion_label.setText(suggestion)
            self.suggestion_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
        if trend is not None and hasattr(self, 'trend_label'):
            trend_color = UP if trend > 0 else DOWN
            self.trend_label.setText(f'较昨日 {"+" if trend > 0 else ""}{trend:.1f}')
            self.trend_label.setStyleSheet(f"color: {trend_color}; font-size: 13px; font-weight: 600;")


class StockInfoCard(QFrame):
    """股票信息卡片 - 代码+名称+现价+涨跌幅+AI评分"""

    def __init__(self, code='', name='', price=0, change=0,
                 ai_score=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            StockInfoCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD},
                    stop:1 {BG_PANEL_ALT});
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(16)

        # 代码名称
        left = QVBoxLayout()
        left.setSpacing(2)
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 700;")
        left.addWidget(self.name_label)
        self.code_label = QLabel(code)
        self.code_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        left.addWidget(self.code_label)
        layout.addLayout(left)

        layout.addStretch()

        # 价格
        price_box = QVBoxLayout()
        price_box.setSpacing(2)
        price_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.price_label = QLabel(f'{price:.2f}')
        self.price_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 20px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        price_box.addWidget(self.price_label)
        change_color = get_change_color(change)
        self.change_label = QLabel(format_change(change))
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 13px; font-weight: 600;")
        price_box.addWidget(self.change_label)
        layout.addLayout(price_box)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)

        # AI评分
        ai_box = QVBoxLayout()
        ai_box.setSpacing(2)
        ai_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        ai_title = QLabel('AI评分')
        ai_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        ai_box.addWidget(ai_title)
        score_color = get_ai_score_color(ai_score)
        self.ai_score_label = QLabel(str(ai_score))
        self.ai_score_label.setStyleSheet(
            f"color: {score_color}; font-size: 22px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        ai_box.addWidget(self.ai_score_label)
        layout.addLayout(ai_box)

    def update_stock(self, code, name, price, change, ai_score=0):
        self.code_label.setText(code)
        self.name_label.setText(name)
        self.price_label.setText(f'{price:.2f}')
        change_color = get_change_color(change)
        self.change_label.setText(format_change(change))
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 13px; font-weight: 600;")
        score_color = get_ai_score_color(ai_score)
        self.ai_score_label.setText(str(ai_score))
        self.ai_score_label.setStyleSheet(
            f"color: {score_color}; font-size: 22px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )


class IndexCard(QFrame):
    """指数卡片 - 指数名称+点位+涨跌"""

    def __init__(self, name='', value=0, change=0, change_pct=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            IndexCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CARD},
                    stop:1 {BG_PANEL_ALT});
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(68)
        self.setMinimumWidth(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self.name_label)

        self.value_label = QLabel(f'{value:.2f}')
        self.value_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        layout.addWidget(self.value_label)

        change_color = get_change_color(change)
        self.change_label = QLabel(f'{format_change(change)}  {format_change(change_pct)}')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.change_label)

    def update_index(self, value, change, change_pct):
        self.value_label.setText(f'{value:.2f}')
        change_color = get_change_color(change)
        self.change_label.setText(f'{format_change(change)}  {format_change(change_pct)}')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 11px; font-weight: 600;")


class CardRow(QHBoxLayout):
    """卡片行布局"""

    def __init__(self, spacing=10, parent=None):
        super().__init__(parent)
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def add_card(self, card):
        self.addWidget(card)


class SectionTitle(QLabel):
    """区块标题"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700; padding: 4px 0px;"
        )


class Divider(QFrame):
    """分割线"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: {BORDER}; background-color: {BORDER};")
        self.setFixedHeight(1)
