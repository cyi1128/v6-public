# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.1 - UI面板

V1.1升级：
- 股票池表格新增字段：模型评分/综合评分/买点等级/风险等级/支撑位/压力位
- 漏斗统计显示
- K线6色标注（绿缩量/黄箱体/红突破/蓝回踩/紫吸筹/橙风险）
- 买点B1-B3/卖点S1-S4标记
- 默认60分以上显示，取消70分硬过滤
"""
import os
import time
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QSplitter,
    QProgressBar, QComboBox, QTextEdit, QLineEdit, QMessageBox,
    QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE, BG_CONTAINER,
    BORDER, BORDER_SOFT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD, ACCENT_ORANGE, STATUS_SUCCESS,
)

# V1.3.8：ECharts K线图组件
try:
    from ui.echarts_kline import EChartsKlineWidget
    ECHARTS_AVAILABLE = True
except Exception as e:
    print(f"[UI WARN] EChartsKlineWidget导入失败，将使用文本标注: {e}", flush=True)
    ECHARTS_AVAILABLE = False

# 6色区域
REGION_COLORS = {
    'shrink': '#22c55e', 'box': '#eab308', 'breakout': '#ef4444',
    'confirm': '#3b82f6', 'accumulation': '#a855f7', 'risk': '#f97316',
}
REGION_NAMES = {
    'shrink': '缩量', 'box': '箱体', 'breakout': '突破',
    'confirm': '回踩', 'accumulation': '吸筹', 'risk': '风险',
}


class ScanWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_scan = pyqtSignal(list, dict)
    error = pyqtSignal(str)

    def __init__(self, strategy, min_score=60.0, max_stocks=None, scan_mode="快速扫描"):
        super().__init__()
        self.strategy = strategy
        self.min_score = min_score
        self.max_stocks = max_stocks
        self.scan_mode = scan_mode

    def run(self):
        try:
            def on_progress(c, t, n):
                self.progress.emit(c, t, n)
            results = self.strategy.scan(
                progress_callback=on_progress, min_score=self.min_score,
                max_stocks=self.max_stocks, scan_mode=self.scan_mode)
            funnel = self.strategy.get_funnel_stats()
            self.finished_scan.emit(results, funnel)
        except Exception as e:
            self.error.emit(str(e))


class ForceBehaviorPanel(QWidget):
    """强势主力行为选股系统 V1.1 面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.strategy = None
        self.scan_worker = None
        self.current_results = []
        self._init_strategy()
        self._init_ui()

    def _init_strategy(self):
        """V1.3.10：策略初始化，增加缓存锁定容错和状态显示"""
        try:
            from strategy.main_force_behavior import ForceBehaviorStrategy
            self.strategy = ForceBehaviorStrategy.instance()
            try:
                from market.data_provider import get_data_provider
                dp = get_data_provider()
                self.strategy.set_data_provider(dp)
                print(f"[ForceBehavior] data_provider设置成功: {type(dp).__name__}", flush=True)
            except Exception as e:
                print(f"[ForceBehavior] data_provider设置失败: {e}", flush=True)
            print(f"[ForceBehavior] 策略初始化成功", flush=True)
        except Exception as e:
            print(f"[ForceBehavior V1.1] 策略初始化失败: {e}", flush=True)
            # V1.3.10：初始化失败时尝试重试一次（可能是临时的文件锁定）
            print(f"[ForceBehavior] 尝试重新初始化策略...", flush=True)
            try:
                from strategy.main_force_behavior import ForceBehaviorStrategy
                # 清除可能存在的单例，重新创建
                ForceBehaviorStrategy._instance = None
                self.strategy = ForceBehaviorStrategy.instance()
                print(f"[ForceBehavior] 策略重新初始化成功", flush=True)
            except Exception as e2:
                print(f"[ForceBehavior] 策略重新初始化也失败: {e2}", flush=True)
                self.strategy = None
                # V1.3.10：显示警告，不禁用扫描按钮（用户可尝试重启程序）
                if hasattr(self, 'status_label'):
                    self.status_label.setText('⚠️ 策略初始化部分失败（缓存锁定），请重启程序')

    def _init_ui(self):
        self.setStyleSheet(f"ForceBehaviorPanel {{ background: {BG_WINDOW}; color: {TEXT_PRIMARY}; }}")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        main_layout.addWidget(self._create_title_bar())
        main_layout.addWidget(self._create_toolbar())
        main_layout.addWidget(self._create_cache_bar())
        main_layout.addWidget(self._create_funnel_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_stock_pool_panel())
        splitter.addWidget(self._create_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)

        self.status_label = QLabel('就绪 | 强势主力行为选股系统 V1.3')
        self.status_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px; padding: 2px 8px;')
        main_layout.addWidget(self.status_label)

        # V1.2.3：面板初始化完成后延迟检查缓存（不阻塞UI）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, self._auto_load_cache)

    def _auto_load_cache(self):
        """V1.2.3：面板打开时自动检查并加载缓存"""
        try:
            self._update_cache_status()
            if self.strategy:
                # V1.2.4：检查预加载状态
                if self.strategy.is_preloading():
                    self.status_label.setText('正在后台预加载...请稍候')
                    print("[UI] 检测到预加载进行中，等待完成", flush=True)
                    # 启动定时器定期检查预加载状态
                    from PyQt6.QtCore import QTimer
                    self._preload_check_timer = QTimer()
                    self._preload_check_timer.timeout.connect(self._check_preload_status)
                    self._preload_check_timer.start(2000)  # 每2秒检查一次
                    return

                info = self.strategy.get_cache_info()
                if info.get('exists') and '有效' in info.get('status', ''):
                    # 缓存有效，自动加载
                    print(f"[UI] 检测到有效缓存，自动加载: {info.get('result_count', 0)}只", flush=True)
                    self._load_cache()
                else:
                    status = info.get('status', '无缓存')
                    self.status_label.setText(f'缓存{status}，请点击"重新全市场扫描"开始')
                    print(f"[UI] 缓存状态: {status}，不自动扫描", flush=True)
        except Exception as e:
            print(f"[UI] 自动缓存检查失败: {e}", flush=True)

    def _check_preload_status(self):
        """V1.2.4：检查预加载是否完成"""
        try:
            if self.strategy and self.strategy.is_preload_finished():
                # 预加载完成，停止定时器并加载缓存
                if hasattr(self, '_preload_check_timer'):
                    self._preload_check_timer.stop()
                print("[UI] 预加载完成，自动加载结果", flush=True)
                self._load_cache()
        except Exception as e:
            print(f"[UI] 检查预加载状态失败: {e}", flush=True)

    def _create_title_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        title = QLabel('🎯 强势主力行为选股系统 V1.3')
        title.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 16px; font-weight: 700;')
        layout.addWidget(title)
        layout.addStretch()
        for name, color in [('涨停回调', '#22c55e'), ('箱体突破', '#eab308'), ('量价突破', '#ef4444')]:
            tag = QLabel(name)
            tag.setStyleSheet(f'background: {color}22; color: {color}; border: 1px solid {color}; '
                              f'border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;')
            layout.addWidget(tag)
        return bar

    def _create_toolbar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        self.btn_load_cache = QPushButton('⚡ 快速加载缓存')
        self.btn_load_cache.setStyleSheet(f"""
            QPushButton {{ background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_BLUE};
                border-radius: 6px; color: {ACCENT_BLUE}; padding: 6px 14px; font-weight: 600; }}
            QPushButton:hover {{ background: {ACCENT_BLUE}; color: white; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; }}
        """)
        self.btn_load_cache.clicked.connect(self._load_cache)
        layout.addWidget(self.btn_load_cache)

        self.btn_scan = QPushButton('🔄 重新全市场扫描')
        self.btn_scan.setStyleSheet(f"""
            QPushButton {{ background: {STATUS_SUCCESS}; border: 1px solid {ACCENT_GREEN};
                border-radius: 6px; color: {TEXT_PRIMARY}; padding: 6px 16px; font-weight: 700; }}
            QPushButton:hover {{ background: {ACCENT_GREEN}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; }}
        """)
        self.btn_scan.clicked.connect(self._start_scan)
        layout.addWidget(self.btn_scan)

        self.btn_refresh = QPushButton('🔃 刷新行情')
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{ background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_ORANGE};
                border-radius: 6px; color: {ACCENT_ORANGE}; padding: 6px 14px; font-weight: 600; }}
            QPushButton:hover {{ background: {ACCENT_ORANGE}; color: white; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; }}
        """)
        self.btn_refresh.clicked.connect(self._refresh_quotes)
        layout.addWidget(self.btn_refresh)

        layout.addWidget(QLabel('最低评分:'))
        self.combo_min_score = QComboBox()
        self.combo_min_score.addItems(['60分(观察池)', '70分(重点观察)', '80分(强势候选)'])
        self.combo_min_score.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; '
                                            f'border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px 6px;')
        layout.addWidget(self.combo_min_score)

        # V1.2：扫描模式选择
        layout.addWidget(QLabel('模式:'))
        self.combo_scan_mode = QComboBox()
        self.combo_scan_mode.addItems(['快速扫描(30日预筛)', '标准扫描(60日预筛)'])
        self.combo_scan_mode.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; '
                                            f'border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px 6px;')
        layout.addWidget(self.combo_scan_mode)

        # V1.1.1：测试单股票分析
        layout.addWidget(QLabel('诊断:'))
        self.input_test_code = QLineEdit()
        self.input_test_code.setPlaceholderText('股票代码 如000001')
        self.input_test_code.setFixedWidth(120)
        self.input_test_code.setStyleSheet(f'background: {BG_INTERACTIVE}; color: {TEXT_PRIMARY}; '
                                            f'border: 1px solid {BORDER_SOFT}; border-radius: 4px; padding: 3px 6px;')
        self.input_test_code.returnPressed.connect(self._diagnose_stock)
        layout.addWidget(self.input_test_code)

        self.btn_diagnose = QPushButton('🔍 测试分析')
        self.btn_diagnose.setStyleSheet(f"""
            QPushButton {{ background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_BLUE};
                border-radius: 4px; color: {ACCENT_BLUE}; padding: 4px 10px; font-size: 11px; }}
            QPushButton:hover {{ background: {ACCENT_BLUE}; color: white; }}
        """)
        self.btn_diagnose.clicked.connect(self._diagnose_stock)
        layout.addWidget(self.btn_diagnose)

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
        """V1.2.3：缓存状态条"""
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 4px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 3, 10, 3)
        self.cache_status_label = QLabel('缓存状态: 检查中...')
        self.cache_status_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        layout.addWidget(self.cache_status_label)
        layout.addStretch()
        return bar

    def _update_cache_status(self):
        """V1.2.3：更新缓存状态显示（V1.3增加数据源状态）"""
        try:
            # V1.3：获取数据源状态
            data_source_str = ""
            try:
                if self.strategy and hasattr(self.strategy, 'scanner') and self.strategy.scanner:
                    scanner = self.strategy.scanner
                    if hasattr(scanner, 'tdx_engine') and scanner.tdx_engine and scanner.tdx_engine.is_available():
                        stats = scanner.tdx_engine.get_memory_cache_stats()
                        latest = stats.get('latest_date', '')
                        data_source_str = (f"📡 数据源: ✅通达信本地 | "
                                           f"K线缓存: {stats['stock_count']}只/{stats['kline_total']}根 | "
                                           f"数据日期: {latest} | ")
                    else:
                        data_source_str = "📡 数据源: ⚠️网络API（通达信本地不可用） | "
            except Exception:
                data_source_str = "📡 数据源: 检测中... | "

            if self.strategy:
                info = self.strategy.get_cache_info()
                if info.get('exists'):
                    status = info.get('status', '未知')
                    scan_time = info.get('scan_time', '')
                    count = info.get('result_count', 0)
                    mode = info.get('scan_mode', '')
                    is_trading = info.get('is_trading_time', False)
                    trading_str = "交易时段" if is_trading else "非交易时段"
                    self.cache_status_label.setText(
                        f"{data_source_str}💾 最后扫描: {scan_time} | 缓存股票: {count}只 | 模式: {mode} | "
                        f"{trading_str} | 状态: {status}"
                    )
                    # 根据状态设置颜色
                    if "有效" in status:
                        self.cache_status_label.setStyleSheet(f'color: {ACCENT_GREEN}; font-size: 11px;')
                    elif "过期" in status or "失效" in status:
                        self.cache_status_label.setStyleSheet(f'color: {ACCENT_ORANGE}; font-size: 11px;')
                    else:
                        self.cache_status_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px;')
                else:
                    self.cache_status_label.setText(f'{data_source_str}💾 缓存状态: 无缓存 | 请点击"重新全市场扫描"开始')
                    self.cache_status_label.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 11px;')
        except Exception as e:
            self.cache_status_label.setText(f'💾 缓存状态读取失败: {e}')
            self.cache_status_label.setStyleSheet(f'color: {ACCENT_RED}; font-size: 11px;')

    def _create_funnel_bar(self):
        """V1.1新增：漏斗统计栏"""
        bar = QFrame()
        bar.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(12)

        self.funnel_labels = {}
        funnel_items = [
            ('全市场', 'total_market', TEXT_MUTED),
            ('主板', 'main_board_count', ACCENT_BLUE),
            ('L1基础', 'layer1_basic_filter', TEXT_SECONDARY),
            ('L2预筛', 'layer2_behavior_prescreen', '#3b82f6'),
            ('L3深度', 'layer3_deep_analysis', ACCENT_GOLD),
            ('涨停回调', 'model_limit_up', '#22c55e'),
            ('箱体突破', 'model_box', '#eab308'),
            ('量价突破', 'model_volume', '#ef4444'),
            ('60+', 'score_60_plus', ACCENT_GREEN),
            ('70+', 'score_70_plus', ACCENT_GOLD),
            ('80+', 'score_80_plus', '#f97316'),
            ('B1', 'buy_b1', '#3b82f6'),
            ('B2', 'buy_b2', '#22c55e'),
            ('B3', 'buy_b3', '#ef4444'),
            ('最终池', 'final_pool', ACCENT_GOLD),
            ('耗时s', 'time_total', TEXT_MUTED),
        ]
        for name, key, color in funnel_items:
            lbl = QLabel(f'{name}: --')
            lbl.setStyleSheet(f'color: {color}; font-size: 11px; font-weight: 600;')
            self.funnel_labels[key] = lbl
            layout.addWidget(lbl)
        layout.addStretch()
        return bar

    def _create_stock_pool_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel('📋 股票池（V1.3：按综合评分降序，60分以上显示）')
        header.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 13px; font-weight: 700;')
        layout.addWidget(header)

        # V1.1：14列完整字段
        self.table = QTableWidget()
        self.table.setStyleSheet(f"""
            QTableWidget {{ background: {BG_CONTAINER}; color: {TEXT_PRIMARY}; gridline-color: {BORDER};
                border: 1px solid {BORDER}; border-radius: 6px; alternate-background-color: {BG_PANEL_ALT}; }}
            QTableWidget::item {{ padding: 3px; border-bottom: 1px solid {BORDER}; }}
            QHeaderView::section {{ background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; padding: 4px;
                border: 1px solid {BORDER}; font-weight: 700; font-size: 10px; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); color: {TEXT_PRIMARY}; }}
        """)
        # V1.3.14：删除买点等级和风险等级两列，保留12列
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            '名称', '代码', '行业', '匹配模型', '模型评分', '综合评分',
            '当前阶段', '支撑位', '压力位',
            '买入信号', '风险提示', '评分等级'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        # V1.3.11：启用列头点击排序
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.cellClicked.connect(self._on_stock_selected)
        layout.addWidget(self.table, stretch=1)
        return panel

    def _create_detail_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.detail_title = QLabel('选择左侧股票查看详情')
        self.detail_title.setStyleSheet(f'color: {ACCENT_GOLD}; font-size: 14px; font-weight: 700;')
        layout.addWidget(self.detail_title)

        # V1.1：买卖点卡片
        self.signal_card = self._create_signal_card()
        layout.addWidget(self.signal_card)

        self.score_card = self._create_score_card()
        layout.addWidget(self.score_card)

        # K线6色标注区域
        kline_container = QFrame()
        kline_container.setStyleSheet(f"background: #0d1117; border: 1px solid {BORDER}; border-radius: 6px;")
        kline_layout = QVBoxLayout(kline_container)
        kline_layout.setContentsMargins(0, 0, 0, 0)

        # 6色图例
        legend = QHBoxLayout()
        legend.setContentsMargins(8, 4, 8, 4)
        for rtype, color in REGION_COLORS.items():
            dot = QLabel('●')
            dot.setStyleSheet(f'color: {color}; font-size: 11px;')
            name = QLabel(REGION_NAMES[rtype])
            name.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 9px;')
            legend.addWidget(dot)
            legend.addWidget(name)
        legend.addStretch()
        kline_layout.addLayout(legend)

        # V1.3.8：ECharts K线图（优先）或QLabel文本标注（降级）
        if ECHARTS_AVAILABLE:
            self.kline_widget = EChartsKlineWidget()
            self.kline_widget.setMinimumHeight(280)
            kline_layout.addWidget(self.kline_widget, stretch=1)
            # 标注文本区域（K线图下方）
            self.annotation_label = QLabel('选择股票后显示K线图和6色标注')
            self.annotation_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.annotation_label.setStyleSheet(f'color: {TEXT_PRIMARY}; background: #0d1117; font-size: 10px; padding: 6px; border-top: 1px solid {BORDER};')
            self.annotation_label.setMaximumHeight(80)
            self.annotation_label.setWordWrap(True)
            kline_layout.addWidget(self.annotation_label)
            # 兼容旧代码
            self.kline_placeholder = self.annotation_label
        else:
            self.kline_placeholder = QLabel('K线图区域\n（选择股票后加载6色标注）')
            self.kline_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.kline_placeholder.setStyleSheet(f'color: {TEXT_MUTED}; background: #0d1117; font-size: 13px;')
            self.kline_placeholder.setMinimumHeight(220)
            kline_layout.addWidget(self.kline_placeholder, stretch=1)
        layout.addWidget(kline_container, stretch=1)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(100)
        self.detail_text.setStyleSheet(f"""
            QTextEdit {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER};
                border-radius: 6px; padding: 6px; font-size: 11px; }}
        """)
        layout.addWidget(self.detail_text)
        return panel

    def _create_signal_card(self):
        """V1.1新增：买卖点信号卡片"""
        card = QFrame()
        card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 6px;")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(15)

        self.buy_label = QLabel('买点: --')
        self.buy_label.setStyleSheet(f'color: {ACCENT_GREEN}; font-size: 13px; font-weight: 700;')
        layout.addWidget(self.buy_label)

        self.sell_label = QLabel('卖点: --')
        self.sell_label.setStyleSheet(f'color: {ACCENT_RED}; font-size: 13px; font-weight: 700;')
        layout.addWidget(self.sell_label)

        self.risk_label = QLabel('风险: --')
        self.risk_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 700;')
        layout.addWidget(self.risk_label)

        self.price_label = QLabel('支撑/压力: --')
        self.price_label.setStyleSheet(f'color: {ACCENT_BLUE}; font-size: 12px;')
        layout.addWidget(self.price_label)
        layout.addStretch()
        return card

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

        self.score_level = QLabel('未评分')
        self.score_level.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600;')
        layout.addWidget(self.score_level)
        layout.addStretch()

        self.dim_labels = {}
        dims = [('主力', 'main_force_structure', 40), ('量价', 'volume_price', 20),
                ('趋势', 'trend_ma', 15), ('涨停', 'limit_up_gene', 10),
                ('指标', 'tech_indicator', 10), ('环境', 'market_env', 5)]
        for name, key, mx in dims:
            vbox = QVBoxLayout()
            lbl = QLabel(f'{name}\n0/{mx}')
            lbl.setStyleSheet(f'color: {TEXT_MUTED}; font-size: 9px;')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dim_labels[key] = lbl
            vbox.addWidget(lbl)
            layout.addLayout(vbox)
        return card

    # ===== 扫描逻辑 =====
    def _start_scan(self):
        if self.strategy is None:
            return
        if self.scan_worker and self.scan_worker.isRunning():
            return
        # V1.2.3：重新扫描前清除旧缓存
        try:
            self.strategy.clear_scan_cache()
        except Exception:
            pass
        min_score_map = {0: 60.0, 1: 70.0, 2: 80.0}
        min_score = min_score_map.get(self.combo_min_score.currentIndex(), 60.0)
        # V1.2：扫描模式
        mode_map = {0: "快速扫描", 1: "标准扫描"}
        scan_mode = mode_map.get(self.combo_scan_mode.currentIndex(), "快速扫描")
        self.btn_scan.setEnabled(False)
        self.btn_load_cache.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._scan_start_time = time.time()
        self.status_label.setText(f'正在{scan_mode}...')
        self.scan_worker = ScanWorker(self.strategy, min_score=min_score, scan_mode=scan_mode)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_scan.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _enrich_industry_info(self, results):
        """V1.3.15：从DuckDB补充行业信息（旧缓存可能没有industry字段）"""
        try:
            from data.duckdb_adapter import DuckDBAdapter
            _db = DuckDBAdapter()
            _basic_df = _db.get_stock_basic()
            if _basic_df is None or len(_basic_df) == 0:
                return
            _industry_map = {}
            for _, _row in _basic_df.iterrows():
                _ts = str(_row.get('ts_code', ''))
                _code = _ts.split('.')[0] if '.' in _ts else _ts
                _ind = _row.get('industry', '')
                if _code and _ind and str(_ind) != 'nan':
                    _industry_map[_code] = str(_ind)
            _hit = 0
            for r in results:
                _code = getattr(r, 'code', '') or (r.get('code') if isinstance(r, dict) else '')
                if _code in _industry_map:
                    _ind = _industry_map[_code]
                    if isinstance(r, dict):
                        if not r.get('industry'):
                            r['industry'] = _ind
                            _hit += 1
                    else:
                        if not getattr(r, 'industry', ''):
                            r.industry = _ind
                            _hit += 1
            print(f"[UI] 行业信息补充: 从DuckDB补充{_hit}/{len(results)}只股票的行业信息", flush=True)
        except Exception as e:
            print(f"[UI WARN] 行业信息补充失败: {e}", flush=True)

    def _load_cache(self):
        """V1.2.3：快速加载缓存"""
        if self.strategy is None:
            return
        self.status_label.setText('正在加载缓存...')
        QApplication.processEvents()
        try:
            start = time.time()
            results = self.strategy.load_cached_scan()
            elapsed = time.time() - start
            if results:
                # V1.3.15：缓存加载后补充行业信息（旧缓存可能没有industry字段）
                self._enrich_industry_info(results)
                self.current_results = results
                self._update_stock_table(results)
                try:
                    funnel = self.strategy.get_funnel_stats()
                    self._update_funnel(funnel)
                except Exception:
                    pass
                self.status_label.setText(
                    f'⚡ 缓存加载完成: {len(results)}只股票, 耗时{elapsed:.1f}秒')
                print(f"[UI] 缓存加载完成: {len(results)}只, 耗时{elapsed:.1f}秒", flush=True)
            else:
                info = self.strategy.get_cache_info()
                status = info.get('status', '无缓存')
                self.status_label.setText(f'缓存不可用({status})，请点击"重新全市场扫描"')
                print(f"[UI] 缓存不可用: {status}", flush=True)
        except Exception as e:
            self.status_label.setText(f'缓存加载失败: {e}')
            print(f"[UI ERROR] 缓存加载失败: {e}", flush=True)
        self._update_cache_status()

    def _refresh_quotes(self):
        """V1.2.3：刷新当前股票池行情"""
        if self.strategy is None:
            return
        if not self.current_results:
            self.status_label.setText('股票池为空，无法刷新行情')
            return
        self.btn_refresh.setEnabled(False)
        self.status_label.setText('正在刷新行情...')
        QApplication.processEvents()
        try:
            start = time.time()
            count = self.strategy.refresh_quotes(self.current_results)
            elapsed = time.time() - start
            self._update_stock_table(self.current_results)
            self.status_label.setText(f'🔃 行情刷新完成: {count}只, 耗时{elapsed:.1f}秒')
            print(f"[UI] 行情刷新完成: {count}只, 耗时{elapsed:.1f}秒", flush=True)
        except Exception as e:
            self.status_label.setText(f'行情刷新失败: {e}')
            print(f"[UI ERROR] 行情刷新失败: {e}", flush=True)
        finally:
            self.btn_refresh.setEnabled(True)

    def _on_scan_progress(self, c, t, n):
        if t > 0:
            self.progress_bar.setMaximum(t)
            self.progress_bar.setValue(c)
            elapsed = time.time() - getattr(self, '_scan_start_time', time.time())
            # n包含阶段信息，如"预筛:000001"或"深度:000001"
            stage = ""
            code = n
            if ':' in n:
                parts = n.split(':', 1)
                stage = parts[0]
                code = parts[1]
            stage_text = f" [{stage}]" if stage else ""
            pct = c / t * 100
            self.status_label.setText(f'扫描中{stage_text}: {c}/{t} ({pct:.0f}%) - {code} - {elapsed:.1f}s')

            # V1.3.2 实时更新漏斗统计栏（每50只更新一次，避免UI卡顿）
            if c % 50 == 0 or c == t:
                try:
                    funnel = self.strategy.get_funnel_stats()
                    if funnel:
                        self._update_funnel(funnel)
                except Exception:
                    pass

    def _on_scan_finished(self, results, funnel):
        """V1.2.1：增加信号链路调试日志"""
        print(f"[UI DEBUG] _on_scan_finished被调用, results={len(results)}只, "
              f"funnel类型={type(funnel).__name__}", flush=True)
        self.btn_scan.setEnabled(True)
        self.btn_load_cache.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.current_results = results
        self._update_stock_table(results)
        self._update_funnel(funnel)
        cnt = len(results)
        avg = sum(r.score.total for r in results) / cnt if cnt > 0 else 0
        elapsed = time.time() - getattr(self, '_scan_start_time', time.time())
        mode = funnel.get('扫描模式', '快速扫描') if isinstance(funnel, dict) else '快速扫描'
        self.stats_label.setText(f'股票池: {cnt}只 | 平均分: {avg:.1f} | 耗时: {elapsed:.1f}s')
        self.status_label.setText(f'{mode}完成 | 股票池{cnt}只 | 耗时{elapsed:.1f}s | 漏斗统计已更新')
        print(f"[UI DEBUG] 表格更新完成, 当前行数={self.table.rowCount()}", flush=True)
        # V1.2.3：更新缓存状态
        self._update_cache_status()

    def _on_scan_error(self, msg):
        self.btn_scan.setEnabled(True)
        self.btn_load_cache.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f'扫描失败: {msg}')
        self._update_cache_status()

    def _resolve_stock_code(self, keyword: str) -> tuple:
        """V1.3.12：将用户输入解析为股票代码

        Returns:
            (code, name) 或 (None, error_msg)
        """
        keyword = keyword.strip()
        if not keyword:
            return None, '请输入股票代码或名称'

        # 如果是6位数字，直接作为代码
        if len(keyword) == 6 and keyword.isdigit():
            return keyword, keyword

        # 从名称缓存查找
        import json, os
        cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  'data', 'cache', 'stock_names.json')
        names_map = {}
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    names_map = data.get('names', {})
        except Exception as e:
            print(f"[DIAG] 读取名称缓存失败: {e}", flush=True)

        # 精确匹配
        for code, name in names_map.items():
            if name == keyword:
                return code, name

        # 模糊匹配（包含关键词）
        matches = []
        for code, name in names_map.items():
            if keyword in name:
                matches.append((code, name))

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            # 多个匹配，返回前5个让用户选择
            options = '\n'.join([f'  {c} - {n}' for c, n in matches[:10]])
            return None, f'找到多个匹配，请输入更精确的名称或直接输入代码：\n{options}'

        # 名称缓存中找不到，尝试从当前股票池查找
        if hasattr(self, 'current_results') and self.current_results:
            for stock in self.current_results:
                if keyword in (stock.name or '') or keyword == stock.code:
                    return stock.code, stock.name

        return None, f'未找到股票：{keyword}，请尝试输入股票代码（如002838）'

    def _diagnose_stock(self):
        """V1.3.12：测试单股票完整诊断（支持名称搜索+模糊匹配）"""
        keyword = self.input_test_code.text().strip()
        if not keyword:
            QMessageBox.warning(self, '提示', '请输入股票代码或名称')
            return
        if self.strategy is None:
            QMessageBox.warning(self, '提示', '策略未初始化')
            return

        # V1.3.12：解析股票代码（支持名称搜索）
        code, resolved = self._resolve_stock_code(keyword)
        if code is None:
            QMessageBox.warning(self, '未找到', resolved)
            return
        if resolved != code:
            print(f"[DIAG] 名称搜索: {keyword} -> {code} {resolved}", flush=True)
            self.status_label.setText(f'正在诊断 {resolved}({code})...')
        else:
            self.status_label.setText(f'正在诊断 {code}...')
        self.btn_diagnose.setEnabled(False)

        try:
            diag = self.strategy.diagnose_stock(code)
        except Exception as e:
            QMessageBox.critical(self, '诊断失败', str(e))
            self.btn_diagnose.setEnabled(True)
            return

        self.btn_diagnose.setEnabled(True)

        # 构建诊断报告
        display_name = resolved if resolved != code else code
        lines = [f"=== 单股票诊断报告: {display_name}({code}) ===", ""]
        lines.append(f"诊断结果: {diag.get('result', '未知')}")
        lines.append(f"K线根数: {diag.get('bars_count', 0)}")
        lines.append(f"行为候选: {'是' if diag.get('behaviors') else '否'}")
        if diag.get('behaviors'):
            lines.append(f"  命中行为: {', '.join(diag['behaviors'])}")
        lines.append(f"匹配模型: {', '.join(diag.get('matched_models', [])) or '无'}")

        if diag.get('result') == '成功':
            lines.append(f"最佳模型: {diag.get('best_model', '-')} ({diag.get('best_model_score', 0):.0f}分)")
            lines.append(f"综合评分: {diag.get('score', 0):.1f} ({diag.get('score_level', '-')})")
            if diag.get('score_breakdown'):
                lines.append(f"  评分明细: {diag['score_breakdown']}")
            lines.append(f"当前阶段: {diag.get('current_stage', '-')}")
            lines.append(f"买点等级: {diag.get('buy_level', '-')}")
            if diag.get('buy_reasons'):
                lines.append(f"  买入理由: {'; '.join(diag['buy_reasons'])}")
            lines.append(f"卖点等级: {diag.get('sell_level', '-')}")
            lines.append(f"风险等级: {diag.get('risk_level', '-')}")
            lines.append(f"支撑位: {diag.get('support', 0):.2f}")
            lines.append(f"压力位: {diag.get('pressure', 0):.2f}")
        else:
            if diag.get('error'):
                lines.append(f"失败原因: {diag['error']}")
            if diag.get('kline_empty'):
                lines.append("  → K线数据为空")
            if diag.get('data_insufficient'):
                lines.append("  → 数据不足")
            if diag.get('no_candidate'):
                lines.append("  → 非行为候选（正常过滤）")

        report = "\n".join(lines)
        self.status_label.setText(f'诊断完成: {display_name}({code}) - {diag.get("result", "")}')

        # V1.3.12：诊断成功后在右侧显示K线图+标注+评分详情
        if diag.get('result') == '成功':
            self._show_diagnose_in_panel(code, display_name, diag)

        # 显示诊断报告
        msg = QMessageBox(self)
        msg.setWindowTitle(f'诊断报告 - {display_name}({code})')
        msg.setText(report)
        msg.setStyleSheet(f"""
            QMessageBox {{ background: {BG_PANEL}; color: {TEXT_PRIMARY}; }}
            QMessageBox QLabel {{ color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 12px; }}
            QPushButton {{ background: {ACCENT_BLUE}; color: white; padding: 6px 20px; border-radius: 4px; }}
        """)
        msg.exec()

    def _show_diagnose_in_panel(self, code: str, name: str, diag: dict):
        """V1.3.12：诊断成功后在右侧面板显示K线图+标注+评分详情"""
        try:
            print(f"[DIAG] 在右侧面板显示: {name}({code})", flush=True)
            # 更新标题
            self.detail_title.setText(f'{name} ({code})')

            # 更新信号卡片
            buy_level = diag.get('buy_level', '-')
            risk_level = diag.get('risk_level', '-')
            if hasattr(self, 'signal_value'):
                signal_text = f'{buy_level} | 风险:{risk_level}'
                self.signal_value.setText(signal_text)
                if 'B3' in buy_level:
                    self.signal_value.setStyleSheet(f'color: #ef4444; font-size: 16px; font-weight: 700;')
                elif 'B2' in buy_level:
                    self.signal_value.setStyleSheet(f'color: #22c55e; font-size: 16px; font-weight: 700;')
                elif 'B1' in buy_level:
                    self.signal_value.setStyleSheet(f'color: #3b82f6; font-size: 16px; font-weight: 700;')

            # 更新评分卡片
            score = diag.get('score', 0)
            score_level = diag.get('score_level', '-')
            if hasattr(self, 'score_value'):
                self.score_value.setText(f'{score:.1f}')
                if score >= 80:
                    self.score_value.setStyleSheet(f'color: #ef4444; font-size: 18px; font-weight: 700;')
                elif score >= 70:
                    self.score_value.setStyleSheet(f'color: #f59e0b; font-size: 18px; font-weight: 700;')
                elif score >= 60:
                    self.score_value.setStyleSheet(f'color: #22c55e; font-size: 18px; font-weight: 700;')

            # 获取K线数据并渲染（V1.3.16：300根K线，支持MA120均线显示）
            if ECHARTS_AVAILABLE and hasattr(self, 'kline_widget') and self.strategy:
                kline_data = self.strategy.get_kline_data(code, days=300)
                if kline_data:
                    self.kline_widget.set_kline_data(kline_data)
                    print(f"[DIAG] {code} K线图渲染成功: {len(kline_data.get('close', []))}根", flush=True)

                    # 叠加标注
                    annotations = {
                        'regions': diag.get('annotation_regions', []),
                        'markers': diag.get('annotation_markers', []),
                        'support': diag.get('support', 0),
                        'resistance': diag.get('pressure', 0),
                    }
                    from PyQt6.QtCore import QTimer
                    self._annotation_retry_count = 0
                    self._annotation_max_retry = 3
                    QTimer.singleShot(300, lambda: self._apply_annotations_with_retry(annotations, code))
                else:
                    print(f"[DIAG] {code} K线数据获取失败", flush=True)

            # 更新详情文本
            lines = [f'<b>{name}</b> ({code})', '']
            lines.append(f'<b>综合评分:</b> {score:.1f} ({score_level})')
            lines.append(f'<b>最佳模型:</b> {diag.get("best_model", "-")} ({diag.get("best_model_score", 0):.0f}分)')
            lines.append(f'<b>匹配模型:</b> {", ".join(diag.get("matched_models", [])) or "无"}')
            lines.append(f'<b>当前阶段:</b> {diag.get("current_stage", "-")}')
            lines.append(f'<b>买点等级:</b> {buy_level}')
            lines.append(f'<b>风险等级:</b> {risk_level}')
            lines.append(f'<b>支撑位:</b> {diag.get("support", 0):.2f}')
            lines.append(f'<b>压力位:</b> {diag.get("pressure", 0):.2f}')
            if diag.get('buy_reasons'):
                lines.append(f'<b>买入理由:</b> {"; ".join(diag["buy_reasons"])}')
            if diag.get('score_breakdown'):
                lines.append(f'<b>评分明细:</b> {diag["score_breakdown"]}')
            self.detail_text.setHtml('<br>'.join(lines))

        except Exception as e:
            print(f"[DIAG] 右侧面板显示异常: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _update_funnel(self, funnel):
        """V1.2：更新漏斗统计（支持浮点数耗时字段）"""
        for key, lbl in self.funnel_labels.items():
            val = funnel.get(key, 0)
            name = lbl.text().split(':')[0]
            if isinstance(val, float):
                lbl.setText(f'{name}: {val:.1f}')
            else:
                lbl.setText(f'{name}: {val}')

    def _update_stock_table(self, results):
        """V1.2.1：增加异常保护，防止单行数据异常导致整表更新失败"""
        print(f"[TABLE DEBUG] 接收数据: {len(results)}只", flush=True)
        if results:
            r0 = results[0]
            print(f"[TABLE DEBUG] 第一只: code={r0.code}, name={r0.name}, "
                  f"score={r0.score.total}, model={r0.best_model}", flush=True)

        # V1.3.11：记录当前选中的股票代码，排序后恢复选中
        selected_code = None
        current_row = self.table.currentRow()
        if current_row >= 0:
            code_item = self.table.item(current_row, 1)
            if code_item:
                selected_code = code_item.text()

        # V1.3.11：填充数据前禁用排序，避免逐行排序影响性能
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        success_count = 0
        for i, r in enumerate(results):
            try:
                self.table.insertRow(i)
                matched_names = [m.model_name for m in r.matched_models if m.matched]
                model_text = '、'.join(matched_names) if matched_names else '-'
                best_score = r.best_model_score if r.best_model_score else 0
                signal_text = '；'.join(r.buy_signal.buy_reasons[:1]) if r.buy_signal.buy_reasons else '-'
                risk_text = '；'.join(r.risk_warnings[:1]) if r.risk_warnings else '-'
                stage_text = r.current_stage or '-'
                buy_level = r.buy_signal.buy_level or '-'
                risk_level = r.buy_signal.risk_level or '-'
                support = r.support if r.support else 0.0
                pressure = r.pressure if r.pressure else 0.0

                # V1.3.11：买点等级排序权重（B3>B2>B1）
                buy_weight = 0
                if 'B3' in buy_level:
                    buy_weight = 3
                elif 'B2' in buy_level:
                    buy_weight = 2
                elif 'B1' in buy_level:
                    buy_weight = 1

                # V1.3.11：风险等级排序权重（高>中>低）
                risk_weight = 0
                if risk_level == '高':
                    risk_weight = 3
                elif risk_level == '中':
                    risk_weight = 2
                elif risk_level == '低':
                    risk_weight = 1

                # V1.3.11：每列数据（显示文本, 排序值）- V1.3.14删除买点等级和风险等级
                items_data = [
                    (r.name if r.name else r.code, r.name if r.name else r.code),  # 0 名称
                    (r.code, r.code),                                                # 1 代码
                    (r.industry or '-', r.industry or '-'),                          # 2 行业
                    (model_text, model_text),                                        # 3 匹配模型
                    (f'{best_score:.0f}', best_score),                               # 4 模型评分
                    (f'{r.score.total:.1f}', r.score.total),                         # 5 综合评分
                    (stage_text, stage_text),                                        # 6 当前阶段
                    (f'{support:.2f}', support),                                     # 7 支撑位
                    (f'{pressure:.2f}', pressure),                                   # 8 压力位
                    (signal_text, signal_text),                                      # 9 买入信号
                    (risk_text, risk_text),                                          # 10 风险提示
                    (r.score.level, r.score.level),                                  # 11 评分等级
                ]
                for j, (text, sort_val) in enumerate(items_data):
                    item = QTableWidgetItem(str(text))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    # V1.3.11：设置排序值（EditRole用于排序比较）
                    item.setData(Qt.ItemDataRole.EditRole, sort_val)
                    if j == 3 and matched_names:
                        if '涨停回调' in matched_names:
                            item.setForeground(QColor('#22c55e'))
                        elif '箱体突破' in matched_names:
                            item.setForeground(QColor('#eab308'))
                        elif '量价突破' in matched_names:
                            item.setForeground(QColor('#ef4444'))
                    if j == 5:
                        if r.score.total >= 80:
                            item.setForeground(QColor('#ef4444'))
                        elif r.score.total >= 70:
                            item.setForeground(QColor('#f59e0b'))
                        elif r.score.total >= 60:
                            item.setForeground(QColor('#22c55e'))
                        item.setFont(QFont('Arial', 10, QFont.Weight.Bold))
                    # V1.3.14：已删除买点等级(j==7)和风险等级(j==8)列的颜色设置
                    self.table.setItem(i, j, item)
                success_count += 1
            except Exception as e:
                print(f"[TABLE ERROR] 第{i}行({getattr(r, 'code', '?')})更新失败: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # 回滚已插入的行
                if self.table.rowCount() > i:
                    self.table.removeRow(i)

        # V1.3.11：填充完成后启用排序，默认按综合评分（第5列）降序
        self.table.setSortingEnabled(True)
        self.table.sortItems(5, Qt.SortOrder.DescendingOrder)

        # V1.3.11：恢复之前选中的股票
        if selected_code:
            for row in range(self.table.rowCount()):
                code_item = self.table.item(row, 1)
                if code_item and code_item.text() == selected_code:
                    self.table.selectRow(row)
                    break

        self.table.resizeColumnsToContents()
        print(f"[TABLE DEBUG] 表格更新完成: 成功{success_count}/{len(results)}行", flush=True)

    # ===== 表格排序 =====
    def _on_header_clicked(self, logical_index):
        """V1.3.11：列头点击排序，三态循环：升序→降序→取消(默认综合评分降序)"""
        header = self.table.horizontalHeader()
        current_sort_col = header.sortIndicatorSection()
        current_order = header.sortIndicatorOrder()

        if current_sort_col != logical_index:
            # 点击新列，默认升序
            self.table.sortItems(logical_index, Qt.SortOrder.AscendingOrder)
        elif current_order == Qt.SortOrder.AscendingOrder:
            # 升序→降序
            self.table.sortItems(logical_index, Qt.SortOrder.DescendingOrder)
        else:
            # 降序→取消排序，恢复默认按综合评分降序
            self.table.sortItems(5, Qt.SortOrder.DescendingOrder)

    # ===== 股票详情 =====
    def _on_stock_selected(self, row, col):
        if row < 0:
            return
        # V1.3.11：排序后通过代码查找股票，不依赖row索引
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
        self.detail_title.setText(f'{stock.name if stock.name else stock.code} ({stock.code}) | {stock.industry or "-"} | ¥{stock.price:.2f}')

        # V1.1：买卖点信号
        bs = stock.buy_signal
        self.buy_label.setText(f'买点: {bs.buy_level or "无"}')
        self.buy_label.setStyleSheet(f'color: {"#ef4444" if "B3" in bs.buy_level else "#22c55e" if "B2" in bs.buy_level else ACCENT_GREEN}; font-size: 13px; font-weight: 700;')
        self.sell_label.setText(f'卖点: {bs.sell_level or "无"}')
        self.risk_label.setText(f'风险: {bs.risk_level}')
        self.risk_label.setStyleSheet(f'color: {"#ef4444" if bs.risk_level=="高" else "#f59e0b" if bs.risk_level=="中" else TEXT_SECONDARY}; font-size: 13px; font-weight: 700;')
        self.price_label.setText(f'支撑: {stock.support:.2f} / 压力: {stock.pressure:.2f}')

        self._update_score_card(stock.score)
        self._update_kline_annotation(stock)
        self._update_detail_text(stock)

    def _update_score_card(self, score):
        self.score_total.setText(f'{score.total:.0f}')
        colors = {'启动候选': '#ef4444', '强势候选': '#f97316', '重点观察': '#f59e0b',
                  '观察池': '#22c55e', '低关注': TEXT_MUTED}
        color = colors.get(score.level, TEXT_SECONDARY)
        self.score_level.setText(score.level)
        self.score_level.setStyleSheet(f'color: {color}; font-size: 12px; font-weight: 600;')
        dim_max = {'main_force_structure': 40, 'volume_price': 20, 'trend_ma': 15,
                   'limit_up_gene': 10, 'tech_indicator': 10, 'market_env': 5}
        dim_names = {'main_force_structure': '主力', 'volume_price': '量价', 'trend_ma': '趋势',
                     'limit_up_gene': '涨停', 'tech_indicator': '指标', 'market_env': '环境'}
        for key, lbl in self.dim_labels.items():
            val = getattr(score, key, 0)
            mx = dim_max.get(key, 10)
            name = dim_names.get(key, key)
            lbl.setText(f'{name}\n{val:.0f}/{mx}')
            ratio = val / mx if mx > 0 else 0
            lbl.setStyleSheet(f'color: {"#22c55e" if ratio>=0.7 else "#f59e0b" if ratio>=0.4 else TEXT_MUTED}; font-size: 9px;')

    def _update_kline_annotation(self, stock):
        """V1.3.9：ECharts K线图渲染 + 标注叠加（6色区域+买卖点+支撑压力位）"""
        ann = stock.annotation

        # V1.3.8：优先渲染ECharts K线图（V1.3.16：300根K线，支持MA120均线显示）
        if ECHARTS_AVAILABLE and hasattr(self, 'kline_widget') and self.strategy:
            try:
                kline_data = self.strategy.get_kline_data(stock.code, days=300)
                if kline_data:
                    self.kline_widget.set_kline_data(kline_data)
                    print(f"[KLINE] {stock.code} ECharts K线图渲染成功: {len(kline_data.get('close', []))}根", flush=True)

                    # V1.3.11：延迟叠加标注（增加重试机制，确保K线图渲染完成）
                    annotations = {
                        'regions': ann.regions,
                        'markers': ann.markers,
                        'support': stock.support if stock.support else 0,
                        'resistance': stock.pressure if stock.pressure else 0,
                    }
                    # 打印标注数据调试信息
                    print(f"[ANNOTATION] {stock.code} 标注数据: 区域{len(ann.regions)}个, 标记{len(ann.markers)}个, "
                          f"支撑={stock.support}, 压力={stock.pressure}", flush=True)
                    for i, region in enumerate(ann.regions[:3]):
                        print(f"[ANNOTATION]   区域[{i}]: {region.get('label')} {region.get('start_date')}~{region.get('end_date')} color={region.get('color')}", flush=True)
                    for i, mk in enumerate(ann.markers[:3]):
                        print(f"[ANNOTATION]   标记[{i}]: {mk.get('level')} {mk.get('date')} price={mk.get('price')}", flush=True)

                    # V1.3.11：多次重试，确保K线图渲染完成后叠加标注
                    from PyQt6.QtCore import QTimer
                    self._annotation_retry_count = 0
                    self._annotation_max_retry = 3
                    QTimer.singleShot(300, lambda: self._apply_annotations_with_retry(annotations, stock.code))
                else:
                    print(f"[KLINE] {stock.code} K线数据获取失败", flush=True)
            except Exception as e:
                print(f"[KLINE] {stock.code} ECharts渲染异常: {e}", flush=True)

        # 标注文本信息（K线图下方或QLabel中）
        lines = [f'📊 K线6色标注（{len(ann.regions)}个区域，{len(ann.markers)}个标记）', '']
        for region in ann.regions:
            color = region.get('color', '#888')
            label = region.get('label', '')
            start = region.get('start_date', '')
            end = region.get('end_date', '')
            top = region.get('top')
            bottom = region.get('bottom')
            extra = f' [{bottom:.2f}-{top:.2f}]' if top and bottom else ''
            lines.append(f'  <span style="color:{color};">●</span> {label}: {start}~{end}{extra}')
        if ann.markers:
            lines.append('')
            lines.append('📍 标记:')
            for mk in ann.markers:
                mtype = mk.get('type', '')
                level = mk.get('level', '')
                label = mk.get('label', '')
                icon = '🟢' if mtype == 'buy' else '🔴' if mtype == 'sell' else '⚠️' if mtype == 'risk' else '📌'
                prefix = f'[{level}] ' if level else ''
                lines.append(f'  {icon} {prefix}{label}')

        # V1.3.8：富文本渲染（支持HTML span颜色）
        self.kline_placeholder.setTextFormat(Qt.TextFormat.RichText)
        self.kline_placeholder.setText('<br>'.join(lines))
        self.kline_placeholder.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.kline_placeholder.setStyleSheet(f'color: {TEXT_PRIMARY}; background: #0d1117; font-size: 10px; padding: 6px;')

    def _apply_annotations_with_retry(self, annotations: dict, code: str):
        """V1.3.11：带重试的标注叠加，确保K线图渲染完成后正确叠加"""
        try:
            if ECHARTS_AVAILABLE and hasattr(self, 'kline_widget'):
                self.kline_widget.set_annotations(annotations)
                self._annotation_retry_count += 1
                print(f"[ANNOTATION] {code} 标注叠加第{self._annotation_retry_count}次尝试完成: "
                      f"区域{len(annotations.get('regions', []))}个, "
                      f"标记{len(annotations.get('markers', []))}个", flush=True)

                # 如果还有重试次数，延迟后再次尝试（确保标注稳定显示）
                if self._annotation_retry_count < self._annotation_max_retry:
                    from PyQt6.QtCore import QTimer
                    delay = 500 * self._annotation_retry_count  # 500ms, 1000ms
                    QTimer.singleShot(delay, lambda: self._apply_annotations_with_retry(annotations, code))
        except Exception as e:
            print(f"[ANNOTATION] {code} 标注叠加异常: {e}", flush=True)
            self._annotation_retry_count += 1
            if self._annotation_retry_count < self._annotation_max_retry:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, lambda: self._apply_annotations_with_retry(annotations, code))

    def _apply_annotations(self, annotations: dict, code: str):
        """V1.3.9：应用标注叠加到ECharts K线图（保留兼容）"""
        try:
            if ECHARTS_AVAILABLE and hasattr(self, 'kline_widget'):
                self.kline_widget.set_annotations(annotations)
                print(f"[ANNOTATION] {code} 标注叠加完成: 区域{len(annotations.get('regions', []))}个, "
                      f"标记{len(annotations.get('markers', []))}个", flush=True)
        except Exception as e:
            print(f"[ANNOTATION] {code} 标注叠加异常: {e}", flush=True)

    def _update_detail_text(self, stock):
        lines = [f'<b>扫描时间:</b> {stock.scan_time}',
                 f'<b>最佳模型:</b> {stock.best_model}({stock.best_model_score:.0f}分)',
                 f'<b>当前阶段:</b> {stock.current_stage or "-"}', '']
        for m in stock.matched_models:
            status = '✅' if m.matched else '❌'
            lines.append(f'<b>{m.model_name}</b>: {status} {m.score:.0f}分 | {m.stage}')
            if m.matched and m.signals:
                lines.append(f'  信号: {"; ".join(m.signals)}')
            if m.matched and m.risks:
                lines.append(f'  风险: {"; ".join(m.risks)}')
        if stock.score.reason:
            lines.append(f'<b>评分理由:</b> {stock.score.reason}')
        self.detail_text.setHtml('<br>'.join(lines))

    def get_strategy(self):
        return self.strategy

    def get_current_results(self):
        return self.current_results

    def closeEvent(self, event):
        """V1.3.10：程序退出时正确关闭DuckDB连接和扫描线程"""
        try:
            # 停止扫描线程
            if self.scan_worker and self.scan_worker.isRunning():
                try:
                    self.scan_worker.terminate()
                    self.scan_worker.wait(2000)
                except Exception:
                    pass
            # 关闭DuckDB连接
            if self.strategy:
                try:
                    if hasattr(self.strategy, 'kline_db') and self.strategy.kline_db:
                        self.strategy.kline_db.close()
                        print("[ForceBehavior] DuckDB连接已关闭", flush=True)
                except Exception as e:
                    print(f"[ForceBehavior] 关闭DuckDB连接异常: {e}", flush=True)
                try:
                    if hasattr(self.strategy, 'cache_manager') and self.strategy.cache_manager:
                        if hasattr(self.strategy.cache_manager, 'close'):
                            self.strategy.cache_manager.close()
                except Exception:
                    pass
        except Exception:
            pass
        super().closeEvent(event)
