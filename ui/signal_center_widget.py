"""
实时交易信号中心 - 三栏模式
买入信号（绿色）、观察信号（黄色）、风险提醒（红色）
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QScrollArea
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from datetime import datetime


class SignalCenterWidget(QWidget):
    """实时交易信号中心 - 三栏模式"""

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
        'yellow': '#ffea00',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buy_signals = []
        self.watch_signals = []
        self.risk_signals = []
        self._init_ui()
        self._generate_demo_signals()

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

        title = QLabel('🔔 实时交易信号中心')
        title.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 16px; font-weight: bold;")
        top_layout.addWidget(title)

        self.time_label = QLabel(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.time_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        top_layout.addWidget(self.time_label)

        top_layout.addStretch()

        refresh_btn = QPushButton('🔄 刷新信号')
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
        refresh_btn.clicked.connect(self._refresh_signals)
        top_layout.addWidget(refresh_btn)

        layout.addWidget(top_bar)

        # 三栏布局
        columns = QHBoxLayout()
        columns.setSpacing(10)

        # 买入信号栏
        columns.addWidget(self._create_signal_column(
            '买入信号', self.DARK_COLORS['green'], self.buy_signals, 'buy'
        ), 1)

        # 观察信号栏
        columns.addWidget(self._create_signal_column(
            '观察信号', self.DARK_COLORS['yellow'], self.watch_signals, 'watch'
        ), 1)

        # 风险提醒栏
        columns.addWidget(self._create_signal_column(
            '风险提醒', self.DARK_COLORS['red'], self.risk_signals, 'risk'
        ), 1)

        layout.addLayout(columns, 1)

        # 定时更新时间
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)

    def _create_signal_column(self, title, color, signals, signal_type):
        """创建信号栏"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {color};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel(f'● {title}')
        title_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        title_layout.addWidget(title_label)

        count_label = QLabel(f'({len(signals)})')
        count_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        title_layout.addWidget(count_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 信号列表（滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {self.DARK_COLORS['bg_primary']};
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {self.DARK_COLORS['border']};
                border-radius: 3px;
            }}
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        for signal in signals:
            card = self._create_signal_card(signal, color, signal_type)
            content_layout.addWidget(card)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # 保存引用以便更新
        if signal_type == 'buy':
            self.buy_scroll = scroll
            self.buy_content = content
        elif signal_type == 'watch':
            self.watch_scroll = scroll
            self.watch_content = content
        else:
            self.risk_scroll = scroll
            self.risk_content = content

        return frame

    def _create_signal_card(self, signal, color, signal_type):
        """创建信号卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border-left: 3px solid {color};
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 股票信息
        header = QHBoxLayout()
        name_label = QLabel(f"{signal.get('stock_name', '--')} ({signal.get('stock_code', '--')})")
        name_label.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 13px; font-weight: bold;")
        header.addWidget(name_label)
        header.addStretch()

        price_label = QLabel(f"¥{signal.get('price', 0):.2f}")
        price_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        header.addWidget(price_label)
        layout.addLayout(header)

        # 买入等级/等待条件/风险原因
        if signal_type == 'buy':
            level = signal.get('level', 3)
            stars = '★' * level + '☆' * (5 - level)
            level_label = QLabel(f"买入等级: {stars}")
            level_label.setStyleSheet(f"color: {self.DARK_COLORS['yellow']}; font-size: 11px;")
            layout.addWidget(level_label)
        elif signal_type == 'watch':
            wait_label = QLabel(f"等待: {signal.get('wait_for', '确认')}")
            wait_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px;")
            layout.addWidget(wait_label)
        else:
            risk_label = QLabel(f"风险: {signal.get('risk_reason', '未知')}")
            risk_label.setStyleSheet(f"color: {self.DARK_COLORS['red']}; font-size: 11px;")
            layout.addWidget(risk_label)

        # 理由
        reasons = signal.get('reasons', [])
        if reasons:
            reason_text = '\n'.join([f"{i+1}. {r}" for i, r in enumerate(reasons[:3])])
            reason_label = QLabel(reason_text)
            reason_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px;")
            reason_label.setWordWrap(True)
            layout.addWidget(reason_label)

        # 建议
        suggestion = signal.get('suggestion', '')
        if suggestion:
            sug_label = QLabel(f"💡 {suggestion}")
            sug_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            layout.addWidget(sug_label)

        # 时间
        time_label = QLabel(signal.get('time', ''))
        time_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 10px;")
        layout.addWidget(time_label)

        return card

    def _generate_demo_signals(self):
        """生成演示信号"""
        now = datetime.now().strftime('%H:%M:%S')

        self.buy_signals = [
            {
                'stock_name': '科大讯飞', 'stock_code': '002230', 'price': 45.80,
                'level': 5,
                'reasons': ['主力资金流入', 'KDJ低位金叉', 'AI消息催化'],
                'suggestion': '试仓30%，突破加仓',
                'time': now,
            },
            {
                'stock_name': '中芯国际', 'stock_code': '688981', 'price': 58.20,
                'level': 4,
                'reasons': ['放量突破', 'MACD金叉', '半导体板块强势'],
                'suggestion': '关注，回踩5日线介入',
                'time': now,
            },
        ]

        self.watch_signals = [
            {
                'stock_name': '宁德时代', 'stock_code': '300750', 'price': 198.50,
                'wait_for': '放量突破200元',
                'reasons': ['横盘整理', '量能萎缩', '等待方向选择'],
                'suggestion': '观望，突破后跟进',
                'time': now,
            },
            {
                'stock_name': '比亚迪', 'stock_code': '002594', 'price': 245.30,
                'wait_for': '回踩确认支撑',
                'reasons': ['短期涨幅较大', '需要消化获利盘'],
                'suggestion': '等待回踩240元附近',
                'time': now,
            },
        ]

        self.risk_signals = [
            {
                'stock_name': '贵州茅台', 'stock_code': '600519', 'price': 1680.00,
                'risk_reason': 'MACD死叉，资金流出',
                'reasons': ['跌破5日线', '成交量放大下跌', '主力净流出'],
                'suggestion': '减仓或止损',
                'time': now,
            },
        ]

    def _refresh_signals(self):
        """刷新信号"""
        self._generate_demo_signals()
        # 重新创建三栏（简化处理）
        # 实际应用中应该调用SignalCenter生成真实信号
        pass

    def _update_time(self):
        """更新时间"""
        self.time_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
