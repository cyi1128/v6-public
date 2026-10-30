# -*- coding: utf-8 -*-
"""
交易辅助中心 V1.0
只新增辅助工具，不修改交易策略、选股、实时监控
功能：持仓管理、盈亏计算、仓位计算器、止损计算器、交易日志
"""
import os
import sys
import json
import threading
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox,
    QTabWidget, QHeaderView, QMessageBox, QFileDialog, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    STATUS_ERROR, STATUS_WARNING, STATUS_INFO,
)

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# 持仓数据文件
POSITION_FILE = os.path.join(DATA_DIR, 'trade_position.json')
# 交易记录文件
TRADE_LOG_FILE = os.path.join(DATA_DIR, 'trade_log.json')


def log_error(error):
    """记录错误日志"""
    try:
        log_file = os.path.join(LOG_DIR, 'trade_assistant_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {error}\n')
            f.write(traceback.format_exc() + '\n')
    except Exception:
        pass


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
    'yellow': ACCENT_GOLD,
}


class TradeAssistantPanel(QWidget):
    """交易辅助中心页面"""

    # 数据更新信号
    position_updated = pyqtSignal()
    # 行情更新信号
    quote_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._positions = []  # 持仓列表
        self._trade_log = []  # 交易记录
        self._account_capital = 100000.0  # 默认账户资金
        self._info_labels = {}  # 信息标签字典

        self._init_ui()
        self._load_position()
        self._load_trade_log()
        self._refresh_position_table()
        self._update_account_summary()

        print("[交易辅助] 交易辅助中心初始化完成")

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ========== 顶部：账户信息卡片 ==========
        self._create_account_card(main_layout)

        # ========== 中间：Tab切换（持仓/计算器/交易日志） ==========
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                background: {DARK_COLORS['bg_primary']};
            }}
            QTabBar::tab {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                padding: 8px 20px;
                border: 1px solid {DARK_COLORS['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background: {DARK_COLORS['bg_primary']};
                color: {DARK_COLORS['accent']};
                border-bottom: 2px solid {DARK_COLORS['accent']};
            }}
            QTabBar::tab:hover {{
                background: {DARK_COLORS['bg_tertiary']};
                color: {DARK_COLORS['text_primary']};
            }}
        """)

        # Tab1: 持仓管理
        self._create_position_tab()
        # Tab2: 仓位计算器
        self._create_calculator_tab()
        # Tab3: 交易日志
        self._create_trade_log_tab()

        main_layout.addWidget(self.tab_widget, 1)

    # ============================================================
    # 顶部账户信息卡片
    # ============================================================
    def _create_account_card(self, parent_layout):
        """创建账户信息卡片"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(30)

        # 账户资金
        self._create_info_item(layout, '💰 账户资金', 'account_capital', '100,000', DARK_COLORS['text_primary'])
        # 持仓市值
        self._create_info_item(layout, '📊 持仓市值', 'market_value', '0', DARK_COLORS['accent'])
        # 可用资金
        self._create_info_item(layout, '💵 可用资金', 'available', '100,000', DARK_COLORS['green'])
        # 总盈亏
        self._create_info_item(layout, '📈 总盈亏', 'total_pnl', '0', DARK_COLORS['text_secondary'])
        # 仓位比例
        self._create_info_item(layout, '📦 仓位', 'position_ratio', '0%', DARK_COLORS['orange'])

        parent_layout.addWidget(frame)

    def _create_info_item(self, parent_layout, title, key, value, color):
        """创建单个信息项"""
        layout = QVBoxLayout()
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-size: 22px; font-weight: bold; color: {color};')
        layout.addWidget(value_label)

        parent_layout.addLayout(layout)
        self._info_labels[key] = value_label

    # ============================================================
    # Tab1: 持仓管理
    # ============================================================
    def _create_position_tab(self):
        """创建持仓管理Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 操作按钮行
        btn_layout = QHBoxLayout()

        self.add_pos_btn = QPushButton('➕ 添加持仓')
        self.add_pos_btn.clicked.connect(self._add_position_dialog)
        self._style_button(self.add_pos_btn)
        btn_layout.addWidget(self.add_pos_btn)

        self.refresh_price_btn = QPushButton('🔄 刷新价格')
        self.refresh_price_btn.clicked.connect(self._refresh_prices)
        self._style_button(self.refresh_price_btn)
        btn_layout.addWidget(self.refresh_price_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # 持仓表格
        self.position_table = QTableWidget()
        self.position_table.setColumnCount(9)
        self.position_table.setHorizontalHeaderLabels([
            '股票代码', '股票名称', '成本价', '当前价', '持仓数量',
            '持仓金额', '盈亏金额', '收益率', '操作'
        ])
        self.position_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.position_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.position_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.position_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background: {DARK_COLORS['bg_tertiary']};
            }}
        """)
        layout.addWidget(self.position_table, 1)

        self.tab_widget.addTab(widget, '📊 持仓管理')

    def _style_button(self, btn):
        """设置按钮样式"""
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['text_primary']};
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {DARK_COLORS['border']};
            }}
        """)

    def _add_position_dialog(self):
        """添加持仓对话框"""
        # 简单的输入对话框
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle('添加持仓')
        dialog.setFixedWidth(350)
        dialog.setStyleSheet(f'background: {DARK_COLORS["bg_secondary"]}; color: {DARK_COLORS["text_primary"]};')

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 股票代码
        layout.addWidget(QLabel('股票代码：'))
        code_input = QLineEdit()
        code_input.setPlaceholderText('如：000001')
        code_input.setStyleSheet(self._input_style())
        layout.addWidget(code_input)

        # 股票名称
        layout.addWidget(QLabel('股票名称：'))
        name_input = QLineEdit()
        name_input.setPlaceholderText('如：平安银行')
        name_input.setStyleSheet(self._input_style())
        layout.addWidget(name_input)

        # 成本价
        layout.addWidget(QLabel('成本价：'))
        cost_input = QDoubleSpinBox()
        cost_input.setRange(0.01, 10000)
        cost_input.setDecimals(2)
        cost_input.setValue(10.00)
        cost_input.setStyleSheet(self._input_style())
        layout.addWidget(cost_input)

        # 持仓数量
        layout.addWidget(QLabel('持仓数量（股）：'))
        qty_input = QSpinBox()
        qty_input.setRange(1, 10000000)
        qty_input.setValue(100)
        qty_input.setStyleSheet(self._input_style())
        layout.addWidget(qty_input)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('确定')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            code = code_input.text().strip()
            name = name_input.text().strip()
            cost = cost_input.value()
            qty = qty_input.value()

            if not code or not name:
                QMessageBox.warning(self, '提示', '请填写股票代码和名称')
                return

            # 添加持仓
            position = {
                'code': code,
                'name': name,
                'cost_price': cost,
                'current_price': cost,  # 默认当前价=成本价
                'quantity': qty,
                'add_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self._positions.append(position)
            self._save_position()
            self._refresh_position_table()
            self._update_account_summary()

            # 记录交易日志
            self._add_trade_log(code, name, '买入', cost, qty, '建仓')

            QMessageBox.information(self, '成功', f'已添加持仓：{name}({code})')

    def _input_style(self):
        """输入框样式"""
        return f"""
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 4px;
                color: {DARK_COLORS['text_primary']};
                padding: 6px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border-color: {DARK_COLORS['accent']};
            }}
        """

    def _refresh_position_table(self):
        """刷新持仓表格"""
        self.position_table.setRowCount(len(self._positions))

        for row, pos in enumerate(self._positions):
            code = pos.get('code', '')
            name = pos.get('name', '')
            cost = pos.get('cost_price', 0)
            current = pos.get('current_price', cost)
            qty = pos.get('quantity', 0)

            # 计算
            amount = current * qty  # 持仓金额
            cost_amount = cost * qty  # 成本金额
            pnl = (current - cost) * qty  # 盈亏金额
            pnl_ratio = (pnl / cost_amount * 100) if cost_amount > 0 else 0  # 收益率

            # 填充表格
            self._set_table_item(row, 0, code)
            self._set_table_item(row, 1, name)
            self._set_table_item(row, 2, f'{cost:.2f}')
            self._set_table_item(row, 3, f'{current:.2f}')
            self._set_table_item(row, 4, str(qty))
            self._set_table_item(row, 5, f'{amount:.2f}')

            # 盈亏金额（红涨绿跌）
            pnl_item = QTableWidgetItem(f'{pnl:+.2f}')
            pnl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if pnl >= 0:
                pnl_item.setForeground(QColor(DARK_COLORS['red']))
            else:
                pnl_item.setForeground(QColor(DARK_COLORS['green']))
            self.position_table.setItem(row, 6, pnl_item)

            # 收益率
            ratio_item = QTableWidgetItem(f'{pnl_ratio:+.2f}%')
            ratio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if pnl_ratio >= 0:
                ratio_item.setForeground(QColor(DARK_COLORS['red']))
            else:
                ratio_item.setForeground(QColor(DARK_COLORS['green']))
            self.position_table.setItem(row, 7, ratio_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            del_btn = QPushButton('删除')
            del_btn.setFixedSize(50, 24)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {DARK_COLORS['red']};
                    border: none;
                    border-radius: 4px;
                    color: white;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: #da3633;
                }}
            """)
            del_btn.clicked.connect(lambda checked, r=row: self._delete_position(r))
            btn_layout.addWidget(del_btn)
            btn_layout.addStretch()

            self.position_table.setCellWidget(row, 8, btn_widget)

    def _set_table_item(self, row, col, text):
        """设置表格项"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_table.setItem(row, col, item)

    def _delete_position(self, row):
        """删除持仓"""
        if row < 0 or row >= len(self._positions):
            return

        pos = self._positions[row]
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定删除持仓 {pos["name"]}({pos["code"]}) 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self._positions[row]
            self._save_position()
            self._refresh_position_table()
            self._update_account_summary()

    def _refresh_prices(self):
        """刷新持仓价格"""
        if not self._positions:
            QMessageBox.information(self, '提示', '暂无持仓')
            return

        self.refresh_price_btn.setEnabled(False)
        self.refresh_price_btn.setText('刷新中...')

        def _do():
            try:
                # 使用已有行情接口获取价格
                from utils.fast_realtime import get_realtime_prices_tencent

                updated = 0
                for pos in self._positions:
                    try:
                        code = pos['code']
                        quote = get_realtime_prices_tencent([code]).get(code)
                        if quote and 'price' in quote:
                            pos['current_price'] = float(quote['price'])
                            updated += 1
                    except Exception:
                        continue

                self.position_updated.emit()
                print(f"[交易辅助] 价格刷新完成，更新{updated}只")

            except Exception as e:
                log_error(str(e))
                print(f"[交易辅助] 价格刷新失败: {e}")

        threading.Thread(target=_do, daemon=True).start()

        # 用信号更新UI
        self.position_updated.connect(self._on_price_refreshed)

    def _on_price_refreshed(self):
        """价格刷新完成"""
        self._save_position()
        self._refresh_position_table()
        self._update_account_summary()
        self.refresh_price_btn.setEnabled(True)
        self.refresh_price_btn.setText('🔄 刷新价格')

    def _update_account_summary(self):
        """更新账户汇总信息"""
        total_market_value = 0
        total_cost = 0
        total_pnl = 0

        for pos in self._positions:
            cost = pos.get('cost_price', 0)
            current = pos.get('current_price', cost)
            qty = pos.get('quantity', 0)
            total_market_value += current * qty
            total_cost += cost * qty
            total_pnl += (current - cost) * qty

        available = self._account_capital - total_cost + total_pnl
        position_ratio = (total_market_value / self._account_capital * 100) if self._account_capital > 0 else 0

        # 更新标签
        self._info_labels['account_capital'].setText(f'{self._account_capital:,.0f}')
        self._info_labels['market_value'].setText(f'{total_market_value:,.2f}')
        self._info_labels['available'].setText(f'{available:,.2f}')

        # 总盈亏
        pnl_label = self._info_labels['total_pnl']
        pnl_label.setText(f'{total_pnl:+,.2f}')
        if total_pnl >= 0:
            pnl_label.setStyleSheet(f'font-size: 22px; font-weight: bold; color: {DARK_COLORS["red"]};')
        else:
            pnl_label.setStyleSheet(f'font-size: 22px; font-weight: bold; color: {DARK_COLORS["green"]};')

        # 仓位比例
        self._info_labels['position_ratio'].setText(f'{position_ratio:.1f}%')

    # ============================================================
    # Tab2: 仓位计算器
    # ============================================================
    def _create_calculator_tab(self):
        """创建计算器Tab"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 左侧：仓位计算器
        left_frame = QFrame()
        left_frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(15)

        title1 = QLabel('📐 仓位计算器')
        title1.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        left_layout.addWidget(title1)

        # 账户资金
        left_layout.addWidget(QLabel('账户资金（元）：'))
        self.calc_capital = QDoubleSpinBox()
        self.calc_capital.setRange(1000, 10000000)
        self.calc_capital.setValue(100000)
        self.calc_capital.setStyleSheet(self._input_style())
        left_layout.addWidget(self.calc_capital)

        # 风险比例
        left_layout.addWidget(QLabel('单票风险比例（%）：'))
        self.calc_risk = QDoubleSpinBox()
        self.calc_risk.setRange(0.1, 100)
        self.calc_risk.setValue(2.0)
        self.calc_risk.setStyleSheet(self._input_style())
        left_layout.addWidget(self.calc_risk)

        # 买入价格
        left_layout.addWidget(QLabel('买入价格（元）：'))
        self.calc_buy_price = QDoubleSpinBox()
        self.calc_buy_price.setRange(0.01, 10000)
        self.calc_buy_price.setValue(10.00)
        self.calc_buy_price.setStyleSheet(self._input_style())
        left_layout.addWidget(self.calc_buy_price)

        # 止损价格
        left_layout.addWidget(QLabel('止损价格（元）：'))
        self.calc_stop_price = QDoubleSpinBox()
        self.calc_stop_price.setRange(0.01, 10000)
        self.calc_stop_price.setValue(9.50)
        self.calc_stop_price.setStyleSheet(self._input_style())
        left_layout.addWidget(self.calc_stop_price)

        # 计算按钮
        calc_btn = QPushButton('🧮 计算')
        calc_btn.clicked.connect(self._calculate_position)
        self._style_button(calc_btn)
        left_layout.addWidget(calc_btn)

        # 结果
        self.calc_result = QLabel('点击计算查看结果')
        self.calc_result.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]}; line-height: 1.8;')
        self.calc_result.setWordWrap(True)
        left_layout.addWidget(self.calc_result)

        left_layout.addStretch()
        layout.addWidget(left_frame, 1)

        # 右侧：止损计算器
        right_frame = QFrame()
        right_frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(15)

        title2 = QLabel('🛡️ 止损计算器')
        title2.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        right_layout.addWidget(title2)

        # 买入价格
        right_layout.addWidget(QLabel('买入价格（元）：'))
        self.stop_buy_price = QDoubleSpinBox()
        self.stop_buy_price.setRange(0.01, 10000)
        self.stop_buy_price.setValue(20.00)
        self.stop_buy_price.setStyleSheet(self._input_style())
        right_layout.addWidget(self.stop_buy_price)

        # 止损比例
        right_layout.addWidget(QLabel('止损比例（%）：'))
        self.stop_ratio = QDoubleSpinBox()
        self.stop_ratio.setRange(0.1, 50)
        self.stop_ratio.setValue(5.0)
        self.stop_ratio.setStyleSheet(self._input_style())
        right_layout.addWidget(self.stop_ratio)

        # 计算按钮
        stop_btn = QPushButton('🧮 计算止损')
        stop_btn.clicked.connect(self._calculate_stop_loss)
        self._style_button(stop_btn)
        right_layout.addWidget(stop_btn)

        # 结果
        self.stop_result = QLabel('点击计算查看结果')
        self.stop_result.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_secondary"]}; line-height: 1.8;')
        self.stop_result.setWordWrap(True)
        right_layout.addWidget(self.stop_result)

        right_layout.addStretch()
        layout.addWidget(right_frame, 1)

        self.tab_widget.addTab(widget, '🧮 计算器')

    def _calculate_position(self):
        """计算仓位"""
        try:
            capital = self.calc_capital.value()
            risk_ratio = self.calc_risk.value() / 100
            buy_price = self.calc_buy_price.value()
            stop_price = self.calc_stop_price.value()

            if buy_price <= stop_price:
                QMessageBox.warning(self, '提示', '止损价格必须低于买入价格')
                return

            # 最大亏损
            max_loss = capital * risk_ratio
            # 每股亏损
            per_share_loss = buy_price - stop_price
            # 买入数量
            buy_quantity = int(max_loss / per_share_loss)
            # 取整到100股
            buy_quantity = (buy_quantity // 100) * 100
            if buy_quantity < 100:
                buy_quantity = 0

            # 买入金额
            buy_amount = buy_quantity * buy_price
            # 仓位比例
            position_ratio = (buy_amount / capital * 100) if capital > 0 else 0

            result = f"""
<b>计算结果：</b>

💰 最大亏损金额：{max_loss:,.2f} 元
（账户资金 × 风险比例）

📊 建议买入金额：{buy_amount:,.2f} 元
📈 建议买入数量：{buy_quantity:,} 股
📦 占用仓位：{position_ratio:.1f}%

💡 说明：
即使止损触发，最大亏损也不会超过 {max_loss:,.2f} 元
（占账户资金的 {risk_ratio*100:.1f}%）
            """.strip()

            self.calc_result.setText(result)
            self.calc_result.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_primary"]}; line-height: 1.8;')

        except Exception as e:
            log_error(str(e))
            QMessageBox.critical(self, '错误', f'计算失败：{e}')

    def _calculate_stop_loss(self):
        """计算止损价"""
        try:
            buy_price = self.stop_buy_price.value()
            ratio = self.stop_ratio.value() / 100

            stop_price = buy_price * (1 - ratio)
            max_loss_per_share = buy_price - stop_price

            result = f"""
<b>计算结果：</b>

🛒 买入价格：{buy_price:.2f} 元
📉 止损价格：{stop_price:.2f} 元
💸 每股最大亏损：{max_loss_per_share:.2f} 元
📊 亏损比例：{ratio*100:.1f}%

💡 说明：
当股价跌到 {stop_price:.2f} 元时，
应坚决止损，避免更大损失。
            """.strip()

            self.stop_result.setText(result)
            self.stop_result.setStyleSheet(f'font-size: 13px; color: {DARK_COLORS["text_primary"]}; line-height: 1.8;')

        except Exception as e:
            log_error(str(e))
            QMessageBox.critical(self, '错误', f'计算失败：{e}')

    # ============================================================
    # Tab3: 交易日志
    # ============================================================
    def _create_trade_log_tab(self):
        """创建交易日志Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 操作按钮行
        btn_layout = QHBoxLayout()

        export_btn = QPushButton('📤 导出CSV')
        export_btn.clicked.connect(self._export_trade_log)
        self._style_button(export_btn)
        btn_layout.addWidget(export_btn)

        clear_btn = QPushButton('🗑️ 清空记录')
        clear_btn.clicked.connect(self._clear_trade_log)
        self._style_button(clear_btn)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # 交易记录表格
        self.trade_table = QTableWidget()
        self.trade_table.setColumnCount(6)
        self.trade_table.setHorizontalHeaderLabels([
            '时间', '股票代码', '股票名称', '方向', '价格', '数量', '备注'
        ])
        self.trade_table.setColumnCount(7)
        self.trade_table.setHorizontalHeaderLabels([
            '时间', '股票代码', '股票名称', '方向', '价格', '数量', '备注'
        ])
        self.trade_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trade_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trade_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_secondary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 8px;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
        """)
        layout.addWidget(self.trade_table, 1)

        self.tab_widget.addTab(widget, '📝 交易日志')

    def _add_trade_log(self, code, name, direction, price, quantity, remark=''):
        """添加交易记录"""
        log = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'code': code,
            'name': name,
            'direction': direction,
            'price': price,
            'quantity': quantity,
            'remark': remark
        }
        self._trade_log.insert(0, log)  # 最新的在最前面
        self._save_trade_log()
        self._refresh_trade_log_table()

    def _refresh_trade_log_table(self):
        """刷新交易日志表格"""
        self.trade_table.setRowCount(len(self._trade_log))

        for row, log in enumerate(self._trade_log):
            self._set_trade_item(row, 0, log.get('time', ''))
            self._set_trade_item(row, 1, log.get('code', ''))
            self._set_trade_item(row, 2, log.get('name', ''))

            # 方向（买入红，卖出绿）
            direction = log.get('direction', '')
            dir_item = QTableWidgetItem(direction)
            dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if direction == '买入':
                dir_item.setForeground(QColor(DARK_COLORS['red']))
            else:
                dir_item.setForeground(QColor(DARK_COLORS['green']))
            self.trade_table.setItem(row, 3, dir_item)

            self._set_trade_item(row, 4, f"{log.get('price', 0):.2f}")
            self._set_trade_item(row, 5, str(log.get('quantity', 0)))
            self._set_trade_item(row, 6, log.get('remark', ''))

    def _set_trade_item(self, row, col, text):
        """设置交易表格项"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trade_table.setItem(row, col, item)

    def _export_trade_log(self):
        """导出交易日志为CSV"""
        if not self._trade_log:
            QMessageBox.information(self, '提示', '暂无交易记录')
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出交易日志', 'trade_log.csv', 'CSV文件 (*.csv)'
        )
        if not file_path:
            return

        try:
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['时间', '股票代码', '股票名称', '方向', '价格', '数量', '备注'])
                for log in self._trade_log:
                    writer.writerow([
                        log.get('time', ''),
                        log.get('code', ''),
                        log.get('name', ''),
                        log.get('direction', ''),
                        log.get('price', ''),
                        log.get('quantity', ''),
                        log.get('remark', '')
                    ])
            QMessageBox.information(self, '成功', f'交易日志已导出到：\n{file_path}')
        except Exception as e:
            log_error(str(e))
            QMessageBox.critical(self, '错误', f'导出失败：{e}')

    def _clear_trade_log(self):
        """清空交易日志"""
        reply = QMessageBox.question(
            self, '确认清空',
            '确定要清空所有交易记录吗？此操作不可恢复！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._trade_log = []
            self._save_trade_log()
            self._refresh_trade_log_table()

    # ============================================================
    # 数据持久化
    # ============================================================
    def _load_position(self):
        """加载持仓数据"""
        try:
            if os.path.exists(POSITION_FILE):
                with open(POSITION_FILE, 'r', encoding='utf-8') as f:
                    self._positions = json.load(f)
                print(f"[交易辅助] 加载持仓数据，共{len(self._positions)}只")
        except Exception as e:
            log_error(str(e))
            print(f"[交易辅助] 加载持仓数据失败: {e}")
            self._positions = []

    def _save_position(self):
        """保存持仓数据"""
        try:
            with open(POSITION_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._positions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_error(str(e))
            print(f"[交易辅助] 保存持仓数据失败: {e}")

    def _load_trade_log(self):
        """加载交易日志"""
        try:
            if os.path.exists(TRADE_LOG_FILE):
                with open(TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
                    self._trade_log = json.load(f)
                print(f"[交易辅助] 加载交易日志，共{len(self._trade_log)}条")
        except Exception as e:
            log_error(str(e))
            print(f"[交易辅助] 加载交易日志失败: {e}")
            self._trade_log = []

    def _save_trade_log(self):
        """保存交易日志"""
        try:
            with open(TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._trade_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_error(str(e))
            print(f"[交易辅助] 保存交易日志失败: {e}")
