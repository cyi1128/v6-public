# -*- coding: utf-8 -*-
"""Public UI card components for the V6.1 design system."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

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
    FLAT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    UP,
    DOWN,
    get_ai_score_color,
    get_change_color,
)


class BaseCard(QFrame):
    """基础卡片：统一圆角、边框、内边距、悬停."""

    def __init__(self, title="", subtitle="", accent=ACCENT_BLUE, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setObjectName("BaseCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"""
            QFrame#BaseCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QFrame#BaseCard:hover {{
                background-color: {BG_CARD_HOVER};
                border: 1px solid {accent};
            }}
            """
        )

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(12, 10, 12, 10)
        self.root.setSpacing(8)

        if title or subtitle:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)

            if title:
                self.title_label = QLabel(title)
                self.title_label.setStyleSheet(
                    f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;"
                )
                header.addWidget(self.title_label)

            if subtitle:
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 600;"
                )
                header.addWidget(self.subtitle_label)
                header.addStretch()

            self.root.addLayout(header)

    def add_widget(self, widget):
        self.root.addWidget(widget)

    def add_layout(self, layout):
        self.root.addLayout(layout)

    def add_stretch(self):
        self.root.addStretch()


class MetricCard(BaseCard):
    """指标卡片：标签 + 数值 + 变化."""

    def __init__(self, label, value, unit="", change=None, accent=ACCENT_RED, parent=None):
        super().__init__(title=label, accent=accent, parent=parent)
        self.setFixedHeight(88)

        self.value_row = QHBoxLayout()
        self.value_row.setSpacing(4)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            f"color: {accent}; font-size: 24px; font-weight: 700;"
        )
        self.value_row.addWidget(self.value_label)

        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self.value_row.addWidget(self.unit_label)

        self.value_row.addStretch()
        self.root.addLayout(self.value_row)

        if change is not None:
            self.change_label = QLabel()
            self._set_change(change)
            self.root.addWidget(self.change_label)

    def _set_change(self, change):
        if change > 0:
            color = UP
            text = f"▲ +{change:.2f}%"
        elif change < 0:
            color = DOWN
            text = f"▼ {abs(change):.2f}%"
        else:
            color = FLAT
            text = "--"
        self.change_label.setText(text)
        self.change_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")


class ScoreCard(BaseCard):
    """评分卡片：大数字 + 状态 + 细项."""

    def __init__(self, title="AI综合评分", score=0, suggestion="强势买入", parent=None):
        super().__init__(title=title, accent=ACCENT_RED, parent=parent)
        self.score = score
        self.setFixedHeight(150)

        self.score_container = QHBoxLayout()
        self.score_container.setSpacing(12)

        self.score_label = QLabel(str(score))
        self.score_label.setStyleSheet(
            f"color: {get_ai_score_color(score)}; font-size: 32px; font-weight: 800;"
        )
        self.score_container.addWidget(self.score_label)

        self.score_suffix = QLabel("/100")
        self.score_suffix.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.score_container.addWidget(self.score_suffix)
        self.score_container.addStretch()
        self.root.addLayout(self.score_container)

        self.suggestion_label = QLabel(suggestion)
        self.suggestion_label.setStyleSheet(
            f"color: {get_ai_score_color(score)}; font-size: 12px; font-weight: 700;"
        )
        self.root.addWidget(self.suggestion_label)

    def update_score(self, score, suggestion=""):
        self.score = score
        self.score_label.setText(str(score))
        color = get_ai_score_color(score)
        self.score_label.setStyleSheet(
            f"color: {color}; font-size: 32px; font-weight: 800;"
        )
        self.suggestion_label.setText(suggestion or "强势买入")
        self.suggestion_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
        )


class StatusCard(BaseCard):
    """状态卡片：用于显示市场状态、数据状态等."""

    def __init__(self, title="状态", value="正常", accent=ACCENT_GREEN, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(
            f"color: {accent}; font-size: 18px; font-weight: 700;"
        )
        self.root.addWidget(self.value_label)


class ActionCard(BaseCard):
    """动作卡片：适合按钮区域等."""

    def __init__(self, title="操作", accent=ACCENT_BLUE, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.root.addStretch()


class IndicatorCard(BaseCard):
    """技术指标卡片：例如 KDJ、MACD、MA 等展示."""

    def __init__(self, title="KDJ", rows=None, accent=ACCENT_ORANGE, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.rows = rows or []
        self._build_rows()

    def _build_rows(self):
        for key, value, color in self.rows:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            label = QLabel(key)
            label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
            row.addWidget(label)
            row.addStretch()

            val = QLabel(str(value))
            val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 700;")
            row.addWidget(val)
            self.root.addLayout(row)


class SignalCard(BaseCard):
    """信号卡片：展示买入/卖出/观察等标签."""

    def __init__(self, title="信号", signals=None, accent=ACCENT_GOLD, parent=None):
        super().__init__(title=title, accent=accent, parent=parent)
        self.signals = signals or []
        self._build_signals()

    def _build_signals(self):
        for signal in self.signals:
            label = QLabel(signal)
            label.setStyleSheet(f"color: {TEXT_PRIMARY}; background-color: {BG_CARD_HOVER}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.root.addWidget(label)


class AIScoreCard(ScoreCard):
    """AI评分卡片：对外统一展示组件."""

    def __init__(self, score=0, suggestion="强势买入", parent=None):
        super().__init__(title="AI综合评分", score=score, suggestion=suggestion, parent=parent)


__all__ = [
    "BaseCard",
    "MetricCard",
    "ScoreCard",
    "StatusCard",
    "ActionCard",
    "IndicatorCard",
    "SignalCard",
    "AIScoreCard",
]
