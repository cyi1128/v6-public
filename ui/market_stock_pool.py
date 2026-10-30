"""
全市场股票实时数据库页面
沪市股票池 + 深市股票池
支持搜索、排序（AI评分/涨幅/资金/成交量）
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit, QComboBox, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
import requests

from ui.stock_detail_simple import StockDetailDialog


class MarketStockPoolWidget(QWidget):
    """全市场股票池页面"""

    DARK_COLORS = {
        'bg_primary': '#0d1117',
        'bg_secondary': '#161b22',
        'bg_tertiary': '#21262d',
        'border': '#30363d',
        'text_primary': '#f0f6fc',
        'text_secondary': '#8b949e',
        'accent': '#58a6ff',
        'red': '#f85149',
        'green': '#3fb950',
        'orange': '#d29922',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sh_stocks = []
        self.sz_stocks = []
        self._init_ui()
        self._load_stocks()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部：搜索和排序
        top_bar = QFrame()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 8, 15, 8)

        title = QLabel('📊 全市场股票池')
        title.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 16px; font-weight: bold;")
        top_layout.addWidget(title)

        top_layout.addStretch()

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索股票名称/代码...')
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """)
        self.search_input.textChanged.connect(self._filter_stocks)
        top_layout.addWidget(self.search_input)

        # 排序选择
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['涨幅排序', 'AI评分排序', '资金排序', '成交量排序'])
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self._sort_stocks)
        top_layout.addWidget(self.sort_combo)

        # 刷新按钮
        refresh_btn = QPushButton('🔄 刷新')
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.DARK_COLORS['accent']};
                color: white;
                border: none;
                padding: 6px 16px;
                font-size: 12px;
                border-radius: 4px;
            }}
        """)
        refresh_btn.clicked.connect(self._load_stocks)
        top_layout.addWidget(refresh_btn)

        layout.addWidget(top_bar)

        # Tab：沪市/深市
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
                background-color: {self.DARK_COLORS['bg_secondary']};
            }}
            QTabBar::tab {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_secondary']};
                padding: 8px 20px;
                border: none;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['accent']};
            }}
        """)

        # 沪市
        self.sh_table = self._create_table()
        self.tab_widget.addTab(self.sh_table, '🇨🇳 沪市股票')

        # 深市
        self.sz_table = self._create_table()
        self.tab_widget.addTab(self.sz_table, '🇨🇳 深市股票')

        layout.addWidget(self.tab_widget, 1)

    def _create_table(self):
        """创建股票表格"""
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            '股票名称', '代码', '最新价', '涨跌幅',
            '成交量(万手)', '换手率', '市值(亿)', 'AI评分'
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: none;
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
        """)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(table.styleSheet() + f"""
            QTableWidget::item {{ padding: 4px; }}
        """)
        table.cellDoubleClicked.connect(self._on_stock_double_clicked)
        return table

    def _on_stock_double_clicked(self, row, col):
        """双击股票打开详情页"""
        table = self.sender()
        if not table:
            return

        name_item = table.item(row, 0)
        code_item = table.item(row, 1)

        if name_item and code_item:
            stock_name = name_item.text()
            stock_code = code_item.text()
            dialog = StockDetailDialog(stock_code, stock_name, self)
            dialog.exec()

    def _load_stocks(self):
        """加载股票数据"""
        self._load_market_stocks('sh', self.sh_table)
        self._load_market_stocks('sz', self.sz_table)

    def _load_market_stocks(self, market, table):
        """加载指定市场股票"""
        try:
            if market == 'sh':
                fs = 'm:1+t:2,m:1+t:23'
            else:
                fs = 'm:0+t:6,m:0+t:80'

            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 100,  # 前100只
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': fs,
                'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62',
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            stocks = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    stock = {
                        'name': item.get('f14', ''),
                        'code': item.get('f12', ''),
                        'price': item.get('f2', 0),
                        'change_pct': item.get('f3', 0),
                        'volume': item.get('f5', 0) / 10000,  # 万手
                        'turnover': item.get('f8', 0),
                        'market_cap': item.get('f20', 0) / 100000000 if item.get('f20') else 0,
                        'fund_flow': item.get('f62', 0) / 100000000 if item.get('f62') else 0,
                        'ai_score': self._calc_ai_score(item),
                    }
                    stocks.append(stock)

            if market == 'sh':
                self.sh_stocks = stocks
            else:
                self.sz_stocks = stocks

            self._update_table(table, stocks)

        except Exception as e:
            table.setRowCount(0)

    def _calc_ai_score(self, item):
        """简化AI评分计算"""
        score = 50
        change = item.get('f3', 0)
        turnover = item.get('f8', 0)
        fund = item.get('f62', 0) / 100000000 if item.get('f62') else 0

        # 涨幅
        if 0 < change <= 5:
            score += 15
        elif change > 5:
            score += 10
        elif -3 <= change < 0:
            score += 5
        elif change < -5:
            score -= 10

        # 换手率
        if 3 <= turnover <= 15:
            score += 15
        elif turnover > 20:
            score += 5

        # 资金
        if fund > 1:
            score += 20
        elif fund > 0:
            score += 10
        elif fund < -1:
            score -= 10

        return max(0, min(100, score))

    def _update_table(self, table, stocks):
        """更新表格"""
        table.setRowCount(len(stocks))
        for i, stock in enumerate(stocks):
            table.setItem(i, 0, QTableWidgetItem(stock['name']))
            table.setItem(i, 1, QTableWidgetItem(stock['code']))
            table.setItem(i, 2, QTableWidgetItem(f"{stock['price']:.2f}"))

            change_item = QTableWidgetItem(f"{stock['change_pct']:+.2f}%")
            change_item.setForeground(QColor('#f85149' if stock['change_pct'] >= 0 else '#3fb950'))
            table.setItem(i, 3, change_item)

            table.setItem(i, 4, QTableWidgetItem(f"{stock['volume']:.1f}"))
            table.setItem(i, 5, QTableWidgetItem(f"{stock['turnover']:.2f}%"))
            table.setItem(i, 6, QTableWidgetItem(f"{stock['market_cap']:.1f}"))

            score = stock['ai_score']
            score_item = QTableWidgetItem(str(score))
            if score >= 80:
                score_item.setForeground(QColor('#ff1744'))
            elif score >= 65:
                score_item.setForeground(QColor('#00e676'))
            elif score >= 50:
                score_item.setForeground(QColor('#ffea00'))
            else:
                score_item.setForeground(QColor('#757575'))
            table.setItem(i, 7, score_item)

    def _filter_stocks(self, text):
        """搜索过滤"""
        text = text.strip()
        if not text:
            self._update_table(self.sh_table, self.sh_stocks)
            self._update_table(self.sz_table, self.sz_stocks)
            return

        sh_filtered = [s for s in self.sh_stocks if text in s['name'] or text in s['code']]
        sz_filtered = [s for s in self.sz_stocks if text in s['name'] or text in s['code']]
        self._update_table(self.sh_table, sh_filtered)
        self._update_table(self.sz_table, sz_filtered)

    def _sort_stocks(self, index):
        """排序"""
        sort_keys = ['change_pct', 'ai_score', 'fund_flow', 'volume']
        key = sort_keys[index]

        self.sh_stocks.sort(key=lambda x: x.get(key, 0), reverse=True)
        self.sz_stocks.sort(key=lambda x: x.get(key, 0), reverse=True)

        self._update_table(self.sh_table, self.sh_stocks)
        self._update_table(self.sz_table, self.sz_stocks)
