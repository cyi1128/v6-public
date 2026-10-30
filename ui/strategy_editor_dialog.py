# -*- coding: utf-8 -*-
"""
策略编辑器对话框

功能：
- 查看/编辑现有策略条件
- 用自然语言创建新策略
- 删除自定义策略
- 重置为默认策略
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton,
    QTextEdit, QGroupBox, QFormLayout, QWidget, QSplitter, QMessageBox,
    QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from strategy.strategy_manager import get_strategy_manager
from strategy.nl_strategy_parser import get_nl_parser


DARK_BG = '#0d1117'
DARK_CARD = '#161b22'
DARK_BORDER = '#30363d'
TEXT_PRIMARY = '#e6edf3'
TEXT_SECONDARY = '#8b949e'
ACCENT_BLUE = '#58a6ff'
ACCENT_GREEN = '#3fb950'
ACCENT_RED = '#f85149'
ACCENT_YELLOW = '#d29922'


class StrategyEditorDialog(QDialog):
    """策略编辑器对话框"""

    strategy_changed = pyqtSignal()  # 策略变更信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('策略管理中心')
        self.setMinimumSize(900, 650)
        self.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')

        self.manager = get_strategy_manager()
        self.parser = get_nl_parser()
        self._current_strategy_id = None
        self._param_widgets = {}

        self._init_ui()
        self._load_strategy_list()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # 标题
        title = QLabel('📋 策略管理中心')
        title.setFont(QFont('Microsoft YaHei', 16, QFont.Weight.Bold))
        title.setStyleSheet(f'color: {TEXT_PRIMARY}; padding: 5px;')
        main_layout.addWidget(title)

        # 主体：左右分栏
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：策略列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        list_title = QLabel('策略列表')
        list_title.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        left_layout.addWidget(list_title)

        self.strategy_list = QListWidget()
        self.strategy_list.setStyleSheet(f"""
            QListWidget {{
                background: {DARK_CARD};
                border: 1px solid {DARK_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 10px;
                border-bottom: 1px solid {DARK_BORDER};
            }}
            QListWidget::item:selected {{
                background: {ACCENT_BLUE};
                color: white;
            }}
        """)
        self.strategy_list.currentItemChanged.connect(self._on_strategy_selected)
        left_layout.addWidget(self.strategy_list)

        # 列表操作按钮
        btn_layout = QHBoxLayout()
        self.btn_rename = QPushButton('✏️ 重命名')
        self.btn_rename.setStyleSheet(self._btn_style(ACCENT_BLUE))
        self.btn_rename.clicked.connect(self._rename_current)
        btn_layout.addWidget(self.btn_rename)

        self.btn_delete = QPushButton('🗑 删除')
        self.btn_delete.setStyleSheet(self._btn_style(ACCENT_RED))
        self.btn_delete.clicked.connect(self._delete_current)
        btn_layout.addWidget(self.btn_delete)

        self.btn_reset = QPushButton('🔄 重置默认')
        self.btn_reset.setStyleSheet(self._btn_style(ACCENT_YELLOW))
        self.btn_reset.clicked.connect(self._reset_default)
        btn_layout.addWidget(self.btn_reset)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_widget)

        # 右侧：Tab页（编辑条件 / 自然语言创建）
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DARK_BORDER};
                border-radius: 6px;
                background: {DARK_CARD};
            }}
            QTabBar::tab {{
                background: {DARK_CARD};
                color: {TEXT_SECONDARY};
                padding: 8px 20px;
                border: 1px solid {DARK_BORDER};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
            QTabBar::tab:selected {{
                background: {ACCENT_BLUE};
                color: white;
            }}
        """)

        # Tab1: 条件编辑
        self.tab_edit = QWidget()
        self._init_edit_tab()
        self.tabs.addTab(self.tab_edit, '✏️ 编辑条件')

        # Tab2: 自然语言创建
        self.tab_nl = QWidget()
        self._init_nl_tab()
        self.tabs.addTab(self.tab_nl, '💬 自然语言创建')

        splitter.addWidget(self.tabs)
        splitter.setSizes([280, 620])

        main_layout.addWidget(splitter)

        # 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_save = QPushButton('💾 保存策略')
        self.btn_save.setStyleSheet(self._btn_style(ACCENT_GREEN))
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._save_current)
        bottom_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton('关闭')
        self.btn_close.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        self.btn_close.setMinimumWidth(80)
        self.btn_close.clicked.connect(self._safe_close)
        bottom_layout.addWidget(self.btn_close)

    def _safe_close(self):
        """安全关闭对话框"""
        try:
            self.strategy_list.currentItemChanged.disconnect(self._on_strategy_selected)
        except Exception:
            pass
        try:
            self.btn_save.clicked.disconnect(self._save_current)
        except Exception:
            pass
        try:
            self.btn_close.clicked.disconnect(self._safe_close)
        except Exception:
            pass
        self.accept()

    def closeEvent(self, event):
        """关闭事件处理"""
        try:
            self.strategy_list.currentItemChanged.disconnect(self._on_strategy_selected)
        except Exception:
            pass
        event.accept()

    def _init_edit_tab(self):
        """初始化条件编辑Tab"""
        layout = QVBoxLayout(self.tab_edit)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 策略名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel('策略名称:'))
        self.name_input = QLineEdit()
        self.name_input.setStyleSheet(self._input_style())
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # 策略描述
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(QLabel('策略描述:'))
        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(60)
        self.desc_input.setStyleSheet(self._input_style())
        desc_layout.addWidget(self.desc_input)
        layout.addLayout(desc_layout)

        # 条件表单（滚动区域）
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f'QScrollArea {{ border: none; background: {DARK_CARD}; }}')

        form_widget = QWidget()
        self.form_layout = QFormLayout(form_widget)
        self.form_layout.setSpacing(10)

        self._build_condition_fields()
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)

    def _build_condition_fields(self):
        """构建条件编辑字段"""
        # 基础过滤
        self.cb_main_board = QCheckBox('只选主板')
        self.cb_main_board.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.form_layout.addRow('市场范围:', self.cb_main_board)

        self.cb_exclude_st = QCheckBox('剔除ST')
        self.cb_exclude_st.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.form_layout.addRow('ST过滤:', self.cb_exclude_st)

        self.cb_no_limit_yesterday = QCheckBox('前一天未涨停')
        self.cb_no_limit_yesterday.setStyleSheet(f'color: {TEXT_PRIMARY};')
        self.form_layout.addRow('涨停过滤:', self.cb_no_limit_yesterday)

        # 价格范围
        price_layout = QHBoxLayout()
        self.price_min = self._make_double_spin(0, 999, 2)
        self.price_max = self._make_double_spin(0, 999, 2)
        price_layout.addWidget(self.price_min)
        price_layout.addWidget(QLabel('~'))
        price_layout.addWidget(self.price_max)
        price_layout.addWidget(QLabel('元'))
        self.form_layout.addRow('价格范围:', self._wrap_layout(price_layout))

        # 市值范围
        mc_layout = QHBoxLayout()
        self.mc_min = self._make_double_spin(0, 9999, 1)
        self.mc_max = self._make_double_spin(0, 9999, 1)
        mc_layout.addWidget(self.mc_min)
        mc_layout.addWidget(QLabel('~'))
        mc_layout.addWidget(self.mc_max)
        mc_layout.addWidget(QLabel('亿'))
        self.form_layout.addRow('市值范围:', self._wrap_layout(mc_layout))

        # 换手率
        to_layout = QHBoxLayout()
        self.to_min = self._make_double_spin(0, 100, 1)
        self.to_max = self._make_double_spin(0, 100, 1)
        to_layout.addWidget(self.to_min)
        to_layout.addWidget(QLabel('~'))
        to_layout.addWidget(self.to_max)
        to_layout.addWidget(QLabel('%'))
        self.form_layout.addRow('换手率:', self._wrap_layout(to_layout))

        # 量比
        self.volume_ratio = self._make_double_spin(0, 50, 1)
        self.form_layout.addRow('量比≥:', self.volume_ratio)

        # 涨停次数
        self.limit_up_count = self._make_spin(0, 100)
        self.form_layout.addRow('年涨停≥:', self.limit_up_count)

        # 振幅
        self.amplitude = self._make_double_spin(0, 100, 1)
        self.form_layout.addRow('振幅≤%:', self.amplitude)

        # 涨跌幅
        pct_layout = QHBoxLayout()
        self.pct_min = self._make_double_spin(-20, 20, 1)
        self.pct_max = self._make_double_spin(-20, 20, 1)
        self.pct_min.setValue(-99)
        self.pct_max.setValue(99)
        pct_layout.addWidget(self.pct_min)
        pct_layout.addWidget(QLabel('~'))
        pct_layout.addWidget(self.pct_max)
        pct_layout.addWidget(QLabel('%'))
        self.form_layout.addRow('涨跌幅:', self._wrap_layout(pct_layout))

        # 高点比例
        hr_layout = QHBoxLayout()
        self.hr_min = self._make_double_spin(0, 200, 0)
        self.hr_max = self._make_double_spin(0, 200, 0)
        hr_layout.addWidget(self.hr_min)
        hr_layout.addWidget(QLabel('~'))
        hr_layout.addWidget(self.hr_max)
        hr_layout.addWidget(QLabel('%'))
        self.form_layout.addRow('高点比例:', self._wrap_layout(hr_layout))

        # 高点周期
        self.high_days = self._make_spin(20, 500)
        self.form_layout.addRow('高点周期(天):', self.high_days)

        # 排除行业
        self.exclude_industries = QLineEdit()
        self.exclude_industries.setPlaceholderText('多个行业用/分隔，如：地产/农业/酒')
        self.exclude_industries.setStyleSheet(self._input_style())
        self.form_layout.addRow('排除行业:', self.exclude_industries)

    def _init_nl_tab(self):
        """初始化自然语言创建Tab"""
        layout = QVBoxLayout(self.tab_nl)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        tip = QLabel('用自然语言描述你的选股策略，系统自动解析为筛选条件')
        tip.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 示例
        example = QLabel('示例：\n主板非ST，价格5-60元，市值30-230亿，年涨停≥3次，8个月高点70%-105%，排除地产/农业/酒/保险')
        example.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 11px; padding: 8px; background: {DARK_BG}; border-radius: 4px;')
        example.setWordWrap(True)
        layout.addWidget(example)

        # AI状态显示
        self.ai_status_label = QLabel()
        self.ai_status_label.setStyleSheet(f'font-size: 11px; padding: 6px; border-radius: 4px;')
        self._update_ai_status()
        layout.addWidget(self.ai_status_label)

        # 输入框
        self.nl_input = QTextEdit()
        self.nl_input.setPlaceholderText('在此输入你的策略描述...')
        self.nl_input.setStyleSheet(self._input_style())
        self.nl_input.setMinimumHeight(120)
        layout.addWidget(self.nl_input)

        # 解析按钮
        self.btn_parse = QPushButton('🔍 解析策略')
        self.btn_parse.setStyleSheet(self._btn_style(ACCENT_BLUE))
        self.btn_parse.clicked.connect(self._parse_nl)
        layout.addWidget(self.btn_parse)

        # 解析结果
        result_label = QLabel('解析结果:')
        result_label.setStyleSheet(f'color: {TEXT_SECONDARY};')
        layout.addWidget(result_label)

        self.nl_result = QTextEdit()
        self.nl_result.setReadOnly(True)
        self.nl_result.setStyleSheet(self._input_style())
        self.nl_result.setMaximumHeight(150)
        layout.addWidget(self.nl_result)

        # 创建按钮
        self.btn_create = QPushButton('➕ 创建新策略')
        self.btn_create.setStyleSheet(self._btn_style(ACCENT_GREEN))
        self.btn_create.setEnabled(False)
        self.btn_create.clicked.connect(self._create_from_nl)
        layout.addWidget(self.btn_create)

        layout.addStretch()

    def _make_double_spin(self, min_val, max_val, decimals):
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(decimals)
        spin.setStyleSheet(self._input_style())
        spin.setMinimumWidth(80)
        return spin

    def _make_spin(self, min_val, max_val):
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setStyleSheet(self._input_style())
        spin.setMinimumWidth(80)
        return spin

    def _wrap_layout(self, layout):
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _btn_style(self, color):
        return f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
            QPushButton:disabled {{
                background: {DARK_BORDER};
                color: {TEXT_SECONDARY};
            }}
        """

    def _input_style(self):
        return f"""
            QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox {{
                background: {DARK_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER};
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {ACCENT_BLUE};
            }}
        """

    def _load_strategy_list(self):
        """加载策略列表"""
        self.strategy_list.clear()
        strategies = self.manager.get_all()
        for s in strategies:
            item = QListWidgetItem(f"📌 {s['name']}")
            item.setData(Qt.ItemDataRole.UserRole, s['id'])
            self.strategy_list.addItem(item)
        if strategies:
            self.strategy_list.setCurrentRow(0)

    def _on_strategy_selected(self, current, previous):
        """选择策略"""
        if not current:
            return
        strategy_id = current.data(Qt.ItemDataRole.UserRole)
        strategy = self.manager.get_by_id(strategy_id)
        if not strategy:
            return
        self._current_strategy_id = strategy_id
        self._fill_form(strategy)

    def _fill_form(self, strategy):
        """填充表单"""
        self.name_input.setText(strategy['name'])
        self.desc_input.setPlainText(strategy['description'])

        cond = strategy.get('conditions', {})
        self.cb_main_board.setChecked(cond.get('main_board_only', False))
        self.cb_exclude_st.setChecked(cond.get('exclude_st', False))
        self.cb_no_limit_yesterday.setChecked(cond.get('no_limit_up_yesterday', False))

        pr = cond.get('price_range', [0, 999])
        self.price_min.setValue(pr[0])
        self.price_max.setValue(pr[1])

        mc = cond.get('market_cap_range', [0, 9999])
        self.mc_min.setValue(mc[0])
        self.mc_max.setValue(mc[1])

        tr = cond.get('turnover_range', [0, 100])
        self.to_min.setValue(tr[0])
        self.to_max.setValue(tr[1])

        self.volume_ratio.setValue(cond.get('volume_ratio_min', 0))
        self.limit_up_count.setValue(cond.get('limit_up_count_min', 0))
        self.amplitude.setValue(cond.get('amplitude_max', 100))

        pct = cond.get('pct_chg_range', [-99, 99])
        self.pct_min.setValue(pct[0])
        self.pct_max.setValue(pct[1])

        hr = cond.get('high_ratio_range', [0, 99])
        self.hr_min.setValue(hr[0] * 100)
        self.hr_max.setValue(hr[1] * 100)

        self.high_days.setValue(cond.get('high_period_days', 160))

        inds = cond.get('exclude_industries', [])
        self.exclude_industries.setText('/'.join(inds))

    def _collect_conditions(self):
        """收集表单条件"""
        return {
            "main_board_only": self.cb_main_board.isChecked(),
            "exclude_st": self.cb_exclude_st.isChecked(),
            "no_limit_up_yesterday": self.cb_no_limit_yesterday.isChecked(),
            "price_range": [self.price_min.value(), self.price_max.value()],
            "market_cap_range": [self.mc_min.value(), self.mc_max.value()],
            "turnover_range": [self.to_min.value(), self.to_max.value()],
            "volume_ratio_min": self.volume_ratio.value(),
            "limit_up_count_min": self.limit_up_count.value(),
            "amplitude_max": self.amplitude.value(),
            "pct_chg_range": [self.pct_min.value(), self.pct_max.value()],
            "high_ratio_range": [self.hr_min.value() / 100, self.hr_max.value() / 100],
            "high_period_days": self.high_days.value(),
            "exclude_industries": [i.strip() for i in self.exclude_industries.text().split('/') if i.strip()],
        }

    def _save_current(self):
        """保存当前策略"""
        if not self._current_strategy_id:
            return
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, '提示', '请输入策略名称')
            return

        conditions = self._collect_conditions()
        description = self.parser.generate_description(conditions)

        self.manager.update_strategy(
            self._current_strategy_id,
            name=name,
            description=description,
            conditions=conditions
        )
        self._load_strategy_list()
        self.strategy_changed.emit()
        QMessageBox.information(self, '成功', f'策略「{name}」已保存')

    def _rename_current(self):
        """重命名当前策略"""
        if not self._current_strategy_id:
            QMessageBox.warning(self, '提示', '请先选择一个策略')
            return
        strategy = self.manager.get_by_id(self._current_strategy_id)
        if not strategy:
            return

        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, '重命名策略', '请输入新的策略名称：',
            text=strategy['name']
        )
        if ok and new_name.strip():
            new_name = new_name.strip()
            # 检查重名
            for s in self.manager.get_all():
                if s['name'] == new_name and s['id'] != self._current_strategy_id:
                    QMessageBox.warning(self, '提示', f'已存在名为「{new_name}」的策略')
                    return
            if self.manager.update_strategy(self._current_strategy_id, name=new_name):
                self._load_strategy_list()
                # 重新选中当前策略
                for i in range(self.strategy_list.count()):
                    item = self.strategy_list.item(i)
                    if new_name in item.text():
                        self.strategy_list.setCurrentRow(i)
                        break
                self.strategy_changed.emit()
                QMessageBox.information(self, '成功', f'策略已重命名为「{new_name}」')
            else:
                QMessageBox.warning(self, '失败', '重命名失败')

    def _delete_current(self):
        """删除当前策略"""
        if not self._current_strategy_id:
            return
        strategy = self.manager.get_by_id(self._current_strategy_id)
        if not strategy:
            return
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定删除策略「{strategy["name"]}」吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.manager.delete_strategy(self._current_strategy_id):
                self._load_strategy_list()
                self.strategy_changed.emit()
            else:
                QMessageBox.warning(self, '提示', '默认策略不能删除')

    def _reset_default(self):
        """重置为默认策略"""
        reply = QMessageBox.question(
            self, '确认重置',
            '确定重置为默认策略吗？所有自定义策略将被删除。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.reset_to_default()
            self._load_strategy_list()
            self.strategy_changed.emit()

    def _update_ai_status(self):
        """更新AI状态显示"""
        try:
            if self.parser.is_llm_available():
                info = self.parser._get_llm_engine().get_model_info()
                model = info.get('model', '未知')
                self.ai_status_label.setText(f'🤖 AI模式已启用（模型: {model}）')
                self.ai_status_label.setStyleSheet(
                    f'font-size: 11px; padding: 6px; border-radius: 4px; '
                    f'background: rgba(46, 160, 67, 0.15); color: #3fb950;'
                )
            else:
                self.ai_status_label.setText(
                    '⚠️ AI模式未启用（未检测到Ollama），当前使用关键词匹配模式。\n'
                    '安装Ollama并下载qwen2.5:7b模型后可启用AI理解能力。'
                )
                self.ai_status_label.setStyleSheet(
                    f'font-size: 11px; padding: 6px; border-radius: 4px; '
                    f'background: rgba(210, 153, 34, 0.15); color: #d29922;'
                )
        except Exception as e:
            self.ai_status_label.setText(f'⚠️ AI状态检测失败: {e}')
            self.ai_status_label.setStyleSheet(
                f'font-size: 11px; padding: 6px; border-radius: 4px; '
                f'background: rgba(248, 81, 73, 0.15); color: #f85149;'
            )

    def _parse_nl(self):
        """解析自然语言"""
        text = self.nl_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, '提示', '请输入策略描述')
            return

        # 显示解析中
        self.btn_parse.setEnabled(False)
        self.btn_parse.setText('解析中...')
        self.nl_result.setPlainText('正在解析，请稍候...')

        # 使用后台线程避免UI卡顿（LLM调用可能需要几秒）
        from PyQt6.QtCore import QThread, pyqtSignal

        class ParseThread(QThread):
            finished_signal = pyqtSignal(dict, str)

            def __init__(self, parser, text):
                super().__init__()
                self.parser = parser
                self.text = text

            def run(self):
                conditions = self.parser.parse(self.text)
                mode = self.parser.get_last_mode()
                self.finished_signal.emit(conditions, mode)

        self._parse_thread = ParseThread(self.parser, text)
        self._parse_thread.finished_signal.connect(self._on_parse_finished)
        self._parse_thread.start()

    def _on_parse_finished(self, conditions, mode):
        """解析完成回调"""
        self.btn_parse.setEnabled(True)
        self.btn_parse.setText('🔍 解析策略')

        description = self.parser.generate_description(conditions)
        mode_text = "🤖 AI大模型解析" if mode == "llm" else "🔤 关键词匹配"

        result_text = f"解析成功（{mode_text}）\n\n策略描述：{description}\n\n详细条件：\n"
        for k, v in conditions.items():
            if v and v != [0, 999] and v != [0, 9999] and v != [0, 100] and v != [0, 99] and v != [-99, 99] and v != 0 and v != 100 and v != [] and v != [-100, 200]:
                result_text += f"  {k}: {v}\n"

        self.nl_result.setPlainText(result_text)
        self._nl_conditions = conditions
        self.btn_create.setEnabled(True)

    def _create_from_nl(self):
        """从自然语言创建新策略"""
        if not hasattr(self, '_nl_conditions'):
            return

        name = self.name_input.text().strip() or '自定义策略'
        description = self.parser.generate_description(self._nl_conditions)

        # 允许在创建前编辑名称，并在成功后反馈“上传成功”
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, '编辑策略名称', '请输入新策略名称：', text=name
        )
        if not ok:
            return
        name = new_name.strip() or name

        strategy_id = self.manager.add_strategy(name, description, self._nl_conditions)
        self._load_strategy_list()
        self.strategy_changed.emit()

        # 选中新策略
        for i in range(self.strategy_list.count()):
            item = self.strategy_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == strategy_id:
                self.strategy_list.setCurrentRow(i)
                break

        self.tabs.setCurrentWidget(self.tab_edit)
        QMessageBox.information(self, '上传成功', f'新策略「{name}」已创建并上传成功。')
        self.btn_create.setEnabled(False)
