# -*- coding: utf-8 -*-
"""
AI量化盯盘系统 V1.0 主窗口
包含：实时监控大厅、AI选股池、大盘板块分析、7×24快讯、股票详情
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QStackedWidget, QPushButton, QStatusBar, QMessageBox,
    QMenu
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.monitor_hall import MonitorHallWidget
from ui.stock_detail_v1 import StockDetailWidget
from ui.stock_pool_panel import StockPoolWidget
from ui.watchlist_panel import WatchlistWidget
from ui.news_panel import NewsPanelWidget, _load_stock_names_async
from ui.market_sentiment_panel import MarketSentimentPanel
from ui.trade_assistant_panel import TradeAssistantPanel
from ui.alarm_center_panel import AlarmCenterPanel
from decision_center import DecisionDashboard
from ui.menu_router import get_menu_router
from market.news_center import NewsCenter
from core.scan_engine import get_scan_engine
from core.watchlist import get_watchlist_manager
from utils.tdx_stock_list import get_stocks_with_quotes_tdx
from pages.chanlun_page import ChanlunPage
from pages.ai_decision_page import AIDecisionPage
from pages.backtest_center_page import BacktestCenterPage
from ui.pages.limit_up_reason_page import LimitUpReasonPage


class MainWindow(QMainWindow):
    """主窗口"""

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
    }

    def __init__(self):
        super().__init__()
        self.news_center = NewsCenter(self)
        self.news_center.news_updated.connect(self._on_news_updated)
        self.scan_engine = get_scan_engine()
        self.scan_engine.scan_progress.connect(self._on_scan_progress)
        self.scan_engine.scan_finished.connect(self._on_scan_finished)
        self.scan_engine.scan_error.connect(self._on_scan_error)

        self._auto_scan_enabled = False  # 自动扫描开关（默认关闭，手动启动）
        self._auto_scan_interval = 60000  # 自动扫描间隔1分钟

        # 菜单路由中心
        self.menu_router = get_menu_router()
        self.menu_router.set_main_window(self)

        # 独立窗口管理
        self.chanlun_window = None  # 缠论分析窗口
        self.ai_decision_window = None  # AI决策中心窗口
        self.backtest_window = None  # 回测中心窗口

        self._init_ui()
        self._setup_timers()
        _load_stock_names_async()
        QTimer.singleShot(500, self._load_news)
        # 启动后延迟10秒自动开始第一次全市场扫描（默认关闭，手动启动）
        # QTimer.singleShot(10000, self._start_auto_scan)

    def _init_ui(self):
        self.setWindowTitle('AI量化盯盘系统 V1.0')
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(f"""
            QMainWindow {{ background: {self.DARK_COLORS['bg_primary']}; }}
            QTabWidget::pane {{ border: 1px solid {self.DARK_COLORS['border']}; background: {self.DARK_COLORS['bg_primary']}; }}
            QTabBar::tab {{
                background: {self.DARK_COLORS['bg_secondary']};
                color: {self.DARK_COLORS['text_secondary']};
                padding: 8px 20px; border: none; margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {self.DARK_COLORS['bg_primary']};
                color: {self.DARK_COLORS['text_primary']};
                border-bottom: 2px solid {self.DARK_COLORS['accent']};
            }}
            QTabBar::tab:hover {{ color: {self.DARK_COLORS['text_primary']}; }}
        """)

        # 创建菜单栏
        self._create_menu_bar()

        # 中央部件
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet(f'background: {self.DARK_COLORS["bg_secondary"]}; border-bottom: 1px solid {self.DARK_COLORS["border"]};')
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 0, 12, 0)

        # 标题
        title = QLabel('📊 AI量化盯盘系统')
        title.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {self.DARK_COLORS["text_primary"]};')
        toolbar_layout.addWidget(title)

        toolbar_layout.addStretch()

        # 市场状态
        self.market_status = QLabel('市场状态: 加载中...')
        self.market_status.setStyleSheet(f'color: {self.DARK_COLORS["text_secondary"]}; font-size: 12px;')
        toolbar_layout.addWidget(self.market_status)

        toolbar_layout.addSpacing(20)

        # 时钟
        self.clock_label = QLabel('')
        self.clock_label.setStyleSheet(f'color: {self.DARK_COLORS["text_secondary"]}; font-size: 13px; font-family: Consolas;')
        toolbar_layout.addWidget(self.clock_label)

        main_layout.addWidget(toolbar)

        # 主内容区 - 使用StackedWidget切换列表/详情
        self.stacked = QStackedWidget()

        # Tab页面
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # Tab1: 实时监控大厅
        self.monitor_hall = MonitorHallWidget()
        self.monitor_hall.stock_clicked.connect(self._show_stock_detail)
        self.monitor_hall.set_scan_callback(self._start_scan)
        self.tab_widget.addTab(self.monitor_hall, '📊 实时监控')

        # Tab2: AI选股池
        self.stock_pool = StockPoolWidget()
        self.stock_pool.stock_clicked.connect(self._show_stock_detail_from_pool)
        self.tab_widget.addTab(self.stock_pool, '🎯 AI选股池')

        # Tab3: 我的自选
        self.watchlist = WatchlistWidget()
        self.watchlist.stock_clicked.connect(self._show_stock_detail)
        self.tab_widget.addTab(self.watchlist, '⭐ 我的自选')

        # Tab4: 7×24快讯
        self.news_panel = NewsPanelWidget()
        self.news_panel.set_refresh_callback(self._refresh_news)
        self.tab_widget.addTab(self.news_panel, '📰 7×24快讯')

        # Tab5: 涨停原因分析
        self.limit_up_reason_page = LimitUpReasonPage()
        self.tab_widget.addTab(self.limit_up_reason_page, '🔥 涨停原因')

        # Tab5: 市场情绪（已移除）
        # self.market_sentiment = MarketSentimentPanel()
        # self.tab_widget.addTab(self.market_sentiment, '📊 市场情绪')

        # Tab6: 交易辅助（已移除）
        # self.trade_assistant = TradeAssistantPanel()
        # self.tab_widget.addTab(self.trade_assistant, '💹 交易辅助')

        # Tab7: 预警中心（已移除）
        # self.alarm_center = AlarmCenterPanel()
        # self.tab_widget.addTab(self.alarm_center, '🔔 预警中心')

        # Tab8: 交易决策仪表盘（已移除）
        # self.trading_dashboard = DecisionDashboard()
        # self.tab_widget.addTab(self.trading_dashboard, '📈 决策中心')

        self.stacked.addWidget(self.tab_widget)

        # 股票详情页
        self.stock_detail = StockDetailWidget()
        self.stock_detail.back_clicked.connect(self._show_list)
        self.stacked.addWidget(self.stock_detail)

        main_layout.addWidget(self.stacked)

        self.setCentralWidget(central)

        # 状态栏
        self.statusBar = QStatusBar()
        self.statusBar.setStyleSheet(f'background: {self.DARK_COLORS["bg_secondary"]}; color: {self.DARK_COLORS["text_secondary"]};')
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage('就绪')

    def _setup_timers(self):
        # 时钟
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

        # 市场状态
        self.market_timer = QTimer(self)
        self.market_timer.timeout.connect(self._update_market_status)
        self.market_timer.start(60000)
        self._update_market_status()

        # 新闻自动刷新（5分钟）
        self.news_timer = QTimer(self)
        self.news_timer.timeout.connect(self._refresh_news)
        self.news_timer.start(300000)

    def _update_clock(self):
        from datetime import datetime
        now = datetime.now()
        self.clock_label.setText(now.strftime('%Y-%m-%d %H:%M:%S'))

    def _update_market_status(self):
        from datetime import datetime
        now = datetime.now()
        weekday = now.weekday()
        hour = now.hour
        minute = now.minute
        time_val = hour * 60 + minute

        if weekday >= 5:
            status = '休市（周末）'
            color = self.DARK_COLORS['text_secondary']
        elif time_val < 9 * 60 + 15:
            status = '盘前'
            color = self.DARK_COLORS['orange']
        elif 9 * 60 + 15 <= time_val < 11 * 60 + 30:
            status = '交易中（上午）'
            color = self.DARK_COLORS['green']
        elif 11 * 60 + 30 <= time_val < 13 * 60:
            status = '午间休市'
            color = self.DARK_COLORS['orange']
        elif 13 * 60 <= time_val < 15 * 60:
            status = '交易中（下午）'
            color = self.DARK_COLORS['green']
        else:
            status = '已收盘'
            color = self.DARK_COLORS['text_secondary']

        self.market_status.setText(f'市场状态: {status}')
        self.market_status.setStyleSheet(f'color: {color}; font-size: 12px; font-weight: bold;')

    def _create_menu_bar(self):
        """创建顶部菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background: {self.DARK_COLORS['bg_secondary']};
                color: {self.DARK_COLORS['text_secondary']};
                border-bottom: 1px solid {self.DARK_COLORS['border']};
                padding: 2px 8px;
                font-size: 13px;
            }}
            QMenuBar::item {{
                padding: 6px 14px;
                background: transparent;
                border-radius: 4px;
            }}
            QMenuBar::item:selected {{
                background: {self.DARK_COLORS['bg_tertiary']};
                color: {self.DARK_COLORS['text_primary']};
            }}
            QMenu {{
                background: {self.DARK_COLORS['bg_secondary']};
                color: {self.DARK_COLORS['text_secondary']};
                border: 1px solid {self.DARK_COLORS['border']};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {self.DARK_COLORS['accent']};
                color: white;
            }}
            QMenu::separator {{
                height: 1px;
                background: {self.DARK_COLORS['border']};
                margin: 4px 8px;
            }}
        """)

        # ========== 0. 决策中心菜单（已移除） ==========
        # menu_dashboard = menubar.addMenu('📈 决策中心')

        # action_dashboard = QAction('交易决策仪表盘', self)
        # action_dashboard.triggered.connect(self.menu_router.open_dashboard)
        # menu_dashboard.addAction(action_dashboard)

        # menu_dashboard.addSeparator()

        # ========== 1. 监控预警菜单（已移除） ==========
        # menu_alert = menubar.addMenu('🔔 监控预警')

        # 预警中心（已移除）
        # action_warning_center = QAction('预警中心', self)
        # action_warning_center.triggered.connect(self.menu_router.open_warning_center)
        # menu_alert.addAction(action_warning_center)

        # menu_alert.addSeparator()

        # action_price_alert = QAction('价格预警设置', self)
        # action_price_alert.triggered.connect(lambda: self._show_not_implemented('价格预警'))
        # menu_alert.addAction(action_price_alert)

        # action_speed_alert = QAction('涨速预警设置', self)
        # action_speed_alert.triggered.connect(lambda: self._show_not_implemented('涨速预警'))
        # menu_alert.addAction(action_speed_alert)

        # action_volume_alert = QAction('量比预警设置', self)
        # action_volume_alert.triggered.connect(lambda: self._show_not_implemented('量比预警'))
        # menu_alert.addAction(action_volume_alert)

        # action_limit_open_alert = QAction('涨停打开预警', self)
        # action_limit_open_alert.triggered.connect(lambda: self._show_not_implemented('涨停打开预警'))
        # menu_alert.addAction(action_limit_open_alert)

        # action_signal_alert = QAction('信号预警设置', self)
        # action_signal_alert.triggered.connect(lambda: self._show_not_implemented('信号预警'))
        # menu_alert.addAction(action_signal_alert)

        # menu_alert.addSeparator()

        # action_alert_record = QAction('预警记录', self)
        # action_alert_record.triggered.connect(lambda: self._show_not_implemented('预警记录'))
        # menu_alert.addAction(action_alert_record)

        # ========== 2. 选股复盘菜单 ==========
        menu_stock = menubar.addMenu('🎯 选股复盘')

        action_stock_pool = QAction('AI选股池', self)
        action_stock_pool.triggered.connect(self.menu_router.open_ai_stock_pool)
        menu_stock.addAction(action_stock_pool)

        action_chanlun = QAction('📿 AI缠论分析', self)
        action_chanlun.triggered.connect(self.open_chanlun_page)
        menu_stock.addAction(action_chanlun)

        action_ai_decision = QAction('🤖 AI决策中心', self)
        action_ai_decision.triggered.connect(self.open_ai_decision_page)
        menu_stock.addAction(action_ai_decision)

        action_backtest = QAction('📊 回测中心', self)
        action_backtest.triggered.connect(self.open_backtest_center)
        menu_stock.addAction(action_backtest)

        menu_stock.addSeparator()

        action_limit_up_review = QAction('涨停板复盘', self)
        action_limit_up_review.triggered.connect(lambda: self._show_not_implemented('涨停板复盘'))
        menu_stock.addAction(action_limit_up_review)

        action_sector_leader = QAction('板块龙头识别', self)
        action_sector_leader.triggered.connect(lambda: self._show_not_implemented('板块龙头识别'))
        menu_stock.addAction(action_sector_leader)

        action_strong_stock = QAction('强势股池', self)
        action_strong_stock.triggered.connect(lambda: self._show_not_implemented('强势股池'))
        menu_stock.addAction(action_strong_stock)

        action_limit_down = QAction('跌停股池', self)
        action_limit_down.triggered.connect(lambda: self._show_not_implemented('跌停股池'))
        menu_stock.addAction(action_limit_down)

        action_northbound = QAction('北向资金选股', self)
        action_northbound.triggered.connect(lambda: self._show_not_implemented('北向资金选股'))
        menu_stock.addAction(action_northbound)

        # ========== 3. 市场情绪菜单（已移除） ==========
        # menu_sentiment = menubar.addMenu('📊 市场情绪')

        # action_sentiment_dashboard = QAction('市场情绪仪表盘', self)
        # action_sentiment_dashboard.triggered.connect(self.menu_router.open_market_dashboard)
        # menu_sentiment.addAction(action_sentiment_dashboard)

        # action_sector_rank = QAction('板块涨跌排行', self)
        # action_sector_rank.triggered.connect(lambda: self._show_not_implemented('板块涨跌排行'))
        # menu_sentiment.addAction(action_sector_rank)

        # action_limit_up_ladder = QAction('连板梯队', self)
        # action_limit_up_ladder.triggered.connect(lambda: self._show_not_implemented('连板梯队'))
        # menu_sentiment.addAction(action_limit_up_ladder)

        # action_yesterday_limit = QAction('昨日涨停表现', self)
        # action_yesterday_limit.triggered.connect(lambda: self._show_not_implemented('昨日涨停表现'))
        # menu_sentiment.addAction(action_yesterday_limit)

        # ========== 4. 交易辅助菜单（已移除） ==========
        # menu_trade = menubar.addMenu('💹 交易辅助')

        # action_trade_center = QAction('交易辅助中心', self)
        # action_trade_center.triggered.connect(self.menu_router.open_trade_helper)
        # menu_trade.addAction(action_trade_center)

        # menu_trade.addSeparator()

        # action_sim_trade = QAction('模拟交易', self)
        # action_sim_trade.triggered.connect(lambda: self._show_not_implemented('模拟交易'))
        # menu_trade.addAction(action_sim_trade)

        # action_trade_log = QAction('交易日志', self)
        # action_trade_log.triggered.connect(lambda: self._show_not_implemented('交易日志'))
        # menu_trade.addAction(action_trade_log)

        # action_position_calc = QAction('仓位计算器', self)
        # action_position_calc.triggered.connect(lambda: self._show_not_implemented('仓位计算器'))
        # menu_trade.addAction(action_position_calc)

        # action_position_pnl = QAction('持仓盈亏', self)
        # action_position_pnl.triggered.connect(lambda: self._show_not_implemented('持仓盈亏'))
        # menu_trade.addAction(action_position_pnl)

        # ========== 5. 工具菜单 ==========
        menu_tools = menubar.addMenu('🔧 工具')

        action_export = QAction('数据导出', self)
        action_export.triggered.connect(lambda: self._show_not_implemented('数据导出'))
        menu_tools.addAction(action_export)

        action_settings = QAction('系统设置', self)
        action_settings.triggered.connect(lambda: self._show_not_implemented('系统设置'))
        menu_tools.addAction(action_settings)

        action_clear_cache = QAction('清空缓存', self)
        action_clear_cache.triggered.connect(lambda: self._show_not_implemented('清空缓存'))
        menu_tools.addAction(action_clear_cache)

        # ========== 6. 帮助菜单 ==========
        menu_help = menubar.addMenu('❓ 帮助')

        action_help = QAction('使用说明', self)
        action_help.triggered.connect(lambda: self._show_not_implemented('使用说明'))
        menu_help.addAction(action_help)

        action_health = QAction('🩺 系统健康检查', self)
        action_health.triggered.connect(self._show_health_check)
        menu_help.addAction(action_health)

        menu_help.addSeparator()

        action_about = QAction('关于', self)
        action_about.triggered.connect(self._show_about)
        menu_help.addAction(action_about)

    def _show_not_implemented(self, feature_name):
        """显示功能开发中提示"""
        QMessageBox.information(self, '提示', f'【{feature_name}】功能开发中，敬请期待！')

    def _show_health_check(self):
        """显示系统健康检查"""
        try:
            from ui.system_health_dialog import SystemHealthDialog
            dialog = SystemHealthDialog(self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(self, '提示', f'系统健康检查加载失败：{e}')

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, '关于 AI量化盯盘系统',
            '<h3>AI量化盯盘系统 V1.0</h3>'
            '<p>专业A股短线量化盯盘辅助软件</p>'
            '<p>技术栈：Python + PyQt6 + ECharts + 通达信行情接口</p>'
            '<p>功能：实时监控、AI选股、自选股管理、技术分析、资讯快讯</p>'
            '<hr>'
            '<p style="color: #8b949e; font-size: 12px;">© 2026 AI量化盯盘系统</p>'
        )

    def _start_scan(self):
        if self.scan_engine.is_scanning():
            return

        self.monitor_hall.set_scanning(True)
        self.statusBar.showMessage('正在获取股票列表...')

        import threading
        def _do():
            try:
                stocks = get_stocks_with_quotes_tdx(max_stocks=500)
                self.statusBar.showMessage(f'已获取{len(stocks)}只股票，开始扫描...')
                self.scan_engine.scan_market(stocks, max_stocks=500)
            except Exception as e:
                self.statusBar.showMessage(f'扫描失败: {e}')
                self.monitor_hall.set_scanning(False)

        threading.Thread(target=_do, daemon=True).start()

    def _start_auto_scan(self):
        """自动扫描入口"""
        if not self._auto_scan_enabled:
            return
        if self.scan_engine.is_scanning():
            # 如果正在扫描，5分钟后再试
            QTimer.singleShot(self._auto_scan_interval, self._start_auto_scan)
            return
        self.statusBar.showMessage('【自动扫描】正在获取股票列表...')
        self._start_scan()

    def _on_scan_progress(self, current, total):
        self.statusBar.showMessage(f'扫描进度: {current}/{total}')

    def _on_scan_finished(self, results):
        self.monitor_hall.update_stocks(results)
        self.monitor_hall.set_scanning(False)
        self.statusBar.showMessage(f'扫描完成，共{len(results)}只股票 | 自动扫描已开启，{self._auto_scan_interval//60000}分钟后自动刷新')

        # 更新预警中心（只读取数据，不修改扫描逻辑）
        try:
            if hasattr(self, 'alarm_center'):
                self.alarm_center.update_from_scan_result(results)
        except Exception as e:
            print(f"更新预警中心失败: {e}")

        # 更新自选股信号提醒
        try:
            from core.watchlist import get_watchlist_manager
            wm = get_watchlist_manager()
            watchlist_codes = set(wm.get_codes())

            # 找出有信号的自选股
            for stock in results:
                code = stock.get('code', '')
                name = stock.get('name', '')
                signals = stock.get('signal_names', [])

                if code in watchlist_codes and signals:
                    # 添加到信号提醒
                    signal_text = '、'.join(signals[:3])
                    if hasattr(self, 'watchlist') and hasattr(self.watchlist, 'add_signal_alert'):
                        self.watchlist.add_signal_alert(signal_text, code, name)
        except Exception as e:
            print(f"更新信号提醒失败: {e}")

        # 设置下一次自动扫描
        if self._auto_scan_enabled:
            QTimer.singleShot(self._auto_scan_interval, self._start_auto_scan)

    def _on_scan_error(self, error):
        self.monitor_hall.set_scanning(False)
        self.statusBar.showMessage(f'扫描错误: {error}')

    def _show_stock_detail(self, code, name):
        print(f"[CLICK STOCK] source: 主窗口, stock_code: {code}, stock_name: {name}")
        print(f"[DETAIL OPEN] code: {code}, name: {name}")
        # 从监控大厅获取股票数据
        for stock in self.monitor_hall.filtered_stocks:
            if stock['code'] == code:
                self.stock_detail.show_stock(stock)
                self.stacked.setCurrentWidget(self.stock_detail)
                return

        # 如果没找到，单独扫描
        self.statusBar.showMessage(f'正在获取{name}详情...')
        import threading
        def _do():
            result = self.scan_engine.scan_single(code, name)
            # UI操作必须放回主线程
            from PyQt6.QtCore import QTimer
            if result:
                QTimer.singleShot(0, lambda: self._show_detail_in_main(result, name))
            else:
                QTimer.singleShot(0, lambda: self.statusBar.showMessage(f'获取{name}详情失败'))

        threading.Thread(target=_do, daemon=True).start()

    def _show_stock_detail_from_pool(self, code, name):
        self._show_stock_detail(code, name)
    
    def _show_detail_in_main(self, result, name):
        """在主线程显示详情页（UI操作必须在主线程）"""
        try:
            self.stock_detail.show_stock(result)
            self.stacked.setCurrentWidget(self.stock_detail)
            self.statusBar.showMessage(f'{name} 详情已加载')
        except Exception as e:
            print(f"[主窗口] 显示详情页出错: {e}")
            import traceback
            traceback.print_exc()

    def _show_list(self):
        self.stacked.setCurrentWidget(self.tab_widget)

    def _load_news(self):
        self._refresh_news()

    def _refresh_news(self):
        self.news_center.refresh_now()

    def _on_news_updated(self, news_list):
        self.news_panel.update_news(news_list)
        self.statusBar.showMessage(f'新闻已更新，共{len(news_list)}条')

        # 计算市场情绪，设置到扫描引擎
        try:
            from strategy.sentiment_analyzer import get_sentiment_analyzer
            analyzer = get_sentiment_analyzer()
            result = analyzer.analyze_news_list(news_list)
            self.scan_engine.set_market_sentiment(result['overall_score'])
            print(f"市场情绪已更新: {result['overall_score']} ({result['overall_sentiment']})")
        except Exception as e:
            print(f"计算市场情绪失败: {e}")

    def open_chanlun_page(self):
        """打开AI缠论分析页面（独立窗口）"""
        print("[主窗口] 打开AI缠论分析页面")

        try:
            # 如果窗口已经打开，激活它
            if self.chanlun_window and self.chanlun_window.isVisible():
                self.chanlun_window.activateWindow()
                self.chanlun_window.raise_()
                return

            # 创建新窗口
            self.chanlun_window = ChanlunPage()
            self.chanlun_window.setWindowTitle('📿 AI缠论多周期分析')
            self.chanlun_window.resize(1000, 800)

            # 窗口关闭时清理引用
            self.chanlun_window.destroyed.connect(self._on_chanlun_closed)

            self.chanlun_window.show()
            print("[主窗口] 缠论分析页面已打开")

        except Exception as e:
            print(f"[主窗口] 打开缠论页面失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开缠论分析页面失败: {str(e)}')

    def _on_chanlun_closed(self):
        """缠论窗口关闭回调"""
        print("[主窗口] 缠论分析页面已关闭")
        self.chanlun_window = None

    def open_ai_decision_page(self):
        """打开AI决策中心页面（独立窗口）"""
        print("[主窗口] 打开AI决策中心页面")

        try:
            # 如果窗口已经打开，激活它
            if self.ai_decision_window and self.ai_decision_window.isVisible():
                self.ai_decision_window.activateWindow()
                self.ai_decision_window.raise_()
                return

            # 创建新窗口
            self.ai_decision_window = AIDecisionPage()
            self.ai_decision_window.setWindowTitle('🤖 AI决策中心')
            self.ai_decision_window.resize(1000, 800)

            # 窗口关闭时清理引用
            self.ai_decision_window.destroyed.connect(self._on_ai_decision_closed)

            self.ai_decision_window.show()
            print("[主窗口] AI决策中心页面已打开")

        except Exception as e:
            print(f"[主窗口] 打开AI决策中心失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开AI决策中心失败: {str(e)}')

    def _on_ai_decision_closed(self):
        """AI决策中心窗口关闭回调"""
        print("[主窗口] AI决策中心页面已关闭")
        self.ai_decision_window = None

    def open_backtest_center(self):
        """打开回测中心页面（独立窗口）"""
        print("[主窗口] 打开回测中心页面")

        try:
            # 如果窗口已经打开，激活它
            if self.backtest_window and self.backtest_window.isVisible():
                self.backtest_window.activateWindow()
                self.backtest_window.raise_()
                return

            # 创建新窗口
            self.backtest_window = BacktestCenterPage()
            self.backtest_window.setWindowTitle('📊 回测中心')
            self.backtest_window.resize(1000, 700)

            # 窗口关闭时清理引用
            self.backtest_window.destroyed.connect(self._on_backtest_closed)

            self.backtest_window.show()
            print("[主窗口] 回测中心页面已打开")

        except Exception as e:
            print(f"[主窗口] 打开回测中心失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开回测中心失败: {str(e)}')

    def _on_backtest_closed(self):
        """回测中心窗口关闭回调"""
        print("[主窗口] 回测中心页面已关闭")
        self.backtest_window = None

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, '确认退出',
            '确定要退出AI量化盯盘系统吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.scan_engine.is_scanning():
                self.scan_engine.stop()
            event.accept()
        else:
            event.ignore()
