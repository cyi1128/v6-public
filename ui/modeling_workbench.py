# -*- coding: utf-8 -*-
"""
🧩 量化策略建模工作台 V1.0
全新可视化建模UI —— 三栏布局：模型库 | 建模画布 | 实时预览

核心功能：
- 三个主力行为模型可视化配置（涨停回调/箱体突破/量价突破）
- AI评分权重实时调节
- 建模画布流程图（输入→初筛→模型匹配→AI评分→输出）
- 实时预览候选股票池
- 专业深色量化终端风格
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
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient

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
# 模型卡片组件
# ============================================================
class ModelCard(QFrame):
    """主力行为模型卡片"""
    
    clicked = pyqtSignal(str)
    
    MODELS = {
        'limit_pullback': {
            'name': '涨停回调',
            'subtitle': '强势股低吸模型',
            'icon': '📉',
            'color': ACCENT_GOLD,
            'desc': '强势启动→涨停→回调→缩量洗盘→支撑→再次启动',
            'tags': ['缩量低吸', '强势洗盘', '5日线支撑'],
        },
        'box_breakout': {
            'name': '箱体突破',
            'subtitle': '二波启动模型',
            'icon': '📦',
            'color': ACCENT_BLUE,
            'desc': '强势上涨→横盘整理→缩量筑平台→突破→第二波',
            'tags': ['平台蓄势', '二次启动', '突破确认'],
        },
        'volume_breakout': {
            'name': '量价突破',
            'subtitle': '主力启动模型',
            'icon': '🚀',
            'color': ACCENT_GREEN,
            'desc': '极限缩量筑底→量价齐升→突破压力→回踩确认→再突破',
            'tags': ['主力启动', '量价齐升', '二次确认'],
        },
    }
    
    def __init__(self, model_key: str, parent=None):
        super().__init__(parent)
        self.model_key = model_key
        self.model_info = self.MODELS[model_key]
        self.active = False
        self._init_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def _init_ui(self):
        self.setFixedHeight(140)
        self.setStyleSheet(f"""
            ModelCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            ModelCard:hover {{
                background: {BG_CARD_HOVER};
                border-color: {self.model_info['color']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        
        # 标题行
        title_row = QHBoxLayout()
        icon = QLabel(self.model_info['icon'])
        icon.setStyleSheet(f'font-size: 20px;')
        title_row.addWidget(icon)
        
        title_col = QVBoxLayout()
        name = QLabel(self.model_info['name'])
        name.setStyleSheet(f'color: {self.model_info["color"]}; font-size: 14px; font-weight: 700;')
        title_col.addWidget(name)
        subtitle = QLabel(self.model_info['subtitle'])
        subtitle.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px;')
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col)
        title_row.addStretch()
        layout.addLayout(title_row)
        
        # 描述
        desc = QLabel(self.model_info['desc'])
        desc.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 10px;')
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 标签
        tag_row = QHBoxLayout()
        for tag in self.model_info['tags']:
            tag_label = QLabel(tag)
            tag_label.setStyleSheet(f"""
                background: {BG_INTERACTIVE};
                color: {TEXT_SECONDARY};
                font-size: 9px;
                padding: 2px 6px;
                border-radius: 3px;
                border: 1px solid {BORDER_SOFT};
            """)
            tag_row.addWidget(tag_label)
        tag_row.addStretch()
        layout.addLayout(tag_row)
    
    def set_active(self, active: bool):
        self.active = active
        if active:
            self.setStyleSheet(f"""
                ModelCard {{
                    background: {BG_CARD_ACTIVE};
                    border: 2px solid {self.model_info['color']};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                ModelCard {{
                    background: {BG_CARD};
                    border: 1px solid {BORDER};
                    border-radius: 10px;
                }}
                ModelCard:hover {{
                    background: {BG_CARD_HOVER};
                    border-color: {self.model_info['color']};
                }}
            """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model_key)
        super().mousePressEvent(event)


# ============================================================
# 建模画布 - 流程图节点
# ============================================================
class FlowNode(QFrame):
    """流程图节点"""
    
    clicked = pyqtSignal(str)
    
    def __init__(self, node_id: str, name: str, icon: str, color: str,
                 status: str = 'idle', parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.name = name
        self.icon = icon
        self.color = color
        self.status = status
        self._init_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def _init_ui(self):
        self.setFixedSize(130, 70)
        self.setStyleSheet(f"""
            FlowNode {{
                background: {BG_CARD};
                border: 2px solid {self.color};
                border-radius: 8px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        
        row = QHBoxLayout()
        icon_label = QLabel(self.icon)
        icon_label.setStyleSheet('font-size: 16px;')
        row.addWidget(icon_label)
        
        name_label = QLabel(self.name)
        name_label.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600;')
        row.addWidget(name_label)
        row.addStretch()
        layout.addLayout(row)
        
        status_label = QLabel(self._status_text())
        status_label.setStyleSheet(f'color: {self._status_color()}; font-size: 9px;')
        layout.addWidget(status_label)
    
    def _status_text(self):
        return {'idle': '待配置', 'ready': '已就绪', 'running': '运行中', 'done': '已完成'}.get(self.status, self.status)
    
    def _status_color(self):
        return {'idle': TEXT_MUTED, 'ready': STATUS_INFO, 'running': STATUS_WARNING, 'done': STATUS_SUCCESS}.get(self.status, TEXT_MUTED)
    
    def set_status(self, status: str):
        self.status = status
        # 更新状态标签
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                if item.widget().text() in ('待配置', '已就绪', '运行中', '已完成'):
                    item.widget().setText(self._status_text())
                    item.widget().setStyleSheet(f'color: {self._status_color()}; font-size: 9px;')
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.node_id)
        super().mousePressEvent(event)


# ============================================================
# 权重滑块组件
# ============================================================
class WeightSlider(QWidget):
    """权重调节滑块"""
    
    valueChanged = pyqtSignal(str, int)
    
    def __init__(self, label: str, key: str, value: int, color: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.color = color
        self._init_ui(label, value)
    
    def _init_ui(self, label: str, value: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        name_label = QLabel(label)
        name_label.setFixedWidth(80)
        name_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        layout.addWidget(name_label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 50)
        self.slider.setValue(value)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {BG_INTERACTIVE}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {self.color}; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.color}; border-radius: 2px;
            }}
        """)
        self.slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self.slider, stretch=1)
        
        self.value_label = QLabel(f'{value}分')
        self.value_label.setFixedWidth(40)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(f'color: {self.color}; font-size: 12px; font-weight: 700;')
        layout.addWidget(self.value_label)
    
    def _on_changed(self, val):
        self.value_label.setText(f'{val}分')
        self.valueChanged.emit(self.key, val)
    
    def value(self):
        return self.slider.value()


# ============================================================
# 主建模工作台
# ============================================================
class ModelingWorkbench(QWidget):
    """量化策略建模工作台"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_models = {'limit_pullback': True, 'box_breakout': True, 'volume_breakout': True}
        self.weights = {
            'main_force': 40, 'volume_price': 20, 'trend_ma': 15,
            'limit_gene': 10, 'tech_confirm': 10, 'market_env': 5,
        }
        self.model_cards = {}
        self.flow_nodes = {}
        self.weight_sliders = {}
        self._init_ui()
        self._load_config()
    
    def _init_ui(self):
        self.setStyleSheet(f"""
            ModelingWorkbench {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ===== 顶部标题栏 =====
        main_layout.addWidget(self._create_title_bar())
        
        # ===== 三栏主体 =====
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{ background: {BORDER}; width: 1px; }}
        """)
        
        splitter.addWidget(self._create_model_library())
        splitter.addWidget(self._create_canvas())
        splitter.addWidget(self._create_preview())
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([260, 560, 320])
        
        main_layout.addWidget(splitter, stretch=1)
        
        # ===== 底部状态栏 =====
        main_layout.addWidget(self._create_status_bar())
    
    # ---------- 顶部标题栏 ----------
    def _create_title_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border-bottom: 1px solid {BORDER};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)
        
        # 标题
        title_col = QVBoxLayout()
        title_row = QHBoxLayout()
        icon = QLabel('🧩')
        icon.setStyleSheet('font-size: 18px;')
        title_row.addWidget(icon)
        title = QLabel('量化策略建模工作台')
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 700;')
        title_row.addWidget(title)
        title_col.addLayout(title_row)
        
        subtitle = QLabel('主力行为模式识别 · 可视化建模 · 实时预览')
        subtitle.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px;')
        title_col.addWidget(subtitle)
        layout.addLayout(title_col)
        
        layout.addStretch()
        
        # 模型名称输入
        self.model_name_input = QLineEdit('主力行为选股模型_v1')
        self.model_name_input.setFixedWidth(200)
        self.model_name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SOFT}; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_BLUE}; }}
        """)
        layout.addWidget(self.model_name_input)
        
        # 按钮组
        for text, color, slot in [
            ('💾 保存', BG_INTERACTIVE, self._save_model),
            ('▶ 运行扫描', STATUS_SUCCESS, self._run_scan),
            ('📊 回测', ACCENT_BLUE, self._run_backtest),
            ('📤 导出', BG_INTERACTIVE, self._export_model),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color}; color: {TEXT_PRIMARY};
                    border: 1px solid {BORDER_STRONG if color == BG_INTERACTIVE else color};
                    border-radius: 6px; padding: 0 14px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            """)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        
        return bar
    
    # ---------- 左侧：模型库 ----------
    def _create_model_library(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(f'QFrame {{ background: {BG_SIDEBAR}; }}')
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # 标题
        header = QLabel('📚 模型库')
        header.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;')
        layout.addWidget(header)
        
        desc = QLabel('点击卡片启用/禁用模型\n拖拽到画布可调整顺序')
        desc.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px;')
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 三个模型卡片
        for key in ['limit_pullback', 'box_breakout', 'volume_breakout']:
            card = ModelCard(key)
            card.clicked.connect(self._toggle_model)
            card.set_active(self.active_models.get(key, True))
            self.model_cards[key] = card
            layout.addWidget(card)
        
        layout.addSpacing(8)
        
        # 扫描参数
        scan_group = QGroupBox('⚙️ 扫描参数')
        scan_group.setStyleSheet(f"""
            QGroupBox {{
                color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
                border: 1px solid {BORDER}; border-radius: 8px;
                margin-top: 10px; padding-top: 8px;
                background: {BG_CARD};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
        """)
        scan_layout = QFormLayout()
        scan_layout.setSpacing(8)
        
        self.min_score_spin = QDoubleSpinBox()
        self.min_score_spin.setRange(0, 100)
        self.min_score_spin.setValue(60)
        self.min_score_spin.setSuffix(' 分')
        self.min_score_spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px;')
        scan_layout.addRow('最低评分:', self.min_score_spin)
        
        self.scan_mode_combo = QComboBox()
        self.scan_mode_combo.addItems(['快速扫描', '深度扫描', '全市场扫描'])
        self.scan_mode_combo.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px;')
        scan_layout.addRow('扫描模式:', self.scan_mode_combo)
        
        self.max_stocks_spin = QSpinBox()
        self.max_stocks_spin.setRange(0, 5000)
        self.max_stocks_spin.setValue(0)
        self.max_stocks_spin.setSpecialValueText('不限制')
        self.max_stocks_spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px;')
        scan_layout.addRow('最大数量:', self.max_stocks_spin)
        
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)
        
        layout.addStretch()
        return panel
    
    # ---------- 中间：建模画布 ----------
    def _create_canvas(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(f'QFrame {{ background: {BG_CONTAINER}; }}')
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 画布标签页
        self.canvas_tabs = QTabWidget()
        self.canvas_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {BG_CONTAINER}; }}
            QTabBar::tab {{
                background: {BG_PANEL}; color: {TEXT_MUTED};
                padding: 8px 20px; font-size: 12px; font-weight: 600;
                border: none; border-right: 1px solid {BORDER};
            }}
            QTabBar::tab:selected {{
                background: {BG_CONTAINER}; color: {ACCENT_BLUE};
                border-bottom: 2px solid {ACCENT_BLUE};
            }}
        """)
        
        self.canvas_tabs.addTab(self._create_flow_canvas(), '🔄 建模流程')
        self.canvas_tabs.addTab(self._create_weight_canvas(), '⚖️ 评分权重')
        self.canvas_tabs.addTab(self._create_param_canvas(), '📝 模型参数')
        
        layout.addWidget(self.canvas_tabs)
        return panel
    
    def _create_flow_canvas(self) -> QWidget:
        canvas = QWidget()
        canvas.setStyleSheet(f'background: {BG_CONTAINER};')
        
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)
        
        # 标题
        title = QLabel('建模流程画布')
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700; margin-bottom: 16px;')
        layout.addWidget(title)
        
        # 流程图区域
        flow_area = QScrollArea()
        flow_area.setWidgetResizable(True)
        flow_area.setStyleSheet(f'QScrollArea {{ background: transparent; border: none; }}')
        
        flow_widget = QWidget()
        flow_layout = QVBoxLayout(flow_widget)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        flow_layout.setSpacing(0)
        
        # 节点定义
        nodes = [
            ('input', '全市场输入', '📥', ACCENT_CYAN, 'ready'),
            ('prescreen', '强势股初筛', '🔍', ACCENT_BLUE, 'ready'),
            ('model_match', '模型匹配', '🎯', ACCENT_GOLD, 'ready'),
            ('ai_score', 'AI综合评分', '🤖', ACCENT_PURPLE, 'ready'),
            ('output', '股票池输出', '📤', ACCENT_GREEN, 'ready'),
        ]
        
        for i, (nid, name, icon, color, status) in enumerate(nodes):
            # 节点行
            node_row = QHBoxLayout()
            node_row.addStretch()
            
            node = FlowNode(nid, name, icon, color, status)
            node.clicked.connect(self._on_flow_node_clicked)
            self.flow_nodes[nid] = node
            node_row.addWidget(node)
            node_row.addStretch()
            flow_layout.addLayout(node_row)
            
            # 连接线
            if i < len(nodes) - 1:
                connector = QLabel('▼')
                connector.setAlignment(Qt.AlignmentFlag.AlignCenter)
                connector.setStyleSheet(f'color: {BORDER_STRONG}; font-size: 14px; padding: 4px 0;')
                flow_layout.addWidget(connector)
        
        flow_area.setWidget(flow_widget)
        layout.addWidget(flow_area, stretch=1)
        
        return canvas
    
    def _create_weight_canvas(self) -> QWidget:
        canvas = QWidget()
        canvas.setStyleSheet(f'background: {BG_CONTAINER};')
        
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel('AI评分权重配置')
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700;')
        layout.addWidget(title)
        
        desc = QLabel('总分100分，拖动滑块实时调整各维度权重')
        desc.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px;')
        layout.addWidget(desc)
        
        # 权重配置卡片
        weight_card = QFrame()
        weight_card.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD}; border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        weight_layout = QVBoxLayout(weight_card)
        weight_layout.setContentsMargins(16, 16, 16, 16)
        weight_layout.setSpacing(12)
        
        weight_configs = [
            ('主力行为结构', 'main_force', 40, ACCENT_GOLD),
            ('量价关系', 'volume_price', 20, ACCENT_GREEN),
            ('趋势均线', 'trend_ma', 15, ACCENT_BLUE),
            ('涨停强势基因', 'limit_gene', 10, ACCENT_RED),
            ('技术指标确认', 'tech_confirm', 10, ACCENT_PURPLE),
            ('市场环境', 'market_env', 5, ACCENT_CYAN),
        ]
        
        for label, key, default, color in weight_configs:
            slider = WeightSlider(label, key, self.weights.get(key, default), color)
            slider.valueChanged.connect(self._on_weight_changed)
            self.weight_sliders[key] = slider
            weight_layout.addWidget(slider)
        
        # 总分显示
        total_row = QHBoxLayout()
        total_label = QLabel('总分:')
        total_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600;')
        total_row.addWidget(total_label)
        
        self.total_weight_label = QLabel('100分')
        self.total_weight_label.setStyleSheet(f'color: {STATUS_SUCCESS}; font-size: 16px; font-weight: 700;')
        total_row.addWidget(self.total_weight_label)
        total_row.addStretch()
        
        self.weight_warning = QLabel('')
        self.weight_warning.setStyleSheet(f'color: {STATUS_WARNING}; font-size: 11px;')
        total_row.addWidget(self.weight_warning)
        
        weight_layout.addLayout(total_row)
        
        layout.addWidget(weight_card)
        layout.addStretch()
        
        return canvas
    
    def _create_param_canvas(self) -> QWidget:
        canvas = QWidget()
        canvas.setStyleSheet(f'background: {BG_CONTAINER};')
        
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        
        title = QLabel('模型参数配置')
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700;')
        layout.addWidget(title)
        
        # 参数标签页
        param_tabs = QTabWidget()
        param_tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {BG_CARD}; }}
            QTabBar::tab {{
                background: {BG_PANEL}; color: {TEXT_MUTED};
                padding: 6px 14px; font-size: 11px;
                border: 1px solid {BORDER}; border-bottom: none;
            }}
            QTabBar::tab:selected {{ background: {BG_CARD}; color: {ACCENT_GOLD}; }}
        """)
        
        # 涨停回调参数
        param_tabs.addTab(self._create_model_params('limit_pullback'), '📉 涨停回调')
        param_tabs.addTab(self._create_model_params('box_breakout'), '📦 箱体突破')
        param_tabs.addTab(self._create_model_params('volume_breakout'), '🚀 量价突破')
        
        layout.addWidget(param_tabs)
        layout.addStretch()
        
        return canvas
    
    def _create_model_params(self, model_key: str) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f'background: {BG_CARD};')
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        params = {
            'limit_pullback': [
                ('涨停回看天数', 30, 5, 120),
                ('回调最大幅度(%)', 25, 5, 50),
                ('缩量阈值(倍)', 0.6, 0.1, 1.5),
                ('支撑均线', 'MA5', ['MA5', 'MA10', 'MA20']),
                ('调整最小天数', 3, 1, 20),
            ],
            'box_breakout': [
                ('箱体最小天数', 10, 5, 60),
                ('箱体振幅(%)', 15, 5, 40),
                ('缩量阈值(倍)', 0.7, 0.1, 1.5),
                ('突破确认(%)', 2, 0.5, 10),
                ('均线粘合阈值(%)', 3, 1, 10),
            ],
            'volume_breakout': [
                ('筑底最小天数', 15, 5, 60),
                ('极限缩量阈值(倍)', 0.4, 0.1, 1.0),
                ('量价齐升天数', 3, 1, 10),
                ('突破放量倍数', 2.0, 1.0, 5.0),
                ('回踩确认天数', 3, 1, 10),
            ],
        }
        
        for param in params.get(model_key, []):
            name = param[0]
            default = param[1]
            if isinstance(default, str):
                # 下拉选择类型: (name, default, [options])
                options = param[2] if len(param) > 2 else [default]
                combo = QComboBox()
                combo.addItems(options)
                combo.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 4px;')
                layout.addRow(f'{name}:', combo)
            elif isinstance(default, int) and not isinstance(default, bool):
                # 整数类型: (name, default, min, max)
                min_val = int(param[2]) if len(param) > 2 else 0
                max_val = int(param[3]) if len(param) > 3 else 100
                spin = QSpinBox()
                spin.setRange(min_val, max_val)
                spin.setValue(default)
                spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 4px;')
                layout.addRow(f'{name}:', spin)
            else:
                # 浮点数类型: (name, default, min, max)
                min_val = param[2] if len(param) > 2 else 0.0
                max_val = param[3] if len(param) > 3 else 100.0
                spin = QDoubleSpinBox()
                spin.setRange(min_val, max_val)
                spin.setValue(default)
                spin.setSingleStep(0.1)
                spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 4px;')
                layout.addRow(f'{name}:', spin)
        
        return widget
    
    # ---------- 右侧：实时预览 ----------
    def _create_preview(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(f'QFrame {{ background: {BG_PANEL}; }}')
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # 标题
        header_row = QHBoxLayout()
        title = QLabel('👁 实时预览')
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 700;')
        header_row.addWidget(title)
        header_row.addStretch()
        
        self.preview_status = QLabel('待运行')
        self.preview_status.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px;')
        header_row.addWidget(self.preview_status)
        layout.addLayout(header_row)
        
        # 统计卡片
        stats_row = QHBoxLayout()
        for label, key, color in [
            ('候选股', 'candidates', ACCENT_BLUE),
            ('S/A级', 'high_grade', ACCENT_GOLD),
            ('平均评分', 'avg_score', ACCENT_GREEN),
        ]:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {BG_CARD}; border: 1px solid {BORDER};
                    border-radius: 8px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(2)
            
            val_label = QLabel('--')
            val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_label.setStyleSheet(f'color: {color}; font-size: 18px; font-weight: 700;')
            card_layout.addWidget(val_label)
            
            name_label = QLabel(label)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 9px;')
            card_layout.addWidget(name_label)
            
            stats_row.addWidget(card)
            setattr(self, f'stats_{key}', val_label)
        
        layout.addLayout(stats_row)
        
        # 评分分布
        dist_group = QGroupBox('📊 评分分布')
        dist_group.setStyleSheet(f"""
            QGroupBox {{
                color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
                border: 1px solid {BORDER}; border-radius: 8px;
                margin-top: 8px; background: {BG_CARD};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
        """)
        dist_layout = QVBoxLayout(dist_group)
        dist_layout.setContentsMargins(10, 12, 10, 10)
        dist_layout.setSpacing(4)
        
        self.dist_bars = {}
        for grade, color in [('S级(90+)', ACCENT_GOLD), ('A级(80-90)', ACCENT_GREEN),
                              ('B级(70-80)', ACCENT_BLUE), ('C级(60-70)', TEXT_MUTED)]:
            bar_row = QHBoxLayout()
            label = QLabel(grade)
            label.setFixedWidth(65)
            label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 10px;')
            bar_row.addWidget(label)
            
            bar_bg = QFrame()
            bar_bg.setFixedHeight(14)
            bar_bg.setStyleSheet(f'background: {BG_INTERACTIVE}; border-radius: 3px;')
            bar_inner = QFrame(bar_bg)
            bar_inner.setFixedHeight(14)
            bar_inner.setStyleSheet(f'background: {color}; border-radius: 3px;')
            bar_inner.setFixedWidth(0)
            bar_row.addWidget(bar_bg, stretch=1)
            
            count_label = QLabel('0')
            count_label.setFixedWidth(30)
            count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            count_label.setStyleSheet(f'color: {color}; font-size: 10px; font-weight: 600;')
            bar_row.addWidget(count_label)
            
            dist_layout.addLayout(bar_row)
            self.dist_bars[grade] = (bar_inner, count_label, bar_bg)
        
        layout.addWidget(dist_group)
        
        # 候选股票列表
        pool_group = QGroupBox('🔥 候选股票TOP10')
        pool_group.setStyleSheet(f"""
            QGroupBox {{
                color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
                border: 1px solid {BORDER}; border-radius: 8px;
                margin-top: 8px; background: {BG_CARD};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
        """)
        pool_layout = QVBoxLayout(pool_group)
        pool_layout.setContentsMargins(4, 10, 4, 4)
        
        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(5)
        self.pool_table.setHorizontalHeaderLabels(['代码', '名称', '评分', '模型', '信号'])
        self.pool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pool_table.horizontalHeader().setDefaultSectionSize(50)
        self.pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pool_table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CONTAINER}; color: {TEXT_PRIMARY};
                gridline-color: {BORDER}; border: none;
                font-size: 10px;
            }}
            QHeaderView::section {{
                background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY};
                padding: 4px; border: none; font-size: 10px; font-weight: 600;
            }}
            QTableWidget::item {{ padding: 3px; border-bottom: 1px solid {BORDER}; }}
        """)
        self.pool_table.setFixedHeight(200)
        pool_layout.addWidget(self.pool_table)
        
        layout.addWidget(pool_group, stretch=1)
        
        return panel
    
    # ---------- 底部状态栏 ----------
    def _create_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {BG_PANEL};
                border-top: 1px solid {BORDER};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(16)
        
        self.status_model = QLabel('模型: 主力行为选股模型_v1')
        self.status_model.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 10px;')
        layout.addWidget(self.status_model)
        
        self.status_active = QLabel('已启用: 3/3 模型')
        self.status_active.setStyleSheet(f'color: {STATUS_SUCCESS}; font-size: 10px;')
        layout.addWidget(self.status_active)
        
        layout.addStretch()
        
        self.status_weights = QLabel('权重: 100/100')
        self.status_weights.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 10px;')
        layout.addWidget(self.status_weights)
        
        self.status_conn = QLabel('● 数据就绪')
        self.status_conn.setStyleSheet(f'color: {STATUS_SUCCESS}; font-size: 10px;')
        layout.addWidget(self.status_conn)
        
        return bar
    
    # ---------- 事件处理 ----------
    def _toggle_model(self, model_key: str):
        self.active_models[model_key] = not self.active_models.get(model_key, True)
        if model_key in self.model_cards:
            self.model_cards[model_key].set_active(self.active_models[model_key])
        
        active_count = sum(1 for v in self.active_models.values() if v)
        self.status_active.setText(f'已启用: {active_count}/3 模型')
        self.status_active.setStyleSheet(f'color: {STATUS_SUCCESS if active_count > 0 else STATUS_ERROR}; font-size: 10px;')
    
    def _on_flow_node_clicked(self, node_id: str):
        node_names = {
            'input': '全市场输入', 'prescreen': '强势股初筛',
            'model_match': '模型匹配', 'ai_score': 'AI综合评分',
            'output': '股票池输出',
        }
        QMessageBox.information(self, f'节点配置 - {node_names.get(node_id, node_id)}',
                                f'点击配置「{node_names.get(node_id, node_id)}」节点参数\n\n'
                                f'（此处可展开详细参数配置面板）')
    
    def _on_weight_changed(self, key: str, value: int):
        self.weights[key] = value
        total = sum(self.weights.values())
        self.total_weight_label.setText(f'{total}分')
        self.status_weights.setText(f'权重: {total}/100')
        
        if total > 100:
            self.total_weight_label.setStyleSheet(f'color: {STATUS_ERROR}; font-size: 16px; font-weight: 700;')
            self.weight_warning.setText('⚠ 超过100分')
        elif total < 100:
            self.total_weight_label.setStyleSheet(f'color: {STATUS_WARNING}; font-size: 16px; font-weight: 700;')
            self.weight_warning.setText('⚠ 不足100分')
        else:
            self.total_weight_label.setStyleSheet(f'color: {STATUS_SUCCESS}; font-size: 16px; font-weight: 700;')
            self.weight_warning.setText('✓ 标准')
    
    def _save_model(self):
        config = {
            'name': self.model_name_input.text(),
            'active_models': self.active_models,
            'weights': self.weights,
            'min_score': self.min_score_spin.value(),
            'scan_mode': self.scan_mode_combo.currentText(),
            'max_stocks': self.max_stocks_spin.value(),
        }
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'modeling_workbench.json'
        )
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, '保存成功', f'模型配置已保存到:\n{config_path}')
    
    def _load_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'modeling_workbench.json'
        )
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if 'name' in config:
                    self.model_name_input.setText(config['name'])
                if 'weights' in config:
                    self.weights.update(config['weights'])
                if 'min_score' in config:
                    self.min_score_spin.setValue(config['min_score'])
            except Exception:
                pass
    
    def _run_scan(self):
        active_count = sum(1 for v in self.active_models.values() if v)
        if active_count == 0:
            QMessageBox.warning(self, '提示', '请至少启用一个模型')
            return
        
        self.preview_status.setText('扫描中...')
        self.preview_status.setStyleSheet(f'color: {STATUS_WARNING}; font-size: 10px;')
        
        # 更新流程节点状态
        for i, nid in enumerate(['input', 'prescreen', 'model_match', 'ai_score', 'output']):
            if nid in self.flow_nodes:
                self.flow_nodes[nid].set_status('running')
                QApplication.processEvents()
        
        # 模拟扫描结果（实际应接入策略引擎）
        self._simulate_scan_results()
        
        for nid in ['input', 'prescreen', 'model_match', 'ai_score', 'output']:
            if nid in self.flow_nodes:
                self.flow_nodes[nid].set_status('done')
        
        self.preview_status.setText('扫描完成')
        self.preview_status.setStyleSheet(f'color: {STATUS_SUCCESS}; font-size: 10px;')
    
    def _simulate_scan_results(self):
        """模拟扫描结果预览（实际应接入 strategy_main_force_behavior）"""
        import random
        random.seed(42)
        
        mock_stocks = [
            ('000001', '平安银行', '涨停回调', '5日线低吸'),
            ('000002', '万科A', '箱体突破', '平台蓄势'),
            ('000063', '中兴通讯', '量价突破', '主力启动'),
            ('000100', 'TCL科技', '涨停回调', '缩量洗盘'),
            ('000333', '美的集团', '箱体突破', '二次启动'),
            ('000651', '格力电器', '量价突破', '二次确认'),
            ('000725', '京东方A', '涨停回调', '强势洗盘'),
            ('000858', '五粮液', '箱体突破', '突破确认'),
            ('002415', '海康威视', '量价突破', '量价齐升'),
            ('002594', '比亚迪', '涨停回调', '缩量低吸'),
        ]
        
        self.pool_table.setRowCount(0)
        grades = {'S级(90+)': 0, 'A级(80-90)': 0, 'B级(70-80)': 0, 'C级(60-70)': 0}
        total_score = 0
        
        for i, (code, name, model, signal) in enumerate(mock_stocks):
            score = random.randint(62, 95)
            total_score += score
            
            if score >= 90: grades['S级(90+)'] += 1
            elif score >= 80: grades['A级(80-90)'] += 1
            elif score >= 70: grades['B级(70-80)'] += 1
            else: grades['C级(60-70)'] += 1
            
            self.pool_table.insertRow(i)
            for j, text in enumerate([code, name, str(score), model, signal]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 2:
                    color = ACCENT_GOLD if score >= 90 else ACCENT_GREEN if score >= 80 else ACCENT_BLUE if score >= 70 else TEXT_MUTED
                    item.setForeground(QColor(color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.pool_table.setItem(i, j, item)
        
        # 更新统计
        self.stats_candidates.setText(str(len(mock_stocks)))
        self.stats_high_grade.setText(str(grades['S级(90+)'] + grades['A级(80-90)']))
        self.stats_avg_score.setText(f'{total_score / len(mock_stocks):.1f}')
        
        # 更新分布条
        for grade, count in grades.items():
            bar_inner, count_label, bar_bg = self.dist_bars[grade]
            pct = count / len(mock_stocks)
            bar_inner.setFixedWidth(int(bar_bg.width() * pct) if bar_bg.width() > 0 else int(100 * pct))
            count_label.setText(str(count))
    
    def _run_backtest(self):
        QMessageBox.information(self, '回测', '回测功能开发中\n\n将接入回测系统，基于当前模型参数进行历史回测。')
    
    def _export_model(self):
        QMessageBox.information(self, '导出', '模型导出功能开发中\n\n支持导出为JSON/Python策略文件，可直接接入回测系统。')
