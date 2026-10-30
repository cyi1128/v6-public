"""
【P4任务4】此文件为历史版本，当前未使用，保留供参考。
股票详情对话框 Pro版 - 三栏布局
左侧: 分时图 + 盘口
中间: 日K线 + 成交量 + KDJ + MACD
右侧: 信号历史 + 基本信息
专业量化交易终端风格 - 深色主题
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QFrame, QScrollArea, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath

from utils.indicators import (
    calc_ma_series, calc_kdj_series, calc_macd_series
)


class StockDetailProDialog(QDialog):
    """股票详情对话框 Pro版 - 三栏布局"""

    # 深色主题颜色
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
        'purple': '#bc8cff',
        'cyan': '#39d0d8',
    }

    # 信号颜色
    SIGNAL_COLORS = {
        '底部吸筹': '#00e676',
        '观察': '#2979ff',
        '买点': '#ff1744',
        '量价观察': '#ffea00',
        '穿九': '#d500f9',
        '站二十': '#00e5ff',
        '死叉观察': '#757575',
    }

    def __init__(self, ts_code, scheduler, parent=None):
        super().__init__(parent)
        self.ts_code = ts_code
        self.scheduler = scheduler
        self.stock_info = scheduler.get_stock_detail(ts_code)

        self.setWindowTitle(f"{self.stock_info.get('name', '')} ({ts_code}) - 股票详情")
        self.setMinimumSize(1400, 850)
        self.setStyleSheet(f"background-color: {self.DARK_COLORS['bg_primary']};")

        self._init_ui()
        self._setup_timer()

    def _init_ui(self):
        """初始化界面 - 三栏布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部信息栏
        main_layout.addWidget(self._create_header())

        # 主体三栏布局
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(10)

        # 左栏: 分时图 + 盘口
        left_panel = self._create_left_panel()
        body_layout.addWidget(left_panel, 2)

        # 中栏: K线图 + 指标
        center_panel = self._create_center_panel()
        body_layout.addWidget(center_panel, 4)

        # 右栏: 信号历史 + 基本信息
        right_panel = self._create_right_panel()
        body_layout.addWidget(right_panel, 2)

        main_layout.addLayout(body_layout, 1)

    def _create_header(self):
        """创建顶部信息栏"""
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border-bottom: 1px solid {self.DARK_COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(20)

        name = self.stock_info.get('name', '')
        price = self.stock_info.get('realtime', {}).get('price', 0)
        if not price:
            daily = self.stock_info.get('daily_data', [])
            if daily:
                price = daily[-1].get('close', 0)

        pct_chg = self.stock_info.get('realtime', {}).get('pct_chg', 0)
        if not pct_chg:
            daily = self.stock_info.get('daily_data', [])
            if daily:
                pct_chg = daily[-1].get('pct_chg', 0)

        # 股票名称和代码
        name_layout = QVBoxLayout()
        name_label = QLabel(f"{name}")
        name_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #f0f6fc;")
        code_label = QLabel(f"{self.ts_code}")
        code_label.setStyleSheet(f"font-size: 14px; color: {self.DARK_COLORS['text_secondary']};")
        name_layout.addWidget(name_label)
        name_layout.addWidget(code_label)
        layout.addLayout(name_layout)

        # 当前价格
        price_color = self.DARK_COLORS['red'] if pct_chg >= 0 else self.DARK_COLORS['green']
        price_layout = QVBoxLayout()
        price_label = QLabel(f"{price:.2f}")
        price_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {price_color};")
        pct_label = QLabel(f"{pct_chg:+.2f}%")
        pct_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {price_color};")
        price_layout.addWidget(price_label)
        price_layout.addWidget(pct_label)
        layout.addLayout(price_layout)

        layout.addSpacing(30)

        # 基本数据
        daily = self.stock_info.get('daily_data', [])
        if daily:
            last = daily[-1]
            high = last.get('high', 0)
            low = last.get('low', 0)
            vol = last.get('volume', 0)
            amount = last.get('amount', 0)

            info_items = [
                ("最高", f"{high:.2f}", self.DARK_COLORS['red']),
                ("最低", f"{low:.2f}", self.DARK_COLORS['green']),
                ("成交量", f"{vol/10000:.0f}万", self.DARK_COLORS['text_primary']),
                ("成交额", f"{amount/100000000:.2f}亿" if amount > 0 else '-', self.DARK_COLORS['text_primary']),
            ]

            for label, value, color in info_items:
                item_layout = QVBoxLayout()
                l = QLabel(label)
                l.setStyleSheet(f"font-size: 11px; color: {self.DARK_COLORS['text_secondary']};")
                v = QLabel(value)
                v.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
                item_layout.addWidget(l)
                item_layout.addWidget(v)
                layout.addLayout(item_layout)
                layout.addSpacing(15)

        layout.addStretch()

        # 信号标签
        signals = self.stock_info.get('signals', [])
        if signals:
            sig_layout = QVBoxLayout()
            sig_title = QLabel("当前信号")
            sig_title.setStyleSheet(f"font-size: 11px; color: {self.DARK_COLORS['text_secondary']};")
            sig_layout.addWidget(sig_title)

            sig_text = ' | '.join([s['name'] for s in signals])
            sig_label = QLabel(sig_text)
            top_color = self.SIGNAL_COLORS.get(signals[0]['name'], self.DARK_COLORS['accent'])
            sig_label.setStyleSheet(f"""
                font-size: 13px;
                font-weight: bold;
                color: {top_color};
                background-color: {self.DARK_COLORS['bg_tertiary']};
                padding: 4px 12px;
                border-radius: 12px;
            """)
            sig_layout.addWidget(sig_label)
            layout.addLayout(sig_layout)

        return header

    def _create_left_panel(self):
        """创建左栏 - 分时图 + 盘口"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 分时图标题
        title = QLabel("📈 实时分时")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.DARK_COLORS['text_primary']};")
        layout.addWidget(title)

        # 分时图画布
        self.minute_chart = MinuteChartPro()
        self.minute_chart.setMinimumHeight(280)
        minute_data = self._load_minute_data()
        self.minute_chart.set_data(minute_data)
        layout.addWidget(self.minute_chart)

        # 盘口
        order_title = QLabel("📊 五档盘口")
        order_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.DARK_COLORS['text_primary']};")
        layout.addWidget(order_title)

        order_layout = QHBoxLayout()

        # 买盘
        buy_group = QFrame()
        buy_group.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        buy_layout = QVBoxLayout(buy_group)
        buy_title = QLabel("买盘")
        buy_title.setStyleSheet(f"font-weight: bold; color: {self.DARK_COLORS['green']}; font-size: 12px;")
        buy_layout.addWidget(buy_title)

        realtime = self.stock_info.get('realtime', {})
        for i in range(1, 6):
            price = realtime.get(f'bid{i}', 0)
            vol = realtime.get(f'bid{i}_vol', 0)
            if price > 0:
                item = QLabel(f"买{i}: {price:.2f}  {vol:.0f}手")
                item.setStyleSheet(f"color: {self.DARK_COLORS['green']}; padding: 2px; font-size: 11px;")
                buy_layout.addWidget(item)
            else:
                item = QLabel(f"买{i}: --")
                item.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; padding: 2px; font-size: 11px;")
                buy_layout.addWidget(item)

        order_layout.addWidget(buy_group)

        # 卖盘
        sell_group = QFrame()
        sell_group.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        sell_layout = QVBoxLayout(sell_group)
        sell_title = QLabel("卖盘")
        sell_title.setStyleSheet(f"font-weight: bold; color: {self.DARK_COLORS['red']}; font-size: 12px;")
        sell_layout.addWidget(sell_title)

        for i in range(1, 6):
            price = realtime.get(f'ask{i}', 0)
            vol = realtime.get(f'ask{i}_vol', 0)
            if price > 0:
                item = QLabel(f"卖{i}: {price:.2f}  {vol:.0f}手")
                item.setStyleSheet(f"color: {self.DARK_COLORS['red']}; padding: 2px; font-size: 11px;")
                sell_layout.addWidget(item)
            else:
                item = QLabel(f"卖{i}: --")
                item.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; padding: 2px; font-size: 11px;")
                sell_layout.addWidget(item)

        order_layout.addWidget(sell_group)

        layout.addLayout(order_layout)

        return panel

    def _create_center_panel(self):
        """创建中栏 - K线图 + 指标"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 标题栏
        title_layout = QHBoxLayout()
        title = QLabel("📊 日K线图")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.DARK_COLORS['text_primary']};")
        title_layout.addWidget(title)

        title_layout.addStretch()

        # 均线图例
        legends = [
            ("MA5", self.DARK_COLORS['yellow']),
            ("MA9", self.DARK_COLORS['purple']),
            ("MA20", self.DARK_COLORS['cyan']),
        ]
        for name, color in legends:
            label = QLabel(f"━ {name}")
            label.setStyleSheet(f"color: {color}; font-size: 11px; padding: 0 8px;")
            title_layout.addWidget(label)

        layout.addLayout(title_layout)

        # K线图画布
        self.daily_chart = DailyChartPro()
        self.daily_chart.setMinimumHeight(550)
        daily_data = self.stock_info.get('daily_data', [])
        self.daily_chart.set_data(daily_data)
        layout.addWidget(self.daily_chart, 1)

        return panel

    def _create_right_panel(self):
        """创建右栏 - 信号历史 + 基本信息"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 信号历史
        sig_title = QLabel("🎯 信号历史")
        sig_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.DARK_COLORS['text_primary']};")
        layout.addWidget(sig_title)

        # 信号列表
        self.signal_list = QTableWidget()
        self.signal_list.setColumnCount(3)
        self.signal_list.setHorizontalHeaderLabels(["时间", "信号", "触发原因"])
        self.signal_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.signal_list.setAlternatingRowColors(True)
        self.signal_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.signal_list.verticalHeader().setVisible(False)
        self.signal_list.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                gridline-color: {self.DARK_COLORS['border']};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_secondary']};
                padding: 6px;
                border: none;
                font-size: 11px;
            }}
        """)

        # 填充当前信号
        signals = self.stock_info.get('signals', [])
        self.signal_list.setRowCount(len(signals))
        for i, sig in enumerate(signals):
            time_item = QTableWidgetItem("今日")
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            sig_item = QTableWidgetItem(sig['name'])
            sig_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = self.SIGNAL_COLORS.get(sig['name'], self.DARK_COLORS['text_primary'])
            sig_item.setForeground(QColor(color))
            font = sig_item.font()
            font.setBold(True)
            sig_item.setFont(font)

            desc_item = QTableWidgetItem(sig.get('description', ''))
            desc_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            self.signal_list.setItem(i, 0, time_item)
            self.signal_list.setItem(i, 1, sig_item)
            self.signal_list.setItem(i, 2, desc_item)

        layout.addWidget(self.signal_list, 1)

        # 基本信息
        info_title = QLabel("📋 基本信息")
        info_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.DARK_COLORS['text_primary']};")
        layout.addWidget(info_title)

        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        info_layout = QGridLayout(info_frame)

        industry = self.stock_info.get('industry', '未知')
        market_cap = self.stock_info.get('market_cap', 0)
        turnover_rate = self.stock_info.get('turnover_rate', 0)
        main_business = self.stock_info.get('main_business', '')
        pe = self.stock_info.get('pe', 0)
        pb = self.stock_info.get('pb', 0)

        info_items = [
            ("行业", industry),
            ("总市值", f"{market_cap:.1f}亿" if market_cap > 0 else '-'),
            ("换手率", f"{turnover_rate:.2f}%" if turnover_rate > 0 else '-'),
            ("市盈率", f"{pe:.2f}" if pe > 0 else '-'),
            ("市净率", f"{pb:.2f}" if pb > 0 else '-'),
            ("交易系统", "主升龙头"),
            ("KDJ参数", "13, 3, 3"),
            ("MACD参数", "8, 21, 5"),
            ("均线", "MA5/MA9/MA20"),
        ]

        for i, (label, value) in enumerate(info_items):
            row = i // 2
            col = (i % 2) * 2

            l = QLabel(label)
            l.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px;")
            info_layout.addWidget(l, row, col)

            v = QLabel(str(value))
            v.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 12px; font-weight: bold;")
            info_layout.addWidget(v, row, col + 1)

        # 主营业务（单独一行，可换行）
        if main_business:
            mb_label = QLabel("主营业务")
            mb_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px;")
            info_layout.addWidget(mb_label, len(info_items) // 2 + 1, 0)

            mb_value = QLabel(main_business)
            mb_value.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 11px;")
            mb_value.setWordWrap(True)
            info_layout.addWidget(mb_value, len(info_items) // 2 + 1, 1, 1, 3)

        layout.addWidget(info_frame)

        return panel

    def _load_minute_data(self):
        """加载分时数据"""
        try:
            from market import get_data_provider
            provider = get_data_provider()
            minute_data = provider.get_minute_data(self.ts_code)
            return minute_data
        except Exception:
            return []

    def _setup_timer(self):
        """设置定时器(实时刷新)"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(5000)  # 5秒刷新一次

    def _refresh_data(self):
        """刷新数据"""
        minute_data = self._load_minute_data()
        if minute_data:
            self.minute_chart.set_data(minute_data)
            self.minute_chart.update()

    def closeEvent(self, event):
        """关闭事件"""
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        event.accept()


class MinuteChartPro(QWidget):
    """分时图画布 - 深色主题"""

    DARK_COLORS = {
        'bg': '#ffffff',
        'grid': '#e0e0e0',
        'text': '#000000',
        'price_line': '#e74c3c',
        'avg_line': '#f39c12',
        'vol_up': '#e74c3c',
        'vol_down': '#2ecc71',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumSize(300, 250)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, QColor(self.DARK_COLORS['bg']))

        if not self.data:
            painter.setPen(QColor(self.DARK_COLORS['text']))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "暂无分时数据")
            return

        prices = [d.get('price', 0) for d in self.data if d.get('price', 0) > 0]
        if not prices:
            return

        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = max_price * 0.02

        margin_left = 50
        margin_right = 10
        margin_top = 20
        margin_bottom = 40

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        prev_close = prices[0]

        # 网格
        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))

            price = max_price - price_range * i / 4
            painter.setPen(QColor(self.DARK_COLORS['text']))
            painter.drawText(5, int(y) + 4, f"{price:.2f}")
            painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))

        # 价格线
        if len(self.data) > 1:
            path = QPainterPath()
            avg_path = QPainterPath()

            for i, d in enumerate(self.data):
                price = d.get('price', 0)
                avg_price = d.get('avg_price', 0)
                if price <= 0:
                    continue

                x = margin_left + chart_w * i / max(len(self.data) - 1, 1)
                y = margin_top + chart_h * (max_price - price) / price_range

                if i == 0 or path.currentPosition().isNull():
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

                if avg_price > 0:
                    avg_y = margin_top + chart_h * (max_price - avg_price) / price_range
                    if i == 0 or avg_path.currentPosition().isNull():
                        avg_path.moveTo(x, avg_y)
                    else:
                        avg_path.lineTo(x, avg_y)

            painter.setPen(QPen(QColor(self.DARK_COLORS['price_line']), 1.5))
            painter.drawPath(path)

            if not avg_path.isEmpty():
                painter.setPen(QPen(QColor(self.DARK_COLORS['avg_line']), 1))
                painter.drawPath(avg_path)

            # 成交量
            vol_h = 30
            vol_top = h - margin_bottom + 5
            volumes = [d.get('volume', 0) for d in self.data]
            max_vol = max(volumes) if volumes else 1
            if max_vol == 0:
                max_vol = 1

            for i, d in enumerate(self.data):
                vol = d.get('volume', 0)
                if vol <= 0:
                    continue

                x = margin_left + chart_w * i / max(len(self.data) - 1, 1)
                bar_h = vol_h * vol / max_vol

                price = d.get('price', 0)
                if i > 0 and self.data[i-1].get('price', 0) > 0:
                    if price >= self.data[i-1].get('price', 0):
                        color = self.DARK_COLORS['vol_up']
                    else:
                        color = self.DARK_COLORS['vol_down']
                else:
                    color = self.DARK_COLORS['vol_up']

                painter.fillRect(int(x - 1), int(vol_top + vol_h - bar_h), 2, int(bar_h), QColor(color))

        # 昨收线
        if prev_close > 0:
            y = margin_top + chart_h * (max_price - prev_close) / price_range
            painter.setPen(QPen(QColor(self.DARK_COLORS['text']), 1, Qt.PenStyle.DashLine))
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))


class DailyChartPro(QWidget):
    """日线图画布 Pro版 - 深色主题"""

    DARK_COLORS = {
        'bg': '#ffffff',
        'grid': '#e0e0e0',
        'text': '#000000',
        'candle_up': '#e74c3c',
        'candle_down': '#2ecc71',
        'ma5': '#f39c12',
        'ma9': '#9b59b6',
        'ma20': '#1abc9c',
        'kdj_k': '#000000',
        'kdj_d': '#f39c12',
        'kdj_j': '#9b59b6',
        'macd_dif': '#000000',
        'macd_dea': '#f39c12',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.ma5_series = None
        self.ma9_series = None
        self.ma20_series = None
        self.k_series = None
        self.d_series = None
        self.j_series = None
        self.dif_series = None
        self.dea_series = None
        self.macd_hist = None
        self.setMinimumSize(500, 500)

    def set_data(self, data):
        self.data = data

        if not data or len(data) < 30:
            return

        close_prices = [d['close'] for d in data]
        high_prices = [d['high'] for d in data]
        low_prices = [d['low'] for d in data]

        self.ma5_series = calc_ma_series(close_prices, 5)
        self.ma9_series = calc_ma_series(close_prices, 9)
        self.ma20_series = calc_ma_series(close_prices, 20)

        self.k_series, self.d_series, self.j_series = calc_kdj_series(
            high_prices, low_prices, close_prices
        )

        self.dif_series, self.dea_series, self.macd_hist = calc_macd_series(close_prices)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, QColor(self.DARK_COLORS['bg']))

        if not self.data or len(self.data) < 30:
            painter.setPen(QColor(self.DARK_COLORS['text']))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "数据不足")
            return

        show_count = min(60, len(self.data))
        data = self.data[-show_count:]

        margin_left = 55
        margin_right = 15
        margin_top = 20

        total_h = h - margin_top - 10
        kline_h = int(total_h * 0.45)
        vol_h = int(total_h * 0.15)
        kdj_h = int(total_h * 0.18)
        macd_h = int(total_h * 0.22)

        kline_top = margin_top
        vol_top = kline_top + kline_h + 10
        kdj_top = vol_top + vol_h + 10
        macd_top = kdj_top + kdj_h + 10

        chart_w = w - margin_left - margin_right

        high_prices = [d['high'] for d in data]
        low_prices = [d['low'] for d in data]
        max_price = max(high_prices)
        min_price = min(low_prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = max_price * 0.02

        # K线
        self._draw_kline(painter, data, margin_left, kline_top, chart_w, kline_h,
                         max_price, min_price, price_range)

        # 均线
        self._draw_ma_lines(painter, data, margin_left, kline_top, chart_w, kline_h,
                           max_price, min_price, price_range)

        # 成交量
        self._draw_volume(painter, data, margin_left, vol_top, chart_w, vol_h)

        # KDJ
        self._draw_kdj(painter, data, margin_left, kdj_top, chart_w, kdj_h)

        # MACD
        self._draw_macd(painter, data, margin_left, macd_top, chart_w, macd_h)

    def _draw_kline(self, painter, data, x, y, w, h, max_p, min_p, p_range):
        painter.save()

        # 网格
        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))
        for i in range(5):
            gy = y + h * i / 4
            painter.drawLine(x, int(gy), x + w, int(gy))

            price = max_p - p_range * i / 4
            painter.setPen(QColor(self.DARK_COLORS['text']))
            painter.drawText(5, int(gy) + 4, f"{price:.2f}")
            painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))

        candle_w = max(3, w / len(data) * 0.7)

        for i, d in enumerate(data):
            cx = x + w * (i + 0.5) / len(data)
            open_p = d['open']
            close_p = d['close']
            high_p = d['high']
            low_p = d['low']

            def price_to_y(price):
                return y + h * (max_p - price) / p_range

            high_y = price_to_y(high_p)
            low_y = price_to_y(low_p)
            open_y = price_to_y(open_p)
            close_y = price_to_y(close_p)

            if close_p >= open_p:
                color = QColor(self.DARK_COLORS['candle_up'])
            else:
                color = QColor(self.DARK_COLORS['candle_down'])

            painter.setPen(QPen(color, 1))
            painter.drawLine(int(cx), int(high_y), int(cx), int(low_y))

            body_top = min(open_y, close_y)
            body_h = abs(close_y - open_y)
            if body_h < 1:
                body_h = 1

            painter.setBrush(color)
            painter.drawRect(int(cx - candle_w/2), int(body_top), int(candle_w), int(body_h))

        painter.restore()

    def _draw_ma_lines(self, painter, data, x, y, w, h, max_p, min_p, p_range):
        if self.ma5_series is None:
            return

        n = len(data)
        start_idx = len(self.data) - n

        def price_to_y(price):
            return y + h * (max_p - price) / p_range

        ma_configs = [
            (self.ma5_series, self.DARK_COLORS['ma5']),
            (self.ma9_series, self.DARK_COLORS['ma9']),
            (self.ma20_series, self.DARK_COLORS['ma20']),
        ]

        for series, color in ma_configs:
            if series is None:
                continue
            painter.setPen(QPen(QColor(color), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(series):
                    break
                val = series.iloc[idx]
                if pd.isna(val):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = price_to_y(val)
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

    def _draw_volume(self, painter, data, x, y, w, h):
        painter.save()

        painter.setPen(QColor(self.DARK_COLORS['text']))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "成交量")

        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))
        painter.drawLine(x, y, x + w, y)
        painter.drawLine(x, y + h, x + w, y + h)

        volumes = [d.get('volume', d.get('vol', 0)) for d in data]
        max_vol = max(volumes) if volumes else 1
        if max_vol == 0:
            max_vol = 1

        bar_w = max(2, w / len(data) * 0.7)

        for i, d in enumerate(data):
            vol = d.get('volume', d.get('vol', 0))
            if vol <= 0:
                continue

            cx = x + w * (i + 0.5) / len(data)
            bar_h = h * vol / max_vol

            open_p = d['open']
            close_p = d['close']
            if close_p >= open_p:
                color = QColor(self.DARK_COLORS['candle_up'])
            else:
                color = QColor(self.DARK_COLORS['candle_down'])

            painter.fillRect(int(cx - bar_w/2), int(y + h - bar_h), int(bar_w), int(bar_h), color)

        painter.restore()

    def _draw_kdj(self, painter, data, x, y, w, h):
        painter.save()

        painter.setPen(QColor(self.DARK_COLORS['text']))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "KDJ(13,3,3)")

        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1))
        painter.drawLine(x, y, x + w, y)
        painter.drawLine(x, y + h, x + w, y + h)

        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1, Qt.PenStyle.DashLine))
        painter.drawLine(x, int(y + h * 0.2), x + w, int(y + h * 0.2))
        painter.drawLine(x, int(y + h * 0.8), x + w, int(y + h * 0.8))

        if self.k_series is None:
            painter.restore()
            return

        n = len(data)
        start_idx = len(self.data) - n

        kdj_min = -20
        kdj_max = 120
        kdj_range = kdj_max - kdj_min

        def kdj_to_y(val):
            return y + h * (kdj_max - val) / kdj_range

        kdj_configs = [
            (self.k_series, self.DARK_COLORS['kdj_k']),
            (self.d_series, self.DARK_COLORS['kdj_d']),
            (self.j_series, self.DARK_COLORS['kdj_j']),
        ]

        for series, color in kdj_configs:
            if series is None:
                continue
            painter.setPen(QPen(QColor(color), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(series):
                    break
                val = series.iloc[idx]
                if pd.isna(val):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = kdj_to_y(val)
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

        painter.restore()

    def _draw_macd(self, painter, data, x, y, w, h):
        painter.save()

        painter.setPen(QColor(self.DARK_COLORS['text']))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "MACD(8,21,5)")

        zero_y = y + h / 2
        painter.setPen(QPen(QColor(self.DARK_COLORS['grid']), 1, Qt.PenStyle.DashLine))
        painter.drawLine(x, int(zero_y), x + w, int(zero_y))

        if self.macd_hist is None:
            painter.restore()
            return

        n = len(data)
        start_idx = len(self.data) - n

        hist_values = []
        for i in range(n):
            idx = start_idx + i
            if idx < len(self.macd_hist):
                val = self.macd_hist.iloc[idx]
                if not pd.isna(val):
                    hist_values.append(abs(val))

        if not hist_values:
            painter.restore()
            return

        max_hist = max(hist_values) * 1.2
        if max_hist == 0:
            max_hist = 1

        bar_w = max(2, w / len(data) * 0.7)

        for i in range(n):
            idx = start_idx + i
            if idx >= len(self.macd_hist):
                continue
            hist_val = self.macd_hist.iloc[idx]
            if pd.isna(hist_val):
                continue

            cx = x + w * (i + 0.5) / n
            bar_h = h / 2 * abs(hist_val) / max_hist

            if hist_val >= 0:
                color = QColor(self.DARK_COLORS['candle_up'])
                bar_y = zero_y - bar_h
            else:
                color = QColor(self.DARK_COLORS['candle_down'])
                bar_y = zero_y

            painter.fillRect(int(cx - bar_w/2), int(bar_y), int(bar_w), int(bar_h), color)

        # DIF / DEA
        for series, color in [
            (self.dif_series, self.DARK_COLORS['macd_dif']),
            (self.dea_series, self.DARK_COLORS['macd_dea']),
        ]:
            if series is None:
                continue
            painter.setPen(QPen(QColor(color), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(series):
                    break
                val = series.iloc[idx]
                if pd.isna(val):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = zero_y - h / 2 * val / max_hist
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

        painter.restore()


# 导入pandas用于isna判断
import pandas as pd
