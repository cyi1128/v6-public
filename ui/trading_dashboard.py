"""
AI交易驾驶舱首页
显示：市场总览、指数、成交额、涨跌家数、涨停跌停、市场情绪周期、AI判断、今日操作、建议仓位
机构交易终端风格，深色主题
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette
import requests
from datetime import datetime

from strategy.market_state_engine import MarketStateEngine
from strategy.strategy_selector import StrategySelector


class TradingDashboard(QWidget):
    """AI交易驾驶舱首页"""

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
        'yellow': '#e3b341',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.market_engine = MarketStateEngine()
        self.strategy_selector = StrategySelector()
        self._init_ui()
        self._setup_timer()
        self.refresh_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部：标题 + 时间
        layout.addWidget(self._create_header())

        # 指数卡片行
        layout.addWidget(self._create_index_cards())

        # 市场数据行
        layout.addWidget(self._create_market_stats())

        # AI决策行
        layout.addWidget(self._create_ai_decision())

        # 底部：热门板块 + 涨跌排行
        bottom = QHBoxLayout()
        bottom.addWidget(self._create_hot_sectors(), 1)
        bottom.addWidget(self._create_top_gainers(), 1)
        layout.addLayout(bottom, 1)

    def _create_header(self):
        """创建标题栏"""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)

        title = QLabel('🚀 AI交易驾驶舱')
        title.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        layout.addStretch()

        self.time_label = QLabel(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.time_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 13px;")
        layout.addWidget(self.time_label)

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
            QPushButton:hover {{ background-color: #79b8ff; }}
        """)
        refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_btn)

        return bar

    def _create_index_cards(self):
        """创建指数卡片"""
        bar = QFrame()
        bar.setFixedHeight(100)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        # 上证指数
        self.sh_index = self._create_index_card('上证指数', '000001', 'sh')
        layout.addWidget(self.sh_index)

        # 深证指数
        self.sz_index = self._create_index_card('深证成指', '399001', 'sz')
        layout.addWidget(self.sz_index)

        # 创业板指
        self.cy_index = self._create_index_card('创业板指', '399006', 'sz')
        layout.addWidget(self.cy_index)

        return bar

    def _create_index_card(self, name, code, market):
        """创建单个指数卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(3)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(name_label)

        price_label = QLabel('--')
        price_label.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 20px; font-weight: bold;")
        layout.addWidget(price_label)

        change_label = QLabel('--')
        change_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(change_label)

        # 保存引用
        card.price_label = price_label
        card.change_label = change_label
        card.market = market
        card.code = code

        return card

    def _create_market_stats(self):
        """创建市场统计数据"""
        bar = QFrame()
        bar.setFixedHeight(90)
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
            ('两市成交额', 'amount', '#58a6ff'),
            ('上涨家数', 'up_count', '#f85149'),
            ('下跌家数', 'down_count', '#3fb950'),
            ('涨停数量', 'limit_up', '#ff1744'),
            ('跌停数量', 'limit_down', '#00e676'),
            ('市场情绪', 'sentiment', '#d29922'),
        ]

        self.stat_labels = {}
        for name, key, color in stats:
            stat_layout = QVBoxLayout()
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
            value_label = QLabel('--')
            value_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
            stat_layout.addWidget(name_label)
            stat_layout.addWidget(value_label)
            layout.addLayout(stat_layout)
            self.stat_labels[key] = value_label

        return bar

    def _create_ai_decision(self):
        """创建AI决策面板"""
        bar = QFrame()
        bar.setFixedHeight(110)
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

        # 市场状态
        state_layout = QVBoxLayout()
        state_label = QLabel('市场状态')
        state_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.market_state_label = QLabel('分析中...')
        self.market_state_label.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 22px; font-weight: bold;")
        state_layout.addWidget(state_label)
        state_layout.addWidget(self.market_state_label)
        layout.addLayout(state_layout)

        # 分隔
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line)

        # 今日操作
        op_layout = QVBoxLayout()
        op_label = QLabel('今日操作')
        op_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.operation_label = QLabel('--')
        self.operation_label.setStyleSheet(f"color: {self.DARK_COLORS['orange']}; font-size: 22px; font-weight: bold;")
        op_layout.addWidget(op_label)
        op_layout.addWidget(self.operation_label)
        layout.addLayout(op_layout)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.VLine)
        line2.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line2)

        # 建议仓位
        pos_layout = QVBoxLayout()
        pos_label = QLabel('建议仓位')
        pos_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.position_label = QLabel('--')
        self.position_label.setStyleSheet(f"color: {self.DARK_COLORS['green']}; font-size: 22px; font-weight: bold;")
        pos_layout.addWidget(pos_label)
        pos_layout.addWidget(self.position_label)
        layout.addLayout(pos_layout)

        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.VLine)
        line3.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line3)

        # 推荐策略
        strat_layout = QVBoxLayout()
        strat_label = QLabel('推荐策略')
        strat_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.strategy_label = QLabel('--')
        self.strategy_label.setStyleSheet(f"color: {self.DARK_COLORS['red']}; font-size: 18px; font-weight: bold;")
        strat_layout.addWidget(strat_label)
        strat_layout.addWidget(self.strategy_label)
        layout.addLayout(strat_layout)

        layout.addStretch()

        # AI分析原因
        self.reason_label = QLabel('')
        self.reason_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.reason_label.setWordWrap(True)
        layout.addWidget(self.reason_label, 2)

        return bar

    def _create_hot_sectors(self):
        """创建热门板块"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('🔥 热门板块')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        self.sector_table = QTableWidget()
        self.sector_table.setColumnCount(3)
        self.sector_table.setHorizontalHeaderLabels(['板块', '涨幅', '资金流入(亿)'])
        self.sector_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sector_table.setStyleSheet(f"""
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
                padding: 5px;
            }}
        """)
        self.sector_table.verticalHeader().setVisible(False)
        layout.addWidget(self.sector_table, 1)

        return frame

    def _create_top_gainers(self):
        """创建涨幅排行"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('📈 涨幅排行')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        self.gainer_table = QTableWidget()
        self.gainer_table.setColumnCount(3)
        self.gainer_table.setHorizontalHeaderLabels(['股票', '现价', '涨幅'])
        self.gainer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.gainer_table.setStyleSheet(f"""
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
                padding: 5px;
            }}
        """)
        self.gainer_table.verticalHeader().setVisible(False)
        layout.addWidget(self.gainer_table, 1)

        return frame

    def _setup_timer(self):
        """设置定时刷新"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)

        # 数据刷新定时器（60秒）
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.refresh_data)
        self.data_timer.start(60000)

    def _update_time(self):
        """更新时间"""
        self.time_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def refresh_data(self):
        """刷新所有数据"""
        self._refresh_indexes()
        self._refresh_market_stats()
        self._refresh_ai_decision()
        self._refresh_sectors()
        self._refresh_gainers()

    def _refresh_indexes(self):
        """刷新指数"""
        indexes = [
            (self.sh_index, 'sh000001'),
            (self.sz_index, 'sz399001'),
            (self.cy_index, 'sz399006'),
        ]

        for card, code in indexes:
            try:
                url = f'https://qt.gtimg.cn/q={code}'
                resp = requests.get(url, timeout=5)
                text = resp.content.decode('gbk', errors='ignore')
                parts = text.split('"')[1].split('~')

                if len(parts) > 32:
                    price = parts[3]
                    change = parts[31] if len(parts) > 31 else '0'
                    change_pct = parts[32] if len(parts) > 32 else '0'

                    card.price_label.setText(price)
                    color = '#f85149' if float(change_pct) >= 0 else '#3fb950'
                    card.change_label.setText(f'{change} ({change_pct}%)')
                    card.change_label.setStyleSheet(f"color: {color}; font-size: 12px;")
            except Exception:
                pass

    def _refresh_market_stats(self):
        """刷新市场统计"""
        try:
            # 获取涨跌家数和涨跌停（东方财富API）
            url = 'https://push2delay.eastmoney.com/api/qt/stock/get'
            params = {
                'fltt': 2,
                'fields': 'f104,f105,f106,f107,f108',
                'secid': '1.000001',
            }
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()

            if data.get('data'):
                up = data['data'].get('f104', 0)
                down = data['data'].get('f105', 0)
                flat = data['data'].get('f106', 0)
                limit_up = data['data'].get('f107', 0)
                limit_down = data['data'].get('f108', 0)

                self.stat_labels['up_count'].setText(str(up))
                self.stat_labels['down_count'].setText(str(down))
                self.stat_labels['limit_up'].setText(str(limit_up))
                self.stat_labels['limit_down'].setText(str(limit_down))

            # 获取两市成交额
            url2 = 'https://push2delay.eastmoney.com/api/qt/ulist.np/get'
            params2 = {
                'fltt': 2,
                'fields': 'f6',
                'secids': '1.000001,0.399001',
            }
            resp2 = requests.get(url2, params=params2, timeout=5)
            data2 = resp2.json()

            if data2.get('data') and data2['data'].get('diff'):
                total_amount = sum(item.get('f6', 0) for item in data2['data']['diff']) / 100000000
                self.stat_labels['amount'].setText(f'{total_amount:.0f}亿')

        except Exception as e:
            pass

    def _refresh_ai_decision(self):
        """刷新AI决策"""
        try:
            result = self.strategy_selector.select_strategy()

            state = result['market_state']
            self.market_state_label.setText(state)
            self.market_state_label.setStyleSheet(f"color: {result['market_state_color']}; font-size: 22px; font-weight: bold;")

            # 今日操作
            if '牛市' in state or '偏强' in state:
                operation = '进攻'
                op_color = '#f85149'
            elif '熊市' in state or '偏弱' in state:
                operation = '防守'
                op_color = '#3fb950'
            else:
                operation = '等待'
                op_color = '#d29922'

            self.operation_label.setText(operation)
            self.operation_label.setStyleSheet(f"color: {op_color}; font-size: 22px; font-weight: bold;")

            self.position_label.setText(f"{result['position_min']}-{result['position_max']}%")
            self.strategy_label.setText(result['selected_strategy'])
            self.strategy_label.setStyleSheet(f"color: {result['strategy_color']}; font-size: 18px; font-weight: bold;")

            reasons = result.get('reasons', [])
            self.reason_label.setText(' | '.join(reasons[:3]))

            # 情绪
            sentiment = result.get('market_details', {}).get('sentiment_score', 50)
            if sentiment >= 70:
                self.stat_labels['sentiment'].setText('强势')
            elif sentiment >= 45:
                self.stat_labels['sentiment'].setText('震荡')
            else:
                self.stat_labels['sentiment'].setText('弱势')

        except Exception as e:
            pass

    def _refresh_sectors(self):
        """刷新热门板块"""
        try:
            # 东方财富行业板块API
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 8,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90+t:2',
                'fields': 'f2,f3,f12,f14,f62',
            }
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()

            if data.get('data') and data['data'].get('diff'):
                sectors = data['data']['diff']
                self.sector_table.setRowCount(len(sectors))
                for i, sector in enumerate(sectors):
                    self.sector_table.setItem(i, 0, QTableWidgetItem(sector.get('f14', '')))
                    change = sector.get('f3', 0)
                    change_item = QTableWidgetItem(f"{change:.2f}%")
                    change_item.setForeground(QColor('#f85149' if change >= 0 else '#3fb950'))
                    self.sector_table.setItem(i, 1, change_item)
                    # 主力资金（单位分，转亿）
                    fund_flow = sector.get('f62', 0) / 100000000
                    fund_item = QTableWidgetItem(f"{fund_flow:.1f}")
                    fund_item.setForeground(QColor('#f85149' if fund_flow >= 0 else '#3fb950'))
                    self.sector_table.setItem(i, 2, fund_item)
            else:
                self.sector_table.setRowCount(0)
        except Exception:
            self.sector_table.setRowCount(0)

    def _refresh_gainers(self):
        """刷新涨幅排行"""
        try:
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 8,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                'fields': 'f2,f3,f12,f14',
            }
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()

            if data.get('data') and data['data'].get('diff'):
                stocks = data['data']['diff']
                self.gainer_table.setRowCount(len(stocks))
                for i, stock in enumerate(stocks):
                    self.gainer_table.setItem(i, 0, QTableWidgetItem(stock.get('f14', '')))
                    self.gainer_table.setItem(i, 1, QTableWidgetItem(str(stock.get('f2', 0))))
                    change_item = QTableWidgetItem(f"{stock.get('f3', 0):.2f}%")
                    change_item.setForeground(QColor('#f85149'))
                    self.gainer_table.setItem(i, 2, change_item)
        except Exception:
            self.gainer_table.setRowCount(0)
