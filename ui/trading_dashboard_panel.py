# -*- coding: utf-8 -*-
"""
交易决策仪表盘 V1.0
综合决策入口，只读取已有数据，不修改任何核心策略
数据来源：市场情绪、AI选股、预警中心、交易辅助、资讯
"""
import os
import sys
import time
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def log_error(error):
    """记录错误日志"""
    try:
        log_file = os.path.join(LOG_DIR, 'dashboard_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {error}\n')
            f.write(traceback.format_exc() + '\n')
    except Exception:
        pass


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
    'purple': '#d500f9',
    'yellow': '#ffea00',
}


class TradingDashboardPanel(QWidget):
    """交易决策仪表盘页面"""

    # 数据更新信号
    data_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._load_start_time = 0
        self._market_data = None
        self._stock_pool_data = []
        self._alarm_data = []
        self._position_data = []
        self._news_data = []
        self._market_metrics = {}  # 市场指标标签
        self._position_summary = {}  # 持仓汇总标签

        self._init_ui()
        print("[决策仪表盘] 初始化完成")

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel('📈 交易决策仪表盘')
        title_label.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self.refresh_btn = QPushButton('🔄 刷新数据')
        self.refresh_btn.clicked.connect(self.refresh_all_data)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
                color: {DARK_COLORS['text_primary']};
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {DARK_COLORS['border']};
            }}
        """)
        title_layout.addWidget(self.refresh_btn)

        main_layout.addLayout(title_layout)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)

        # 第一行：市场状态
        self._create_market_section(content_layout)

        # 第二行：今日机会 + 实时机会
        row2 = QHBoxLayout()
        row2.setSpacing(15)
        self._create_stock_pool_section(row2)
        self._create_alarm_section(row2)
        content_layout.addLayout(row2)

        # 第三行：我的持仓 + 资讯催化
        row3 = QHBoxLayout()
        row3.setSpacing(15)
        self._create_position_section(row3)
        self._create_news_section(row3)
        content_layout.addLayout(row3)

        content_layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        # 加载时间标签
        self.load_time_label = QLabel('点击刷新加载数据')
        self.load_time_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
        self.load_time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.load_time_label)

    # ============================================================
    # 第一区域：市场状态
    # ============================================================
    def _create_market_section(self, parent_layout):
        """创建市场状态区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        # 标题
        title_label = QLabel('🌡️ 市场状态')
        title_label.setStyleSheet(f'font-size: 15px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        layout.addWidget(title_label)

        # 市场温度 + 指标
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)

        # 左侧：温度大数字
        self.market_temp_label = QLabel('--')
        self.market_temp_label.setStyleSheet(f'font-size: 48px; font-weight: bold; color: {DARK_COLORS["accent"]};')
        self.market_temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.market_temp_label, 1)

        # 右侧：状态 + 指标
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        self.market_status_label = QLabel('加载中...')
        self.market_status_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {DARK_COLORS["text_secondary"]};')
        right_layout.addWidget(self.market_status_label)

        # 指标网格
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)
        metrics_layout.setHorizontalSpacing(20)

        self._create_metric_item(metrics_layout, '涨停', 'limit_up', '--', DARK_COLORS['red'], 0, 0)
        self._create_metric_item(metrics_layout, '跌停', 'limit_down', '--', DARK_COLORS['green'], 0, 1)
        self._create_metric_item(metrics_layout, '上涨比例', 'up_ratio', '--%', DARK_COLORS['accent'], 1, 0)
        self._create_metric_item(metrics_layout, '炸板率', 'broken_ratio', '--%', DARK_COLORS['orange'], 1, 1)

        right_layout.addLayout(metrics_layout)

        content_layout.addLayout(right_layout, 3)

        layout.addLayout(content_layout)

        parent_layout.addWidget(frame)

    def _create_metric_item(self, layout, title, key, value, color, row, col):
        """创建单个小指标项"""
        item_layout = QVBoxLayout()
        item_layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
        item_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {color};')
        item_layout.addWidget(value_label)

        layout.addLayout(item_layout, row, col)
        self._market_metrics[key] = value_label

    # ============================================================
    # 第二区域：今日机会（AI选股TOP10）
    # ============================================================
    def _create_stock_pool_section(self, parent_layout):
        """创建今日机会区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel('🎯 今日机会 TOP10')
        title_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        count_label = QLabel('--只')
        count_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
        self.stock_pool_count = count_label
        title_layout.addWidget(count_label)

        layout.addLayout(title_layout)

        # 表格
        self.stock_pool_table = QTableWidget()
        self.stock_pool_table.setColumnCount(5)
        self.stock_pool_table.setHorizontalHeaderLabels(['股票', '评分', '价格', '涨跌幅', '信号'])
        self.stock_pool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stock_pool_table.horizontalHeader().setDefaultSectionSize(60)
        self.stock_pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stock_pool_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.stock_pool_table.verticalHeader().setVisible(False)
        self.stock_pool_table.setMaximumHeight(280)
        self.stock_pool_table.setStyleSheet(f"""
            QTableWidget {{
                background: {DARK_COLORS['bg_primary']};
                border: none;
                gridline-color: {DARK_COLORS['border']};
                color: {DARK_COLORS['text_primary']};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background: {DARK_COLORS['bg_tertiary']};
                color: {DARK_COLORS['text_secondary']};
                border: none;
                border-bottom: 1px solid {DARK_COLORS['border']};
                padding: 6px;
                font-size: 11px;
            }}
            QTableWidget::item {{
                padding: 4px;
                border: none;
            }}
        """)
        layout.addWidget(self.stock_pool_table, 1)

        parent_layout.addWidget(frame, 1)

    # ============================================================
    # 第三区域：实时机会（预警中心S级）
    # ============================================================
    def _create_alarm_section(self, parent_layout):
        """创建实时机会区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel('🔥 实时预警')
        title_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        s_count_label = QLabel('🔥 S级: --')
        s_count_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["red"]};')
        self.alarm_s_count = s_count_label
        title_layout.addWidget(s_count_label)

        layout.addLayout(title_layout)

        # 预警列表
        self.alarm_list_layout = QVBoxLayout()
        self.alarm_list_layout.setSpacing(8)
        self.alarm_list_layout.addStretch()

        layout.addLayout(self.alarm_list_layout, 1)

        parent_layout.addWidget(frame, 1)

    # ============================================================
    # 第四区域：我的持仓
    # ============================================================
    def _create_position_section(self, parent_layout):
        """创建我的持仓区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel('💼 我的持仓')
        title_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        layout.addWidget(title_label)

        # 汇总信息
        summary_layout = QGridLayout()
        summary_layout.setSpacing(10)

        self._create_summary_item(summary_layout, '持仓数量', 'pos_count', '--只', DARK_COLORS['accent'], 0, 0)
        self._create_summary_item(summary_layout, '今日盈亏', 'today_pnl', '--', DARK_COLORS['text_secondary'], 0, 1)
        self._create_summary_item(summary_layout, '总市值', 'total_value', '--', DARK_COLORS['text_primary'], 1, 0)
        self._create_summary_item(summary_layout, '风险等级', 'risk_level', '--', DARK_COLORS['orange'], 1, 1)

        layout.addLayout(summary_layout)

        # 持仓列表（简化）
        self.position_list_layout = QVBoxLayout()
        self.position_list_layout.setSpacing(6)
        self.position_list_layout.addStretch()

        layout.addLayout(self.position_list_layout, 1)

        parent_layout.addWidget(frame, 1)

    def _create_summary_item(self, layout, title, key, value, color, row, col):
        """创建汇总项"""
        item_layout = QVBoxLayout()
        item_layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
        item_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {color};')
        item_layout.addWidget(value_label)

        layout.addLayout(item_layout, row, col)
        self._position_summary[key] = value_label

    # ============================================================
    # 第五区域：资讯催化
    # ============================================================
    def _create_news_section(self, parent_layout):
        """创建资讯催化区域"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_secondary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel('📰 资讯催化')
        title_label.setStyleSheet(f'font-size: 14px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        layout.addWidget(title_label)

        # 热点标签
        self.hot_tags_layout = QHBoxLayout()
        self.hot_tags_layout.setSpacing(8)
        self.hot_tags_layout.addStretch()
        layout.addLayout(self.hot_tags_layout)

        # 新闻列表
        self.news_list_layout = QVBoxLayout()
        self.news_list_layout.setSpacing(8)
        self.news_list_layout.addStretch()

        layout.addLayout(self.news_list_layout, 1)

        parent_layout.addWidget(frame, 1)

    # ============================================================
    # 数据刷新
    # ============================================================
    def refresh_all_data(self):
        """刷新所有数据（只读取缓存，不重新计算）"""
        self._load_start_time = time.time()
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText('加载中...')

        def _do():
            try:
                # 1. 读取市场情绪数据
                self._load_market_data()

                # 2. 读取AI选股数据
                self._load_stock_pool_data()

                # 3. 读取预警中心数据
                self._load_alarm_data()

                # 4. 读取持仓数据
                self._load_position_data()

                # 5. 读取资讯数据
                self._load_news_data()

                # 通知主线程更新UI
                self.data_updated.emit()

            except Exception as e:
                log_error(str(e))
                print(f"[决策仪表盘] 数据加载失败: {e}")
                self.data_updated.emit()

        import threading
        threading.Thread(target=_do, daemon=True).start()

        # 连接信号
        try:
            self.data_updated.disconnect()
        except Exception:
            pass
        self.data_updated.connect(self._on_data_updated)

    def _on_data_updated(self):
        """数据加载完成，更新UI"""
        try:
            self._update_market_ui()
            self._update_stock_pool_ui()
            self._update_alarm_ui()
            self._update_position_ui()
            self._update_news_ui()

            elapsed = (time.time() - self._load_start_time) * 1000
            self.load_time_label.setText(f'加载时间: {elapsed:.0f}ms | 更新时间: {datetime.now().strftime("%H:%M:%S")}')

            print(f"[决策仪表盘] 数据加载完成，耗时{elapsed:.0f}ms")

        except Exception as e:
            log_error(str(e))
            print(f"[决策仪表盘] UI更新失败: {e}")

        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText('🔄 刷新数据')

    # ============================================================
    # 数据加载（只读取已有模块数据，不重新计算）
    # ============================================================
    def _load_market_data(self):
        """读取市场情绪数据"""
        try:
            # 从市场情绪模块读取缓存
            from ui.market_sentiment_panel import MarketSentimentPanel
            # 尝试获取单例（如果存在）
            if hasattr(MarketSentimentPanel, '_instance') and MarketSentimentPanel._instance:
                panel = MarketSentimentPanel._instance
                if hasattr(panel, '_data') and panel._data:
                    self._market_data = panel._data
                    print(f"[决策仪表盘] 读取市场情绪数据成功")
                    return
        except Exception:
            pass

        # 如果没有，尝试直接获取一次（简化）
        try:
            from utils.tdx_stock_list import get_stocks_with_quotes_tdx
            stocks = get_stocks_with_quotes_tdx()
            if stocks:
                # 简单计算几个核心指标
                total = len(stocks)
                up = sum(1 for s in stocks if s.get('pct_chg', 0) > 0.1)
                down = sum(1 for s in stocks if s.get('pct_chg', 0) < -0.1)
                up_ratio = up / total * 100 if total > 0 else 0

                self._market_data = {
                    'temp_score': int(up_ratio * 0.6 + 40),  # 简化估算
                    'status': '活跃' if up_ratio > 60 else '震荡' if up_ratio > 40 else '弱势',
                    # [CYB] 涨停/跌停家数按板性：主板 9.8% / 创业板 19.8%
                    'limit_up': sum(1 for s in stocks
                                    if s.get('pct_chg', 0) >= (
                                        19.8 if str(s.get('code', '')).startswith(('300', '301'))
                                        else 9.8)),
                    'limit_down': sum(1 for s in stocks
                                      if s.get('pct_chg', 0) <= -(
                                          19.8 if str(s.get('code', '')).startswith(('300', '301'))
                                          else 9.8)),
                    'up_ratio': up_ratio,
                    'broken_ratio': 15.0,  # 简化
                }
                print(f"[决策仪表盘] 市场情绪数据计算完成（简化版）")
        except Exception as e:
            log_error(str(e))
            self._market_data = None

    def _load_stock_pool_data(self):
        """读取AI选股池数据"""
        try:
            # 从菜单路由读取缓存
            from ui.menu_router import get_menu_router
            router = get_menu_router()
            cache, _ = router.get_stock_pool_cache()
            if cache:
                self._stock_pool_data = cache[:10]  # TOP10
                print(f"[决策仪表盘] 读取选股池数据成功，共{len(self._stock_pool_data)}只")
                return
        except Exception:
            pass

        # 没有缓存就空着
        self._stock_pool_data = []
        print(f"[决策仪表盘] 选股池暂无缓存数据")

    def _load_alarm_data(self):
        """读取预警中心数据"""
        try:
            from ui.alarm_center_panel import AlarmCenterPanel
            if hasattr(AlarmCenterPanel, '_instance') and AlarmCenterPanel._instance:
                panel = AlarmCenterPanel._instance
                if hasattr(panel, '_current_alarms'):
                    self._alarm_data = panel._current_alarms
                    print(f"[决策仪表盘] 读取预警数据成功，共{len(self._alarm_data)}条")
                    return
        except Exception:
            pass

        self._alarm_data = []
        print(f"[决策仪表盘] 预警中心暂无数据")

    def _load_position_data(self):
        """读取持仓数据"""
        try:
            from ui.trade_assistant_panel import TradeAssistantPanel
            if hasattr(TradeAssistantPanel, '_instance') and TradeAssistantPanel._instance:
                panel = TradeAssistantPanel._instance
                if hasattr(panel, '_positions'):
                    self._position_data = panel._positions
                    print(f"[决策仪表盘] 读取持仓数据成功，共{len(self._position_data)}只")
                    return
        except Exception:
            pass

        # 尝试从文件读取
        try:
            pos_file = os.path.join(DATA_DIR, 'trade_position.json')
            if os.path.exists(pos_file):
                import json
                with open(pos_file, 'r', encoding='utf-8') as f:
                    self._position_data = json.load(f)
                print(f"[决策仪表盘] 从文件读取持仓数据，共{len(self._position_data)}只")
                return
        except Exception:
            pass

        self._position_data = []

    def _load_news_data(self):
        """读取资讯数据"""
        try:
            # 从新闻面板读取
            from ui.news_panel import NewsPanelWidget
            # 简化：暂时用模拟数据，后续接入真实资讯
            self._news_data = [
                {'title': 'AI服务器需求爆发，相关产业链受益', 'hot': True},
                {'title': '人形机器人产业化加速', 'hot': True},
                {'title': '半导体设备国产化率提升', 'hot': True},
            ]
            print(f"[决策仪表盘] 资讯数据加载完成（模拟）")
        except Exception:
            self._news_data = []

    # ============================================================
    # UI更新
    # ============================================================
    def _update_market_ui(self):
        """更新市场状态UI"""
        if not self._market_data:
            self.market_temp_label.setText('--')
            self.market_status_label.setText('暂无数据')
            return

        temp = self._market_data.get('temp_score', 0)
        status = self._market_data.get('status', '--')

        self.market_temp_label.setText(str(temp))

        # 颜色
        if temp >= 80:
            color = DARK_COLORS['red']
        elif temp >= 60:
            color = DARK_COLORS['orange']
        elif temp >= 40:
            color = DARK_COLORS['accent']
        else:
            color = DARK_COLORS['green']

        self.market_temp_label.setStyleSheet(f'font-size: 48px; font-weight: bold; color: {color};')
        self.market_status_label.setText(status)
        self.market_status_label.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {color};')

        # 指标
        self._market_metrics['limit_up'].setText(str(self._market_data.get('limit_up', 0)))
        self._market_metrics['limit_down'].setText(str(self._market_data.get('limit_down', 0)))
        self._market_metrics['up_ratio'].setText(f"{self._market_data.get('up_ratio', 0):.1f}%")
        self._market_metrics['broken_ratio'].setText(f"{self._market_data.get('broken_ratio', 0):.1f}%")

    def _update_stock_pool_ui(self):
        """更新今日机会UI"""
        data = self._stock_pool_data
        self.stock_pool_count.setText(f'{len(data)}只')

        self.stock_pool_table.setRowCount(len(data))

        for row, stock in enumerate(data):
            name = stock.get('name', '')
            code = stock.get('code', '')
            score = stock.get('score', 0)
            price = stock.get('price', 0)
            pct_chg = stock.get('pct_chg', 0)
            signals = stock.get('signal_names', [])

            # 股票名称+代码
            self._set_table_item(self.stock_pool_table, row, 0, f'{name}\n{code}')

            # 评分
            score_item = QTableWidgetItem(str(score))
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if score >= 90:
                score_item.setForeground(QColor(DARK_COLORS['red']))
            elif score >= 80:
                score_item.setForeground(QColor(DARK_COLORS['orange']))
            else:
                score_item.setForeground(QColor(DARK_COLORS['accent']))
            self.stock_pool_table.setItem(row, 1, score_item)

            # 价格
            self._set_table_item(self.stock_pool_table, row, 2, f'{price:.2f}')

            # 涨跌幅
            pct_item = QTableWidgetItem(f'{pct_chg:+.1f}%')
            pct_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if pct_chg >= 0:
                pct_item.setForeground(QColor(DARK_COLORS['red']))
            else:
                pct_item.setForeground(QColor(DARK_COLORS['green']))
            self.stock_pool_table.setItem(row, 3, pct_item)

            # 信号
            signal_text = '、'.join(signals[:2]) if signals else '--'
            self._set_table_item(self.stock_pool_table, row, 4, signal_text)

    def _set_table_item(self, table, row, col, text):
        """设置表格项"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, col, item)

    def _update_alarm_ui(self):
        """更新实时预警UI"""
        # 清空
        while self.alarm_list_layout.count() > 0:
            item = self.alarm_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # S级数量
        s_count = sum(1 for a in self._alarm_data if a.get('level') == 'S')
        self.alarm_s_count.setText(f'🔥 S级: {s_count}')

        # 显示前5条
        display_alarms = self._alarm_data[:5]

        if not display_alarms:
            label = QLabel('暂无预警信号')
            label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.alarm_list_layout.addWidget(label)
            return

        for alarm in display_alarms:
            self.alarm_list_layout.addWidget(self._create_alarm_item(alarm))

        self.alarm_list_layout.addStretch()

    def _create_alarm_item(self, alarm):
        """创建单个预警项"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_tertiary']};
                border: 1px solid {DARK_COLORS['border']};
                border-radius: 6px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        level = alarm.get('level', 'B')
        level_color = DARK_COLORS['red'] if level == 'S' else DARK_COLORS['orange'] if level == 'A' else DARK_COLORS['accent']

        # 等级
        level_label = QLabel(level)
        level_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {level_color};')
        level_label.setFixedWidth(25)
        level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(level_label)

        # 股票信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(f"{alarm.get('name', '')} {alarm.get('code', '')}")
        name_label.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {DARK_COLORS["text_primary"]};')
        info_layout.addWidget(name_label)

        signal_text = '、'.join(alarm.get('signals', [])[:2])
        signal_label = QLabel(signal_text)
        signal_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
        info_layout.addWidget(signal_label)

        layout.addLayout(info_layout, 1)

        # 价格+评分
        right_layout = QVBoxLayout()
        right_layout.setSpacing(2)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        price_label = QLabel(f"{alarm.get('price', 0):.2f}")
        price_label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_primary"]};')
        right_layout.addWidget(price_label)

        score_label = QLabel(f"评分 {alarm.get('score', 0)}")
        score_label.setStyleSheet(f'font-size: 11px; color: {level_color};')
        right_layout.addWidget(score_label)

        layout.addLayout(right_layout)

        return frame

    def _update_position_ui(self):
        """更新持仓UI"""
        positions = self._position_data
        self._position_summary['pos_count'].setText(f'{len(positions)}只')

        # 计算总市值和盈亏
        total_value = 0
        total_pnl = 0
        for pos in positions:
            current = pos.get('current_price', pos.get('cost_price', 0))
            cost = pos.get('cost_price', 0)
            qty = pos.get('quantity', 0)
            total_value += current * qty
            total_pnl += (current - cost) * qty

        self._position_summary['total_value'].setText(f'{total_value:,.0f}')

        pnl_label = self._position_summary['today_pnl']
        pnl_label.setText(f'{total_pnl:+,.0f}')
        if total_pnl >= 0:
            pnl_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {DARK_COLORS["red"]};')
        else:
            pnl_label.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {DARK_COLORS["green"]};')

        # 风险等级
        risk = '低' if len(positions) <= 2 else '中' if len(positions) <= 5 else '高'
        risk_color = DARK_COLORS['green'] if risk == '低' else DARK_COLORS['orange'] if risk == '中' else DARK_COLORS['red']
        self._position_summary['risk_level'].setText(risk)
        self._position_summary['risk_level'].setStyleSheet(f'font-size: 16px; font-weight: bold; color: {risk_color};')

        # 清空列表
        while self.position_list_layout.count() > 0:
            item = self.position_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 显示前3只
        for pos in positions[:3]:
            self.position_list_layout.addWidget(self._create_position_item(pos))

        if len(positions) > 3:
            more_label = QLabel(f'... 还有{len(positions) - 3}只')
            more_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
            more_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.position_list_layout.addWidget(more_label)

        self.position_list_layout.addStretch()

    def _create_position_item(self, pos):
        """创建单个持仓项"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {DARK_COLORS['bg_tertiary']};
                border: none;
                border-radius: 4px;
            }}
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # 名称
        name_label = QLabel(f"{pos.get('name', '')}")
        name_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_primary"]};')
        layout.addWidget(name_label, 1)

        # 盈亏
        cost = pos.get('cost_price', 0)
        current = pos.get('current_price', cost)
        qty = pos.get('quantity', 0)
        pnl = (current - cost) * qty

        pnl_label = QLabel(f'{pnl:+.0f}')
        pnl_label.setStyleSheet(f'font-size: 11px; font-weight: bold; color: {DARK_COLORS["red"] if pnl >= 0 else DARK_COLORS["green"]};')
        layout.addWidget(pnl_label)

        return frame

    def _update_news_ui(self):
        """更新资讯UI"""
        # 清空热点标签
        while self.hot_tags_layout.count() > 0:
            item = self.hot_tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 清空新闻列表
        while self.news_list_layout.count() > 0:
            item = self.news_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._news_data:
            label = QLabel('暂无资讯')
            label.setStyleSheet(f'font-size: 12px; color: {DARK_COLORS["text_secondary"]};')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.news_list_layout.addWidget(label)
            self.hot_tags_layout.addStretch()
            return

        # 热点标签
        for news in self._news_data[:3]:
            tag = QLabel(f'🔥 {news["title"][:6]}')
            tag.setStyleSheet(f"""
                QLabel {{
                    background: {DARK_COLORS['bg_tertiary']};
                    border: 1px solid {DARK_COLORS['border']};
                    border-radius: 10px;
                    padding: 4px 10px;
                    font-size: 11px;
                    color: {DARK_COLORS['orange']};
                }}
            """)
            self.hot_tags_layout.addWidget(tag)

        self.hot_tags_layout.addStretch()

        # 新闻列表
        for news in self._news_data[:5]:
            news_label = QLabel(f'• {news["title"]}')
            news_label.setStyleSheet(f'font-size: 11px; color: {DARK_COLORS["text_secondary"]};')
            news_label.setWordWrap(True)
            self.news_list_layout.addWidget(news_label)

        self.news_list_layout.addStretch()

    def showEvent(self, event):
        """页面显示时自动刷新一次"""
        super().showEvent(event)
        if not self._market_data and not self._stock_pool_data:
            self.refresh_all_data()
