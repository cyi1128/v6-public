"""
股票消息雷达页面
自动扫描7×24快讯，AI过滤股票相关信息
显示：股票、代码、现价、消息、影响
颜色：利好绿色背景、重大利好红色闪烁、利空蓝色/灰色
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
import requests
from datetime import datetime

from strategy.stock_news_radar import StockNewsRadar


class NewsRadarWidget(QWidget):
    """股票消息雷达页面"""

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
        self.news_radar = StockNewsRadar()
        self.news_list = []
        self._init_ui()
        self._load_news()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部栏
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

        title = QLabel('📡 股票消息雷达')
        title.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 16px; font-weight: bold;")
        top_layout.addWidget(title)

        # 统计
        self.stats_label = QLabel('加载中...')
        self.stats_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        top_layout.addWidget(self.stats_label)

        top_layout.addStretch()

        # 搜索
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索股票...')
        self.search_input.setFixedWidth(150)
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
        self.search_input.textChanged.connect(self._filter_news)
        top_layout.addWidget(self.search_input)

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
        refresh_btn.clicked.connect(self._load_news)
        top_layout.addWidget(refresh_btn)

        layout.addWidget(top_bar)

        # 消息表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['时间', '股票', '代码', '现价', '消息', '影响'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(5, 80)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
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
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        # 自动刷新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._load_news)
        self.timer.start(120000)  # 2分钟刷新

    def _load_news(self):
        """加载消息"""
        try:
            # 从7×24快讯获取
            url = 'https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=50&zhibo_id=152&tag_id=0&dire=f&dpc=1'
            resp = requests.get(url, timeout=8)
            data = resp.json()

            self.news_list = []
            if data.get('result') and data['result'].get('data') and data['result']['data'].get('feed'):
                for item in data['result']['data']['feed'].get('list', []):
                    content = item.get('rich_text', '')
                    if not content:
                        continue

                    # 分析消息
                    level, impact = self.news_radar._analyze_news(content)

                    # 提取股票名称（简单匹配）
                    stock_name, stock_code = self._extract_stock(content)

                    news_item = {
                        'time': datetime.fromtimestamp(item.get('create_time', 0)).strftime('%H:%M'),
                        'stock_name': stock_name,
                        'stock_code': stock_code,
                        'price': self._get_price(stock_code) if stock_code else '--',
                        'content': content[:100],
                        'level': level,
                        'impact': impact,
                        'color': self.news_radar.LEVEL_COLORS.get(level, '#8b949e'),
                    }
                    self.news_list.append(news_item)

            self._update_table(self.news_list)
            self._update_stats()

        except Exception as e:
            pass

    def _extract_stock(self, content):
        """从内容中提取股票（简化版）"""
        # 常见股票名称匹配
        stock_names = ['贵州茅台', '宁德时代', '比亚迪', '平安银行', '招商银行',
                       '中国平安', '五粮液', '美的集团', '格力电器', '恒瑞医药',
                       '中芯国际', '科大讯飞', '隆基绿能', '药明康德', '海康威视']

        for name in stock_names:
            if name in content:
                # 简单代码映射
                codes = {
                    '贵州茅台': '600519', '宁德时代': '300750', '比亚迪': '002594',
                    '平安银行': '000001', '招商银行': '600036', '中国平安': '601318',
                    '五粮液': '000858', '美的集团': '000333', '格力电器': '000651',
                    '恒瑞医药': '600276', '中芯国际': '688981', '科大讯飞': '002230',
                    '隆基绿能': '601012', '药明康德': '603259', '海康威视': '002415',
                }
                return name, codes.get(name, '')

        return '--', ''

    def _get_price(self, code):
        """获取股票价格"""
        try:
            if code.startswith('6'):
                market = 'sh'
            else:
                market = 'sz'
            url = f'https://qt.gtimg.cn/q={market}{code}'
            resp = requests.get(url, timeout=3)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')
            if len(parts) > 3:
                return parts[3]
        except Exception:
            pass
        return '--'

    def _update_table(self, news_list):
        """更新表格"""
        self.table.setRowCount(len(news_list))
        for i, news in enumerate(news_list):
            self.table.setItem(i, 0, QTableWidgetItem(news['time']))
            self.table.setItem(i, 1, QTableWidgetItem(news['stock_name']))
            self.table.setItem(i, 2, QTableWidgetItem(news['stock_code']))
            self.table.setItem(i, 3, QTableWidgetItem(str(news['price'])))
            self.table.setItem(i, 4, QTableWidgetItem(news['content']))

            impact_item = QTableWidgetItem(news['level'])
            impact_item.setForeground(QColor(news['color']))
            impact_item.setFont(QFont('Arial', 10, QFont.Weight.Bold))
            self.table.setItem(i, 5, impact_item)

            # 背景色
            if news['level'] == '重大利好':
                for col in range(6):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QColor(40, 20, 20))  # 淡红背景
            elif news['level'] == '普通利好':
                for col in range(6):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QColor(15, 35, 20))  # 淡绿背景
            elif news['level'] in ['风险提示', '重大利空']:
                for col in range(6):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QColor(20, 25, 35))  # 淡蓝背景

    def _update_stats(self):
        """更新统计"""
        major_positive = sum(1 for n in self.news_list if n['level'] == '重大利好')
        positive = sum(1 for n in self.news_list if n['level'] == '普通利好')
        risk = sum(1 for n in self.news_list if n['level'] == '风险提示')
        negative = sum(1 for n in self.news_list if n['level'] == '重大利空')

        self.stats_label.setText(
            f"共{len(self.news_list)}条 | 重大利好{major_positive} | 利好{positive} | 风险{risk} | 利空{negative}"
        )

    def _filter_news(self, text):
        """搜索过滤"""
        text = text.strip()
        if not text:
            self._update_table(self.news_list)
            return

        filtered = [n for n in self.news_list if text in n['stock_name'] or text in n['content']]
        self._update_table(filtered)
