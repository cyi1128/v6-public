# -*- coding: utf-8 -*-
"""📈 策略看板 —— 独立页面：经典技术指标策略全市场扫描（对标 TickFlow Stock Panel）。

页面定位
--------
对标 TickFlow Stock Panel 的「选股」Tab：MA / MACD / RSI / KDJ 等内置策略扫全市场。
数据全在本地 kline_cache（与「控盘选股」同一批日K），不做网络兜底。

列（7 列）：股票名称 / 代码 / 现价 / 涨跌幅 / **命中策略**（可多条）/ 位置 / 数据日。
工具栏：7 个策略复选框（默认全选）+ 开始扫描 / 停止。
结果落 data/cache/strategy_panel.json，重开程序直接载入，不用再等。
"""
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .base import (BC, L, BattleModuleBase, make_table,
                   set_table_item, pct_color)

import services.strategy_scan_service as SS

PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '命中策略', '位置', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_HITS, C_POS, C_DATE) = range(PAGE_COL_N)
PAGE_WIDTHS = [100, 70, 72, 76, 320, 60, 96]

_BTN_STYLE = (f'QPushButton{{background:{BC.BG_CARD};color:{BC.TEXT};'
              f'border:1px solid {BC.BORDER};border-radius:4px;'
              f'padding:3px 10px;font-size:11px;}}'
              f'QPushButton:hover{{color:{BC.BLUE};border-color:{BC.BLUE};}}'
              f'QPushButton:disabled{{color:{BC.TEXT3};border-color:{BC.BORDER};}}')
_CHK_STYLE = f'QCheckBox{{color:{BC.TEXT2};font-size:11px;margin-right:8px;}}QCheckBox::indicator{{width:12px;height:12px;}}'
_BAR_STYLE = (f'QProgressBar{{background:{BC.BG_HEADER};border:1px solid {BC.BORDER};'
              f'border-radius:3px;height:10px;text-align:center;font-size:10px;color:{BC.TEXT2};}}'
              f'QProgressBar::chunk{{background:{BC.BLUE};border-radius:2px;}}')


class StrategyPanelWidget(BattleModuleBase):
    """策略看板页（独立顶层 Tab）"""

    stock_clicked = pyqtSignal(str, str)      # code, name
    _scan_progress = pyqtSignal(int, int, str)

    def __init__(self, parent=None):
        self._all_rows = []
        self._stats = {}
        self._scanning = False
        self._cancel = False
        super().__init__('📈 策略看板', parent)
        self._scan_progress.connect(self._on_scan_progress)

        outer = QTabWidget()
        outer.setStyleSheet('QTabBar::tab{padding:6px 16px;font-size:12px;}')

        # Tab0：市场看板（整屏仪表盘，对标 TickFlow 首页布局）
        try:
            from ui.battle_widgets.market_dashboard_widget import MarketDashboardWidget
            self._dash = MarketDashboardWidget()
            outer.addTab(self._dash, '市场看板')
            self._dash.stock_clicked.connect(lambda c, n: self.stock_clicked.emit(c, n))
        except Exception as e:
            import traceback; traceback.print_exc()
            outer.addTab(L('市场看板加载失败: %s' % e, BC.TEXT2, 11), '市场看板')

        # Tab1：策略扫描（原有内容）
        tab1 = QWidget()
        l1 = QVBoxLayout(tab1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(4)
        self._build_controls(l1)
        self._build_table(l1)
        outer.addTab(tab1, '策略扫描')

        # Tab2：盘后复盘（连板梯队 / 概念轮动 / 涨停·炸板，复用现有成熟模块）
        try:
            tab2 = self._build_review_tab()
            outer.addTab(tab2, '盘后复盘')
        except Exception as e:
            import traceback; traceback.print_exc()
            outer.addTab(L('盘后复盘加载失败: %s' % e, BC.TEXT2, 11), '盘后复盘')

        # Tab3：AI 复盘（本地 Ollama）
        try:
            from ui.battle_widgets.ai_review_widget import AiReviewWidget
            outer.addTab(AiReviewWidget(), 'AI 复盘')
        except Exception as e:
            import traceback; traceback.print_exc()
            outer.addTab(L('AI 复盘加载失败: %s' % e, BC.TEXT2, 11), 'AI 复盘')

        self.content_layout.addWidget(outer, 1)
        self._load_snapshot_into_ui()

    def _build_review_tab(self):
        """盘后复盘子页：直接复用程序里已有的三个成熟控件，不重复造数据引擎。
        连板梯队=LeaderLadderWidget，概念轮动=MarketRhythmWidget，涨停·炸板=LimitUpWidget
        （涨停控件按「炸板也不删」保留炸板股，故可看炸板翘板）。"""
        from ui.battle_widgets.leader_ladder_widget import LeaderLadderWidget
        from ui.battle_widgets.limit_up_widget import LimitUpWidget
        from ui.battle_widgets.market_rhythm_widget import MarketRhythmWidget
        tabs = QTabWidget()
        tabs.setStyleSheet('QTabBar::tab{padding:5px 14px;font-size:11px;}')
        self._review_widgets = []
        pages = [('连板梯队', LeaderLadderWidget()),
                 ('概念轮动', MarketRhythmWidget()),
                 ('涨停·炸板', LimitUpWidget())]
        for label, w in pages:
            tabs.addTab(w, label)
            self._review_widgets.append(w)
            sig = getattr(w, 'stock_clicked', None)
            if sig is not None:
                sig.connect(lambda c, n: self.stock_clicked.emit(c, n))
        return tabs

    # ================================================================
    # 工具栏
    # ================================================================
    def _build_controls(self, target):
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(L('策略：', BC.TEXT2, 11, True))
        self._chks = {}
        for key, name, desc in SS.STRATEGIES:
            c = QCheckBox(name)
            c.setStyleSheet(_CHK_STYLE)
            c.setChecked(True)
            c.setToolTip(desc)
            self._chks[key] = c
            bar.addWidget(c)
        bar.addSpacing(8)

        self._btn_start = QPushButton('开始扫描')
        self._btn_start.setStyleSheet(_BTN_STYLE)
        self._btn_start.clicked.connect(self._start_scan)
        bar.addWidget(self._btn_start)

        self._btn_stop = QPushButton('停止')
        self._btn_stop.setStyleSheet(_BTN_STYLE)
        self._btn_stop.clicked.connect(self._cancel_scan)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)

        bar.addStretch()

        self._progress = QProgressBar()
        self._progress.setFixedWidth(180)
        self._progress.setStyleSheet(_BAR_STYLE)
        self._progress.setVisible(False)
        bar.addWidget(self._progress)

        target.addLayout(bar)

    # ================================================================
    # 表格
    # ================================================================
    def _build_table(self, target):
        self.table = make_table(PAGE_COL_N, PAGE_HEADERS)
        for i, w in enumerate(PAGE_WIDTHS):
            if i == C_HITS:
                continue
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            C_HITS, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double)
        target.addWidget(self.table, 1)

    # ================================================================
    # 扫描
    # ================================================================
    def _selected_keys(self):
        return [k for k, c in self._chks.items() if c.isChecked()]

    def _start_scan(self):
        if self._scanning:
            return
        keys = self._selected_keys()
        if not keys:
            self.set_status('请至少勾选一个策略')
            return
        self._scanning = True
        self._cancel = False
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setVisible(True)
        self.set_status('正在读K线…')

        def job():
            return SS.scan_market(
                keys=keys,
                progress_cb=lambda d, t, m: self._scan_progress.emit(d, t, m),
                cancel_cb=lambda: self._cancel,
            )

        self.run_async(job, self._on_scan_ok,
                       lambda e: self._on_scan_fail(str(e)))

    def _cancel_scan(self):
        self._cancel = True
        self.set_status('正在停止…')

    def _on_scan_progress(self, done, total, msg):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(done)
        self.set_status(msg)

    def _on_scan_ok(self, payload):
        self._scanning = False
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setVisible(False)
        self._all_rows = payload.get('rows', [])
        self._stats = payload.get('stats', {})
        SS.save_snapshot(payload)
        self._render()
        s = self._stats
        per = ' ｜ '.join('%s %d' % (SS.KEY2NAME[k], v)
                          for k, v in (s.get('per_strategy') or {}).items() if v)
        self.set_status('命中 %d 只 ｜ 扫描 %d 只 ｜ 数据日 %s ｜ 耗时 %ss ｜ %s'
                        % (s.get('hits', 0), s.get('total', 0),
                           payload.get('data_date', ''), s.get('elapsed', 0), per))

    def _on_scan_fail(self, err):
        self._scanning = False
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setVisible(False)
        self.set_status('扫描失败: %s' % err)

    # ================================================================
    # 渲染
    # ================================================================
    def _render(self):
        rows = self._all_rows
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            set_table_item(self.table, i, C_NAME, r.get('name', ''))
            set_table_item(self.table, i, C_CODE, r.get('code', ''))
            set_table_item(self.table, i, C_PRICE, '%.2f' % r.get('price', 0),
                           align=Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignRight)
            pct = r.get('pct', 0)
            set_table_item(self.table, i, C_PCT, '%+.2f%%' % pct,
                           color=pct_color(pct),
                           align=Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignRight)
            hits_txt = ' + '.join(SS.KEY2NAME.get(k, k) for k in r.get('hits', []))
            set_table_item(self.table, i, C_HITS, hits_txt,
                           color=BC.BLUE if len(r.get('hits', [])) >= 2 else BC.TEXT2)
            set_table_item(self.table, i, C_POS, '%.2f' % r.get('pos', 0),
                           align=Qt.AlignmentFlag.AlignVCenter |
                           Qt.AlignmentFlag.AlignRight)
            set_table_item(self.table, i, C_DATE, r.get('date', ''))
        self.table.setSortingEnabled(True)

    def _load_snapshot_into_ui(self):
        snap = SS.load_snapshot()
        if not snap:
            self.set_status('尚未扫描（点「开始扫描」）')
            return
        self._all_rows = snap.get('rows', [])
        self._stats = snap.get('stats', {})
        self._render()
        self.set_status('快照 %s ｜ 命中 %d 只 ｜ 数据日 %s'
                        % (snap.get('saved_at', ''), len(self._all_rows),
                           snap.get('data_date', '')))

    def _on_cell_double(self, row, col):
        code = self.table.item(row, C_CODE).text() if self.table.item(row, C_CODE) else ''
        name = self.table.item(row, C_NAME).text() if self.table.item(row, C_NAME) else ''
        if code:
            self.stock_clicked.emit(code, name)
