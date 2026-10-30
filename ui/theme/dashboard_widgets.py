# -*- coding: utf-8 -*-
"""
仪表盘组件
市场情绪仪表盘、仓位环形图、风险等级等
"""

from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath
from ui.theme.theme_colors import (
    BG_CARD, BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT_RED, ACCENT_GOLD, ACCENT_GREEN, ACCENT_ORANGE,
    STATUS_RISK_LOW, STATUS_RISK_MID, STATUS_RISK_HIGH
)


class GaugeWidget(QWidget):
    """仪表盘组件 - 用于市场情绪、风险等级等"""

    def __init__(self, value=0, max_value=100, label='', parent=None):
        super().__init__(parent)
        self.value = value
        self.max_value = max_value
        self.label = label
        self.setMinimumSize(140, 140)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_value(self, value):
        self.value = value
        self.update()

    def set_label(self, label):
        self.label = label
        self.update()

    def _get_color(self, value):
        if value >= 70:
            return ACCENT_RED
        elif value >= 50:
            return ACCENT_ORANGE
        elif value >= 30:
            return ACCENT_GOLD
        else:
            return ACCENT_GREEN

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        center_x = w / 2
        center_y = h / 2 + 10
        radius = min(w, h) / 2 - 20

        # 背景圆弧
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 8))
        painter.drawArc(QRectF(center_x - radius, center_y - radius,
                               radius * 2, radius * 2), 30 * 16, 300 * 16)

        # 值圆弧
        color = self._get_color(self.value)
        painter.setPen(QPen(QColor(color), 8))
        span = int(300 * (self.value / self.max_value))
        painter.drawArc(QRectF(center_x - radius, center_y - radius,
                               radius * 2, radius * 2), 30 * 16, -span * 16)

        # 中心数值
        painter.setPen(QColor(color))
        painter.setFont(QFont('Consolas', 28, QFont.Weight.Bold))
        painter.drawText(QRectF(0, center_y - 25, w, 40),
                         Qt.AlignmentFlag.AlignCenter, str(int(self.value)))

        # 标签
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.setFont(QFont('Microsoft YaHei', 11))
        painter.drawText(QRectF(0, center_y + 15, w, 20),
                         Qt.AlignmentFlag.AlignCenter, self.label)

        painter.end()


class RiskLevelCard(QFrame):
    """风险等级卡片"""

    def __init__(self, level=2, level_text='低风险', trend=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            RiskLevelCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
            }}
        """)
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # 左侧：等级
        left = QVBoxLayout()
        left.setSpacing(2)

        title = QLabel('风险等级')
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        left.addWidget(title)

        risk_color = STATUS_RISK_LOW if level <= 2 else STATUS_RISK_MID if level <= 4 else STATUS_RISK_HIGH
        self.level_label = QLabel(f'{level}级')
        self.level_label.setStyleSheet(
            f"color: {risk_color}; font-size: 32px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        left.addWidget(self.level_label)

        self.level_text_label = QLabel(level_text)
        self.level_text_label.setStyleSheet(f"color: {risk_color}; font-size: 12px; font-weight: 600;")
        left.addWidget(self.level_text_label)

        layout.addLayout(left)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER_DEFAULT};")
        layout.addWidget(sep)

        # 右侧：趋势
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addStretch()

        if trend != 0:
            trend_color = ACCENT_GREEN if trend < 0 else ACCENT_RED
            trend_text = f'较昨日 {"下降" if trend < 0 else "上升"} {abs(trend)}级'
            self.trend_label = QLabel(trend_text)
            self.trend_label.setStyleSheet(f"color: {trend_color}; font-size: 11px; font-weight: 600;")
            right.addWidget(self.trend_label)

        layout.addLayout(right, 1)

    def update_risk(self, level, level_text, trend=0):
        risk_color = STATUS_RISK_LOW if level <= 2 else STATUS_RISK_MID if level <= 4 else STATUS_RISK_HIGH
        self.level_label.setText(f'{level}级')
        self.level_label.setStyleSheet(
            f"color: {risk_color}; font-size: 32px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        self.level_text_label.setText(level_text)
        self.level_text_label.setStyleSheet(f"color: {risk_color}; font-size: 12px; font-weight: 600;")


class PositionRingCard(QFrame):
    """仓位环形图卡片"""

    def __init__(self, position=35, suggested=40, parent=None):
        super().__init__(parent)
        self.position = position
        self.suggested = suggested
        self.setStyleSheet(f"""
            PositionRingCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
            }}
        """)
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 环形图
        self.ring = PositionRing(position, suggested)
        self.ring.setFixedSize(70, 70)
        layout.addWidget(self.ring)

        # 文字
        right = QVBoxLayout()
        right.setSpacing(2)

        title = QLabel('当前仓位')
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        right.addWidget(title)

        self.pos_label = QLabel(f'{position}%')
        self.pos_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 24px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        right.addWidget(self.pos_label)

        self.suggest_label = QLabel(f'建议仓位: {suggested}%')
        self.suggest_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        right.addWidget(self.suggest_label)

        layout.addLayout(right, 1)

    def update_position(self, position, suggested=None):
        self.position = position
        self.pos_label.setText(f'{position}%')
        self.ring.set_position(position)
        if suggested:
            self.suggested = suggested
            self.suggest_label.setText(f'建议仓位: {suggested}%')
            self.ring.set_suggested(suggested)


class PositionRing(QWidget):
    """仓位环形图"""

    def __init__(self, position=35, suggested=40, parent=None):
        super().__init__(parent)
        self.position = position
        self.suggested = suggested
        self.setFixedSize(70, 70)

    def set_position(self, pos):
        self.position = pos
        self.update()

    def set_suggested(self, sug):
        self.suggested = sug
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 6
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        # 背景环
        painter.setPen(QPen(QColor(BORDER_DEFAULT), 6))
        painter.drawArc(rect, 0, 360 * 16)

        # 建议仓位（浅红）
        sug_span = int(360 * self.suggested / 100)
        painter.setPen(QPen(QColor('#3D1515'), 6))
        painter.drawArc(rect, 90 * 16, -sug_span * 16)

        # 当前仓位（红）
        pos_span = int(360 * self.position / 100)
        painter.setPen(QPen(QColor(ACCENT_RED), 6))
        painter.drawArc(rect, 90 * 16, -pos_span * 16)

        # 中心文字
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont('Consolas', 11, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f'{self.position}%')

        painter.end()


class MarketSentimentCard(QFrame):
    """市场情绪卡片（含仪表盘）"""

    def __init__(self, score=68, label='积极', parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            MarketSentimentCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
            }}
        """)
        self.setFixedHeight(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel('市场情绪')
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;")
        layout.addWidget(title)

        self.gauge = GaugeWidget(score, 100, label)
        self.gauge.setFixedSize(140, 120)
        layout.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)

    def update_sentiment(self, score, label):
        self.gauge.set_value(score)
        self.gauge.set_label(label)
