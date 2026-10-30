# -*- coding: utf-8 -*-
"""
顶部行情栏组件 - top_bar.py
显示指数、涨跌家数、市场状态、AI状态、时钟
专业量化终端风格
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme.design_tokens import (
    ACCENT_BLUE,
    ACCENT_GOLD,
    ACCENT_RED,
    BG_CARD,
    BG_PANEL,
    BG_PANEL_ALT,
    BG_WINDOW,
    BORDER,
    BORDER_SOFT,
    FLAT,
    LIMIT_UP,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    UP,
    DOWN,
)


class IndexCard(QWidget):
    """指数卡片"""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self._name = name
        self.setFixedHeight(48)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(0)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(
            f'color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;'
        )
        layout.addWidget(self.name_label)

        value_layout = QHBoxLayout()
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(8)

        self.price_label = QLabel('--')
        self.price_label.setStyleSheet(
            f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700; '
            'font-family: "Consolas", "Courier New", monospace;'
        )
        value_layout.addWidget(self.price_label)

        self.change_label = QLabel('--')
        self.change_label.setStyleSheet(
            f'color: {TEXT_MUTED}; font-size: 11px; font-weight: 700; '
            'font-family: "Consolas", "Courier New", monospace;'
        )
        value_layout.addWidget(self.change_label)
        value_layout.addStretch()

        layout.addLayout(value_layout)

    def update_data(self, price: str, change_pct: str, is_up: bool):
        """更新指数数据"""
        self.price_label.setText(price)
        color = UP if is_up else DOWN
        arrow = '▲' if is_up else '▼'
        self.change_label.setText(f'{arrow} {change_pct}')
        self.change_label.setStyleSheet(
            f'color: {color}; font-size: 11px; font-weight: 700; '
            'font-family: "Consolas", "Courier New", monospace;'
        )


class MarketStatsWidget(QWidget):
    """涨跌家数统计"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        # 上涨
        up_layout = QVBoxLayout()
        up_layout.setContentsMargins(0, 0, 0, 0)
        up_layout.setSpacing(0)
        up_label = QLabel('上涨')
        up_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px; font-weight: 700;')
        up_layout.addWidget(up_label)
        self.up_count = QLabel('--')
        self.up_count.setStyleSheet(
            f'color: {UP}; font-size: 14px; font-weight: 700; '
            'font-family: "Consolas", monospace;'
        )
        up_layout.addWidget(self.up_count)
        layout.addLayout(up_layout)

        # 下跌
        down_layout = QVBoxLayout()
        down_layout.setContentsMargins(0, 0, 0, 0)
        down_layout.setSpacing(0)
        down_label = QLabel('下跌')
        down_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px; font-weight: 700;')
        down_layout.addWidget(down_label)
        self.down_count = QLabel('--')
        self.down_count.setStyleSheet(
            f'color: {DOWN}; font-size: 14px; font-weight: 700; '
            'font-family: "Consolas", monospace;'
        )
        down_layout.addWidget(self.down_count)
        layout.addLayout(down_layout)

        # 涨停
        limit_layout = QVBoxLayout()
        limit_layout.setContentsMargins(0, 0, 0, 0)
        limit_layout.setSpacing(0)
        limit_label = QLabel('涨停')
        limit_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px; font-weight: 700;')
        limit_layout.addWidget(limit_label)
        self.limit_count = QLabel('--')
        self.limit_count.setStyleSheet(
            f'color: {LIMIT_UP}; font-size: 14px; font-weight: 700; '
            'font-family: "Consolas", monospace;'
        )
        limit_layout.addWidget(self.limit_count)
        layout.addLayout(limit_layout)

    def update_data(self, up: int, down: int, limit_up: int):
        self.up_count.setText(str(up))
        self.down_count.setText(str(down))
        self.limit_count.setText(str(limit_up))


class TopBar(QWidget):
    """
    顶部行情栏
    左侧：涨跌家数
    右侧：市场状态 + AI状态 + 时钟 + 设置按钮
    """

    settings_clicked = pyqtSignal()
    backup_clicked = pyqtSignal()
    restore_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_PANEL},
                    stop:1 #0f1722);
                border-bottom: 1px solid {BORDER};
            }}
            QFrame {{
                border: 1px solid {BORDER};
            }}
        """)

        self._init_ui()
        self._setup_clock()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        layout.addStretch()

        # 状态块
        status_panel = QWidget()
        status_panel.setStyleSheet(f"""
            QWidget {{
                background: rgba(27, 35, 48, 0.88);
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(8, 6, 8, 6)
        status_layout.setSpacing(12)

        self.market_status_dot = QLabel('●')
        self.market_status_dot.setStyleSheet(f'color: {DOWN}; font-size: 12px;')
        status_layout.addWidget(self.market_status_dot)

        self.market_status_label = QLabel('交易中')
        self.market_status_label.setStyleSheet(
            f'color: {DOWN}; font-size: 12px; font-weight: 700;'
        )
        status_layout.addWidget(self.market_status_label)

        self.ai_status_dot = QLabel('●')
        self.ai_status_dot.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 12px;')
        status_layout.addWidget(self.ai_status_dot)

        self.ai_status_label = QLabel('AI在线')
        self.ai_status_label.setStyleSheet(
            f'color: {ACCENT_BLUE}; font-size: 12px; font-weight: 700;'
        )
        status_layout.addWidget(self.ai_status_label)

        self.data_status_dot = QLabel('●')
        self.data_status_dot.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 12px;')
        status_layout.addWidget(self.data_status_dot)

        self.data_status_label = QLabel('数据正常')
        self.data_status_label.setStyleSheet(
            f'color: {ACCENT_GOLD}; font-size: 12px; font-weight: 700;'
        )
        status_layout.addWidget(self.data_status_label)

        status_layout.addStretch()
        layout.addWidget(status_panel)

        # 时钟
        self.clock_panel = QWidget()
        self.clock_panel.setStyleSheet(f"""
            QWidget {{
                background: rgba(27, 35, 48, 0.88);
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        clock_layout = QVBoxLayout(self.clock_panel)
        clock_layout.setContentsMargins(10, 6, 10, 6)
        clock_layout.setSpacing(0)
        self.clock_label = QLabel('--:--')
        self.clock_label.setStyleSheet(
            f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700; '
            'font-family: "Consolas", "Courier New", monospace; letter-spacing: 1px;'
        )
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clock_layout.addWidget(self.clock_label)
        layout.addWidget(self.clock_panel)

        # 备份按钮
        self.backup_btn = QPushButton('备份')
        self.backup_btn.setFixedHeight(30)
        self.backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOFT}; border-radius: 6px;
                color: {TEXT_SECONDARY}; font-size: 13px; padding: 0 12px;
            }}
            QPushButton:hover {{
                background: rgba(90,169,255,0.10); color: {TEXT_PRIMARY}; border-color: {ACCENT_BLUE};
            }}
        """)
        self.backup_btn.clicked.connect(self.backup_clicked.emit)
        layout.addWidget(self.backup_btn)

        # 回滚按钮
        self.restore_btn = QPushButton('回滚')
        self.restore_btn.setFixedHeight(30)
        self.restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOFT}; border-radius: 6px;
                color: {TEXT_SECONDARY}; font-size: 13px; padding: 0 12px;
            }}
            QPushButton:hover {{
                background: rgba(190,80,80,0.12); color: #ff8a80; border-color: #e57373;
            }}
        """)
        self.restore_btn.clicked.connect(self.restore_clicked.emit)
        layout.addWidget(self.restore_btn)

        # 设置按钮
        self.settings_btn = QPushButton('⚙')
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {BORDER_SOFT}; border-radius: 6px;
                color: {TEXT_SECONDARY}; font-size: 16px;
            }}
            QPushButton:hover {{
                background: rgba(90,169,255,0.10); color: {TEXT_PRIMARY}; border-color: {ACCENT_BLUE};
            }}
        """)
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn)

    def _setup_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(60000)  # 每分钟更新一次，避免秒数跳动
        self._update_clock()

    def _update_clock(self):
        from datetime import datetime
        now = datetime.now()
        self.clock_label.setText(now.strftime('%H:%M'))

    def set_market_status(self, status: str, is_open: bool):
        """设置市场状态"""
        color = DOWN if is_open else ACCENT_RED
        self.market_status_dot.setStyleSheet(f'color: {color}; font-size: 12px;')
        self.market_status_label.setStyleSheet(
            f'color: {color}; font-size: 12px; font-weight: 600;'
        )
        self.market_status_label.setText(status)

    def set_ai_status(self, status: str, online: bool):
        """设置AI状态"""
        color = ACCENT_BLUE if online else ACCENT_RED
        self.ai_status_dot.setStyleSheet(f'color: {color}; font-size: 12px;')
        self.ai_status_label.setStyleSheet(
            f'color: {color}; font-size: 12px; font-weight: 600;'
        )
        self.ai_status_label.setText(status)
