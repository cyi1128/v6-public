# -*- coding: utf-8 -*-
"""
V6.0 Pro 手动筛选条件设置面板
14种筛选条件，支持保存/加载方案
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QDoubleSpinBox, QComboBox, QPushButton, QScrollArea,
    QGroupBox, QLineEdit, QMessageBox, QInputDialog
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE, BG_CONTAINER,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    ACCENT_PURPLE, STATUS_SUCCESS, STATUS_INFO,
)
from strategy.manual_filter_engine import ManualFilterConfig, PRESET_CONFIGS
import os
import json


class ManualFilterPanel(QWidget):
    """手动筛选条件设置面板"""

    filter_applied = pyqtSignal(object)  # 发送ManualFilterConfig
    filter_cancelled = pyqtSignal()

    # 可选行业列表
    INDUSTRY_OPTIONS = [
        '半导体', '人工智能', '机器人', '新能源', '汽车', '医药',
        '通信', '电子', '计算机', '软件', '互联网', '传媒',
        '化工', '有色金属', '钢铁', '煤炭', '电力', '机械设备',
        '建筑材料', '建筑工程', '家电', '食品饮料', '纺织服装',
        '造纸', '塑料', '橡胶', '医疗器械', '生物制药', '化学制药',
        '元器件', '通信设备', '汽车零部件', '证券', '银行',
        '石油', '公用事业', '交通运输', '房地产', '农林牧渔',
        '商业百货', '旅游酒店', '军工', '环保', '其他'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ManualFilterConfig()
        self._init_ui()
        self._load_saved_configs()

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
            QGroupBox {{
                color: {ACCENT_BLUE};
                font-weight: 700;
                border: 1px solid {BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
            }}
            QComboBox, QLineEdit, QDoubleSpinBox {{
                background: {BG_INTERACTIVE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SOFT};
                border-radius: 6px;
                padding: 4px 6px;
            }}
            QPushButton {{
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }}
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 顶部：方案名称 + 保存/加载
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel('方案名称:'))
        self.name_edit = QLineEdit('未命名方案')
        self.name_edit.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; padding: 4px;')
        top_bar.addWidget(self.name_edit)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem('-- 预设方案 --')
        for name in PRESET_CONFIGS.keys():
            self.preset_combo.addItem(name)
        self.preset_combo.addItem('-- 我的方案 --')
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        top_bar.addWidget(self.preset_combo)

        save_btn = QPushButton('💾 保存')
        save_btn.setStyleSheet(f'background: {STATUS_SUCCESS}; color: {TEXT_PRIMARY}; padding: 4px 12px; border-radius: 3px;')
        save_btn.clicked.connect(self._save_config)
        top_bar.addWidget(save_btn)

        load_btn = QPushButton('📂 加载')
        load_btn.setStyleSheet(f'background: {STATUS_INFO}; color: {TEXT_PRIMARY}; padding: 4px 12px; border-radius: 3px;')
        load_btn.clicked.connect(self._load_config)
        top_bar.addWidget(load_btn)

        top_bar.addSpacing(10)

        # 筛选模式
        top_bar.addWidget(QLabel('模式:'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem('严格模式(全部符合)')
        self.mode_combo.addItem('宽松模式(按命中率排序)')
        self.mode_combo.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; padding: 4px;')
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self.mode_combo)

        self.min_hit_label = QLabel('最低命中率:')
        self.min_hit_label.setStyleSheet(f'color: {TEXT_SECONDARY};')
        self.min_hit_label.setVisible(False)
        top_bar.addWidget(self.min_hit_label)

        self.min_hit_spin = QDoubleSpinBox()
        self.min_hit_spin.setRange(0.1, 1.0)
        self.min_hit_spin.setValue(0.5)
        self.min_hit_spin.setSingleStep(0.1)
        self.min_hit_spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};')
        self.min_hit_spin.setVisible(False)
        top_bar.addWidget(self.min_hit_spin)

        main_layout.addLayout(top_bar)

        # 滚动区域：所有筛选条件
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(6)

        # 1. 行业板块
        self._create_industry_group(content_layout)

        # 2. 基础数据条件
        self._create_basic_group(content_layout)

        # 3. 技术指标条件
        self._create_technical_group(content_layout)

        # 4. 形态条件
        self._create_pattern_group(content_layout)

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, stretch=1)

        # 底部按钮
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        reset_btn = QPushButton('🔄 重置')
        reset_btn.setStyleSheet(f'background: {BORDER_STRONG}; color: {TEXT_PRIMARY}; padding: 6px 16px; border-radius: 3px;')
        reset_btn.clicked.connect(self._reset_config)
        bottom_bar.addWidget(reset_btn)

        cancel_btn = QPushButton('取消')
        cancel_btn.setStyleSheet(f'background: {BORDER_STRONG}; color: {TEXT_PRIMARY}; padding: 6px 16px; border-radius: 3px;')
        cancel_btn.clicked.connect(self.filter_cancelled.emit)
        bottom_bar.addWidget(cancel_btn)

        apply_btn = QPushButton('✅ 应用筛选')
        apply_btn.setStyleSheet(f'background: {STATUS_SUCCESS}; color: {TEXT_PRIMARY}; padding: 6px 20px; border-radius: 3px; font-weight: bold;')
        apply_btn.clicked.connect(self._apply_filter)
        bottom_bar.addWidget(apply_btn)

        main_layout.addLayout(bottom_bar)

    def _create_industry_group(self, parent_layout):
        """行业板块选择"""
        group = QGroupBox('1. 行业板块（多选）')
        layout = QVBoxLayout(group)

        self.industry_check = QCheckBox('启用行业筛选')
        self.industry_check.setStyleSheet(f'color: {TEXT_PRIMARY};')
        layout.addWidget(self.industry_check)

        # 行业多选（用checkbox网格）
        industry_widget = QWidget()
        industry_layout = QHBoxLayout(industry_widget)
        industry_layout.setContentsMargins(0, 0, 0, 0)

        self.industry_checkboxes = []
        # 分两列
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        for i, ind in enumerate(self.INDUSTRY_OPTIONS):
            cb = QCheckBox(ind)
            cb.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
            self.industry_checkboxes.append(cb)
            if i % 2 == 0:
                col1.addWidget(cb)
            else:
                col2.addWidget(cb)
        industry_layout.addLayout(col1)
        industry_layout.addLayout(col2)
        layout.addWidget(industry_widget)

        parent_layout.addWidget(group)

    def _create_basic_group(self, parent_layout):
        """基础数据条件"""
        group = QGroupBox('2. 基础数据条件')
        layout = QVBoxLayout(group)

        # 价格范围
        self.price_check, self.price_min, self.price_max = self._create_range_row(
            layout, '股价范围(元):', 0, 1000, 5, 60, 0.01
        )

        # 市值范围
        self.cap_check, self.cap_min, self.cap_max = self._create_range_row(
            layout, '总市值范围(亿):', 0, 10000, 30, 300, 1
        )

        # 换手率范围
        self.turnover_check, self.turnover_min, self.turnover_max = self._create_range_row(
            layout, '换手率范围(%):', 0, 100, 5, 20, 0.1
        )

        # 量比范围
        self.vr_check, self.vr_min, self.vr_max = self._create_range_row(
            layout, '量比范围:', 0, 50, 1.2, 3, 0.1
        )

        # 涨幅范围
        self.pct_check, self.pct_min, self.pct_max = self._create_range_row(
            layout, '当日涨幅范围(%):', -20, 20, 2, 8, 0.1
        )

        # 振幅范围
        self.amp_check, self.amp_min, self.amp_max = self._create_range_row(
            layout, '振幅范围(%):', 0, 30, 3, 15, 0.1
        )

        # 成交量突破倍数
        self.vb_check, self.vb_min, self.vb_max = self._create_range_row(
            layout, '成交量/5日均量倍数:', 0, 50, 1.5, 10, 0.1
        )

        parent_layout.addWidget(group)

    def _create_technical_group(self, parent_layout):
        """技术指标条件"""
        group = QGroupBox('3. 技术指标条件')
        layout = QVBoxLayout(group)

        # 均线多头排列
        self.ma_bullish_check = QCheckBox('均线多头排列 (MA5 > MA9 > MA20)')
        self.ma_bullish_check.setStyleSheet(f'color: {TEXT_PRIMARY};')
        layout.addWidget(self.ma_bullish_check)

        # KDJ J值范围
        self.kdj_check, self.kdj_min, self.kdj_max = self._create_range_row(
            layout, 'KDJ J值范围:', -50, 150, -20, 10, 1
        )

        # MA5上穿MA9
        self.ma5_cross_check = QCheckBox('MA5上穿MA9 (穿九信号)')
        self.ma5_cross_check.setStyleSheet(f'color: {TEXT_PRIMARY};')
        layout.addWidget(self.ma5_cross_check)

        # 收盘价与MA9距离
        self.ma9_dist_check, self.ma9_dist_min, self.ma9_dist_max = self._create_range_row(
            layout, '|收盘价-MA9|距离(元):', 0, 10, 0.02, 0.10, 0.01
        )

        # 收盘价与MA5距离
        self.ma5_dist_check, self.ma5_dist_min, self.ma5_dist_max = self._create_range_row(
            layout, '|收盘价-MA5|距离(元):', 0, 10, 0.02, 0.10, 0.01
        )

        parent_layout.addWidget(group)

    def _create_pattern_group(self, parent_layout):
        """形态条件"""
        group = QGroupBox('4. K线形态条件')
        layout = QVBoxLayout(group)

        # 连续上涨
        self.cont_up_check = QCheckBox('连续上涨')
        self.cont_up_check.setStyleSheet(f'color: {TEXT_PRIMARY};')
        layout.addWidget(self.cont_up_check)

        cont_row = QHBoxLayout()
        cont_row.addWidget(QLabel('连续天数:'))
        self.cont_up_days = QDoubleSpinBox()
        self.cont_up_days.setRange(2, 10)
        self.cont_up_days.setValue(3)
        self.cont_up_days.setDecimals(0)
        self.cont_up_days.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};')
        cont_row.addWidget(self.cont_up_days)

        cont_row.addWidget(QLabel('每日涨幅≥(%):'))
        self.cont_up_pct = QDoubleSpinBox()
        self.cont_up_pct.setRange(0.1, 10)
        self.cont_up_pct.setValue(1.0)
        self.cont_up_pct.setSingleStep(0.1)
        self.cont_up_pct.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};')
        cont_row.addWidget(self.cont_up_pct)
        cont_row.addStretch()
        layout.addLayout(cont_row)

        parent_layout.addWidget(group)

    def _create_range_row(self, parent_layout, label, min_val, max_val, default_min, default_max, step):
        """创建范围输入行"""
        row = QHBoxLayout()

        check = QCheckBox(label)
        check.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 12px;')
        row.addWidget(check)

        min_spin = QDoubleSpinBox()
        min_spin.setRange(min_val, max_val)
        min_spin.setValue(default_min)
        min_spin.setSingleStep(step)
        min_spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; padding: 2px;')
        min_spin.setFixedWidth(80)
        row.addWidget(min_spin)

        row.addWidget(QLabel('~'))

        max_spin = QDoubleSpinBox()
        max_spin.setRange(min_val, max_val)
        max_spin.setValue(default_max)
        max_spin.setSingleStep(step)
        max_spin.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SOFT}; padding: 2px;')
        max_spin.setFixedWidth(80)
        row.addWidget(max_spin)

        row.addStretch()
        parent_layout.addLayout(row)

        return check, min_spin, max_spin

    def _on_mode_changed(self, index):
        """模式切换"""
        is_loose = (index == 1)
        self.min_hit_label.setVisible(is_loose)
        self.min_hit_spin.setVisible(is_loose)

    def _collect_config(self):
        """从UI收集配置"""
        config = ManualFilterConfig()
        config.name = self.name_edit.text()

        # 行业
        config.industry_enabled = self.industry_check.isChecked()
        config.industries = [cb.text() for cb in self.industry_checkboxes if cb.isChecked()]

        # 基础数据
        config.price_enabled = self.price_check.isChecked()
        config.price_min = self.price_min.value()
        config.price_max = self.price_max.value()

        config.market_cap_enabled = self.cap_check.isChecked()
        config.market_cap_min = self.cap_min.value()
        config.market_cap_max = self.cap_max.value()

        config.turnover_enabled = self.turnover_check.isChecked()
        config.turnover_min = self.turnover_min.value()
        config.turnover_max = self.turnover_max.value()

        config.volume_ratio_enabled = self.vr_check.isChecked()
        config.volume_ratio_min = self.vr_min.value()
        config.volume_ratio_max = self.vr_max.value()

        config.pct_enabled = self.pct_check.isChecked()
        config.pct_min = self.pct_min.value()
        config.pct_max = self.pct_max.value()

        config.amplitude_enabled = self.amp_check.isChecked()
        config.amplitude_min = self.amp_min.value()
        config.amplitude_max = self.amp_max.value()

        config.volume_break_enabled = self.vb_check.isChecked()
        config.volume_break_min = self.vb_min.value()
        config.volume_break_max = self.vb_max.value()

        # 技术指标
        config.ma_bullish_enabled = self.ma_bullish_check.isChecked()

        config.kdj_enabled = self.kdj_check.isChecked()
        config.kdj_j_min = self.kdj_min.value()
        config.kdj_j_max = self.kdj_max.value()

        config.ma5_cross_ma9_enabled = self.ma5_cross_check.isChecked()

        config.ma9_distance_enabled = self.ma9_dist_check.isChecked()
        config.ma9_distance_min = self.ma9_dist_min.value()
        config.ma9_distance_max = self.ma9_dist_max.value()

        config.ma5_distance_enabled = self.ma5_dist_check.isChecked()
        config.ma5_distance_min = self.ma5_dist_min.value()
        config.ma5_distance_max = self.ma5_dist_max.value()

        # 形态
        config.continuous_up_enabled = self.cont_up_check.isChecked()
        config.continuous_up_days = int(self.cont_up_days.value())
        config.continuous_up_min_pct = self.cont_up_pct.value()

        # 筛选模式
        config.strict_mode = (self.mode_combo.currentIndex() == 0)
        config.min_hit_rate = self.min_hit_spin.value()

        return config

    def _apply_config_to_ui(self, config):
        """将配置应用到UI"""
        self.name_edit.setText(config.name)

        # 行业
        self.industry_check.setChecked(config.industry_enabled)
        for cb in self.industry_checkboxes:
            cb.setChecked(cb.text() in config.industries)

        # 基础数据
        self.price_check.setChecked(config.price_enabled)
        self.price_min.setValue(config.price_min)
        self.price_max.setValue(config.price_max)

        self.cap_check.setChecked(config.market_cap_enabled)
        self.cap_min.setValue(config.market_cap_min)
        self.cap_max.setValue(config.market_cap_max)

        self.turnover_check.setChecked(config.turnover_enabled)
        self.turnover_min.setValue(config.turnover_min)
        self.turnover_max.setValue(config.turnover_max)

        self.vr_check.setChecked(config.volume_ratio_enabled)
        self.vr_min.setValue(config.volume_ratio_min)
        self.vr_max.setValue(config.volume_ratio_max)

        self.pct_check.setChecked(config.pct_enabled)
        self.pct_min.setValue(config.pct_min)
        self.pct_max.setValue(config.pct_max)

        self.amp_check.setChecked(config.amplitude_enabled)
        self.amp_min.setValue(config.amplitude_min)
        self.amp_max.setValue(config.amplitude_max)

        self.vb_check.setChecked(config.volume_break_enabled)
        self.vb_min.setValue(config.volume_break_min)
        self.vb_max.setValue(config.volume_break_max)

        # 技术指标
        self.ma_bullish_check.setChecked(config.ma_bullish_enabled)

        self.kdj_check.setChecked(config.kdj_enabled)
        self.kdj_min.setValue(config.kdj_j_min)
        self.kdj_max.setValue(config.kdj_j_max)

        self.ma5_cross_check.setChecked(config.ma5_cross_ma9_enabled)

        self.ma9_dist_check.setChecked(config.ma9_distance_enabled)
        self.ma9_dist_min.setValue(config.ma9_distance_min)
        self.ma9_dist_max.setValue(config.ma9_distance_max)

        self.ma5_dist_check.setChecked(config.ma5_distance_enabled)
        self.ma5_dist_min.setValue(config.ma5_distance_min)
        self.ma5_dist_max.setValue(config.ma5_distance_max)

        # 形态
        self.cont_up_check.setChecked(config.continuous_up_enabled)
        self.cont_up_days.setValue(config.continuous_up_days)
        self.cont_up_pct.setValue(config.continuous_up_min_pct)

        # 筛选模式
        self.mode_combo.setCurrentIndex(0 if config.strict_mode else 1)
        self.min_hit_spin.setValue(config.min_hit_rate)
        self._on_mode_changed(0 if config.strict_mode else 1)

    def _apply_filter(self):
        """应用筛选"""
        config = self._collect_config()
        self.filter_applied.emit(config)

    def _reset_config(self):
        """重置配置"""
        reply = QMessageBox.question(self, '确认', '确定重置所有筛选条件？',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_config_to_ui(ManualFilterConfig())

    def _save_config(self):
        """保存配置"""
        config = self._collect_config()
        name = config.name.strip()
        if not name or name == '未命名方案':
            name, ok = QInputDialog.getText(self, '保存方案', '请输入方案名称:')
            if not ok or not name.strip():
                return
            config.name = name.strip()

        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'manual_filters')
        os.makedirs(config_dir, exist_ok=True)
        filepath = os.path.join(config_dir, f'{config.name}.json')
        config.save_to_file(filepath)
        self._load_saved_configs()
        QMessageBox.information(self, '保存成功', f'方案"{config.name}"已保存')

    def _load_config(self):
        """加载配置"""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'manual_filters')
        if not os.path.exists(config_dir):
            QMessageBox.warning(self, '加载', '暂无保存的方案')
            return

        files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
        if not files:
            QMessageBox.warning(self, '加载', '暂无保存的方案')
            return

        names = [f.replace('.json', '') for f in files]
        name, ok = QInputDialog.getItem(self, '加载方案', '选择方案:', names, 0, False)
        if ok and name:
            filepath = os.path.join(config_dir, f'{name}.json')
            config = ManualFilterConfig.load_from_file(filepath)
            if config:
                self._apply_config_to_ui(config)
                QMessageBox.information(self, '加载成功', f'方案"{name}"已加载')

    def _on_preset_selected(self, name):
        """预设方案选择"""
        if name in PRESET_CONFIGS:
            config = ManualFilterConfig.from_dict(PRESET_CONFIGS[name])
            self._apply_config_to_ui(config)
            self.preset_combo.setCurrentIndex(0)

    def _load_saved_configs(self):
        """加载已保存的方案列表到下拉框"""
        # 保持预设方案，重新添加我的方案
        while self.preset_combo.count() > 0:
            self.preset_combo.removeItem(0)

        self.preset_combo.addItem('-- 预设方案 --')
        for name in PRESET_CONFIGS.keys():
            self.preset_combo.addItem(name)

        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'manual_filters')
        if os.path.exists(config_dir):
            files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
            if files:
                self.preset_combo.addItem('-- 我的方案 --')
                for f in files:
                    self.preset_combo.addItem(f.replace('.json', ''))
