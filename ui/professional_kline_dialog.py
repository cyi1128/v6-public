"""
V7.5.7 专业K线查看对话框
复用原程序自选股的KlineContainer（ECharts专业K线），支持：
- 鼠标拖拽平移
- 滚轮缩放
- 十字光标
- MA5/MA10/MA20/MA120
- MACD/KDJ/成交量
- 前复权数据
"""
import sys
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QTimer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class ProfessionalKlineDialog(QDialog):
    """专业K线查看对话框 - 复用KlineContainer"""

    def __init__(self, code, name, parent=None):
        super().__init__(parent)
        self.code = code
        self.name = name
        self.kline_container = None
        self._load_attempts = 0

        self.setWindowTitle(f'{name}({code}) - 专业K线图')
        self.setMinimumSize(1200, 700)
        self.resize(1200, 700)

        self._init_ui()
        self._load_kline_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部信息栏
        info_bar = QHBoxLayout()
        self.title_label = QLabel(f'📈 {self.name}({self.code}) - 日K线（前复权）')
        self.title_label.setStyleSheet('font-size: 14px; font-weight: 700; color: #58a6ff;')
        info_bar.addWidget(self.title_label)
        info_bar.addStretch()

        self.status_label = QLabel('加载中...')
        self.status_label.setStyleSheet('font-size: 11px; color: #8b949e;')
        info_bar.addWidget(self.status_label)

        close_btn = QPushButton('✕ 关闭')
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        info_bar.addWidget(close_btn)

        layout.addLayout(info_bar)

        # K线容器
        try:
            from ui.kline_container import KlineContainer
            self.kline_container = KlineContainer(self)
            layout.addWidget(self.kline_container, 1)
        except Exception as e:
            error_label = QLabel(f'K线组件加载失败：{e}\n\n请检查ui/kline_container.py是否存在。')
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet('color: #f85149; font-size: 14px;')
            layout.addWidget(error_label, 1)

        # 底部提示
        hint_label = QLabel('💡 操作提示：鼠标拖拽平移 | 滚轮缩放 | 移动鼠标显示十字光标 | MA5/10/20/120 + MACD + KDJ + 成交量')
        hint_label.setStyleSheet('font-size: 10px; color: #6e7681; background: #161b22; padding: 4px 8px; border-radius: 4px;')
        layout.addWidget(hint_label)

    def _load_kline_data(self):
        """加载K线数据"""
        try:
            from utils.kline_provider import get_daily_kline
            kline_data = get_daily_kline(self.code, count=250)
            if kline_data and len(kline_data.get('close', [])) >= 10:
                # 延迟设置数据，等待KlineContainer初始化完成
                QTimer.singleShot(500, lambda: self._set_kline_data(kline_data))
                self.status_label.setText(f'数据加载完成（{len(kline_data.get("close", []))}根K线）')
                self.status_label.setStyleSheet('font-size: 11px; color: #3fb950;')
            else:
                self.status_label.setText('数据不足，无法显示K线')
                self.status_label.setStyleSheet('font-size: 11px; color: #f85149;')
        except Exception as e:
            self.status_label.setText(f'数据加载失败：{e}')
            self.status_label.setStyleSheet('font-size: 11px; color: #f85149;')

    def _set_kline_data(self, kline_data):
        """设置K线数据到容器"""
        if self.kline_container:
            try:
                self.kline_container.set_kline_data(kline_data, getattr(self, 'code', ''))
            except Exception as e:
                # 如果组件还没初始化完成，重试一次
                self._load_attempts += 1
                if self._load_attempts < 3:
                    QTimer.singleShot(1000, lambda: self._set_kline_data(kline_data))
