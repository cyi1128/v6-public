"""
我的持仓AI管理页面
手动添加持仓，AI自动分析，每日持仓报告
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit, QDialog, QFormLayout, QDialogButtonBox, QTextEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    STATUS_ERROR, STATUS_WARNING, STATUS_INFO,
)
from strategy.portfolio_manager import PortfolioManager


class PortfolioWidget(QWidget):
    """我的持仓AI管理页面"""

    DARK_COLORS = {
        'bg_primary': BG_WINDOW,
        'bg_secondary': BG_CARD,
        'bg_tertiary': BG_INTERACTIVE,
        'border': BORDER,
        'text_primary': TEXT_PRIMARY,
        'text_secondary': TEXT_SECONDARY,
        'accent': ACCENT_BLUE,
        'red': ACCENT_RED,
        'green': ACCENT_GREEN,
        'orange': ACCENT_GOLD,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.portfolio_manager = PortfolioManager()
        self._init_ui()
        self.refresh_portfolio()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部：持仓概览
        layout.addWidget(self._create_summary_bar())

        # 操作按钮
        btn_layout = QHBoxLayout()
        add_btn = QPushButton('➕ 添加持仓')
        add_btn.setStyleSheet(self._btn_style(self.DARK_COLORS['accent']))
        add_btn.clicked.connect(self._show_add_dialog)
        btn_layout.addWidget(add_btn)

        refresh_btn = QPushButton('🔄 刷新')
        refresh_btn.setStyleSheet(self._btn_style(self.DARK_COLORS['green']))
        refresh_btn.clicked.connect(self.refresh_portfolio)
        btn_layout.addWidget(refresh_btn)

        report_btn = QPushButton('📊 生成持仓报告')
        report_btn.setStyleSheet(self._btn_style(self.DARK_COLORS['orange']))
        report_btn.clicked.connect(self._generate_report)
        btn_layout.addWidget(report_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 持仓表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            '股票名称', '代码', '成本价', '现价', '涨跌幅',
            '持仓数量', '盈亏', '盈亏%', '操作'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(self._table_style())
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        # 持仓报告区域
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setMaximumHeight(200)
        self.report_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.report_text)

    def _create_summary_bar(self):
        """创建持仓概览栏"""
        bar = QFrame()
        bar.setFixedHeight(80)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(30)

        stats = [
            ('持仓数量', 'stock_count', '0只', self.DARK_COLORS['accent']),
            ('总市值', 'total_value', '0元', self.DARK_COLORS['text_primary']),
            ('总成本', 'total_cost', '0元', self.DARK_COLORS['text_secondary']),
            ('总盈亏', 'total_profit', '0元', self.DARK_COLORS['red']),
            ('总盈亏%', 'total_profit_pct', '0%', self.DARK_COLORS['red']),
        ]

        self.summary_labels = {}
        for name, key, default, color in stats:
            stat_layout = QVBoxLayout()
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
            value_label = QLabel(default)
            value_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
            stat_layout.addWidget(name_label)
            stat_layout.addWidget(value_label)
            layout.addLayout(stat_layout)
            self.summary_labels[key] = value_label

        return bar

    def _btn_style(self, color):
        """按钮样式"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """

    def _table_style(self):
        """表格样式"""
        return f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {self.DARK_COLORS['border']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_secondary']};
                border: none;
                padding: 8px;
                font-weight: bold;
            }}
        """

    def refresh_portfolio(self):
        """刷新持仓"""
        results, summary = self.portfolio_manager.analyze_portfolio()

        # 更新概览
        self.summary_labels['stock_count'].setText(f"{summary['stock_count']}只")
        self.summary_labels['total_value'].setText(f"{summary['total_value']:.0f}元")
        self.summary_labels['total_cost'].setText(f"{summary['total_cost']:.0f}元")

        profit_color = self.DARK_COLORS['red'] if summary['total_profit'] >= 0 else self.DARK_COLORS['green']
        self.summary_labels['total_profit'].setText(f"{summary['total_profit']:+.0f}元")
        self.summary_labels['total_profit'].setStyleSheet(f"color: {profit_color}; font-size: 18px; font-weight: bold;")
        self.summary_labels['total_profit_pct'].setText(f"{summary['total_profit_pct']:+.2f}%")
        self.summary_labels['total_profit_pct'].setStyleSheet(f"color: {profit_color}; font-size: 18px; font-weight: bold;")

        # 更新表格
        self.table.setRowCount(len(results))
        for i, stock in enumerate(results):
            self.table.setItem(i, 0, QTableWidgetItem(stock['stock_name']))
            self.table.setItem(i, 1, QTableWidgetItem(stock['ts_code']))
            self.table.setItem(i, 2, QTableWidgetItem(f"{stock['cost_price']:.2f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{stock['current_price']:.2f}"))

            change_item = QTableWidgetItem(f"{stock['change_pct']:+.2f}%")
            change_item.setForeground(QColor('#f85149' if stock['change_pct'] >= 0 else '#3fb950'))
            self.table.setItem(i, 4, change_item)

            self.table.setItem(i, 5, QTableWidgetItem(str(stock['quantity'])))

            profit_item = QTableWidgetItem(f"{stock['profit']:+.2f}")
            profit_item.setForeground(QColor('#f85149' if stock['profit'] >= 0 else '#3fb950'))
            self.table.setItem(i, 6, profit_item)

            pct_item = QTableWidgetItem(f"{stock['profit_pct']:+.2f}%")
            pct_item.setForeground(QColor('#f85149' if stock['profit_pct'] >= 0 else '#3fb950'))
            self.table.setItem(i, 7, pct_item)

            # 删除按钮
            del_btn = QPushButton('删除')
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #da3633;
                    color: white;
                    border: none;
                    padding: 4px 12px;
                    font-size: 11px;
                    border-radius: 3px;
                }}
            """)
            del_btn.clicked.connect(lambda checked, code=stock['ts_code']: self._remove_stock(code))
            self.table.setCellWidget(i, 8, del_btn)

    def _show_add_dialog(self):
        """显示添加持仓对话框"""
        dialog = AddStockDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            result = self.portfolio_manager.add_stock(
                data['ts_code'], data['stock_name'],
                data['cost_price'], data['quantity']
            )
            if result['success']:
                self.refresh_portfolio()
                QMessageBox.information(self, '成功', result['message'])
            else:
                QMessageBox.warning(self, '失败', result['message'])

    def _remove_stock(self, ts_code):
        """删除持仓"""
        reply = QMessageBox.question(self, '确认', '确定要删除该持仓吗？')
        if reply == QMessageBox.StandardButton.Yes:
            self.portfolio_manager.remove_stock(ts_code)
            self.refresh_portfolio()

    def _generate_report(self):
        """生成持仓报告"""
        report, results, summary = self.portfolio_manager.generate_daily_report()
        self.report_text.setPlainText(report)


class AddStockDialog(QDialog):
    """添加持仓对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('添加持仓')
        self.setFixedWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText('如：000001')
        form.addRow('股票代码:', self.code_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText('如：平安银行')
        form.addRow('股票名称:', self.name_input)

        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText('如：10.50')
        form.addRow('成本价:', self.cost_input)

        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText('如：1000')
        form.addRow('持仓数量:', self.quantity_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 样式
        self.setStyleSheet("""
            QDialog { background-color: #161b22; }
            QLabel { color: #8b949e; font-size: 13px; }
            QLineEdit {
                background-color: #0d1117;
                color: #f0f6fc;
                border: 1px solid #30363d;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #58a6ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
        """)

    def get_data(self):
        """获取输入数据"""
        return {
            'ts_code': self.code_input.text().strip(),
            'stock_name': self.name_input.text().strip(),
            'cost_price': float(self.cost_input.text() or 0),
            'quantity': int(self.quantity_input.text() or 100),
        }
