# -*- coding: utf-8 -*-
"""
主题管理器
统一管理全局主题的加载和应用
"""

import os
from PyQt6.QtWidgets import QApplication


class ThemeManager:
    """全局主题管理器"""

    _instance = None
    _current_theme = 'dark'
    _qss_cache = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_qss_path(cls):
        """获取QSS文件路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, 'theme', 'global_style.qss')

    @classmethod
    def load_qss(cls):
        """加载全局QSS样式"""
        if cls._qss_cache is not None:
            return cls._qss_cache

        qss_path = cls.get_qss_path()
        if os.path.exists(qss_path):
            with open(qss_path, 'r', encoding='utf-8') as f:
                cls._qss_cache = f.read()
            return cls._qss_cache
        return ''

    @classmethod
    def apply_theme(cls, app):
        """应用主题到应用"""
        qss = cls.load_qss()
        if qss:
            app.setStyleSheet(qss)
            return True
        return False

    @classmethod
    def reload_theme(cls, app=None):
        """重新加载主题（运行时切换）"""
        cls._qss_cache = None
        if app is None:
            app = QApplication.instance()
        if app:
            return cls.apply_theme(app)
        return False

    @classmethod
    def get_colors(cls):
        """获取颜色配置"""
        from ui.theme.theme_colors import (
            BG_DARKEST, BG_WINDOW, BG_CARD, BORDER_DEFAULT,
            TEXT_PRIMARY, TEXT_SECONDARY,
            UP_COLOR, DOWN_COLOR, ACCENT_RED
        )
        return {
            'bg_darkest': BG_DARKEST,
            'bg_window': BG_WINDOW,
            'bg_card': BG_CARD,
            'border': BORDER_DEFAULT,
            'text_primary': TEXT_PRIMARY,
            'text_secondary': TEXT_SECONDARY,
            'up': UP_COLOR,
            'down': DOWN_COLOR,
            'accent': ACCENT_RED,
        }


def apply_global_theme(app):
    """便捷函数：应用全局主题"""
    return ThemeManager.apply_theme(app)
