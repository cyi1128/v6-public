# -*- coding: utf-8 -*-
"""
AI量化盯盘系统 V1.0 主窗口
包含：实时监控大厅、AI选股池、大盘板块分析、7×24快讯、股票详情
"""
import os
import json

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QStackedWidget, QPushButton, QStatusBar, QMessageBox,
    QMenu, QFrame
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ui.monitor_hall import MonitorHallWidget
from ui.stock_detail_v1 import StockDetailWidget
from ui.watchlist_panel import WatchlistWidget
from ui.news_panel import NewsPanelWidget, _load_stock_names_async
from ui.market_sentiment_panel import MarketSentimentPanel
from ui.trade_assistant_panel import TradeAssistantPanel
from ui.alarm_center_panel import AlarmCenterPanel
from ui.components.sidebar import Sidebar
from ui.components.top_bar import TopBar
from decision_center import DecisionDashboard
from ui.menu_router import get_menu_router
from market.news_center import NewsCenter
from core.scan_engine import get_scan_engine
from core.watchlist import get_watchlist_manager
from utils.tdx_stock_list import get_full_market_quotes
from pages.ai_decision_page import AIDecisionPage
from ui.stock_backtest_window import StockBacktestWindow
from pages.backtest_center_page import BacktestCenterPage
from pages.ai_decision_center_tab import AIDecisionCenterTab
# from ui.pages.limit_up_reason_page import LimitUpReasonPage  # 涨停原因功能已移除


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
        self.backtest_window = None  # 股票回测窗口
        self.ai_decision_window = None  # AI决策中心窗口
        self.backtest_window = None  # 回测中心窗口
        self.v74_window = None  # V7.4精准买点窗口
        # V7.4回退：已删除V8.0 AI交易大脑窗口

        self._init_ui()
        self._setup_timers()
        _load_stock_names_async()
        QTimer.singleShot(500, self._load_news)
        # 收盘总结：仅在15:05之后后台生成一次并自动推送企业微信
        self._close_summary_last_date = None
        self.close_summary_timer = QTimer(self)
        self.close_summary_timer.timeout.connect(self._check_close_summary)
        self.close_summary_timer.start(30000)
        QTimer.singleShot(5000, self._check_close_summary)
        # 启动后延迟10秒自动开始第一次全市场扫描（默认关闭，手动启动）
        # QTimer.singleShot(10000, self._start_auto_scan)
        # V1.2.4：启动后延迟3秒后台静默预加载强势主力行为选股（仅交易时段）
        QTimer.singleShot(3000, self._preload_force_behavior)

    def _preload_force_behavior(self):
        """V1.2.4：后台静默预加载强势主力行为选股（V1.3增加通达信本地K线预加载）"""
        try:
            # V1.3：第一步 - 通达信本地K线预加载到内存（如果可用）
            try:
                from data.tdx_data_engine import get_tdx_data_engine
                tdx_engine = get_tdx_data_engine()
                if tdx_engine and tdx_engine.is_available():
                    print("[PRELOAD] V1.3 通达信本地数据可用，开始预加载K线到内存...", flush=True)
                    import threading
                    def _tdx_preload():
                        try:
                            codes = tdx_engine.get_all_main_board_codes()
                            if codes:
                                result = tdx_engine.preload_to_memory(codes, days=120, max_workers=8)
                                print(f"[PRELOAD] 通达信K线预加载完成: {result['success']}/{result['total']}只, "
                                      f"耗时{result['elapsed_seconds']}秒", flush=True)
                        except Exception as e:
                            print(f"[PRELOAD] 通达信K线预加载异常: {e}", flush=True)
                    tdx_thread = threading.Thread(target=_tdx_preload, daemon=True)
                    tdx_thread.start()
                    # 等待通达信预加载完成（最多等30秒）
                    tdx_thread.join(timeout=30)
            except Exception as e:
                print(f"[PRELOAD] 通达信预加载初始化失败: {e}", flush=True)

            from strategy.scan_cache_manager import ScanCacheManager
            # 检查是否为交易时段
            if not ScanCacheManager.is_trading_time():
                print("[PRELOAD] 非交易时段，跳过完整扫描预加载", flush=True)
                return
            # 检查是否已有有效缓存
            from strategy.main_force_behavior import ForceBehaviorStrategy
            strategy = ForceBehaviorStrategy.instance()
            info = strategy.get_cache_info()
            if info.get('exists') and '有效' in info.get('status', ''):
                print(f"[PRELOAD] 已有有效缓存({info.get('result_count', 0)}只)，跳过预加载", flush=True)
                return
            # 启动后台线程预加载
            import threading
            def _do_preload():
                try:
                    print("[PRELOAD] 开始后台预加载强势主力行为选股...", flush=True)
                    # 设置数据提供者
                    from market.data_provider import get_data_provider
                    strategy.set_data_provider(get_data_provider())
                    strategy.quick_scan()
                except Exception as e:
                    print(f"[PRELOAD] 预加载异常: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
            t = threading.Thread(target=_do_preload, daemon=True)
            t.start()
        except Exception as e:
            print(f"[PRELOAD] 启动预加载失败: {e}", flush=True)

    def _init_ui(self):
        self.setWindowTitle('AI量化盯盘系统 V6.0 Pro')
        self.setMinimumSize(1280, 820)
        self.setStyleSheet('''
            QMainWindow {
                background: #0b0f14;
                color: #edf2f7;
            }
            QWidget {
                color: #edf2f7;
                background: transparent;
            }
            QLabel {
                color: #edf2f7;
            }
            QFrame {
                border: 1px solid #2a3342;
            }
            QStackedWidget {
                background: #0d141d;
                border-left: 1px solid #2a3342;
            }
            QStatusBar {
                background: #0d1117;
                color: #9aa9b5;
                border-top: 1px solid #2a3342;
            }
            QToolBar {
                background: #111b27;
                border: 1px solid #2a3342;
                border-radius: 8px;
            }
            QPushButton {
                background: #1a2331;
                color: #edf2f7;
                border: 1px solid #2a3342;
                border-radius: 6px;
                padding: 6px 10px;
                min-height: 28px;
            }
            QPushButton:hover {
                background: #212d3d;
                border-color: #5aa9ff;
            }
            QPushButton:pressed {
                background: #162230;
            }
            QTableWidget, QTableView {
                background: #101821;
                color: #edf2f7;
                gridline-color: #2a3342;
                alternate-background-color: #121d2a;
                selection-background-color: rgba(90, 169, 255, 0.22);
                selection-color: #edf2f7;
                border: 1px solid #2a3342;
                border-radius: 8px;
            }
            QHeaderView::section {
                background: #151e2a;
                color: #9aa9b5;
                border: 1px solid #2a3342;
                padding: 6px 8px;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #3a4658;
                border-radius: 4px;
                min-height: 32px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        ''')

        # 创建菜单栏
        self._create_menu_bar()

        # 中央部件
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 顶部行情栏 =====
        self.top_bar = TopBar()
        self.top_bar.settings_clicked.connect(self._open_settings)
        self.top_bar.backup_clicked.connect(self._run_backup)
        self.top_bar.restore_clicked.connect(self._run_restore)
        main_layout.addWidget(self.top_bar)

        # ===== 主体区域：左侧导航 + 中央工作区 =====
        body = QWidget()
        body.setObjectName('mainBody')
        body.setStyleSheet('''
            QWidget#mainBody {
                background: #0d141d;
                border: 1px solid #2a3342;
                border-top: none;
                border-radius: 0px;
            }
        ''')
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 左侧导航栏
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._navigate)
        body_layout.addWidget(self.sidebar)

        # 中央工作区（StackedWidget）
        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet('''
            QStackedWidget {
                background: #101821;
                border-left: 1px solid #2a3342;
            }
        ''')

        # 页面1: 实时监控大厅
        self.monitor_hall = MonitorHallWidget()
        self.monitor_hall.stock_clicked.connect(self._show_stock_detail)
        self.monitor_hall.set_scan_callback(self._start_scan)
        self.stacked.addWidget(self.monitor_hall)

        # 页面2: 我的自选
        self.watchlist = WatchlistWidget()
        self.watchlist.stock_clicked.connect(self._show_stock_detail)
        self.stacked.addWidget(self.watchlist)

        # 页面3: 7×24快讯
        self.news_panel = NewsPanelWidget()
        self.news_panel.set_refresh_callback(self._refresh_news)
        self.stacked.addWidget(self.news_panel)

        # 页面4: AI决策中心
        self.ai_decision_center_tab = AIDecisionCenterTab()
        self.ai_decision_center_tab.stock_selected.connect(self._show_stock_detail)
        self.stacked.addWidget(self.ai_decision_center_tab)

        # 页面5: 股票详情
        self.stock_detail = StockDetailWidget()
        self.stock_detail.back_clicked.connect(self._show_list)
        self.stacked.addWidget(self.stock_detail)

        body_layout.addWidget(self.stacked, 1)
        main_layout.addWidget(body, 1)

        self.setCentralWidget(central)

        # ===== 构建导航菜单 =====
        self._build_nav_menu()

        # 默认显示实时监控
        self.sidebar.set_current_page('monitor')
        self.stacked.setCurrentIndex(0)

        # 状态栏
        self.statusBar = QStatusBar()
        self.statusBar.setSizeGripEnabled(False)
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage('就绪')

        # 兼容旧代码：保留clock_label和market_status引用
        self.clock_label = self.top_bar.clock_label
        self.market_status = self.top_bar.market_status_label
        self.market_indicator = self.top_bar.market_status_dot
        self.ai_indicator = self.top_bar.ai_status_dot

    def _build_nav_menu(self):
        """构建左侧导航菜单"""
        # 监控组
        g_monitor = self.sidebar.add_group('监控中心')
        self.sidebar.add_nav_item(g_monitor, '📊', '实时监控', 'monitor')
        self.sidebar.add_nav_item(g_monitor, '📡', 'AI实时监控', 'ai_monitor')

        # 选股组
        g_screen = self.sidebar.add_group('选股复盘')
        self.sidebar.add_nav_item(g_screen, '⭐', '我的自选', 'watchlist')

        # AI中心组（已整合到实时监控大厅，隐藏独立入口）
        # g_ai = self.sidebar.add_group('AI决策')
        # self.sidebar.add_nav_item(g_ai, '🤖', 'AI决策中心', 'ai_decision')

        # 资讯组
        g_news = self.sidebar.add_group('资讯数据')
        self.sidebar.add_nav_item(g_news, '📰', '7×24快讯', 'news')

        # 页面ID到stacked index的映射
        self._page_map = {
            'monitor': 0,
            'watchlist': 1,
            'news': 2,
            'ai_decision': 3,
        }
        self._last_list_page = 'monitor'  # 记录最后一个列表页面

    def _navigate(self, page_id: str):
        """导航切换页面"""
        if page_id in self._page_map:
            idx = self._page_map[page_id]
            self.stacked.setCurrentIndex(idx)
            self._last_list_page = page_id
        elif page_id == 'ai_monitor':
            # AI实时监控 -> 切换到实时监控页面
            self.sidebar.set_current_page('monitor')
            self.stacked.setCurrentIndex(0)
            self._last_list_page = 'monitor'

    def _open_settings(self):
        """打开设置对话框"""
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    def _run_backup(self):
        """点击[备份]：调用 scripts/backup.py 并弹窗显示结果"""
        import subprocess, sys, os
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'backup.py')
        try:
            result = subprocess.run([sys.executable, script], capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=300)
            msg = (result.stdout or result.stderr or '').strip()
            ok = result.returncode == 0
        except Exception as e:
            msg = str(e)
            ok = False
        if ok:
            QMessageBox.information(self, '备份', msg or '备份完成')
        else:
            QMessageBox.warning(self, '备份失败', msg or '未知错误')

    def _run_restore(self):
        """点击[回滚]：列出备份供选择，确认后恢复并弹窗显示结果"""
        import subprocess, sys, os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(base, 'scripts', 'restore.py')
        try:
            result = subprocess.run([sys.executable, script, '--list'], capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=60)
            choices = [x for x in (result.stdout or '').splitlines() if x.strip()]
            if result.returncode != 0 or not choices:
                QMessageBox.warning(self, '回滚', '未找到任何备份，请先点击[备份]。')
                return
            from PyQt6.QtWidgets import QInputDialog
            item, okbtn = QInputDialog.getItem(self, '选择备份', '要恢复哪个备份？', choices, 0, False)
            if not okbtn or not item:
                return
            num = item.split('.', 1)[0].strip()
            r2 = subprocess.run([sys.executable, script, '--pick', num, '--yes'],
                                capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=600)
            msg = (r2.stdout or r2.stderr or '').strip()
            if r2.returncode == 0:
                QMessageBox.information(self, '回滚', msg or '恢复完成，请重启程序')
            else:
                QMessageBox.warning(self, '回滚失败', msg or '未知错误')
        except Exception as e:
            QMessageBox.warning(self, '回滚', '操作失败：' + str(e))

    def _setup_timers(self):
        # 时钟已由TopBar组件自行管理，避免重复更新导致跳动
        # self.clock_timer = QTimer(self)
        # self.clock_timer.timeout.connect(self._update_clock)
        # self.clock_timer.start(1000)
        # self._update_clock()

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
            status = '休市'
            color = '#5C6470'
            indicator_color = '#5C6470'
        elif time_val < 9 * 60 + 15:
            status = '盘前'
            color = '#FFD700'
            indicator_color = '#FFD700'
        elif 9 * 60 + 15 <= time_val < 11 * 60 + 30:
            status = '交易中'
            color = '#3FB950'
            indicator_color = '#3FB950'
        elif 11 * 60 + 30 <= time_val < 13 * 60:
            status = '午间休市'
            color = '#FFD700'
            indicator_color = '#FFD700'
        elif 13 * 60 <= time_val < 15 * 60:
            status = '交易中'
            color = '#3FB950'
            indicator_color = '#3FB950'
        else:
            status = '已收盘'
            color = '#5C6470'
            indicator_color = '#5C6470'

        self.market_status.setText(status)
        self.market_status.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 600;')
        self.market_indicator.setStyleSheet(f'color: {indicator_color}; font-size: 11px;')

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

        # V1.3.18：强势主力行为选股已提升为一级菜单，此处移除
        # action_screener = QAction('🎯 强势主力行为选股', self)
        # action_screener.triggered.connect(self.open_force_behavior_screener)
        # menu_stock.addAction(action_screener)

        action_strategy_lab = QAction('🧪 策略实验室（重构中）', self)
        action_strategy_lab.triggered.connect(lambda: self._show_not_implemented('策略实验室'))
        menu_stock.addAction(action_strategy_lab)

        # V7.6-A信号源集成：V7.4精准买点已集成到实时监控大厅，隐藏独立入口
        # action_v74 = QAction('⭐ V7.4精准买点', self)
        # action_v74.triggered.connect(self.open_v74_precision_buy)
        # menu_stock.addAction(action_v74)

        # V7.4回退：已删除V8.0 AI交易大脑菜单

        # 以下菜单项已移除（V0.4.2.3 精简）
        # action_ai_decision = QAction('🤖 AI决策中心', self)
        # action_ai_decision.triggered.connect(self.open_ai_decision_page)
        # menu_stock.addAction(action_ai_decision)

        # action_backtest = QAction('📊 回测中心', self)
        # action_backtest.triggered.connect(self.open_backtest_center)
        # menu_stock.addAction(action_backtest)

        # menu_stock.addSeparator()

        # action_limit_up_review = QAction('涨停板复盘', self)
        # action_limit_up_review.triggered.connect(lambda: self._show_not_implemented('涨停板复盘'))
        # menu_stock.addAction(action_limit_up_review)

        # action_sector_leader = QAction('板块龙头识别', self)
        # action_sector_leader.triggered.connect(lambda: self._show_not_implemented('板块龙头识别'))
        # menu_stock.addAction(action_sector_leader)

        # action_strong_stock = QAction('强势股池', self)
        # action_strong_stock.triggered.connect(lambda: self._show_not_implemented('强势股池'))
        # menu_stock.addAction(action_strong_stock)

        # action_limit_down = QAction('跌停股池', self)
        # action_limit_down.triggered.connect(lambda: self._show_not_implemented('跌停股池'))
        # menu_stock.addAction(action_limit_down)

        # action_northbound = QAction('北向资金选股', self)
        # action_northbound.triggered.connect(lambda: self._show_not_implemented('北向资金选股'))
        # menu_stock.addAction(action_northbound)

        # ========== 2.5 股票回测菜单 ==========
        menu_backtest = menubar.addMenu('📊 股票回测')

        action_backtest_center = QAction('回测中心', self)
        action_backtest_center.triggered.connect(self.open_backtest_window)
        menu_backtest.addAction(action_backtest_center)

        action_annotation_training = QAction('✏️ K线标注训练', self)
        action_annotation_training.triggered.connect(self.open_annotation_training)
        menu_backtest.addAction(action_annotation_training)

        menu_backtest.addSeparator()

        action_backtest_report = QAction('回测报告', self)
        action_backtest_report.triggered.connect(lambda: self._show_not_implemented('回测报告'))
        menu_backtest.addAction(action_backtest_report)

        action_param_optimize = QAction('参数优化', self)
        action_param_optimize.triggered.connect(lambda: self._show_not_implemented('参数优化'))
        menu_backtest.addAction(action_param_optimize)

        # ========== V1.3.18：股票投资日历（提升为一级菜单） ==========
        menu_calendar = menubar.addMenu('📅 股票投资日历')
        action_calendar_top = QAction('📅 打开股票投资日历', self)
        action_calendar_top.triggered.connect(self.open_investment_calendar)
        menu_calendar.addAction(action_calendar_top)

        # ========== V1.3.18：强势主力行为选股（提升为一级菜单） ==========
        menu_screener_top = menubar.addMenu('🎯 强势主力行为选股')
        action_screener_top = QAction('🎯 打开强势主力行为选股', self)
        action_screener_top.triggered.connect(self.open_force_behavior_screener)
        menu_screener_top.addAction(action_screener_top)
        
        # 策略建模工作台
        action_modeling = QAction('🧩 策略建模工作台', self)
        action_modeling.triggered.connect(self.open_modeling_workbench)
        menu_screener_top.addAction(action_modeling)

        # ========== V1.0：九重共振选股中心（新增独立一级菜单） ==========
        menu_nine_filter = menubar.addMenu('🎯 九重共振选股')
        action_nine_filter = QAction('🎯 打开九重共振选股中心', self)
        action_nine_filter.triggered.connect(self.open_nine_filter_screener)
        menu_nine_filter.addAction(action_nine_filter)

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

        # V1.3.18：股票投资日历已提升为一级菜单，此处移除
        # action_calendar = QAction('📅 股票投资日历', self)
        # action_calendar.triggered.connect(self.open_investment_calendar)
        # menu_tools.addAction(action_calendar)

        action_export = QAction('数据导出', self)
        action_export.triggered.connect(lambda: self._show_not_implemented('数据导出'))
        menu_tools.addAction(action_export)

        action_settings = QAction('系统设置', self)
        action_settings.triggered.connect(lambda: self._show_not_implemented('系统设置'))
        menu_tools.addAction(action_settings)

        action_clear_cache = QAction('清空缓存', self)
        action_clear_cache.triggered.connect(lambda: self._show_not_implemented('清空缓存'))
        menu_tools.addAction(action_clear_cache)

        # 皮肤切换子菜单
        menu_skin = menu_tools.addMenu('🎨 界面皮肤')
        from ui.theme.skin_manager import SkinManager
        for skin_key, skin_name, skin_desc in SkinManager.get_skins():
            action_skin = QAction(f'{skin_name} - {skin_desc}', self)
            action_skin.triggered.connect(lambda checked, k=skin_key: self._switch_skin(k))
            menu_skin.addAction(action_skin)

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

    def _switch_skin(self, skin_key):
        """切换界面皮肤"""
        try:
            from ui.theme.skin_manager import SkinManager
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if SkinManager.set_skin(skin_key, app):
                skin_name = SkinManager.get_current_skin_name()
                self.statusBar().showMessage(f'皮肤已切换为: {skin_name}', 3000)
        except Exception as e:
            print(f'切换皮肤失败: {e}')

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
                # 获取全市场主板非ST股票实时行情（不限制数量，确保覆盖所有主板股票）
                stocks = get_full_market_quotes(main_board_only=True, exclude_st=True)
                self.statusBar.showMessage(f'已获取{len(stocks)}只主板非ST股票，开始扫描...')
                # 扫描引擎最多处理3000只，确保覆盖所有主板股票
                self.scan_engine.scan_market(stocks, max_stocks=3000)
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

        # 记录当前页面，用于返回
        self._last_list_page = self.sidebar.get_current_page() or 'monitor'

        # 先从监控大厅查找（快速路径）
        for stock in self.monitor_hall.filtered_stocks:
            if stock['code'] == code:
                self.stock_detail.show_stock(stock)
                self.stacked.setCurrentWidget(self.stock_detail)
                return

        # 监控大厅没有，单独扫描（AI决策中心/选股池/自选股走这里）
        self.statusBar.showMessage(f'正在获取{name}({code})详情...')
        import threading
        def _do():
            try:
                result = self.scan_engine.scan_single(code, name)
                from PyQt6.QtCore import QTimer
                if result:
                    QTimer.singleShot(0, lambda: self._show_detail_in_main(result, name))
                else:
                    QTimer.singleShot(0, lambda: self.statusBar.showMessage(f'获取{name}({code})详情失败，请检查网络'))
            except Exception as e:
                print(f"[主窗口] 扫描{code}异常: {e}")
                import traceback
                traceback.print_exc()
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.statusBar.showMessage(f'获取{name}({code})详情出错: {str(e)[:30]}'))

        threading.Thread(target=_do, daemon=True).start()

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
        """从股票详情返回列表"""
        if hasattr(self, '_last_list_page') and self._last_list_page in self._page_map:
            idx = self._page_map[self._last_list_page]
            self.stacked.setCurrentIndex(idx)
            self.sidebar.set_current_page(self._last_list_page)
        else:
            self.stacked.setCurrentIndex(0)
            self.sidebar.set_current_page('monitor')

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

    def open_force_behavior_screener(self):
        """打开强势主力行为选股系统（独立窗口）"""
        print("[主窗口] 打开强势主力行为选股系统")

        try:
            from ui.force_behavior_panel import ForceBehaviorPanel

            # 如果窗口已经打开，激活它
            if hasattr(self, 'force_behavior_window') and self.force_behavior_window and self.force_behavior_window.isVisible():
                self.force_behavior_window.activateWindow()
                self.force_behavior_window.raise_()
                return

            # 创建新窗口
            from PyQt6.QtWidgets import QMainWindow
            self.force_behavior_window = QMainWindow()
            self.force_behavior_window.setWindowTitle('🎯 强势主力行为选股系统 V1.3')
            self.force_behavior_window.resize(1500, 900)
            self.force_behavior_window.setStyleSheet("background:#0d1117;")

            panel = ForceBehaviorPanel()
            self.force_behavior_window.setCentralWidget(panel)

            self.force_behavior_window.show()
            print("[主窗口] 强势主力行为选股系统已打开")

        except Exception as e:
            print(f"[主窗口] 打开强势主力行为选股系统失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开强势主力行为选股系统失败: {str(e)}')

    def open_modeling_workbench(self):
        """打开量化策略建模工作台（独立窗口）- V3卡片式高光UI"""
        print("[主窗口] 打开量化策略建模工作台 V3")

        try:
            from ui.modeling_workbench_v3 import ModelingWorkbenchV3

            # 如果窗口已经打开，激活它
            if hasattr(self, 'modeling_window') and self.modeling_window and self.modeling_window.isVisible():
                self.modeling_window.activateWindow()
                self.modeling_window.raise_()
                return

            # 创建新窗口
            from PyQt6.QtWidgets import QMainWindow
            self.modeling_window = QMainWindow()
            self.modeling_window.setWindowTitle('🧩 量化策略建模工作台 V3.0 · 卡片式高光UI')
            self.modeling_window.resize(1450, 900)
            self.modeling_window.setStyleSheet("background:#0a0e17;")

            panel = ModelingWorkbenchV3()
            self.modeling_window.setCentralWidget(panel)

            self.modeling_window.show()
            print("[主窗口] 量化策略建模工作台 V3 已打开")

        except Exception as e:
            print(f"[主窗口] 打开量化策略建模工作台失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开量化策略建模工作台失败: {str(e)}')

    def open_nine_filter_screener(self):
        """打开九重共振选股中心（独立窗口）"""
        print("[主窗口] 打开九重共振选股中心")

        try:
            from ui.nine_filter_panel import NineFilterPanel

            # 如果窗口已经打开，激活它
            if hasattr(self, 'nine_filter_window') and self.nine_filter_window and self.nine_filter_window.isVisible():
                self.nine_filter_window.activateWindow()
                self.nine_filter_window.raise_()
                return

            # 创建新窗口
            from PyQt6.QtWidgets import QMainWindow
            self.nine_filter_window = QMainWindow()
            self.nine_filter_window.setWindowTitle('🎯 九重共振选股中心 V1.0')
            self.nine_filter_window.resize(1600, 950)
            self.nine_filter_window.setStyleSheet("background:#0d1117;")

            panel = NineFilterPanel()
            self.nine_filter_window.setCentralWidget(panel)

            self.nine_filter_window.show()
            print("[主窗口] 九重共振选股中心已打开")

        except Exception as e:
            print(f"[主窗口] 打开九重共振选股中心失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开九重共振选股中心失败: {str(e)}')

    def open_strategy_lab(self):
        """策略实验室（已重构，功能迁移至强势主力行为选股系统）"""
        self._show_not_implemented('策略实验室（已迁移至强势主力行为选股系统）')

    def open_v74_precision_buy(self):
        """打开V7.4精准买点页面（独立窗口）"""
        print("[主窗口] 打开V7.4精准买点页面")

        try:
            # 如果窗口已经打开，激活它
            if self.v74_window and self.v74_window.isVisible():
                self.v74_window.activateWindow()
                self.v74_window.raise_()
                return

            # 延迟导入，避免启动时依赖
            from ui.v74_precision_buy_page import V74PrecisionBuyPage
            self.v74_window = V74PrecisionBuyPage()
            self.v74_window.setWindowTitle('⭐ V7.4 精准买点 - 冻结交易规则')
            self.v74_window.resize(1400, 900)

            # 窗口关闭时清理引用
            self.v74_window.destroyed.connect(self._on_v74_closed)

            self.v74_window.show()
            print("[主窗口] V7.4精准买点页面已打开")

        except Exception as e:
            print(f"[主窗口] 打开V7.4精准买点页面失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开V7.4精准买点页面失败: {str(e)}')

    def _on_v74_closed(self):
        """V7.4窗口关闭回调"""
        print("[主窗口] V7.4精准买点页面已关闭")
        self.v74_window = None

    # V7.4回退：已删除V8.0 AI交易大脑相关方法

    def open_backtest_window(self):
        """打开股票回测中心（独立窗口）"""
        print("[主窗口] 打开股票回测中心")

        try:
            # 如果窗口已经打开，激活它
            if self.backtest_window and self.backtest_window.isVisible():
                self.backtest_window.activateWindow()
                self.backtest_window.raise_()
                return

            # 创建新窗口
            self.backtest_window = StockBacktestWindow()
            self.backtest_window.resize(1400, 900)

            # 窗口关闭时清理引用
            self.backtest_window.destroyed.connect(self._on_backtest_closed)

            self.backtest_window.show()
            print("[主窗口] 股票回测中心已打开")

        except Exception as e:
            print(f"[主窗口] 打开回测中心失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开股票回测中心失败: {str(e)}')

    def _on_backtest_closed(self):
        """回测窗口关闭回调"""
        print("[主窗口] 股票回测中心已关闭")
        self.backtest_window = None

    def open_annotation_training(self):
        """打开K线标注训练系统（独立窗口）"""
        print("[主窗口] 打开K线标注训练系统")

        try:
            from ui.kline_annotation_training_panel import KlineAnnotationTrainingPanel

            # 如果窗口已经打开，激活它
            if hasattr(self, 'annotation_window') and self.annotation_window and self.annotation_window.isVisible():
                self.annotation_window.activateWindow()
                self.annotation_window.raise_()
                return

            # 创建新窗口
            from PyQt6.QtWidgets import QMainWindow
            self.annotation_window = QMainWindow()
            self.annotation_window.setWindowTitle('✏️ K线人工标注训练系统')
            self.annotation_window.resize(1400, 900)

            panel = KlineAnnotationTrainingPanel()
            self.annotation_window.setCentralWidget(panel)

            self.annotation_window.show()
            print("[主窗口] K线标注训练系统已打开")

        except Exception as e:
            print(f"[主窗口] 打开K线标注训练系统失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开K线标注训练系统失败: {str(e)}')

    def open_investment_calendar(self):
        """打开股票投资日历（独立窗口）"""
        print("[主窗口] 打开股票投资日历")

        try:
            from ui.investment_calendar_panel import InvestmentCalendarPanel

            # 如果窗口已经打开，激活它
            if hasattr(self, 'calendar_window') and self.calendar_window and self.calendar_window.isVisible():
                self.calendar_window.activateWindow()
                self.calendar_window.raise_()
                return

            # 创建新窗口
            from PyQt6.QtWidgets import QMainWindow
            self.calendar_window = QMainWindow()
            self.calendar_window.setWindowTitle('📅 股票投资日历')
            self.calendar_window.resize(1200, 800)

            panel = InvestmentCalendarPanel()
            self.calendar_window.setCentralWidget(panel)

            self.calendar_window.show()
            print("[主窗口] 股票投资日历已打开")

        except Exception as e:
            print(f"[主窗口] 打开股票投资日历失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, '错误', f'打开股票投资日历失败: {str(e)}')

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

    def _check_close_summary(self):
        """15:05后生成并自动推送当日收盘总结；只执行一次/交易日。"""
        from datetime import datetime
        now = datetime.now()
        if now.weekday() >= 5 or (now.hour * 60 + now.minute) < (15 * 60 + 5):
            return
        today = now.strftime('%Y-%m-%d')
        if self._close_summary_last_date == today:
            return
        # 后台线程生成，绝不阻塞UI
        import threading
        self._close_summary_last_date = today
        def _worker():
            try:
                from services.daily_close_summary_service import get_daily_close_summary_service
                service = get_daily_close_summary_service()
                result = service.generate_and_push(self)
                print(f"[收盘总结] {result.get('status')}: {result.get('message', '')}", flush=True)
            except Exception as e:
                print(f"[收盘总结] 生成/推送失败: {e}", flush=True)
        threading.Thread(target=_worker, daemon=True, name='DailyCloseSummary').start()

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
