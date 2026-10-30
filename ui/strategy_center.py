"""
AI策略中心页面
显示当前市场状态、推荐策略、禁止策略
用户可切换策略：短线游资、趋势波段、价值投资、超跌反弹、防守模式
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QScrollArea, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from strategy.strategy_selector import StrategySelector
from strategy.strategy_library import StrategyLibrary
from strategy.market_state_engine import MarketStateEngine


class StrategyCenterWidget(QWidget):
    """AI策略中心页面"""

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strategy_selector = StrategySelector()
        self.strategy_library = StrategyLibrary()
        self.current_result = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部：市场状态 + 推荐策略
        layout.addWidget(self._create_market_status_bar())

        # 策略切换按钮
        layout.addWidget(self._create_strategy_buttons())

        # 中部：策略详情 + 市场分析
        middle = QHBoxLayout()
        middle.addWidget(self._create_strategy_detail(), 2)
        middle.addWidget(self._create_market_analysis(), 1)
        layout.addLayout(middle, 1)

        # 底部：操作建议
        layout.addWidget(self._create_suggestions())

    def _create_market_status_bar(self):
        """创建市场状态栏"""
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
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(30)

        # 当前市场状态
        state_layout = QVBoxLayout()
        state_label = QLabel('当前市场状态')
        state_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.market_state_label = QLabel('震荡轮动')
        self.market_state_label.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 24px; font-weight: bold;")
        state_layout.addWidget(state_label)
        state_layout.addWidget(self.market_state_label)
        layout.addLayout(state_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line)

        # 推荐策略
        strategy_layout = QVBoxLayout()
        strategy_label = QLabel('AI推荐策略')
        strategy_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.recommended_strategy_label = QLabel('趋势波段')
        self.recommended_strategy_label.setStyleSheet(f"color: {self.DARK_COLORS['green']}; font-size: 24px; font-weight: bold;")
        strategy_layout.addWidget(strategy_label)
        strategy_layout.addWidget(self.recommended_strategy_label)
        layout.addLayout(strategy_layout)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.VLine)
        line2.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line2)

        # 仓位建议
        position_layout = QVBoxLayout()
        position_label = QLabel('建议仓位')
        position_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.position_label = QLabel('40%-60%')
        self.position_label.setStyleSheet(f"color: {self.DARK_COLORS['orange']}; font-size: 24px; font-weight: bold;")
        position_layout.addWidget(position_label)
        position_layout.addWidget(self.position_label)
        layout.addLayout(position_layout)

        # 分隔线
        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.VLine)
        line3.setStyleSheet(f"color: {self.DARK_COLORS['border']};")
        layout.addWidget(line3)

        # 禁止策略
        forbidden_layout = QVBoxLayout()
        forbidden_label = QLabel('禁止策略')
        forbidden_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        self.forbidden_label = QLabel('追涨打板')
        self.forbidden_label.setStyleSheet(f"color: {self.DARK_COLORS['red']}; font-size: 16px; font-weight: bold;")
        forbidden_layout.addWidget(forbidden_label)
        forbidden_layout.addWidget(self.forbidden_label)
        layout.addLayout(forbidden_layout)

        layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton('🔄 重新分析')
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.DARK_COLORS['accent']};
                color: white;
                border: none;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #79b8ff;
            }}
        """)
        refresh_btn.clicked.connect(self.refresh_analysis)
        layout.addWidget(refresh_btn)

        return bar

    def _create_strategy_buttons(self):
        """创建策略切换按钮"""
        bar = QFrame()
        bar.setFixedHeight(60)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        title = QLabel('策略切换:')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        strategies = [
            (StrategyLibrary.STRATEGY_HOT_MONEY, '🟥 短线游资', '#f85149'),
            (StrategyLibrary.STRATEGY_TREND, '🟩 趋势波段', '#3fb950'),
            (StrategyLibrary.STRATEGY_VALUE, '🟦 价值投资', '#58a6ff'),
            (StrategyLibrary.STRATEGY_OVERSOLD, '🟨 超跌反弹', '#d29922'),
            (StrategyLibrary.STRATEGY_DEFENSE, '⬛ 防守模式', '#8b949e'),
        ]

        self.strategy_buttons = {}
        for strategy, name, color in strategies:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.DARK_COLORS['bg_tertiary']};
                    color: {color};
                    border: 2px solid {color};
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: bold;
                    border-radius: 6px;
                }}
                QPushButton:checked {{
                    background-color: {color};
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {color};
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked, s=strategy: self._on_strategy_selected(s))
            layout.addWidget(btn)
            self.strategy_buttons[strategy] = btn

        layout.addStretch()

        return bar

    def _create_strategy_detail(self):
        """创建策略详情面板"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel('📊 策略详情')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self.strategy_detail_text = QTextEdit()
        self.strategy_detail_text.setReadOnly(True)
        self.strategy_detail_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.strategy_detail_text, 1)

        return frame

    def _create_market_analysis(self):
        """创建市场分析面板"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel('📈 市场分析')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        # 各维度得分
        self.market_scores_text = QTextEdit()
        self.market_scores_text.setReadOnly(True)
        self.market_scores_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.market_scores_text, 1)

        return frame

    def _create_suggestions(self):
        """创建操作建议栏"""
        bar = QFrame()
        bar.setFixedHeight(80)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)

        title = QLabel('💡 AI操作建议')
        title.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        self.suggestions_label = QLabel('等待分析...')
        self.suggestions_label.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 12px;")
        self.suggestions_label.setWordWrap(True)
        layout.addWidget(self.suggestions_label)

        return bar

    def refresh_analysis(self):
        """刷新市场分析"""
        # 使用默认数据进行分析（实际使用时传入真实指数数据）
        result = self.strategy_selector.select_strategy()
        self.current_result = result
        self._update_display(result)

    def _update_display(self, result):
        """更新显示"""
        # 市场状态
        self.market_state_label.setText(result['market_state'])
        self.market_state_label.setStyleSheet(f"color: {result['market_state_color']}; font-size: 24px; font-weight: bold;")

        # 推荐策略
        self.recommended_strategy_label.setText(result['selected_strategy'])
        self.recommended_strategy_label.setStyleSheet(f"color: {result['strategy_color']}; font-size: 24px; font-weight: bold;")

        # 仓位
        self.position_label.setText(f"{result['position_min']}%-{result['position_max']}%")

        # 禁止策略
        forbidden = result.get('forbidden_strategies', [])
        self.forbidden_label.setText('、'.join(forbidden) if forbidden else '无')

        # 选中推荐策略按钮
        strategy = result['selected_strategy']
        for s, btn in self.strategy_buttons.items():
            btn.setChecked(s == strategy)

        # 策略详情
        self._update_strategy_detail(strategy)

        # 市场分析
        self._update_market_analysis(result)

        # 操作建议
        suggestions = result.get('suggestions', [])
        self.suggestions_label.setText(' | '.join(suggestions[:4]))

    def _update_strategy_detail(self, strategy):
        """更新策略详情"""
        details = {
            StrategyLibrary.STRATEGY_HOT_MONEY: """
            <h3 style="color:#f85149;">🟥 游资短线攻击模式</h3>
            <p><b>适合市场：</b>牛市攻击、市场强势阶段</p>
            <p><b>核心逻辑：</b>抓涨停、做龙头、快进快出</p>
            <p><b>扫描条件：</b></p>
            <ul>
                <li>涨停基因（近20日涨停次数≥2）</li>
                <li>龙头地位（10日涨幅领先）</li>
                <li>资金抢筹（量能放大1.5倍以上）</li>
                <li>热点第一梯队（接近近期新高）</li>
            </ul>
            <p><b>买点：</b>回封板、分歧低吸</p>
            <p><b>风险：</b>龙头断板、情绪退潮</p>
            <p><b>仓位：</b>20%-30%</p>
            <p><b>持有：</b>1-3天</p>
            """,
            StrategyLibrary.STRATEGY_TREND: """
            <h3 style="color:#3fb950;">🟩 趋势波段模式</h3>
            <p><b>适合市场：</b>震荡偏强、趋势行情</p>
            <p><b>核心逻辑：</b>抓主升浪，回踩低吸</p>
            <p><b>条件：</b></p>
            <ul>
                <li>MA多头排列（MA5>MA10>MA20）</li>
                <li>MACD红柱扩大</li>
                <li>成交量温和增加</li>
                <li>回踩支撑有效</li>
            </ul>
            <p><b>操作：</b>持有为主，回踩10日/20日线加仓</p>
            <p><b>止损：</b>跌破20日线</p>
            <p><b>仓位：</b>30%-50%</p>
            <p><b>持有：</b>5-20天</p>
            """,
            StrategyLibrary.STRATEGY_VALUE: """
            <h3 style="color:#58a6ff;">🟦 价值成长模式</h3>
            <p><b>适合市场：</b>震荡市、中长期布局</p>
            <p><b>核心逻辑：</b>低估值+高成长，长期持有</p>
            <p><b>分析维度：</b></p>
            <ul>
                <li>营收增长、净利润增长</li>
                <li>行业空间大</li>
                <li>机构持仓</li>
                <li>估值合理（PE&lt;30）</li>
            </ul>
            <p><b>操作：</b>分批建仓，忽略短期波动</p>
            <p><b>仓位：</b>20%-40%</p>
            <p><b>持有：</b>3-12个月</p>
            """,
            StrategyLibrary.STRATEGY_OVERSOLD: """
            <h3 style="color:#d29922;">🟨 超跌反弹模式</h3>
            <p><b>适合市场：</b>震荡偏弱、熊市末期</p>
            <p><b>核心逻辑：</b>寻找错杀机会，快进快出</p>
            <p><b>寻找条件：</b></p>
            <ul>
                <li>跌幅较大（回撤≥25%）</li>
                <li>基本面未恶化</li>
                <li>资金开始回流</li>
                <li>放量止跌</li>
            </ul>
            <p><b>买点：</b>放量止跌时</p>
            <p><b>目标：</b>反弹至20日/60日线</p>
            <p><b>仓位：</b>10%-20%</p>
            <p><b>持有：</b>3-10天</p>
            """,
            StrategyLibrary.STRATEGY_DEFENSE: """
            <h3 style="color:#8b949e;">⬛ 防守避险模式</h3>
            <p><b>适合市场：</b>熊市防守、市场弱势</p>
            <p><b>核心逻辑：</b>控制风险，现金为王</p>
            <p><b>过滤条件：</b></p>
            <ul>
                <li>业绩下降</li>
                <li>高减持</li>
                <li>监管风险</li>
                <li>高估值（PE&gt;50）</li>
            </ul>
            <p><b>操作：</b>减少操作，配置防御性品种</p>
            <p><b>仓位：</b>10%-20%</p>
            <p><b>配置方向：</b>银行、电力、公用事业</p>
            """,
        }

        self.strategy_detail_text.setHtml(details.get(strategy, '暂无详情'))

    def _update_market_analysis(self, result):
        """更新市场分析"""
        md = result.get('market_details', {})

        html = f"""
        <p><b>综合得分：</b><span style="color:{result['market_state_color']};font-size:18px;font-weight:bold;">{md.get('total_score', 0):.0f}</span>/100</p>
        <hr style="border:1px solid {self.DARK_COLORS['border']};">
        <p><b>趋势得分：</b>{md.get('trend_score', 0):.0f}/100</p>
        <p><b>量能得分：</b>{md.get('volume_score', 0):.0f}/100</p>
        <p><b>情绪得分：</b>{md.get('sentiment_score', 0):.0f}/100</p>
        <p><b>资金得分：</b>{md.get('fund_score', 0):.0f}/100</p>
        <p><b>轮动得分：</b>{md.get('rotation_score', 0):.0f}/100</p>
        <hr style="border:1px solid {self.DARK_COLORS['border']};">
        <p><b>分析原因：</b></p>
        """

        for reason in md.get('reasons', [])[:5]:
            html += f"<p>• {reason}</p>"

        self.market_scores_text.setHtml(html)

    def _on_strategy_selected(self, strategy):
        """策略选择事件"""
        for s, btn in self.strategy_buttons.items():
            btn.setChecked(s == strategy)
        self._update_strategy_detail(strategy)
