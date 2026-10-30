# -*- coding: utf-8 -*-
"""
信号参数配置面板
支持每个信号的参数手动填写和修改
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QDoubleSpinBox, QPushButton, QListWidget, QListWidgetItem,
    QScrollArea, QGroupBox, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE, BG_CONTAINER,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    ACCENT_PURPLE, STATUS_SUCCESS, STATUS_INFO,
)
from strategy.signal_config import SignalConfig


class SignalConfigPanel(QWidget):
    """信号参数配置面板"""

    config_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = SignalConfig()
        self._current_signal = None
        self._param_widgets = {}
        self._init_ui()
        self._load_signal_list()

    def _init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QListWidget {{
                background: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QListWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background: {STATUS_INFO};
                color: {TEXT_PRIMARY};
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
            }}
            QGroupBox {{
                color: {ACCENT_GOLD};
                border: 1px solid {BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
            }}
            QDoubleSpinBox {{
                background: {BG_INTERACTIVE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SOFT};
                border-radius: 6px;
                padding: 4px;
            }}
            QPushButton {{
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }}
        """)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 左侧：信号列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel('信号列表'))
        self.signal_list = QListWidget()
        self.signal_list.setStyleSheet(f"""
            QListWidget {{ background: {BG_PANEL}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; }}
            QListWidget::item {{ padding: 6px; }}
            QListWidget::item:selected {{ background: {STATUS_INFO}; }}
        """)
        self.signal_list.currentItemChanged.connect(self._on_signal_selected)
        left_layout.addWidget(self.signal_list)

        # 底部按钮
        btn_layout = QHBoxLayout()
        reset_all_btn = QPushButton('全部重置')
        reset_all_btn.setStyleSheet(f'background: {BORDER_STRONG}; color: {TEXT_PRIMARY}; padding: 4px;')
        reset_all_btn.clicked.connect(self._reset_all)
        btn_layout.addWidget(reset_all_btn)
        left_layout.addLayout(btn_layout)

        # 右侧：参数编辑
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 信号名称和启用状态
        header = QHBoxLayout()
        self.signal_name_label = QLabel('选择一个信号')
        self.signal_name_label.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 14px; font-weight: bold;')
        header.addWidget(self.signal_name_label)
        header.addStretch()

        self.enable_check = QCheckBox('启用')
        self.enable_check.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.enable_check.stateChanged.connect(self._on_enable_changed)
        header.addWidget(self.enable_check)
        right_layout.addLayout(header)

        # 参数滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")

        self.params_widget = QWidget()
        self.params_layout = QVBoxLayout(self.params_widget)
        self.params_layout.setSpacing(8)
        self.params_layout.addStretch()
        scroll.setWidget(self.params_widget)
        right_layout.addWidget(scroll, stretch=1)

        # 底部按钮
        bottom_btn = QHBoxLayout()
        bottom_btn.addStretch()

        reset_btn = QPushButton('重置此信号')
        reset_btn.setStyleSheet(f'background: {BORDER_STRONG}; color: {TEXT_PRIMARY}; padding: 6px 12px;')
        reset_btn.clicked.connect(self._reset_current)
        bottom_btn.addWidget(reset_btn)

        save_btn = QPushButton('💾 保存配置')
        save_btn.setStyleSheet(f'background: {STATUS_SUCCESS}; color: {TEXT_PRIMARY}; padding: 6px 20px; font-weight: bold;')
        save_btn.clicked.connect(self._save_config)
        bottom_btn.addWidget(save_btn)

        right_layout.addLayout(bottom_btn)

        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 400])
        main_layout.addWidget(splitter)

    def _load_signal_list(self):
        """加载信号列表"""
        self.signal_list.clear()
        signals = self.config.get_signal_list()
        for sig in signals:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, sig['key'])
            # 显示名称和启用状态
            status = '✅' if sig['enabled'] else '⬜'
            item.setText(f"{status} {sig['name']}")
            self.signal_list.addItem(item)

    def _on_signal_selected(self, current, previous):
        """信号选择变化"""
        if current is None:
            return

        signal_key = current.data(Qt.ItemDataRole.UserRole)
        self._current_signal = signal_key
        self._load_signal_params(signal_key)

    def _load_signal_params(self, signal_key):
        """加载信号参数到UI"""
        sig_config = self.config.get_signal(signal_key)
        self.signal_name_label.setText(sig_config.get('name', signal_key))
        self.enable_check.setChecked(sig_config.get('enabled', True))

        # 清除旧参数
        while self.params_layout.count() > 1:
            item = self.params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._param_widgets = {}

        params = sig_config.get('params', {})
        if not params:
            label = QLabel('此信号无可配置参数')
            label.setStyleSheet(f'color: {TEXT_SECONDARY};')
            self.params_layout.insertWidget(0, label)
            return

        # 参数说明
        desc_label = QLabel('参数说明：可手动修改数值，保存后立即生效')
        desc_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        self.params_layout.insertWidget(0, desc_label)

        # 为每个参数创建输入框
        row = 1
        for param_name, param_value in params.items():
            group = QGroupBox(self._get_param_desc(param_name))
            group.setStyleSheet(f"""
                QGroupBox {{ color: {ACCENT_GOLD}; border: 1px solid {BORDER}; border-radius: 4px;
                           margin-top: 8px; padding-top: 8px; }}
            """)
            group_layout = QHBoxLayout(group)

            group_layout.addWidget(QLabel(f'{param_name}:'))

            spin = QDoubleSpinBox()
            spin.setRange(-10000, 10000)
            spin.setValue(float(param_value))
            spin.setDecimals(4)
            spin.setSingleStep(0.01)
            spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; padding: 4px;')
            spin.setMinimumWidth(120)
            group_layout.addWidget(spin)

            # 显示当前值
            current_label = QLabel(f'当前: {param_value}')
            current_label.setStyleSheet(f'color: {TEXT_SECONDARY};')
            group_layout.addWidget(current_label)

            group_layout.addStretch()
            self.params_layout.insertWidget(row, group)
            self._param_widgets[param_name] = spin
            row += 1

    def _get_param_desc(self, param_name):
        """获取参数中文说明"""
        desc_map = {
            'days': '横盘天数',
            'amplitude_max': '最大振幅(%)',
            'vol_shrink': '成交量萎缩比例',
            'angle_min': '最小角度',
            'distance_pct': '距离百分比(%)',
            'yang_min_pct': '阳线最小涨幅(%)',
            'ratio_min': '最小倍数',
            'lookback_days': '回看天数',
            'big_yang_min': '大阳线最小涨幅(%)',
            'big_yang_max': '大阳线最大涨幅(%)',
            'vol_increase': '放量倍数',
            'pullback_dist': '回踩距离(%)',
            'golden_lookback': '金叉回看天数',
            'near_ma_pct': '接近均线百分比(%)',
            'diff_min': '距离最小值(元)',
            'diff_max': '距离最大值(元)',
            'adjust_days': '连续调整天数',
            'mild_drop_max': '温和调整最大跌幅(元)',
            'turnover_min': '最小换手率(%)',
            'turnover_max': '最大换手率(%)',
            'dist_min': '距离最小值(元)',
            'dist_max': '距离最大值(元)',
            'lower_shadow_min': '长下影线最小值(元)',
        }
        return desc_map.get(param_name, param_name)

    def _on_enable_changed(self, state):
        """启用状态变化"""
        if self._current_signal:
            enabled = (state == Qt.CheckState.Checked.value)
            self.config.set_enabled(self._current_signal, enabled)
            # 更新列表显示
            current_item = self.signal_list.currentItem()
            if current_item:
                sig_name = self.config.get_signal(self._current_signal).get('name', '')
                status = '✅' if enabled else '⬜'
                current_item.setText(f"{status} {sig_name}")

    def _save_config(self):
        """保存配置"""
        if not self._current_signal:
            QMessageBox.warning(self, '提示', '请先选择一个信号')
            return

        # 收集参数
        params = {}
        for param_name, spin in self._param_widgets.items():
            params[param_name] = spin.value()

        # 保存
        for param_name, value in params.items():
            self.config.set_param(self._current_signal, param_name, value)

        self.config_saved.emit()
        QMessageBox.information(self, '保存成功', f'信号"{self.signal_name_label.text()}"参数已保存\n下次扫描立即生效')

        # 重新加载显示
        self._load_signal_params(self._current_signal)

    def _reset_current(self):
        """重置当前信号"""
        if not self._current_signal:
            return

        reply = QMessageBox.question(self, '确认', f'确定重置"{self.signal_name_label.text()}"为默认参数？',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.config.reset_to_default(self._current_signal)
            self._load_signal_params(self._current_signal)
            self._load_signal_list()
            QMessageBox.information(self, '重置成功', '已恢复默认参数')

    def _reset_all(self):
        """全部重置"""
        reply = QMessageBox.question(self, '确认', '确定重置所有信号为默认参数？',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.config.reset_to_default()
            self._load_signal_list()
            if self._current_signal:
                self._load_signal_params(self._current_signal)
            QMessageBox.information(self, '重置成功', '所有信号已恢复默认参数')
