# -*- coding: utf-8 -*-
"""
左侧导航栏组件 - sidebar.py
专业量化终端风格，支持展开/收缩、分组菜单、高亮选中
"""

import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont

from ui.theme.design_tokens import (
    ACCENT_BLUE,
    ACCENT_RED,
    BG_PANEL,
    BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE,
    BORDER,
    BORDER_SOFT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_WEAK,
)


class NavButton(QPushButton):
    """导航按钮"""

    def __init__(self, icon: str, text: str, page_id: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._text = text
        self._page_id = page_id
        self._active = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setText(f'  {icon}  {text}')
        self.setStyleSheet(self._normal_style())

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.setStyleSheet(self._active_style())
        else:
            self.setStyleSheet(self._normal_style())

    def _normal_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding-left: 16px;
                font-size: 12px;
                font-weight: 600;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background: rgba(90, 169, 255, 0.08);
                color: {TEXT_PRIMARY};
                border-left: 3px solid {ACCENT_BLUE};
            }}
        """

    def _active_style(self) -> str:
        return f"""
            QPushButton {{
                background: rgba(90, 169, 255, 0.10);
                color: {ACCENT_RED};
                border: none;
                border-left: 3px solid {ACCENT_RED};
                text-align: left;
                padding-left: 16px;
                font-size: 12px;
                font-weight: 700;
                border-radius: 0;
            }}
        """


class NavGroup(QWidget):
    """导航分组（带标题）"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QWidget {{
                background: rgba(18, 25, 34, 0.82);
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f'color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; '
            f'padding: 4px 6px; letter-spacing: 1px; text-transform: uppercase;'
        )
        layout.addWidget(self.title_label)

        self.buttons_layout = QVBoxLayout()
        self.buttons_layout.setSpacing(2)
        layout.addLayout(self.buttons_layout)

    def add_button(self, button: NavButton):
        self.buttons_layout.addWidget(button)


class Sidebar(QWidget):
    """
    左侧导航栏
    支持分组菜单、页面切换信号、展开/收缩
    """

    page_changed = pyqtSignal(str)  # 页面ID

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = {}
        self._current_page = None
        self._expanded = True

        self.setFixedWidth(224)
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_SIDEBAR},
                    stop:1 #0b1017);
                border-right: 1px solid {BORDER};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QGroupBox {{
                border: none;
            }}
        """)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Logo区域
        logo_widget = QWidget()
        logo_widget.setFixedHeight(60)
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(16, 0, 16, 0)
        logo_layout.setSpacing(10)

        logo_icon = QLabel('📊')
        logo_icon.setStyleSheet('font-size: 22px;')
        logo_layout.addWidget(logo_icon)

        logo_text_layout = QVBoxLayout()
        logo_text_layout.setContentsMargins(0, 0, 0, 0)
        logo_text_layout.setSpacing(0)

        logo_title = QLabel('QUANT AI')
        logo_title.setStyleSheet(
            f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 800; letter-spacing: 1px;'
        )
        logo_title.setContentsMargins(0, 0, 0, 0)
        logo_text_layout.addWidget(logo_title)

        logo_sub = QLabel('TERMINAL V6')
        logo_sub.setStyleSheet(
            f'color: {TEXT_WEAK}; font-size: 9px; font-weight: 700; letter-spacing: 2px;'
        )
        logo_text_layout.addWidget(logo_sub)

        logo_layout.addLayout(logo_text_layout)
        logo_layout.addStretch()
        main_layout.addWidget(logo_widget)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f'background: {BORDER_SOFT}; max-height: 1px;')
        main_layout.addWidget(sep)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_SOFT}; border-radius: 2px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background: transparent;")
        self.nav_layout = QVBoxLayout(scroll_content)
        self.nav_layout.setContentsMargins(8, 8, 8, 16)
        self.nav_layout.setSpacing(8)
        self.nav_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 底部工具区：ChatGPT入口
        tool_widget = QWidget()
        tool_widget.setFixedHeight(52)
        tool_layout = QVBoxLayout(tool_widget)
        tool_layout.setContentsMargins(12, 8, 12, 0)
        tool_layout.setSpacing(0)

        self.chatgpt_btn = QPushButton('🤖 ChatGPT AI助手')
        self.chatgpt_btn.setToolTip('打开 ChatGPT，会在系统默认浏览器中打开，不使用API。')
        self.chatgpt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chatgpt_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(90, 169, 255, 0.12);
                border: 1px solid {BORDER_SOFT};
                border-radius: 8px;
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 700;
                padding: 8px 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: rgba(90, 169, 255, 0.18);
                border: 1px solid {ACCENT_BLUE};
                box-shadow: inset 0 0 0 1px rgba(90,169,255,0.18);
            }}
        """)
        self.chatgpt_btn.clicked.connect(self._open_chatgpt)
        tool_layout.addWidget(self.chatgpt_btn)
        main_layout.addWidget(tool_widget)

        # 底部状态
        bottom = QWidget()
        bottom.setFixedHeight(50)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 0, 16, 0)
        bottom_layout.setSpacing(8)

        self.status_dot = QLabel('●')
        self.status_dot.setStyleSheet(f'color: {ACCENT_RED}; font-size: 10px;')
        bottom_layout.addWidget(self.status_dot)

        self.status_text = QLabel('系统正常')
        self.status_text.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        bottom_layout.addWidget(self.status_text)
        bottom_layout.addStretch()

        main_layout.addWidget(bottom)

    def add_group(self, title: str):
        """添加导航分组"""
        group = NavGroup(title)
        # 插入到stretch之前
        self.nav_layout.insertWidget(self.nav_layout.count() - 1, group)
        return group

    def add_nav_item(self, group: NavGroup, icon: str, text: str, page_id: str):
        """添加导航项"""
        btn = NavButton(icon, text, page_id)
        btn.clicked.connect(lambda: self._on_nav_clicked(page_id))
        group.add_button(btn)
        self._buttons[page_id] = btn
        return btn

    def _on_nav_clicked(self, page_id: str):
        self.set_current_page(page_id)
        self.page_changed.emit(page_id)

    def set_current_page(self, page_id: str):
        """设置当前选中页面"""
        if page_id not in self._buttons:
            return
        self._current_page = page_id
        for pid, btn in self._buttons.items():
            btn.set_active(pid == page_id)

    def _open_chatgpt(self):
        """使用系统默认浏览器打开 ChatGPT；没有真实数据源，因此不显示假状态。"""
        try:
            webbrowser.open('https://chatgpt.com/', new=2)
        except Exception:
            pass

    def get_current_page(self) -> str:
        return self._current_page

    def set_status(self, text: str, color: str = '#3FB950'):
        """设置底部状态"""
        self.status_text.setText(text)
        self.status_dot.setStyleSheet(f'color: {color}; font-size: 10px;')
