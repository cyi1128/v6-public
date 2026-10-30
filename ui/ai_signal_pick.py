"""
AI量化选股结果页面
显示：股票列表 + 信号标签 + AI评分 + 详情分析
专业交易工作台风格
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLineEdit, QSplitter, QTextEdit, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import requests
import json

from strategy.ai_signal_engine import AISignalEngine
from strategy.watchlist_manager import get_watchlist_manager
from strategy.stock_pool_filter import get_stock_pool_filter
from strategy.multi_strategy_filter import Strategy2Filter, Strategy3Filter
from strategy.wencai_filter import get_wencai_filter
from utils.kline_provider import get_daily_kline


class ScanWorker(QThread):
    """扫描工作线程"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, stock_list=None):
        super().__init__()
        self.stock_list = stock_list
        self.engine = AISignalEngine()

    def run(self):
        try:
            results = []
            if self.stock_list:
                stocks = self.stock_list
            else:
                # 获取全市场股票（涨幅前100）
                stocks = self._get_market_stocks()

            for stock in stocks[:50]:  # 限制扫描数量
                try:
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    change = stock.get('change', 0)

                    # 获取日线数据
                    daily_data = self._get_daily_data(code)
                    if daily_data and len(daily_data) >= 30:
                        analysis = self.engine.analyze(daily_data)
                        if analysis['signals']:
                            results.append({
                                'code': code,
                                'name': name,
                                'price': price,
                                'change': change,
                                'signals': analysis['signals'],
                                'total_score': analysis['total_score'],
                                'rating': analysis['rating'],
                                'analysis': analysis['analysis'],
                                'daily_data': daily_data,
                            })
                except Exception:
                    continue

            # 按评分排序
            results.sort(key=lambda x: x['total_score'], reverse=True)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _get_market_stocks(self):
        """获取全市场股票（通达信行情）"""
        try:
            from utils.tdx_stock_list import get_stocks_with_quotes_tdx
            return get_stocks_with_quotes_tdx(max_stocks=300)
        except Exception:
            return []

    def _get_daily_data(self, code):
        """获取日线数据"""
        return get_daily_kline(code, 80)


class WencaiWorker(QThread):
    """问财选股工作线程"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query
        self.engine = AISignalEngine()
        self.wencai = get_wencai_filter()

    def run(self):
        try:
            # 第一步：问财选股
            stocks = self.wencai.query(self.query, perpage=50)

            if not stocks:
                self.finished.emit([])
                return

            # 第二步：对选出的股票进行AI信号分析
            results = []
            for stock in stocks[:30]:  # 限制分析数量
                try:
                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    change = stock.get('change', 0)

                    daily_data = get_daily_kline(code, 80)
                    if daily_data and len(daily_data) >= 30:
                        analysis = self.engine.analyze(daily_data)
                        results.append({
                            'code': code,
                            'name': name,
                            'price': price,
                            'change': change,
                            'signals': analysis['signals'],
                            'total_score': analysis['total_score'],
                            'rating': analysis['rating'],
                            'analysis': analysis['analysis'],
                            'daily_data': daily_data,
                        })
                    else:
                        # 无K线数据也显示
                        results.append({
                            'code': code,
                            'name': name,
                            'price': price,
                            'change': change,
                            'signals': [],
                            'total_score': 0,
                            'rating': '无数据',
                            'analysis': '问财选股结果',
                            'daily_data': [],
                        })
                except Exception:
                    continue

            # 按评分排序
            results.sort(key=lambda x: x['total_score'], reverse=True)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PoolScanWorker(QThread):
    """选股池扫描工作线程：先按8个条件筛选，再进行AI信号分析"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 当前进度, 总数

    def __init__(self):
        super().__init__()
        self.engine = AISignalEngine()
        self.pool_filter = get_stock_pool_filter()

    def run(self):
        try:
            # 第一步：选股池筛选
            filtered_stocks = self.pool_filter.filter_with_enrichment(max_stocks=150)

            if not filtered_stocks:
                self.finished.emit([])
                return

            # 第二步：对筛选出的股票进行AI信号分析
            results = []
            total = len(filtered_stocks)
            for i, stock in enumerate(filtered_stocks):
                try:
                    self.progress.emit(i + 1, total)

                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    change = stock.get('change', 0)

                    # 获取日线数据
                    daily_data = self._get_daily_data(code)
                    if daily_data and len(daily_data) >= 30:
                        analysis = self.engine.analyze(daily_data)
                        if analysis['signals']:
                            results.append({
                                'code': code,
                                'name': name,
                                'price': price,
                                'change': change,
                                'signals': analysis['signals'],
                                'total_score': analysis['total_score'],
                                'rating': analysis['rating'],
                                'analysis': analysis['analysis'],
                                'daily_data': daily_data,
                                'market_cap': stock.get('market_cap', 0),
                                'industry': stock.get('industry', ''),
                            })
                except Exception:
                    continue

            # 按评分排序
            results.sort(key=lambda x: x['total_score'], reverse=True)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _get_daily_data(self, code):
        """获取日线数据"""
        return get_daily_kline(code, 80)


class MultiStrategyScanWorker(QThread):
    """多策略扫描工作线程（策略2/3）"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, strategy_type=2):
        super().__init__()
        self.strategy_type = strategy_type
        self.engine = AISignalEngine()
        self.strategy2 = Strategy2Filter()
        self.strategy3 = Strategy3Filter()

    def run(self):
        try:
            # 第一步：按策略筛选股票
            if self.strategy_type == 2:
                filtered_stocks = self.strategy2.filter_stocks(max_stocks=150)
            else:
                filtered_stocks = self.strategy3.filter_stocks(max_stocks=150)

            if not filtered_stocks:
                self.finished.emit([])
                return

            # 第二步：对筛选出的股票进行AI信号分析
            results = []
            total = len(filtered_stocks)
            for i, stock in enumerate(filtered_stocks):
                try:
                    self.progress.emit(i + 1, total)

                    code = stock.get('code', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    change = stock.get('change', 0)

                    daily_data = self._get_daily_data(code)
                    if daily_data and len(daily_data) >= 30:
                        analysis = self.engine.analyze(daily_data)
                        results.append({
                            'code': code,
                            'name': name,
                            'price': price,
                            'change': change,
                            'signals': analysis['signals'],
                            'total_score': analysis['total_score'],
                            'rating': analysis['rating'],
                            'analysis': analysis['analysis'],
                            'daily_data': daily_data,
                            'strategy': f'策略{self.strategy_type}',
                        })
                except Exception:
                    continue

            results.sort(key=lambda x: x['total_score'], reverse=True)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _get_daily_data(self, code):
        """获取日线数据（优先通达信）"""
        return get_daily_kline(code, 80)


class AISignalPickWidget(QWidget):
    """AI信号选股页面"""

    DARK_COLORS = {
        'bg_primary': '#0d1117', 'bg_secondary': '#161b22',
        'bg_tertiary': '#21262d', 'border': '#30363d',
        'text_primary': '#f0f6fc', 'text_secondary': '#8b949e',
        'accent': '#58a6ff', 'red': '#f85149', 'green': '#3fb950',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = AISignalEngine()
        self.watchlist = get_watchlist_manager()
        self.current_stock = None
        self.scan_worker = None
        self.wencai_worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 顶部工具栏
        layout.addWidget(self._create_toolbar())

        # 问财选股行
        layout.addWidget(self._create_wencai_bar())

        # 主内容：左侧股票列表 + 右侧详情
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧股票列表
        splitter.addWidget(self._create_stock_list())

        # 右侧详情分析
        splitter.addWidget(self._create_detail_panel())

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def _create_toolbar(self):
        """创建顶部工具栏"""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(10)

        # 标题
        title = QLabel('🎯 AI量化选股')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 策略选择
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([
            '策略1: 11信号识别',
            '策略2: 趋势回踩',
            '策略3: 突破放量',
        ])
        self.strategy_combo.setFixedHeight(32)
        self.strategy_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
        """)
        layout.addWidget(self.strategy_combo)

        layout.addSpacing(20)

        # 手动输入股票
        self.stock_input = QLineEdit()
        self.stock_input.setPlaceholderText('输入股票代码（如000001）')
        self.stock_input.setFixedWidth(180)
        self.stock_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.stock_input)

        # 分析按钮
        analyze_btn = QPushButton('🔍 分析')
        analyze_btn.setFixedHeight(32)
        analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        analyze_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.DARK_COLORS['accent']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #1f6feb; }}
        """)
        analyze_btn.clicked.connect(self._analyze_single_stock)
        layout.addWidget(analyze_btn)

        layout.addStretch()

        # 扫描全市场按钮
        self.scan_btn = QPushButton('🚀 扫描全市场')
        self.scan_btn.setFixedHeight(32)
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #238636;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #2ea043; }}
        """)
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        # 选股池按钮
        self.pool_btn = QPushButton('📊 选股池')
        self.pool_btn.setFixedHeight(32)
        self.pool_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pool_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #d29922;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #e3b341; }}
        """)
        self.pool_btn.clicked.connect(self._start_pool_scan)
        layout.addWidget(self.pool_btn)

        # 加入自选按钮
        self.add_watchlist_btn = QPushButton('⭐ 加入自选')
        self.add_watchlist_btn.setFixedHeight(32)
        self.add_watchlist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_watchlist_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {self.DARK_COLORS['border']}; }}
        """)
        self.add_watchlist_btn.clicked.connect(self._add_to_watchlist)
        layout.addWidget(self.add_watchlist_btn)

        return bar

    def _create_wencai_bar(self):
        """创建问财选股栏"""
        bar = QFrame()
        bar.setFixedHeight(45)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 6, 15, 6)
        layout.setSpacing(10)

        # 问财图标和标题
        title = QLabel('🤖 问财选股')
        title.setStyleSheet(f"color: #d29922; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        # 问财输入框
        self.wencai_input = QLineEdit()
        self.wencai_input.setPlaceholderText('输入自然语言选股条件，如：今日涨停、市值50-200亿非ST主板')
        self.wencai_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
        """)
        self.wencai_input.returnPressed.connect(self._start_wencai_query)
        layout.addWidget(self.wencai_input, 1)

        # 问财查询按钮
        wencai_btn = QPushButton('🔍 问财查询')
        wencai_btn.setFixedHeight(32)
        wencai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        wencai_btn.setStyleSheet("""
            QPushButton {
                background-color: #d29922;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e3b341; }
        """)
        wencai_btn.clicked.connect(self._start_wencai_query)
        layout.addWidget(wencai_btn)

        # 常用查询快捷按钮
        quick_queries = ['今日涨停', '连续3天上涨', '放量突破', '主力资金流入']
        for q in quick_queries:
            btn = QPushButton(q)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.DARK_COLORS['bg_tertiary']};
                    color: {self.DARK_COLORS['text_secondary']};
                    border: 1px solid {self.DARK_COLORS['border']};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ color: {self.DARK_COLORS['text_primary']}; border-color: #d29922; }}
            """)
            btn.clicked.connect(lambda checked, q=q: self._quick_wencai_query(q))
            layout.addWidget(btn)

        return bar

    def _create_stock_list(self):
        """创建股票列表"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel('📋 选股结果')
        title.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(6)
        self.stock_table.setHorizontalHeaderLabels(['股票', '代码', '现价', '涨幅', '信号', 'AI评分'])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stock_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: none;
                gridline-color: {self.DARK_COLORS['border']};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_secondary']};
                border: none;
                padding: 6px;
            }}
        """)
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.stock_table.cellClicked.connect(self._on_stock_selected)
        layout.addWidget(self.stock_table, 1)

        return frame

    def _create_detail_panel(self):
        """创建详情分析面板"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.DARK_COLORS['bg_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 股票信息头部
        self.detail_header = QLabel('选择股票查看详情')
        self.detail_header.setStyleSheet(f"color: {self.DARK_COLORS['text_primary']}; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.detail_header)

        # 评分和评级
        self.rating_label = QLabel('')
        self.rating_label.setStyleSheet(f"color: {self.DARK_COLORS['accent']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.rating_label)

        # 信号标签
        self.signals_label = QLabel('')
        self.signals_label.setWordWrap(True)
        self.signals_label.setStyleSheet(f"color: {self.DARK_COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.signals_label)

        # AI分析理由
        layout.addWidget(QLabel('📊 AI分析理由：'))
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 4px;
                font-size: 12px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.analysis_text, 1)

        return frame

    def _start_scan(self):
        """开始扫描（根据选择的策略）"""
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.information(self, '提示', '扫描正在进行中...')
            return

        strategy_idx = self.strategy_combo.currentIndex()
        self.scan_btn.setText('扫描中...')
        self.scan_btn.setEnabled(False)
        self.stock_table.setRowCount(0)

        if strategy_idx == 0:
            # 策略1：11信号识别（全市场涨幅前100）
            self.scan_worker = ScanWorker()
        else:
            # 策略2/3：多策略筛选
            strategy_type = 2 if strategy_idx == 1 else 3
            self.scan_worker = MultiStrategyScanWorker(strategy_type)
            self.scan_worker.progress.connect(self._on_scan_progress)

        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_progress(self, current, total):
        """扫描进度"""
        self.scan_btn.setText(f'分析中 {current}/{total}')

    def _start_pool_scan(self):
        """开始选股池扫描"""
        if hasattr(self, 'pool_worker') and self.pool_worker and self.pool_worker.isRunning():
            QMessageBox.information(self, '提示', '选股池扫描正在进行中...')
            return

        self.pool_btn.setText('筛选中...')
        self.pool_btn.setEnabled(False)
        self.stock_table.setRowCount(0)

        self.pool_worker = PoolScanWorker()
        self.pool_worker.finished.connect(self._on_pool_scan_finished)
        self.pool_worker.error.connect(self._on_pool_scan_error)
        self.pool_worker.progress.connect(self._on_pool_progress)
        self.pool_worker.start()

    def _on_pool_progress(self, current, total):
        """选股池扫描进度"""
        self.pool_btn.setText(f'分析中 {current}/{total}')

    def _on_pool_scan_finished(self, results):
        """选股池扫描完成"""
        self.pool_btn.setText('📊 选股池')
        self.pool_btn.setEnabled(True)

        # 复用扫描完成的显示逻辑
        self._on_scan_finished(results)

        if not results:
            QMessageBox.information(self, '提示', '选股池筛选完成，未发现符合信号的股票')

    def _on_pool_scan_error(self, error_msg):
        """选股池扫描出错"""
        self.pool_btn.setText('📊 选股池')
        self.pool_btn.setEnabled(True)
        QMessageBox.warning(self, '错误', f'选股池扫描失败: {error_msg}')

    def _quick_wencai_query(self, query):
        """快捷问财查询"""
        self.wencai_input.setText(query)
        self._start_wencai_query()

    def _start_wencai_query(self):
        """开始问财选股"""
        query = self.wencai_input.text().strip()
        if not query:
            QMessageBox.information(self, '提示', '请输入选股条件')
            return

        if self.wencai_worker and self.wencai_worker.isRunning():
            QMessageBox.information(self, '提示', '问财查询正在进行中...')
            return

        self.stock_table.setRowCount(0)
        self.wencai_worker = WencaiWorker(query)
        self.wencai_worker.finished.connect(self._on_wencai_finished)
        self.wencai_worker.error.connect(self._on_wencai_error)
        self.wencai_worker.start()

    def _on_wencai_finished(self, results):
        """问财查询完成"""
        # 复用扫描完成的显示逻辑
        self._on_scan_finished(results)

        if not results:
            QMessageBox.information(self, '提示', '问财选股完成，未找到符合条件的股票')

    def _on_wencai_error(self, error_msg):
        """问财查询出错"""
        QMessageBox.warning(self, '错误', f'问财选股失败: {error_msg}')

    def _on_scan_finished(self, results):
        """扫描完成"""
        self.scan_btn.setText('🚀 扫描全市场')
        self.scan_btn.setEnabled(True)

        self.stock_table.setRowCount(len(results))
        for i, stock in enumerate(results):
            # 股票名称
            name_item = QTableWidgetItem(stock['name'])
            name_item.setForeground(QColor(self.DARK_COLORS['text_primary']))
            self.stock_table.setItem(i, 0, name_item)

            # 代码
            code_item = QTableWidgetItem(stock['code'])
            code_item.setForeground(QColor(self.DARK_COLORS['text_secondary']))
            self.stock_table.setItem(i, 1, code_item)

            # 现价
            price_item = QTableWidgetItem(str(stock['price']))
            self.stock_table.setItem(i, 2, price_item)

            # 涨幅
            change = stock['change']
            change_item = QTableWidgetItem(f"{change:.2f}%")
            change_item.setForeground(QColor('#f85149' if change >= 0 else '#3fb950'))
            self.stock_table.setItem(i, 3, change_item)

            # 信号（显示前2个）
            signal_names = [s['name'] for s in stock['signals'][:2]]
            signal_text = '、'.join(signal_names)
            signal_item = QTableWidgetItem(signal_text)
            if stock['signals']:
                signal_item.setForeground(QColor(stock['signals'][0]['color']))
            self.stock_table.setItem(i, 4, signal_item)

            # AI评分
            score_item = QTableWidgetItem(str(stock['total_score']))
            score_color = '#ff1744' if stock['total_score'] >= 90 else \
                          '#00e676' if stock['total_score'] >= 75 else \
                          '#ffea00' if stock['total_score'] >= 60 else '#757575'
            score_item.setForeground(QColor(score_color))
            self.stock_table.setItem(i, 5, score_item)

        # 保存结果
        self.scan_results = results

        if not results:
            QMessageBox.information(self, '提示', '扫描完成，未找到符合条件的股票')

    def update_realtime_prices(self, quotes):
        """实时更新扫描结果中的股票价格"""
        if not hasattr(self, 'scan_results') or not self.scan_results or not quotes:
            return

        try:
            quote_dict = {}
            for q in quotes:
                code = q.get('ts_code', q.get('code', ''))
                if code:
                    quote_dict[code] = q

            for i, stock in enumerate(self.scan_results):
                code = stock.get('code', '')
                if code in quote_dict:
                    q = quote_dict[code]
                    new_price = q.get('price', stock['price'])
                    new_change = q.get('pct_chg', q.get('change', stock['change']))

                    # 更新数据
                    stock['price'] = new_price
                    stock['change'] = new_change

                    # 更新表格
                    if i < self.stock_table.rowCount():
                        price_item = self.stock_table.item(i, 2)
                        if price_item:
                            price_item.setText(f"{new_price:.2f}")

                        change_item = self.stock_table.item(i, 3)
                        if change_item:
                            change_item.setText(f"{new_change:.2f}%")
                            change_item.setForeground(QColor('#f85149' if new_change >= 0 else '#3fb950'))
        except Exception:
            pass

    def _on_scan_error(self, error_msg):
        """扫描出错"""
        self.scan_btn.setText('🚀 扫描全市场')
        self.scan_btn.setEnabled(True)
        QMessageBox.warning(self, '错误', f'扫描失败: {error_msg}')

    def _on_stock_selected(self, row, col):
        """选中股票"""
        if not hasattr(self, 'scan_results') or row >= len(self.scan_results):
            return

        stock = self.scan_results[row]
        self.current_stock = stock

        # 更新详情
        self.detail_header.setText(f"{stock['name']} ({stock['code']})")
        self.rating_label.setText(f"AI评分: {stock['total_score']}分 | 评级: {stock['rating']}")

        # 信号标签
        signal_html = ' '.join([
            f'<span style="color: {s["color"]}; font-weight: bold;">【{s["name"]}】</span>'
            for s in stock['signals']
        ])
        self.signals_label.setText(signal_html)

        # 分析理由
        self.analysis_text.setPlainText(stock['analysis'])

    def _analyze_single_stock(self):
        """分析单只股票"""
        code = self.stock_input.text().strip()
        if not code:
            QMessageBox.information(self, '提示', '请输入股票代码')
            return

        # 获取股票名称
        try:
            market = 'sh' if code.startswith(('6', '9')) else 'sz'
            url = f'https://qt.gtimg.cn/q={market}{code}'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')
            name = parts[1]
            price = float(parts[3])
            change = float(parts[32])
        except Exception:
            name = code
            price = 0
            change = 0

        # 获取日线数据并分析
        self.scan_btn.setText('分析中...')
        self.scan_btn.setEnabled(False)

        worker = ScanWorker([{'code': code, 'name': name, 'price': price, 'change': change}])
        worker.finished.connect(self._on_single_analyze_finished)
        worker.start()

    def _on_single_analyze_finished(self, results):
        """单只股票分析完成"""
        self.scan_btn.setText('🚀 扫描全市场')
        self.scan_btn.setEnabled(True)

        if results:
            self.scan_results = results
            self._on_scan_finished(results)
            # 自动选中第一行
            if results:
                self._on_stock_selected(0, 0)
        else:
            QMessageBox.information(self, '提示', '未发现明显信号')

    def _add_to_watchlist(self):
        """加入自选股"""
        if not self.current_stock:
            QMessageBox.information(self, '提示', '请先选择股票')
            return

        code = self.current_stock['code']
        name = self.current_stock['name']

        try:
            self.watchlist.add_stock(code, name)
            QMessageBox.information(self, '成功', f'{name}({code})已加入自选股')
        except Exception as e:
            QMessageBox.warning(self, '错误', f'添加失败: {e}')
