# -*- coding: utf-8 -*-
"""
基础卡片组件
所有页面的信息展示必须使用此卡片，禁止裸露内容
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from ui.theme.theme_config import (
    BG_CARD, BG_CARD_HOVER, BORDER_DEFAULT, BORDER_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_RED
)


class CardWidget(QFrame):
    """基础卡片 - 带圆角边框和悬停效果"""

    def __init__(self, title='', accent_color=None, parent=None):
        super().__init__(parent)
        self.accent_color = accent_color or BORDER_DEFAULT
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
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
            }}
            CardWidget:hover {{
                border: 1px solid {self.accent_color};
                background-color: {BG_CARD_HOVER};
            }}
        """)

    def add_widget(self, widget):
        """添加内容组件"""
        self._layout.addWidget(widget)

    def add_layout(self, layout):
        """添加布局"""
        self._layout.addLayout(layout)

    def add_stretch(self):
        """添加弹性空间"""
        self._layout.addStretch()

    def set_content_margins(self, left, top, right, bottom):
        """设置内容边距"""
        self._layout.setContentsMargins(left, top, right, bottom)


class CardRow(QHBoxLayout):
    """卡片行布局 - 均匀分布多个卡片"""

    def __init__(self, spacing=10, parent=None):
        super().__init__(parent)
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def add_card(self, card):
        """添加卡片"""
        self.addWidget(card)


class SectionTitle(QLabel):
    """区块标题"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            f"padding: 4px 0px;"
        )


class Divider(QFrame):
    """分割线"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: {BORDER_DEFAULT}; background-color: {BORDER_DEFAULT};")
        self.setFixedHeight(1)
