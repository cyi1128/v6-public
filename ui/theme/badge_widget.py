# -*- coding: utf-8 -*-
"""
标签组件
用于展示交易信号、状态标签、策略标签等
"""

from PyQt6.QtWidgets import QLabel, QFrame, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
from ui.theme.theme_config import (
    UP_COLOR, DOWN_COLOR, ACCENT_GOLD, ACCENT_BLUE, ACCENT_GREEN,
    ACCENT_ORANGE, TEXT_SECONDARY, BG_CARD
)


class BadgeWidget(QLabel):
    """单个标签"""

    def __init__(self, text, badge_type='default', parent=None):
        super().__init__(text, parent)
        self.badge_type = badge_type
        self._apply_style()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.setMinimumWidth(40)

    def _apply_style(self):
        styles = {
            'buy': (BG_CARD, '#0D3B25', '#3FB950'),
            'sell': (BG_CARD, '#3D1515', '#F85149'),
            'watch': (BG_CARD, '#3D3010', '#FFD700'),
            'danger': (BG_CARD, '#3D1515', '#F85149'),
            'success': (BG_CARD, '#0D3B25', '#3FB950'),
            'info': (BG_CARD, '#15253D', '#58A6FF'),
            'warning': (BG_CARD, '#3D3010', '#FFD700'),
            'limit_up': (BG_CARD, '#3D3010', '#FFD700'),
            'limit_down': (BG_CARD, '#15253D', '#58A6FF'),
            'default': (BG_CARD, '#263241', TEXT_SECONDARY),
            'strategy': (BG_CARD, '#2D1B3D', '#A855F7'),
            'ai': (BG_CARD, '#3D1515', '#F85149'),
        }
        bg, border, color = styles.get(self.badge_type, styles['default'])
        self.setStyleSheet(f"""
            background-color: {bg};
            border: 1px solid {border};
            color: {color};
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
        """)

    def set_type(self, badge_type):
        """切换标签类型"""
        self.badge_type = badge_type
        self._apply_style()


class BadgeRow(QFrame):
    """标签行 - 流式展示多个标签"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: transparent; border: none;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch()

    def add_badge(self, text, badge_type='default'):
        """添加标签"""
        badge = BadgeWidget(text, badge_type)
        # 插入到stretch之前
        self._layout.insertWidget(self._layout.count() - 1, badge)
        return badge

    def clear_badges(self):
        """清空所有标签"""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_badges(self, badges):
        """批量设置标签
        badges: [(text, type), ...]
        """
        self.clear_badges()
        for text, btype in badges:
            self.add_badge(text, btype)


class SignalBadgeGroup(QFrame):
    """交易信号标签组"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: transparent; border: none;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch()

    def set_signals(self, buy_signals=None, sell_signals=None, watch_signals=None):
        """设置信号标签"""
        self.clear_signals()
        if buy_signals:
            for s in buy_signals[:3]:
                self._add_signal(s, 'buy')
        if sell_signals:
            for s in sell_signals[:3]:
                self._add_signal(s, 'sell')
        if watch_signals:
            for s in watch_signals[:3]:
                self._add_signal(s, 'watch')

    def _add_signal(self, text, stype):
        badge = BadgeWidget(text, stype)
        self._layout.insertWidget(self._layout.count() - 1, badge)

    def clear_signals(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
