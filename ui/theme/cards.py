"""
通用卡片组件 - 科技感量化终端风格
支持渐变背景、发光边框、多种强调色
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# 强调色配置（对应React应用的accentMap）
ACCENT_COLORS = {
    'cyan': {
        'bg': '#0f172a',
        'border': '#164e63',
        'border_hover': '#22d3ee',
        'value': '#67e8f9',
        'icon_bg': '#164e63',
        'icon_color': '#22d3ee',
        'glow': '#22d3ee',
    },
    'purple': {
        'bg': '#0f172a',
        'border': '#581c87',
        'border_hover': '#c084fc',
        'value': '#d8b4fe',
        'icon_bg': '#581c87',
        'icon_color': '#a855f7',
        'glow': '#a855f7',
    },
    'yellow': {
        'bg': '#0f172a',
        'border': '#713f12',
        'border_hover': '#fbbf24',
        'value': '#fde047',
        'icon_bg': '#713f12',
        'icon_color': '#eab308',
        'glow': '#eab308',
    },
    'red': {
        'bg': '#0f172a',
        'border': '#7f1d1d',
        'border_hover': '#f87171',
        'value': '#fca5a5',
        'icon_bg': '#7f1d1d',
        'icon_color': '#ef4444',
        'glow': '#ef4444',
    },
    'green': {
        'bg': '#0f172a',
        'border': '#064e3b',
        'border_hover': '#4ade80',
        'value': '#86efac',
        'icon_bg': '#064e3b',
        'icon_color': '#22c55e',
        'glow': '#22c55e',
    },
    'orange': {
        'bg': '#0f172a',
        'border': '#7c2d12',
        'border_hover': '#fb923c',
        'value': '#fdba74',
        'icon_bg': '#7c2d12',
        'icon_color': '#f97316',
        'glow': '#f97316',
    },
    'gray': {
        'bg': '#0f172a',
        'border': '#334155',
        'border_hover': '#64748b',
        'value': '#e2e8f0',
        'icon_bg': '#1e293b',
        'icon_color': '#94a3b8',
        'glow': '#64748b',
    },
}


class CardWidget(QFrame):
    """基础卡片 - 带渐变背景和发光边框"""

    def __init__(self, accent='cyan', glow=False, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.glow = glow
        self._setup_style()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _setup_style(self):
        c = ACCENT_COLORS.get(self.accent, ACCENT_COLORS['cyan'])
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {c['bg']};
                border: 1px solid {c['border']};
                border-radius: 6px;
            }}
            CardWidget:hover {{
                border: 1px solid {c['border_hover']};
            }}
        """)

    def set_content(self, widget):
        """设置卡片内容"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(widget)


class DataCard(QFrame):
    """数据展示卡片 - 标签+数值+单位+子值"""

    def __init__(self, label, value, unit='', sub_value='',
                 sub_color='muted', accent='cyan', glow=False, parent=None):
        super().__init__(parent)
        self.accent = accent
        c = ACCENT_COLORS.get(accent, ACCENT_COLORS['cyan'])

        self.setStyleSheet(f"""
            DataCard {{
                background-color: {c['bg']};
                border: 1px solid {c['border']};
                border-radius: 6px;
            }}
            DataCard:hover {{
                border: 1px solid {c['border_hover']};
            }}
        """)
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # 标签
        self.label = QLabel(label)
        self.label.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.label)

        # 数值行
        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            f"color: {c['value']}; font-size: 22px; font-weight: 700; "
            f"font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        value_row.addWidget(self.value_label)

        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setStyleSheet("color: #64748b; font-size: 11px;")
            value_row.addWidget(self.unit_label)

        value_row.addStretch()
        layout.addLayout(value_row)

        # 子值
        if sub_value:
            color_map = {
                'up': '#ef4444',
                'down': '#22c55e',
                'muted': '#64748b',
            }
            self.sub_label = QLabel(sub_value)
            self.sub_label.setStyleSheet(
                f"color: {color_map.get(sub_color, '#64748b')}; font-size: 11px; font-weight: 500;"
            )
            layout.addWidget(self.sub_label)

    def update_value(self, value, sub_value=None):
        """更新数值"""
        self.value_label.setText(str(value))
        if sub_value and hasattr(self, 'sub_label'):
            self.sub_label.setText(sub_value)


class AIScoreCard(QFrame):
    """AI评分卡片 - 大数字+星级+建议"""

    def __init__(self, score=0, stars=0, suggestion='', confidence='', parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            AIScoreCard {
                background-color: #0f172a;
                border: 1px solid #7f1d1d;
                border-radius: 6px;
            }
        """)
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # 左侧：评分
        left = QVBoxLayout()
        left.setSpacing(2)

        self.score_label = QLabel(str(score))
        self.score_label.setStyleSheet(
            "color: #ef4444; font-size: 36px; font-weight: 700; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        left.addWidget(self.score_label)

        self.stars_label = QLabel('★' * stars + '☆' * (5 - stars))
        self.stars_label.setStyleSheet("color: #fbbf24; font-size: 14px;")
        left.addWidget(self.stars_label)

        layout.addLayout(left)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #1e293b;")
        layout.addWidget(sep)

        # 右侧：建议
        right = QVBoxLayout()
        right.setSpacing(4)

        title = QLabel('AI综合评分')
        title.setStyleSheet("color: #64748b; font-size: 11px;")
        right.addWidget(title)

        self.suggestion_label = QLabel(suggestion)
        self.suggestion_label.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: 600;")
        self.suggestion_label.setWordWrap(True)
        right.addWidget(self.suggestion_label)

        if confidence:
            self.confidence_label = QLabel(f'置信度: {confidence}')
            self.confidence_label.setStyleSheet("color: #38bdf8; font-size: 11px;")
            right.addWidget(self.confidence_label)

        right.addStretch()
        layout.addLayout(right, 1)

    def update_score(self, score, stars=None, suggestion=None):
        """更新评分"""
        self.score_label.setText(str(score))
        if stars is not None:
            self.stars_label.setText('★' * stars + '☆' * (5 - stars))
        if suggestion:
            self.suggestion_label.setText(suggestion)


class StockCard(QFrame):
    """股票信息卡片 - 代码名称+价格+涨跌"""

    def __init__(self, code='', name='', price=0, change=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            StockCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
            StockCard:hover {
                border: 1px solid #38bdf8;
            }
        """)
        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 左侧：代码名称
        left = QVBoxLayout()
        left.setSpacing(2)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #e2e8f0; font-size: 14px; font-weight: 600;")
        left.addWidget(self.name_label)

        self.code_label = QLabel(code)
        self.code_label.setStyleSheet(
            "color: #67e8f9; font-size: 11px; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        left.addWidget(self.code_label)

        layout.addLayout(left)
        layout.addStretch()

        # 右侧：价格涨跌
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.price_label = QLabel(f'{price:.2f}')
        self.price_label.setStyleSheet(
            "color: #e2e8f0; font-size: 16px; font-weight: 700; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        right.addWidget(self.price_label)

        change_color = '#ef4444' if change >= 0 else '#22c55e'
        change_sign = '+' if change >= 0 else ''
        self.change_label = QLabel(f'{change_sign}{change:.2f}%')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 12px; font-weight: 600;")
        right.addWidget(self.change_label)

        layout.addLayout(right)

    def update_stock(self, code, name, price, change):
        """更新股票信息"""
        self.code_label.setText(code)
        self.name_label.setText(name)
        self.price_label.setText(f'{price:.2f}')
        change_color = '#ef4444' if change >= 0 else '#22c55e'
        change_sign = '+' if change >= 0 else ''
        self.change_label.setText(f'{change_sign}{change:.2f}%')
        self.change_label.setStyleSheet(f"color: {change_color}; font-size: 12px; font-weight: 600;")


class SignalCard(QFrame):
    """信号标签卡片 - 流式标签展示"""

    def __init__(self, signals=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            SignalCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(6)

        title = QLabel('交易信号')
        title.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
        self.layout.addWidget(title)

        self.tags_layout = QHBoxLayout()
        self.tags_layout.setSpacing(6)
        self.layout.addLayout(self.tags_layout)

        if signals:
            self.set_signals(signals)

    def set_signals(self, signals):
        """设置信号标签"""
        # 清空旧标签
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        signal_colors = {
            'buy': '#0f172a', 'buy_border': '#065f46', 'buy_text': '#34d399',
            'sell': '#0f172a', 'sell_border': '#7f1d1d', 'sell_text': '#f87171',
            'watch': '#0f172a', 'watch_border': '#713f12', 'watch_text': '#fbbf24',
        }

        for sig in signals[:6]:
            tag = QLabel(sig)
            tag.setStyleSheet(
                f"background-color: {signal_colors['watch']}; "
                f"border: 1px solid {signal_colors['watch_border']}; "
                f"color: {signal_colors['watch_text']}; "
                f"padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;"
            )
            self.tags_layout.addWidget(tag)

        self.tags_layout.addStretch()


class PriceZoneCard(QFrame):
    """关键价格区间卡片"""

    def __init__(self, support=0, pressure=0, current=0, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            PriceZoneCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)
        self.setFixedHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel('关键价格区间')
        title.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
        layout.addWidget(title)

        # 价格行
        prices = QHBoxLayout()
        prices.setSpacing(8)

        # 支撑位
        support_box = QVBoxLayout()
        support_box.setSpacing(2)
        s_label = QLabel('支撑位')
        s_label.setStyleSheet("color: #22c55e; font-size: 10px;")
        support_box.addWidget(s_label)
        self.support_label = QLabel(f'{support:.2f}')
        self.support_label.setStyleSheet(
            "color: #86efac; font-size: 14px; font-weight: 700; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        support_box.addWidget(self.support_label)
        prices.addLayout(support_box)

        # 当前价
        current_box = QVBoxLayout()
        current_box.setSpacing(2)
        c_label = QLabel('当前价')
        c_label.setStyleSheet("color: #38bdf8; font-size: 10px;")
        current_box.addWidget(c_label)
        self.current_label = QLabel(f'{current:.2f}')
        self.current_label.setStyleSheet(
            "color: #67e8f9; font-size: 14px; font-weight: 700; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        current_box.addWidget(self.current_label)
        prices.addLayout(current_box)

        # 压力位
        pressure_box = QVBoxLayout()
        pressure_box.setSpacing(2)
        p_label = QLabel('压力位')
        p_label.setStyleSheet("color: #ef4444; font-size: 10px;")
        pressure_box.addWidget(p_label)
        self.pressure_label = QLabel(f'{pressure:.2f}')
        self.pressure_label.setStyleSheet(
            "color: #fca5a5; font-size: 14px; font-weight: 700; "
            "font-family: 'IBM Plex Mono', 'Consolas', monospace;"
        )
        pressure_box.addWidget(self.pressure_label)
        prices.addLayout(pressure_box)

        layout.addLayout(prices)

    def update_prices(self, support, pressure, current):
        """更新价格"""
        self.support_label.setText(f'{support:.2f}')
        self.pressure_label.setText(f'{pressure:.2f}')
        self.current_label.setText(f'{current:.2f}')


class CardRow(QHBoxLayout):
    """卡片行布局 - 均匀分布多个卡片"""

    def __init__(self, spacing=10, parent=None):
        super().__init__(parent)
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def add_card(self, card):
        """添加卡片"""
        self.addWidget(card)
