# -*- coding: utf-8 -*-
"""
九重共振选股中心 - UI面板 V1.0

页面结构：
  顶部：真实市场状态（情绪周期/涨停数/跌停数/连板高度/情绪温度）
  工具栏：扫描/缓存加载/最低通过重数选择
  漏斗栏：九重过滤每层通过数量
  股票列表：代码/名称/现价/涨跌幅/成交额/换手率/量比/RPS20/资金/趋势/情绪/九重/评分/等级
  点击股票：进入现有K线分析页面
"""
import os
import time
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QSplitter,
    QProgressBar, QComboBox, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

# 主题系统
try:
    from ui.theme.design_tokens import (
        BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE, BG_CONTAINER,
        BORDER, BORDER_SOFT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
        ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD, ACCENT_ORANGE, STATUS_SUCCESS,
    )
    THEME_AVAILABLE = True
except Exception:
    THEME_AVAILABLE = False
    # 降级配色
    BG_WINDOW = "#0d1117"
    BG_PANEL = "#161b22"
    BG_CARD = "#1c2128"
    BG_INTERACTIVE = "#21262d"
    BG_CONTAINER = "#0d1117"
    BORDER = "#30363d"
    BORDER_SOFT = "#21262d"
    TEXT_PRIMARY = "#e6edf3"
    TEXT_SECONDARY = "#8b949e"
    TEXT_MUTED = "#6e7681"
    ACCENT_BLUE = "#58a6ff"
    ACCENT_GREEN = "#3fb950"
    ACCENT_RED = "#f85149"
    ACCENT_GOLD = "#d29922"
    ACCENT_ORANGE = "#db6d28"
    STATUS_SUCCESS = "#238636"

# ECharts K线组件
try:
    from ui.echarts_kline import EChartsKlineWidget
    ECHARTS_AVAILABLE = True
except Exception as e:
    print(f"[NINE FILTER UI] ECharts导入失败: {e}", flush=True)
    ECHARTS_AVAILABLE = False

# 九重策略
from strategy.nine_filter_strategy import (
    NineFilterStrategy, NineFilterStockResult, MarketSentiment,
    LAYER_NAMES, CYCLE_RISING, CYCLE_CHAOS, CYCLE_FALLING, CYCLE_FREEZING,
)
from strategy.nine_score_engine import GRADE_S_PLUS, GRADE_S, GRADE_A, GRADE_B


class NineScanWorker(QThread):
    """九重扫描后台线程"""
    progress = pyqtSignal(int, int, str)
    finished_scan = pyqtSignal(list, dict)
    error = pyqtSignal(str)

    def __init__(self, strategy, min_pass_count=5, max_stocks=None, scan_mode="标准扫描"):
        super().__init__()
        self.strategy = strategy
        self.min_pass_count = min_pass_count
        self.max_stocks = max_stocks
        self.scan_mode = scan_mode

    def run(self):
        try:
            def on_progress(c, t, n):
                self.progress.emit(c, t, n)
            results = self.strategy.scan(
                progress_callback=on_progress,
                min_pass_count=self.min_pass_count,
                max_stocks=self.max_stocks,
                scan_mode=self.scan_mode,
            )
            funnel = self.strategy.get_funnel_stats()
            self.finished_scan.emit(results, funnel)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class NineFilterPanel(QWidget):
    """九重共振选股中心面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strategy = None
        self.scan_worker = None
        self.current_results = []
        self._init_strategy()
        self._init_ui()

    def _init_strategy(self):
        """初始化策略引擎"""
        try:
            self.strategy = NineFilterStrategy.instance()
            print("[NINE FILTER UI] 策略初始化成功", flush=True)
        except Exception as e:
            print(f"[NINE FILTER UI] 策略初始化失败: {e}", flush=True)
            self.strategy = None

    def _init_ui(self):
        self.setStyleSheet(f"NineFilterPanel {{ background: {BG_WINDOW}; color: {TEXT_PRIMARY}; }}")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        main_layout.addWidget(self._create_title_bar())
        main_layout.addWidget(self._create_market_status_bar())
        main_layout.addWidget(self._create_toolbar())
        main_layout.addWidget(self._create_cache_bar())
        main_layout.addWidget(self._create_funnel_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_stock_pool_panel())
        splitter.addWidget(self._create_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)

        self.status_label = QLabel('就绪 | 九重共振选股中心 V1.0')
        self.status_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px; padding: 2px 8px;')
        main_layout.addWidget(self.status_label)

        # 延迟检查缓存
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, self._auto_load_cache)

    # ============================================================
    # UI组件创建
    # ============================================================
    def _create_title_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        title = QLabel('🎯 九重共振选股中心 V1.0')
        title.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 16px; font-weight: 700;')
        layout.addWidget(title)
        layout.addStretch()
        # 九重标签
        for i, name in enumerate(LAYER_NAMES[:5]):
            tag = QLabel(f"L{i+1}")
            tag.setStyleSheet(f'background: {ACCENT_BLUE}22; color: {ACCENT_BLUE}; '
                              f'border: 1px solid {ACCENT_BLUE}; border-radius: 4px; '
                              f'padding: 2px 6px; font-size: 10px; font-weight: 600;')
            layout.addWidget(tag)
        return bar

    def _create_market_status_bar(self):
        """市场状态条（第1重）"""
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(15)

        self.market_labels = {}
        items = [
            ('情绪周期', 'cycle', ACCENT_GOLD),
            ('涨停数', 'limit_up', ACCENT_RED),
            ('跌停数', 'limit_down', ACCENT_GREEN),
            ('连板高度', 'consecutive', ACCENT_ORANGE),
            ('情绪温度', 'temperature', ACCENT_BLUE),
            ('上涨/下跌', 'up_down', TEXT_SECONDARY),
        ]
        for name, key, color in items:
            lbl = QLabel(f'{name}: --')
            lbl.setStyleSheet(f'color: {color}; font-size: 12px; font-weight: 600;')
            self.market_labels[key] = lbl
            layout.addWidget(lbl)
        layout.addStretch()
        return bar

    def _create_toolbar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self.btn_load_cache = QPushButton('⚡ 加载缓存')
        self.btn_load_cache.setStyleSheet(f"""
            QPushButton {{ background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_BLUE};
                border-radius: 6px; color: {ACCENT_BLUE}; padding: 6px 14px; font-weight: 600; }}
            QPushButton:hover {{ background: {ACCENT_BLUE}; color: white; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; }}
        """)
        self.btn_load_cache.clicked.connect(self._load_cache)
        layout.addWidget(self.btn_load_cache)

        self.btn_scan = QPushButton('🔄 全市场九重扫描')
        self.btn_scan.setStyleSheet(f"""
            QPushButton {{ background: {STATUS_SUCCESS}; border: 1px solid {ACCENT_GREEN};
                border-radius: 6px; color: {TEXT_PRIMARY}; padding: 6px 16px; font-weight: 700; }}
            QPushButton:hover {{ background: {ACCENT_GREEN}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; }}
        """)
        self.btn_scan.clicked.connect(self._start_scan)
        layout.addWidget(self.btn_scan)

        layout.addWidget(QLabel('最低通过:'))
        self.combo_min_pass = QComboBox()
        self.combo_min_pass.addItems(['5重以上', '6重以上', '7重以上', '8重以上', '全部'])
        self.combo_min_pass.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; '
                                           f'border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px 6px;')
        layout.addWidget(self.combo_min_pass)

        layout.addWidget(QLabel('模式:'))
        self.combo_scan_mode = QComboBox()
        self.combo_scan_mode.addItems(['标准扫描(120日)', '快速扫描(60日)'])
        self.combo_scan_mode.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; '
                                            f'border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px 6px;')
        layout.addWidget(self.combo_scan_mode)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {BG_CONTAINER}; border: 1px solid {BORDER}; border-radius: 4px;
                color: {TEXT_PRIMARY}; text-align: center; height: 18px; }}
            QProgressBar::chunk {{ background: {ACCENT_BLUE}; border-radius: 3px; }}
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar, stretch=1)

        self.stats_label = QLabel('')
        self.stats_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        layout.addWidget(self.stats_label)
        return bar

    def _create_cache_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 4px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 3, 10, 3)
        self.cache_status_label = QLabel('缓存状态: 检查中...')
        self.cache_status_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        layout.addWidget(self.cache_status_label)
        layout.addStretch()
        return bar

    def _create_funnel_bar(self):
        """九重漏斗统计栏"""
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        self.funnel_labels = {}
        colors = [ACCENT_GOLD, ACCENT_BLUE, '#3b82f6', ACCENT_GREEN, '#a855f7',
                  ACCENT_ORANGE, '#f97316', ACCENT_RED, '#22c55e']
        for i, name in enumerate(LAYER_NAMES):
            short_name = name[:4] if len(name) > 4 else name
            lbl = QLabel(f'L{i+1}{short_name}: --')
            lbl.setStyleSheet(f'color: {colors[i]}; font-size: 10px; font-weight: 600;')
            self.funnel_labels[f'layer{i+1}'] = lbl
            layout.addWidget(lbl)

        self.funnel_final_label = QLabel('候选: --')
        self.funnel_final_label.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 11px; font-weight: 700;')
        layout.addWidget(self.funnel_final_label)
        layout.addStretch()
        return bar

    def _create_stock_pool_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel('📋 九重共振股票池（按综合评分降序）')
        header.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 13px; font-weight: 700;')
        layout.addWidget(header)

        # 14列
        self.table = QTableWidget()
        self.table.setStyleSheet(f"""
            QTableWidget {{ background: {BG_CONTAINER}; color: {TEXT_PRIMARY}; gridline-color: {BORDER};
                border: 1px solid {BORDER}; border-radius: 6px; alternate-background-color: {BG_PANEL_ALT}; }}
            QTableWidget::item {{ padding: 3px; border-bottom: 1px solid {BORDER}; }}
            QHeaderView::section {{ background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; padding: 4px;
                border: 1px solid {BORDER}; font-weight: 700; font-size: 10px; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); color: {TEXT_PRIMARY}; }}
        """)
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels([
            '名称', '代码', '现价', '涨跌幅', '成交额(万)', '换手率',
            '量比', 'RPS20', '资金分', '趋势分', '情绪分',
            '九重通过', '综合评分', '等级'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._on_stock_double_clicked)
        self.table.cellClicked.connect(self._on_stock_selected)
        layout.addWidget(self.table, stretch=1)
        return panel

    def _create_detail_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.detail_title = QLabel('选择左侧股票查看详情（双击进入K线分析）')
        self.detail_title.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 14px; font-weight: 700;')
        layout.addWidget(self.detail_title)

        # 评分卡片
        self.score_card = self._create_score_card()
        layout.addWidget(self.score_card)

        # 九重通过状态
        self.nine_status_label = QLabel('九重通过: --')
        self.nine_status_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px; padding: 4px;')
        layout.addWidget(self.nine_status_label)

        # K线图区域
        kline_container = QFrame()
        kline_container.setStyleSheet(f"background: #0d1117; border: 1px solid {BORDER}; border-radius: 6px;")
        kline_layout = QVBoxLayout(kline_container)
        kline_layout.setContentsMargins(0, 0, 0, 0)

        # K线标题栏（显示股票名称、最新日期、数据状态）
        self.kline_title_label = QLabel('选择股票查看K线图')
        self.kline_title_label.setStyleSheet(
            f'color: {TEXT_PRIMARY}; background: {BG_PANEL}; '
            f'padding: 6px 10px; font-size: 12px; font-weight: bold; '
            f'border-bottom: 1px solid {BORDER};')
        kline_layout.addWidget(self.kline_title_label)

        if ECHARTS_AVAILABLE:
            self.kline_widget = EChartsKlineWidget()
            self.kline_widget.setMinimumHeight(260)
            kline_layout.addWidget(self.kline_widget, stretch=1)
        else:
            self.kline_widget = QLabel('K线图区域\n（选择股票后加载）')
            self.kline_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.kline_widget.setStyleSheet(f'color: {TEXT_MUTED}; background: #0d1117; font-size: 13px;')
            self.kline_widget.setMinimumHeight(200)
            kline_layout.addWidget(self.kline_widget, stretch=1)
        layout.addWidget(kline_container, stretch=1)

        # 详情文本
        self.detail_text = QLabel('')
        self.detail_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_text.setWordWrap(True)
        self.detail_text.setStyleSheet(f'color: {TEXT_PRIMARY}; background: {BG_CARD}; '
                                        f'border: 1px solid {BORDER}; border-radius: 6px; '
                                        f'padding: 8px; font-size: 11px;')
        self.detail_text.setMaximumHeight(120)
        layout.addWidget(self.detail_text)
        return panel

    def _create_score_card(self):
        card = QFrame()
        card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self.score_total = QLabel('--')
        self.score_total.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 26px; font-weight: 800;')
        self.score_total.setMinimumWidth(55)
        layout.addWidget(self.score_total)

        self.score_grade = QLabel('未评分')
        self.score_grade.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 700;')
        layout.addWidget(self.score_grade)
        layout.addStretch()

        self.dim_labels = {}
        dims = [('资金', 'fund', 40), ('趋势', 'trend', 40), ('情绪', 'sentiment', 20)]
        for name, key, mx in dims:
            vbox = QVBoxLayout()
            lbl = QLabel(f'{name}\n0/{mx}')
            lbl.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 10px;')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dim_labels[key] = lbl
            vbox.addWidget(lbl)
            layout.addLayout(vbox)
        return card

    # ============================================================
    # 扫描逻辑
    # ============================================================
    def _start_scan(self):
        if self.strategy is None:
            QMessageBox.warning(self, '提示', '策略未初始化')
            return
        if self.scan_worker and self.scan_worker.isRunning():
            return

        # 清除旧缓存
        try:
            self.strategy.clear_scan_cache()
        except Exception:
            pass

        min_pass_map = {0: 5, 1: 6, 2: 7, 3: 8, 4: 0}
        min_pass = min_pass_map.get(self.combo_min_pass.currentIndex(), 5)
        mode_map = {0: "标准扫描", 1: "快速扫描"}
        scan_mode = mode_map.get(self.combo_scan_mode.currentIndex(), "标准扫描")

        self.btn_scan.setEnabled(False)
        self.btn_load_cache.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._scan_start_time = time.time()
        self.status_label.setText(f'正在{scan_mode}...')

        self.scan_worker = NineScanWorker(self.strategy, min_pass_count=min_pass, scan_mode=scan_mode)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_scan.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_progress(self, c, t, n):
        if t > 0:
            self.progress_bar.setMaximum(t)
            self.progress_bar.setValue(c)
            elapsed = time.time() - getattr(self, '_scan_start_time', time.time())
            pct = c / t * 100
            self.status_label.setText(f'扫描中: {c}/{t} ({pct:.0f}%) - {n} - {elapsed:.1f}s')

    def _on_scan_finished(self, results, funnel):
        self.btn_scan.setEnabled(True)
        self.btn_load_cache.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.current_results = results
        self._update_market_status()
        self._update_stock_table(results)
        self._update_funnel(funnel)
        cnt = len(results)
        avg = sum(r.score.total for r in results) / cnt if cnt > 0 else 0
        elapsed = time.time() - getattr(self, '_scan_start_time', time.time())
        self.stats_label.setText(f'股票池: {cnt}只 | 平均分: {avg:.1f} | 耗时: {elapsed:.1f}s')
        self.status_label.setText(f'扫描完成 | 候选{cnt}只 | 耗时{elapsed:.1f}s')
        self._update_cache_status()

    def _on_scan_error(self, msg):
        self.btn_scan.setEnabled(True)
        self.btn_load_cache.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f'扫描失败: {msg}')
        QMessageBox.critical(self, '扫描失败', msg)

    # ============================================================
    # 缓存
    # ============================================================
    def _auto_load_cache(self):
        try:
            self._update_cache_status()
            if self.strategy:
                info = self.strategy.get_cache_info()
                if info.get('exists') and info.get('status') == '有效':
                    print(f"[NINE UI] 检测到有效缓存，自动加载: {info.get('result_count', 0)}只", flush=True)
                    self._load_cache()
                else:
                    status = info.get('status', '无缓存')
                    self.status_label.setText(f'缓存{status}，请点击"全市场九重扫描"开始')
        except Exception as e:
            print(f"[NINE UI] 自动缓存检查失败: {e}", flush=True)

    def _load_cache(self):
        if self.strategy is None:
            return
        self.status_label.setText('正在加载缓存...')
        QApplication.processEvents()
        try:
            start = time.time()
            results = self.strategy.load_cached_scan()
            elapsed = time.time() - start
            if results:
                self.current_results = results
                self._update_market_status()
                self._update_stock_table(results)
                try:
                    funnel = self.strategy.get_funnel_stats()
                    self._update_funnel(funnel)
                except Exception:
                    pass
                self.status_label.setText(f'⚡ 缓存加载完成: {len(results)}只, 耗时{elapsed:.1f}秒')
            else:
                info = self.strategy.get_cache_info()
                status = info.get('status', '无缓存')
                self.status_label.setText(f'缓存不可用({status})，请点击"全市场九重扫描"')
        except Exception as e:
            self.status_label.setText(f'缓存加载失败: {e}')
        self._update_cache_status()

    def _update_cache_status(self):
        try:
            data_source_str = ""
            if self.strategy and self.strategy.tdx_engine and self.strategy.tdx_engine.is_available():
                stats = self.strategy.tdx_engine.get_memory_cache_stats()
                latest = stats.get('latest_date', '')
                data_source_str = (f"📡 数据源: ✅通达信本地 | K线缓存: {stats['stock_count']}只 | "
                                   f"数据日期: {latest} | ")
            else:
                data_source_str = "📡 数据源: ⚠️通达信不可用 | "

            if self.strategy:
                info = self.strategy.get_cache_info()
                if info.get('exists'):
                    status = info.get('status', '未知')
                    scan_time = info.get('scan_time', '')
                    count = info.get('result_count', 0)
                    self.cache_status_label.setText(
                        f"{data_source_str}💾 最后扫描: {scan_time} | 缓存股票: {count}只 | 状态: {status}"
                    )
                    color = ACCENT_GREEN if "有效" in status else ACCENT_ORANGE if "过期" in status else TEXT_MUTED
                    self.cache_status_label.setStyleSheet(f'color: {color}; font-size: 11px;')
                else:
                    self.cache_status_label.setText(f'{data_source_str}💾 缓存状态: 无缓存')
                    self.cache_status_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px;')
        except Exception as e:
            self.cache_status_label.setText(f'💾 缓存状态读取失败: {e}')

    # ============================================================
    # 市场状态更新
    # ============================================================
    def _update_market_status(self):
        if not self.strategy:
            return
        sent = self.strategy.get_market_sentiment()
        cycle_colors = {
            CYCLE_RISING: ACCENT_RED, CYCLE_CHAOS: ACCENT_GOLD,
            CYCLE_FALLING: ACCENT_BLUE, CYCLE_FREEZING: TEXT_MUTED,
        }
        self.market_labels['cycle'].setText(f'情绪周期: {sent.cycle}')
        self.market_labels['cycle'].setStyleSheet(
            f'color: {cycle_colors.get(sent.cycle, ACCENT_GOLD)}; font-size: 12px; font-weight: 700;')
        self.market_labels['limit_up'].setText(f'涨停: {sent.limit_up_count}')
        self.market_labels['limit_down'].setText(f'跌停: {sent.limit_down_count}')
        self.market_labels['consecutive'].setText(f'连板高度: {sent.max_consecutive_board}')
        self.market_labels['temperature'].setText(f'情绪温度: {sent.sentiment_temperature:.0f}')
        self.market_labels['up_down'].setText(f'上涨/下跌: {sent.up_count}/{sent.down_count}')

    # ============================================================
    # 漏斗更新
    # ============================================================
    def _update_funnel(self, funnel):
        for i in range(9):
            key = f'layer{i+1}_{LAYER_NAMES[i]}'
            val = funnel.get(key, 0)
            lbl = self.funnel_labels.get(f'layer{i+1}')
            if lbl:
                short_name = LAYER_NAMES[i][:4] if len(LAYER_NAMES[i]) > 4 else LAYER_NAMES[i]
                lbl.setText(f'L{i+1}{short_name}: {val}')
        final_key = [k for k in funnel.keys() if k.startswith('pass_')]
        if final_key:
            self.funnel_final_label.setText(f'候选: {funnel[final_key[0]]}')

    # ============================================================
    # 股票表格更新
    # ============================================================
    def _update_stock_table(self, results):
        print(f"[NINE TABLE] 接收数据: {len(results)}只", flush=True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        success_count = 0
        for i, r in enumerate(results):
            try:
                self.table.insertRow(i)
                amount_wan = r.amount / 10000 if r.amount > 0 else 0
                items_data = [
                    (r.name if r.name else r.code, r.name if r.name else r.code),  # 0 名称
                    (r.code, r.code),                                                 # 1 代码
                    (f'{r.price:.2f}', r.price),                                      # 2 现价
                    (f'{r.change_pct:+.2f}%', r.change_pct),                         # 3 涨跌幅
                    (f'{amount_wan:.0f}', amount_wan),                                # 4 成交额
                    (f'{r.turnover_rate:.1f}%', r.turnover_rate),                    # 5 换手率
                    (f'{r.volume_ratio:.2f}', r.volume_ratio),                        # 6 量比
                    (f'{r.rps20:.0f}', r.rps20),                                      # 7 RPS20
                    (f'{r.score.fund_score:.0f}', r.score.fund_score),               # 8 资金分
                    (f'{r.score.trend_score:.0f}', r.score.trend_score),             # 9 趋势分
                    (f'{r.score.sentiment_score:.0f}', r.score.sentiment_score),     # 10 情绪分
                    (f'{r.pass_count}/9', r.pass_count),                              # 11 九重通过
                    (f'{r.score.total:.1f}', r.score.total),                          # 12 综合评分
                    (r.score.grade, r.score.total),                                    # 13 等级
                ]
                for j, (text, sort_val) in enumerate(items_data):
                    item = QTableWidgetItem(str(text))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setData(Qt.ItemDataRole.EditRole, sort_val)
                    # 涨跌幅颜色
                    if j == 3:
                        if r.change_pct > 0:
                            item.setForeground(QColor(ACCENT_RED))
                        elif r.change_pct < 0:
                            item.setForeground(QColor(ACCENT_GREEN))
                    # 综合评分颜色
                    if j == 12:
                        if r.score.total >= 80:
                            item.setForeground(QColor(ACCENT_RED))
                        elif r.score.total >= 70:
                            item.setForeground(QColor(ACCENT_ORANGE))
                        elif r.score.total >= 60:
                            item.setForeground(QColor(ACCENT_GREEN))
                        item.setFont(QFont('Arial', 10, QFont.Weight.Bold))
                    # 等级颜色
                    if j == 13:
                        grade_colors = {
                            GRADE_S_PLUS: ACCENT_RED, GRADE_S: ACCENT_ORANGE,
                            GRADE_A: ACCENT_GOLD, GRADE_B: ACCENT_GREEN,
                        }
                        color = grade_colors.get(r.score.grade, TEXT_MUTED)
                        item.setForeground(QColor(color))
                        item.setFont(QFont('Arial', 10, QFont.Weight.Bold))
                    self.table.setItem(i, j, item)
                success_count += 1
            except Exception as e:
                print(f"[NINE TABLE ERROR] 第{i}行更新失败: {e}", flush=True)
                if self.table.rowCount() > i:
                    self.table.removeRow(i)

        self.table.setSortingEnabled(True)
        self.table.sortItems(12, Qt.SortOrder.DescendingOrder)
        self.table.resizeColumnsToContents()
        print(f"[NINE TABLE] 表格更新完成: 成功{success_count}/{len(results)}行", flush=True)

    # ============================================================
    # 股票详情
    # ============================================================
    def _on_stock_selected(self, row, col):
        if row < 0:
            return
        code_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text()
        stock = None
        for s in self.current_results:
            if s.code == code:
                stock = s
                break
        if stock is None:
            return

        self.detail_title.setText(f'{stock.name if stock.name else stock.code} ({stock.code}) | ¥{stock.price:.2f}')

        # 评分卡片
        self.score_total.setText(f'{stock.score.total:.0f}')
        grade_colors = {
            GRADE_S_PLUS: ACCENT_RED, GRADE_S: ACCENT_ORANGE,
            GRADE_A: ACCENT_GOLD, GRADE_B: ACCENT_GREEN,
        }
        self.score_grade.setText(stock.score.grade)
        self.score_grade.setStyleSheet(f'color: {grade_colors.get(stock.score.grade, TEXT_MUTED)}; '
                                        f'font-size: 14px; font-weight: 700;')

        dim_max = {'fund': 40, 'trend': 40, 'sentiment': 20}
        dim_names = {'fund': '资金', 'trend': '趋势', 'sentiment': '情绪'}
        dim_vals = {'fund': stock.score.fund_score, 'trend': stock.score.trend_score,
                    'sentiment': stock.score.sentiment_score}
        for key, lbl in self.dim_labels.items():
            val = dim_vals.get(key, 0)
            mx = dim_max.get(key, 10)
            name = dim_names.get(key, key)
            lbl.setText(f'{name}\n{val:.0f}/{mx}')
            ratio = val / mx if mx > 0 else 0
            lbl.setStyleSheet(f'color: {"#22c55e" if ratio>=0.7 else "#f59e0b" if ratio>=0.4 else TEXT_MUTED}; '
                               f'font-size: 10px;')

        # 九重状态
        pass_names = [LAYER_NAMES[i] for i in range(9) if stock.layer_pass[i]]
        fail_names = [LAYER_NAMES[i] for i in range(9) if not stock.layer_pass[i]]
        nine_text = f'九重通过: {stock.pass_count}/9'
        if pass_names:
            nine_text += f'\n✅ 通过: {"、".join(pass_names)}'
        if fail_names:
            nine_text += f'\n❌ 未通过: {"、".join(fail_names)}'
        self.nine_status_label.setText(nine_text)

        # K线图
        if ECHARTS_AVAILABLE and hasattr(self, 'kline_widget') and self.strategy:
            try:
                kline_data = self.strategy.get_kline_data(code, days=120)
                if kline_data:
                    self.kline_widget.set_kline_data(kline_data)
                    # 更新K线标题栏：显示股票名称、最新日期、价格、数据状态
                    dates = kline_data.get('dates', [])
                    closes = kline_data.get('close', [])
                    if dates and closes:
                        latest_date = dates[-1]
                        latest_price = closes[-1]
                        # 格式化日期显示
                        if len(latest_date) == 8:
                            date_display = f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:8]}"
                        else:
                            date_display = latest_date
                        # 检查数据是否最新（对比今天日期）
                        from datetime import datetime
                        today_str = datetime.now().strftime('%Y%m%d')
                        if latest_date >= today_str:
                            data_status = "✅ 实时数据"
                            status_color = "#3fb950"
                        else:
                            data_status = f"⚠️ 数据日期{date_display}（请在通达信下载最新盘后数据）"
                            status_color = "#d29922"
                        self.kline_title_label.setText(
                            f'📈 {stock.name if stock.name else code}({code}) | '
                            f'最新: {date_display} 收{latest_price:.2f} | '
                            f'<span style="color:{status_color}">{data_status}</span>'
                        )
                        self.kline_title_label.setTextFormat(Qt.TextFormat.RichText)
            except Exception as e:
                print(f"[NINE UI] K线图渲染异常: {e}", flush=True)
                if hasattr(self, 'kline_title_label'):
                    self.kline_title_label.setText(f'📈 {stock.name or code}({code}) | K线加载失败')

        # 详情文本
        lines = [
            f'<b>代码:</b> {stock.code} | <b>名称:</b> {stock.name or "-"}',
            f'<b>现价:</b> {stock.price:.2f} | <b>涨跌幅:</b> {stock.change_pct:+.2f}%',
            f'<b>成交额:</b> {stock.amount/10000:.0f}万 | <b>换手率:</b> {stock.turnover_rate:.1f}%',
            f'<b>量比:</b> {stock.volume_ratio:.2f} | <b>RPS20:</b> {stock.rps20:.0f}',
            f'<b>MA5/10/20/60:</b> {stock.ma5:.2f}/{stock.ma10:.2f}/{stock.ma20:.2f}/{stock.ma60:.2f}',
            f'<b>筹码:</b> {stock.chip_peak_type} {stock.chip_position} 峰价{stock.chip_peak_price:.2f}',
            f'<b>分时信号:</b> {stock.intraday_signal or "-"}',
            f'<b>支撑/压力:</b> {stock.support_price:.2f}/{stock.pressure_price:.2f}',
            f'<b>首板回调:</b> {"✅匹配" if stock.first_board.matched else "未匹配"} {stock.first_board.signal_type}',
        ]
        if stock.score.reasons:
            lines.append(f'<b>评分理由:</b> {"; ".join(stock.score.reasons)}')
        self.detail_text.setText('<br>'.join(lines))

    def _on_stock_double_clicked(self, row, col):
        """双击股票进入现有K线分析页面"""
        code_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text()
        name_item = self.table.item(row, 0)
        name = name_item.text() if name_item else code
        print(f"[NINE UI] 双击打开K线分析: {name}({code})", flush=True)

        # 尝试打开现有K线分析页面
        try:
            from ui.stock_detail import StockDetailDialog
            dialog = StockDetailDialog(code, name, parent=self)
            dialog.exec()
            return
        except Exception as e:
            print(f"[NINE UI] StockDetailDialog打开失败: {e}", flush=True)

        try:
            from ui.kline_viewer_dialog import KlineViewerDialog
            dialog = KlineViewerDialog(code, name, parent=self)
            dialog.exec()
            return
        except Exception as e:
            print(f"[NINE UI] KlineViewerDialog打开失败: {e}", flush=True)

        QMessageBox.information(self, 'K线分析', f'股票: {name}({code})\n\nK线分析页面暂不可用，\n请在主程序K线模块中查看。')

    # ============================================================
    # 公共接口
    # ============================================================
    def get_strategy(self):
        return self.strategy

    def get_current_results(self):
        return self.current_results

    def closeEvent(self, event):
        try:
            if self.scan_worker and self.scan_worker.isRunning():
                try:
                    self.scan_worker.terminate()
                    self.scan_worker.wait(2000)
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(event)
