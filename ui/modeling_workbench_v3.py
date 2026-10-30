# -*- coding: utf-8 -*-
"""
🧩 量化策略建模工作台 V3.0
设计风格：卡片式高光UI (Card-based Highlight UI)
参考：独立卡片 + 选中高光 + 交替背景 + 专业深色终端

布局：左侧垂直导航 | 顶部工具栏 | 主内容区(卡片式) | 右侧实时预览 | 底部状态栏
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
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_CARD_HOVER,
    BG_CARD_ACTIVE, BG_CONTAINER, BG_INTERACTIVE, BG_SIDEBAR,
    BG_SIDEBAR_ACTIVE, BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_WEAK,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    ACCENT_ORANGE, ACCENT_PURPLE, ACCENT_CYAN,
    STATUS_SUCCESS, STATUS_WARNING, STATUS_ERROR, STATUS_INFO,
)


# ============================================================
# 卡片式高光样式
# ============================================================
# 普通卡片
CARD_NORMAL = """
    background: rgba(22, 28, 38, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
"""

# 高光卡片（选中/激活）
CARD_HIGHLIGHT = """
    background: rgba(30, 50, 80, 0.6);
    border: 1px solid rgba(90, 169, 255, 0.5);
    border-radius: 12px;
"""

# 交替背景卡片
CARD_ALT = """
    background: rgba(18, 24, 34, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 10px;
"""

# 高光按钮
BTN_HIGHLIGHT = """
    QPushButton {
        background: rgba(90, 169, 255, 0.15);
        border: 1px solid rgba(90, 169, 255, 0.4);
        border-radius: 8px;
        color: #5aa9ff;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: rgba(90, 169, 255, 0.25);
        border: 1px solid rgba(90, 169, 255, 0.6);
    }
    QPushButton:pressed {
        background: rgba(90, 169, 255, 0.35);
    }
"""

BTN_SUCCESS = """
    QPushButton {
        background: rgba(0, 200, 83, 0.15);
        border: 1px solid rgba(0, 200, 83, 0.4);
        border-radius: 8px;
        color: #00c853;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: rgba(0, 200, 83, 0.25);
        border: 1px solid rgba(0, 200, 83, 0.6);
    }
"""

BTN_DEFAULT = """
    QPushButton {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        color: #9aa9b5;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        color: #edf2f7;
    }
"""

INPUT_GLASS = """
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 6px;
        color: #edf2f7;
        padding: 6px 10px;
        font-size: 12px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid rgba(90, 169, 255, 0.5);
        background: rgba(90, 169, 255, 0.05);
    }
    QComboBox QAbstractItemView {
        background: rgba(15, 20, 30, 0.98);
        border: 1px solid rgba(90, 169, 255, 0.3);
        border-radius: 8px;
        color: #edf2f7;
        padding: 4px;
        outline: none;
    }
    QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: 4px; }
    QComboBox QAbstractItemView::item:selected { background: rgba(90, 169, 255, 0.2); color: #5aa9ff; }
"""

TABLE_CARD = """
    QTableWidget {
        background: transparent;
        border: none;
        gridline-color: transparent;
        color: #edf2f7;
        font-size: 11px;
        outline: none;
    }
    QHeaderView::section {
        background: rgba(30, 41, 59, 0.6);
        color: #9aa9b5;
        padding: 8px 6px;
        border: none;
        border-bottom: 1px solid rgba(90, 169, 255, 0.2);
        font-size: 10px;
        font-weight: 700;
    }
    QTableWidget::item { padding: 8px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.03); }
    QTableWidget::item:selected { background: rgba(90, 169, 255, 0.15); color: #5aa9ff; }
"""


# ============================================================
# 渐变背景
# ============================================================
class GradientBackground(QWidget):
    """渐变光晕背景"""
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        
        # 基础深色
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0, QColor('#0a0e17'))
        base.setColorAt(0.5, QColor('#0d1520'))
        base.setColorAt(1, QColor('#0a0e17'))
        painter.fillRect(self.rect(), base)
        
        # 左上蓝光晕
        glow1 = QRadialGradient(int(w*0.12), int(h*0.08), 0, int(w*0.12), int(h*0.08), int(w*0.5))
        glow1.setColorAt(0, QColor(90, 169, 255, 30))
        glow1.setColorAt(0.6, QColor(90, 169, 255, 8))
        glow1.setColorAt(1, QColor(90, 169, 255, 0))
        painter.fillRect(self.rect(), glow1)
        
        # 右下紫光晕
        glow2 = QRadialGradient(int(w*0.88), int(h*0.92), 0, int(w*0.88), int(h*0.92), int(w*0.4))
        glow2.setColorAt(0, QColor(159, 122, 234, 22))
        glow2.setColorAt(0.6, QColor(159, 122, 234, 6))
        glow2.setColorAt(1, QColor(159, 122, 234, 0))
        painter.fillRect(self.rect(), glow2)


# ============================================================
# 高光卡片基类
# ============================================================
class HighlightCard(QFrame):
    """卡片式高光组件基类"""
    
    def __init__(self, highlight: bool = False, parent=None):
        super().__init__(parent)
        self._highlight = highlight
        self._apply_style()
        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
    
    def _apply_style(self):
        self.setStyleSheet(f"""
            HighlightCard {{ {CARD_HIGHLIGHT if self._highlight else CARD_NORMAL} }}
        """)
    
    def set_highlight(self, highlight: bool):
        self._highlight = highlight
        self._apply_style()


# ============================================================
# 左侧导航项（高光样式）
# ============================================================
class NavItemCard(QFrame):
    """卡片式导航项"""
    
    clicked = pyqtSignal(str)
    
    def __init__(self, nav_id: str, icon: str, name: str, active: bool = False, parent=None):
        super().__init__(parent)
        self.nav_id = nav_id
        self.icon = icon
        self.name = name
        self.active = active
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)
        
        # 左侧高光指示条
        self.indicator = QFrame()
        self.indicator.setFixedWidth(3)
        self.indicator.setFixedHeight(18)
        self.indicator.setStyleSheet(f"""
            QFrame {{
                background: {'#5aa9ff' if self.active else 'transparent'};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.indicator)
        
        # 图标
        self.icon_label = QLabel(self.icon)
        self.icon_label.setStyleSheet(f'font-size: 15px; color: {"#5aa9ff" if self.active else "#697a89"};')
        self.icon_label.setFixedWidth(22)
        layout.addWidget(self.icon_label)
        
        # 名称
        self.name_label = QLabel(self.name)
        self.name_label.setStyleSheet(f"""
            color: {'#edf2f7' if self.active else '#9aa9b5'};
            font-size: 12px;
            font-weight: {'600' if self.active else '400'};
        """)
        layout.addWidget(self.name_label)
        layout.addStretch()
        
        self._update_bg()
    
    def _update_bg(self):
        if self.active:
            self.setStyleSheet("""
                NavItemCard {
                    background: rgba(90, 169, 255, 0.1);
                    border: 1px solid rgba(90, 169, 255, 0.2);
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                NavItemCard { background: transparent; border: 1px solid transparent; border-radius: 8px; }
                NavItemCard:hover { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.06); }
            """)
    
    def set_active(self, active: bool):
        self.active = active
        self.indicator.setStyleSheet(f"""
            QFrame {{ background: {'#5aa9ff' if self.active else 'transparent'}; border-radius: 2px; }}
        """)
        self.icon_label.setStyleSheet(f'font-size: 15px; color: {"#5aa9ff" if self.active else "#697a89"};')
        self.name_label.setStyleSheet(f"""
            color: {'#edf2f7' if self.active else '#9aa9b5'};
            font-size: 12px; font-weight: {'600' if self.active else '400'};
        """)
        self._update_bg()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.nav_id)
        super().mousePressEvent(event)


# ============================================================
# 模型卡片（高光样式）
# ============================================================
class ModelCardHighlight(HighlightCard):
    """高光模型卡片"""
    
    clicked = pyqtSignal(str)
    
    MODELS = {
        'limit_pullback': {
            'name': '涨停回调', 'subtitle': '强势股低吸模型', 'icon': '📉',
            'color': '#ffd166', 'desc': '强势启动→涨停→回调→缩量洗盘→支撑→再次启动',
            'tags': ['缩量低吸', '强势洗盘', '5日线支撑'],
        },
        'box_breakout': {
            'name': '箱体突破', 'subtitle': '二波启动模型', 'icon': '📦',
            'color': '#5aa9ff', 'desc': '强势上涨→横盘整理→缩量筑平台→突破→第二波',
            'tags': ['平台蓄势', '二次启动', '突破确认'],
        },
        'volume_breakout': {
            'name': '量价突破', 'subtitle': '主力启动模型', 'icon': '🚀',
            'color': '#00c853', 'desc': '极限缩量筑底→量价齐升→突破压力→回踩确认→再突破',
            'tags': ['主力启动', '量价齐升', '二次确认'],
        },
    }
    
    def __init__(self, model_key: str, active: bool = True, parent=None):
        super().__init__(highlight=active, parent=parent)
        self.model_key = model_key
        self.model_info = self.MODELS[model_key]
        self.active = active
        self.setFixedHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()
    
    def _init_ui(self):
        color = self.model_info['color']
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        # 标题行
        title_row = QHBoxLayout()
        icon = QLabel(self.model_info['icon'])
        icon.setStyleSheet('font-size: 22px;')
        title_row.addWidget(icon)
        
        title_col = QVBoxLayout()
        name = QLabel(self.model_info['name'])
        name.setStyleSheet(f'color: {color}; font-size: 15px; font-weight: 700;')
        title_col.addWidget(name)
        subtitle = QLabel(self.model_info['subtitle'])
        subtitle.setStyleSheet('color: #697a89; font-size: 10px;')
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col)
        title_row.addStretch()
        
        # 状态徽章
        self.status_badge = QLabel('● 已启用' if self.active else '○ 已禁用')
        self.status_badge.setStyleSheet(f"""
            color: {color if self.active else '#4a5868'};
            font-size: 10px; font-weight: 600;
            background: {'rgba(0,200,83,0.1)' if self.active else 'rgba(255,255,255,0.03)'};
            padding: 3px 8px; border-radius: 4px;
            border: 1px solid {'rgba(0,200,83,0.3)' if self.active else 'rgba(255,255,255,0.06)'};
        """)
        title_row.addWidget(self.status_badge)
        
        layout.addLayout(title_row)
        
        # 描述
        desc = QLabel(self.model_info['desc'])
        desc.setStyleSheet('color: #9aa9b5; font-size: 10px;')
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 标签
        tag_row = QHBoxLayout()
        for tag in self.model_info['tags']:
            tag_label = QLabel(tag)
            tag_label.setStyleSheet(f"""
                background: rgba({int(color[1:3],16)}, {int(color[3:5],16)}, {int(color[5:7],16)}, 0.1);
                color: {color};
                font-size: 9px; font-weight: 600;
                padding: 2px 7px; border-radius: 4px;
                border: 1px solid rgba({int(color[1:3],16)}, {int(color[3:5],16)}, {int(color[5:7],16)}, 0.2);
            """)
            tag_row.addWidget(tag_label)
        tag_row.addStretch()
        layout.addLayout(tag_row)
        
        layout.addStretch()
    
    def set_active(self, active: bool):
        self.active = active
        self.set_highlight(active)
        color = self.model_info['color']
        self.status_badge.setText('● 已启用' if self.active else '○ 已禁用')
        self.status_badge.setStyleSheet(f"""
            color: {color if self.active else '#4a5868'};
            font-size: 10px; font-weight: 600;
            background: {'rgba(0,200,83,0.1)' if self.active else 'rgba(255,255,255,0.03)'};
            padding: 3px 8px; border-radius: 4px;
            border: 1px solid {'rgba(0,200,83,0.3)' if self.active else 'rgba(255,255,255,0.06)'};
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model_key)
        super().mousePressEvent(event)


# ============================================================
# 权重滑块（高光样式）
# ============================================================
class WeightSliderCard(QWidget):
    """卡片式权重滑块"""
    
    valueChanged = pyqtSignal(str, int)
    
    def __init__(self, label: str, key: str, value: int, color: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.color = color
        self._init_ui(label, value)
    
    def _init_ui(self, label: str, value: int):
        # 外层卡片
        self.setStyleSheet("""
            WeightSliderCard {
                background: rgba(22, 28, 38, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 10px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        
        # 颜色指示点
        dot = QLabel('●')
        dot.setStyleSheet(f'color: {self.color}; font-size: 12px;')
        dot.setFixedWidth(14)
        layout.addWidget(dot)
        
        # 名称
        name_label = QLabel(label)
        name_label.setFixedWidth(90)
        name_label.setStyleSheet('color: #9aa9b5; font-size: 11px; font-weight: 500;')
        layout.addWidget(name_label)
        
        # 滑块
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 50)
        self.slider.setValue(value)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 5px; background: rgba(255,255,255,0.06); border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 18px; height: 18px; margin: -7px 0;
                background: {self.color};
                border: 2px solid rgba(255,255,255,0.4);
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.color}; border-radius: 3px;
            }}
        """)
        self.slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self.slider, stretch=1)
        
        # 数值
        self.value_label = QLabel(f'{value}分')
        self.value_label.setFixedWidth(45)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(f'color: {self.color}; font-size: 14px; font-weight: 700;')
        layout.addWidget(self.value_label)
    
    def _on_changed(self, val):
        self.value_label.setText(f'{val}分')
        self.valueChanged.emit(self.key, val)
    
    def value(self):
        return self.slider.value()


# ============================================================
# 主工作台 V3.0 - 卡片式高光UI
# ============================================================
class ModelingWorkbenchV3(QWidget):
    """量化策略建模工作台 V3.0 - 卡片式高光UI"""
    
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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 渐变背景
        self.bg = GradientBackground(self)
        self.bg.setGeometry(self.rect())
        
        # 内容容器
        self.content = QWidget(self)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        content_layout.addWidget(self._create_top_bar())
        
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setStyleSheet("QSplitter::handle { background: rgba(255,255,255,0.05); width: 1px; }")
        body.addWidget(self._create_left_nav())
        body.addWidget(self._create_main_content())
        body.addWidget(self._create_right_preview())
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([210, 720, 310])
        content_layout.addWidget(body, stretch=1)
        
        content_layout.addWidget(self._create_status_bar())
        
        main_layout.addWidget(self.content)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg'):
            self.bg.setGeometry(self.rect())
    
    # ---------- 顶部工具栏 ----------
    def _create_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(58)
        bar.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.7);
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(14)
        
        # Logo
        logo_row = QHBoxLayout()
        logo = QLabel('🧩')
        logo.setStyleSheet('font-size: 24px;')
        logo_row.addWidget(logo)
        title_col = QVBoxLayout()
        title = QLabel('量化策略建模工作台')
        title.setStyleSheet('color: #edf2f7; font-size: 14px; font-weight: 700;')
        title_col.addWidget(title)
        sub = QLabel('CARD-BASED HIGHLIGHT UI · V3.0')
        sub.setStyleSheet('color: #4a5868; font-size: 9px; letter-spacing: 1px;')
        title_col.addWidget(sub)
        logo_row.addLayout(title_col)
        layout.addLayout(logo_row)
        
        layout.addSpacing(16)
        
        # 模型名称输入
        self.model_name_input = QLineEdit('主力行为选股模型_v1')
        self.model_name_input.setFixedWidth(210)
        self.model_name_input.setStyleSheet(INPUT_GLASS)
        layout.addWidget(self.model_name_input)
        
        layout.addStretch()
        
        # 状态指示
        for text, color in [('● AI在线', '#00c853'), ('● 数据正常', '#5aa9ff')]:
            s = QLabel(text)
            s.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 500;')
            layout.addWidget(s)
        
        layout.addSpacing(8)
        
        # 按钮
        for text, style, slot in [
            ('💾 保存', BTN_DEFAULT, self._save_model),
            ('▶ 运行扫描', BTN_SUCCESS, self._run_scan),
            ('📊 回测', BTN_HIGHLIGHT, self._run_backtest),
            ('📤 导出', BTN_DEFAULT, self._export_model),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        
        return bar
    
    # ---------- 左侧导航 ----------
    def _create_left_nav(self) -> QWidget:
        nav = QFrame()
        nav.setFixedWidth(210)
        nav.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.5);
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(3)
        
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
            sec = QLabel(section_name)
            sec.setStyleSheet('color: #4a5868; font-size: 10px; font-weight: 700; padding: 10px 10px 4px 10px; letter-spacing: 0.5px;')
            layout.addWidget(sec)
            for nav_id, icon, name, active in items:
                item = NavItemCard(nav_id, icon, name, active)
                item.clicked.connect(self._on_nav_clicked)
                self.nav_items[nav_id] = item
                layout.addWidget(item)
        
        layout.addStretch()
        
        # AI助手卡片
        ai_card = HighlightCard(highlight=False)
        ai_card.setFixedHeight(58)
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
        self.stack = QTabWidget()
        self.stack.setStyleSheet("QTabWidget::pane { border: none; background: transparent; } QTabBar::tab { height: 0; padding: 0; border: none; margin: 0; }")
        self.stack.tabBar().hide()
        
        self.stack.addTab(self._create_models_page(), 'models')
        self.stack.addTab(self._create_weights_page(), 'weights')
        self.stack.addTab(self._create_params_page(), 'params')
        self.stack.addTab(self._create_placeholder('回测分析', '📊'), 'backtest')
        self.stack.addTab(self._create_placeholder('信号记录', '🔔'), 'signals')
        self.stack.addTab(self._create_placeholder('历史版本', '📜'), 'history')
        self.stack.addTab(self._create_placeholder('设置', '⚙️'), 'settings')
        
        return self.stack
    
    def _create_models_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { width: 6px; background: transparent; } QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 3px; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        # 页面标题卡片
        header_card = HighlightCard(highlight=False)
        header_card.setFixedHeight(70)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 12, 18, 12)
        title_col = QVBoxLayout()
        title = QLabel('🎯 模型库')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        title_col.addWidget(title)
        desc = QLabel('点击卡片启用/禁用模型，每个模型包含独立的参数配置和识别逻辑')
        desc.setStyleSheet('color: #697a89; font-size: 11px;')
        title_col.addWidget(desc)
        header_layout.addLayout(title_col)
        header_layout.addStretch()
        active_count = sum(1 for v in self.active_models.values() if v)
        count_badge = QLabel(f'已启用 {active_count}/3')
        count_badge.setStyleSheet("""
            color: #00c853; font-size: 12px; font-weight: 700;
            background: rgba(0,200,83,0.1); padding: 6px 14px; border-radius: 6px;
            border: 1px solid rgba(0,200,83,0.3);
        """)
        header_layout.addWidget(count_badge)
        layout.addWidget(header_card)
        
        # 模型卡片网格
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, key in enumerate(['limit_pullback', 'box_breakout', 'volume_breakout']):
            card = ModelCardHighlight(key, self.active_models.get(key, True))
            card.clicked.connect(self._toggle_model)
            self.model_cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)
        
        # 扫描参数卡片
        scan_card = HighlightCard(highlight=False)
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(18, 14, 18, 14)
        scan_layout.setSpacing(12)
        scan_title = QLabel('⚙️ 扫描参数')
        scan_title.setStyleSheet('color: #edf2f7; font-size: 13px; font-weight: 700;')
        scan_layout.addWidget(scan_title)
        
        params_row = QHBoxLayout()
        params_row.setSpacing(16)
        for label, widget in [
            ('最低评分', self._make_spin(60, 0, 100, '分')),
            ('扫描模式', self._make_combo(['快速扫描', '深度扫描', '全市场扫描'])),
            ('最大数量', self._make_spin(0, 0, 5000, '只', special=True)),
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
        scroll.setWidget(content)
        return scroll
    
    def _create_weights_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { width: 6px; background: transparent; } QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 3px; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        # 标题
        title = QLabel('⚖️ AI评分权重配置')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        layout.addWidget(title)
        desc = QLabel('总分100分，拖动滑块实时调整各维度权重，系统自动校验总分')
        desc.setStyleSheet('color: #697a89; font-size: 11px;')
        layout.addWidget(desc)
        
        # 权重卡片
        weight_card = HighlightCard(highlight=False)
        weight_layout = QVBoxLayout(weight_card)
        weight_layout.setContentsMargins(18, 16, 18, 16)
        weight_layout.setSpacing(10)
        
        configs = [
            ('主力行为结构', 'main_force', 40, '#ffd166'),
            ('量价关系', 'volume_price', 20, '#00c853'),
            ('趋势均线', 'trend_ma', 15, '#5aa9ff'),
            ('涨停强势基因', 'limit_gene', 10, '#ef5350'),
            ('技术指标确认', 'tech_confirm', 10, '#9f7aea'),
            ('市场环境', 'market_env', 5, '#64d2ff'),
        ]
        
        for label, key, default, color in configs:
            slider = WeightSliderCard(label, key, self.weights.get(key, default), color)
            slider.valueChanged.connect(self._on_weight_changed)
            self.weight_sliders[key] = slider
            weight_layout.addWidget(slider)
        
        # 分隔线
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet('background: rgba(255,255,255,0.06);')
        weight_layout.addWidget(line)
        
        # 总分行
        total_row = QHBoxLayout()
        total_label = QLabel('总分')
        total_label.setStyleSheet('color: #9aa9b5; font-size: 13px; font-weight: 600;')
        total_row.addWidget(total_label)
        total_row.addStretch()
        self.total_weight_label = QLabel('100 / 100')
        self.total_weight_label.setStyleSheet('color: #00c853; font-size: 22px; font-weight: 700;')
        total_row.addWidget(self.total_weight_label)
        self.weight_status = QLabel('✓ 标准')
        self.weight_status.setStyleSheet('color: #00c853; font-size: 11px; margin-left: 14px;')
        total_row.addWidget(self.weight_status)
        weight_layout.addLayout(total_row)
        
        layout.addWidget(weight_card)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll
    
    def _create_params_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { width: 6px; background: transparent; } QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 3px; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel('📝 模型参数配置')
        title.setStyleSheet('color: #edf2f7; font-size: 18px; font-weight: 700;')
        layout.addWidget(title)
        
        # 参数标签页
        params_tabs = QTabWidget()
        params_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
                background: rgba(22, 28, 38, 0.4);
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.03);
                color: #9aa9b5;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
                border: 1px solid rgba(255,255,255,0.06);
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(30, 50, 80, 0.5);
                color: #5aa9ff;
                border: 1px solid rgba(90, 169, 255, 0.3);
                border-bottom: none;
            }
        """)
        params_tabs.addTab(self._create_model_params('limit_pullback'), '📉 涨停回调')
        params_tabs.addTab(self._create_model_params('box_breakout'), '📦 箱体突破')
        params_tabs.addTab(self._create_model_params('volume_breakout'), '🚀 量价突破')
        layout.addWidget(params_tabs)
        
        layout.addStretch()
        scroll.setWidget(content)
        return scroll
    
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
                w = QComboBox()
                w.addItems(param[2])
                w.setStyleSheet(INPUT_GLASS)
                w.setFixedWidth(220)
            elif ptype == 'int':
                w = QSpinBox()
                w.setRange(param[2], param[3])
                w.setValue(param[1])
                w.setStyleSheet(INPUT_GLASS)
                w.setFixedWidth(220)
            else:
                w = QDoubleSpinBox()
                w.setRange(param[2], param[3])
                w.setValue(param[1])
                w.setSingleStep(0.1)
                w.setStyleSheet(INPUT_GLASS)
                w.setFixedWidth(220)
            
            layout.addRow(label, w)
        
        return widget
    
    def _create_placeholder(self, title: str, icon: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet('font-size: 52px;')
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        t = QLabel(title)
        t.setStyleSheet('color: #9aa9b5; font-size: 16px; font-weight: 600;')
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t)
        d = QLabel('功能开发中...')
        d.setStyleSheet('color: #4a5868; font-size: 12px;')
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(d)
        return page
    
    # ---------- 右侧预览 ----------
    def _create_right_preview(self) -> QWidget:
        preview = QFrame()
        preview.setFixedWidth(310)
        preview.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.5);
                border-left: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(12)
        
        # 标题
        header = QHBoxLayout()
        title = QLabel('👁 实时预览')
        title.setStyleSheet('color: #edf2f7; font-size: 13px; font-weight: 700;')
        header.addWidget(title)
        header.addStretch()
        self.preview_status = QLabel('待运行')
        self.preview_status.setStyleSheet('color: #697a89; font-size: 10px;')
        header.addWidget(self.preview_status)
        layout.addLayout(header)
        
        # 统计卡片（3个并排）
        stats_row = QHBoxLayout()
        for label, key, color in [
            ('候选股', 'candidates', '#5aa9ff'),
            ('S/A级', 'high_grade', '#ffd166'),
            ('平均分', 'avg_score', '#00c853'),
        ]:
            card = HighlightCard(highlight=False)
            card.setFixedHeight(62)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(4, 6, 4, 6)
            cl.setSpacing(2)
            val = QLabel('--')
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(f'color: {color}; font-size: 16px; font-weight: 700;')
            cl.addWidget(val)
            n = QLabel(label)
            n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet('color: #697a89; font-size: 9px;')
            cl.addWidget(n)
            stats_row.addWidget(card)
            setattr(self, f'stats_{key}', val)
        layout.addLayout(stats_row)
        
        # 评分分布卡片
        dist_card = HighlightCard(highlight=False)
        dl = QVBoxLayout(dist_card)
        dl.setContentsMargins(12, 12, 12, 12)
        dl.setSpacing(6)
        dt = QLabel('📊 评分分布')
        dt.setStyleSheet('color: #edf2f7; font-size: 11px; font-weight: 600;')
        dl.addWidget(dt)
        self.dist_bars = {}
        for grade, color in [('S级(90+)', '#ffd166'), ('A级(80-90)', '#00c853'),
                              ('B级(70-80)', '#5aa9ff'), ('C级(60-70)', '#697a89')]:
            br = QHBoxLayout()
            lab = QLabel(grade)
            lab.setFixedWidth(58)
            lab.setStyleSheet('color: #9aa9b5; font-size: 9px;')
            br.addWidget(lab)
            bar_bg = QFrame()
            bar_bg.setFixedHeight(10)
            bar_bg.setStyleSheet('background: rgba(255,255,255,0.05); border-radius: 5px;')
            bar_inner = QFrame(bar_bg)
            bar_inner.setFixedHeight(10)
            bar_inner.setStyleSheet(f'background: {color}; border-radius: 5px;')
            bar_inner.setFixedWidth(0)
            br.addWidget(bar_bg, stretch=1)
            cl = QLabel('0')
            cl.setFixedWidth(20)
            cl.setAlignment(Qt.AlignmentFlag.AlignRight)
            cl.setStyleSheet(f'color: {color}; font-size: 9px; font-weight: 600;')
            br.addWidget(cl)
            dl.addLayout(br)
            self.dist_bars[grade] = (bar_inner, cl, bar_bg)
        layout.addWidget(dist_card)
        
        # 候选股票卡片
        pool_card = HighlightCard(highlight=False)
        pl = QVBoxLayout(pool_card)
        pl.setContentsMargins(8, 10, 8, 8)
        pt = QLabel('🔥 候选股票 TOP10')
        pt.setStyleSheet('color: #edf2f7; font-size: 11px; font-weight: 600; padding: 0 4px 6px 4px;')
        pl.addWidget(pt)
        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(4)
        self.pool_table.setHorizontalHeaderLabels(['代码', '名称', '评分', '模型'])
        self.pool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pool_table.setStyleSheet(TABLE_CARD)
        self.pool_table.verticalHeader().setVisible(False)
        self.pool_table.setFixedHeight(220)
        pl.addWidget(self.pool_table)
        layout.addWidget(pool_card, stretch=1)
        
        return preview
    
    # ---------- 底部状态栏 ----------
    def _create_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.7);
                border-top: 1px solid rgba(255, 255, 255, 0.05);
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
    
    # ---------- 辅助 ----------
    def _make_spin(self, value, min_val, max_val, suffix, special=False):
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(value)
        if special:
            spin.setSpecialValueText('不限制')
        spin.setSuffix(f' {suffix}')
        spin.setStyleSheet(INPUT_GLASS)
        spin.setFixedWidth(150)
        return spin
    
    def _make_combo(self, items):
        combo = QComboBox()
        combo.addItems(items)
        combo.setStyleSheet(INPUT_GLASS)
        combo.setFixedWidth(150)
        return combo
    
    # ---------- 事件 ----------
    def _on_nav_clicked(self, nav_id: str):
        for nid, item in self.nav_items.items():
            item.set_active(nid == nav_id)
        self.current_nav = nav_id
        for i in range(self.stack.count()):
            if self.stack.tabText(i) == nav_id:
                self.stack.setCurrentIndex(i)
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
            self.total_weight_label.setStyleSheet('color: #ef5350; font-size: 22px; font-weight: 700;')
            self.weight_status.setText('⚠ 超过100分')
            self.weight_status.setStyleSheet('color: #ef5350; font-size: 11px; margin-left: 14px;')
        elif total < 100:
            self.total_weight_label.setStyleSheet('color: #ffd166; font-size: 22px; font-weight: 700;')
            self.weight_status.setText('⚠ 不足100分')
            self.weight_status.setStyleSheet('color: #ffd166; font-size: 11px; margin-left: 14px;')
        else:
            self.total_weight_label.setStyleSheet('color: #00c853; font-size: 22px; font-weight: 700;')
            self.weight_status.setText('✓ 标准')
            self.weight_status.setStyleSheet('color: #00c853; font-size: 11px; margin-left: 14px;')
    
    def _save_model(self):
        config = {'name': self.model_name_input.text(), 'active_models': self.active_models, 'weights': self.weights}
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'modeling_workbench_v3.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, '保存成功', f'模型配置已保存到:\n{path}')
    
    def _load_config(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'modeling_workbench_v3.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
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
        self._simulate_scan()
        self.preview_status.setText('扫描完成')
        self.preview_status.setStyleSheet('color: #00c853; font-size: 10px;')
    
    def _simulate_scan(self):
        import random
        random.seed(42)
        mock = [
            ('000001', '平安银行', '涨停回调'), ('000002', '万科A', '箱体突破'),
            ('000063', '中兴通讯', '量价突破'), ('000100', 'TCL科技', '涨停回调'),
            ('000333', '美的集团', '箱体突破'), ('000651', '格力电器', '量价突破'),
            ('000725', '京东方A', '涨停回调'), ('000858', '五粮液', '箱体突破'),
            ('002415', '海康威视', '量价突破'), ('002594', '比亚迪', '涨停回调'),
        ]
        self.pool_table.setRowCount(0)
        grades = {'S级(90+)': 0, 'A级(80-90)': 0, 'B级(70-80)': 0, 'C级(60-70)': 0}
        total = 0
        for i, (code, name, model) in enumerate(mock):
            score = random.randint(62, 95)
            total += score
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
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.pool_table.setItem(i, j, item)
        self.stats_candidates.setText(str(len(mock)))
        self.stats_high_grade.setText(str(grades['S级(90+)'] + grades['A级(80-90)']))
        self.stats_avg_score.setText(f'{total / len(mock):.1f}')
        for grade, count in grades.items():
            bar_inner, count_label, bar_bg = self.dist_bars[grade]
            pct = count / len(mock)
            bar_inner.setFixedWidth(int(bar_bg.width() * pct) if bar_bg.width() > 0 else int(80 * pct))
            count_label.setText(str(count))
    
    def _run_backtest(self):
        QMessageBox.information(self, '回测', '回测功能开发中\n\n将接入回测系统，基于当前模型参数进行历史回测。')
    
    def _export_model(self):
        QMessageBox.information(self, '导出', '模型导出功能开发中\n\n支持导出为JSON/Python策略文件，可直接接入回测系统。')
