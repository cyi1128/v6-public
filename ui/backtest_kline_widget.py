# -*- coding: utf-8 -*-
"""
回测K线图组件 - matplotlib绘制K线+买卖点标记
专门用于回测结果可视化，稳定可靠，不依赖ECharts异步加载
"""
import os
import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

import matplotlib
matplotlib.use('Agg')  # 非交互式后端
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
from datetime import datetime

# 深色主题
matplotlib.rcParams['figure.facecolor'] = '#0d1117'
matplotlib.rcParams['axes.facecolor'] = '#0d1117'
matplotlib.rcParams['text.color'] = '#c9d1d9'
matplotlib.rcParams['axes.labelcolor'] = '#8b949e'
matplotlib.rcParams['xtick.color'] = '#8b949e'
matplotlib.rcParams['ytick.color'] = '#8b949e'
matplotlib.rcParams['grid.color'] = '#21262d'
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
matplotlib.rcParams['axes.unicode_minus'] = False


class BacktestKlineWidget(QWidget):
    """回测K线图组件 - 显示K线+成交量+买卖点标记"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        self._kline_data = None
        self._trade_points = []

    def set_data(self, kline_data, trade_points=None):
        """设置K线数据和买卖点

        Args:
            kline_data: dict, 包含 dates, open, high, low, close, volume
            trade_points: list, [{'date':'2025-01-01', 'type':'buy'/'sell', 'price':20.5, 'pnl':0}]
        """
        self._kline_data = kline_data
        self._trade_points = trade_points or []
        self._draw()

    def _draw(self):
        """绘制K线图"""
        self.figure.clear()
        if not self._kline_data:
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, '回测完成后显示K线图和买卖点',
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=14, color='#8b949e')
            ax.set_axis_off()
            self.canvas.draw()
            return

        dates = self._kline_data.get('dates', [])
        opens = self._kline_data.get('open', [])
        highs = self._kline_data.get('high', [])
        lows = self._kline_data.get('low', [])
        closes = self._kline_data.get('close', [])
        volumes = self._kline_data.get('volume', [])

        if not dates:
            return

        # 解析日期
        try:
            date_objs = [datetime.strptime(str(d)[:10], '%Y-%m-%d') for d in dates]
        except Exception:
            date_objs = list(range(len(dates)))

        n = len(dates)
        x = list(range(n))

        # 创建子图：K线(上) + 成交量(下)
        gs = self.figure.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)
        ax_kline = self.figure.add_subplot(gs[0])
        ax_volume = self.figure.add_subplot(gs[1], sharex=ax_kline)

        # 绘制K线
        width = 0.6
        for i in range(n):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            color = '#ef4444' if c >= o else '#22c55e'  # 红涨绿跌
            # 影线
            ax_kline.plot([x[i], x[i]], [l, h], color=color, linewidth=0.8)
            # 实体
            body_bottom = min(o, c)
            body_height = abs(c - o) if abs(c - o) > 0.001 else 0.001
            rect = Rectangle((x[i] - width/2, body_bottom), width, body_height,
                           facecolor=color, edgecolor=color, linewidth=0.5)
            ax_kline.add_patch(rect)

        # 绘制MA均线
        if n >= 5:
            ma5 = [sum(closes[max(0,i-4):i+1])/min(5,i+1) for i in range(n)]
            ax_kline.plot(x, ma5, color='#ffffff', linewidth=0.8, label='MA5', alpha=0.8)
        if n >= 9:
            ma9 = [sum(closes[max(0,i-8):i+1])/min(9,i+1) for i in range(n)]
            ax_kline.plot(x, ma9, color='#fbbf24', linewidth=0.8, label='MA9', alpha=0.8)
        if n >= 20:
            ma20 = [sum(closes[max(0,i-19):i+1])/min(20,i+1) for i in range(n)]
            ax_kline.plot(x, ma20, color='#3b82f6', linewidth=0.8, label='MA20', alpha=0.8)

        # 绘制买卖点标记
        date_to_idx = {str(d)[:10]: i for i, d in enumerate(dates)}
        buy_count = 0
        sell_count = 0
        for tp in self._trade_points:
            d = str(tp.get('date', tp.get('filled_date', '')))[:10]
            if d not in date_to_idx:
                continue
            idx = date_to_idx[d]
            ttype = tp.get('type', tp.get('side', ''))
            price = tp.get('price', tp.get('filled_price', 0))
            pnl = tp.get('pnl', 0)

            if 'buy' in str(ttype).lower() or '买' in str(ttype):
                ax_kline.annotate('▲B', xy=(idx, lows[idx] * 0.99),
                                fontsize=10, color='#22c55e', fontweight='bold',
                                ha='center', va='top')
                buy_count += 1
            elif 'sell' in str(ttype).lower() or '卖' in str(ttype):
                pnl_str = f'{pnl:+.0f}' if pnl else ''
                ax_kline.annotate(f'▼S{pnl_str}', xy=(idx, highs[idx] * 1.01),
                                fontsize=9, color='#ef4444', fontweight='bold',
                                ha='center', va='bottom')
                sell_count += 1

        # K线图样式
        ax_kline.set_title(f'K线回测图  (买入{buy_count}次 / 卖出{sell_count}次)',
                          fontsize=12, pad=10)
        ax_kline.legend(loc='upper left', fontsize=9, framealpha=0.3,
                       facecolor='#161b22', edgecolor='#30363d')
        ax_kline.grid(True, alpha=0.3)
        ax_kline.set_ylabel('价格')

        # 绘制成交量
        for i in range(n):
            color = '#ef4444' if closes[i] >= opens[i] else '#22c55e'
            ax_volume.bar(x[i], volumes[i], width=width, color=color, alpha=0.7)
        ax_volume.set_ylabel('成交量')
        ax_volume.grid(True, alpha=0.3)

        # X轴日期标签（稀疏显示）
        tick_step = max(1, n // 10)
        tick_positions = list(range(0, n, tick_step))
        tick_labels = [str(dates[i])[:10] for i in tick_positions]
        ax_volume.set_xticks(tick_positions)
        ax_volume.set_xticklabels(tick_labels, rotation=45, fontsize=8)
        ax_kline.set_xticklabels([])

        self.figure.tight_layout()
        self.canvas.draw()
