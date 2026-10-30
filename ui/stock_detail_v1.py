# -*- coding: utf-8 -*-
"""
股票详情页
K线图 + 技术指标 + AI分析
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
import pandas as pd
import numpy as np

from utils.indicators import calc_ma_series, calc_kdj_series, calc_macd_series
from ui.kline_container import KlineContainer


class KlineChartWidget(QWidget):
    """简易K线图组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kline_data = None
        self.setMinimumHeight(300)
        self.setStyleSheet('background: #0d1117;')

    def set_kline(self, kline_data):
        self.kline_data = kline_data
        self.update()

    def paintEvent(self, event):
        if not self.kline_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        padding = 40

        closes = self.kline_data.get('close', [])
        highs = self.kline_data.get('high', [])
        lows = self.kline_data.get('low', [])
        opens = self.kline_data.get('open', [])

        if len(closes) < 5:
            return

        # 只显示最近60根K线
        show_count = min(60, len(closes))
        closes = closes[-show_count:]
        highs = highs[-show_count:]
        lows = lows[-show_count:]
        opens = opens[-show_count:]

        # 计算价格范围
        all_prices = highs + lows
        max_price = max(all_prices)
        min_price = min(all_prices)
        price_range = max_price - min_price if max_price > min_price else 1

        # 计算均线
        ma5 = calc_ma_series(self.kline_data['close'], 5).iloc[-show_count:].tolist()
        ma10 = calc_ma_series(self.kline_data['close'], 10).iloc[-show_count:].tolist()
        ma20 = calc_ma_series(self.kline_data['close'], 20).iloc[-show_count:].tolist()

        # K线宽度
        candle_w = (w - padding * 2) / show_count * 0.7
        gap = (w - padding * 2) / show_count

        def price_to_y(price):
            return padding + (max_price - price) / price_range * (h - padding * 2)

        # 绘制网格
        painter.setPen(QPen(QColor('#21262d'), 1))
        for i in range(5):
            y = padding + i * (h - padding * 2) / 4
            painter.drawLine(padding, int(y), w - padding, int(y))
            price = max_price - i * price_range / 4
            painter.setPen(QColor('#8b949e'))
            painter.drawText(2, int(y) + 4, f'{price:.2f}')
            painter.setPen(QPen(QColor('#21262d'), 1))

        # 绘制K线
        for i in range(show_count):
            x = padding + i * gap + gap * 0.15
            o = opens[i]
            c = closes[i]
            h_val = highs[i]
            l_val = lows[i]

            is_up = c >= o
            color = QColor('#f85149') if is_up else QColor('#3fb950')

            # 影线
            painter.setPen(QPen(color, 1))
            painter.drawLine(int(x + candle_w / 2), int(price_to_y(h_val)),
                           int(x + candle_w / 2), int(price_to_y(l_val)))

            # 实体
            painter.setBrush(QBrush(color))
            body_top = price_to_y(max(o, c))
            body_bottom = price_to_y(min(o, c))
            body_h = max(1, body_bottom - body_top)
            painter.drawRect(int(x), int(body_top), int(candle_w), int(body_h))

        # 绘制均线
        def draw_ma(ma_list, color_str):
            painter.setPen(QPen(QColor(color_str), 1.5))
            points = []
            for i, val in enumerate(ma_list):
                if pd.isna(val):
                    if points:
                        painter.drawPolyline(points)
                        points = []
                    continue
                x = padding + i * gap + gap / 2
                y = price_to_y(val)
                points.append((int(x), int(y)))
            if points:
                painter.drawPolyline(points)

        draw_ma(ma5, '#ffea00')   # MA5 黄色
        draw_ma(ma10, '#58a6ff')  # MA10 蓝色
        draw_ma(ma20, '#d500f9')  # MA20 紫色

        # 图例
        painter.setPen(QColor('#ffea00'))
        painter.drawText(padding + 10, 15, 'MA5')
        painter.setPen(QColor('#58a6ff'))
        painter.drawText(padding + 60, 15, 'MA10')
        painter.setPen(QColor('#d500f9'))
        painter.drawText(padding + 120, 15, 'MA20')

        painter.end()


class IndicatorWidget(QWidget):
    """指标显示组件（MACD/KDJ）"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.data = None
        self.setMinimumHeight(100)
        self.setStyleSheet('background: #0d1117;')

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        if not self.data:
            return

        painter = QPainter(self)
        w = self.width()
        h = self.height()
        padding = 25

        values = self.data[-60:] if len(self.data) > 60 else self.data
        valid_values = [v for v in values if not pd.isna(v)]
        if not valid_values:
            return

        max_val = max(valid_values)
        min_val = min(valid_values)
        val_range = max_val - min_val if max_val > min_val else 1

        bar_w = (w - padding * 2) / len(values) * 0.7
        gap = (w - padding * 2) / len(values)

        zero_y = padding + (max_val) / val_range * (h - padding * 2)

        for i, val in enumerate(values):
            if pd.isna(val):
                continue
            x = padding + i * gap + gap * 0.15
            y = padding + (max_val - val) / val_range * (h - padding * 2)

            color = QColor('#f85149') if val >= 0 else QColor('#3fb950')
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)

            if val >= 0:
                painter.drawRect(int(x), int(y), int(bar_w), int(zero_y - y))
            else:
                painter.drawRect(int(x), int(zero_y), int(bar_w), int(y - zero_y))

        # 标题
        painter.setPen(QColor('#8b949e'))
        painter.drawText(5, 15, self.title)

        painter.end()


class MacdWidget(QWidget):
    """MACD指标显示组件（DIF线 + DEA线 + MACD柱）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dif_data = None
        self.dea_data = None
        self.macd_data = None
        self.cursor_index = -1  # 当前光标位置（-1表示不显示）
        self.setMinimumHeight(120)
        self.setStyleSheet('background: #0d1117;')
    
    def set_cursor_index(self, index):
        """设置光标位置（用于与K线联动）"""
        self.cursor_index = index
        self.update()
    
    def set_macd(self, dif, dea, macd):
        """设置MACD数据"""
        self.dif_data = dif.tolist() if hasattr(dif, 'tolist') else dif
        self.dea_data = dea.tolist() if hasattr(dea, 'tolist') else dea
        self.macd_data = macd.tolist() if hasattr(macd, 'tolist') else macd
        self.cursor_index = -1
        self.update()
    
    def paintEvent(self, event):
        if not self.dif_data or not self.dea_data or not self.macd_data:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        padding = 25
        
        # 填充深色背景
        painter.fillRect(0, 0, w, h, QColor('#0d1117'))
        
        # 只显示最近60根
        show_count = min(60, len(self.dif_data))
        dif_vals = self.dif_data[-show_count:]
        dea_vals = self.dea_data[-show_count:]
        macd_vals = self.macd_data[-show_count:]
        
        # 过滤NaN
        all_vals = []
        for v in dif_vals + dea_vals + macd_vals:
            if not pd.isna(v):
                all_vals.append(v)
        
        if not all_vals:
            return
        
        max_val = max(all_vals)
        min_val = min(all_vals)
        # 确保零轴在范围内
        if max_val < 0:
            max_val = 0
        if min_val > 0:
            min_val = 0
        val_range = max_val - min_val if max_val > min_val else 1
        
        gap = (w - padding * 2) / show_count
        bar_w = gap * 0.7
        
        # 零轴位置
        zero_y = padding + (max_val - 0) / val_range * (h - padding * 2)
        
        # 画零轴
        painter.setPen(QPen(QColor('#6e7681'), 1, Qt.PenStyle.DashLine))
        painter.drawLine(padding, int(zero_y), w - padding, int(zero_y))
        
        # 画MACD柱状图
        for i, val in enumerate(macd_vals):
            if pd.isna(val):
                continue
            x = padding + i * gap + gap * 0.15
            y = padding + (max_val - val) / val_range * (h - padding * 2)
            
            color = QColor('#f85149') if val >= 0 else QColor('#3fb950')
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            
            if val >= 0:
                painter.drawRect(int(x), int(y), int(bar_w), int(zero_y - y))
            else:
                painter.drawRect(int(x), int(zero_y), int(bar_w), int(y - zero_y))
        
        # 画DIF线（白色）
        painter.setPen(QPen(QColor('#f0f6fc'), 1.5))
        self._draw_line(painter, dif_vals, padding, gap, max_val, min_val, val_range, h)
        
        # 画DEA线（黄色）
        painter.setPen(QPen(QColor('#ffeb3b'), 1.5))
        self._draw_line(painter, dea_vals, padding, gap, max_val, min_val, val_range, h)
        
        # 标题和图例
        painter.setPen(QColor('#8b949e'))
        painter.drawText(5, 15, 'MACD(8,21,5)')
        
        painter.setPen(QColor('#f0f6fc'))
        painter.drawText(75, 15, 'DIF')
        painter.setPen(QColor('#ffeb3b'))
        painter.drawText(100, 15, 'DEA')
        
        # 画光标垂直线（与K线联动）
        if self.cursor_index >= 0:
            # 转换为显示范围内的索引
            display_index = self.cursor_index - (len(self.dif_data) - show_count)
            if 0 <= display_index < show_count:
                cursor_x = padding + display_index * gap + gap / 2
                painter.setPen(QPen(QColor('#58a6ff'), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(cursor_x), padding, int(cursor_x), h - padding)
        
        painter.end()
    
    def _draw_line(self, painter, values, padding, gap, max_val, min_val, val_range, h):
        """画一条线"""
        points = []
        for i, val in enumerate(values):
            if pd.isna(val):
                continue
            x = padding + i * gap + gap / 2
            y = padding + (max_val - val) / val_range * (h - padding * 2)
            points.append((x, y))
        
        if len(points) < 2:
            return
        
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))


class KdjWidget(QWidget):
    """KDJ指标显示组件（K、D、J三线）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.k_data = None
        self.d_data = None
        self.j_data = None
        self.cursor_index = -1  # 当前光标位置
        self.setMinimumHeight(120)
        self.setStyleSheet('background: #0d1117;')
    
    def set_cursor_index(self, index):
        """设置光标位置（用于与K线联动）"""
        self.cursor_index = index
        self.update()
    
    def set_kdj(self, k, d, j):
        """设置KDJ数据"""
        self.k_data = k.tolist() if hasattr(k, 'tolist') else k
        self.d_data = d.tolist() if hasattr(d, 'tolist') else d
        self.j_data = j.tolist() if hasattr(j, 'tolist') else j
        self.cursor_index = -1
        self.update()
    
    def paintEvent(self, event):
        if not self.k_data or not self.d_data or not self.j_data:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        padding = 25
        
        # 填充深色背景
        painter.fillRect(0, 0, w, h, QColor('#0d1117'))
        
        # 只显示最近60根
        show_count = min(60, len(self.k_data))
        k_vals = self.k_data[-show_count:]
        d_vals = self.d_data[-show_count:]
        j_vals = self.j_data[-show_count:]
        
        # 过滤NaN
        all_vals = []
        for v in k_vals + d_vals + j_vals:
            if not pd.isna(v):
                all_vals.append(v)
        
        if not all_vals:
            return
        
        max_val = max(max(all_vals), 100)
        min_val = min(min(all_vals), 0)
        val_range = max_val - min_val if max_val > min_val else 1
        
        gap = (w - padding * 2) / show_count
        
        # 画超买超卖线（80、20）
        painter.setPen(QPen(QColor('#6e7681'), 1, Qt.PenStyle.DashLine))
        y_80 = padding + (max_val - 80) / val_range * (h - padding * 2)
        y_20 = padding + (max_val - 20) / val_range * (h - padding * 2)
        painter.drawLine(padding, int(y_80), w - padding, int(y_80))
        painter.drawLine(padding, int(y_20), w - padding, int(y_20))
        
        # 标注80和20
        painter.setPen(QColor('#6e7681'))
        painter.drawText(w - padding - 20, int(y_80) - 2, '80')
        painter.drawText(w - padding - 20, int(y_20) + 10, '20')
        
        # 画K线（白色）
        painter.setPen(QPen(QColor('#f0f6fc'), 1.5))
        self._draw_line(painter, k_vals, padding, gap, max_val, min_val, val_range, h)
        
        # 画D线（黄色）
        painter.setPen(QPen(QColor('#ffeb3b'), 1.5))
        self._draw_line(painter, d_vals, padding, gap, max_val, min_val, val_range, h)
        
        # 画J线（紫色）
        painter.setPen(QPen(QColor('#ab47bc'), 1.5))
        self._draw_line(painter, j_vals, padding, gap, max_val, min_val, val_range, h)
        
        # 标题和数值
        painter.setPen(QColor('#8b949e'))
        painter.drawText(5, 15, 'KDJ(13,3,3)')
        
        # 图例
        painter.setPen(QColor('#f0f6fc'))
        painter.drawText(60, 15, 'K')
        painter.setPen(QColor('#ffeb3b'))
        painter.drawText(75, 15, 'D')
        painter.setPen(QColor('#ab47bc'))
        painter.drawText(90, 15, 'J')
        
        # 画光标垂直线（与K线联动）
        if self.cursor_index >= 0:
            display_index = self.cursor_index - (len(self.k_data) - show_count)
            if 0 <= display_index < show_count:
                cursor_x = padding + display_index * gap + gap / 2
                painter.setPen(QPen(QColor('#58a6ff'), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(cursor_x), padding, int(cursor_x), h - padding)
        
        painter.end()
    
    def _draw_line(self, painter, values, padding, gap, max_val, min_val, val_range, h):
        """画一条线"""
        points = []
        for i, val in enumerate(values):
            if pd.isna(val):
                continue
            x = padding + i * gap + gap / 2
            y = padding + (max_val - val) / val_range * (h - padding * 2)
            points.append((x, y))
        
        if len(points) < 2:
            return
        
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))


class StockDetailWidget(QWidget):
    """股票详情页"""

    back_clicked = pyqtSignal()
    kline_data_ready = pyqtSignal(object, str, str)  # K线数据加载完成信号 (kline_data, code, name)
    time_share_ready = pyqtSignal(object, str, str)  # 分时数据加载完成信号 (time_share_data, code, name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_stock = None
        self.current_kline_code = ''  # 当前K线对应的股票代码，用于防止幽灵K线
        self.current_kline_data = None  # 保存当前K线数据，用于AI分析
        self._ai_analyzing = False  # AI分析是否进行中
        # V2.7.2：K线实时刷新定时器（盘中每30秒刷新一次）
        self._kline_refresh_timer = None
        self._init_ui()
        self._setup_kline_refresh_timer()

    def _init_ui(self):
        # 连接K线数据信号（跨线程安全）
        self.kline_data_ready.connect(self._set_kline_data)
        self.time_share_ready.connect(self._set_time_share_data)

    def _setup_kline_refresh_timer(self):
        """V2.7.2：设置K线实时刷新定时器（盘中每30秒刷新一次）"""
        try:
            from PyQt6.QtCore import QTimer
            self._kline_refresh_timer = QTimer(self)
            self._kline_refresh_timer.timeout.connect(self._refresh_kline_realtime)
            self._kline_refresh_timer.start(30000)  # 30秒刷新一次
            print("[详情页] K线实时刷新定时器已启动（30秒/次）")
        except Exception as e:
            print(f"[详情页] K线刷新定时器启动失败: {e}")

    def _is_trading_time(self):
        """V2.7.2：判断是否为交易时段"""
        try:
            from datetime import datetime, time
            now = datetime.now().time()
            # 上午交易时段 9:30-11:30，下午交易时段 13:00-15:00
            morning_start = time(9, 30)
            morning_end = time(11, 30)
            afternoon_start = time(13, 0)
            afternoon_end = time(15, 0)
            return (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end)
        except Exception:
            return True  # 出错时默认刷新

    def _refresh_kline_realtime(self):
        """V2.7.2：实时刷新当前股票的K线数据"""
        try:
            if not self.current_stock:
                return
            if not self._is_trading_time():
                return  # 非交易时段不刷新
            
            code = self.current_stock.get('code', '')
            name = self.current_stock.get('name', '')
            if not code:
                return
            
            # 重新加载K线数据（使用现有方法）
            self._load_kline_async(code, name)
        except Exception as e:
            print(f"[详情页] K线实时刷新失败: {e}")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 顶部信息栏
        header = QHBoxLayout()

        self.back_btn = QPushButton('← 返回')
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; border: 1px solid #30363d;
                border-radius: 4px; padding: 4px 12px; color: #f0f6fc;
            }
            QPushButton:hover { background: #30363d; }
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        header.addWidget(self.back_btn)

        self.stock_title = QLabel('请选择股票')
        self.stock_title.setStyleSheet('font-size: 18px; font-weight: bold; color: #f0f6fc;')
        header.addWidget(self.stock_title)

        self.price_label = QLabel('')
        self.price_label.setStyleSheet('font-size: 16px; font-weight: bold;')
        header.addWidget(self.price_label)

        self.pct_label = QLabel('')
        self.pct_label.setStyleSheet('font-size: 14px; font-weight: bold;')
        header.addWidget(self.pct_label)

        header.addStretch()
        main_layout.addLayout(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: none; background: #0d1117; }')

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        # 周期切换按钮栏
        period_bar = QWidget()
        period_bar.setStyleSheet('background: #161b22; border-radius: 6px 6px 0 0;')
        period_layout = QHBoxLayout(period_bar)
        period_layout.setContentsMargins(10, 5, 10, 5)
        period_layout.setSpacing(5)
        
        self.detail_period = 'day'
        self.detail_period_buttons = {}
        periods = [
            ('15min', '15分'),
            ('30min', '30分'),
            ('60min', '60分'),
            ('day', '日K'),
            ('week', '周K'),
            ('month', '月K'),
        ]
        
        for period, name in periods:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #8b949e;
                    border: none;
                    padding: 2px 8px;
                    font-size: 12px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background: #21262d;
                    color: #f0f6fc;
                }
                QPushButton:checked {
                    background: #21262d;
                    color: #58a6ff;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, p=period: self._on_detail_period_changed(p))
            period_layout.addWidget(btn)
            self.detail_period_buttons[period] = btn
        
        # 默认选中日K
        self.detail_period_buttons['day'].setChecked(True)
        
        period_layout.addStretch()
        content_layout.addWidget(period_bar)
        
        # K线图
        self.kline_chart = KlineContainer()
        self.kline_chart.setMinimumHeight(400)
        # 连接光标位置变化信号，实现K线与MACD/KDJ联动
        self.kline_chart.cursor_index_changed.connect(self._on_kline_cursor_changed)
        content_layout.addWidget(self.kline_chart)

        # 指标区（垂直排列：MACD在上，KDJ在下）
        self.macd_chart = MacdWidget()
        self.macd_chart.setMinimumHeight(130)
        content_layout.addWidget(self.macd_chart)
        self.kdj_chart = KdjWidget()
        self.kdj_chart.setMinimumHeight(130)
        content_layout.addWidget(self.kdj_chart)

        # 技术指标数值
        self.indicator_frame = QFrame()
        self.indicator_frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        self.indicator_layout = QVBoxLayout(self.indicator_frame)
        content_layout.addWidget(self.indicator_frame)

        # AI分析区
        self.ai_frame = QFrame()
        self.ai_frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        self.ai_layout = QVBoxLayout(self.ai_frame)
        content_layout.addWidget(self.ai_frame)

        # 信号标签区
        self.signal_frame = QFrame()
        self.signal_frame.setStyleSheet('background: #161b22; border-radius: 6px;')
        self.signal_layout = QVBoxLayout(self.signal_frame)
        content_layout.addWidget(self.signal_frame)

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def show_stock(self, stock_data):
        """显示股票详情"""
        import threading
        print(f"[DETAIL show_stock] 被调用，线程ID: {threading.current_thread().ident}")
        print(f"[详情页] stock_data类型: {type(stock_data)}")
        print(f"[详情页] stock_data keys: {list(stock_data.keys()) if stock_data else 'None'}")
        
        if not stock_data:
            print("[详情页] ❌ stock_data为空，返回")
            return
        
        try:
            self.current_stock = stock_data
            code = stock_data.get('code', '')
            name = stock_data.get('name', '')
            price = stock_data.get('price', 0)
            pct_chg = stock_data.get('pct_chg', 0)
            ai_analysis = stock_data.get('ai_analysis', {})
            signals = stock_data.get('signals', [])
            
            print(f"[详情页] 股票: {name} ({code}), 价格: {price}, 涨跌幅: {pct_chg}")
            print(f"[详情页] 信号数量: {len(signals)}")
            
            # 标题
            self.stock_title.setText(f'{name} ({code})')
            
            # 价格（安全转换）
            try:
                price_val = float(price) if price else 0
                self.price_label.setText(f'{price_val:.2f}')
                price_color = '#f85149' if pct_chg >= 0 else '#3fb950'
                self.price_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {price_color};')
                self.pct_label.setText(f'{pct_chg:+.2f}%')
                self.pct_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {price_color};')
            except Exception as e:
                print(f"[详情页] 价格显示出错: {e}")
                self.price_label.setText('--')
                self.pct_label.setText('--')
            
            # K线图：详情页自己获取500根K线，统一数据源
            # 不用传入的kline（可能是批量扫描的120根）
            print(f"[DETAIL KLINE START] code: {code}")
            self.current_kline_code = code  # 设置当前K线代码，用于防止幽灵K线
            self._load_kline_async(code, name)
            
            # 技术指标数值
            try:
                self._update_indicators(ai_analysis.get('indicators', {}))
            except Exception as e:
                print(f"[详情页] 指标更新出错: {e}")
            
            # AI分析
            try:
                self._update_ai_analysis(ai_analysis)
            except Exception as e:
                print(f"[详情页] AI分析更新出错: {e}")
            
            # 信号标签
            try:
                self._update_signals(signals)
            except Exception as e:
                print(f"[详情页] 信号更新出错: {e}")
            
            print("[详情页] show_stock基础信息加载完成")
            
        except Exception as e:
            print(f"[详情页] ❌ show_stock整体出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_kline_async(self, code, name):
        """异步加载K线数据（后台线程获取，主线程设置）"""
        import threading
        print(f"[详情页] _load_kline_async启动，股票: {name} ({code})")
        
        def _do():
            try:
                print(f"[详情页] 后台线程开始获取K线: {code}")
                from utils.kline_provider import get_daily_kline
                kline = get_daily_kline(code, count=500)
                
                if kline:
                    print(f"[DETAIL KLINE RESULT] code: {code}, count: {len(kline.get('close', []))}")
                else:
                    print(f"[DETAIL KLINE RESULT] code: {code}, count: 0 (失败)")
                
                # 用信号发送到主线程（跨线程安全）
                print(f"[详情页] 发送kline_data_ready信号: {code}")
                self.kline_data_ready.emit(kline, code, name)
            except Exception as e:
                print(f"[详情页] 获取K线出错: {e}")
                import traceback
                traceback.print_exc()
        
        threading.Thread(target=_do, daemon=True).start()
        print(f"[详情页] 后台线程已启动: {code}")
    
    def _on_kline_cursor_changed(self, index):
        """K线光标位置变化时，同步更新MACD和KDJ的光标"""
        if hasattr(self, 'macd_chart') and self.macd_chart:
            self.macd_chart.set_cursor_index(index)
        if hasattr(self, 'kdj_chart') and self.kdj_chart:
            self.kdj_chart.set_cursor_index(index)
    
    def _set_kline_data(self, kline, code, name):
        """在主线程设置K线数据"""
        import threading
        print(f"[详情页] _set_kline_data进入")
        print(f"[SET KLINE] code: {code}, 线程ID: {threading.current_thread().ident}")
        print(f"[详情页] 请求代码: {code}, 当前代码: {self.current_kline_code}")
        print(f"[详情页] KlineContainer初始化状态: {self.kline_chart.is_initialized}")
        print(f"[详情页] KlineContainer使用类型: {self.kline_chart.get_kline_type()}")
        
        # 幽灵K线防护：如果当前股票代码已经变了，就不更新
        if code != self.current_kline_code:
            print(f"[详情页] ⚠️  股票已切换，忽略旧请求 {code}")
            return
        
        if not kline or not isinstance(kline, dict) or len(kline.get('close', [])) < 10:
            print("[详情页] ⚠️  K线数据不足或格式不对")
            return
        
        try:
            kline_count = len(kline['close'])
            print(f"[KLINE UPDATE] old_code: {self.current_kline_code}, new_code: {code}, data_count: {kline_count}")
            print(f"[详情页] K线数据正常，共{kline_count}根，开始设置K线...")
            print(f"[详情页] K线第一天: 日期={kline.get('dates', [''])[0] if kline.get('dates') else 'N/A'}, 开={kline['open'][0]}, 收={kline['close'][0]}")
            print(f"[详情页] K线最后一天: 日期={kline.get('dates', [''])[-1] if kline.get('dates') else 'N/A'}, 开={kline['open'][-1]}, 收={kline['close'][-1]}, 低={kline['low'][-1]}, 高={kline['high'][-1]}, 量={kline['volume'][-1]}")

            # 保存K线数据用于AI分析
            self.current_kline_data = kline
            
            # 验证MA计算（手动计算MA5/MA10/MA20）
            closes = kline['close']
            if len(closes) >= 5:
                ma5_check = sum(closes[-5:]) / 5
                print(f"[详情页] MA5验证（手动计算最后一天）: {ma5_check:.2f}")
            if len(closes) >= 10:
                ma10_check = sum(closes[-10:]) / 10
                print(f"[详情页] MA10验证（手动计算最后一天）: {ma10_check:.2f}")
            if len(closes) >= 20:
                ma20_check = sum(closes[-20:]) / 20
                print(f"[详情页] MA20验证（手动计算最后一天）: {ma20_check:.2f}")
            
            # 设置K线
            print(f"[详情页] 调用kline_chart.set_kline_data...")
            self.kline_chart.set_kline_data(kline, code)
            print(f"[详情页] K线设置完成")

            # AI视觉识别：检测五买等形态并在K线图显示标记
            try:
                from ai.kline_vision import get_kline_vision
                vision = get_kline_vision()
                vision_signals = vision.analyze(kline)
                if vision_signals:
                    signal_dicts = [
                        {
                            'signal_type': s.signal_type,
                            'score': s.score,
                            'date': s.date,
                            'price': s.price,
                            'reason': s.reason,
                        }
                        for s in vision_signals
                    ]
                    self.kline_chart.set_vision_signals(signal_dicts)
                    print(f"[详情页 AI视觉] 识别到{len(vision_signals)}个信号: {[s.signal_type for s in vision_signals]}")

                # AI结构区域标记
                structure_data = vision.get_structure_data(kline)
                if structure_data:
                    self.kline_chart.set_vision_structure(structure_data)
                    if 'trend_stage' in structure_data:
                        print(f"[详情页 AI视觉] 走势阶段: {structure_data['trend_stage']}")
            except Exception as ve:
                print(f"[详情页 AI视觉] 识别异常: {ve}")

            # MACD/KDJ图
            try:
                dif, dea, macd_hist = calc_macd_series(kline['close'], fast=8, slow=21, signal=5)
                self.macd_chart.set_macd(dif, dea, macd_hist)
                
                k, d, j = calc_kdj_series(kline['high'], kline['low'], kline['close'], n=13, m1=3, m2=3)
                self.kdj_chart.set_kdj(k, d, j)
                print("[详情页] MACD/KDJ设置完成")
            except Exception as e:
                print(f"[详情页] MACD/KDJ计算出错: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"[详情页] K线设置出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _set_time_share_data(self, data, code, name):
        """设置分时图数据（主线程）"""
        print(f"[详情页] _set_time_share_data进入，code: {code}")
        
        # 幽灵K线防护
        if code != self.current_kline_code:
            print(f"[详情页] ⚠️  股票已切换，忽略旧分时请求 {code}")
            return
        
        if not data:
            print("[详情页] ⚠️  分时数据为空")
            return
        
        try:
            print(f"[详情页] 分时数据正常，共{len(data.get('times', []))}分钟")
            self.kline_chart.set_time_share_data(data)
            print("[详情页] 分时图设置完成")
            
            # MACD/KDJ清空（分时图不需要）
            # TODO: 分时图可以添加分时指标
            
        except Exception as e:
            print(f"[详情页] 分时图设置出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_detail_period_changed(self, period):
        """详情页K线周期切换"""
        if period == self.detail_period:
            return
        
        # 更新按钮状态
        for p, btn in self.detail_period_buttons.items():
            btn.setChecked(p == period)
        
        self.detail_period = period
        print(f"[详情页] 切换K线周期: {period}")
        
        # 如果有当前股票，重新加载K线
        if self.current_kline_code and self.current_stock:
            name = self.current_stock.get('name', '')
            self._load_detail_kline_for_period(self.current_kline_code, name, period)
    
    def _load_detail_kline_for_period(self, code, name, period):
        """加载指定周期的K线数据（后台线程）"""
        if period == 'time':
            # 分时图
            def _do_time():
                try:
                    from utils.kline_provider import get_minute_time_data
                    data = get_minute_time_data(code)
                    if data:
                        # 用信号发送到主线程
                        self.time_share_ready.emit(data, code, name)
                except Exception as e:
                    print(f"[详情页] 加载分时图失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            import threading
            threading.Thread(target=_do_time, daemon=True).start()
            return
        
        def _do():
            try:
                from utils.kline_provider import get_kline_by_period
                count = 500 if period in ['day', 'week', 'month'] else 300
                kline = get_kline_by_period(code, count, period)
                if kline:
                    # 用信号发送到主线程
                    self.kline_data_ready.emit(kline, code, name)
            except Exception as e:
                print(f"[详情页] 加载{period}K线失败: {e}")
                import traceback
                traceback.print_exc()
        
        import threading
        threading.Thread(target=_do, daemon=True).start()

    def _update_indicators(self, indicators):
        # 清空
        while self.indicator_layout.count():
            item = self.indicator_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        title = QLabel('📈 技术指标')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc; padding: 8px;')
        self.indicator_layout.addWidget(title)

        if not indicators:
            return

        data_layout = QHBoxLayout()
        items = [
            ('MA5', indicators.get('ma5', 0)),
            ('MA10', indicators.get('ma10', 0)),
            ('MA20', indicators.get('ma20', 0)),
            ('K', indicators.get('k', 0)),
            ('D', indicators.get('d', 0)),
            ('J', indicators.get('j', 0)),
            ('DIF', indicators.get('dif', 0)),
            ('DEA', indicators.get('dea', 0)),
            ('量比', indicators.get('vol_ratio', 0)),
        ]

        for name, val in items:
            label = QLabel(f'{name}: {val:.2f}')
            label.setStyleSheet('color: #8b949e; font-size: 12px; padding: 4px 8px;')
            data_layout.addWidget(label)

        self.indicator_layout.addLayout(data_layout)

    def _update_ai_analysis(self, ai_analysis):
        """更新AI分析区域（预计算数据 + Ollama本地AI按钮）"""
        while self.ai_layout.count():
            item = self.ai_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 标题行：标题 + AI智能分析按钮
        title_row = QHBoxLayout()
        title = QLabel('🤖 AI交易分析')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc; padding: 8px;')
        title_row.addWidget(title)
        title_row.addStretch()

        self.ai_analyze_btn = QPushButton('🧠 AI智能分析')
        self.ai_analyze_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb; color: #ffffff;
                border: 1px solid #1f6feb; border-radius: 4px;
                padding: 4px 12px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #388bfd; }
            QPushButton:disabled { background: #21262d; color: #8b949e; border-color: #30363d; }
        """)
        self.ai_analyze_btn.clicked.connect(self._on_ai_analyze)
        title_row.addWidget(self.ai_analyze_btn)

        self.signal_explain_btn = QPushButton('📖 信号解读')
        self.signal_explain_btn.setStyleSheet("""
            QPushButton {
                background: #238636; color: #ffffff;
                border: 1px solid #238636; border-radius: 4px;
                padding: 4px 12px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #2ea043; }
            QPushButton:disabled { background: #21262d; color: #8b949e; border-color: #30363d; }
        """)
        self.signal_explain_btn.clicked.connect(self._on_signal_explain)
        title_row.addWidget(self.signal_explain_btn)

        self.multi_period_btn = QPushButton('📊 多周期')
        self.multi_period_btn.setStyleSheet("""
            QPushButton {
                background: #8957e5; color: #ffffff;
                border: 1px solid #8957e5; border-radius: 4px;
                padding: 4px 12px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #a371f7; }
            QPushButton:disabled { background: #21262d; color: #8b949e; border-color: #30363d; }
        """)
        self.multi_period_btn.clicked.connect(self._on_multi_period)
        title_row.addWidget(self.multi_period_btn)
        self.ai_layout.addLayout(title_row)

        if not ai_analysis:
            # 提示文字
            hint = QLabel('点击上方"AI智能分析"按钮，使用本地大模型分析当前股票')
            hint.setStyleSheet('color: #8b949e; font-size: 11px; padding: 4px 8px;')
            hint.setWordWrap(True)
            self.ai_layout.addWidget(hint)
            return

        # 评分和趋势
        header_layout = QHBoxLayout()
        score = ai_analysis.get('score', 0)
        trend = ai_analysis.get('trend', '')
        suggestion = ai_analysis.get('suggestion', '')

        score_color = '#ff1744' if score >= 80 else '#00e676' if score >= 60 else '#ffea00' if score >= 40 else '#757575'
        score_label = QLabel(f'AI评分: {score}/100')
        score_label.setStyleSheet(f'color: {score_color}; font-size: 16px; font-weight: bold; padding: 0 8px;')
        header_layout.addWidget(score_label)

        trend_label = QLabel(f'趋势: {trend}')
        trend_color = '#f85149' if trend == '强势' else '#ffea00' if trend == '中性' else '#3fb950'
        trend_label.setStyleSheet(f'color: {trend_color}; font-size: 14px; padding: 0 8px;')
        header_layout.addWidget(trend_label)

        suggestion_label = QLabel(f'建议: {suggestion}')
        suggestion_label.setStyleSheet('color: #58a6ff; font-size: 14px; font-weight: bold; padding: 0 8px;')
        header_layout.addWidget(suggestion_label)
        header_layout.addStretch()
        self.ai_layout.addLayout(header_layout)

        # 买入条件
        buy_conditions = ai_analysis.get('buy_conditions', [])
        if buy_conditions:
            buy_label = QLabel(f'✅ 买入条件: {", ".join(buy_conditions[:5])}')
            buy_label.setStyleSheet('color: #3fb950; font-size: 12px; padding: 4px 8px;')
            buy_label.setWordWrap(True)
            self.ai_layout.addWidget(buy_label)

        # 风险
        risks = ai_analysis.get('risks', [])
        if risks:
            risk_label = QLabel(f'⚠️ 风险提示: {", ".join(risks[:5])}')
            risk_label.setStyleSheet('color: #f85149; font-size: 12px; padding: 4px 8px;')
            risk_label.setWordWrap(True)
            self.ai_layout.addWidget(risk_label)

        # Ollama分析结果显示区域
        self.ai_result_label = QLabel('')
        self.ai_result_label.setStyleSheet('color: #c9d1d9; font-size: 12px; padding: 8px; background: #0d1117; border-radius: 4px;')
        self.ai_result_label.setWordWrap(True)
        self.ai_result_label.setVisible(False)
        self.ai_layout.addWidget(self.ai_result_label)

    def _update_signals(self, signals):
        while self.signal_layout.count():
            item = self.signal_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        title = QLabel('🏷️ 识别信号')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #f0f6fc; padding: 8px;')
        self.signal_layout.addWidget(title)

        if not signals:
            empty = QLabel('暂无信号')
            empty.setStyleSheet('color: #8b949e; font-size: 12px; padding: 0 8px 8px;')
            self.signal_layout.addWidget(empty)
            return

        sig_layout = QHBoxLayout()
        sig_layout.setSpacing(6)
        for sig in signals:
            name = sig.get('name', '')
            color = sig.get('color', '#8b949e')
            desc = sig.get('desc', '')
            label = QLabel(f'[{name}] {desc}')
            label.setStyleSheet(f'color: {color}; font-size: 11px; padding: 4px 8px;')
            label.setWordWrap(True)
            sig_layout.addWidget(label)
        sig_layout.addStretch()
        self.signal_layout.addLayout(sig_layout)

    # ===== V0.7.1 Ollama本地AI分析 =====

    def _on_signal_explain(self):
        """点击信号解读按钮"""
        from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox
        from ai.signal_explainer import get_ai_signal_explainer

        explainer = get_ai_signal_explainer()

        # 获取当前股票信号
        signal_keys = []
        if hasattr(self, 'current_signals') and self.current_signals:
            signal_keys = list(self.current_signals.keys()) if isinstance(self.current_signals, dict) else self.current_signals

        # 如果没有信号，从stock_data获取
        if not signal_keys and hasattr(self, 'stock_data'):
            signals = self.stock_data.get('signals', [])
            signal_names = self.stock_data.get('signal_names', [])
            if signal_names:
                # 映射信号名到键名
                name_to_key = {
                    '横盘筑底': 'horizontal_base',
                    '锐角': 'sharp_angle',
                    '五日线': 'ma5_touch',
                    '一阳穿5/10': 'cross_5_10',
                    '一阳穿三线': 'cross_three',
                    '倍量': 'double_volume',
                    '回踩': 'pullback',
                    '注意买点': 'buy_point',
                    '59线': 'line_59',
                    '买入': 'buy_confirm',
                    '穿九': 'cross_9',
                    '站二十': 'stand_ma20',
                }
                for name in signal_names:
                    key = name_to_key.get(name)
                    if key:
                        signal_keys.append(key)

        # 技术数据
        technical_data = {}
        if hasattr(self, 'stock_data'):
            kline = self.stock_data.get('kline', {})
            if kline:
                closes = kline.get('close', [])
                if closes:
                    technical_data['price'] = closes[-1]
                    if len(closes) >= 2:
                        technical_data['pct_chg'] = (closes[-1] - closes[-2]) / closes[-2] * 100

        # 生成解释
        stock_name = getattr(self, 'current_name', '股票')
        stock_code = getattr(self, 'current_code', '')

        if signal_keys:
            explanation = explainer.generate_stock_explanation(
                stock_name, stock_code, signal_keys, technical_data
            )
        else:
            explanation = f"【{stock_name}({stock_code}) 信号解读】\n\n当前暂无明确技术信号。\n\n建议：\n- 继续观察价格和成交量变化\n- 等待MA5/MA10/MACD等指标给出明确信号\n- 关注大盘和板块环境"

        # 显示对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f'📖 信号解读 - {stock_name}')
        dialog.resize(600, 500)
        dialog.setStyleSheet("""
            QDialog { background: #0d1117; }
            QTextEdit {
                background: #161b22; color: #f0f6fc;
                border: 1px solid #30363d; border-radius: 4px;
                padding: 8px; font-size: 12px;
            }
        """)

        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(explanation)
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)

        dialog.exec()

    def _on_multi_period(self):
        """点击多周期分析按钮"""
        from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox, QPushButton, QHBoxLayout, QApplication
        from ai.multi_period_analyzer import get_multi_period_analyzer

        analyzer = get_multi_period_analyzer()
        stock_code = getattr(self, 'current_code', '')
        stock_name = getattr(self, 'current_name', '股票')

        if not stock_code:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f'📊 多周期分析 - {stock_name}')
        dialog.resize(650, 600)
        dialog.setStyleSheet("""
            QDialog { background: #0d1117; }
            QTextEdit {
                background: #161b22; color: #f0f6fc;
                border: 1px solid #30363d; border-radius: 4px;
                padding: 8px; font-size: 12px;
            }
        """)

        layout = QVBoxLayout(dialog)

        # 按钮行
        btn_layout = QHBoxLayout()
        ai_btn = QPushButton('🧠 AI深度分析')
        ai_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb; color: white;
                border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: #388bfd; }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(ai_btn)
        layout.addLayout(btn_layout)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText('正在分析日线、周线、月线数据...')
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)

        # 执行分析
        analysis = analyzer.analyze_all_periods(stock_code, stock_name)
        text_edit.setPlainText(analyzer.format_report(analysis))

        def do_ai_analysis():
            ai_btn.setEnabled(False)
            ai_btn.setText('分析中...')
            QApplication.processEvents()
            try:
                report = analyzer.generate_ai_report(analysis)
                text_edit.setPlainText(report)
            except Exception as e:
                text_edit.setPlainText(f'AI分析失败: {e}')
            ai_btn.setEnabled(True)
            ai_btn.setText('🧠 AI深度分析')

        ai_btn.clicked.connect(do_ai_analysis)

        dialog.exec()

    def _on_ai_analyze(self):
        """点击AI智能分析按钮"""
        if self._ai_analyzing:
            return
        if not self.current_kline_data:
            if hasattr(self, 'ai_result_label'):
                self.ai_result_label.setText('⚠️ K线数据未加载完成，请稍候再试')
                self.ai_result_label.setVisible(True)
            return

        self._ai_analyzing = True
        self.ai_analyze_btn.setEnabled(False)
        self.ai_analyze_btn.setText('⏳ 分析中...')

        # 显示加载提示
        if hasattr(self, 'ai_result_label'):
            self.ai_result_label.setText('🧠 正在调用本地AI模型分析，请稍候（首次加载约10-30秒）...')
            self.ai_result_label.setVisible(True)

        # 收集指标数据
        indicators = self._collect_indicators_for_ai()

        # 获取股票基本信息
        code = self.current_stock.get('code', '') if self.current_stock else ''
        name = self.current_stock.get('name', '') if self.current_stock else ''
        price = self.current_stock.get('price', 0) if self.current_stock else 0
        pct_chg = self.current_stock.get('pct_chg', 0) if self.current_stock else 0
        signals = self.current_stock.get('signals', []) if self.current_stock else []

        # 启动后台线程
        self._ai_thread = AIAnalysisThread(
            code=code, name=name, price=price, pct_chg=pct_chg,
            indicators=indicators, signals=signals
        )
        self._ai_thread.finished.connect(self._on_ai_result)
        self._ai_thread.error.connect(self._on_ai_error)
        self._ai_thread.start()

    def _collect_indicators_for_ai(self) -> dict:
        """从当前K线数据收集技术指标，用于AI分析"""
        kline = self.current_kline_data
        if not kline:
            return {}

        closes = kline.get('close', [])
        highs = kline.get('high', [])
        lows = kline.get('low', [])
        volumes = kline.get('volume', [])

        if len(closes) < 20:
            return {}

        indicators = {}

        # 最新价格和涨跌幅
        indicators['最新收盘'] = round(closes[-1], 2)
        if len(closes) >= 2:
            daily_chg = (closes[-1] - closes[-2]) / closes[-2] * 100
            indicators['当日涨跌幅'] = f'{daily_chg:+.2f}%'

        # 均线
        try:
            ma5 = calc_ma_series(closes, 5)
            ma10 = calc_ma_series(closes, 10)
            ma20 = calc_ma_series(closes, 20)
            ma60 = calc_ma_series(closes, 60) if len(closes) >= 60 else None
            ma120 = calc_ma_series(closes, 120) if len(closes) >= 120 else None

            def _last(series):
                """安全获取pandas Series最后一个值"""
                if series is None or len(series) == 0:
                    return None
                try:
                    val = series.iloc[-1]
                    return None if pd.isna(val) else float(val)
                except Exception:
                    return None

            ma5_last = _last(ma5)
            ma10_last = _last(ma10)
            ma20_last = _last(ma20)
            ma60_last = _last(ma60)
            ma120_last = _last(ma120)

            if ma5_last: indicators['MA5'] = round(ma5_last, 2)
            if ma10_last: indicators['MA10'] = round(ma10_last, 2)
            if ma20_last: indicators['MA20'] = round(ma20_last, 2)
            if ma60_last: indicators['MA60'] = round(ma60_last, 2)
            if ma120_last: indicators['MA120'] = round(ma120_last, 2)

            # 均线排列判断
            if all([ma5_last, ma10_last, ma20_last]):
                if ma5_last > ma10_last > ma20_last:
                    indicators['均线排列'] = '多头排列（强势）'
                elif ma5_last < ma10_last < ma20_last:
                    indicators['均线排列'] = '空头排列（弱势）'
                else:
                    indicators['均线排列'] = '交叉缠绕（震荡）'

            # 价格与MA20关系
            if ma20_last:
                if closes[-1] > ma20_last:
                    indicators['价格位置'] = f'站上MA20（支撑{ma20_last:.2f}）'
                else:
                    indicators['价格位置'] = f'跌破MA20（压力{ma20_last:.2f}）'
        except Exception as e:
            indicators['均线计算'] = f'异常: {e}'

        # MACD
        try:
            dif, dea, macd_hist = calc_macd_series(closes, fast=8, slow=21, signal=5)
            if dif is not None and dea is not None and macd_hist is not None and len(dif) > 0:
                dif_last = float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else 0
                dea_last = float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else 0
                hist_last = float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else 0

                indicators['MACD_DIF'] = round(dif_last, 4)
                indicators['MACD_DEA'] = round(dea_last, 4)
                indicators['MACD柱'] = round(hist_last, 4)

                # MACD状态判断
                if len(dif) >= 2:
                    dif_prev = float(dif.iloc[-2]) if not pd.isna(dif.iloc[-2]) else 0
                    dea_prev = float(dea.iloc[-2]) if not pd.isna(dea.iloc[-2]) else 0
                    hist_prev = float(macd_hist.iloc[-2]) if not pd.isna(macd_hist.iloc[-2]) else 0

                    if dif_last > dea_last and dif_prev <= dea_prev:
                        indicators['MACD状态'] = '金叉（买入信号）'
                    elif dif_last < dea_last and dif_prev >= dea_prev:
                        indicators['MACD状态'] = '死叉（卖出信号）'
                    elif dif_last > dea_last:
                        if hist_last > hist_prev:
                            indicators['MACD状态'] = '红柱扩大（多头增强）'
                        else:
                            indicators['MACD状态'] = '红柱缩小（多头减弱）'
                    else:
                        if hist_last < hist_prev:
                            indicators['MACD状态'] = '绿柱扩大（空头增强）'
                        else:
                            indicators['MACD状态'] = '绿柱缩小（空头减弱）'

                if dif_last > 0 and dea_last > 0:
                    indicators['MACD位置'] = '零轴上方（强势区）'
                elif dif_last < 0 and dea_last < 0:
                    indicators['MACD位置'] = '零轴下方（弱势区）'
                else:
                    indicators['MACD位置'] = '零轴附近（变盘区）'
        except Exception as e:
            indicators['MACD计算'] = f'异常: {e}'

        # KDJ
        try:
            k, d, j = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)
            if k is not None and d is not None and j is not None and len(k) > 0:
                k_last = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50
                d_last = float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 50
                j_last = float(j.iloc[-1]) if not pd.isna(j.iloc[-1]) else 50

                indicators['KDJ_K'] = round(k_last, 2)
                indicators['KDJ_D'] = round(d_last, 2)
                indicators['KDJ_J'] = round(j_last, 2)

                # KDJ状态
                if k_last > 80:
                    indicators['KDJ状态'] = '超买区（警惕回调）'
                elif k_last < 20:
                    indicators['KDJ状态'] = '超卖区（关注反弹）'
                else:
                    indicators['KDJ状态'] = '正常区间'

                if len(k) >= 2:
                    k_prev = float(k.iloc[-2]) if not pd.isna(k.iloc[-2]) else 50
                    d_prev = float(d.iloc[-2]) if not pd.isna(d.iloc[-2]) else 50
                    if k_last > d_last and k_prev <= d_prev:
                        indicators['KDJ金叉'] = '是（低位金叉更佳）'
                    elif k_last < d_last and k_prev >= d_prev:
                        indicators['KDJ死叉'] = '是（高位死叉风险大）'
        except Exception as e:
            indicators['KDJ计算'] = f'异常: {e}'

        # 成交量
        try:
            if volumes and len(volumes) >= 5:
                avg_vol5 = sum(volumes[-5:]) / 5
                current_vol = volumes[-1]
                vol_ratio = current_vol / avg_vol5 if avg_vol5 > 0 else 0
                indicators['今日成交量'] = round(current_vol, 0)
                indicators['5日均量'] = round(avg_vol5, 0)
                indicators['量比'] = round(vol_ratio, 2)

                if vol_ratio >= 2:
                    indicators['量能状态'] = '明显放量'
                elif vol_ratio >= 1.2:
                    indicators['量能状态'] = '温和放量'
                elif vol_ratio <= 0.7:
                    indicators['量能状态'] = '缩量'
                else:
                    indicators['量能状态'] = '量能正常'
        except Exception as e:
            indicators['成交量计算'] = f'异常: {e}'

        # 近期高低点
        try:
            if len(closes) >= 20:
                recent_high = max(highs[-20:])
                recent_low = min(lows[-20:])
                indicators['20日最高'] = round(recent_high, 2)
                indicators['20日最低'] = round(recent_low, 2)
                position_in_range = (closes[-1] - recent_low) / (recent_high - recent_low) * 100 if recent_high > recent_low else 50
                indicators['20日位置'] = f'{position_in_range:.0f}%（0%=最低，100%=最高）'
        except Exception:
            pass

        return indicators

    def _on_ai_result(self, result: str):
        """AI分析完成回调"""
        self._ai_analyzing = False
        self.ai_analyze_btn.setEnabled(True)
        self.ai_analyze_btn.setText('🧠 AI智能分析')

        if hasattr(self, 'ai_result_label'):
            self.ai_result_label.setText(result)
            self.ai_result_label.setVisible(True)

    def _on_ai_error(self, error: str):
        """AI分析错误回调"""
        self._ai_analyzing = False
        self.ai_analyze_btn.setEnabled(True)
        self.ai_analyze_btn.setText('🧠 AI智能分析')

        if hasattr(self, 'ai_result_label'):
            self.ai_result_label.setText(f'⚠️ AI分析失败: {error}')
            self.ai_result_label.setVisible(True)


class AIAnalysisThread(QThread):
    """AI分析后台线程，避免UI阻塞"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, code, name, price, pct_chg, indicators, signals):
        super().__init__()
        self.code = code
        self.name = name
        self.price = price
        self.pct_chg = pct_chg
        self.indicators = indicators
        self.signals = signals

    def run(self):
        try:
            from ai.ollama_client import get_ollama_client
            client = get_ollama_client()

            if not client.is_available():
                self.error.emit('Ollama服务未启动，请先启动Ollama')
                return

            # 构建信号描述
            signal_desc = ''
            if self.signals:
                signal_names = [s.get('name', s.get('desc', '')) for s in self.signals if isinstance(s, dict)]
                if signal_names:
                    signal_desc = ', '.join(signal_names[:5])

            # 构建提示词
            import json
            prompt = f"""请对以下A股股票进行专业技术分析：

股票：{self.name}({self.code})
当前价格：{self.price}
涨跌幅：{self.pct_chg:+.2f}%
当前识别信号：{signal_desc if signal_desc else '无'}

技术指标数据：
{json.dumps(self.indicators, ensure_ascii=False, indent=2)}

请按以下格式输出分析结果：

【当前趋势判断】
（结合均线排列、价格位置、MACD位置判断）

【K线形态分析】
（结合近期高低点、20日位置、量能状态判断）

【技术优势】
1. ...
2. ...
（列出支持上涨的技术条件，2-3条）

【风险提示】
1. ...
2. ...
（列出需要警惕的风险信号，2-3条）

【操作建议】
（观察/关注/谨慎，不给出具体买卖点和价位）

请简洁、客观、专业地回答，不要预测具体涨跌，只分析当前技术状态。"""

            result = client.chat(prompt, temperature=0.3)
            if result:
                self.finished.emit(result)
            else:
                self.error.emit('AI模型返回为空')
        except Exception as e:
            import traceback
            self.error.emit(f'{str(e)[:100]}')
