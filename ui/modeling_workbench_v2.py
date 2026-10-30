# -*- coding: utf-8 -*-
"""
🧩 量化策略建模工作台 V2.0
设计风格：苹果玻璃UI (Glassmorphism) + 背景高斯模糊 + 专业量化终端

布局：左侧垂直导航 | 顶部工具栏 | 主内容区 | 右侧实时预览 | 底部状态栏
"""
import os
import json
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QSplitter,
    QProgressBar, QComboBox, QLineEdit, QMessageBox, QApplication,
    QScrollArea, QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
    QCheckBox, QSlider, QTabWidget, QSizePolicy, QGridLayout,
    QGraphicsBlurEffect, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient, QPalette

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_CARD_HOVER,
    BG_CARD_ACTIVE, BG_CONTAINER, BG_INTERACTIVE, BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE, BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_WEAK,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    ACCENT_ORANGE, ACCENT_PURPLE, ACCENT_CYAN,
    STATUS_SUCCESS, STATUS_WARNING, STATUS_ERROR, STATUS_INFO,
    UP, DOWN, FLAT,
)


# ============================================================
# 苹果玻璃效果样式表
# ============================================================
GLASS_CARD = """
    background: rgba(30, 41, 59, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
"""

GLASS_CARD_HOVER = """
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 14px;
"""

GLASS_BUTTON = """
    QPushButton {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 10px;
        color: #edf2f7;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.25);
    }
    QPushButton:pressed {
        background: rgba(255, 255, 255, 0.2);
    }
"""

GLASS_BUTTON_PRIMARY = """
    QPushButton {
        background: rgba(90, 169, 255, 0.3);
        border: 1px solid rgba(90, 169, 255, 0.5);
        border-radius: 10px;
        color: #edf2f7;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: rgba(90, 169, 255, 0.45);
        border: 1px solid rgba(90, 169, 255, 0.7);
    }
"""

GLASS_BUTTON_SUCCESS = """
    QPushButton {
        background: rgba(0, 200, 83, 0.25);
        border: 1px solid rgba(0, 200, 83, 0.45);
        border-radius: 10px;
        color: #edf2f7;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: rgba(0, 200, 83, 0.4);
        border: 1px solid rgba(0, 200, 83, 0.6);
    }
"""

GLASS_INPUT = """
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        color: #edf2f7;
        padding: 6px 10px;
        font-size: 12px;
        selection-background-color: rgba(90, 169, 255, 0.4);
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid rgba(90, 169, 255, 0.5);
        background: rgba(255, 255, 255, 0.1);
    }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: rgba(20, 28, 40, 0.95);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 8px;
        color: #edf2f7;
        padding: 4px;
        outline: none;
    }
    QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: 4px; }
    QComboBox QAbstractItemView::item:selected { background: rgba(90, 169, 255, 0.3); }
"""

GLASS_TABLE = """
    QTableWidget {
        background: rgba(15, 23, 35, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        gridline-color: rgba(255, 255, 255, 0.05);
        color: #edf2f7;
        font-size: 11px;
        outline: none;
    }
    QHeaderView::section {
        background: rgba(30, 41, 59, 0.6);
        color: #9aa9b5;
        padding: 8px 6px;
        border: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        font-size: 11px;
        font-weight: 600;
    }
    QTableWidget::item { padding: 6px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
    QTableWidget::item:selected { background: rgba(90, 169, 255, 0.25); color: #edf2f7; }
"""


# ============================================================
# 高斯模糊背景层
# ============================================================
class BlurBackground(QWidget):
    """高斯模糊渐变背景"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # 基础深色渐变
        base_grad = QLinearGradient(0, 0, w, h)
        base_grad.setColorAt(0, QColor('#0a0e17'))
        base_grad.setColorAt(0.5, QColor('#0d1520'))
        base_grad.setColorAt(1, QColor('#0a0e17'))
        painter.fillRect(self.rect(), base_grad)
        
        # 左上角蓝色光晕（模糊效果）
        blue_glow = QRadialGradient(int(w * 0.15), int(h * 0.1), 0, int(w * 0.15), int(h * 0.1), int(w * 0.5))
        blue_glow.setColorAt(0, QColor(90, 169, 255, 35))
        blue_glow.setColorAt(0.5, QColor(90, 169, 255, 10))
        blue_glow.setColorAt(1, QColor(90, 169, 255, 0))
        painter.fillRect(self.rect(), blue_glow)
        
        # 右下角紫色光晕
        purple_glow = QRadialGradient(int(w * 0.85), int(h * 0.9), 0, int(w * 0.85), int(h * 0.9), int(w * 0.45))
        purple_glow.setColorAt(0, QColor(159, 122, 234, 25))
        purple_glow.setColorAt(0.5, QColor(159, 122, 234, 8))
        purple_glow.setColorAt(1, QColor(159, 122, 234, 0))
        painter.fillRect(self.rect(), purple_glow)
        
        # 中间金色微光
        gold_glow = QRadialGradient(int(w * 0.5), int(h * 0.4), 0, int(w * 0.5), int(h * 0.4), int(w * 0.35))
        gold_glow.setColorAt(0, QColor(255, 209, 102, 12))
        gold_glow.setColorAt(1, QColor(255, 209, 102, 0))
        painter.fillRect(self.rect(), gold_glow)


# ============================================================
# 玻璃卡片基类
# ============================================================
class GlassCard(QFrame):
    """苹果玻璃效果卡片"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                {GLASS_CARD}
            }}
        """)
        # 阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)


# ============================================================
# 玻璃按钮
# ============================================================
class GlassButton(QPushButton):
    """苹果玻璃效果按钮"""
    
    def __init__(self, text: str, variant: str = 'default', parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
    
    def _apply_style(self):
        if self.variant == 'primary':
            self.setStyleSheet(GLASS_BUTTON_PRIMARY)
        elif self.variant == 'success':
            self.setStyleSheet(GLASS_BUTTON_SUCCESS)
        else:
            self.setStyleSheet(GLASS_BUTTON)


# ============================================================
# 左侧导航项
# ============================================================
class NavItem(QFrame):
    """左侧导航项"""
    
    clicked = pyqtSignal(str)
    
    def __init__(self, nav_id: str, icon: str, name: str, active: bool = False, parent=None):
        super().__init__(parent)
        self.nav_id = nav_id
        self.icon = icon
        self.name = name
        self.active = active
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)
        
        # 激活指示条
        self.indicator = QFrame()
        self.indicator.setFixedWidth(3)
        self.indicator.setFixedHeight(20)
        self.indicator.setStyleSheet(f"""
            QFrame {{
                background: {'#5aa9ff' if self.active else 'transparent'};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.indicator)
        
        # 图标
        icon_label = QLabel(self.icon)
        icon_label.setStyleSheet(f'font-size: 16px; color: {"#5aa9ff" if self.active else "#9aa9b5"};')
        icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)
        
        # 名称
        name_label = QLabel(self.name)
        name_label.setStyleSheet(f"""
            color: {'#edf2f7' if self.active else '#9aa9b5'};
            font-size: 12px;
            font-weight: {'600' if self.active else '400'};
        """)
        layout.addWidget(name_label)
        layout.addStretch()
        
        self._update_bg()
    
    def _update_bg(self):
        if self.active:
            self.setStyleSheet("""
                NavItem {
                    background: rgba(90, 169, 255, 0.12);
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                NavItem { background: transparent; border-radius: 10px; }
                NavItem:hover { background: rgba(255, 255, 255, 0.05); }
            """)
    
    def set_active(self, active: bool):
        self.active = active
        # 更新指示条
        self.indicator.setStyleSheet(f"""
            QFrame {{
                background: {'#5aa9ff' if self.active else 'transparent'};
                border-radius: 2px;
            }}
        """)
        # 更新图标和名称颜色
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                w = item.widget()
                if w.text() == self.icon:
                    w.setStyleSheet(f'font-size: 16px; color: {"#5aa9ff" if self.active else "#9aa9b5"};')
                elif w.text() == self.name:
                    w.setStyleSheet(f"""
                        color: {'#edf2f7' if self.active else '#9aa9b5'};
                        font-size: 12px;
                        font-weight: {'600' if self.active else '400'};
                    """)
        self._update_bg()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.nav_id)
        super().mousePressEvent(event)


# ============================================================
# 模型卡片（玻璃风格）
# ============================================================
class ModelCardGlass(GlassCard):
    """玻璃风格模型卡片"""
    
    clicked = pyqtSignal(str)
    
    MODELS = {
        'limit_pullback': {
            'name': '涨停回调', 'subtitle': '强势股低吸模型', 'icon': '📉',
            'color': '#ffd166', 'desc': '强势启动→涨停→回调→缩量洗盘→支撑→再次启动',
        },
        'box_breakout': {
            'name': '箱体突破', 'subtitle': '二波启动模型', 'icon': '📦',
            'color': '#5aa9ff', 'desc': '强势上涨→横盘整理→缩量筑平台→突破→第二波',
        },
        'volume_breakout': {
            'name': '量价突破', 'subtitle': '主力启动模型', 'icon': '🚀',
            'color': '#00c853', 'desc': '极限缩量筑底→量价齐升→突破压力→回踩确认→再突破',
        },
    }
    
    def __init__(self, model_key: str, active: bool = True, parent=None):
        super().__init__(parent)
        self.model_key = model_key
        self.model_info = self.MODELS[model_key]
        self.active = active
        self.setFixedHeight(130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()
    
    def _init_ui(self):
        color = self.model_info['color']
        border_color = color if self.active else 'rgba(255, 255, 255, 0.12)'
        
        self.setStyleSheet(f"""
            ModelCardGlass {{
                background: rgba(30, 41, 59, {'0.5' if self.active else '0.35'});
                border: 1px solid {border_color};
                border-radius: 14px;
            }}
            ModelCardGlass:hover {{
                background: rgba(30, 41, 59, 0.55);
                border: 1px solid {color};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        
        # 标题行
        title_row = QHBoxLayout()
        icon = QLabel(self.model_info['icon'])
        icon.setStyleSheet('font-size: 20px;')
        title_row.addWidget(icon)
        
        title_col = QVBoxLayout()
        name = QLabel(self.model_info['name'])
        name.setStyleSheet(f'color: {color}; font-size: 14px; font-weight: 700;')
        title_col.addWidget(name)
        subtitle = QLabel(self.model_info['subtitle'])
        subtitle.setStyleSheet('color: #697a89; font-size: 10px;')
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col)
        title_row.addStretch()
        
        # 状态指示
        status_dot = QLabel('●' if self.active else '○')
        status_dot.setStyleSheet(f'color: {color if self.active else "#4a5868"}; font-size: 12px;')
        title_row.addWidget(status_dot)
        
        layout.addLayout(title_row)
        
        # 描述
        desc = QLabel(self.model_info['desc'])
        desc.setStyleSheet('color: #9aa9b5; font-size: 10px;')
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addStretch()
    
    def set_active(self, active: bool):
        self.active = active
        color = self.model_info['color']
        border_color = color if self.active else 'rgba(255, 255, 255, 0.12)'
        self.setStyleSheet(f"""
            ModelCardGlass {{
                background: rgba(30, 41, 59, {'0.5' if self.active else '0.35'});
                border: 1px solid {border_color};
                border-radius: 14px;
            }}
            ModelCardGlass:hover {{
                background: rgba(30, 41, 59, 0.55);
                border: 1px solid {color};
            }}
        """)
        # 更新状态指示点
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                w = item.widget()
                if w.text() in ('●', '○'):
                    w.setText('●' if self.active else '○')
                    w.setStyleSheet(f'color: {color if self.active else "#4a5868"}; font-size: 12px;')
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model_key)
        super().mousePressEvent(event)


# ============================================================
# 权重滑块（玻璃风格）
# ============================================================
class WeightSliderGlass(QWidget):
    """玻璃风格权重滑块"""
    
    valueChanged = pyqtSignal(str, int)
    
    def __init__(self, label: str, key: str, value: int, color: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.color = color
        self._init_ui(label, value)
    
    def _init_ui(self, label: str, value: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        name_label = QLabel(label)
        name_label.setFixedWidth(85)
        name_label.setStyleSheet('color: #9aa9b5; font-size: 11px;')
        layout.addWidget(name_label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 50)
        self.slider.setValue(value)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -6px 0;
                background: {self.color};
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.color}; border-radius: 2px;
            }}
        """)
        self.slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self.slider, stretch=1)
        
        self.value_label = QLabel(f'{value}分')
        self.value_label.setFixedWidth(42)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(f'color: {self.color}; font-size: 13px; font-weight: 700;')
        layout.addWidget(self.value_label)
    
    def _on_changed(self, val):
        self.value_label.setText(f'{val}分')
        self.valueChanged.emit(self.key, val)
    
    def value(self):
        return self.slider.value()


# ============================================================
# 主建模工作台 V2.0
# ============================================================
class ModelingWorkbenchV2(QWidget):
    """量化策略建模工作台 V2.0 - 苹果玻璃UI + 高斯模糊背景"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_models = {'limit_pullback': True, 'box_breakout': True, 'volume_breakout': True}
        self.weights = {
            'main_force': 40, 'volume_price': 20, 'trend_ma': 15,
            'limit_gene': 10, 'tech_confirm': 10, 'market_env': 5,
        }
        self.current_nav = 'models'
        self.nav_items = {}
        self.model_cards = {}
        self.weight_sliders = {}
        self._init_ui()
        self._load_config()
    
    def _init_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 高斯模糊背景层
        self.blur_bg = BlurBackground(self)
        self.blur_bg.setGeometry(self.rect())
        
        # 内容容器（在背景之上）
        self.content = QWidget(self)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 顶部工具栏
        content_layout.addWidget(self._create_top_bar())
        
        # 主体三栏
        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,0.06); width: 1px; }")
        
        body_splitter.addWidget(self._create_left_nav())
        body_splitter.addWidget(self._create_main_content())
        body_splitter.addWidget(self._create_right_preview())
        
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setStretchFactor(2, 0)
        body_splitter.setSizes([200, 700, 300])
        
        content_layout.addWidget(body_splitter, stretch=1)
        
        # 底部状态栏
        content_layout.addWidget(self._create_status_bar())
        
        main_layout.addWidget(self.content)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'blur_bg'):
            self.blur_bg.setGeometry(self.rect())
    
    # ---------- 顶部工具栏 ----------
    def _create_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.6);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)
        
        # Logo + 标题
        logo_row = QHBoxLayout()
        logo = QLabel('🧩')
        logo.setStyleSheet('font-size: 22px;')
        logo_row.addWidget(logo)
        
        title_col = QVBoxLayout()
        title = QLabel('量化策略建模工作台')
        title.setStyleSheet('color: #edf2f7; font-size: 14px; font-weight: 700;')
        title_col.addWidget(title)
        subtitle = QLabel('QUANT AI · TERMINAL V2.0')
        subtitle.setStyleSheet('color: #697a89; font-size: 9px; letter-spacing: 1px;')
        title_col.addWidget(subtitle)
        logo_row.addLayout(title_col)
        layout.addLayout(logo_row)
        
        layout.addSpacing(20)
        
        # 模型名称
        self.model_name_input = QLineEdit('主力行为选股模型_v1')
        self.model_name_input.setFixedWidth(200)
        self.model_name_input.setStyleSheet(GLASS_INPUT)
        layout.addWidget(self.model_name_input)
        
        layout.addStretch()
        
        # 状态指示
        for text, color in [('● AI在线', '#00c853'), ('● 数据正常', '#5aa9ff')]:
            status = QLabel(text)
            status.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 500;')
            layout.addWidget(status)
        
        layout.addSpacing(8)
        
        # 按钮组
        for text, variant, slot in [
            ('💾 保存', 'default', self._save_model),
            ('▶ 运行扫描', 'success', self._run_scan),
            ('📊 回测', 'primary', self._run_backtest),
            ('📤 导出', 'default', self._export_model),
        ]:
            btn = GlassButton(text, variant)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        
        return bar
    
    # ---------- 左侧导航 ----------
    def _create_left_nav(self) -> QWidget:
        nav = QFrame()
        nav.setFixedWidth(200)
        nav.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.4);
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(4)
        
        # 分组标题
        sections = [
            ('建模中心', [
                ('models', '🎯', '模型库', True),
                ('weights', '⚖️', '评分权重', False),
                ('params', '📝', '模型参数', False),
            ]),
            ('分析中心', [
                ('backtest', '📊', '回测分析', False),
                ('signals', '🔔', '信号记录', False),
            ]),
            ('系统', [
                ('history', '📜', '历史版本', False),
                ('settings', '⚙️', '设置', False),
            ]),
        ]
        
        for section_name, items in sections:
            section_label = QLabel(section_name)
            section_label.setStyleSheet('color: #4a5868; font-size: 10px; font-weight: 600; padding: 8px 8px 4px 8px; letter-spacing: 0.5px;')
            layout.addWidget(section_label)
            
            for nav_id, icon, name, active in items:
                item = NavItem(nav_id, icon, name, active)
                item.clicked.connect(self._on_nav_clicked)
                self.nav_items[nav_id] = item
                layout.addWidget(item)
        
        layout.addStretch()
        
        # 底部AI助手入口
        ai_card = GlassCard()
        ai_card.setFixedHeight(60)
        ai_layout = QHBoxLayout(ai_card)
        ai_layout.setContentsMargins(12, 8, 12, 8)
        ai_icon = QLabel('🤖')
        ai_icon.setStyleSheet('font-size: 20px;')
        ai_layout.addWidget(ai_icon)
        ai_col = QVBoxLayout()
        ai_title = QLabel('AI助手')
        ai_title.setStyleSheet('color: #edf2f7; font-size: 11px; font-weight: 600;')
        ai_col.addWidget(ai_title)
        ai_sub = QLabel('智能建模建议')
        ai_sub.setStyleSheet('color: #697a89; font-size: 9px;')
        ai_col.addWidget(ai_sub)
        ai_layout.addLayout(ai_col)
        layout.addWidget(ai_card)
        
        return nav
    
    # ---------- 主内容区 ----------
    def _create_main_content(self) -> QWidget:
        self.content_stack = QTabWidget()
        self.content_stack.setStyleSheet("""
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar { display: none; }
        """)
        
        self.content_stack.addTab(self._create_models_page(), 'models')
        self.content_stack.addTab(self._create_weights_page(), 'weights')
        self.content_stack.addTab(self._create_params_page(), 'params')
        self.content_stack.addTab(self._create_placeholder_page('回测分析', '📊'), 'backtest')
        self.content_stack.addTab(self._create_placeholder_page('信号记录', '🔔'), 'signals')
        self.content_stack.addTab(self._create_placeholder_page('历史版本', '📜'), 'history')
        self.content_stack.addTab(self._create_placeholder_page('设置', '⚙️'), 'settings')
        
        return self.content_stack
    
    def _create_models_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        # 页面标题
        title_row = QHBoxLayout()
        title = QLabel('🎯 模型库')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        title_row.addWidget(title)
        title_row.addStretch()
        
        active_count = sum(1 for v in self.active_models.values() if v)
        count_label = QLabel(f'已启用 {active_count}/3 个模型')
        count_label.setStyleSheet('color: #00c853; font-size: 12px; font-weight: 600;')
        title_row.addWidget(count_label)
        layout.addLayout(title_row)
        
        desc = QLabel('点击卡片启用/禁用模型，每个模型包含独立的参数配置和识别逻辑')
        desc.setStyleSheet('color: #697a89; font-size: 11px;')
        layout.addWidget(desc)
        
        # 模型卡片网格
        cards_layout = QGridLayout()
        cards_layout.setSpacing(14)
        
        for i, key in enumerate(['limit_pullback', 'box_breakout', 'volume_breakout']):
            card = ModelCardGlass(key, self.active_models.get(key, True))
            card.clicked.connect(self._toggle_model)
            self.model_cards[key] = card
            cards_layout.addWidget(card, i // 3, i % 3)
        
        layout.addLayout(cards_layout)
        
        # 扫描参数卡片
        scan_card = GlassCard()
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(18, 14, 18, 14)
        scan_layout.setSpacing(12)
        
        scan_title = QLabel('⚙️ 扫描参数')
        scan_title.setStyleSheet('color: #edf2f7; font-size: 13px; font-weight: 700;')
        scan_layout.addWidget(scan_title)
        
        params_row = QHBoxLayout()
        params_row.setSpacing(16)
        
        for label, widget in [
            ('最低评分', self._create_spin(60, 0, 100, '分')),
            ('扫描模式', self._create_combo(['快速扫描', '深度扫描', '全市场扫描'])),
            ('最大数量', self._create_spin(0, 0, 5000, '只', special=True)),
        ]:
            col = QVBoxLayout()
            lab = QLabel(label)
            lab.setStyleSheet('color: #9aa9b5; font-size: 10px; margin-bottom: 4px;')
            col.addWidget(lab)
            col.addWidget(widget)
            params_row.addLayout(col)
        
        params_row.addStretch()
        scan_layout.addLayout(params_row)
        
        layout.addWidget(scan_card)
        layout.addStretch()
        
        return page
    
    def _create_weights_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel('⚖️ AI评分权重配置')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        layout.addWidget(title)
        
        desc = QLabel('总分100分，拖动滑块实时调整各维度权重，系统自动校验总分')
        desc.setStyleSheet('color: #697a89; font-size: 11px;')
        layout.addWidget(desc)
        
        # 权重卡片
        weight_card = GlassCard()
        weight_layout = QVBoxLayout(weight_card)
        weight_layout.setContentsMargins(20, 18, 20, 18)
        weight_layout.setSpacing(14)
        
        weight_configs = [
            ('主力行为结构', 'main_force', 40, '#ffd166'),
            ('量价关系', 'volume_price', 20, '#00c853'),
            ('趋势均线', 'trend_ma', 15, '#5aa9ff'),
            ('涨停强势基因', 'limit_gene', 10, '#ef5350'),
            ('技术指标确认', 'tech_confirm', 10, '#9f7aea'),
            ('市场环境', 'market_env', 5, '#64d2ff'),
        ]
        
        for label, key, default, color in weight_configs:
            slider = WeightSliderGlass(label, key, self.weights.get(key, default), color)
            slider.valueChanged.connect(self._on_weight_changed)
            self.weight_sliders[key] = slider
            weight_layout.addWidget(slider)
        
        # 分隔线
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet('background: rgba(255,255,255,0.08);')
        weight_layout.addWidget(line)
        
        # 总分
        total_row = QHBoxLayout()
        total_label = QLabel('总分')
        total_label.setStyleSheet('color: #9aa9b5; font-size: 13px; font-weight: 600;')
        total_row.addWidget(total_label)
        total_row.addStretch()
        
        self.total_weight_label = QLabel('100 / 100')
        self.total_weight_label.setStyleSheet('color: #00c853; font-size: 20px; font-weight: 700;')
        total_row.addWidget(self.total_weight_label)
        
        self.weight_status = QLabel('✓ 标准')
        self.weight_status.setStyleSheet('color: #00c853; font-size: 11px; margin-left: 12px;')
        total_row.addWidget(self.weight_status)
        
        weight_layout.addLayout(total_row)
        
        layout.addWidget(weight_card)
        layout.addStretch()
        
        return page
    
    def _create_params_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel('📝 模型参数配置')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        layout.addWidget(title)
        
        # 参数标签页
        params_tabs = QTabWidget()
        params_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                background: rgba(30, 41, 59, 0.3);
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.04);
                color: #9aa9b5;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
                border: 1px solid rgba(255,255,255,0.08);
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(30, 41, 59, 0.5);
                color: #5aa9ff;
            }
        """)
        
        params_tabs.addTab(self._create_model_params('limit_pullback'), '📉 涨停回调')
        params_tabs.addTab(self._create_model_params('box_breakout'), '📦 箱体突破')
        params_tabs.addTab(self._create_model_params('volume_breakout'), '🚀 量价突破')
        
        layout.addWidget(params_tabs)
        layout.addStretch()
        
        return page
    
    def _create_model_params(self, model_key: str) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet('background: transparent;')
        layout = QFormLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        params = {
            'limit_pullback': [
                ('涨停回看天数', 30, 5, 120, 'int'),
                ('回调最大幅度(%)', 25, 5, 50, 'float'),
                ('缩量阈值(倍)', 0.6, 0.1, 1.5, 'float'),
                ('支撑均线', 'MA5', ['MA5', 'MA10', 'MA20'], 'combo'),
                ('调整最小天数', 3, 1, 20, 'int'),
            ],
            'box_breakout': [
                ('箱体最小天数', 10, 5, 60, 'int'),
                ('箱体振幅(%)', 15, 5, 40, 'float'),
                ('缩量阈值(倍)', 0.7, 0.1, 1.5, 'float'),
                ('突破确认(%)', 2, 0.5, 10, 'float'),
                ('均线粘合阈值(%)', 3, 1, 10, 'float'),
            ],
            'volume_breakout': [
                ('筑底最小天数', 15, 5, 60, 'int'),
                ('极限缩量阈值(倍)', 0.4, 0.1, 1.0, 'float'),
                ('量价齐升天数', 3, 1, 10, 'int'),
                ('突破放量倍数', 2.0, 1.0, 5.0, 'float'),
                ('回踩确认天数', 3, 1, 10, 'int'),
            ],
        }
        
        for param in params.get(model_key, []):
            name = param[0]
            ptype = param[-1]
            label = QLabel(name)
            label.setStyleSheet('color: #9aa9b5; font-size: 12px;')
            
            if ptype == 'combo':
                widget_ctrl = QComboBox()
                widget_ctrl.addItems(param[2])
                widget_ctrl.setStyleSheet(GLASS_INPUT)
                widget_ctrl.setFixedWidth(200)
            elif ptype == 'int':
                widget_ctrl = QSpinBox()
                widget_ctrl.setRange(param[2], param[3])
                widget_ctrl.setValue(param[1])
                widget_ctrl.setStyleSheet(GLASS_INPUT)
                widget_ctrl.setFixedWidth(200)
            else:
                widget_ctrl = QDoubleSpinBox()
                widget_ctrl.setRange(param[2], param[3])
                widget_ctrl.setValue(param[1])
                widget_ctrl.setSingleStep(0.1)
                widget_ctrl.setStyleSheet(GLASS_INPUT)
                widget_ctrl.setFixedWidth(200)
            
            layout.addRow(label, widget_ctrl)
        
        return widget
    
    def _create_placeholder_page(self, title: str, icon: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet('font-size: 48px;')
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet('color: #9aa9b5; font-size: 16px; font-weight: 600;')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        desc = QLabel('功能开发中...')
        desc.setStyleSheet('color: #4a5868; font-size: 12px;')
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        return page
    
    # ---------- 右侧实时预览 ----------
    def _create_right_preview(self) -> QWidget:
        preview = QFrame()
        preview.setFixedWidth(300)
        preview.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.4);
                border-left: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(12)
        
        # 标题
        header_row = QHBoxLayout()
        title = QLabel('👁 实时预览')
        title.setStyleSheet('color: #edf2f7; font-size: 13px; font-weight: 700;')
        header_row.addWidget(title)
        header_row.addStretch()
        
        self.preview_status = QLabel('待运行')
        self.preview_status.setStyleSheet('color: #697a89; font-size: 10px;')
        header_row.addWidget(self.preview_status)
        layout.addLayout(header_row)
        
        # 统计卡片
        stats_row = QHBoxLayout()
        for label, key, color in [
            ('候选股', 'candidates', '#5aa9ff'),
            ('S/A级', 'high_grade', '#ffd166'),
            ('平均分', 'avg_score', '#00c853'),
        ]:
            card = GlassCard()
            card.setFixedHeight(64)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)
            card_layout.setSpacing(2)
            
            val = QLabel('--')
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(f'color: {color}; font-size: 16px; font-weight: 700;')
            card_layout.addWidget(val)
            
            name = QLabel(label)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet('color: #697a89; font-size: 9px;')
            card_layout.addWidget(name)
            
            stats_row.addWidget(card)
            setattr(self, f'stats_{key}', val)
        
        layout.addLayout(stats_row)
        
        # 评分分布
        dist_card = GlassCard()
        dist_layout = QVBoxLayout(dist_card)
        dist_layout.setContentsMargins(12, 12, 12, 12)
        dist_layout.setSpacing(6)
        
        dist_title = QLabel('📊 评分分布')
        dist_title.setStyleSheet('color: #edf2f7; font-size: 11px; font-weight: 600;')
        dist_layout.addWidget(dist_title)
        
        self.dist_bars = {}
        for grade, color in [('S级(90+)', '#ffd166'), ('A级(80-90)', '#00c853'),
                              ('B级(70-80)', '#5aa9ff'), ('C级(60-70)', '#697a89')]:
            bar_row = QHBoxLayout()
            label = QLabel(grade)
            label.setFixedWidth(58)
            label.setStyleSheet('color: #9aa9b5; font-size: 9px;')
            bar_row.addWidget(label)
            
            bar_bg = QFrame()
            bar_bg.setFixedHeight(10)
            bar_bg.setStyleSheet('background: rgba(255,255,255,0.06); border-radius: 5px;')
            bar_inner = QFrame(bar_bg)
            bar_inner.setFixedHeight(10)
            bar_inner.setStyleSheet(f'background: {color}; border-radius: 5px;')
            bar_inner.setFixedWidth(0)
            bar_row.addWidget(bar_bg, stretch=1)
            
            count_label = QLabel('0')
            count_label.setFixedWidth(20)
            count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            count_label.setStyleSheet(f'color: {color}; font-size: 9px; font-weight: 600;')
            bar_row.addWidget(count_label)
            
            dist_layout.addLayout(bar_row)
            self.dist_bars[grade] = (bar_inner, count_label, bar_bg)
        
        layout.addWidget(dist_card)
        
        # 候选股票列表
        pool_card = GlassCard()
        pool_layout = QVBoxLayout(pool_card)
        pool_layout.setContentsMargins(8, 10, 8, 8)
        
        pool_title = QLabel('🔥 候选股票 TOP10')
        pool_title.setStyleSheet('color: #edf2f7; font-size: 11px; font-weight: 600; padding: 0 4px 6px 4px;')
        pool_layout.addWidget(pool_title)
        
        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(4)
        self.pool_table.setHorizontalHeaderLabels(['代码', '名称', '评分', '模型'])
        self.pool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pool_table.setStyleSheet(GLASS_TABLE)
        self.pool_table.verticalHeader().setVisible(False)
        self.pool_table.setFixedHeight(220)
        pool_layout.addWidget(self.pool_table)
        
        layout.addWidget(pool_card, stretch=1)
        
        return preview
    
    # ---------- 底部状态栏 ----------
    def _create_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.6);
                border-top: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 4, 20, 4)
        layout.setSpacing(20)
        
        self.status_model = QLabel('模型: 主力行为选股模型_v1')
        self.status_model.setStyleSheet('color: #9aa9b5; font-size: 10px;')
        layout.addWidget(self.status_model)
        
        self.status_active = QLabel('已启用: 3/3 模型')
        self.status_active.setStyleSheet('color: #00c853; font-size: 10px;')
        layout.addWidget(self.status_active)
        
        layout.addStretch()
        
        self.status_weights = QLabel('权重: 100/100')
        self.status_weights.setStyleSheet('color: #9aa9b5; font-size: 10px;')
        layout.addWidget(self.status_weights)
        
        self.status_system = QLabel('● 系统正常')
        self.status_system.setStyleSheet('color: #00c853; font-size: 10px;')
        layout.addWidget(self.status_system)
        
        return bar
    
    # ---------- 辅助方法 ----------
    def _create_spin(self, value, min_val, max_val, suffix, special=False):
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(value)
        if special:
            spin.setSpecialValueText('不限制')
        spin.setSuffix(f' {suffix}')
        spin.setStyleSheet(GLASS_INPUT)
        spin.setFixedWidth(140)
        return spin
    
    def _create_combo(self, items):
        combo = QComboBox()
        combo.addItems(items)
        combo.setStyleSheet(GLASS_INPUT)
        combo.setFixedWidth(140)
        return combo
    
    # ---------- 事件处理 ----------
    def _on_nav_clicked(self, nav_id: str):
        for nid, item in self.nav_items.items():
            item.set_active(nid == nav_id)
        self.current_nav = nav_id
        
        # 切换到对应页面
        for i in range(self.content_stack.count()):
            if self.content_stack.tabText(i) == nav_id:
                self.content_stack.setCurrentIndex(i)
                break
    
    def _toggle_model(self, model_key: str):
        self.active_models[model_key] = not self.active_models.get(model_key, True)
        if model_key in self.model_cards:
            self.model_cards[model_key].set_active(self.active_models[model_key])
        
        active_count = sum(1 for v in self.active_models.values() if v)
        self.status_active.setText(f'已启用: {active_count}/3 模型')
        self.status_active.setStyleSheet(f'color: {"#00c853" if active_count > 0 else "#ef5350"}; font-size: 10px;')
    
    def _on_weight_changed(self, key: str, value: int):
        self.weights[key] = value
        total = sum(self.weights.values())
        self.total_weight_label.setText(f'{total} / 100')
        self.status_weights.setText(f'权重: {total}/100')
        
        if total > 100:
            self.total_weight_label.setStyleSheet('color: #ef5350; font-size: 20px; font-weight: 700;')
            self.weight_status.setText('⚠ 超过100分')
            self.weight_status.setStyleSheet('color: #ef5350; font-size: 11px; margin-left: 12px;')
        elif total < 100:
            self.total_weight_label.setStyleSheet('color: #ffd166; font-size: 20px; font-weight: 700;')
            self.weight_status.setText('⚠ 不足100分')
            self.weight_status.setStyleSheet('color: #ffd166; font-size: 11px; margin-left: 12px;')
        else:
            self.total_weight_label.setStyleSheet('color: #00c853; font-size: 20px; font-weight: 700;')
            self.weight_status.setText('✓ 标准')
            self.weight_status.setStyleSheet('color: #00c853; font-size: 11px; margin-left: 12px;')
    
    def _save_model(self):
        config = {
            'name': self.model_name_input.text(),
            'active_models': self.active_models,
            'weights': self.weights,
        }
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'modeling_workbench_v2.json'
        )
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, '保存成功', f'模型配置已保存到:\n{config_path}')
    
    def _load_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'modeling_workbench_v2.json'
        )
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if 'name' in config:
                    self.model_name_input.setText(config['name'])
                if 'weights' in config:
                    self.weights.update(config['weights'])
            except Exception:
                pass
    
    def _run_scan(self):
        active_count = sum(1 for v in self.active_models.values() if v)
        if active_count == 0:
            QMessageBox.warning(self, '提示', '请至少启用一个模型')
            return
        
        self.preview_status.setText('扫描中...')
        self.preview_status.setStyleSheet('color: #ffd166; font-size: 10px;')
        QApplication.processEvents()
        
        # 模拟扫描结果
        self._simulate_scan_results()
        
        self.preview_status.setText('扫描完成')
        self.preview_status.setStyleSheet('color: #00c853; font-size: 10px;')
    
    def _simulate_scan_results(self):
        import random
        random.seed(42)
        
        mock_stocks = [
            ('000001', '平安银行', '涨停回调'),
            ('000002', '万科A', '箱体突破'),
            ('000063', '中兴通讯', '量价突破'),
            ('000100', 'TCL科技', '涨停回调'),
            ('000333', '美的集团', '箱体突破'),
            ('000651', '格力电器', '量价突破'),
            ('000725', '京东方A', '涨停回调'),
            ('000858', '五粮液', '箱体突破'),
            ('002415', '海康威视', '量价突破'),
            ('002594', '比亚迪', '涨停回调'),
        ]
        
        self.pool_table.setRowCount(0)
        grades = {'S级(90+)': 0, 'A级(80-90)': 0, 'B级(70-80)': 0, 'C级(60-70)': 0}
        total_score = 0
        
        for i, (code, name, model) in enumerate(mock_stocks):
            score = random.randint(62, 95)
            total_score += score
            
            if score >= 90: grades['S级(90+)'] += 1
            elif score >= 80: grades['A级(80-90)'] += 1
            elif score >= 70: grades['B级(70-80)'] += 1
            else: grades['C级(60-70)'] += 1
            
            self.pool_table.insertRow(i)
            for j, text in enumerate([code, name, str(score), model]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 2:
                    color = '#ffd166' if score >= 90 else '#00c853' if score >= 80 else '#5aa9ff' if score >= 70 else '#697a89'
                    item.setForeground(QColor(color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.pool_table.setItem(i, j, item)
        
        self.stats_candidates.setText(str(len(mock_stocks)))
        self.stats_high_grade.setText(str(grades['S级(90+)'] + grades['A级(80-90)']))
        self.stats_avg_score.setText(f'{total_score / len(mock_stocks):.1f}')
        
        for grade, count in grades.items():
            bar_inner, count_label, bar_bg = self.dist_bars[grade]
            pct = count / len(mock_stocks)
            bar_inner.setFixedWidth(int(bar_bg.width() * pct) if bar_bg.width() > 0 else int(80 * pct))
            count_label.setText(str(count))
    
    def _run_backtest(self):
        QMessageBox.information(self, '回测', '回测功能开发中\n\n将接入回测系统，基于当前模型参数进行历史回测。')
    
    def _export_model(self):
        QMessageBox.information(self, '导出', '模型导出功能开发中\n\n支持导出为JSON/Python策略文件，可直接接入回测系统。')
