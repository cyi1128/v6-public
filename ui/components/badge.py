# -*- coding: utf-8 -*-
"""Unified badge component for the V6.1 UI design system."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QFrame

from ui.theme.design_tokens import (
    ACCENT_BLUE,
    ACCENT_GOLD,
    ACCENT_GREEN,
    ACCENT_ORANGE,
    ACCENT_RED,
    BG_CARD,
    BG_CARD_HOVER,
    BORDER,
    BORDER_SOFT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class Badge(QLabel):
    """通用状态标签."""

    def __init__(self, text="", variant="neutral", parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(self._style_for_variant(variant))
        self.setFixedHeight(22)

    def _style_for_variant(self, variant):
        palette = {
            "buy": (ACCENT_GREEN, "#173f2a", "#d9ffe4"),
            "sell": (ACCENT_RED, "#3a1f1d", "#ffe3e0"),
            "watch": (ACCENT_GOLD, "#433718", "#fff0b3"),
            "risk": (ACCENT_RED, "#3a1f1d", "#ffe3e0"),
            "ai": (ACCENT_RED, "#3a1f1d", "#ffe3e0"),
            "signal": (ACCENT_ORANGE, "#423317", "#ffe8cc"),
            "info": (ACCENT_BLUE, "#1e2d42", "#dfeeff"),
            "neutral": (TEXT_SECONDARY, BORDER_SOFT, BG_CARD_HOVER),
        }
        color, border, bg = palette.get(variant, palette["neutral"])
        return (
            f"background-color: {bg}; border: 1px solid {border}; "
            f"color: {color}; border-radius: 4px; padding: 2px 8px; "
            f"font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )


class BadgeRow(QFrame):
    """图标标签组."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

    def add_badge(self, text, variant="neutral"):
        badge = Badge(text, variant)
        self.layout.addWidget(badge)
        return badge


__all__ = ["Badge", "BadgeRow"]
