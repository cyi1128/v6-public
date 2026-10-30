# -*- coding: utf-8 -*-
"""
皮肤管理器
支持14套主题切换：
深色终端、深蓝科技、黑金高端、护眼绿、
冰川蓝、银灰科技、暗夜蓝、极光青、深空灰、赛博紫、海洋蓝绿、
专业金融终端V2、石板蓝
"""

import os
import json
from PyQt6.QtWidgets import QApplication


# 皮肤配置
SKINS = {
    'dark_terminal': {
        'name': '深色终端',
        'desc': '专业量化交易终端风格',
        'colors': {
            'bg_darkest': '#080C12',
            'bg_window': '#0D1117',
            'bg_card': '#161B22',
            'bg_card_hover': '#1C2128',
            'border': '#30363D',
            'border_hover': '#484F58',
            'text_primary': '#FFFFFF',
            'text_secondary': '#8B949E',
            'up': '#F85149',
            'down': '#3FB950',
            'accent': '#F85149',
            'limit_up': '#FFD700',
            'limit_down': '#58A6FF',
        }
    },
    'deep_blue': {
        'name': '深蓝科技',
        'desc': '科技蓝深色主题',
        'colors': {
            'bg_darkest': '#0A0E1A',
            'bg_window': '#0F172A',
            'bg_card': '#1E293B',
            'bg_card_hover': '#273449',
            'border': '#334155',
            'border_hover': '#475569',
            'text_primary': '#F1F5F9',
            'text_secondary': '#94A3B8',
            'up': '#EF4444',
            'down': '#22C55E',
            'accent': '#3B82F6',
            'limit_up': '#FBBF24',
            'limit_down': '#60A5FA',
        }
    },
    'black_gold': {
        'name': '黑金高端',
        'desc': '黑金高端商务风格',
        'colors': {
            'bg_darkest': '#0A0A0A',
            'bg_window': '#121212',
            'bg_card': '#1A1A1A',
            'bg_card_hover': '#222222',
            'border': '#333333',
            'border_hover': '#444444',
            'text_primary': '#F5F5F5',
            'text_secondary': '#A0A0A0',
            'up': '#E53935',
            'down': '#43A047',
            'accent': '#FFD700',
            'limit_up': '#FFD700',
            'limit_down': '#64B5F6',
        }
    },
    'eye_green': {
        'name': '护眼绿',
        'desc': '护眼深色主题',
        'colors': {
            'bg_darkest': '#0C120C',
            'bg_window': '#111914',
            'bg_card': '#1A241D',
            'bg_card_hover': '#222E26',
            'border': '#2D3D32',
            'border_hover': '#3D5244',
            'text_primary': '#E8F5E9',
            'text_secondary': '#81C784',
            'up': '#EF5350',
            'down': '#66BB6A',
            'accent': '#66BB6A',
            'limit_up': '#FFCA28',
            'limit_down': '#42A5F5',
        }
    },
    'glacier_blue': {
        'name': '冰川蓝',
        'desc': '冷蓝冰川科技风格',
        'colors': {
            'bg_darkest': '#0A1628',
            'bg_window': '#0F1E35',
            'bg_card': '#162942',
            'bg_card_hover': '#1E3554',
            'border': '#2A4565',
            'border_hover': '#3A5A7E',
            'text_primary': '#E3F2FD',
            'text_secondary': '#90CAF9',
            'up': '#EF5350',
            'down': '#26A69A',
            'accent': '#42A5F5',
            'limit_up': '#FFD54F',
            'limit_down': '#64B5F6',
        }
    },
    'silver_gray': {
        'name': '银灰科技',
        'desc': '银灰极简专业风格',
        'colors': {
            'bg_darkest': '#1A1D23',
            'bg_window': '#22262E',
            'bg_card': '#2B303A',
            'bg_card_hover': '#353B47',
            'border': '#404754',
            'border_hover': '#525A6A',
            'text_primary': '#ECEFF1',
            'text_secondary': '#B0BEC5',
            'up': '#E53935',
            'down': '#43A047',
            'accent': '#78909C',
            'limit_up': '#FFB300',
            'limit_down': '#1E88E5',
        }
    },
    'midnight_blue': {
        'name': '暗夜蓝',
        'desc': '深夜蓝专业交易风格',
        'colors': {
            'bg_darkest': '#050D1A',
            'bg_window': '#0A1525',
            'bg_card': '#111E33',
            'bg_card_hover': '#182944',
            'border': '#1F3354',
            'border_hover': '#2A4570',
            'text_primary': '#D6E4F0',
            'text_secondary': '#7B9BB8',
            'up': '#FF5252',
            'down': '#00E676',
            'accent': '#2979FF',
            'limit_up': '#FFD740',
            'limit_down': '#40C4FF',
        }
    },
    'aurora_cyan': {
        'name': '极光青',
        'desc': '极光青冷科技风格',
        'colors': {
            'bg_darkest': '#081C1C',
            'bg_window': '#0D2828',
            'bg_card': '#143636',
            'bg_card_hover': '#1B4545',
            'border': '#245555',
            'border_hover': '#2E6B6B',
            'text_primary': '#E0F7FA',
            'text_secondary': '#80DEEA',
            'up': '#FF5252',
            'down': '#69F0AE',
            'accent': '#00BCD4',
            'limit_up': '#FFE082',
            'limit_down': '#80D8FF',
        }
    },
    'deep_space': {
        'name': '深空灰',
        'desc': '深空灰极简科技风格',
        'colors': {
            'bg_darkest': '#0D0F12',
            'bg_window': '#14171C',
            'bg_card': '#1C2026',
            'bg_card_hover': '#252A32',
            'border': '#30363F',
            'border_hover': '#414954',
            'text_primary': '#F0F2F5',
            'text_secondary': '#9BA3AF',
            'up': '#FC4D5E',
            'down': '#2ECC71',
            'accent': '#5D6D7E',
            'limit_up': '#F1C40F',
            'limit_down': '#3498DB',
        }
    },
    'cyber_purple': {
        'name': '赛博紫',
        'desc': '赛博朋克紫蓝科技风格',
        'colors': {
            'bg_darkest': '#0D0A1A',
            'bg_window': '#141025',
            'bg_card': '#1E1833',
            'bg_card_hover': '#282044',
            'border': '#352B55',
            'border_hover': '#463870',
            'text_primary': '#EDE7F6',
            'text_secondary': '#B39DDB',
            'up': '#FF4081',
            'down': '#00E5FF',
            'accent': '#7C4DFF',
            'limit_up': '#FFEA00',
            'limit_down': '#40C4FF',
        }
    },
    'ocean_teal': {
        'name': '海洋蓝绿',
        'desc': '深海蓝绿专业风格',
        'colors': {
            'bg_darkest': '#06121A',
            'bg_window': '#0B1F2A',
            'bg_card': '#112E3D',
            'bg_card_hover': '#173D50',
            'border': '#1E4D63',
            'border_hover': '#286580',
            'text_primary': '#E0F2F1',
            'text_secondary': '#80CBC4',
            'up': '#EF5350',
            'down': '#26A69A',
            'accent': '#00897B',
            'limit_up': '#FFB74D',
            'limit_down': '#4FC3F7',
        }
    },
    'pro_terminal_v2': {
        'name': '专业金融终端V2',
        'desc': '深灰蓝渐变+低饱和科技色（推荐）',
        'colors': {
            'bg_darkest': '#0F1419',
            'bg_window': '#161B22',
            'bg_card': '#1C2330',
            'bg_card_hover': '#242D3D',
            'border': '#2D3748',
            'border_hover': '#3D4A5C',
            'text_primary': '#E2E8F0',
            'text_secondary': '#94A3B8',
            'up': '#F87171',
            'down': '#34D399',
            'accent': '#3B82F6',
            'limit_up': '#FBBF24',
            'limit_down': '#60A5FA',
        }
    },
    'slate_blue': {
        'name': '石板蓝',
        'desc': '石板蓝灰极简专业风格',
        'colors': {
            'bg_darkest': '#0F172A',
            'bg_window': '#1E293B',
            'bg_card': '#273449',
            'bg_card_hover': '#334155',
            'border': '#475569',
            'border_hover': '#64748B',
            'text_primary': '#F1F5F9',
            'text_secondary': '#94A3B8',
            'up': '#EF4444',
            'down': '#22C55E',
            'accent': '#6366F1',
            'limit_up': '#F59E0B',
            'limit_down': '#3B82F6',
        }
    },
}

DEFAULT_SKIN = 'dark_terminal'
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '..', 'skin_config.json')


class SkinManager:
    """皮肤管理器"""

    _instance = None
    _current_skin = DEFAULT_SKIN
    _qss_cache = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """加载皮肤配置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self._current_skin = config.get('skin', DEFAULT_SKIN)
        except Exception:
            self._current_skin = DEFAULT_SKIN

    def _save_config(self):
        """保存皮肤配置"""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'skin': self._current_skin}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def get_skins(cls):
        """获取所有皮肤列表"""
        return [(key, val['name'], val['desc']) for key, val in SKINS.items()]

    @classmethod
    def get_current_skin(cls):
        """获取当前皮肤key"""
        return cls._current_skin

    @classmethod
    def get_current_skin_name(cls):
        """获取当前皮肤名称"""
        return SKINS.get(cls._current_skin, SKINS[DEFAULT_SKIN])['name']

    @classmethod
    def get_colors(cls, skin_key=None):
        """获取指定皮肤的颜色配置"""
        key = skin_key or cls._current_skin
        return SKINS.get(key, SKINS[DEFAULT_SKIN])['colors']

    @classmethod
    def set_skin(cls, skin_key, app=None):
        """切换皮肤"""
        if skin_key not in SKINS:
            return False
        cls._current_skin = skin_key
        cls._qss_cache = {}
        if app is None:
            app = QApplication.instance()
        if app:
            cls.apply_theme(app)
        cls._save_config(cls)
        return True

    @classmethod
    def generate_qss(cls, skin_key=None):
        """根据皮肤颜色生成QSS"""
        colors = cls.get_colors(skin_key)
        c = colors

        qss = f"""
/* ===== 全局 ===== */
QWidget {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    font-family: "Microsoft YaHei", "Segoe UI", "Roboto", sans-serif;
    font-size: 12px;
}}

QMainWindow {{
    background-color: {c['bg_darkest']};
}}

/* ===== 菜单栏 ===== */
QMenuBar {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    border-bottom: 1px solid {c['border']};
    padding: 2px 0px;
    font-size: 12px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 14px;
    border-radius: 6px;
    margin: 2px 2px;
}}

QMenuBar::item:selected {{
    background-color: {c['bg_card_hover']};
    color: {c['accent']};
}}

QMenu {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {c['bg_card_hover']};
    color: {c['accent']};
}}

QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 4px 8px;
}}

/* ===== TabWidget ===== */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    border-radius: 0px;
    background-color: {c['bg_window']};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {c['bg_window']};
    color: {c['text_secondary']};
    padding: 10px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 0px;
    font-size: 12px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {c['bg_card']};
    color: {c['accent']};
    border-bottom: 2px solid {c['accent']};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
}}

/* ===== 表格 ===== */
QTableWidget {{
    background-color: {c['bg_window']};
    alternate-background-color: {c['bg_card']};
    gridline-color: {c['border']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    selection-background-color: {c['bg_card_hover']};
    selection-color: {c['text_primary']};
    outline: none;
}}

QTableWidget::item {{
    padding: 8px 10px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
    border-left: 3px solid {c['accent']};
}}

QTableWidget::item:hover {{
    background-color: {c['bg_card_hover']};
}}

QHeaderView::section {{
    background-color: {c['bg_card']};
    color: {c['text_secondary']};
    padding: 10px 8px;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 2px solid {c['accent']};
    font-weight: 600;
    font-size: 11px;
}}

QHeaderView::section:hover {{
    background-color: {c['bg_card_hover']};
    color: {c['accent']};
}}

/* ===== 按钮 ===== */
QPushButton {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
    font-size: 12px;
}}

QPushButton:hover {{
    background-color: {c['bg_card_hover']};
    border-color: {c['accent']};
    color: {c['accent']};
}}

QPushButton:pressed {{
    background-color: {c['bg_card']};
    padding-top: 8px;
    padding-bottom: 6px;
}}

QPushButton:disabled {{
    color: {c['text_secondary']};
    border-color: {c['border']};
}}

QPushButton[class="primary"] {{
    background-color: {c['accent']};
    color: #FFFFFF;
    border: 1px solid {c['accent']};
    font-weight: 600;
    padding: 7px 18px;
}}

QPushButton[class="primary"]:hover {{
    background-color: {c['border_hover']};
    border-color: {c['border_hover']};
    color: #FFFFFF;
}}

QPushButton[class="success"] {{
    background-color: {c['down']};
    color: #FFFFFF;
    border: 1px solid {c['down']};
    font-weight: 600;
}}

QPushButton[class="success"]:hover {{
    background-color: {c['border_hover']};
    border-color: {c['border_hover']};
}}

QPushButton[class="danger"] {{
    background-color: {c['up']};
    color: #FFFFFF;
    border: 1px solid {c['up']};
    font-weight: 600;
}}

QPushButton[class="danger"]:hover {{
    background-color: {c['border_hover']};
    border-color: {c['border_hover']};
}}

QPushButton[class="secondary"] {{
    background-color: {c['bg_card']};
    color: {c['text_secondary']};
    border: 1px solid {c['border']};
}}

QPushButton[class="secondary"]:hover {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}

/* ===== 输入框 ===== */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: {c['accent']};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['accent']};
}}

/* ===== 下拉框 ===== */
QComboBox {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 5px 8px;
}}

QComboBox:hover {{
    border-color: {c['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    selection-background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background-color: {c['bg_window']};
    width: 6px;
    border-radius: 3px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {c['border']};
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c['accent']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {c['bg_window']};
    height: 6px;
    border-radius: 3px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: {c['border']};
    border-radius: 3px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c['accent']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ===== GroupBox ===== */
QGroupBox {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0px 8px;
    color: {c['accent']};
}}

/* ===== 标签 ===== */
QLabel {{
    background: transparent;
    color: {c['text_primary']};
}}

QLabel[class="title"] {{
    font-size: 16px;
    font-weight: 700;
    color: {c['text_primary']};
}}

QLabel[class="subtitle"] {{
    font-size: 12px;
    color: {c['text_secondary']};
}}

QLabel[class="up"] {{
    color: {c['up']};
    font-weight: 700;
}}

QLabel[class="down"] {{
    color: {c['down']};
    font-weight: 700;
}}

QLabel[class="ai_score"] {{
    color: {c['up']};
    font-size: 20px;
    font-weight: 700;
    font-family: "Consolas", "Courier New", monospace;
}}

QLabel[class="mono"] {{
    font-family: "Consolas", "Courier New", monospace;
}}

QLabel[class="limit_up"] {{
    color: {c['limit_up']};
    font-weight: 700;
}}

QLabel[class="limit_down"] {{
    color: {c['limit_down']};
    font-weight: 700;
}}

/* ===== 状态栏 ===== */
QStatusBar {{
    background-color: {c['bg_darkest']};
    color: {c['text_secondary']};
    border-top: 1px solid {c['border']};
    font-size: 11px;
    padding: 2px 8px;
}}

QStatusBar::item {{
    border: none;
}}

QStatusBar QLabel {{
    color: {c['text_secondary']};
    padding: 0 8px;
}}

/* ===== 分割线 ===== */
QSplitter::handle {{
    background-color: {c['border']};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

/* ===== 复选框/单选框 ===== */
QCheckBox, QRadioButton {{
    color: {c['text_primary']};
    spacing: 6px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {c['border']};
    border-radius: 3px;
    background-color: {c['bg_window']};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
}}

/* ===== 进度条 ===== */
QProgressBar {{
    background-color: {c['bg_window']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    text-align: center;
    color: {c['text_primary']};
    height: 16px;
    font-size: 11px;
}}

QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 5px;
}}

/* ===== ToolTip ===== */
QToolTip {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['accent']};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ===== SpinBox ===== */
QSpinBox, QDoubleSpinBox {{
    background-color: {c['bg_window']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 3px 6px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c['accent']};
}}

/* ===== ListWidget ===== */
QListWidget {{
    background-color: {c['bg_window']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {c['border']};
}}

QListWidget::item:selected {{
    background-color: {c['bg_card_hover']};
    color: {c['text_primary']};
}}

QListWidget::item:hover {{
    background-color: {c['bg_card']};
}}

/* ===== 侧边栏导航 ===== */
QListWidget[class="sidebar"] {{
    background-color: {c['bg_window']};
    border: none;
    border-right: 1px solid {c['border']};
    border-radius: 0px;
    outline: none;
}}

QListWidget[class="sidebar"]::item {{
    padding: 10px 16px;
    border: none;
    border-left: 3px solid transparent;
    color: {c['text_secondary']};
    font-size: 13px;
    font-weight: 500;
}}

QListWidget[class="sidebar"]::item:selected {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border-left: 3px solid {c['accent']};
}}

QListWidget[class="sidebar"]::item:hover {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
}}
"""
        return qss

    @classmethod
    def apply_theme(cls, app=None):
        """应用当前皮肤主题"""
        if app is None:
            app = QApplication.instance()
        if not app:
            return False

        skin_key = cls._current_skin
        if skin_key not in cls._qss_cache:
            cls._qss_cache[skin_key] = cls.generate_qss(skin_key)

        qss = cls._qss_cache[skin_key]
        app.setStyleSheet(qss)
        return True

    @classmethod
    def apply_skin(cls, skin_key, app=None):
        """切换并应用皮肤"""
        return cls.set_skin(skin_key, app)
