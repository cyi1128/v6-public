# -*- coding: utf-8 -*-
"""
数据指标卡片组件
用于展示核心指标：AI评分、风险、仓位、信号数等
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from ui.theme.theme_config import (
    BG_CARD, BG_CARD_HOVER, BORDER_DEFAULT,
    TEXT_PRIMARY, TEXT_SECONDARY,
    UP_COLOR, DOWN_COLOR, FLAT_COLOR,
    AI_SCORE_HIGH, AI_SCORE_MID_HIGH, AI_SCORE_MID, AI_SCORE_LOW,
    ACCENT_RED, ACCENT_BLUE, ACCENT_GOLD, ACCENT_GREEN, ACCENT_ORANGE
)


class MetricCard(QFrame):
    """数据指标卡片 - 标签+大数值+单位+变化"""

    def __init__(self, label, value, unit='', change=None,
                 accent='red', parent=None):
        super().__init__(parent)
        self.accent = accent
        accent_colors = {
            'red': ACCENT_RED,
            'blue': ACCENT_BLUE,
            'gold': ACCENT_GOLD,
            'green': ACCENT_GREEN,
            'orange': ACCENT_ORANGE,
            'gray': TEXT_SECONDARY,
        }
        self.accent_color = accent_colors.get(accent, ACCENT_RED)

        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
            }}
            MetricCard:hover {{
                border: 1px solid {self.accent_color};
                background-color: {BG_CARD_HOVER};
            }}
        """)
        self.setFixedHeight(76)
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
            f"color: {self.accent_color}; font-size: 24px; font-weight: 700; "
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
                c_color = UP_COLOR
                c_text = f'↑{change:.2f}%'
            elif change < 0:
                c_color = DOWN_COLOR
                c_text = f'↓{abs(change):.2f}%'
            else:
                c_color = FLAT_COLOR
                c_text = '0.00%'
            self.change_label = QLabel(c_text)
            self.change_label.setStyleSheet(f"color: {c_color}; font-size: 11px; font-weight: 600;")
            layout.addWidget(self.change_label)

    def update_value(self, value, change=None):
        """更新数值"""
        self.value_label.setText(str(value))
        if change is not None and hasattr(self, 'change_label'):
            if change > 0:
                c_color = UP_COLOR
                c_text = f'↑{change:.2f}%'
            elif change < 0:
                c_color = DOWN_COLOR
                c_text = f'↓{abs(change):.2f}%'
            else:
                c_color = FLAT_COLOR
                c_text = '0.00%'
            self.change_label.setText(c_text)
            self.change_label.setStyleSheet(f"color: {c_color}; font-size: 11px; font-weight: 600;")


class AIScoreCard(QFrame):
    """AI评分卡片 - 大数字+等级+建议"""

    def __init__(self, score=0, suggestion='', stars=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            AIScoreCard {{
                background-color: {BG_CARD};
                border: 1px solid {ACCENT_RED};
                border-radius: 6px;
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

        score_color = self._get_score_color(score)
        self.score_label = QLabel(str(score))
        self.score_label.setStyleSheet(
            f"color: {score_color}; font-size: 38px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        left.addWidget(self.score_label)

        self.stars_label = QLabel('★' * stars + '☆' * (5 - stars))
        self.stars_label.setStyleSheet(f"color: {ACCENT_GOLD}; font-size: 14px;")
        left.addWidget(self.stars_label)

        layout.addLayout(left)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER_DEFAULT}; background-color: {BORDER_DEFAULT};")
        layout.addWidget(sep)

        # 右侧：建议
        right = QVBoxLayout()
        right.setSpacing(4)

        title = QLabel('AI综合评分')
        title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        right.addWidget(title)

        self.suggestion_label = QLabel(suggestion)
        self.suggestion_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        self.suggestion_label.setWordWrap(True)
        right.addWidget(self.suggestion_label)

        self.level_label = QLabel(self._get_level_text(score))
        self.level_label.setStyleSheet(f"color: {score_color}; font-size: 11px; font-weight: 600;")
        right.addWidget(self.level_label)

        right.addStretch()
        layout.addLayout(right, 1)

    def _get_score_color(self, score):
        if score >= 90:
            return AI_SCORE_HIGH
        elif score >= 80:
            return AI_SCORE_MID_HIGH
        elif score >= 70:
            return AI_SCORE_MID
        else:
            return AI_SCORE_LOW

    def _get_level_text(self, score):
        if score >= 90:
            return '强烈关注'
        elif score >= 80:
            return '重点关注'
        elif score >= 70:
            return '适度关注'
        else:
            return '观望'

    def update_score(self, score, suggestion=None, stars=None):
        """更新评分"""
        color = self._get_score_color(score)
        self.score_label.setText(str(score))
        self.score_label.setStyleSheet(
            f"color: {color}; font-size: 38px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        if suggestion:
            self.suggestion_label.setText(suggestion)
        if stars is not None:
            self.stars_label.setText('★' * stars + '☆' * (5 - stars))
        self.level_label.setText(self._get_level_text(score))
        self.level_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")


class StockInfoCard(QFrame):
    """股票信息卡片 - 代码+名称+现价+涨跌幅+AI评分"""

    def __init__(self, code='', name='', price=0, change=0,
                 ai_score=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            StockInfoCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 6px;
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
        change_color = UP_COLOR if change >= 0 else DOWN_COLOR
        change_sign = '+' if change >= 0 else ''
        self.change_label = QLabel(f'{change_sign}{change:.2f}%')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 13px; font-weight: 600;")
        price_box.addWidget(self.change_label)
        layout.addLayout(price_box)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {BORDER_DEFAULT};")
        layout.addWidget(sep)

        # AI评分
        ai_box = QVBoxLayout()
        ai_box.setSpacing(2)
        ai_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        ai_title = QLabel('AI评分')
        ai_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        ai_box.addWidget(ai_title)
        score_color = AI_SCORE_HIGH if ai_score >= 80 else AI_SCORE_MID
        self.ai_score_label = QLabel(str(ai_score))
        self.ai_score_label.setStyleSheet(
            f"color: {score_color}; font-size: 22px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
        ai_box.addWidget(self.ai_score_label)
        layout.addLayout(ai_box)

    def update_stock(self, code, name, price, change, ai_score=0):
        """更新股票信息"""
        self.code_label.setText(code)
        self.name_label.setText(name)
        self.price_label.setText(f'{price:.2f}')
        change_color = UP_COLOR if change >= 0 else DOWN_COLOR
        change_sign = '+' if change >= 0 else ''
        self.change_label.setText(f'{change_sign}{change:.2f}%')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 13px; font-weight: 600;")
        score_color = AI_SCORE_HIGH if ai_score >= 80 else AI_SCORE_MID
        self.ai_score_label.setText(str(ai_score))
        self.ai_score_label.setStyleSheet(
            f"color: {score_color}; font-size: 22px; font-weight: 700; "
            f"font-family: 'Consolas', 'Courier New', monospace;"
        )
