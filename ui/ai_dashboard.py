"""
AI决策仪表盘
显示今日强势股票排名：名称、代码、AI评分、当前阶段、买入价格、止损价格、目标价格、风险等级、催化因素、操作建议
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QScrollArea, QGridLayout, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont


class DashboardRefreshWorker(QThread):
    """V0.7.1.1 AI仪表盘刷新后台线程"""
    finished = pyqtSignal(dict)  # 返回 dashboard_data
    error = pyqtSignal(str)

    def __init__(self, stock_codes=None, market_env='震荡', top_n=None):
        super().__init__()
        self._stock_codes = stock_codes
        self._market_env = market_env
        self._top_n = top_n

    def run(self):
        try:
            # 确保项目根目录在 sys.path 中
            import sys as _sys
            import os as _os
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from dashboard.decision_adapter import get_decision_adapter
            adapter = get_decision_adapter()
            data = adapter.get_dashboard_data(
                stock_codes=self._stock_codes,
                market_env=self._market_env,
                top_n=self._top_n,
            )
            self.finished.emit(data or {})
        except Exception as e:
            self.error.emit(str(e))


class AIDashboardWidget(QWidget):
    """AI决策仪表盘"""

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

    STAGE_COLORS = {
        '观察': '#8b949e',
        '回踩': '#39d0d8',
        '突破': '#d29922',
        '买入': '#f85149',
        '风险': '#da3633',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stocks_data = []
        self._refresh_worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部统计栏
        layout.addWidget(self._create_stats_bar())

        # 评分维度说明
        layout.addWidget(self._create_score_legend())

        # V0.7.1.1 状态标签（异步加载提示）
        self.status_label = QLabel('就绪')
        self.status_label.setStyleSheet(
            f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px; padding: 2px 4px;"
        )
        layout.addWidget(self.status_label)

        # 仪表盘表格
        self.dashboard_table = QTableWidget()
        self.dashboard_table.setColumnCount(11)
        self.dashboard_table.setHorizontalHeaderLabels([
            '排名', '股票名称', '代码', 'AI评分', '当前阶段',
            '买入价格', '止损价格', '目标价格', '风险等级',
            '催化因素', '操作建议'
        ])
        self.dashboard_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.dashboard_table.setAlternatingRowColors(True)
        self.dashboard_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dashboard_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dashboard_table.setSortingEnabled(True)
        self.dashboard_table.verticalHeader().setVisible(False)
        self.dashboard_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                gridline-color: {self.DARK_COLORS['border']};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 8px 4px;
            }}
            QHeaderView::section {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                color: {self.DARK_COLORS['text_secondary']};
                padding: 10px 6px;
                border: none;
                border-right: 1px solid {self.DARK_COLORS['border']};
                border-bottom: 1px solid {self.DARK_COLORS['border']};
                font-weight: bold;
                font-size: 12px;
            }}
        """)

        # 设置列宽
        self.dashboard_table.setColumnWidth(0, 50)   # 排名
        self.dashboard_table.setColumnWidth(1, 100)  # 股票名称
        self.dashboard_table.setColumnWidth(2, 90)   # 代码
        self.dashboard_table.setColumnWidth(3, 80)   # AI评分
        self.dashboard_table.setColumnWidth(4, 80)   # 当前阶段
        self.dashboard_table.setColumnWidth(5, 80)   # 买入价格
        self.dashboard_table.setColumnWidth(6, 80)   # 止损价格
        self.dashboard_table.setColumnWidth(7, 80)   # 目标价格
        self.dashboard_table.setColumnWidth(8, 70)   # 风险等级
        self.dashboard_table.setColumnWidth(9, 250)  # 催化因素
        self.dashboard_table.setColumnWidth(10, 250) # 操作建议

        layout.addWidget(self.dashboard_table, 1)

    def _create_stats_bar(self):
        """创建统计栏"""
        bar = QFrame()
        bar.setFixedHeight(70)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(25)

        # 统计项
        self.stats_labels = {}
        stats_items = [
            ('total', '股票总数', '0', self.DARK_COLORS['accent']),
            ('strong', '强烈关注(90+)', '0', self.DARK_COLORS['red']),
            ('focus', '重点观察(80+)', '0', self.DARK_COLORS['orange']),
            ('buy', '买入信号', '0', self.DARK_COLORS['green']),
            ('risk', '风险提示', '0', self.DARK_COLORS['yellow']),
            ('avg_score', '平均评分', '0', self.DARK_COLORS['cyan']),
        ]

        for key, label, value, color in stats_items:
            item_layout = QVBoxLayout()
            l = QLabel(label)
            l.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 11px;")
            v = QLabel(value)
            v.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            item_layout.addWidget(l)
            item_layout.addWidget(v)
            layout.addLayout(item_layout)
            self.stats_labels[key] = v

        layout.addStretch()

        return bar

    def _create_score_legend(self):
        """创建评分维度说明"""
        bar = QFrame()
        bar.setFixedHeight(35)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(20)

        legend_items = [
            ('趋势 25分', self.DARK_COLORS['accent']),
            ('量能 25分', self.DARK_COLORS['green']),
            ('技术 25分', self.DARK_COLORS['purple']),
            ('资金 25分', self.DARK_COLORS['orange']),
            ('|  90-100 强烈关注', self.DARK_COLORS['red']),
            ('80-90 重点观察', self.DARK_COLORS['orange']),
            ('70-80 等待确认', self.DARK_COLORS['yellow']),
            ('70以下 过滤', self.DARK_COLORS['text_secondary']),
        ]

        for text, color in legend_items:
            label = QLabel(text)
            label.setStyleSheet(f"color: {color}; font-size: 11px;")
            layout.addWidget(label)

        layout.addStretch()
        return bar

    def update_data(self, stocks_data):
        """更新仪表盘数据"""
        # 按AI评分排序
        sorted_stocks = sorted(stocks_data, key=lambda x: x.get('total_score', 0), reverse=True)
        self.stocks_data = sorted_stocks

        # 更新统计
        self._update_stats()

        # 更新表格
        self.dashboard_table.setSortingEnabled(False)
        self.dashboard_table.setRowCount(len(sorted_stocks))

        for i, stock in enumerate(sorted_stocks):
            row = i

            name = stock.get('name', '')
            ts_code = stock.get('ts_code', '')
            price = stock.get('price', stock.get('buy_price', 0))
            total_score = stock.get('total_score', 0)
            stage = stock.get('stage', '观察')
            buy_price = stock.get('buy_price', price)
            stop_loss = stock.get('stop_loss', 0)
            target_price = stock.get('target_price', 0)
            risk_level = stock.get('risk_level', '低')
            catalysts = stock.get('catalysts', [])
            catalyst_str = '、'.join(catalysts[:4]) if isinstance(catalysts, list) else str(catalysts)
            suggestion = stock.get('suggestion', '')

            items = [
                str(i + 1),
                name,
                ts_code,
                f'{total_score:.0f}',
                stage,
                f'{buy_price:.2f}',
                f'{stop_loss:.2f}',
                f'{target_price:.2f}',
                risk_level,
                catalyst_str,
                suggestion,
            ]

            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # 排名颜色
                if col == 0:
                    if i < 3:
                        item.setForeground(QColor(self.DARK_COLORS['yellow']))
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

                # AI评分颜色和进度条
                if col == 3:
                    color = self._get_score_color(total_score)
                    item.setForeground(QColor(color))
                    font = item.font()
                    font.setBold(True)
                    font.setPointSize(13)
                    item.setFont(font)

                # 阶段颜色
                if col == 4:
                    stage_color = self.STAGE_COLORS.get(stage, self.DARK_COLORS['text_secondary'])
                    item.setForeground(QColor(stage_color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                # 买入/止损/目标价格颜色
                if col == 5:  # 买入价
                    item.setForeground(QColor(self.DARK_COLORS['green']))
                if col == 6:  # 止损价
                    item.setForeground(QColor(self.DARK_COLORS['red']))
                if col == 7:  # 目标价
                    item.setForeground(QColor(self.DARK_COLORS['orange']))

                # 风险等级颜色
                if col == 8:
                    if risk_level == '高':
                        item.setForeground(QColor(self.DARK_COLORS['red']))
                    elif risk_level == '中':
                        item.setForeground(QColor(self.DARK_COLORS['orange']))
                    else:
                        item.setForeground(QColor(self.DARK_COLORS['green']))

                # 催化因素左对齐
                if col == 9:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setForeground(QColor(self.DARK_COLORS['cyan']))

                # 操作建议颜色
                if col == 10:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    if '买入' in text or '强烈' in text:
                        item.setForeground(QColor(self.DARK_COLORS['red']))
                    elif '关注' in text or '观察' in text:
                        item.setForeground(QColor(self.DARK_COLORS['orange']))
                    elif '谨慎' in text or '回避' in text or '过滤' in text:
                        item.setForeground(QColor(self.DARK_COLORS['green']))
                    else:
                        item.setForeground(QColor(self.DARK_COLORS['text_secondary']))

                # 交替行颜色
                if i % 2 == 1:
                    item.setBackground(QColor(self.DARK_COLORS['bg_secondary']))

                self.dashboard_table.setItem(row, col, item)

        self.dashboard_table.setSortingEnabled(True)

    def _update_stats(self):
        """更新统计数据"""
        if not self.stocks_data:
            return

        total = len(self.stocks_data)
        strong = len([s for s in self.stocks_data if s.get('total_score', 0) >= 90])
        focus = len([s for s in self.stocks_data if 80 <= s.get('total_score', 0) < 90])
        buy = len([s for s in self.stocks_data if s.get('stage', '') == '买入' or '买' in s.get('suggestion', '')])
        risk = len([s for s in self.stocks_data if s.get('risk_level', '') in ['中', '高']])
        avg_score = sum(s.get('total_score', 0) for s in self.stocks_data) / total if total > 0 else 0

        self.stats_labels['total'].setText(str(total))
        self.stats_labels['strong'].setText(str(strong))
        self.stats_labels['focus'].setText(str(focus))
        self.stats_labels['buy'].setText(str(buy))
        self.stats_labels['risk'].setText(str(risk))
        self.stats_labels['avg_score'].setText(f'{avg_score:.1f}')

    def _get_score_color(self, score):
        """根据评分获取颜色"""
        if score >= 90:
            return self.DARK_COLORS['red']
        elif score >= 80:
            return self.DARK_COLORS['orange']
        elif score >= 70:
            return self.DARK_COLORS['yellow']
        elif score >= 60:
            return self.DARK_COLORS['text_secondary']
        else:
            return self.DARK_COLORS['green']

    # ================================================================
    # V0.7 C5.2.1 新增：从DecisionService刷新数据（最低侵入）
    # ================================================================
    def refresh_from_service(
        self,
        stock_codes=None,
        market_env='震荡',
        top_n=None,
    ):
        """
        V0.7.1.1 异步刷新：后台线程计算，不阻塞UI主线程

        Args:
            stock_codes: 股票代码列表，None则使用Top股票
            market_env: 市场环境 bull/震荡/bear
            top_n: 返回数量限制
        """
        # 防止重复启动
        if self._refresh_worker and self._refresh_worker.isRunning():
            self.status_label.setText('AI数据正在计算中，请稍候...')
            return

        self.status_label.setText('正在后台计算AI决策数据...')

        # 启动后台线程
        self._refresh_worker = DashboardRefreshWorker(
            stock_codes=stock_codes,
            market_env=market_env,
            top_n=top_n,
        )
        self._refresh_worker.finished.connect(self._on_refresh_finished)
        self._refresh_worker.error.connect(self._on_refresh_error)
        self._refresh_worker.start()

    def _on_refresh_finished(self, data):
        """仪表盘刷新完成回调（主线程）"""
        try:
            # V0.7.2 显示缓存状态
            cache_info = ''
            try:
                from decision.decision_service import get_decision_service
                svc = get_decision_service()
                cs = svc.get_cache_status()
                if cs.get('expired'):
                    cache_info = '（新计算）'
                else:
                    cache_info = f'（缓存日期: {cs.get("date")}）'
            except Exception:
                pass

            if data and data.get('stocks'):
                self.update_data(data)
                count = len(data.get('stocks', []))
                self.status_label.setText(f'AI决策数据加载完成，共{count}只股票 {cache_info}')
            else:
                self.update_data([])
                self.status_label.setText(f'暂无符合条件的AI决策股票 {cache_info}')
        except Exception as e:
            self.status_label.setText(f'AI数据处理异常: {e}')
        finally:
            self._refresh_worker = None

    def _on_refresh_error(self, error_msg):
        """仪表盘刷新错误回调"""
        self.status_label.setText(f'AI决策数据加载失败: {error_msg}')
        self._refresh_worker = None
