# -*- coding: utf-8 -*-
"""
通用K线查看对话框
点击股票后弹出显示K线图
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    ACCENT_GOLD, ACCENT_PURPLE, STATUS_SUCCESS, STATUS_INFO,
)


class KlineViewerDialog(QDialog):
    """K线查看对话框"""

    def __init__(self, code, name, parent=None):
        super().__init__(parent)
        self.code = code
        self.name = name
        self.kline_data = []
        # 使用项目TdxDataEngine加载K线（替代不可靠的utils.kline_provider）
        try:
            import sys
            import os
            BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if BASE_DIR not in sys.path:
                sys.path.insert(0, BASE_DIR)
            if os.path.join(BASE_DIR, 'data') not in sys.path:
                sys.path.insert(0, os.path.join(BASE_DIR, 'data'))
            from tdx_data_engine import TdxDataEngine
            self.engine = TdxDataEngine()
        except Exception:
            self.engine = None
        self._init_ui()
        self._load_kline()

    def _init_ui(self):
        self.setWindowTitle(f'📈 K线图 - {self.name}({self.code})')
        self.setMinimumSize(900, 600)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_WINDOW}; }}
            QLabel {{ color: {TEXT_PRIMARY}; }}
            QPushButton {{
                background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER}; border-radius: 5px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background: {BG_CARD}; border-color: {ACCENT_BLUE}; }}
            QComboBox {{
                background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER}; border-radius: 5px;
                padding: 4px 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        title_label = QLabel(f'{self.name} ({self.code})')
        title_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};')
        toolbar.addWidget(title_label)

        toolbar.addStretch()

        # 周期选择
        self.period_combo = QComboBox()
        self.period_combo.addItems(['日线', '周线', '月线'])
        self.period_combo.setFixedWidth(80)
        self.period_combo.currentTextChanged.connect(self._on_period_changed)
        toolbar.addWidget(QLabel('周期:'))
        toolbar.addWidget(self.period_combo)

        # 均线选择
        self.ma_combo = QComboBox()
        self.ma_combo.addItems(['MA5/9/20', 'MA5/10/20', 'MA5/20/60'])
        self.ma_combo.setFixedWidth(100)
        toolbar.addWidget(QLabel('均线:'))
        toolbar.addWidget(self.ma_combo)

        # 刷新按钮
        self.refresh_btn = QPushButton('🔄 刷新')
        self.refresh_btn.clicked.connect(self._load_kline)
        toolbar.addWidget(self.refresh_btn)

        layout.addLayout(toolbar)

        # K线画布
        self.canvas = KlineCanvas()
        layout.addWidget(self.canvas, 1)

        # 底部信息
        self.info_label = QLabel('加载中...')
        self.info_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

    def _load_kline(self):
        """加载K线数据：优先用本地kline_cache（启动时自动增量更新），兜底通达信"""
        self.info_label.setText('正在加载K线数据...')
        try:
            from services.kline_cache_service import get_latest_kline
            kline = get_latest_kline(self.code, count=250)
            if kline and len(kline) > 0:
                self._on_kline_loaded(kline)
                return
        except Exception as e:
            print(f"[K线查看] kline_cache失败，fallback通达信: {e}")
        if self.engine is not None:
            try:
                kline = self.engine.get_kline(self.code, days=250)
                self._on_kline_loaded(kline)
                return
            except Exception as e:
                print(f"[K线查看] 通达信也失败: {e}")
        self.info_label.setText('暂无K线数据')

    def _on_kline_loaded(self, kline):
        """K线数据加载完成"""
        if not kline or len(kline) == 0:
            self.info_label.setText('暂无K线数据')
            return

        self.kline_data = kline
        self.canvas.set_data(kline)

        # 显示最新价格信息
        latest = kline[-1]
        prev_close = kline[-2]['close'] if len(kline) > 1 else latest['open']
        change = latest['close'] - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
        color = '#f85149' if change >= 0 else '#3fb950'

        self.info_label.setText(
            f"最新: {latest['close']:.2f}  "
            f"<span style='color:{color}'>{change:+.2f} ({change_pct:+.2f}%)</span>  "
            f"最高: {latest['high']:.2f}  最低: {latest['low']:.2f}  "
            f"成交量: {latest['volume']:.0f}  共{len(kline)}根"
        )

    def _on_period_changed(self, period):
        """周期切换"""
        # 目前只支持日线，后续可扩展
        self._load_kline()


# ========== K线绘制画布 ==========
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtCore import QRectF, Qt


class KlineCanvas(QWidget):
    """K线绘制画布"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumHeight(400)
        self.setStyleSheet(f'background: {BG_WINDOW}; border: 1px solid {BORDER}; border-radius: 6px;')

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if not self.data or len(self.data) < 2:
            painter.setPen(QColor('#8b949e'))
            painter.setFont(QFont('Microsoft YaHei', 12))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, '暂无K线数据')
            return

        # 只显示最近120根
        display_data = self.data[-120:] if len(self.data) > 120 else self.data
        n = len(display_data)

        # 计算价格范围
        prices = []
        for d in display_data:
            prices.extend([d['high'], d['low']])
        max_p = max(prices)
        min_p = min(prices)
        p_range = max_p - min_p if max_p > min_p else 1

        # 布局: K线区70% + 成交量30%
        margin_left = 50
        margin_right = 10
        margin_top = 10
        margin_bottom = 25
        total_h = h - margin_top - margin_bottom
        kline_h = int(total_h * 0.7)
        vol_h = total_h - kline_h - 10
        vol_top = margin_top + kline_h + 10

        chart_w = w - margin_left - margin_right
        candle_w = max(2, chart_w / n * 0.7)
        gap = chart_w / n

        # 计算均线
        ma5 = self._calc_ma(display_data, 5)
        ma9 = self._calc_ma(display_data, 9)
        ma20 = self._calc_ma(display_data, 20)

        # 绘制网格
        painter.setPen(QPen(QColor('#21262d'), 1))
        for i in range(5):
            y = margin_top + kline_h * i / 4
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            price = max_p - p_range * i / 4
            painter.setPen(QColor('#8b949e'))
            painter.setFont(QFont('Consolas', 9))
            painter.drawText(2, int(y) + 4, f'{price:.2f}')
            painter.setPen(QPen(QColor('#21262d'), 1))

        # 绘制K线
        for i, d in enumerate(display_data):
            x = margin_left + i * gap + gap / 2
            open_p = d['open']
            close_p = d['close']
            high_p = d['high']
            low_p = d['low']

            is_up = close_p >= open_p
            color = QColor('#f85149') if is_up else QColor('#3fb950')

            # 影线
            y_high = margin_top + (max_p - high_p) / p_range * kline_h
            y_low = margin_top + (max_p - low_p) / p_range * kline_h
            painter.setPen(QPen(color, 1))
            painter.drawLine(int(x), int(y_high), int(x), int(y_low))

            # 实体
            y_open = margin_top + (max_p - open_p) / p_range * kline_h
            y_close = margin_top + (max_p - close_p) / p_range * kline_h
            body_top = min(y_open, y_close)
            body_h = max(1, abs(y_close - y_open))
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, 1))
            painter.drawRect(QRectF(x - candle_w / 2, body_top, candle_w, body_h))

        # 绘制均线
        self._draw_ma(painter, ma5, display_data, max_p, p_range, margin_left, gap, kline_h, margin_top, '#ffffff', 'MA5')
        self._draw_ma(painter, ma9, display_data, max_p, p_range, margin_left, gap, kline_h, margin_top, '#ffd700', 'MA9')
        self._draw_ma(painter, ma20, display_data, max_p, p_range, margin_left, gap, kline_h, margin_top, '#58a6ff', 'MA20')

        # 绘制成交量
        max_vol = max([d['volume'] for d in display_data]) if display_data else 1
        for i, d in enumerate(display_data):
            x = margin_left + i * gap + gap / 2
            vol = d['volume']
            vol_h_bar = (vol / max_vol) * vol_h if max_vol > 0 else 0
            is_up = d['close'] >= d['open']
            color = QColor('#f85149') if is_up else QColor('#3fb950')
            color.setAlpha(180)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x - candle_w / 2, vol_top + vol_h - vol_h_bar, candle_w, vol_h_bar))

        # 图例
        painter.setPen(QColor('#ffffff'))
        painter.setFont(QFont('Microsoft YaHei', 10))
        painter.drawText(margin_left + 5, margin_top + 15, 'MA5')
        painter.setPen(QColor('#ffd700'))
        painter.drawText(margin_left + 45, margin_top + 15, 'MA9')
        painter.setPen(QColor('#58a6ff'))
        painter.drawText(margin_left + 85, margin_top + 15, 'MA20')

        painter.end()

    def _draw_ma(self, painter, ma_data, display_data, max_p, p_range, margin_left, gap, kline_h, margin_top, color_str, label):
        """绘制均线"""
        if not ma_data:
            return
        color = QColor(color_str)
        painter.setPen(QPen(color, 1.5))
        points = []
        for i, val in enumerate(ma_data):
            if val is not None:
                x = margin_left + i * gap + gap / 2
                y = margin_top + (max_p - val) / p_range * kline_h
                points.append((x, y))
        for i in range(len(points) - 1):
            painter.drawLine(int(points[i][0]), int(points[i][1]),
                             int(points[i + 1][0]), int(points[i + 1][1]))

    def _calc_ma(self, data, period):
        """计算均线"""
        result = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(None)
            else:
                vals = [data[j]['close'] for j in range(i - period + 1, i + 1)]
                result.append(sum(vals) / period)
        return result
