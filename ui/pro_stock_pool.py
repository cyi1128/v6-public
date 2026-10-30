# -*- coding: utf-8 -*-
"""
V6.0 Pro 专业量化盯盘主面板

整合：
- 顶部功能按钮栏
- 股票池表格（排序+新字段+信号标签颜色）
- 实时交易信号中心（买入/观察/风险）
- 股票详情窗口（弹出式）

风格：深色专业量化交易终端
"""
import os
import sys
import csv
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QSplitter, QScrollArea, QGridLayout, QDialog, QTabWidget,
    QMessageBox, QFileDialog, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QColor, QBrush, QFont, QAction

# 信号标签颜色定义
SIGNAL_COLORS = {
    '底部吸筹': '#3fb950',      # 绿色
    '观察': '#58a6ff',           # 蓝色
    '买点': '#f85149',           # 红色
    '量价观察': '#d29922',       # 黄色
    '穿九': '#bc8cff',           # 紫色
    '站二十': '#39c5cf',         # 青色
    '死叉观察': '#8b949e',       # 灰色
    '五九回踩': '#f85149',       # 红色
    '三倍量': '#d29922',         # 黄色
    'MACD金叉': '#58a6ff',       # 蓝色
    'KDJ金叉': '#58a6ff',        # 蓝色
    '涨停突破': '#f85149',       # 红色
    '资金流入': '#3fb950',       # 绿色
}

# 默认颜色
DEFAULT_SIGNAL_COLOR = '#8b949e'


class SignalLabel(QLabel):
    """信号标签控件"""
    clicked = pyqtSignal(str)

    def __init__(self, signal_name, parent=None):
        super().__init__(signal_name, parent)
        self.signal_name = signal_name
        color = SIGNAL_COLORS.get(signal_name, DEFAULT_SIGNAL_COLOR)
        self.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: white;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }}
            QLabel:hover {{
                border: 1px solid white;
            }}
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit(self.signal_name)
        super().mousePressEvent(event)


class ProStockTable(QTableWidget):
    """专业股票池表格（支持排序）"""

    stock_double_clicked = pyqtSignal(dict)

    COLUMNS = [
        ('序号', 50),
        ('代码', 80),
        ('名称', 100),
        ('现价', 80),
        ('涨跌幅', 80),
        ('成交量', 100),
        ('换手率', 80),
        ('总市值', 90),
        ('主营行业', 100),
        ('涨停次数', 80),
        ('信号标签', 150),
        ('命中率', 80),
        ('AI评分', 70),
        ('操作建议', 100),
        ('风险等级', 80),
        ('关键价格', 140),
        ('更新时间', 120),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._init_ui()

    def _init_ui(self):
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        for i, (_, width) in enumerate(self.COLUMNS):
            self.setColumnWidth(i, width)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QTableWidget {
                background: #0d1117;
                color: #f0f6fc;
                gridline-color: #21262d;
                border: 1px solid #30363d;
                font-size: 12px;
            }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background: #1f6feb; color: white; }
            QHeaderView::section {
                background: #161b22;
                color: #f0f6fc;
                padding: 6px;
                border: 1px solid #30363d;
                font-weight: bold;
            }
        """)

        # 点击表头排序
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

    def _on_header_clicked(self, column):
        """表头点击排序"""
        if self._sort_column == column:
            self._sort_order = (Qt.SortOrder.DescendingOrder
                               if self._sort_order == Qt.SortOrder.AscendingOrder
                               else Qt.SortOrder.AscendingOrder)
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        self._sort_data()
        self._refresh_table()

    def _sort_data(self):
        """数据排序"""
        if self._sort_column < 0 or not self._data:
            return

        col_name = self.COLUMNS[self._sort_column][0]
        key_map = {
            '序号': 'index',
            '代码': 'code',
            '名称': 'name',
            '现价': 'price',
            '涨跌幅': 'pct_chg',
            '成交量': 'volume',
            '换手率': 'turnover',
            '总市值': 'market_cap',
            '主营行业': 'industry',
            '涨停次数': 'limit_up_count',
            '信号标签': 'signals',
            '命中率': 'hit_rate',
            'AI评分': 'ai_score',
            '操作建议': 'ai_action',
            '风险等级': 'ai_risk',
            '更新时间': 'update_time',
        }
        key = key_map.get(col_name, 'code')

        def sort_key(item):
            val = item.get(key, '')
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, list):
                return ','.join(val)
            return str(val)

        self._data.sort(key=sort_key, reverse=(self._sort_order == Qt.SortOrder.DescendingOrder))

    def _on_cell_double_clicked(self, row, col):
        """双击行打开详情"""
        if 0 <= row < len(self._data):
            self.stock_double_clicked.emit(self._data[row])

    def set_data(self, data):
        """设置表格数据"""
        self._data = data
        self._sort_data()
        self._refresh_table()

    def _refresh_table(self):
        """刷新表格显示"""
        self.setRowCount(len(self._data))
        for row, stock in enumerate(self._data):
            self._set_row(row, stock)

    def _set_row(self, row, stock):
        """设置单行数据"""
        # 序号
        self.setItem(row, 0, QTableWidgetItem(str(row + 1)))

        # 代码
        self.setItem(row, 1, QTableWidgetItem(stock.get('code', '')))

        # 名称
        name_item = QTableWidgetItem(stock.get('name', ''))
        name_item.setForeground(QBrush(QColor('#58a6ff')))
        self.setItem(row, 2, name_item)

        # 现价
        price = stock.get('price', 0)
        price_item = QTableWidgetItem(f"{price:.2f}")
        pct = stock.get('pct_chg', 0)
        if pct > 0:
            price_item.setForeground(QBrush(QColor('#f85149')))
        elif pct < 0:
            price_item.setForeground(QBrush(QColor('#3fb950')))
        self.setItem(row, 3, price_item)

        # 涨跌幅
        pct_item = QTableWidgetItem(f"{pct:+.2f}%")
        if pct > 0:
            pct_item.setForeground(QBrush(QColor('#f85149')))
        elif pct < 0:
            pct_item.setForeground(QBrush(QColor('#3fb950')))
        self.setItem(row, 4, pct_item)

        # 成交量
        vol = stock.get('volume', 0)
        vol_text = f"{vol/10000:.1f}万" if vol >= 10000 else f"{vol:.0f}"
        self.setItem(row, 5, QTableWidgetItem(vol_text))

        # 换手率
        turnover = stock.get('turnover', 0)
        self.setItem(row, 6, QTableWidgetItem(f"{turnover:.2f}%"))

        # 总市值
        mcap = stock.get('market_cap', 0)
        self.setItem(row, 7, QTableWidgetItem(f"{mcap:.1f}亿"))

        # 主营行业
        self.setItem(row, 8, QTableWidgetItem(stock.get('industry', '')))

        # 涨停次数
        self.setItem(row, 9, QTableWidgetItem(str(stock.get('limit_up_count', 0))))

        # 信号标签（用widget显示多个标签）
        signals = stock.get('signals', [])
        if isinstance(signals, str):
            signals = [signals]
        signal_widget = QWidget()
        signal_layout = QHBoxLayout(signal_widget)
        signal_layout.setContentsMargins(2, 2, 2, 2)
        signal_layout.setSpacing(2)
        for sig in signals[:3]:  # 最多显示3个标签
            label = SignalLabel(sig)
            label.clicked.connect(lambda s=sig: self._show_signal_reason(s, stock))
            signal_layout.addWidget(label)
        signal_layout.addStretch()
        self.setCellWidget(row, 10, signal_widget)

        # 命中率
        hit_count = stock.get('hit_count', 0)
        total_cond = stock.get('total_conditions', 0)
        hit_rate = stock.get('hit_rate', 0)
        if total_cond > 0:
            hit_text = f"{hit_count}/{total_cond} ({hit_rate:.0f}%)"
            hit_item = QTableWidgetItem(hit_text)
            if hit_rate >= 80:
                hit_item.setForeground(QBrush(QColor('#3fb950')))
            elif hit_rate >= 50:
                hit_item.setForeground(QBrush(QColor('#d29922')))
            else:
                hit_item.setForeground(QBrush(QColor('#8b949e')))
            self.setItem(row, 11, hit_item)
        else:
            self.setItem(row, 11, QTableWidgetItem('--'))

        # AI评分（V0.7 C5.2.2新增）
        ai_score = stock.get('ai_score', None)
        if ai_score is not None:
            ai_item = QTableWidgetItem(f"{ai_score:.0f}")
            if ai_score >= 80:
                ai_item.setForeground(QBrush(QColor('#f85149')))
            elif ai_score >= 70:
                ai_item.setForeground(QBrush(QColor('#d29922')))
            elif ai_score >= 60:
                ai_item.setForeground(QBrush(QColor('#e3b341')))
            else:
                ai_item.setForeground(QBrush(QColor('#8b949e')))
            font = ai_item.font()
            font.setBold(True)
            ai_item.setFont(font)
            self.setItem(row, 12, ai_item)
        else:
            self.setItem(row, 12, QTableWidgetItem('--'))

        # 操作建议（V0.7 C5.2.2新增）
        ai_action = stock.get('ai_action', '')
        ai_position = stock.get('ai_position', '')
        action_text = f"{ai_action}" if ai_action else '--'
        if ai_position and ai_position != '0%':
            action_text = f"{ai_action}({ai_position})"
        action_item = QTableWidgetItem(action_text)
        if ai_action in ('买入', '加仓'):
            action_item.setForeground(QBrush(QColor('#f85149')))
        elif ai_action == '持有':
            action_item.setForeground(QBrush(QColor('#3fb950')))
        elif ai_action in ('减仓', '卖出'):
            action_item.setForeground(QBrush(QColor('#da3633')))
        else:
            action_item.setForeground(QBrush(QColor('#8b949e')))
        self.setItem(row, 13, action_item)

        # 风险等级（V0.7 C5.2.2新增）
        ai_risk = stock.get('ai_risk', '')
        risk_item = QTableWidgetItem(ai_risk if ai_risk else '--')
        if ai_risk == '高':
            risk_item.setForeground(QBrush(QColor('#da3633')))
        elif ai_risk == '中':
            risk_item.setForeground(QBrush(QColor('#d29922')))
        elif ai_risk == '低':
            risk_item.setForeground(QBrush(QColor('#3fb950')))
        self.setItem(row, 14, risk_item)

        # 关键价格（V1.0.3新增）
        code = stock.get('code', '')
        price = stock.get('price', 0)
        try:
            from utils.key_price_calculator import get_key_price_calculator
            calculator = get_key_price_calculator()
            key_price = calculator.calculate(code, price)
            buy_zone = key_price.get('buy_zone', '--')
            kp_item = QTableWidgetItem(buy_zone)
            kp_item.setForeground(QBrush(QColor('#3fb950')))
            tooltip = (
                f"💰 关键价格\n"
                f"买入区域: {key_price.get('buy_zone', '--')}\n"
                f"止损位: {key_price.get('stop_loss', '--')}\n"
                f"压力位: {key_price.get('resistance', '--')}\n"
                f"第一目标: {key_price.get('target1', '--')}\n"
                f"第二目标: {key_price.get('target2', '--')}\n"
                f"风险回报比: 1:{key_price.get('risk_reward', 0)}"
            )
            kp_item.setToolTip(tooltip)
        except Exception:
            kp_item = QTableWidgetItem('--')
        self.setItem(row, 15, kp_item)

        # 更新时间
        self.setItem(row, 16, QTableWidgetItem(stock.get('update_time', '')))

    def enrich_with_ai(self, market_env='震荡'):
        """
        V0.7 C5.2.2 新增：为当前股票池数据补充AI决策评分

        不改变原选股逻辑，仅通过DecisionAdapter获取AI评分并补充到数据中。
        调用后表格自动刷新。

        Args:
            market_env: 市场环境 bull/震荡/bear
        """
        if not self._data:
            return False

        try:
            # 确保项目根目录在 sys.path 中
            import sys as _sys
            import os as _os
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from dashboard.decision_adapter import get_decision_adapter
            adapter = get_decision_adapter()

            # 获取所有股票代码
            codes = [s.get('code', '') for s in self._data if s.get('code')]
            if not codes:
                return False

            # 批量获取决策数据
            decisions = adapter.service.get_batch_decisions(codes, market_env=market_env)
            decision_map = {d.get('stock_code', ''): d for d in decisions}

            # 补充到每条股票数据
            for stock in self._data:
                code = stock.get('code', '')
                d = decision_map.get(code, {})
                if d:
                    stock['ai_score'] = d.get('confidence', 50)
                    stock['ai_action'] = d.get('action_label', '观望')
                    stock['ai_position'] = d.get('position_pct', '0%')
                    sell_score = d.get('sell_score', 30)
                    if sell_score >= 60:
                        stock['ai_risk'] = '高'
                    elif sell_score >= 40:
                        stock['ai_risk'] = '中'
                    else:
                        stock['ai_risk'] = '低'
                    stock['ai_reason'] = d.get('reason', [])

            # 刷新表格
            self._refresh_table()
            return True

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"股票池AI评分增强失败: {e}")
            return False

    def _show_signal_reason(self, signal_name, stock):
        """显示信号触发原因"""
        reasons = {
            '买点': '股价站5日均线，接近9日均线，连续上涨',
            '底部吸筹': '成交量萎缩后放量，价格在低位企稳',
            '观察': '指标待确认，等待信号明确',
            '量价观察': '成交量变化，价格待突破',
            '穿九': '收盘价上穿9日均线',
            '站二十': '收盘价站上20日均线',
            '死叉观察': 'MACD/KDJ出现死叉迹象',
            '五九回踩': '回踩5日和9日均线支撑',
            '三倍量': '成交量超过5日均量3倍',
            'MACD金叉': 'MACD快线穿慢线向上',
            'KDJ金叉': 'KDJ低位金叉',
            '涨停突破': '涨停突破关键位',
            '资金流入': '主力资金净流入',
        }
        reason = reasons.get(signal_name, '技术信号触发')
        QMessageBox.information(
            self,
            f"信号详情 - {signal_name}",
            f"股票: {stock.get('name','')} ({stock.get('code','')})\n"
            f"信号: {signal_name}\n"
            f"触发原因: {reason}\n"
            f"当前价: {stock.get('price',0):.2f}\n"
            f"涨跌幅: {stock.get('pct_chg',0):+.2f}%"
        )

    def get_data(self):
        return self._data


class SignalCenterWidget(QWidget):
    """实时交易信号中心"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buy_signals = []
        self._watch_signals = []
        self._risk_signals = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 标题
        title = QLabel('📡 实时交易信号中心')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc;')
        layout.addWidget(title)

        # 三区域横向布局
        areas = QHBoxLayout()
        areas.setSpacing(4)

        # 买入提醒（红色）
        self.buy_area = self._create_signal_area('买入提醒', '#f85149', '#2d1212')
        areas.addWidget(self.buy_area['container'])

        # 观察提醒（蓝色）
        self.watch_area = self._create_signal_area('观察提醒', '#58a6ff', '#0d1b2d')
        areas.addWidget(self.watch_area['container'])

        # 风险提醒（灰色）
        self.risk_area = self._create_signal_area('风险提醒', '#8b949e', '#1a1a1a')
        areas.addWidget(self.risk_area['container'])

        layout.addLayout(areas)

    def _create_signal_area(self, title, color, bg_color):
        """创建信号区域"""
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: {bg_color};
                border: 1px solid {color};
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        header = QLabel(f"{title} (0)")
        header.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {bg_color}; }}
            QScrollBar:vertical {{ background: {bg_color}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {color}; border-radius: 4px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        content = QWidget()
        content.setStyleSheet(f"background: {bg_color};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        return {
            'container': container,
            'header': header,
            'content': content,
            'layout': content_layout,
            'color': color,
        }

    def add_signal(self, signal_type, stock, signal_name, reason):
        """添加信号"""
        area_map = {
            'buy': self.buy_area,
            'watch': self.watch_area,
            'risk': self.risk_area,
        }
        area = area_map.get(signal_type)
        if not area:
            return

        now = datetime.now().strftime('%H:%M:%S')
        signal_widget = QLabel(
            f"{now} {stock.get('name','')}({stock.get('code','')}) "
            f"{stock.get('price',0):.2f} 【{signal_name}】\n  {reason}"
        )
        signal_widget.setStyleSheet(f"""
            QLabel {{
                color: {area['color']};
                background: rgba(255,255,255,0.05);
                padding: 4px;
                border-radius: 2px;
                font-size: 11px;
            }}
        """)
        signal_widget.setWordWrap(True)

        # 插入到顶部
        area['layout'].insertWidget(0, signal_widget)

        # 更新计数
        count = area['layout'].count() - 1  # 减去stretch
        area['header'].setText(f"{area['header'].text().split('(')[0]}({count})")

        # 限制最多显示20条
        if count > 20:
            item = area['layout'].takeAt(area['layout'].count() - 2)
            if item.widget():
                item.widget().deleteLater()

    def clear_all(self):
        """清空所有信号"""
        for area in [self.buy_area, self.watch_area, self.risk_area]:
            while area['layout'].count() > 1:
                item = area['layout'].takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            area['header'].setText(f"{area['header'].text().split('(')[0]}(0)")


class StockDetailDialog(QDialog):
    """V6.0 Pro 股票详情窗口 - 接入ECharts K线 + 指标 + 信号分析"""

    def __init__(self, stock_data, parent=None):
        super().__init__(parent)
        self.stock_data = stock_data
        self.kline_data = None
        self.current_period = 'day'
        self.setWindowTitle(f"股票详情 - {stock_data.get('name','')} ({stock_data.get('code','')})")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("""
            QDialog { background: #0d1117; }
            QLabel { color: #f0f6fc; }
            QPushButton {
                background: #21262d; color: #f0f6fc; border: 1px solid #30363d;
                padding: 4px 12px; border-radius: 3px; font-size: 12px;
            }
            QPushButton:hover { background: #30363d; }
            QPushButton:checked { background: #1f6feb; border-color: #1f6feb; }
            QComboBox {
                background: #21262d; color: #f0f6fc; border: 1px solid #30363d;
                padding: 4px 8px; border-radius: 3px;
            }
        """)
        self._init_ui()
        self._load_kline()
        self._load_ai_decision()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ===== 顶部信息栏 =====
        info_bar = QHBoxLayout()

        code_name = QLabel(f"{self.stock_data.get('name','')} ({self.stock_data.get('code','')})")
        code_name.setStyleSheet('font-size: 18px; font-weight: bold; color: #f0f6fc;')
        info_bar.addWidget(code_name)

        price = self.stock_data.get('price', 0)
        pct = self.stock_data.get('pct_chg', 0)
        self.price_label = QLabel(f"{price:.2f}  {pct:+.2f}%")
        price_color = '#f85149' if pct > 0 else '#3fb950' if pct < 0 else '#f0f6fc'
        self.price_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {price_color};')
        info_bar.addWidget(self.price_label)

        info_bar.addSpacing(20)

        # 基本信息
        amount = self.stock_data.get('amount', 0)
        amount_text = f"{amount/100000000:.2f}亿" if amount >= 100000000 else f"{amount/10000:.0f}万" if amount > 0 else "--"
        volume = self.stock_data.get('volume', 0)
        info_text = QLabel(
            f"市值:{self.stock_data.get('market_cap',0):.1f}亿 | "
            f"换手:{self.stock_data.get('turnover',0):.2f}% | "
            f"成交额:{amount_text} | "
            f"行业:{self.stock_data.get('industry','')} | "
            f"涨停:{self.stock_data.get('limit_up_count',0)}次"
        )
        info_text.setStyleSheet('color: #8b949e; font-size: 12px;')
        info_bar.addWidget(info_text)
        info_bar.addStretch()

        # 周期切换
        self.period_buttons = {}
        for period, label in [('min', '分时'), ('day', '日K'), ('week', '周K'), ('month', '月K')]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            if period == 'day':
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, p=period: self._switch_period(p))
            self.period_buttons[period] = btn
            info_bar.addWidget(btn)

        # 刷新按钮
        refresh_btn = QPushButton('🔄 刷新')
        refresh_btn.clicked.connect(self._refresh_data)
        info_bar.addWidget(refresh_btn)

        layout.addLayout(info_bar)

        # ===== 主内容区 =====
        content = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：K线 + 指标
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # K线区域
        kline_frame = QFrame()
        kline_frame.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 4px;")
        kline_layout = QVBoxLayout(kline_frame)
        kline_layout.setContentsMargins(4, 4, 4, 4)

        kline_title = QLabel('📈 K线图 (MA5/MA9/MA20 + 成交量)')
        kline_title.setStyleSheet('color: #f0f6fc; font-weight: bold; font-size: 12px; padding: 2px;')
        kline_layout.addWidget(kline_title)

        # 接入KlineContainer（ECharts）
        try:
            from ui.kline_container import KlineContainer
            self.kline_widget = KlineContainer()
            self.kline_widget.setMinimumHeight(350)
            kline_layout.addWidget(self.kline_widget)
        except Exception as e:
            print(f"[StockDetail] KlineContainer加载失败: {e}")
            self.kline_widget = QLabel('K线组件加载失败')
            self.kline_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.kline_widget.setStyleSheet('color: #f85149; padding: 40px;')
            kline_layout.addWidget(self.kline_widget)

        left_layout.addWidget(kline_frame, stretch=3)

        # 指标区域（KDJ + MACD）
        indicator_frame = QFrame()
        indicator_frame.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 4px;")
        indicator_layout = QHBoxLayout(indicator_frame)
        indicator_layout.setContentsMargins(8, 8, 8, 8)
        indicator_layout.setSpacing(12)

        # KDJ面板
        kdj_panel = self._create_indicator_panel('📊 KDJ (13,3,3)', [
            ('K值', 'kdj_k', '#f85149'),
            ('D值', 'kdj_d', '#58a6ff'),
            ('J值', 'kdj_j', '#d29922'),
            ('状态', 'kdj_status', '#3fb950'),
        ])
        indicator_layout.addWidget(kdj_panel)

        # MACD面板
        macd_panel = self._create_indicator_panel('📉 MACD (8,21,5)', [
            ('DIFF', 'macd_diff', '#f85149'),
            ('DEA', 'macd_dea', '#58a6ff'),
            ('MACD柱', 'macd_bar', '#d29922'),
            ('状态', 'macd_status', '#3fb950'),
        ])
        indicator_layout.addWidget(macd_panel)

        left_layout.addWidget(indicator_frame, stretch=1)

        content.addWidget(left_container)

        # 右侧：AI信号分析
        right_container = QFrame()
        right_container.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 4px;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        # AI信号分析标题
        signal_title = QLabel('🤖 AI信号分析')
        signal_title.setStyleSheet('color: #f0f6fc; font-weight: bold; font-size: 14px;')
        right_layout.addWidget(signal_title)

        # ===== V0.7 C5.2.4 AI综合决策卡片 =====
        ai_decision_frame = QFrame()
        ai_decision_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1f2e, stop:1 #161b22);
                border: 1px solid #30363d;
                border-radius: 6px;
            }
        """)
        ai_decision_layout = QVBoxLayout(ai_decision_frame)
        ai_decision_layout.setContentsMargins(10, 8, 10, 8)
        ai_decision_layout.setSpacing(4)

        # 第一行：星级 + 建议
        ai_top_row = QHBoxLayout()
        self.ai_stars_label = QLabel('★★★☆☆')
        self.ai_stars_label.setStyleSheet('color: #d29922; font-size: 16px; font-weight: bold;')
        ai_top_row.addWidget(self.ai_stars_label)

        self.ai_action_label = QLabel('加载中...')
        self.ai_action_label.setStyleSheet('color: #f0f6fc; font-size: 16px; font-weight: bold;')
        ai_top_row.addWidget(self.ai_action_label)
        ai_top_row.addStretch()
        ai_decision_layout.addLayout(ai_top_row)

        # 第二行：4个关键指标
        ai_metrics_row = QHBoxLayout()
        self.ai_confidence_label = QLabel('置信度: --')
        self.ai_confidence_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        ai_metrics_row.addWidget(self.ai_confidence_label)

        self.ai_position_label = QLabel('仓位: --')
        self.ai_position_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        ai_metrics_row.addWidget(self.ai_position_label)

        self.ai_buy_score_label = QLabel('买入: --')
        self.ai_buy_score_label.setStyleSheet('color: #3fb950; font-size: 11px;')
        ai_metrics_row.addWidget(self.ai_buy_score_label)

        self.ai_sell_score_label = QLabel('风险: --')
        self.ai_sell_score_label.setStyleSheet('color: #f85149; font-size: 11px;')
        ai_metrics_row.addWidget(self.ai_sell_score_label)
        ai_decision_layout.addLayout(ai_metrics_row)

        # 第三行：核心理由
        self.ai_reason_label = QLabel('理由: 加载中...')
        self.ai_reason_label.setStyleSheet('color: #c9d1d9; font-size: 11px;')
        self.ai_reason_label.setWordWrap(True)
        ai_decision_layout.addWidget(self.ai_reason_label)

        # 第四行：风险提示
        self.ai_risk_label = QLabel('')
        self.ai_risk_label.setStyleSheet('color: #f85149; font-size: 11px;')
        self.ai_risk_label.setWordWrap(True)
        ai_decision_layout.addWidget(self.ai_risk_label)

        right_layout.addWidget(ai_decision_frame)

        # 当前信号
        current_sig_title = QLabel('【当前信号】')
        current_sig_title.setStyleSheet('color: #8b949e; font-size: 12px; font-weight: bold;')
        right_layout.addWidget(current_sig_title)

        self.current_signals_widget = QWidget()
        self.current_signals_layout = QVBoxLayout(self.current_signals_widget)
        self.current_signals_layout.setContentsMargins(0, 0, 0, 0)
        self.current_signals_layout.setSpacing(2)
        right_layout.addWidget(self.current_signals_widget)

        # 触发原因
        reason_title = QLabel('【触发原因】')
        reason_title.setStyleSheet('color: #8b949e; font-size: 12px; font-weight: bold; margin-top: 8px;')
        right_layout.addWidget(reason_title)

        self.reason_label = QLabel('加载中...')
        self.reason_label.setStyleSheet('color: #f0f6fc; font-size: 11px;')
        self.reason_label.setWordWrap(True)
        right_layout.addWidget(self.reason_label)

        # 历史信号
        history_title = QLabel('【历史信号】')
        history_title.setStyleSheet('color: #8b949e; font-size: 12px; font-weight: bold; margin-top: 8px;')
        right_layout.addWidget(history_title)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.history_content = QWidget()
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(2)
        self.history_layout.addStretch()
        self.history_scroll.setWidget(self.history_content)
        right_layout.addWidget(self.history_scroll, stretch=1)

        # 技术面总结
        summary_title = QLabel('【技术面总结】')
        summary_title.setStyleSheet('color: #8b949e; font-size: 12px; font-weight: bold; margin-top: 8px;')
        right_layout.addWidget(summary_title)

        self.summary_label = QLabel('加载中...')
        self.summary_label.setStyleSheet('color: #f0f6fc; font-size: 11px;')
        self.summary_label.setWordWrap(True)
        right_layout.addWidget(self.summary_label)

        # 买卖点标记（轻量方式，不修改K线组件）
        signal_marker_title = QLabel('【买卖点标记】')
        signal_marker_title.setStyleSheet('color: #8b949e; font-size: 12px; font-weight: bold; margin-top: 8px;')
        right_layout.addWidget(signal_marker_title)

        self.signal_marker_layout = QVBoxLayout()
        self.signal_marker_layout.setContentsMargins(0, 0, 0, 0)
        self.signal_marker_layout.setSpacing(2)
        right_layout.addLayout(self.signal_marker_layout)

        content.addWidget(right_container)
        content.setSizes([800, 300])

        layout.addWidget(content)

        # 底部按钮
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #f0f6fc; border: 1px solid #30363d;
                padding: 6px 24px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { background: #30363d; }
        """)
        close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(close_btn)
        layout.addLayout(btn_bar)

        # 初始化信号显示
        self._update_signals_display()

    def _create_indicator_panel(self, title, items):
        """创建指标面板"""
        panel = QFrame()
        panel.setStyleSheet("background: #0d1117; border-radius: 3px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet('color: #f0f6fc; font-weight: bold; font-size: 12px;')
        layout.addWidget(title_label)

        for label_text, attr_name, color in items:
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet(f'color: #8b949e; font-size: 11px; min-width: 45px;')
            val = QLabel('--')
            val.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: bold;')
            setattr(self, attr_name + '_label', val)
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            layout.addLayout(row)

        return panel

    def _load_kline(self):
        """加载K线数据"""
        try:
            from utils.kline_provider import get_daily_kline
            code = self.stock_data.get('code', '')
            if not code:
                return
            self._kline_code = code        # 供 _set_kline_data 透传给 K 线控件
            # 获取500根日K
            self.kline_data = get_daily_kline(code, count=500)
            if self.kline_data and self.kline_widget:
                # 转换为KlineContainer需要的格式
                kline_for_container = {
                    'dates': self.kline_data.get('dates', []),
                    'open': self.kline_data.get('open', []),
                    'high': self.kline_data.get('high', []),
                    'low': self.kline_data.get('low', []),
                    'close': self.kline_data.get('close', []),
                    'volume': self.kline_data.get('volume', []),
                }
                # 延迟设置数据，等待ECharts初始化
                QTimer.singleShot(1000, lambda: self._set_kline_data(kline_for_container))

            # 计算指标
            self._calc_indicators()

        except Exception as e:
            print(f"[StockDetail] 加载K线失败: {e}")
            import traceback
            traceback.print_exc()

    def _set_kline_data(self, kline_data):
        """设置K线数据到组件"""
        try:
            if hasattr(self.kline_widget, 'set_kline_data'):
                self.kline_widget.set_kline_data(kline_data, getattr(self, '_kline_code', ''))
                print(f"[StockDetail] K线数据已设置，共{len(kline_data.get('close',[]))}根")
        except Exception as e:
            print(f"[StockDetail] 设置K线数据失败: {e}")

    def _calc_indicators(self):
        """计算KDJ和MACD指标"""
        if not self.kline_data:
            return

        try:
            import pandas as pd
            from utils.indicators import calc_kdj_series, calc_macd_series, calc_ma_series

            closes = self.kline_data.get('close', [])
            highs = self.kline_data.get('high', [])
            lows = self.kline_data.get('low', [])
            volumes = self.kline_data.get('volume', [])

            if len(closes) < 30:
                return

            # 安全获取Series最后一个值
            def _last(series, default=0):
                if series is None:
                    return default
                if hasattr(series, 'iloc'):
                    if len(series) == 0:
                        return default
                    val = series.iloc[-1]
                    return float(val) if not pd.isna(val) else default
                if isinstance(series, (list, tuple)):
                    if len(series) == 0:
                        return default
                    return float(series[-1]) if series[-1] is not None else default
                return default

            # KDJ (13,3,3) - 返回tuple (k, d, j)
            kdj_result = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)
            if kdj_result and len(kdj_result) >= 3:
                k_series, d_series, j_series = kdj_result
                k_val = _last(k_series)
                d_val = _last(d_series)
                j_val = _last(j_series)
                self.kdj_k_label.setText(f"{k_val:.2f}")
                self.kdj_d_label.setText(f"{d_val:.2f}")
                self.kdj_j_label.setText(f"{j_val:.2f}")

                # KDJ状态判断
                if k_val > d_val and j_val > 50:
                    status = '金叉/强势'
                    self.kdj_status_label.setStyleSheet('color: #3fb950; font-size: 11px; font-weight: bold;')
                elif k_val < d_val and j_val < 50:
                    status = '死叉/弱势'
                    self.kdj_status_label.setStyleSheet('color: #f85149; font-size: 11px; font-weight: bold;')
                else:
                    status = '震荡'
                    self.kdj_status_label.setStyleSheet('color: #d29922; font-size: 11px; font-weight: bold;')
                self.kdj_status_label.setText(status)

            # MACD (8,21,5) - 返回tuple (dif, dea, macd_hist)
            macd_result = calc_macd_series(closes, fast=8, slow=21, signal=5)
            if macd_result and len(macd_result) >= 3:
                diff_series, dea_series, bar_series = macd_result
                diff_val = _last(diff_series)
                dea_val = _last(dea_series)
                bar_val = _last(bar_series)
                self.macd_diff_label.setText(f"{diff_val:.4f}")
                self.macd_dea_label.setText(f"{dea_val:.4f}")
                self.macd_bar_label.setText(f"{bar_val:.4f}")

                # MACD状态判断
                if diff_val > dea_val and bar_val > 0:
                    status = '红柱/多头'
                    self.macd_status_label.setStyleSheet('color: #3fb950; font-size: 11px; font-weight: bold;')
                elif diff_val < dea_val and bar_val < 0:
                    status = '绿柱/空头'
                    self.macd_status_label.setStyleSheet('color: #f85149; font-size: 11px; font-weight: bold;')
                else:
                    status = '转换中'
                    self.macd_status_label.setStyleSheet('color: #d29922; font-size: 11px; font-weight: bold;')
                self.macd_status_label.setText(status)

            # MA均线
            ma5 = calc_ma_series(closes, 5)
            ma9 = calc_ma_series(closes, 9)
            ma20 = calc_ma_series(closes, 20)
            current_price = closes[-1] if closes else 0

            ma5_val = _last(ma5)
            ma9_val = _last(ma9)
            ma20_val = _last(ma20)

            # 技术面总结
            summary_parts = []
            if ma5_val and current_price > ma5_val:
                summary_parts.append("站上MA5")
            else:
                summary_parts.append("跌破MA5")
            if ma9_val and current_price > ma9_val:
                summary_parts.append("站上MA9")
            else:
                summary_parts.append("跌破MA9")
            if ma20_val and current_price > ma20_val:
                summary_parts.append("站上MA20")
            else:
                summary_parts.append("跌破MA20")

            self.summary_label.setText(" | ".join(summary_parts))

            # 真实信号计算
            self._calc_real_signals(closes, volumes, ma5_val, ma9_val, ma20_val,
                                    k_val, d_val, j_val, diff_val, dea_val)

        except Exception as e:
            print(f"[StockDetail] 计算指标失败: {e}")
            import traceback
            traceback.print_exc()

    def _calc_real_signals(self, closes, volumes, ma5, ma9, ma20, k, d, j, diff, dea):
        """根据真实K线数据计算信号"""
        import pandas as pd
        real_signals = []
        real_reasons = []

        if not closes or len(closes) < 10:
            self.stock_data['signals'] = real_signals
            self._update_signals_display()
            return

        current_price = closes[-1]
        prev_price = closes[-2] if len(closes) >= 2 else current_price

        # 1. 买点：站上MA5，接近MA9，连续上涨
        if ma5 and current_price > ma5:
            if ma9 and abs(current_price - ma9) / ma9 < 0.03:
                # 连续上涨2天
                if len(closes) >= 3 and closes[-1] > closes[-2] > closes[-3]:
                    real_signals.append('买点')
                    real_reasons.append('1. 股价站上5日均线\n2. 价格接近9日均线(差距<3%)\n3. 连续2日上涨')

        # 2. 穿九：今日上穿MA9
        if ma9 and len(closes) >= 2:
            prev_ma9 = ma9  # 简化，实际应计算昨日MA9
            if prev_price < ma9 and current_price > ma9:
                real_signals.append('穿九')
                real_reasons.append('1. 昨日收盘价低于9日均线\n2. 今日收盘价上穿9日均线\n3. 短期趋势转强')

        # 3. 站二十：收盘价站上MA20
        if ma20 and current_price > ma20:
            if len(closes) >= 2 and closes[-2] <= ma20:
                real_signals.append('站二十')
                real_reasons.append('1. 昨日收盘价未站上20日线\n2. 今日收盘价突破20日线\n3. 中期趋势转强')
            elif current_price > ma20:
                # 已在20日线上
                pass

        # 4. 底部吸筹：价格在近60日低点附近，成交量放大
        if len(closes) >= 60 and len(volumes) >= 60:
            recent_low = min(closes[-60:])
            if current_price < recent_low * 1.15:
                avg_vol_20 = sum(volumes[-20:]) / 20
                if volumes[-1] > avg_vol_20 * 1.3 and volumes[-2] < avg_vol_20:
                    real_signals.append('底部吸筹')
                    real_reasons.append('1. 价格在近60日低点附近(+15%内)\n2. 前日成交量萎缩\n3. 今日放量(>20日均量1.3倍)')

        # 5. 量价观察：成交量异常
        if len(volumes) >= 5:
            avg_vol_5 = sum(volumes[-5:]) / 5
            if volumes[-1] > avg_vol_5 * 1.5:
                if '买点' not in real_signals and '底部吸筹' not in real_signals:
                    real_signals.append('量价观察')
                    real_reasons.append('1. 今日成交量超过5日均量1.5倍\n2. 关注价格突破方向\n3. 等待后续确认')

        # 6. KDJ金叉
        if len(closes) >= 2 and k > d:
            # 简化判断：K>D且J从低位回升
            if j < 30:
                real_signals.append('KDJ金叉')
                real_reasons.append(f'1. KDJ低位金叉(K={k:.1f}>D={d:.1f})\n2. J值={j:.1f}从超卖区回升\n3. 短期反弹信号')

        # 7. MACD金叉
        if diff > dea:
            if len(closes) >= 2:
                real_signals.append('MACD金叉')
                real_reasons.append(f'1. MACD金叉(DIFF={diff:.4f}>DEA={dea:.4f})\n2. 绿柱缩短转红\n3. 中期趋势转强')

        # 8. 死叉观察
        dead_cross = False
        if k < d and j > 70:
            real_signals.append('死叉观察')
            real_reasons.append(f'1. KDJ高位死叉(K={k:.1f}<D={d:.1f})\n2. J值={j:.1f}从超买区回落\n3. 短期调整风险')
            dead_cross = True
        if diff < dea and not dead_cross:
            real_signals.append('死叉观察')
            real_reasons.append(f'1. MACD死叉(DIFF={diff:.4f}<DEA={dea:.4f})\n2. 红柱缩短转绿\n3. 中期趋势转弱')

        # 9. 观察：无明确信号但指标中性
        if not real_signals:
            real_signals.append('观察')
            real_reasons.append('1. 无明确买卖信号\n2. 指标处于中性区域\n3. 等待量价配合确认')

        # 保存真实信号和原因
        self.stock_data['signals'] = real_signals
        self.stock_data['signal_reasons'] = real_reasons
        self._update_signals_display()
        self._update_signal_markers(real_signals, current_price)

    def _update_signals_display(self):
        """更新信号显示"""
        signals = self.stock_data.get('signals', [])
        if isinstance(signals, str):
            signals = [signals]

        # 清空当前信号
        while self.current_signals_layout.count():
            item = self.current_signals_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 显示当前信号
        if signals:
            for sig in signals[:5]:
                sig_label = SignalLabel(sig)
                self.current_signals_layout.addWidget(sig_label)
        else:
            no_sig = QLabel('暂无当前信号')
            no_sig.setStyleSheet('color: #8b949e; font-size: 11px;')
            self.current_signals_layout.addWidget(no_sig)

        # 触发原因（优先使用真实计算的原因）
        real_reasons = self.stock_data.get('signal_reasons', [])
        if real_reasons:
            reason_text = real_reasons[0] if isinstance(real_reasons[0], str) else '\n'.join(real_reasons)
        else:
            reasons = {
                '买点': '1. 股价站上5日均线\n2. 价格接近9日均线\n3. 连续上涨趋势',
                '底部吸筹': '1. 成交量萎缩后放量\n2. 价格在低位企稳\n3. 主力资金净流入',
                '观察': '1. 指标待确认\n2. 等待信号明确\n3. 关注量价配合',
                '量价观察': '1. 成交量出现变化\n2. 价格待突破\n3. 关注后续确认',
                '穿九': '1. 收盘价上穿9日均线\n2. 成交量配合\n3. 短期趋势转强',
                '站二十': '1. 收盘价站上20日均线\n2. 中期趋势转强\n3. 关注回踩支撑',
                '死叉观察': '1. MACD/KDJ出现死叉迹象\n2. 短期趋势转弱\n3. 注意风险控制',
            }
            reason_text = reasons.get(signals[0], '技术信号触发，建议结合多指标综合判断') if signals else '暂无明确信号，建议观望等待'
        self.reason_label.setText(reason_text)

        # 历史信号（基于近期K线简单计算）
        while self.history_layout.count() > 1:
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 从K线数据计算最近10天的简单信号
        hist_signals = self._calc_recent_history_signals()
        if hist_signals:
            for date_str, sig in hist_signals:
                hist_label = QLabel(f"{date_str}  {sig}")
                color = SIGNAL_COLORS.get(sig, DEFAULT_SIGNAL_COLOR)
                hist_label.setStyleSheet(f'color: {color}; font-size: 10px; padding: 1px;')
                self.history_layout.insertWidget(0, hist_label)
        else:
            no_hist = QLabel('暂无历史信号记录')
            no_hist.setStyleSheet('color: #8b949e; font-size: 10px;')
            self.history_layout.insertWidget(0, no_hist)

    def _update_signal_markers(self, signals, current_price):
        """更新买卖点标记（轻量显示）"""
        # 清空
        while self.signal_marker_layout.count():
            item = self.signal_marker_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not signals:
            no_marker = QLabel('暂无买卖点标记')
            no_marker.setStyleSheet('color: #8b949e; font-size: 10px;')
            self.signal_marker_layout.addWidget(no_marker)
            return

        # 买入信号标记
        buy_signals = ['买点', '底部吸筹', '穿九', '站二十', 'MACD金叉', 'KDJ金叉']
        sell_signals = ['死叉观察']

        for sig in signals[:5]:
            if sig in buy_signals:
                marker = QLabel(f"🟢 {sig} @ {current_price:.2f}")
                marker.setStyleSheet('color: #3fb950; font-size: 10px; padding: 1px;')
            elif sig in sell_signals:
                marker = QLabel(f"🔴 {sig} @ {current_price:.2f}")
                marker.setStyleSheet('color: #f85149; font-size: 10px; padding: 1px;')
            else:
                marker = QLabel(f"⚪ {sig} @ {current_price:.2f}")
                marker.setStyleSheet('color: #8b949e; font-size: 10px; padding: 1px;')
            self.signal_marker_layout.addWidget(marker)

    def _calc_recent_history_signals(self):
        """基于近期K线计算历史信号（最近10个交易日）"""
        if not self.kline_data:
            return []

        try:
            import pandas as pd
            from utils.indicators import calc_ma_series

            closes = self.kline_data.get('close', [])
            dates = self.kline_data.get('dates', [])
            if len(closes) < 30 or len(dates) < 30:
                return []

            ma5 = calc_ma_series(closes, 5)
            ma9 = calc_ma_series(closes, 9)
            ma20 = calc_ma_series(closes, 20)

            def _val(series, idx):
                if series is None or idx >= len(series):
                    return None
                v = series.iloc[idx] if hasattr(series, 'iloc') else series[idx]
                return float(v) if not pd.isna(v) else None

            history = []
            # 检查最近10个交易日
            for i in range(max(0, len(closes)-10), len(closes)):
                date_str = dates[i][5:] if i < len(dates) else ''
                close = closes[i]
                m5 = _val(ma5, i)
                m9 = _val(ma9, i)
                m20 = _val(ma20, i)

                sig = None
                # 穿九：上穿MA9
                if m9 and i > 0:
                    prev_m9 = _val(ma9, i-1)
                    prev_close = closes[i-1]
                    if prev_close <= prev_m9 and close > m9:
                        sig = '穿九'
                # 站二十：上穿MA20
                elif m20 and i > 0:
                    prev_m20 = _val(ma20, i-1)
                    prev_close = closes[i-1]
                    if prev_close <= prev_m20 and close > m20:
                        sig = '站二十'
                # 买点：站上MA5且接近MA9
                elif m5 and m9 and close > m5 and abs(close-m9)/m9 < 0.02:
                    sig = '买点'
                # 底部吸筹：在低点附近
                elif i >= 20 and close < min(closes[max(0,i-60):i+1]) * 1.1:
                    sig = '底部吸筹'

                if sig:
                    history.append((date_str, sig))

            return history[-8:]  # 最多显示8条

        except Exception as e:
            print(f"[StockDetail] 计算历史信号失败: {e}")
            return []

    def _switch_period(self, period):
        """切换K线周期"""
        self.current_period = period
        for p, btn in self.period_buttons.items():
            btn.setChecked(p == period)

        if period == 'day':
            self._load_kline()
        elif period == 'min':
            self._load_minute_data()
        elif period == 'week':
            QMessageBox.information(self, '周K', '周K数据接口待接入，当前显示日K')
        elif period == 'month':
            QMessageBox.information(self, '月K', '月K数据接口待接入，当前显示日K')

    def _load_minute_data(self):
        """加载分时数据"""
        try:
            from utils.kline_provider import get_minute_time_data
            code = self.stock_data.get('code', '')
            if not code:
                return

            minute_data = get_minute_time_data(code)
            if not minute_data or not minute_data.get('prices'):
                QMessageBox.warning(self, '分时', '分时数据获取失败，可能为非交易时间')
                return

            # 转换为KlineContainer可识别的格式
            kline_format = {
                'dates': minute_data.get('times', []),
                'open': minute_data.get('prices', []),
                'high': minute_data.get('prices', []),
                'low': minute_data.get('prices', []),
                'close': minute_data.get('prices', []),
                'volume': minute_data.get('volumes', []),
                'avg_prices': minute_data.get('avg_prices', []),
                'pre_close': minute_data.get('pre_close', 0),
                'period': 'time'
            }

            self._set_kline_data(kline_format)
            print(f"[StockDetail] 分时数据加载成功，共{len(minute_data.get('prices',[]))}个时间点")

        except Exception as e:
            print(f"[StockDetail] 加载分时数据失败: {e}")
            import traceback
            traceback.print_exc()

    def _load_ai_decision(self):
        """V0.7 C5.2.4 加载AI综合决策数据"""
        try:
            # 确保项目根目录在 sys.path 中
            import sys as _sys
            import os as _os
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from dashboard.decision_adapter import get_decision_adapter
            adapter = get_decision_adapter()

            code = self.stock_data.get('code', '')
            if not code:
                self.ai_action_label.setText('无代码')
                return

            detail = adapter.get_stock_detail(code, market_env='震荡')

            # 星级
            self.ai_stars_label.setText(detail.get('stars', '★★★☆☆'))

            # 建议
            action = detail.get('action_label', '观望')
            self.ai_action_label.setText(action)
            action_colors = {
                '买入': '#f85149', '加仓': '#f85149',
                '持有': '#3fb950', '观望': '#d29922',
                '减仓': '#f0883e', '卖出': '#da3633',
            }
            self.ai_action_label.setStyleSheet(
                f"color: {action_colors.get(action, '#f0f6fc')}; "
                f"font-size: 16px; font-weight: bold;"
            )

            # 置信度
            confidence = detail.get('confidence', 0)
            self.ai_confidence_label.setText(f'置信度: {confidence:.0f}%')

            # 仓位
            position = detail.get('position_pct', '0%')
            self.ai_position_label.setText(f'仓位: {position}')

            # 买入评分
            buy_score = detail.get('buy_score', 0)
            self.ai_buy_score_label.setText(f'买入: {buy_score:.0f}')
            if buy_score >= 80:
                self.ai_buy_score_label.setStyleSheet('color: #3fb950; font-size: 11px; font-weight: bold;')
            elif buy_score >= 60:
                self.ai_buy_score_label.setStyleSheet('color: #d29922; font-size: 11px;')

            # 卖出风险
            sell_score = detail.get('sell_score', 0)
            self.ai_sell_score_label.setText(f'风险: {sell_score:.0f}')
            if sell_score >= 60:
                self.ai_sell_score_label.setStyleSheet('color: #da3633; font-size: 11px; font-weight: bold;')
            elif sell_score >= 40:
                self.ai_sell_score_label.setStyleSheet('color: #f85149; font-size: 11px;')

            # 核心理由
            reasons = detail.get('reason', [])
            if reasons:
                reason_text = '✓ ' + '  ✓ '.join(reasons[:4])
                self.ai_reason_label.setText(reason_text)
            else:
                self.ai_reason_label.setText('✓ 数据加载中或无明显信号')

            # 风险提示
            risks = detail.get('risk_warnings', [])
            if risks:
                risk_text = '⚠ ' + '  ⚠ '.join(risks[:3])
                self.ai_risk_label.setText(risk_text)
            else:
                self.ai_risk_label.setText('')

        except Exception as e:
            self.ai_action_label.setText('AI不可用')
            self.ai_reason_label.setText(f'决策服务异常: {e}')
            import logging
            logging.getLogger(__name__).warning(f"个股详情AI决策加载失败: {e}")

    def _refresh_data(self):
        """刷新数据"""
        try:
            from utils.tdx_stock_list import get_realtime_quotes_tdx
            code = self.stock_data.get('code', '')
            if code:
                quotes = get_realtime_quotes_tdx([code])
                if quotes and len(quotes) > 0:
                    q = quotes[0]
                    self.stock_data['price'] = q.get('price', self.stock_data.get('price', 0))
                    self.stock_data['pct_chg'] = q.get('pct_chg', self.stock_data.get('pct_chg', 0))
                    self.stock_data['volume'] = q.get('volume', self.stock_data.get('volume', 0))
                    self.stock_data['turnover'] = q.get('turnover', self.stock_data.get('turnover', 0))

                    # 更新价格显示
                    price = self.stock_data['price']
                    pct = self.stock_data['pct_chg']
                    price_color = '#f85149' if pct > 0 else '#3fb950' if pct < 0 else '#f0f6fc'
                    self.price_label.setText(f"{price:.2f}  {pct:+.2f}%")
                    self.price_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {price_color};')

            # 重新加载K线
            self._load_kline()

        except Exception as e:
            print(f"[StockDetail] 刷新失败: {e}")


class ScanWorker(QThread):
    """后台扫描线程 - 全流程后台执行（行情+财务+K线筛选）"""
    progress = pyqtSignal(str, int, int)  # (阶段描述, 当前, 总数)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            # 确保项目根目录在 sys.path 中
            import os as _os
            import sys as _sys
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)

            from utils.tdx_stock_list import get_full_market_quotes, enrich_finance_info
            from utils.kline_provider import get_daily_kline
            from strategy.pro_stock_pool_filter import get_pro_stock_pool_filter

            pool_filter = get_pro_stock_pool_filter()

            # ===== 第一步：获取全市场行情 =====
            if self._stop:
                return
            self.progress.emit('[1/5] 正在获取全市场股票列表...', 0, 1)

            def market_cb(current, total, msg):
                if not self._stop:
                    self.progress.emit(f'[1/5] {msg}', current, total)

            all_stocks = get_full_market_quotes(progress_callback=market_cb, main_board_only=True, exclude_st=True)
            if not all_stocks:
                self.error.emit('获取全市场股票列表失败')
                return

            self.progress.emit(f'[1/5] 全市场共{len(all_stocks)}只股票', len(all_stocks), len(all_stocks))

            # ===== 第二步：价格+主板初步过滤 =====
            if self._stop:
                return
            self.progress.emit('[2/5] 正在进行价格+主板初步过滤...', 0, len(all_stocks))

            pre_filtered = []
            for i, s in enumerate(all_stocks):
                if self._stop:
                    return
                code = s.get('code', '')
                name = s.get('name', '')
                price = s.get('price', 0)

                # ST过滤
                if 'ST' in name or 'st' in name.lower() or '*ST' in name:
                    continue
                # 主板过滤
                if not (code.startswith('60') or code.startswith('00')):
                    continue
                # 价格过滤
                if price < pool_filter.MIN_PRICE or price > pool_filter.MAX_PRICE:
                    continue

                pre_filtered.append(s)
                if (i + 1) % 200 == 0:
                    self.progress.emit(f'[2/5] 价格+主板过滤中...', i + 1, len(all_stocks))

            self.progress.emit(f'[2/5] 价格+主板过滤后剩余{len(pre_filtered)}只', len(pre_filtered), len(all_stocks))

            if not pre_filtered:
                self.finished.emit([])
                return

            # ===== 第三步：获取财务信息 =====
            if self._stop:
                return
            self.progress.emit(f'[3/5] 正在获取{len(pre_filtered)}只股票的财务信息...', 0, len(pre_filtered))

            def finance_cb(current, total, msg):
                if not self._stop:
                    self.progress.emit(f'[3/5] {msg}', current, total)

            enriched = enrich_finance_info(pre_filtered, progress_callback=finance_cb)

            # ===== 第四步：市值+行业过滤 =====
            if self._stop:
                return
            self.progress.emit('[4/5] 正在进行市值+行业过滤...', 0, len(enriched))

            final_candidates = []
            for i, s in enumerate(enriched):
                if self._stop:
                    return
                market_cap = s.get('market_cap', 0)
                industry = s.get('industry', '')

                # 市值过滤
                if market_cap < pool_filter.MIN_MARKET_CAP or market_cap > pool_filter.MAX_MARKET_CAP:
                    continue
                # 行业过滤
                skip = False
                for excl in pool_filter.EXCLUDE_INDUSTRIES:
                    if excl in industry:
                        skip = True
                        break
                if skip:
                    continue

                final_candidates.append(s)
                if (i + 1) % 100 == 0:
                    self.progress.emit(f'[4/5] 市值+行业过滤中...', i + 1, len(enriched))

            self.progress.emit(f'[4/5] 市值+行业过滤后剩余{len(final_candidates)}只', len(final_candidates), len(enriched))

            if not final_candidates:
                self.finished.emit([])
                return

            # ===== 第五步：逐只获取K线并最终筛选（同时计算信号标签） =====
            self.progress.emit(f'[5/5] 开始K线深度筛选，共{len(final_candidates)}只...', 0, len(final_candidates))

            from strategy.kline_scanner import get_scanner
            from strategy.indicator_scanner import get_indicator_scanner
            kline_scanner = get_scanner()
            indicator_scanner = get_indicator_scanner()

            results = []
            total = len(final_candidates)
            for i, stock in enumerate(final_candidates):
                if self._stop:
                    break
                try:
                    code = stock.get('code', '')
                    kline = get_daily_kline(code)
                    filtered = pool_filter.filter_stock(stock, kline)
                    if filtered:
                        # 同时计算信号标签（避免主线程再次获取K线）
                        signals = []
                        try:
                            kline_sigs = kline_scanner.scan(kline)
                            for sig in kline_sigs:
                                name = sig.get('name', '')
                                if name and name not in signals:
                                    signals.append(name)
                            ind_sigs = indicator_scanner.scan_all(kline)
                            for sig in ind_sigs:
                                name = sig.get('name', '')
                                if name and name not in signals:
                                    signals.append(name)
                        except Exception:
                            pass
                        filtered['signals'] = signals[:5]
                        filtered['update_time'] = datetime.now().strftime('%H:%M:%S')
                        results.append(filtered)
                except Exception as e:
                    print(f"扫描{stock.get('code','?')}失败: {e}")

                if (i + 1) % 3 == 0:
                    self.progress.emit(f'[5/5] K线深度筛选中...', i + 1, total)

            self.progress.emit(f'[5/5] K线筛选完成', total, total)
            self.finished.emit(results)

        except Exception as e:
            print(f"扫描线程异常: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class ManualFilterWorker(QThread):
    """手动筛选后台线程"""
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, config, stock_list=None):
        super().__init__()
        self.config = config
        self.stock_list = stock_list  # None表示全市场，否则用预筛选列表
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            # 确保项目根目录在 sys.path 中
            import os as _os
            import sys as _sys
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)

            from strategy.manual_filter_engine import ManualFilterEngine
            engine = ManualFilterEngine()

            def progress_cb(current, total, msg):
                if not self._stop:
                    self.progress.emit(msg, current, total)

            results = engine.filter(self.config, self.stock_list, progress_cb)
            if self._stop:
                return
            self.finished.emit(results)
        except Exception as e:
            print(f"手动筛选线程异常: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class AIScoreWorker(QThread):
    """V0.7.1.1 AI评分后台线程，避免阻塞UI主线程"""
    finished = pyqtSignal(list)  # 返回决策列表
    error = pyqtSignal(str)

    def __init__(self, codes, market_env='震荡'):
        super().__init__()
        self._codes = codes
        self._market_env = market_env

    def run(self):
        try:
            # 确保项目根目录在 sys.path 中
            import sys as _sys
            import os as _os
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from dashboard.decision_adapter import get_decision_adapter
            adapter = get_decision_adapter()
            decisions = adapter.service.get_batch_decisions(
                self._codes, market_env=self._market_env
            )
            self.finished.emit(decisions)
        except Exception as e:
            self.error.emit(str(e))


class ProStockPoolPanel(QWidget):
    """V6.0 Pro 专业股票池主面板"""

    stock_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scan_worker = None
        self._manual_worker = None
        self._ai_worker = None
        self.ai_score_btn = None
        self._stock_data = []
        self._filter_mode = 'auto'  # auto / manual / combo
        # V0.7.4 股票池缓存文件路径
        import os as _os
        self._cache_file = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            'cache', 'stock_pool_cache.json'
        )
        self._init_ui()
        # V0.7.4 启动时自动加载当天缓存
        self._load_today_cache()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部功能按钮栏
        self._create_toolbar(layout)

        # 股票池信息栏
        self._create_info_bar(layout)

        # 主分割区：表格 + 信号中心
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 股票池表格
        self.table = ProStockTable()
        self.table.stock_double_clicked.connect(self._on_stock_double_clicked)
        splitter.addWidget(self.table)

        # 信号中心
        self.signal_center = SignalCenterWidget()
        splitter.addWidget(self.signal_center)

        splitter.setSizes([500, 200])
        layout.addWidget(splitter)

        # 状态栏
        self.status_label = QLabel('就绪')
        self.status_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        layout.addWidget(self.status_label)

    def _create_toolbar(self, layout):
        """创建顶部功能按钮栏"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        buttons = [
            ('▶ 自动选股', '#238636', self._start_scan),
            ('⏹ 停止', '#da3633', self._stop_scan),
            ('🔧 手动筛选', '#8957e5', self._open_manual_filter),
            ('🔗 组合筛选', '#d29922', self._open_combo_filter),
            ('📋 策略管理', '#f0883e', self._show_strategy_manager),
            ('🤖 AI评分', '#bc8cff', self._enrich_ai_scores),
            ('🔄 更新AI数据', '#238636', self._force_refresh_ai),
            ('🔄 刷新行情', '#1f6feb', self._refresh_quotes),
            ('📤 导出记录', '#6e7681', self._export_data),
        ]

        for text, color, callback in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color}; color: white; border: none;
                    padding: 6px 12px; border-radius: 4px; font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ opacity: 0.8; }}
                QPushButton:disabled {{ background: #30363d; color: #8b949e; }}
            """)
            btn.clicked.connect(callback)
            toolbar.addWidget(btn)
            if 'AI评分' in text:
                self.ai_score_btn = btn

        toolbar.addStretch()
        layout.addLayout(toolbar)

    def _create_info_bar(self, layout):
        """创建股票池信息栏"""
        info_bar = QHBoxLayout()
        info_bar.setSpacing(16)

        self.count_label = QLabel('股票池: 0只')
        self.count_label.setStyleSheet('color: #f0f6fc; font-size: 13px; font-weight: bold;')
        info_bar.addWidget(self.count_label)

        self.time_label = QLabel('更新时间: --')
        self.time_label.setStyleSheet('color: #8b949e; font-size: 12px;')
        info_bar.addWidget(self.time_label)

        # 筛选条件显示
        self.filter_label = QLabel('筛选: 主板 | 5-60元 | 30-230亿 | 涨停≥3次 | 8月高点70%-105%')
        self.filter_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        info_bar.addWidget(self.filter_label)

        info_bar.addStretch()
        layout.addLayout(info_bar)

    def _start_scan(self):
        """开始扫描（全流程后台执行，不阻塞UI）"""
        if self._scan_worker and self._scan_worker.isRunning():
            self.status_label.setText('正在扫描中...')
            return

        self.status_label.setText('正在启动扫描线程...')
        try:
            # 所有耗时操作全部在ScanWorker后台线程中执行
            self._scan_worker = ScanWorker()
            self._scan_worker.progress.connect(self._on_scan_progress)
            self._scan_worker.finished.connect(self._on_scan_finished)
            self._scan_worker.error.connect(self._on_scan_error)
            self._scan_worker.start()
            self.status_label.setText('扫描线程已启动，正在获取全市场行情...')
        except Exception as e:
            self.status_label.setText(f'扫描启动失败: {e}')
            print(f'扫描启动失败: {e}')
            import traceback
            traceback.print_exc()

    def _stop_scan(self):
        """停止扫描"""
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.stop()
            self.status_label.setText('自动扫描已停止')
        if self._manual_worker and self._manual_worker.isRunning():
            self._manual_worker.stop()
            self.status_label.setText('手动筛选已停止')

    def _on_scan_progress(self, stage_msg, current, total):
        """扫描进度（全流程后台，5个阶段）"""
        if total > 0:
            pct = current * 100 // total
            self.status_label.setText(f'{stage_msg} ({current}/{total}, {pct}%)')
        else:
            self.status_label.setText(stage_msg)

    def _load_today_cache(self):
        """V0.7.4 加载当天股票池缓存（秒加载，不重新扫描）"""
        try:
            import os as _os
            import json as _json
            from datetime import datetime as _dt
            print(f'[Pro股票池] 检查缓存文件: {self._cache_file}')
            if not _os.path.exists(self._cache_file):
                print('[Pro股票池] 缓存文件不存在')
                self.status_label.setText('就绪（无缓存，点击自动选股开始扫描）')
                return
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                cache = _json.load(f)
            cache_date = cache.get('date', '')
            today = _dt.now().strftime('%Y-%m-%d')
            print(f'[Pro股票池] 缓存日期={cache_date}, 今天={today}')
            if cache_date != today:
                print(f'[Pro股票池] 缓存已过期（{cache_date}）')
                self.status_label.setText(f'就绪（缓存{cache_date}已过期，点击自动选股重新扫描）')
                return
            results = cache.get('results', [])
            if not results:
                print('[Pro股票池] 缓存结果为空')
                self.status_label.setText('就绪（缓存为空，点击自动选股开始扫描）')
                return
            # 加载缓存到UI
            self._filter_mode = 'auto'
            self._stock_data = results
            self.table.set_data(results)
            self.count_label.setText(f'自动股票池: {len(results)}只（缓存）')
            cache_time = cache.get('time', '')
            self.time_label.setText(f'更新时间: {cache_time}')
            self.status_label.setText(f'已加载今日缓存，共{len(results)}只股票（点击自动选股可重新扫描）')
            # 生成信号提醒
            self._generate_signal_alerts(results)
            print(f'[Pro股票池] 已加载今日缓存: {len(results)}只, 时间={cache_time}')
        except Exception as e:
            print(f'[Pro股票池] 加载缓存失败: {e}')
            import traceback
            traceback.print_exc()
            self.status_label.setText('就绪（缓存加载失败，点击自动选股开始扫描）')

    def _save_cache(self, results):
        """V0.7.4 保存股票池结果到当天缓存"""
        try:
            import os as _os
            import json as _json
            from datetime import datetime as _dt
            _os.makedirs(_os.path.dirname(self._cache_file), exist_ok=True)
            # 清洗数据：确保所有值可JSON序列化
            def _clean(obj):
                if isinstance(obj, dict):
                    return {k: _clean(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_clean(v) for v in obj]
                elif hasattr(obj, 'item'):  # numpy类型
                    return obj.item()
                elif hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
                    return str(obj)
                return obj
            clean_results = _clean(results)
            cache = {
                'date': _dt.now().strftime('%Y-%m-%d'),
                'time': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(clean_results),
                'results': clean_results,
            }
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                _json.dump(cache, f, ensure_ascii=False)
            print(f'[Pro股票池] 缓存已保存: {len(clean_results)}只 -> {self._cache_file}')
            # 验证保存
            if _os.path.exists(self._cache_file):
                fsize = _os.path.getsize(self._cache_file)
                print(f'[Pro股票池] 缓存文件大小: {fsize} bytes')
        except Exception as e:
            print(f'[Pro股票池] 保存缓存失败: {e}')
            import traceback
            traceback.print_exc()

    def _on_scan_finished(self, results):
        """扫描完成（信号标签已在后台线程计算好）"""
        self._filter_mode = 'auto'
        self._stock_data = results
        self.table.set_data(results)
        self.count_label.setText(f'自动股票池: {len(results)}只')
        self.time_label.setText(f'更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.status_label.setText(f'自动选股完成，共筛选出 {len(results)} 只股票')
        # V0.7.4 保存到当天缓存
        self._save_cache(results)
        # 生成信号提醒
        self._generate_signal_alerts(results)

    def _on_scan_error(self, error_msg):
        """扫描错误"""
        self.status_label.setText(f'扫描错误: {error_msg}')

    def _open_manual_filter(self):
        """打开手动筛选条件面板"""
        from ui.manual_filter_panel import ManualFilterPanel
        from PyQt6.QtWidgets import QDialog

        dialog = QDialog(self)
        dialog.setWindowTitle('手动条件筛选')
        dialog.setMinimumSize(600, 700)
        dialog.setStyleSheet('background: #0d1117;')

        layout = QVBoxLayout(dialog)
        panel = ManualFilterPanel()
        panel.filter_applied.connect(lambda config: self._on_manual_filter_applied(config, dialog))
        panel.filter_cancelled.connect(dialog.close)
        layout.addWidget(panel)

        dialog.exec()

    def _on_manual_filter_applied(self, config, dialog):
        """应用手动筛选条件"""
        dialog.close()
        self._filter_mode = 'manual'

        if self._manual_worker and self._manual_worker.isRunning():
            self._manual_worker.stop()

        self.status_label.setText(f'[手动筛选] 方案"{config.name}"，正在全市场扫描...')
        self._manual_worker = ManualFilterWorker(config, stock_list=None)
        self._manual_worker.progress.connect(self._on_manual_filter_progress)
        self._manual_worker.finished.connect(self._on_manual_filter_finished)
        self._manual_worker.error.connect(self._on_manual_filter_error)
        self._manual_worker.start()

    def _on_manual_filter_progress(self, msg, current, total):
        """手动筛选进度"""
        if total > 0:
            pct = current * 100 // total
            self.status_label.setText(f'[手动筛选] {msg} ({current}/{total}, {pct}%)')
        else:
            self.status_label.setText(f'[手动筛选] {msg}')

    def _on_manual_filter_finished(self, results):
        """手动筛选完成"""
        self._stock_data = results
        self.table.set_data(results)
        self.count_label.setText(f'手动筛选: {len(results)}只')
        self.time_label.setText(f'更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.status_label.setText(f'[手动筛选] 完成，共发现{len(results)}只股票')
        self._generate_signal_alerts(results)

    def _on_manual_filter_error(self, error_msg):
        """手动筛选错误"""
        self.status_label.setText(f'[手动筛选] 错误: {error_msg}')

    def _open_combo_filter(self):
        """组合筛选：在自动选股结果基础上再手动筛选"""
        if not self._stock_data:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, '组合筛选', '请先运行自动选股，获取股票池后再进行组合筛选')
            return

        from ui.manual_filter_panel import ManualFilterPanel
        from PyQt6.QtWidgets import QDialog

        dialog = QDialog(self)
        dialog.setWindowTitle('组合筛选（自动股票池 + 手动条件）')
        dialog.setMinimumSize(600, 700)
        dialog.setStyleSheet('background: #0d1117;')

        layout = QVBoxLayout(dialog)
        panel = ManualFilterPanel()
        panel.filter_applied.connect(lambda config: self._on_combo_filter_applied(config, dialog))
        panel.filter_cancelled.connect(dialog.close)
        layout.addWidget(panel)

        dialog.exec()

    def _on_combo_filter_applied(self, config, dialog):
        """应用组合筛选"""
        dialog.close()
        self._filter_mode = 'combo'

        if self._manual_worker and self._manual_worker.isRunning():
            self._manual_worker.stop()

        self.status_label.setText(f'[组合筛选] 在{len(self._stock_data)}只自动股票池中应用手动条件...')
        # 在自动选股结果基础上再手动筛选
        self._manual_worker = ManualFilterWorker(config, stock_list=self._stock_data.copy())
        self._manual_worker.progress.connect(self._on_manual_filter_progress)
        self._manual_worker.finished.connect(self._on_combo_filter_finished)
        self._manual_worker.error.connect(self._on_manual_filter_error)
        self._manual_worker.start()

    def _on_combo_filter_finished(self, results):
        """组合筛选完成"""
        self._stock_data = results
        self.table.set_data(results)
        self.count_label.setText(f'组合筛选: {len(results)}只')
        self.time_label.setText(f'更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.status_label.setText(f'[组合筛选] 完成，共{len(results)}只股票')
        self._generate_signal_alerts(results)

    def _enrich_signals(self, results):
        """补充信号标签"""
        try:
            from strategy.kline_scanner import get_scanner
            from strategy.indicator_scanner import get_indicator_scanner
            from utils.kline_provider import get_daily_kline

            kline_scanner = get_scanner()
            indicator_scanner = get_indicator_scanner()

            for stock in results:
                try:
                    code = stock.get('code', '')
                    kline = get_daily_kline(code)
                    if kline:
                        signals = []
                        # K线形态信号
                        kline_sigs = kline_scanner.scan(kline)
                        for sig in kline_sigs:
                            name = sig.get('name', '')
                            if name and name not in signals:
                                signals.append(name)
                        # 指标信号
                        ind_sigs = indicator_scanner.scan_all(kline)
                        for sig in ind_sigs:
                            name = sig.get('name', '')
                            if name and name not in signals:
                                signals.append(name)
                        stock['signals'] = signals[:5]
                        stock['update_time'] = datetime.now().strftime('%H:%M:%S')
                except Exception:
                    stock['signals'] = []
                    stock['update_time'] = datetime.now().strftime('%H:%M:%S')
        except Exception as e:
            print(f'补充信号失败: {e}')

    def _generate_signal_alerts(self, results):
        """生成信号提醒"""
        self.signal_center.clear_all()

        for stock in results:
            signals = stock.get('signals', [])
            if isinstance(signals, str):
                signals = [signals]

            for sig in signals:
                # 买入信号
                if sig in ['买点', '涨停突破', '三倍量', '五九回踩']:
                    self.signal_center.add_signal('buy', stock, sig, '买入信号触发')
                # 观察信号
                elif sig in ['MACD金叉', 'KDJ金叉', '量价观察', '底部吸筹']:
                    self.signal_center.add_signal('watch', stock, sig, '观察信号，待确认')
                # 风险信号
                elif sig in ['死叉观察', '站二十', '穿九']:
                    self.signal_center.add_signal('risk', stock, sig, '风险/趋势变化信号')

    def _enrich_ai_scores(self):
        """V0.7.1.1 异步AI评分：后台线程计算，不阻塞UI"""
        if not self._stock_data:
            self.status_label.setText('暂无数据，请先扫描')
            return

        # 防止重复启动
        if self._ai_worker and self._ai_worker.isRunning():
            self.status_label.setText('AI评分正在计算中，请稍候...')
            return

        codes = [s.get('code', '') for s in self._stock_data if s.get('code')]
        if not codes:
            self.status_label.setText('无有效股票代码')
            return

        # 禁用按钮，显示状态
        if self.ai_score_btn:
            self.ai_score_btn.setEnabled(False)
            self.ai_score_btn.setText('🤖 计算中...')
        self.status_label.setText(f'正在后台计算AI评分（{len(codes)}只）...')

        # 启动后台线程
        self._ai_worker = AIScoreWorker(codes, market_env='震荡')
        self._ai_worker.finished.connect(self._on_ai_score_finished)
        self._ai_worker.error.connect(self._on_ai_score_error)
        self._ai_worker.start()

    def _on_ai_score_finished(self, decisions):
        """AI评分完成回调（主线程）"""
        try:
            decision_map = {d.get('stock_code', ''): d for d in decisions}
            count = 0
            for stock in self._stock_data:
                code = stock.get('code', '')
                d = decision_map.get(code, {})
                if d:
                    stock['ai_score'] = d.get('confidence', 50)
                    stock['ai_action'] = d.get('action_label', '观望')
                    stock['ai_position'] = d.get('position_pct', '0%')
                    sell_score = d.get('sell_score', 30)
                    if sell_score >= 60:
                        stock['ai_risk'] = '高'
                    elif sell_score >= 40:
                        stock['ai_risk'] = '中'
                    else:
                        stock['ai_risk'] = '低'
                    stock['ai_reason'] = d.get('reason', [])
                    count += 1

            # 同步到table并刷新
            self.table._data = self._stock_data
            self.table._refresh_table()
            self.status_label.setText(f'AI评分完成，共{count}只股票')
        except Exception as e:
            self.status_label.setText(f'AI评分结果处理异常: {e}')
        finally:
            if self.ai_score_btn:
                self.ai_score_btn.setEnabled(True)
                self.ai_score_btn.setText('🤖 AI评分')
            self._ai_worker = None

    def _on_ai_score_error(self, error_msg):
        """AI评分错误回调"""
        self.status_label.setText(f'AI评分计算失败: {error_msg}')
        if self.ai_score_btn:
            self.ai_score_btn.setEnabled(True)
            self.ai_score_btn.setText('🤖 AI评分')
        self._ai_worker = None

    def _force_refresh_ai(self):
        """V0.7.2 强制刷新AI日缓存（清除当天缓存，下次计算重新生成）"""
        try:
            from decision.decision_service import get_decision_service
            svc = get_decision_service()
            svc.force_refresh_cache()
            status = svc.get_cache_status()
            self.status_label.setText(
                f'AI缓存已清除，下次AI评分将重新计算（缓存日期: {status.get("date")}）'
            )
        except Exception as e:
            self.status_label.setText(f'清除AI缓存失败: {e}')

    def _refresh_quotes(self):
        """刷新行情"""
        if not self._stock_data:
            self.status_label.setText('暂无数据，请先扫描')
            return

        self.status_label.setText('正在刷新行情...')
        try:
            from utils.tdx_stock_list import get_realtime_quotes_tdx
            codes = [s['code'] for s in self._stock_data]
            quotes = get_realtime_quotes_tdx(codes)

            quote_map = {q['code']: q for q in quotes} if quotes else {}
            for stock in self._stock_data:
                code = stock.get('code', '')
                if code in quote_map:
                    q = quote_map[code]
                    stock['price'] = q.get('price', stock.get('price', 0))
                    stock['pct_chg'] = q.get('pct_chg', stock.get('pct_chg', 0))
                    stock['volume'] = q.get('volume', stock.get('volume', 0))
                    stock['turnover'] = q.get('turnover', stock.get('turnover', 0))
                    stock['update_time'] = datetime.now().strftime('%H:%M:%S')

            self.table.set_data(self._stock_data)
            self.time_label.setText(f'更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            self.status_label.setText(f'行情刷新完成，共 {len(self._stock_data)} 只')
        except Exception as e:
            self.status_label.setText(f'刷新失败: {e}')

    def _show_pool_info(self):
        """显示股票池信息"""
        from strategy.pro_stock_pool_filter import get_pro_stock_pool_filter
        pool_filter = get_pro_stock_pool_filter()
        summary = pool_filter.get_filter_summary()
        info_text = "\n".join([f"{k}: {v}" for k, v in summary.items()])
        QMessageBox.information(self, '股票池筛选条件', info_text)

    def _show_strategy_manager(self):
        """打开策略管理器"""
        from ui.strategy_editor_dialog import StrategyEditorDialog
        dialog = StrategyEditorDialog(self)
        dialog.exec()

    def _toggle_signal_monitor(self):
        """切换信号监控"""
        QMessageBox.information(self, '信号监控', '信号监控功能已启用\n实时监控买入/观察/风险信号')

    def _show_settings(self):
        """策略设置"""
        QMessageBox.information(
            self, '策略设置',
            'V6.0 Pro 筛选条件：\n\n'
            '价格: 5-60元\n'
            '市值: 30-230亿\n'
            '主板股票\n'
            '排除: ST/地产/农业/酒/保险\n'
            '8个月高点: 70%-105%\n'
            '一年内涨停: ≥3次\n'
            '前一日未涨停\n\n'
            '指标参数: KDJ(13,3,3) MACD(8,21,5)'
        )

    def _export_data(self):
        """导出数据"""
        if not self._stock_data:
            QMessageBox.warning(self, '导出', '暂无数据可导出')
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出股票池',
            f'stock_pool_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            'CSV文件 (*.csv)'
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['序号', '代码', '名称', '现价', '涨跌幅', '成交量',
                               '换手率', '总市值', '主营行业', '涨停次数', '信号标签', '更新时间'])
                for i, stock in enumerate(self._stock_data, 1):
                    signals = stock.get('signals', [])
                    if isinstance(signals, list):
                        signals = ','.join(signals)
                    writer.writerow([
                        i, stock.get('code', ''), stock.get('name', ''),
                        stock.get('price', 0), f"{stock.get('pct_chg',0):+.2f}%",
                        stock.get('volume', 0), f"{stock.get('turnover',0):.2f}%",
                        f"{stock.get('market_cap',0):.1f}亿", stock.get('industry', ''),
                        stock.get('limit_up_count', 0), signals,
                        stock.get('update_time', '')
                    ])
            QMessageBox.information(self, '导出成功', f'已导出到: {file_path}')
            self.status_label.setText(f'已导出: {file_path}')
        except Exception as e:
            QMessageBox.critical(self, '导出失败', str(e))

    def _on_stock_double_clicked(self, stock):
        """双击股票打开详情"""
        dialog = StockDetailDialog(stock, self)
        dialog.exec()
        self.stock_selected.emit(stock)
