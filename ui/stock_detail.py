"""
股票详情对话框 - 分时图 + 日线图 + 指标
包含: MA5, MA9, MA20, KDJ(13,3,3), MACD(8,21,5)
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QFrame, QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath
from PyQt6.QtWidgets import QSizePolicy

from utils.indicators import (
    calc_ma_series, calc_kdj_series, calc_macd_series
)


class StockDetailDialog(QDialog):
    """股票详情对话框"""

    def __init__(self, ts_code, scheduler, parent=None):
        super().__init__(parent)
        self.ts_code = ts_code
        self.scheduler = scheduler
        self.stock_info = scheduler.get_stock_detail(ts_code)

        self.setWindowTitle(f"{self.stock_info.get('name', '')} ({ts_code}) - 股票详情")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("background-color: #f5f5f5;")

        self._init_ui()
        self._setup_timer()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部信息栏
        info_layout = QHBoxLayout()

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
        name_label = QLabel(f"{name}  {self.ts_code}")
        name_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        info_layout.addWidget(name_label)

        info_layout.addSpacing(30)

        # 当前价格
        price_color = '#d32f2f' if pct_chg >= 0 else '#388e3c'
        price_label = QLabel(f"{price:.2f}")
        price_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {price_color};")
        info_layout.addWidget(price_label)

        # 涨跌幅
        pct_label = QLabel(f"{pct_chg:+.2f}%")
        pct_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {price_color};")
        info_layout.addWidget(pct_label)

        info_layout.addStretch()

        # 信号标签
        signals = self.stock_info.get('signals', [])
        if signals:
            sig_text = ' | '.join([s['name'] for s in signals])
            sig_label = QLabel(f"信号: {sig_text}")
            sig_label.setStyleSheet("""
                background-color: #e3f2fd;
                color: #1565c0;
                padding: 5px 15px;
                border-radius: 15px;
                font-weight: bold;
            """)
            info_layout.addWidget(sig_label)

        layout.addLayout(info_layout)

        # Tab页
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ddd; background: white; }
            QTabBar::tab {
                padding: 10px 25px;
                font-weight: bold;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background-color: #1976d2;
                color: white;
            }
        """)

        # 1. 分时图
        self.minute_tab = self._create_minute_tab()
        self.tab_widget.addTab(self.minute_tab, "📈 分时图")

        # 2. 日线图
        self.daily_tab = self._create_daily_tab()
        self.tab_widget.addTab(self.daily_tab, "📊 日线图")

        layout.addWidget(self.tab_widget)

    def _create_minute_tab(self):
        """创建分时图Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # 分时图画布
        self.minute_chart = MinuteChartWidget()
        self.minute_chart.setMinimumHeight(500)

        # 加载分时数据
        minute_data = self._load_minute_data()
        self.minute_chart.set_data(minute_data)

        layout.addWidget(self.minute_chart)

        # 盘口信息
        order_layout = QHBoxLayout()

        # 买盘
        buy_group = QFrame()
        buy_group.setStyleSheet("background-color: #f1f8e9; border-radius: 5px; padding: 10px;")
        buy_layout = QVBoxLayout(buy_group)
        buy_title = QLabel("买盘")
        buy_title.setStyleSheet("font-weight: bold; color: #388e3c;")
        buy_layout.addWidget(buy_title)

        realtime = self.stock_info.get('realtime', {})
        for i in range(1, 6):
            price = realtime.get(f'bid{i}', 0)
            vol = realtime.get(f'bid{i}_vol', 0)
            if price > 0:
                item = QLabel(f"买{i}: {price:.2f}  {vol:.0f}手")
                item.setStyleSheet("color: #388e3c; padding: 2px;")
                buy_layout.addWidget(item)

        order_layout.addWidget(buy_group)

        # 卖盘
        sell_group = QFrame()
        sell_group.setStyleSheet("background-color: #ffebee; border-radius: 5px; padding: 10px;")
        sell_layout = QVBoxLayout(sell_group)
        sell_title = QLabel("卖盘")
        sell_title.setStyleSheet("font-weight: bold; color: #d32f2f;")
        sell_layout.addWidget(sell_title)

        for i in range(1, 6):
            price = realtime.get(f'ask{i}', 0)
            vol = realtime.get(f'ask{i}_vol', 0)
            if price > 0:
                item = QLabel(f"卖{i}: {price:.2f}  {vol:.0f}手")
                item.setStyleSheet("color: #d32f2f; padding: 2px;")
                sell_layout.addWidget(item)

        order_layout.addWidget(sell_group)

        layout.addLayout(order_layout)

        return widget

    def _create_daily_tab(self):
        """创建日线图Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # 日线图画布
        self.daily_chart = DailyChartWidget()
        self.daily_chart.setMinimumHeight(600)

        # 加载日线数据
        daily_data = self.stock_info.get('daily_data', [])
        self.daily_chart.set_data(daily_data)

        layout.addWidget(self.daily_chart)

        return widget

    def _load_minute_data(self):
        """加载分时数据"""
        # 从行情提供者获取分时数据
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
        # 刷新分时图
        minute_data = self._load_minute_data()
        if minute_data:
            self.minute_chart.set_data(minute_data)
            self.minute_chart.update()

    def closeEvent(self, event):
        """关闭事件"""
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        event.accept()


class MinuteChartWidget(QWidget):
    """分时图画布"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumSize(800, 400)
        self.setStyleSheet("background-color: white;")

    def set_data(self, data):
        """设置分时数据"""
        self.data = data
        self.update()

    def paintEvent(self, event):
        """绘制分时图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor('#ffffff'))

        if not self.data:
            painter.setPen(QColor('#999'))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "暂无分时数据")
            return

        # 计算价格范围
        prices = [d.get('price', 0) for d in self.data if d.get('price', 0) > 0]
        if not prices:
            return

        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = max_price * 0.02

        # 留边距
        margin_left = 60
        margin_right = 20
        margin_top = 30
        margin_bottom = 50

        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        # 昨收(用第一个价格作为参考)
        prev_close = prices[0] if prices else 0

        # 绘制网格
        painter.setPen(QPen(QColor('#e0e0e0'), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))

            # 价格标签
            price = max_price - price_range * i / 4
            painter.setPen(QColor('#666'))
            painter.drawText(5, int(y) + 5, f"{price:.2f}")
            painter.setPen(QPen(QColor('#e0e0e0'), 1))

        # 绘制均价线和价格线
        if len(self.data) > 1:
            # 价格线
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

            # 绘制价格线(白色填充)
            painter.setPen(QPen(QColor('#d32f2f'), 1.5))
            painter.drawPath(path)

            # 绘制均价线(黄色)
            if not avg_path.isEmpty():
                painter.setPen(QPen(QColor('#ff9800'), 1))
                painter.drawPath(avg_path)

            # 绘制成交量柱状图(底部)
            vol_h = 40
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

                # 颜色: 涨红跌绿
                price = d.get('price', 0)
                if i > 0 and self.data[i-1].get('price', 0) > 0:
                    if price >= self.data[i-1].get('price', 0):
                        painter.fillRect(int(x - 1), int(vol_top + vol_h - bar_h), 2, int(bar_h), QColor('#d32f2f'))
                    else:
                        painter.fillRect(int(x - 1), int(vol_top + vol_h - bar_h), 2, int(bar_h), QColor('#388e3c'))

        # 昨收线
        if prev_close > 0:
            y = margin_top + chart_h * (max_price - prev_close) / price_range
            painter.setPen(QPen(QColor('#999'), 1, Qt.PenStyle.DashLine))
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))

        # 标题
        painter.setPen(QColor('#333'))
        painter.setFont(QFont('Microsoft YaHei', 10, QFont.Weight.Bold))
        painter.drawText(margin_left, 20, "分时走势")


class DailyChartWidget(QWidget):
    """日线图画布 - K线 + 成交量 + MA5/MA9/MA20 + KDJ + MACD"""

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
        self.setMinimumSize(900, 600)
        self.setStyleSheet("background-color: white;")

    def set_data(self, data):
        """设置日线数据并计算指标"""
        self.data = data

        if not data or len(data) < 30:
            return

        # 提取数据
        close_prices = [d['close'] for d in data]
        high_prices = [d['high'] for d in data]
        low_prices = [d['low'] for d in data]

        # 计算均线
        self.ma5_series = calc_ma_series(close_prices, 5)
        self.ma9_series = calc_ma_series(close_prices, 9)
        self.ma20_series = calc_ma_series(close_prices, 20)

        # 计算KDJ
        self.k_series, self.d_series, self.j_series = calc_kdj_series(
            high_prices, low_prices, close_prices
        )

        # 计算MACD
        self.dif_series, self.dea_series, self.macd_hist = calc_macd_series(close_prices)

        self.update()

    def paintEvent(self, event):
        """绘制日线图"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor('#ffffff'))

        if not self.data or len(self.data) < 30:
            painter.setPen(QColor('#999'))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "数据不足，无法绘制K线")
            return

        # 只显示最近60根K线
        show_count = min(60, len(self.data))
        data = self.data[-show_count:]

        # 布局: K线区(50%) + 成交量(15%) + KDJ(15%) + MACD(20%)
        margin_left = 60
        margin_right = 20
        margin_top = 25

        total_h = h - margin_top - 20
        kline_h = int(total_h * 0.45)
        vol_h = int(total_h * 0.15)
        kdj_h = int(total_h * 0.18)
        macd_h = int(total_h * 0.22)

        kline_top = margin_top
        vol_top = kline_top + kline_h + 10
        kdj_top = vol_top + vol_h + 10
        macd_top = kdj_top + kdj_h + 10

        chart_w = w - margin_left - margin_right

        # 计算价格范围
        high_prices = [d['high'] for d in data]
        low_prices = [d['low'] for d in data]
        max_price = max(high_prices)
        min_price = min(low_prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = max_price * 0.02

        # ========== 1. 绘制K线 ==========
        self._draw_kline(painter, data, margin_left, kline_top, chart_w, kline_h,
                         max_price, min_price, price_range)

        # 绘制均线
        self._draw_ma_lines(painter, data, margin_left, kline_top, chart_w, kline_h,
                           max_price, min_price, price_range)

        # ========== 2. 绘制成交量 ==========
        self._draw_volume(painter, data, margin_left, vol_top, chart_w, vol_h)

        # ========== 3. 绘制KDJ ==========
        self._draw_kdj(painter, data, margin_left, kdj_top, chart_w, kdj_h)

        # ========== 4. 绘制MACD ==========
        self._draw_macd(painter, data, margin_left, macd_top, chart_w, macd_h)

        # ========== 图例 ==========
        self._draw_legend(painter, margin_left, 5)

    def _draw_kline(self, painter, data, x, y, w, h, max_p, min_p, p_range):
        """绘制K线"""
        painter.save()

        # 网格
        painter.setPen(QPen(QColor('#e0e0e0'), 1))
        for i in range(5):
            gy = y + h * i / 4
            painter.drawLine(x, int(gy), x + w, int(gy))

            # 价格标签
            price = max_p - p_range * i / 4
            painter.setPen(QColor('#666'))
            painter.drawText(5, int(gy) + 5, f"{price:.2f}")
            painter.setPen(QPen(QColor('#e0e0e0'), 1))

        # K线
        candle_w = max(3, w / len(data) * 0.7)

        for i, d in enumerate(data):
            cx = x + w * (i + 0.5) / len(data)
            open_p = d['open']
            close_p = d['close']
            high_p = d['high']
            low_p = d['low']

            # 计算Y坐标
            def price_to_y(price):
                return y + h * (max_p - price) / p_range

            high_y = price_to_y(high_p)
            low_y = price_to_y(low_p)
            open_y = price_to_y(open_p)
            close_y = price_to_y(close_p)

            # 颜色: 涨红跌绿
            if close_p >= open_p:
                color = QColor('#d32f2f')
            else:
                color = QColor('#388e3c')

            painter.setPen(QPen(color, 1))

            # 影线
            painter.drawLine(int(cx), int(high_y), int(cx), int(low_y))

            # 实体
            body_top = min(open_y, close_y)
            body_h = abs(close_y - open_y)
            if body_h < 1:
                body_h = 1

            painter.setBrush(color)
            painter.drawRect(int(cx - candle_w/2), int(body_top), int(candle_w), int(body_h))

        painter.restore()

    def _draw_ma_lines(self, painter, data, x, y, w, h, max_p, min_p, p_range):
        """绘制均线"""
        if self.ma5_series is None:
            return

        n = len(data)
        start_idx = len(self.data) - n

        def price_to_y(price):
            return y + h * (max_p - price) / p_range

        # MA5 (黄色)
        if self.ma5_series is not None and len(self.ma5_series) > start_idx:
            painter.setPen(QPen(QColor('#ffeb3b'), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(self.ma5_series):
                    break
                ma_val = self.ma5_series.iloc[idx]
                if ma_val is None or (hasattr(ma_val, 'isnan') and ma_val.isnan()):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = price_to_y(ma_val)
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

        # MA9 (紫色)
        if self.ma9_series is not None and len(self.ma9_series) > start_idx:
            painter.setPen(QPen(QColor('#9c27b0'), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(self.ma9_series):
                    break
                ma_val = self.ma9_series.iloc[idx]
                if ma_val is None or (hasattr(ma_val, 'isnan') and ma_val.isnan()):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = price_to_y(ma_val)
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

        # MA20 (蓝色)
        if self.ma20_series is not None and len(self.ma20_series) > start_idx:
            painter.setPen(QPen(QColor('#2196f3'), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(self.ma20_series):
                    break
                ma_val = self.ma20_series.iloc[idx]
                if ma_val is None or (hasattr(ma_val, 'isnan') and ma_val.isnan()):
                    continue
                cx = x + w * (i + 0.5) / n
                cy = price_to_y(ma_val)
                if not started:
                    path.moveTo(cx, cy)
                    started = True
                else:
                    path.lineTo(cx, cy)
            if started:
                painter.drawPath(path)

    def _draw_volume(self, painter, data, x, y, w, h):
        """绘制成交量"""
        painter.save()

        # 标题
        painter.setPen(QColor('#333'))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "成交量")

        # 网格线
        painter.setPen(QPen(QColor('#e0e0e0'), 1))
        painter.drawLine(x, y, x + w, y)
        painter.drawLine(x, y + h, x + w, y + h)

        # 最大成交量
        volumes = [d.get('volume', d.get('vol', 0)) for d in data]
        max_vol = max(volumes) if volumes else 1
        if max_vol == 0:
            max_vol = 1

        # 柱状图
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
                color = QColor('#d32f2f')
            else:
                color = QColor('#388e3c')

            painter.fillRect(int(cx - bar_w/2), int(y + h - bar_h), int(bar_w), int(bar_h), color)

        painter.restore()

    def _draw_kdj(self, painter, data, x, y, w, h):
        """绘制KDJ指标"""
        painter.save()

        # 标题
        painter.setPen(QColor('#333'))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "KDJ(13,3,3)")

        # 网格
        painter.setPen(QPen(QColor('#e0e0e0'), 1))
        painter.drawLine(x, y, x + w, y)
        painter.drawLine(x, y + h, x + w, y + h)

        # 超买超卖线(20, 80)
        painter.setPen(QPen(QColor('#ccc'), 1, Qt.PenStyle.DashLine))
        painter.drawLine(x, int(y + h * 0.2), x + w, int(y + h * 0.2))
        painter.drawLine(x, int(y + h * 0.8), x + w, int(y + h * 0.8))

        if self.k_series is None:
            painter.restore()
            return

        n = len(data)
        start_idx = len(self.data) - n

        # KDJ范围: -20 到 120
        kdj_min = -20
        kdj_max = 120
        kdj_range = kdj_max - kdj_min

        def kdj_to_y(val):
            return y + h * (kdj_max - val) / kdj_range

        # K线(白色)
        painter.setPen(QPen(QColor('#ffffff'), 1.5))
        path = QPainterPath()
        started = False
        for i in range(n):
            idx = start_idx + i
            if idx >= len(self.k_series):
                break
            val = self.k_series.iloc[idx]
            if val is None or (hasattr(val, 'isnan') and val.isnan()):
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

        # D线(黄色)
        painter.setPen(QPen(QColor('#ffeb3b'), 1.5))
        path = QPainterPath()
        started = False
        for i in range(n):
            idx = start_idx + i
            if idx >= len(self.d_series):
                break
            val = self.d_series.iloc[idx]
            if val is None or (hasattr(val, 'isnan') and val.isnan()):
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

        # J线(紫色)
        painter.setPen(QPen(QColor('#9c27b0'), 1.5))
        path = QPainterPath()
        started = False
        for i in range(n):
            idx = start_idx + i
            if idx >= len(self.j_series):
                break
            val = self.j_series.iloc[idx]
            if val is None or (hasattr(val, 'isnan') and val.isnan()):
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
        """绘制MACD指标"""
        painter.save()

        # 标题
        painter.setPen(QColor('#333'))
        painter.setFont(QFont('Microsoft YaHei', 9))
        painter.drawText(x, y - 5, "MACD(8,21,5)")

        # 零线
        painter.setPen(QPen(QColor('#999'), 1, Qt.PenStyle.DashLine))
        zero_y = y + h / 2
        painter.drawLine(x, int(zero_y), x + w, int(zero_y))

        if self.macd_hist is None:
            painter.restore()
            return

        n = len(data)
        start_idx = len(self.data) - n

        # 计算MACD范围
        hist_values = []
        for i in range(n):
            idx = start_idx + i
            if idx < len(self.macd_hist):
                val = self.macd_hist.iloc[idx]
                if val is not None and not (hasattr(val, 'isnan') and val.isnan()):
                    hist_values.append(abs(val))

        if not hist_values:
            painter.restore()
            return

        max_hist = max(hist_values) * 1.2
        if max_hist == 0:
            max_hist = 1

        # 柱状图
        bar_w = max(2, w / len(data) * 0.7)

        for i in range(n):
            idx = start_idx + i
            if idx >= len(self.macd_hist):
                continue
            hist_val = self.macd_hist.iloc[idx]
            if hist_val is None or (hasattr(hist_val, 'isnan') and hist_val.isnan()):
                continue

            cx = x + w * (i + 0.5) / n
            bar_h = h / 2 * abs(hist_val) / max_hist

            if hist_val >= 0:
                color = QColor('#d32f2f')
                bar_y = zero_y - bar_h
            else:
                color = QColor('#388e3c')
                bar_y = zero_y

            painter.fillRect(int(cx - bar_w/2), int(bar_y), int(bar_w), int(bar_h), color)

        # DIF线(白色)
        if self.dif_series is not None:
            painter.setPen(QPen(QColor('#ffffff'), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(self.dif_series):
                    break
                val = self.dif_series.iloc[idx]
                if val is None or (hasattr(val, 'isnan') and val.isnan()):
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

        # DEA线(黄色)
        if self.dea_series is not None:
            painter.setPen(QPen(QColor('#ffeb3b'), 1.5))
            path = QPainterPath()
            started = False
            for i in range(n):
                idx = start_idx + i
                if idx >= len(self.dea_series):
                    break
                val = self.dea_series.iloc[idx]
                if val is None or (hasattr(val, 'isnan') and val.isnan()):
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

    def _draw_legend(self, painter, x, y):
        """绘制图例"""
        painter.save()
        painter.setFont(QFont('Microsoft YaHei', 9))

        legends = [
            ('MA5', QColor('#ffeb3b')),
            ('MA9', QColor('#9c27b0')),
            ('MA20', QColor('#2196f3')),
            ('K', QColor('#ffffff')),
            ('D', QColor('#ffeb3b')),
            ('J', QColor('#9c27b0')),
            ('DIF', QColor('#ffffff')),
            ('DEA', QColor('#ffeb3b')),
        ]

        cx = x
        for name, color in legends:
            painter.setPen(color)
            painter.drawText(cx, y + 12, f"━ {name}")
            cx += 60

        painter.restore()
