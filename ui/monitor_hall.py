# -*- coding: utf-8 -*-
"""
实时监控大厅
股票列表 + 排序 + 信号筛选
"""
import ast
import json
import os
import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QComboBox,
    QLineEdit, QMenu, QDialog, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QTimer, QThread
from PyQt6.QtGui import QColor, QFont, QBrush, QDesktopServices

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_CARD_HOVER,
    BG_INTERACTIVE, BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE,
    ACCENT_RED, ACCENT_GREEN, ACCENT_GOLD, UP, DOWN,
)
from core.watchlist import get_watchlist_manager
from utils.wechat_push import get_wechat_pusher


class MonitorHallWidget(QWidget):
    """实时监控大厅"""

    stock_clicked = pyqtSignal(str, str)  # code, name

    # 所有信号标签
    ALL_SIGNALS = [
        '横盘筑底', '锐角', '五日线', '一阳穿5/10', '一阳穿三线',
        '倍量', '回踩', '注意买点', '主升启动买点',
        '负J', '穿K', '15K', 'KDJ金叉', '轴下金叉', '轴上金叉',
        '低价5k', '低价9k', '收盘5k', '收盘9k',
        '59线', '平行5', '买入',
        '共振', '回踩二十日',
        # 20日涨停记忆·回调后启动雷达
        '回调后启动', '今日启动', '20日涨停记忆'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stocks = []
        self.filtered_stocks = []
        self.current_signal_filter = None
        self.custom_signal_filters = self._load_custom_signal_filters()
        self.current_sort = ('pct_chg', True)  # 列名, 降序
        self._concept_load_token = 0
        self._loading_concepts = False  # 概念加载中标志，避免重复加载
        self._v76_score_thread = None
        self._v76_score_cache = {}  # code -> {score, grade, core_count, date}
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"""
            MonitorHallWidget {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # 标题
        title = QLabel('📊 实时监控大厅')
        title.setStyleSheet(f"""
            font-size: 15px;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            letter-spacing: 0.5px;
        """)
        toolbar.addWidget(title)

        toolbar.addStretch()

        # 搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('搜索股票代码/名称...')
        self.search_box.setFixedWidth(180)
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; padding: 5px 10px; color: {TEXT_PRIMARY};
                selection-background-color: rgba(90,169,255,0.35);
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT_BLUE};
            }}
        """)
        self.search_box.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_box)

        # 排序下拉
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            '涨跌幅降序', '涨跌幅升序', '价格降序', '价格升序',
            '成交量降序', '成交量升序', '换手率降序', '换手率升序'
        ])
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; padding: 5px 10px; color: {TEXT_PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {BG_PANEL_ALT}; border: 1px solid {BORDER};
                color: {TEXT_PRIMARY}; selection-background-color: rgba(90,169,255,0.22);
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toolbar.addWidget(self.sort_combo)

        # 扫描按钮
        self.scan_btn = QPushButton('🔍 全市场扫描')
        self.scan_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_CARD}; border: 1px solid {ACCENT_GREEN};
                border-radius: 6px; padding: 6px 14px; color: {TEXT_PRIMARY}; font-weight: 700;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; border-color: {BORDER}; }}
        """)
        toolbar.addWidget(self.scan_btn)

        # 推送按钮
        self.push_btn = QPushButton('📤 推送微信')
        self.push_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(90, 169, 255, 0.10); border: 1px solid {BORDER_STRONG};
                border-radius: 6px; padding: 6px 12px; color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: rgba(90, 169, 255, 0.18); border-color: {ACCENT_BLUE}; }}
        """)
        self.push_btn.clicked.connect(self._push_to_wechat)
        toolbar.addWidget(self.push_btn)

        # 设置按钮
        self.settings_btn = QPushButton('⚙')
        self.settings_btn.setFixedWidth(36)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; color: {TEXT_SECONDARY}; font-size: 14px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; color: {TEXT_PRIMARY}; border-color: {ACCENT_BLUE}; }}
        """)
        self.settings_btn.clicked.connect(self._show_wechat_settings)
        toolbar.addWidget(self.settings_btn)

        # 信号代码编辑按钮（唯一工具栏按钮）
        self.signal_config_btn = QPushButton('📝 信号代码编辑')
        self.signal_config_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 193, 7, 0.10); border: 1px solid {BORDER_STRONG};
                border-radius: 6px; color: #ffc107; font-size: 12px; font-weight: 700;
                padding: 6px 10px;
            }}
            QPushButton:hover {{ background: rgba(255, 193, 7, 0.18); border-color: #ffc107; }}
        """)
        self.signal_config_btn.clicked.connect(self._open_code_editor)
        toolbar.addWidget(self.signal_config_btn)

        layout.addLayout(toolbar)

        # 信号筛选栏
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)

        filter_label = QLabel('信号筛选:')
        filter_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        filter_bar.addWidget(filter_label)

        # 全部按钮
        self.all_btn = QPushButton('全部')
        self.all_btn.setCheckable(True)
        self.all_btn.setChecked(True)
        self.all_btn.setStyleSheet(self._filter_btn_style(True))
        self.all_btn.clicked.connect(lambda: self._on_signal_filter(None))
        filter_bar.addWidget(self.all_btn)

        # 信号按钮
        self.signal_buttons = {}
        for sig in self.ALL_SIGNALS:
            btn = QPushButton(sig)
            btn.setCheckable(True)
            btn.setStyleSheet(self._filter_btn_style(False))
            btn.clicked.connect(lambda checked, s=sig: self._on_signal_filter(s))
            self.signal_buttons[sig] = btn
            filter_bar.addWidget(btn)

        # 最优组合快捷按钮（基于回测结果）
        filter_bar.addSpacing(10)
        self.combo_buttons = {}
        preset_combos = [
            ('⭐五日线+回踩', ['五日线', '回踩'], '胜率50.5% 盈亏比1.19'),
            ('🏆一阳穿+回踩', ['一阳穿5/10', '回踩'], '胜率52.2% 盈亏比1.27'),
            ('📊三信号组合', ['回踩', '低价5k', '五日线'], '胜率50.6%'),
        ]
        for combo_name, combo_sigs, tip in preset_combos:
            btn = QPushButton(combo_name)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,193,7,0.15); color: #ffc107;
                    border: 1px solid rgba(255,193,7,0.4); border-radius: 4px;
                    padding: 3px 8px; font-size: 11px;
                }}
                QPushButton:hover {{ background: rgba(255,193,7,0.3); }}
                QPushButton:checked {{ background: rgba(255,193,7,0.4); border-color: #ffc107; }}
            """)
            btn.clicked.connect(lambda checked, sigs=combo_sigs: self._apply_preset_combo(sigs))
            self.combo_buttons[combo_name] = btn
            filter_bar.addWidget(btn)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # 股票表格
        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            '代码', '名称', '现价', '涨跌幅', '成交量', '换手率',
            '信号标签', '雷达等级', '雷达评分', '最近涨停', '主营业务', '关键价格'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)  # 启用点击列头排序
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CONTAINER}; gridline-color: {BORDER};
                color: {TEXT_PRIMARY}; border: 1px solid {BORDER};
                font-size: 12px; alternate-background-color: {BG_PANEL_ALT};
                selection-background-color: rgba(90,169,255,0.22);
                selection-color: {TEXT_PRIMARY};
                border-radius: 8px;
            }}
            QTableWidget::item {{ padding: 5px 4px; border-bottom: 1px solid {BORDER}; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); }}
            QHeaderView::section {{
                background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER}; border-left: none; border-top: none;
                padding: 7px 6px; font-weight: 700;
            }}
            QHeaderView::section:first {{ border-left: none; }}
        """)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

        # 监控中心仅保留真实股票表格，删除所有已废弃的仪表盘残留对象

        # 状态栏
        self.status_label = QLabel('就绪 | 共 0 只股票')
        self.status_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600; letter-spacing: 0.2px;')
        layout.addWidget(self.status_label)

    def _filter_btn_style(self, active):
        if active:
            return f"""
                QPushButton {{
                    background: rgba(90,169,255,0.20); border: 1px solid {ACCENT_BLUE};
                    border-radius: 5px; padding: 3px 8px; color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 700;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                    border-radius: 5px; padding: 3px 8px;
                    color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {BG_CARD_HOVER}; color: {TEXT_PRIMARY}; border-color: {BORDER_STRONG}; }}
                QPushButton:checked {{ background: rgba(90,169,255,0.20); color: {TEXT_PRIMARY}; border: 1px solid {ACCENT_BLUE}; }}
            """

    def update_stocks(self, stocks):
        """更新股票列表（过滤：主板、非ST、价格>=6元、最多1000只）"""
        print(f"[监控大厅] update_stocks输入: {len(stocks)}只")
        # 过滤：主板(60/000/001)、非ST、价格>=6元
        filtered = []
        for stock in stocks:
            code = str(stock.get('code', ''))
            name = str(stock.get('name', ''))
            price = float(stock.get('price', stock.get('close', 0)) or 0)
            # 主板：60开头沪市主板，000/001开头深市主板
            is_main_board = code.startswith('60') or code.startswith('000') or code.startswith('001')
            # 非ST：排除ST、*ST、S*ST
            is_st = 'ST' in name.upper()
            # 价格>=6元
            price_ok = price >= 6.0
            if is_main_board and not is_st and price_ok:
                filtered.append(stock)

        print(f"[监控大厅] 基础过滤后(主板非ST6元+): {len(filtered)}只")

        # 最多1000只：按涨跌幅降序取前1000
        if len(filtered) > 1000:
            filtered.sort(key=lambda s: float(s.get('pct_chg', s.get('change_percent', 0)) or 0), reverse=True)
            filtered = filtered[:1000]
            print(f"[监控大厅] 截断到1000只后: {len(filtered)}只")

        self.stocks = filtered
        # 应用缓存的V7.6评分
        self._apply_v76_cache()
        self._apply_filter_and_sort()
        print(f"[监控大厅] _apply_filter_and_sort后显示: {len(self.filtered_stocks)}只")
        # 注意：已停止V7.6/KDJ评分线程（用户要求不需要评分）
        # self._start_v76_score_calc()

    def _apply_v76_cache(self):
        """将缓存的V7.6评分应用到股票列表（不生成信号标签）"""
        for stock in self.stocks:
            code = stock.get('code', '')
            cached = self._v76_score_cache.get(code)
            if cached:
                stock['v76_score'] = cached.get('score', 0)
                stock['v76_grade'] = cached.get('grade', '')
                stock['v76_core_count'] = cached.get('core_count', 0)
                # KDJ评分缓存
                kdj_score = cached.get('kdj_score', 0)
                if kdj_score > 0:
                    stock['kdj_score'] = kdj_score
                    stock['kdj_grade'] = cached.get('kdj_grade', '')

    def _start_v76_score_calc(self):
        """启动后台V7.6评分计算线程"""
        # 停止之前的线程
        if self._v76_score_thread and self._v76_score_thread.isRunning():
            self._v76_score_thread.stop()
            self._v76_score_thread.wait(1000)

        # 只对有代码的股票计算
        codes = [s.get('code', '') for s in self.stocks if s.get('code')]
        if not codes:
            return

        from PyQt6.QtCore import QThread
        print(f"[V7.6评分] 线程启动，共{len(codes)}只股票")
        self._v76_score_thread = V76ScoreThread(codes, self._v76_score_cache)
        self._v76_score_thread.score_updated.connect(self._on_v76_score_updated)
        self._v76_score_thread.finished_all.connect(self._on_v76_score_finished)
        self._v76_score_thread.start()

    def _on_v76_score_updated(self, code, score_data):
        """单只股票评分更新（不生成V7.6/KDJ买点信号标签）"""
        self._v76_score_cache[code] = score_data
        # 更新当前股票列表中的对应股票
        for stock in self.stocks:
            if stock.get('code') == code:
                stock['v76_score'] = score_data.get('score', 0)
                stock['v76_grade'] = score_data.get('grade', '')
                stock['v76_core_count'] = score_data.get('core_count', 0)
                # KDJ策略评分
                kdj_score = score_data.get('kdj_score', 0)
                stock['kdj_score'] = kdj_score
                stock['kdj_grade'] = score_data.get('kdj_grade', '')

                # 回踩二十日信号
                ma20_pullback = score_data.get('ma20_pullback')
                if ma20_pullback and ma20_pullback.get('has_signal'):
                    sigs = stock.get('signal_names', [])
                    if isinstance(sigs, str):
                        sigs = [sigs]
                    if '回踩二十日' not in sigs:
                        sigs.append('回踩二十日')
                        stock['signal_names'] = sigs
                    stock['ma20_pullback_detail'] = ma20_pullback

                # 注意：共振信号不在此同步计算（会阻塞UI），
                # 改为在_on_v76_score_finished中批量异步计算
                break

    def _on_v76_score_finished(self, total_calculated):
        """全部评分计算完成"""
        # 评分分布统计
        all_scores = [s.get('v76_score', 0) for s in self.stocks if s.get('v76_score', 0) > 0]
        ge70 = sum(1 for s in all_scores if s >= 70)
        ge60 = sum(1 for s in all_scores if s >= 60)
        ge50 = sum(1 for s in all_scores if s >= 50)
        ge40 = sum(1 for s in all_scores if s >= 40)
        max_s = max(all_scores) if all_scores else 0
        avg_s = sum(all_scores) / len(all_scores) if all_scores else 0
        print(f"[V7.6评分] 计算完成: {total_calculated}只, 分布: >=70={ge70}, >=60={ge60}, >=50={ge50}, >=40={ge40}, 最高={max_s:.1f}, 平均={avg_s:.1f}")

        # KDJ评分统计
        kdj_scores = [s.get('kdj_score', 0) for s in self.stocks if s.get('kdj_score', 0) > 0]
        kdj_ge60 = sum(1 for s in kdj_scores if s >= 60)
        kdj_ge50 = sum(1 for s in kdj_scores if s >= 50)
        kdj_max = max(kdj_scores) if kdj_scores else 0
        print(f"[KDJ评分] 分布: >=60={kdj_ge60}, >=50={kdj_ge50}, 最高={kdj_max:.1f}")

        # 重新应用筛选和排序，刷新表格
        self._apply_filter_and_sort()
        # 注意：已停止V7.6/KDJ评分，不再显示V7.6信号数量

        # 批量异步计算共振信号（不阻塞UI）
        self._calc_resonance_batch_async()

    def _calc_resonance_batch_async(self):
        """批量异步计算所有股票的共振信号（后台线程，不阻塞UI）"""
        import threading
        stocks_copy = list(self.stocks)  # 复制避免线程安全问题

        def _do_calc():
            try:
                from strategy.resonance_signals import calc_resonance_signal
                count = 0
                for stock in stocks_copy:
                    try:
                        resonance = calc_resonance_signal(stock)
                        if resonance.get('has_signal'):
                            sigs = stock.get('signal_names', [])
                            if isinstance(sigs, str):
                                sigs = [sigs]
                            if '共振' not in sigs:
                                sigs.append('共振')
                                stock['signal_names'] = sigs
                            stock['resonance_detail'] = resonance
                            count += 1
                    except Exception:
                        continue
                print(f"[共振信号] 批量计算完成: {count}只触发共振信号")
                # 计算完成后刷新表格
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._apply_filter_and_sort())
            except Exception as e:
                print(f"[共振信号] 批量计算失败: {e}")

        threading.Thread(target=_do_calc, daemon=True).start()

    def _resolve_concept_text(self, stock):
        """优先返回真实概念数据；如果没有数据则返回 '--'，不返回假加载态。"""
        concept_text = stock.get('concept_text')
        if isinstance(concept_text, str) and concept_text.strip() and concept_text.strip() not in {'加载中...', '暂无概念', '概念接口异常'}:
            return concept_text.strip()

        concept_value = stock.get('concept')
        if isinstance(concept_value, list):
            cleaned = []
            for item in concept_value:
                if isinstance(item, str):
                    item = item.strip()
                    if item and item not in {'--', '暂无概念', '概念接口异常'}:
                        cleaned.append(item)
            if cleaned:
                return ' | '.join(cleaned[:8])
        elif isinstance(concept_value, str):
            cleaned = concept_value.strip()
            if cleaned and cleaned not in {'--', '暂无概念', '概念接口异常'}:
                return cleaned

        return '--'

    def _apply_filter_and_sort(self):
        """应用筛选和排序，确保空值与非标准数据不会造成筛选失效或卡顿。"""
        filtered = []
        search_text = (self.search_box.text() or '').strip().lower()
        filter_values = self.current_signal_filter
        if isinstance(filter_values, str):
            filter_values = [filter_values]
        elif filter_values is None:
            filter_values = []
        else:
            filter_values = list(filter_values)

        for stock in self.stocks:
            if not isinstance(stock, dict):
                continue

            # 搜索筛选：代码/名称都支持，且不会因为 None 触发异常
            if search_text:
                code = str(stock.get('code', '') or '').lower()
                name = str(stock.get('name', '') or '').lower()
                if search_text not in code and search_text not in name:
                    continue

            # 剔除无信号股票：只显示有至少1个信号标签的股票
            signal_names = stock.get('signal_names', [])
            if isinstance(signal_names, str):
                signal_names = [signal_names] if signal_names else []
            elif not isinstance(signal_names, (list, tuple, set)):
                signal_names = []
            if not signal_names or len(signal_names) == 0:
                continue

            # 信号筛选：兼容 list / tuple / str 等输入
            if filter_values:
                # AND逻辑：同时包含所有选中信号
                if not all(name in signal_names for name in filter_values):
                    continue

            filtered.append(stock)

        sort_key, reverse = self.current_sort
        try:
            filtered.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=reverse)
        except Exception:
            filtered.sort(key=lambda x: float(x.get(sort_key, 0) or 0), reverse=reverse)

        self.filtered_stocks = filtered
        self._refresh_table()

    def _refresh_table(self):
        """刷新表格显示"""
        self.table.setSortingEnabled(False)  # 刷新时暂时禁用排序
        self.table.setRowCount(len(self.filtered_stocks))

        for row, stock in enumerate(self.filtered_stocks):
            code = stock.get('code', '')
            name = stock.get('name', '')
            price = stock.get('price', 0)
            pct_chg = stock.get('pct_chg', 0)
            volume = stock.get('volume', 0)
            turnover = stock.get('turnover', 0)
            ai_score = stock.get('ai_score', 0)
            v76_score = stock.get('v76_score', 0)
            v76_grade = stock.get('v76_grade', '')
            trend = stock.get('trend', '')
            signals = stock.get('signal_names', [])

            # 代码
            item = QTableWidgetItem(code)
            item.setForeground(QBrush(QColor('#8b949e')))
            self.table.setItem(row, 0, item)

            # 名称
            item = QTableWidgetItem(name)
            item.setForeground(QBrush(QColor('#f0f6fc')))
            self.table.setItem(row, 1, item)

            # 用真实时间判断是否连续竞价时段（9:30-11:30, 13:00-15:00）
            # 集合竞价(9:15-9:25)和盘前/午休/盘后，数据可能为0
            from datetime import datetime, time as dt_time
            current_time = datetime.now().time()
            is_continuous_trading = (
                (dt_time(9, 30) <= current_time <= dt_time(11, 30)) or
                (dt_time(13, 0) <= current_time <= dt_time(15, 0))
            )
            # 非连续竞价时段，如果pct_chg=0且volume=0，显示"--"
            is_non_trading_zero = (not is_continuous_trading) and (pct_chg == 0 and volume == 0)

            # 现价
            item = QTableWidgetItem(f'{price:.2f}')
            item.setData(Qt.ItemDataRole.UserRole, price)  # 用于数值排序
            color = '#f85149' if pct_chg >= 0 else '#3fb950'
            item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 2, item)

            # 涨跌幅
            pct_text = "--" if is_non_trading_zero else f'{pct_chg:+.2f}%'
            item = QTableWidgetItem(pct_text)
            item.setData(Qt.ItemDataRole.UserRole, pct_chg)
            item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 3, item)

            # 成交量
            if is_non_trading_zero:
                vol_text = "--"
            else:
                vol_text = f'{volume/10000:.0f}万' if volume >= 10000 else f'{volume:.0f}'
            item = QTableWidgetItem(vol_text)
            item.setData(Qt.ItemDataRole.UserRole, volume)
            item.setForeground(QBrush(QColor('#8b949e')))
            self.table.setItem(row, 4, item)

            # 换手率
            turnover_text = "--" if is_non_trading_zero else f'{turnover:.2f}%'
            item = QTableWidgetItem(turnover_text)
            item.setData(Qt.ItemDataRole.UserRole, turnover)
            item.setForeground(QBrush(QColor('#8b949e')))
            self.table.setItem(row, 5, item)

            # 信号标签
            sig_text = ' '.join([f'[{s}]' for s in signals[:5]])
            item = QTableWidgetItem(sig_text)
            item.setForeground(QBrush(QColor('#d29922')))
            self.table.setItem(row, 6, item)

            # 雷达等级
            radar_grade = stock.get('radar_grade', '')
            grade_color = {'S': '#f85149', 'A': '#d29922', 'B': '#58a6ff', 'C': '#8b949e'}.get(radar_grade, '#8b949e')
            item = QTableWidgetItem(radar_grade if radar_grade else '--')
            item.setForeground(QBrush(QColor(grade_color)))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 7, item)

            # 雷达评分
            radar_score = stock.get('radar_score', 0)
            item = QTableWidgetItem(f'{radar_score:.0f}' if radar_score > 0 else '--')
            item.setData(Qt.ItemDataRole.UserRole, radar_score)
            score_color = QColor('#d29922') if radar_score >= 60 else QColor('#8b949e')
            item.setForeground(QBrush(score_color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 8, item)

            # 最近涨停
            last_limit = stock.get('radar_last_limit_date', '')
            limit_count = stock.get('radar_limit_count', 0)
            limit_text = f'{last_limit}({limit_count}次)' if last_limit else '--'
            item = QTableWidgetItem(limit_text)
            limit_color = QColor('#f85149') if last_limit else QColor('#8b949e')
            item.setForeground(QBrush(limit_color))
            self.table.setItem(row, 9, item)

            # 主营业务：从缓存获取，显示前30字；空缓存显示"加载中..."
            from utils.main_business_service import get_main_business_service
            biz_service = get_main_business_service()
            biz = stock.get('main_business', '') or biz_service.get_main_business(code)
            if biz:
                stock['main_business'] = biz
                business_text = biz[:30] + '...' if len(biz) > 30 else biz
                stock['business_text'] = business_text
            else:
                business_text = '加载中...'
                stock['business_text'] = '加载中...'
            item = QTableWidgetItem(business_text)
            if business_text == '加载中...':
                item.setForeground(QBrush(QColor('#6e7681')))
            elif business_text == '--':
                item.setForeground(QBrush(QColor('#8b949e')))
            else:
                item.setForeground(QBrush(QColor('#58a6ff')))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 10, item)

            # 关键价格（买入区域，tooltip显示完整信息）
            try:
                from utils.key_price_calculator import get_key_price_calculator
                calculator = get_key_price_calculator()
                key_price = calculator.calculate(code, price)
                buy_zone = key_price.get('buy_zone', '--')
                item = QTableWidgetItem(buy_zone)
                item.setForeground(QBrush(QColor('#3fb950')))
                tooltip = (
                    f"💰 关键价格\n"
                    f"买入区域: {key_price.get('buy_zone', '--')}\n"
                    f"止损位: {key_price.get('stop_loss', '--')}\n"
                    f"压力位: {key_price.get('resistance', '--')}\n"
                    f"第一目标: {key_price.get('target1', '--')}\n"
                    f"第二目标: {key_price.get('target2', '--')}\n"
                    f"风险回报比: 1:{key_price.get('risk_reward', 0)}"
                )
                item.setToolTip(tooltip)
            except Exception:
                item = QTableWidgetItem('--')
            self.table.setItem(row, 11, item)

        # 调整列宽
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 200)
        self.table.setColumnWidth(7, 60)   # 雷达等级
        self.table.setColumnWidth(8, 60)   # 雷达评分
        self.table.setColumnWidth(9, 110)  # 最近涨停
        self.table.setColumnWidth(10, 200) # 主营业务
        self.table.setColumnWidth(11, 130) # 关键价格

        # 异步加载主营业务
        self._load_main_business_async()

        # 更新状态
        total = len(self.stocks)
        shown = len(self.filtered_stocks)
        # 组合筛选显示
        cf = self.current_signal_filter
        if isinstance(cf, (list, tuple, set)) and len(cf) > 1:
            filter_info = f' | 组合筛选: {" + ".join(sorted(cf))}'
        elif isinstance(cf, str) and cf:
            filter_info = f' | 筛选: {cf}'
        else:
            filter_info = ''
        self.status_label.setText(f'共 {total} 只 | 显示 {shown} 只{filter_info}')

        self.table.setSortingEnabled(True)  # 恢复排序

    @staticmethod
    def _extract_signal_names_from_code(payload):
        """从代码块/字符串中抽取信号名称列表。"""
        if not payload:
            return []
        cleaned = str(payload).strip()

        for expr in [cleaned, cleaned.replace('\\n', '\n')]:
            try:
                parsed = ast.literal_eval(expr)
                if isinstance(parsed, (list, tuple, set)):
                    values = []
                    for item in parsed:
                        if isinstance(item, str):
                            item = item.strip()
                            if item and item not in values:
                                values.append(item)
                    if values:
                        return values
            except Exception:
                pass

        matches = re.findall(r"['\"]([^'\"\n]+?)['\"]", cleaned)
        if matches:
            values = []
            for item in matches:
                item = item.strip()
                if item and item not in values:
                    values.append(item)
            if values:
                return values

        values = []
        for line in cleaned.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            for part in re.split(r"[，,;；\n]+", line):
                part = part.strip().strip("'\"[](){}")
                if part and part not in values:
                    values.append(part)
        return values

    @staticmethod
    def _parse_manual_signal_filter_text(raw_text):
        """解析人工输入的信号筛选文本。"""
        if raw_text is None:
            return []
        text = str(raw_text).strip()
        if not text:
            return []

        extracted = MonitorHallWidget._extract_signal_names_from_code(text)
        if extracted:
            return extracted

        values = []
        for part in re.split(r"[\n,，;；]+", text):
            value = part.strip().strip("'\"")
            if value and value not in values:
                values.append(value)
        return values

    def _load_custom_signal_filters(self):
        """加载本地自定义信号筛选配置。"""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, 'custom_signal_filters.json')
        if not os.path.exists(config_path):
            return []
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _save_custom_signal_filters(self, signal_names):
        """保存自定义信号筛选配置。"""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, 'custom_signal_filters.json')
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(signal_names, f, ensure_ascii=False, indent=2)
            self.custom_signal_filters = signal_names
            return True
        except Exception:
            return False

    def _open_code_editor(self):
        """打开源代码编辑器对话框"""
        try:
            from ui.code_editor_dialog import CodeEditorDialog
            dialog = CodeEditorDialog(self, default_file='monitor_hall.py')
            dialog.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, '编辑器错误', f'无法打开代码编辑器：{e}')

    def _show_custom_signal_editor(self):
        """弹出自定义信号编辑器对话框。"""
        dialog = QDialog(self)
        dialog.setWindowTitle('自定义信号筛选 - 手动编辑并上传')
        dialog.resize(560, 380)
        dialog.setStyleSheet(f"""
            QDialog {{ background: {BG_WINDOW}; color: {TEXT_PRIMARY}; }}
            QLabel {{ color: {TEXT_PRIMARY}; }}
            QTextEdit, QLineEdit {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; color: {TEXT_PRIMARY}; padding: 8px;
            }}
            QPushButton {{
                background: {ACCENT_BLUE}; border: none; border-radius: 6px;
                color: white; font-weight: 700; padding: 7px 14px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel('输入信号名称（支持一行一个 / 用逗号分隔 / 代码列表）')
        label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 12px;')
        layout.addWidget(label)

        editor = QTextEdit()
        editor.setPlaceholderText("示例：\n倍量\n买入\nKDJ金叉\n['底部吸筹', 'MACD金叉']")
        if isinstance(self.current_signal_filter, (list, tuple, set)):
            editor.setPlainText('\n'.join(self.current_signal_filter))
        elif isinstance(self.current_signal_filter, str):
            editor.setPlainText(self.current_signal_filter)
        elif self.custom_signal_filters:
            editor.setPlainText('\n'.join(self.custom_signal_filters))
        layout.addWidget(editor)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        preview_btn = QPushButton('预览解析')
        preview_btn.clicked.connect(lambda: self._preview_manual_signal_filter(editor, dialog))
        btn_layout.addWidget(preview_btn)

        save_btn = QPushButton('保存并应用')
        save_btn.clicked.connect(lambda: self._handle_custom_signal_submit(editor, dialog))
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)
        dialog.exec()

    def _preview_manual_signal_filter(self, editor, dialog):
        """预览自定义信号解析结果。"""
        signals = self._parse_manual_signal_filter_text(editor.toPlainText())
        if not signals:
            QMessageBox.warning(dialog, '提示', '没有解析出可用信号，请检查输入格式。')
            return
        preview = '、'.join(signals[:10]) + ('...' if len(signals) > 10 else '')
        QMessageBox.information(dialog, '预览结果', preview)

    def _handle_custom_signal_submit(self, editor, dialog):
        """保存并应用自定义信号筛选。"""
        signals = self._parse_manual_signal_filter_text(editor.toPlainText())
        if not signals:
            QMessageBox.warning(dialog, '提示', '请输入至少一个有效信号名称。')
            return

        if not self._save_custom_signal_filters(signals):
            QMessageBox.critical(dialog, '失败', '保存自定义信号失败。')
            return

        self.current_signal_filter = signals if len(signals) > 1 else signals[0]
        self._on_signal_filter(self.current_signal_filter)
        self.status_label.setText(f'自定义信号已保存并应用：{signals[:5]}')
        dialog.accept()
        QMessageBox.information(self, '成功', f'已上传 {len(signals)} 个自定义信号筛选条件。')

    def _on_search(self, text):
        self._apply_filter_and_sort()

    def _on_sort_changed(self, index):
        sort_map = [
            ('pct_chg', True), ('pct_chg', False),
            ('price', True), ('price', False),
            ('volume', True), ('volume', False),
            ('turnover', True), ('turnover', False),
            ('ai_score', True), ('ai_score', False),
            ('v76_score', True), ('v76_score', False),
            ('kdj_score', True), ('kdj_score', False),
        ]
        if index < len(sort_map):
            self.current_sort = sort_map[index]
            self._apply_filter_and_sort()

    def _on_signal_filter(self, signal):
        """信号筛选：普通点击=单选，Ctrl+点击=多选（AND逻辑）"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        modifiers = QApplication.keyboardModifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        if is_ctrl:
            # 多选模式：添加/移除
            current = self.current_signal_filter
            if isinstance(current, str):
                selected = {current} if current else set()
            elif isinstance(current, (list, tuple, set)):
                selected = set(current)
            else:
                selected = set()
            if signal in selected:
                selected.remove(signal)
            else:
                selected.add(signal)
            if not selected:
                self.current_signal_filter = None
            elif len(selected) == 1:
                self.current_signal_filter = list(selected)[0]
            else:
                self.current_signal_filter = list(selected)
        else:
            # 单选模式
            self.current_signal_filter = signal

        # 更新按钮状态
        is_all = self.current_signal_filter is None or (
            isinstance(self.current_signal_filter, (list, tuple, set)) and not self.current_signal_filter
        )
        self.all_btn.setChecked(is_all)
        self.all_btn.setStyleSheet(self._filter_btn_style(is_all))

        current_filter = self.current_signal_filter
        if isinstance(current_filter, str):
            active_set = {current_filter}
        elif isinstance(current_filter, (list, tuple, set)):
            active_set = set(current_filter)
        else:
            active_set = set()

        for sig, btn in self.signal_buttons.items():
            is_active = sig in active_set
            btn.setChecked(is_active)
            btn.setStyleSheet(self._filter_btn_style(is_active))

        # 重置组合按钮状态
        for btn in self.combo_buttons.values():
            btn.setChecked(False)

        self._apply_filter_and_sort()

    def _apply_preset_combo(self, sigs):
        """应用预设组合筛选"""
        self.current_signal_filter = list(sigs)
        # 更新信号按钮状态
        for sig, btn in self.signal_buttons.items():
            is_active = sig in sigs
            btn.setChecked(is_active)
            btn.setStyleSheet(self._filter_btn_style(is_active))
        self.all_btn.setChecked(False)
        self.all_btn.setStyleSheet(self._filter_btn_style(False))
        # 高亮选中的组合按钮
        for name, btn in self.combo_buttons.items():
            btn.setChecked(False)
        self._apply_filter_and_sort()

    def _load_main_business_async(self):
        """异步批量加载股票主营业务；分批加载避免API限流，覆盖所有显示股票。"""
        # 超时保护：如果加载标志超过60秒仍为True，强制重置（防止异常卡住）
        import time
        if self._loading_concepts:
            if hasattr(self, '_loading_start_time') and (time.time() - self._loading_start_time) > 60:
                print(f"[主营业务] 加载超时，强制重置标志")
                self._loading_concepts = False
            else:
                return

        from utils.main_business_service import get_main_business_service
        biz_service = get_main_business_service()

        codes_need = []
        for stock in self.filtered_stocks:
            code = str(stock.get('code', '') or '').strip()
            if code and not biz_service.has_cached(code):
                codes_need.append(code)

        if not codes_need:
            # 所有股票都有缓存，直接更新表格
            self._update_all_business_cells()
            return

        self._loading_concepts = True
        self._loading_start_time = time.time()
        token = self._concept_load_token = self._concept_load_token + 1
        codes_need = list(dict.fromkeys(codes_need))
        total = len(codes_need)
        print(f"[主营业务] 开始加载 {total} 只股票主营业务，分批处理（每批20只，间隔0.5秒）")

        def _do_load():
            try:
                batch_size = 20
                loaded = 0
                success_count = 0
                fail_count = 0
                for i in range(0, total, batch_size):
                    if token != self._concept_load_token:
                        return
                    batch = codes_need[i:i+batch_size]
                    biz_map = {}
                    for code in batch:
                        if token != self._concept_load_token:
                            return
                        try:
                            biz = biz_service.fetch_main_business(code)
                            if biz and len(biz) > 2:
                                biz_map[code] = biz
                                success_count += 1
                                if success_count <= 3:
                                    print(f"[主营业务] 成功 {code}: {biz[:40]}")
                            else:
                                biz_map[code] = '--'
                                fail_count += 1
                        except Exception as e:
                            biz_map[code] = '--'
                            fail_count += 1
                            if fail_count <= 3:
                                print(f"[主营业务] 失败 {code}: {e}")
                    loaded += len(batch)
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda m=biz_map: self._update_business_cells(m))
                    print(f"[主营业务] 进度: {loaded}/{total} (成功{success_count}, 失败{fail_count})")
                    if i + batch_size < total:
                        import time
                        time.sleep(0.5)
                print(f"[主营业务] 完成: {loaded}/{total} (成功{success_count}, 失败{fail_count})")
            except Exception as e:
                print(f"[主营业务] 加载失败: {e}")
            finally:
                self._loading_concepts = False

        import threading
        threading.Thread(target=_do_load, daemon=True).start()

    def _update_business_cells(self, biz_map):
        """更新主营业务单元格"""
        from utils.main_business_service import get_main_business_service
        biz_service = get_main_business_service()
        for row, stock in enumerate(self.filtered_stocks):
            code = stock.get('code', '')
            if code in biz_map:
                value = biz_map[code]
            else:
                value = biz_service.get_main_business(code)
            if value and value != '--':
                stock['main_business'] = value
                # 主营业务可能很长，表格显示前30字
                display = value[:30] + '...' if len(value) > 30 else value
                stock['business_text'] = display
            else:
                stock['main_business'] = ''
                stock['business_text'] = '--'
            item = self.table.item(row, 7)  # 主营业务列（索引7）
            if item:
                item.setText(stock.get('business_text', '--'))
                item.setForeground(QBrush(QColor('#58a6ff' if stock.get('business_text', '--') != '--' else '#8b949e')))

    def _update_all_business_cells(self):
        """从缓存更新所有主营业务单元格"""
        from utils.main_business_service import get_main_business_service
        biz_service = get_main_business_service()
        biz_map = {}
        for stock in self.filtered_stocks:
            code = stock.get('code', '')
            biz_map[code] = biz_service.get_main_business(code)
        self._update_business_cells(biz_map)

    def _on_cell_clicked(self, row, col):
        """单击单元格：点击主营业务列时弹出详情"""
        if col == 7:  # 主营业务列
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if not code_item or not name_item:
                return
            code = code_item.text()
            name = name_item.text()
            stock = None
            for s in self.filtered_stocks:
                if str(s.get('code', '')) == code:
                    stock = s
                    break
            if not stock:
                return
            self._show_business_detail(code, name, stock)

    def _show_business_detail(self, code, name, stock):
        """显示股票主营业务详情对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle(f'📋 {name}({code}) 主营业务详情')
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)

        title = QLabel(f'<h3>{name}({code})</h3>')
        layout.addWidget(title)

        business = stock.get('main_business', '')
        business_edit = QTextEdit()
        business_edit.setReadOnly(True)

        if business:
            business_edit.setPlainText(business)
        else:
            business_edit.setPlainText('主营业务数据加载中...\n\n（正在从AkShare获取数据，请稍候...）')
            # 主动加载该股票的主营业务
            def _load_single_business():
                try:
                    from utils.main_business_service import get_main_business_service
                    biz_service = get_main_business_service()
                    biz = biz_service.fetch_main_business(code)
                    if biz:
                        stock['main_business'] = biz
                        stock['business_text'] = biz[:30] + '...' if len(biz) > 30 else biz
                        # 更新表格
                        for row, s in enumerate(self.filtered_stocks):
                            if str(s.get('code', '')) == code:
                                item = self.table.item(row, 7)
                                if item:
                                    item.setText(stock['business_text'])
                                    item.setForeground(QBrush(QColor('#58a6ff')))
                                break
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: business_edit.setPlainText(biz))
                    else:
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: business_edit.setPlainText('暂无主营业务数据'))
                except Exception as e:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: business_edit.setPlainText(f'获取失败: {e}'))

            import threading
            threading.Thread(target=_load_single_business, daemon=True).start()

        layout.addWidget(business_edit, 1)

        source_label = QLabel('<i>数据来源：AkShare 个股信息</i>')
        source_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        layout.addWidget(source_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec()

    def _on_cell_double_clicked(self, row, col):
        # 从表格单元格直接获取代码和名称（不受排序影响）
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item or not name_item:
            return
        code = code_item.text()
        name = name_item.text()
        # 名称列双击打开日线图
        if col == 1:
            self._open_kline(code)
        else:
            self.stock_clicked.emit(code, name)

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        # 从表格单元格直接获取代码和名称（不受排序影响）
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item or not name_item:
            return
        code = code_item.text()
        name = name_item.text()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #21262d; color: #f0f6fc; border: 1px solid #30363d;
                padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #1f6feb; }
        """)

        # 查看日线图
        action_kline = menu.addAction('📈 查看日线图（同花顺）')
        action_kline.triggered.connect(lambda: self._open_kline(code))

        menu.addSeparator()

        # 添加/移除自选
        wm = get_watchlist_manager()
        if wm.is_in_watchlist(code):
            action_remove = menu.addAction('⭐ 移除自选')
            action_remove.triggered.connect(lambda: self._remove_from_watchlist(code))
        else:
            action_add = menu.addAction('⭐ 添加自选')
            action_add.triggered.connect(lambda: self._add_to_watchlist(code, name))

        menu.exec(self.table.mapToGlobal(pos))

    def _open_kline(self, code):
        """打开同花顺日线图（延迟执行，避免菜单阻塞）"""
        url = f'http://stockpage.10jqka.com.cn/{code}/'
        QTimer.singleShot(100, lambda: QDesktopServices.openUrl(QUrl(url)))

    def _add_to_watchlist(self, code, name):
        """添加到自选股"""
        wm = get_watchlist_manager()
        if wm.add(code, name):
            self.status_label.setText(f'已添加 {name} 到自选')

    def _remove_from_watchlist(self, code):
        """从自选股移除"""
        wm = get_watchlist_manager()
        if wm.remove(code):
            self.status_label.setText(f'已从自选移除')

    def set_scan_callback(self, callback):
        self.scan_btn.clicked.connect(callback)

    def set_scanning(self, scanning):
        self.scan_btn.setDisabled(scanning)
        self.scan_btn.setText('扫描中...' if scanning else '🔍 全市场扫描')

    def _push_to_wechat(self):
        """推送到微信"""
        pusher = get_wechat_pusher()
        if not pusher.is_configured():
            self._show_wechat_settings()
            return

        if not self.filtered_stocks:
            self.status_label.setText('没有可推送的数据，请先扫描')
            return

        self.status_label.setText('正在推送到微信...')

        import threading
        def _do():
            success, msg = pusher.send_stock_list("实时监控信号股", self.filtered_stocks, max_count=30)
            self.status_label.setText(f'微信推送：{msg}')

        threading.Thread(target=_do, daemon=True).start()

    def _show_signal_config(self):
        """显示信号参数配置对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from ui.signal_config_panel import SignalConfigPanel

        dialog = QDialog(self)
        dialog.setWindowTitle('信号参数配置 - 可手动修改每个信号的触发条件')
        dialog.setMinimumSize(700, 550)
        dialog.setStyleSheet('background: #0d1117;')

        layout = QVBoxLayout(dialog)
        panel = SignalConfigPanel()
        panel.config_saved.connect(lambda: self.statusBar().showMessage('信号参数已保存，下次扫描生效', 3000) if hasattr(self, 'statusBar') else None)
        layout.addWidget(panel)

        dialog.exec()

    def _show_wechat_settings(self):
        """显示微信推送设置对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

        pusher = get_wechat_pusher()

        dialog = QDialog(self)
        dialog.setWindowTitle('微信推送设置')
        dialog.setFixedWidth(500)
        dialog.setStyleSheet("""
            QDialog { background: #161b22; }
            QLabel { color: #f0f6fc; font-size: 13px; }
            QLineEdit {
                background: #0d1117; border: 1px solid #30363d;
                border-radius: 4px; padding: 8px; color: #f0f6fc;
                font-size: 12px;
            }
            QPushButton {
                background: #238636; border: none; border-radius: 4px;
                padding: 8px 20px; color: white; font-weight: bold;
            }
            QPushButton:hover { background: #2ea043; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 说明
        desc = QLabel('企业微信群机器人 Webhook 地址：')
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 输入框
        input_field = QLineEdit()
        input_field.setPlaceholderText('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx')
        input_field.setText(pusher.webhook_url or '')
        layout.addWidget(input_field)

        # 使用说明
        help_text = QLabel(
            '\n💡 获取方法：\n'
            '1. 打开企业微信，创建一个群聊\n'
            '2. 点击群右上角「...」→「群机器人」→「添加机器人」\n'
            '3. 输入机器人名称，点击添加\n'
            '4. 复制 Webhook 地址，粘贴到上方\n'
        )
        help_text.setStyleSheet('color: #8b949e; font-size: 11px;')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        test_btn = QPushButton('测试推送')
        test_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb; border: none; border-radius: 4px;
                padding: 8px 16px; color: white;
            }
            QPushButton:hover { background: #388bfd; }
        """)
        test_btn.clicked.connect(lambda: self._test_wechat_push(input_field, dialog))
        btn_layout.addWidget(test_btn)

        save_btn = QPushButton('保存')
        save_btn.clicked.connect(lambda: self._save_wechat_settings(input_field, dialog))
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        dialog.exec()

    def _save_wechat_settings(self, input_field, dialog):
        """保存微信设置"""
        webhook = input_field.text().strip()
        if not webhook:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(dialog, '提示', '请输入Webhook地址')
            return

        pusher = get_wechat_pusher()
        if pusher.save_config(webhook):
            self.status_label.setText('微信推送设置已保存')
            dialog.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(dialog, '错误', '保存失败')

    def _test_wechat_push(self, input_field, dialog):
        """测试微信推送"""
        webhook = input_field.text().strip()
        if not webhook:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(dialog, '提示', '请先输入Webhook地址')
            return

        from utils.wechat_push import WechatPusher
        test_pusher = WechatPusher(webhook)
        success, msg = test_pusher.test_push()

        from PyQt6.QtWidgets import QMessageBox
        if success:
            QMessageBox.information(dialog, '成功', '测试消息已发送，请查看企业微信群！')
        else:
            QMessageBox.critical(dialog, '失败', f'推送失败：{msg}')


# ============================================================
# V7.6-A 精准买点评分后台线程
# ============================================================
class V76ScoreThread(QThread):
    """后台计算V7.6-A精准买点评分，不阻塞UI"""
    score_updated = pyqtSignal(str, dict)  # code, score_data
    finished_all = pyqtSignal(int)  # total_calculated

    def __init__(self, codes, cache=None):
        super().__init__()
        self.codes = codes
        self.cache = cache or {}
        self._stopped = False
        self._engine = None

    def stop(self):
        self._stopped = True

    def run(self):
        try:
            import os, sys
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for p in [base, os.path.join(base, 'strategies'), os.path.join(base, 'data'), os.path.join(base, 'utils')]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            from strategies.v75_optimized_strategy import (
                calculate_v75_score, generate_buy_conditions, load_stock_data, determine_v75_grade,
            )
            from strategies.kdj_strategy import calculate_kdj_score
            from data.tdx_data_engine import TdxDataEngine
            from utils.tdx_stock_list import get_realtime_quotes_tdx
            from datetime import datetime, timedelta
            import pandas as pd

            self._engine = TdxDataEngine()

            # 批量获取实时报价
            realtime_quotes = {}
            try:
                for batch_start in range(0, len(self.codes), 80):
                    if self._stopped:
                        return
                    batch = self.codes[batch_start:batch_start+80]
                    q = get_realtime_quotes_tdx(batch)
                    if q:
                        realtime_quotes.update(q)
            except Exception:
                pass

            calculated = 0
            for code in self.codes:
                if self._stopped:
                    break
                try:
                    df = load_stock_data(self._engine, code, days=400, trim_tail=False)
                    if df is None or len(df) < 60:
                        continue

                    # 用实时报价补充最新K线
                    quote = realtime_quotes.get(code)
                    if quote and quote.get('price', 0) > 0:
                        price = quote['price']
                        last_close = float(df['close'].values[-1])
                        if abs(price - last_close) > 0.001:
                            last_date = str(df['date'].values[-1])
                            try:
                                last_dt = datetime.strptime(last_date[:8], '%Y%m%d')
                                new_date = int((last_dt + timedelta(days=1)).strftime('%Y%m%d'))
                            except Exception:
                                new_date = int(last_date[:8]) + 1
                            new_row = df.iloc[-1].copy()
                            new_row['date'] = new_date
                            new_row['open'] = quote.get('open', price) or price
                            new_row['high'] = quote.get('high', price) or price
                            new_row['low'] = quote.get('low', price) or price
                            new_row['close'] = price
                            new_row['volume'] = quote.get('volume', 0)
                            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

                    conds = generate_buy_conditions(df)
                    n = len(df)
                    idx = n - 1  # 只计算最新一天

                    score, details, core_count = calculate_v75_score(
                        df.iloc[:idx+1], {k: v[:idx+1] for k, v in conds.items()}, idx, '震荡'
                    )

                    grade_result = determine_v75_grade(score, core_count)
                    grade = grade_result[0] if isinstance(grade_result, tuple) else grade_result

                    # KDJ策略评分（独立信号源）
                    kdj_score = 0
                    kdj_grade = '过滤'
                    try:
                        kdj_score, kdj_details, kdj_grade, kdj_reason = calculate_kdj_score(df, idx)
                    except Exception:
                        pass

                    # 回踩二十日信号（使用已有K线数据）
                    ma20_pullback = None
                    try:
                        from strategy.resonance_signals import calc_ma20_pullback_signal
                        # 将DataFrame转为list of dict
                        kline_list = df.to_dict('records') if hasattr(df, 'to_dict') else df
                        ma20_pullback = calc_ma20_pullback_signal({'code': code}, kline_list)
                    except Exception:
                        pass

                    score_data = {
                        'score': score,
                        'grade': grade,
                        'core_count': core_count,
                        'date': str(df.iloc[idx].get('date', '')),
                        'details': details,
                        'kdj_score': kdj_score,
                        'kdj_grade': kdj_grade,
                        'ma20_pullback': ma20_pullback,
                    }
                    self.score_updated.emit(code, score_data)
                    calculated += 1
                    if calculated % 100 == 0:
                        print(f"[V7.6评分线程] 进度: {calculated}/{len(self.codes)}")
                except Exception:
                    continue

            self.finished_all.emit(calculated)
        except Exception as e:
            print(f"[V7.6评分线程] 错误: {e}")
            self.finished_all.emit(0)
