"""
股票详情对话框 - 同花顺风格
显示K线图、成交量、MACD、KDJ
可直接从股票列表双击打开
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QWidget, QPushButton
)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath
import requests
import numpy as np
from datetime import datetime


class KLineChart(QWidget):
    """K线图组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.daily_data = []
        self.ma5 = []
        self.ma10 = []
        self.ma20 = []

    def set_data(self, daily_data):
        """设置K线数据"""
        self.daily_data = daily_data
        # 计算均线
        closes = [d['close'] for d in daily_data]
        self.ma5 = self._calc_ma(closes, 5)
        self.ma10 = self._calc_ma(closes, 10)
        self.ma20 = self._calc_ma(closes, 20)
        self.update()

    def _calc_ma(self, data, period):
        """计算均线"""
        result = []
        for i in range(len(data)):
            if i >= period - 1:
                result.append(np.mean(data[i-period+1:i+1]))
            else:
                result.append(None)
        return result

    def paintEvent(self, event):
        """绘制K线图"""
        if not self.daily_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        padding_left = 50
        padding_right = 20
        padding_top = 20
        padding_bottom = 30

        chart_w = w - padding_left - padding_right
        chart_h = h - padding_top - padding_bottom

        # 显示最近60根K线
        data = self.daily_data[-60:]
        n = len(data)
        if n == 0:
            return

        candle_w = chart_w / n * 0.7
        gap = chart_w / n

        # 计算价格范围
        highs = [d['high'] for d in data]
        lows = [d['low'] for d in data]
        max_price = max(highs)
        min_price = min(lows)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = 1

        def price_to_y(price):
            return padding_top + chart_h - (price - min_price) / price_range * chart_h

        # 绘制背景网格
        painter.setPen(QPen(QColor('#30363d'), 1))
        for i in range(5):
            y = padding_top + chart_h * i / 4
            painter.drawLine(padding_left, int(y), w - padding_right, int(y))
            price = max_price - price_range * i / 4
            painter.setPen(QColor('#8b949e'))
            painter.drawText(5, int(y) + 4, f"{price:.2f}")
            painter.setPen(QPen(QColor('#30363d'), 1))

        # 绘制K线
        for i, d in enumerate(data):
            x = padding_left + i * gap + gap / 2
            open_p = d['open']
            close_p = d['close']
            high_p = d['high']
            low_p = d['low']

            is_up = close_p >= open_p
            color = QColor('#f85149') if is_up else QColor('#3fb950')

            # 影线
            painter.setPen(QPen(color, 1))
            painter.drawLine(int(x), int(price_to_y(high_p)), int(x), int(price_to_y(low_p)))

            # 实体
            body_top = price_to_y(max(open_p, close_p))
            body_bottom = price_to_y(min(open_p, close_p))
            body_h = max(1, body_bottom - body_top)

            if is_up:
                painter.setBrush(color)
                painter.drawRect(int(x - candle_w/2), int(body_top), int(candle_w), int(body_h))
            else:
                painter.setBrush(color)
                painter.drawRect(int(x - candle_w/2), int(body_top), int(candle_w), int(body_h))

        # 绘制均线
        ma_colors = {
            'ma5': QColor('#e3b341'),
            'ma10': QColor('#58a6ff'),
            'ma20': QColor('#bc8cff'),
        }

        for ma_name, ma_data in [('ma5', self.ma5), ('ma10', self.ma10), ('ma20', self.ma20)]:
            ma_data_slice = ma_data[-60:]
            points = []
            for i, val in enumerate(ma_data_slice):
                if val is not None:
                    x = padding_left + i * gap + gap / 2
                    y = price_to_y(val)
                    points.append(QPointF(x, y))

            if len(points) > 1:
                painter.setPen(QPen(ma_colors[ma_name], 1.5))
                path = QPainterPath()
                path.moveTo(points[0])
                for p in points[1:]:
                    path.lineTo(p)
                painter.drawPath(path)

        # 图例
        painter.setPen(QColor('#e3b341'))
        painter.drawText(padding_left + 5, 15, 'MA5')
        painter.setPen(QColor('#58a6ff'))
        painter.drawText(padding_left + 50, 15, 'MA10')
        painter.setPen(QColor('#bc8cff'))
        painter.drawText(padding_left + 100, 15, 'MA20')

        painter.end()


class VolumeChart(QWidget):
    """成交量图组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.daily_data = []

    def set_data(self, daily_data):
        """设置数据"""
        self.daily_data = daily_data
        self.update()

    def paintEvent(self, event):
        """绘制成交量"""
        if not self.daily_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        padding_left = 50
        padding_right = 20
        padding_top = 10
        padding_bottom = 20

        chart_w = w - padding_left - padding_right
        chart_h = h - padding_top - padding_bottom

        data = self.daily_data[-60:]
        n = len(data)
        if n == 0:
            return

        bar_w = chart_w / n * 0.7
        gap = chart_w / n

        max_vol = max([d['volume'] for d in data])
        if max_vol == 0:
            max_vol = 1

        for i, d in enumerate(data):
            x = padding_left + i * gap + gap / 2
            vol = d['volume']
            bar_h = vol / max_vol * chart_h

            is_up = d['close'] >= d['open']
            color = QColor('#f85149') if is_up else QColor('#3fb950')

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(x - bar_w/2), int(padding_top + chart_h - bar_h), int(bar_w), int(bar_h))

        # 标题
        painter.setPen(QColor('#8b949e'))
        painter.drawText(5, 15, '成交量')

        painter.end()


class MACDChart(QWidget):
    """MACD图组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.daily_data = []

    def set_data(self, daily_data):
        """设置数据"""
        self.daily_data = daily_data
        self.update()

    def _calc_ema(self, data, period):
        """计算EMA"""
        if not data:
            return []
        multiplier = 2 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema

    def paintEvent(self, event):
        """绘制MACD"""
        if not self.daily_data or len(self.daily_data) < 26:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        padding_left = 50
        padding_right = 20
        padding_top = 10
        padding_bottom = 20

        chart_w = w - padding_left - padding_right
        chart_h = h - padding_top - padding_bottom

        data = self.daily_data[-60:]
        closes = [d['close'] for d in self.daily_data]

        ema12 = self._calc_ema(closes, 12)
        ema26 = self._calc_ema(closes, 26)
        diff = [ema12[i] - ema26[i] for i in range(len(closes))]
        dea = self._calc_ema(diff, 9)
        macd = [(diff[i] - dea[i]) * 2 for i in range(len(closes))]

        diff_slice = diff[-60:]
        dea_slice = dea[-60:]
        macd_slice = macd[-60:]

        n = len(data)
        if n == 0:
            return

        gap = chart_w / n
        bar_w = gap * 0.5

        all_vals = diff_slice + dea_slice + macd_slice
        max_val = max(all_vals)
        min_val = min(all_vals)
        val_range = max(max_val - min_val, 0.001)

        def val_to_y(val):
            return padding_top + chart_h - (val - min_val) / val_range * chart_h

        # 零轴
        zero_y = val_to_y(0)
        painter.setPen(QPen(QColor('#30363d'), 1, Qt.PenStyle.DashLine))
        painter.drawLine(padding_left, int(zero_y), w - padding_right, int(zero_y))

        # MACD柱
        for i, val in enumerate(macd_slice):
            x = padding_left + i * gap + gap / 2
            bar_h = abs(val - 0) / val_range * chart_h
            color = QColor('#f85149') if val >= 0 else QColor('#3fb950')
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            if val >= 0:
                painter.drawRect(int(x - bar_w/2), int(zero_y - bar_h), int(bar_w), int(bar_h))
            else:
                painter.drawRect(int(x - bar_w/2), int(zero_y), int(bar_w), int(bar_h))

        # DIFF线
        painter.setPen(QPen(QColor('#e3b341'), 1.5))
        points = [QPointF(padding_left + i * gap + gap / 2, val_to_y(diff_slice[i])) for i in range(n)]
        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)
        painter.drawPath(path)

        # DEA线
        painter.setPen(QPen(QColor('#58a6ff'), 1.5))
        points = [QPointF(padding_left + i * gap + gap / 2, val_to_y(dea_slice[i])) for i in range(n)]
        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)
        painter.drawPath(path)

        # 图例
        painter.setPen(QColor('#e3b341'))
        painter.drawText(5, 15, 'DIFF')
        painter.setPen(QColor('#58a6ff'))
        painter.drawText(50, 15, 'DEA')
        painter.setPen(QColor('#8b949e'))
        painter.drawText(95, 15, 'MACD')

        painter.end()


class StockDetailDialog(QDialog):
    """股票详情对话框 - 同花顺风格"""

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
    }

    def __init__(self, ts_code, stock_name='', parent=None):
        super().__init__(parent)
        self.ts_code = ts_code
        self.stock_name = stock_name
        self.daily_data = []

        self.setWindowTitle(f"{stock_name} ({ts_code}) - K线详情")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(f"background-color: {self.DARK_COLORS['bg_primary']};")

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部信息栏
        layout.addWidget(self._create_header())

        # K线图区域
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(10, 10, 10, 10)
        chart_layout.setSpacing(5)

        self.kline_chart = KLineChart()
        chart_layout.addWidget(self.kline_chart, 3)

        self.volume_chart = VolumeChart()
        chart_layout.addWidget(self.volume_chart, 1)

        self.macd_chart = MACDChart()
        chart_layout.addWidget(self.macd_chart, 1)

        layout.addWidget(chart_container, 1)

        # 底部信息栏
        layout.addWidget(self._create_footer())

    def _create_header(self):
        """创建顶部信息栏"""
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border-bottom: 1px solid {self.DARK_COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)

        # 股票名称和代码
        name_layout = QVBoxLayout()
        name_label = QLabel(f"{self.stock_name}")
        name_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #f0f6fc;")
        code_label = QLabel(f"{self.ts_code}")
        code_label.setStyleSheet(f"font-size: 12px; color: {self.DARK_COLORS['text_secondary']};")
        name_layout.addWidget(name_label)
        name_layout.addWidget(code_label)
        layout.addLayout(name_layout)

        layout.addSpacing(30)

        # 价格信息（占位，加载后更新）
        self.price_label = QLabel("--")
        self.price_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #f85149;")
        layout.addWidget(self.price_label)

        self.pct_label = QLabel("--")
        self.pct_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #f85149;")
        layout.addWidget(self.pct_label)

        layout.addStretch()

        # 周期切换
        for period in ['日K', '周K', '月K']:
            btn = QPushButton(period)
            btn.setFixedSize(50, 28)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.DARK_COLORS['bg_tertiary']};
                    color: {self.DARK_COLORS['text_secondary']};
                    border: 1px solid {self.DARK_COLORS['border']};
                    border-radius: 4px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    color: {self.DARK_COLORS['accent']};
                    border-color: {self.DARK_COLORS['accent']};
                }}
            """)
            layout.addWidget(btn)

        return header

    def _create_footer(self):
        """创建底部信息栏"""
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border-top: 1px solid {self.DARK_COLORS['border']};
            }}
        """)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 5, 20, 5)

        self.info_label = QLabel("加载中...")
        self.info_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.info_label)

        layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(60, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.DARK_COLORS['accent']};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return footer

    def _load_data(self):
        """加载股票数据"""
        try:
            # 使用腾讯API获取实时价格
            if self.ts_code.startswith('6'):
                market = 'sh'
            else:
                market = 'sz'

            url = f'https://qt.gtimg.cn/q={market}{self.ts_code}'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')

            if len(parts) > 32:
                name = parts[1]
                price = float(parts[3])
                pct = float(parts[32])

                if not self.stock_name:
                    self.stock_name = name
                    self.setWindowTitle(f"{name} ({self.ts_code}) - K线详情")

                color = '#f85149' if pct >= 0 else '#3fb950'
                self.price_label.setText(f"{price:.2f}")
                self.price_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {color};")
                self.pct_label.setText(f"{pct:+.2f}%")
                self.pct_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")

            # 获取K线数据（使用pytdx）
            self._load_kline_data()

        except Exception as e:
            self.info_label.setText(f"数据加载失败: {str(e)[:30]}")

    def _load_kline_data(self):
        """加载K线数据"""
        try:
            from pytdx.hq import TdxHq_API

            api = TdxHq_API()
            if api.connect('119.147.212.81', 7709):
                # 0=深圳, 1=上海
                market = 1 if self.ts_code.startswith('6') else 0
                data = api.get_security_bars(9, market, self.ts_code, 0, 80)  # 9=日K
                api.disconnect()

                if data:
                    self.daily_data = []
                    for item in data:
                        self.daily_data.append({
                            'open': item.get('open', 0),
                            'close': item.get('close', 0),
                            'high': item.get('high', 0),
                            'low': item.get('low', 0),
                            'volume': item.get('vol', 0),
                        })

                    # 更新图表
                    self.kline_chart.set_data(self.daily_data)
                    self.volume_chart.set_data(self.daily_data)
                    self.macd_chart.set_data(self.daily_data)

                    # 更新底部信息
                    if self.daily_data:
                        last = self.daily_data[-1]
                        self.info_label.setText(
                            f"开:{last['open']:.2f} 高:{last['high']:.2f} "
                            f"低:{last['low']:.2f} 收:{last['close']:.2f} "
                            f"量:{last['volume']:.0f} | 共{len(self.daily_data)}根K线"
                        )

        except Exception as e:
            self.info_label.setText(f"K线数据加载失败: {str(e)[:30]}，请确保已安装pytdx")
