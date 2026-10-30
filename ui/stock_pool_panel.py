# -*- coding: utf-8 -*-
"""
智能选股池UI
趋势突破池 + 强势突破池
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFrame, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QColor, QBrush, QDesktopServices

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_CARD_HOVER,
    BG_INTERACTIVE, BG_CONTAINER, BORDER, BORDER_SOFT, BORDER_STRONG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACCENT_BLUE,
    ACCENT_RED, ACCENT_GREEN, ACCENT_GOLD, UP, DOWN,
)
from strategy.stock_pool_v1 import get_stock_pool_filter
from utils.kline_provider import get_daily_kline
from utils.tdx_stock_list import get_stocks_with_quotes_tdx
from core.watchlist import get_watchlist_manager
from utils.wechat_push import get_wechat_pusher


class StockPoolWidget(QWidget):
    """智能选股池面板"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        if self._initialized:
            return
        super().__init__(parent)
        self._initialized = True
        self.current_strategy_id = 'trend_breakout'
        self.pool_data = {}
        self._is_generating = False
        self._stop_requested = False
        from strategy.strategy_manager import get_strategy_manager
        self.strategy_mgr = get_strategy_manager()
        self._init_ui()
        self._load_strategies()

    def _init_ui(self):
        self.setStyleSheet(f"""
            StockPoolWidget {{
                background: {BG_WINDOW};
                color: {TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel('🎯 AI选股池')
        title.setStyleSheet(f'font-size: 15px; font-weight: 700; color: {TEXT_PRIMARY}; letter-spacing: 0.2px;')
        header.addWidget(title)
        header.addStretch()

        # 选股池选择
        self.pool_combo = QComboBox()
        self.pool_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; padding: 4px 8px; color: {TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView {{
                background: {BG_PANEL_ALT}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER};
            }}
        """)
        self.pool_combo.currentIndexChanged.connect(self._on_pool_changed)
        header.addWidget(self.pool_combo)

        # 策略管理按钮
        self.strategy_mgr_btn = QPushButton('📋 策略管理')
        self.strategy_mgr_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
                padding: 6px 12px; color: {TEXT_PRIMARY}; font-size: 12px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
        """)
        self.strategy_mgr_btn.clicked.connect(self._show_strategy_manager)
        header.addWidget(self.strategy_mgr_btn)

        # 生成按钮
        self.generate_btn = QPushButton('⚡ 生成选股池')
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_CARD}; border: 1px solid {ACCENT_GREEN}; border-radius: 6px;
                padding: 6px 16px; color: {TEXT_PRIMARY}; font-weight: 700;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; border-color: {BORDER}; }}
        """)
        self.generate_btn.clicked.connect(self._toggle_generate)
        header.addWidget(self.generate_btn)

        # 构建涨停缓存按钮
        self.cache_btn = QPushButton('📊 涨停缓存')
        self.cache_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_GOLD}; border-radius: 6px;
                padding: 6px 12px; color: {TEXT_PRIMARY}; font-size: 12px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; border-color: {BORDER}; }}
        """)
        self.cache_btn.clicked.connect(self._build_limit_up_cache)
        header.addWidget(self.cache_btn)

        # 推送按钮
        self.push_btn = QPushButton('📤 推送到微信')
        self.push_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {ACCENT_BLUE}; border-radius: 6px;
                padding: 6px 12px; color: {TEXT_PRIMARY}; font-size: 12px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
            QPushButton:disabled {{ background: {BG_INTERACTIVE}; color: {TEXT_MUTED}; border-color: {BORDER}; }}
        """)
        self.push_btn.clicked.connect(self._push_to_wechat)
        header.addWidget(self.push_btn)

        # 设置按钮
        self.settings_btn = QPushButton('⚙')
        self.settings_btn.setFixedWidth(36)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INTERACTIVE}; border: 1px solid {BORDER_SOFT};
                border-radius: 6px; color: {TEXT_SECONDARY}; font-size: 14px;
            }}
            QPushButton:hover {{ background: {BG_CARD_HOVER}; color: {TEXT_PRIMARY}; }}
        """)
        self.settings_btn.clicked.connect(self._show_wechat_settings)
        header.addWidget(self.settings_btn)

        layout.addLayout(header)

        # 策略说明
        self.desc_label = QLabel()
        self.desc_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px; padding: 4px;')
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        self._update_desc()

        # 股票表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            '代码', '名称', '现价', '涨跌幅', '换手率', '市值(亿)', '所属概念', '信号标签', '选股池'
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)  # 启用点击列头排序
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {BG_CONTAINER}; gridline-color: {BORDER};
                color: {TEXT_PRIMARY}; border: 1px solid {BORDER}; font-size: 12px;
                alternate-background-color: {BG_PANEL_ALT};
                selection-background-color: rgba(90,169,255,0.22);
                selection-color: {TEXT_PRIMARY};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background: {BG_INTERACTIVE}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER};
                padding: 6px; font-weight: 700;
            }}
            QTableWidget::item {{ border-bottom: 1px solid {BORDER}; padding: 5px 4px; }}
            QTableWidget::item:selected {{ background: rgba(90,169,255,0.22); }}
        """)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

        # 状态栏
        self.status_label = QLabel('就绪')
        self.status_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        layout.addWidget(self.status_label)

    def _load_strategies(self):
        """从策略管理器加载策略列表"""
        self.pool_combo.blockSignals(True)
        self.pool_combo.clear()
        strategies = self.strategy_mgr.get_all()
        for s in strategies:
            self.pool_combo.addItem(s['name'], s['id'])
            self.pool_data[s['id']] = []
        self.pool_combo.blockSignals(False)
        if strategies:
            self.current_strategy_id = strategies[0]['id']
        self._update_desc()

    def _update_desc(self):
        if self.current_strategy_id:
            strategy = self.strategy_mgr.get_by_id(self.current_strategy_id)
            if strategy:
                self.desc_label.setText(f"策略: {strategy['description']}")
                return
        self.desc_label.setText('请选择策略')

    def _on_pool_changed(self, index):
        strategy_id = self.pool_combo.itemData(index)
        if strategy_id:
            self.current_strategy_id = strategy_id
        self._update_desc()
        self._refresh_table()

    def _show_strategy_manager(self):
        """打开策略管理器"""
        from ui.strategy_editor_dialog import StrategyEditorDialog
        dialog = StrategyEditorDialog(self)
        dialog.strategy_changed.connect(self._load_strategies)
        dialog.exec()

    def _build_limit_up_cache(self):
        """构建涨停次数缓存（后台线程）"""
        from PyQt6.QtWidgets import QMessageBox
        from strategy.limit_up_cache import get_limit_up_cache

        cache = get_limit_up_cache()
        reply = QMessageBox.question(
            self, '构建涨停缓存',
            f'当前缓存: {cache.get_cache_size()}只股票\n\n'
            '构建全市场涨停次数缓存约需3-5分钟，\n'
            '构建后筛选速度大幅提升。\n\n'
            '是否开始构建？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.cache_btn.setDisabled(True)
        self.cache_btn.setText('构建中...')
        self.status_label.setText('正在获取股票列表...')

        import threading
        def _do():
            try:
                # 获取股票列表
                from utils.tdx_stock_list import get_stocks_with_quotes_tdx
                stocks = get_stocks_with_quotes_tdx(max_stocks=5000,
                    progress_callback=lambda c, t, m: self.status_label.setText(f'获取股票: {c}/{t}'))
                print(f"[缓存构建] 获取到{len(stocks)}只股票")

                # 过滤主板非ST
                codes = []
                for s in stocks:
                    code = s.get('code', '')
                    name = s.get('name', '')
                    if code.startswith(('300', '301', '688', '689', '8', '4')):
                        continue
                    if 'ST' in name or 'st' in name:
                        continue
                    codes.append(code)

                print(f"[缓存构建] 主板非ST: {len(codes)}只")
                self.status_label.setText(f'开始构建涨停缓存: {len(codes)}只')

                # 批量获取K线并构建缓存
                from utils.kline_provider import get_daily_kline_batch
                kline_map = get_daily_kline_batch(codes, count=252, max_workers=8,
                    progress_callback=lambda d, t, c: self.status_label.setText(f'K线获取: {d}/{t}'))

                print(f"[缓存构建] 获取K线: {len(kline_map)}只")
                self.status_label.setText(f'计算涨停次数: {len(kline_map)}只')

                # 写入缓存
                updated = 0
                for code, kline in kline_map.items():
                    cache.refresh_single(code, kline)
                    updated += 1
                    if updated % 100 == 0:
                        self.status_label.setText(f'缓存写入: {updated}/{len(kline_map)}')

                cache._save()
                print(f"[缓存构建] 完成，共{updated}只")

                QTimer.singleShot(0, lambda: self.status_label.setText(f'涨停缓存构建完成，共{updated}只股票'))
                QTimer.singleShot(0, lambda: QMessageBox.information(self, '构建完成', f'涨停缓存构建完成！\n共缓存{updated}只股票'))
            except Exception as e:
                import traceback
                traceback.print_exc()
                QTimer.singleShot(0, lambda: self.status_label.setText(f'缓存构建失败: {e}'))
            finally:
                QTimer.singleShot(0, lambda: self.cache_btn.setDisabled(False))
                QTimer.singleShot(0, lambda: self.cache_btn.setText('📊 涨停缓存'))

        threading.Thread(target=_do, daemon=True).start()

    def _toggle_generate(self):
        """切换生成/停止"""
        if self._is_generating:
            # 停止生成
            self._stop_requested = True
            self.generate_btn.setDisabled(True)
            self.generate_btn.setText('停止中...')
            self.status_label.setText('正在停止...')
        else:
            # 开始生成
            self._stop_requested = False
            self._generate_pool()

    def _generate_pool(self):
        self._is_generating = True
        self.generate_btn.setText('⏹ 停止生成')
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_RED}; border: 1px solid {ACCENT_RED}; border-radius: 6px;
                padding: 6px 16px; color: {TEXT_PRIMARY}; font-weight: 700;
            }}
            QPushButton:hover {{ background: {ACCENT_RED}; opacity: 0.9; }}
        """)
        self.status_label.setText('正在获取股票列表...')

        # 进度回调（支持停止中断）
        def _progress(current, total, message):
            if self._stop_requested:
                raise InterruptedError('用户停止生成')
            self.status_label.setText(f'[{current}/{total}] {message}')

        # 在线程中执行
        import threading
        def _do():
            try:
                # 获取股票列表+行情（带进度）
                stocks = get_stocks_with_quotes_tdx(max_stocks=600, progress_callback=_progress)

                # 停止检查
                if self._stop_requested:
                    print("[SCAN] 用户停止（获取股票列表后）")
                    self.pool_data[self.current_strategy_id] = []
                    QTimer.singleShot(0, self._refresh_table)
                    QTimer.singleShot(0, lambda: self.status_label.setText('已停止'))
                    return

                print(f"[SCAN] 股票列表：{len(stocks)}只")
                self.status_label.setText(f'已获取{len(stocks)}只股票，正在基础过滤...')

                # 先做基础过滤（使用当前策略条件）
                pool_filter = get_stock_pool_filter()
                strategy = self.strategy_mgr.get_by_id(self.current_strategy_id)
                cond = strategy.get('conditions', {}) if strategy else {}
                strategy_name = strategy.get('name', '自定义策略') if strategy else '自定义策略'

                # 从策略条件读取过滤参数
                main_board_only = cond.get('main_board_only', True)
                exclude_st = cond.get('exclude_st', True)
                price_range = cond.get('price_range', [5, 60])
                mc_range = cond.get('market_cap_range', [30, 230])
                exclude_inds = cond.get('exclude_industries', pool_filter.EXCLUDE_INDUSTRIES)
                turnover_range = cond.get('turnover_range', [0, 100])
                limit_count_min = cond.get('limit_up_count_min', 0)
                pct_chg_range = cond.get('pct_chg_range', [-99, 99])

                # 判断是否需要K线（高点比例/量比/振幅/前一天未涨停 需要K线）
                need_kline = (
                    (cond.get('high_ratio_range', [0, 99])[0] > 0 or cond.get('high_ratio_range', [0, 99])[1] < 99) or
                    cond.get('volume_ratio_min', 0) > 0 or
                    cond.get('amplitude_max', 100) < 100 or
                    cond.get('no_limit_up_yesterday', False) or
                    self.current_strategy_id in ['trend_breakout', 'strong_breakout', 'steady_pullback']
                )

                print(f"[SCAN] 策略: {strategy_name}, 需要K线: {need_kline}")

                # 第一步：快速条件过滤（不需要K线）
                filtered = []
                for s in stocks:
                    code = s.get('code', '')
                    name = s.get('name', '')
                    # 主板过滤
                    if main_board_only and code.startswith(('300', '301', '688', '689', '8', '4')):
                        continue
                    # ST过滤
                    if exclude_st and ('ST' in name or 'st' in name):
                        continue
                    price = s.get('price', 0)
                    if price <= 0 or price < price_range[0] or price > price_range[1]:
                        continue
                    market_cap = s.get('market_cap', 0)
                    if market_cap < mc_range[0] or market_cap > mc_range[1]:
                        continue
                    industry = s.get('industry', '')
                    if any(ind in industry for ind in exclude_inds):
                        continue
                    # 换手率过滤（快速条件）
                    turnover = s.get('turnover', 0)
                    if (turnover_range[0] > 0 or turnover_range[1] < 100):
                        if turnover < turnover_range[0] or turnover > turnover_range[1]:
                            continue
                    # 涨跌幅过滤（快速条件）
                    pct_chg = s.get('pct_chg', s.get('change', 0))
                    if (pct_chg_range[0] > -99 or pct_chg_range[1] < 99):
                        if pct_chg < pct_chg_range[0] or pct_chg > pct_chg_range[1]:
                            continue
                    filtered.append(s)

                print(f"[SCAN] 快速条件过滤通过：{len(filtered)}只")
                self.status_label.setText(f'快速过滤后剩余{len(filtered)}只')

                # 停止检查
                if self._stop_requested:
                    print("[SCAN] 用户停止（快速过滤后）")
                    self.pool_data[self.current_strategy_id] = []
                    QTimer.singleShot(0, self._refresh_table)
                    QTimer.singleShot(0, lambda: self.status_label.setText('已停止'))
                    return

                # 第二步：涨停次数缓存过滤（不需要K线）
                if limit_count_min > 0:
                    try:
                        from strategy.limit_up_cache import get_limit_up_cache
                        cache = get_limit_up_cache()
                        cache_size = cache.get_cache_size()
                        print(f"[SCAN] 涨停缓存: {cache_size}只")

                        if cache_size > 0:
                            # 有缓存，直接过滤
                            cache_filtered = []
                            for s in filtered:
                                code = s.get('code', '')
                                if cache.has_cache(code):
                                    if cache.get_limit_up_count(code) >= limit_count_min:
                                        cache_filtered.append(s)
                                else:
                                    # 缓存未命中，保留待K线计算
                                    cache_filtered.append(s)
                            filtered = cache_filtered
                            print(f"[SCAN] 涨停次数过滤后：{len(filtered)}只")
                            self.status_label.setText(f'涨停过滤后剩余{len(filtered)}只')
                    except Exception as e:
                        print(f"[SCAN] 涨停缓存过滤失败: {e}")

                # 空结果保护
                if not filtered:
                    print("[SCAN] 快速过滤后无股票，直接返回空结果")
                    self.pool_data[self.current_strategy_id] = []
                    QTimer.singleShot(0, self._refresh_table)
                    QTimer.singleShot(0, lambda: self.status_label.setText('生成完成，符合条件股票0只'))
                    return

                # 第三步：如果不需要K线，直接返回结果
                if not need_kline and limit_count_min == 0:
                    # 纯快速条件策略，不需要K线
                    results = []
                    for s in filtered:
                        results.append({
                            'code': s.get('code', ''),
                            'name': s.get('name', ''),
                            'price': s.get('price', 0),
                            'pct_chg': s.get('pct_chg', s.get('change', 0)),
                            'volume': s.get('volume', 0),
                            'turnover': s.get('turnover', 0),
                            'market_cap': s.get('market_cap', 0),
                            'industry': s.get('industry', ''),
                            'limit_count': 0,
                            'ai_score': 0,
                            'trend': '',
                            'signal_names': [],
                            'pool': strategy_name
                        })
                    print(f"[SCAN] 纯快速条件筛选完成：{len(results)}只")
                    self.pool_data[self.current_strategy_id] = results
                    QTimer.singleShot(0, self._refresh_table)
                    QTimer.singleShot(0, lambda: self.status_label.setText(f'生成完成，共{len(results)}只股票'))
                    return

                # 第四步：需要K线，批量获取
                self.status_label.setText(f'正在批量获取K线（{len(filtered)}只，5线程）...')
                from utils.kline_provider import get_daily_kline_batch
                codes = [s['code'] for s in filtered]

                def _kline_progress(d, t, c):
                    if self._stop_requested:
                        raise InterruptedError('用户停止生成')
                    self.status_label.setText(f'K线获取: {d}/{t}')

                kline_map = get_daily_kline_batch(codes, count=180, max_workers=5,
                                                   progress_callback=_kline_progress)

                kline_count = len(kline_map)
                print(f"[SCAN] 成功获取K线：{kline_count}只")

                # 停止检查
                if self._stop_requested:
                    print("[SCAN] 用户停止（获取K线后）")
                    self.pool_data[self.current_strategy_id] = []
                    QTimer.singleShot(0, self._refresh_table)
                    QTimer.singleShot(0, lambda: self.status_label.setText('已停止'))
                    return

                self.status_label.setText(f'K线获取完成（{kline_count}只），正在技术筛选...')

                # 根据策略ID选择筛选方法
                builtin_methods = {
                    'trend_breakout': pool_filter._filter_single_trend,
                    'strong_breakout': pool_filter._filter_single_strong,
                    'steady_pullback': pool_filter._filter_single_steady,
                }

                # 逐只筛选（带进度和停止检查）
                results = []
                total = len(filtered)
                for idx, stock in enumerate(filtered):
                    # 停止检查
                    if self._stop_requested:
                        print(f"[SCAN] 用户停止生成，已筛选{idx}/{total}只，入选{len(results)}只")
                        break

                    code = stock.get('code', '')
                    kline = kline_map.get(code)
                    if kline:
                        if self.current_strategy_id in builtin_methods:
                            r = builtin_methods[self.current_strategy_id](stock, kline)
                        else:
                            r = pool_filter._filter_single_by_strategy(
                                stock, kline,
                                strategy_conditions=cond,
                                strategy_name=strategy_name,
                                skip_ai_score=True
                            )
                        if r:
                            results.append(r)
                    # 进度更新（每50只更新一次）
                    if (idx + 1) % 50 == 0:
                        self.status_label.setText(f'技术筛选: {idx+1}/{total}, 已入选{len(results)}只')

                # 稳健低吸池按量比降序
                if self.current_strategy_id == 'steady_pullback':
                    results.sort(key=lambda x: x.get('vol_ratio', 0), reverse=True)

                print(f"[SCAN] 最终入选：{len(results)}只")

                self.pool_data[self.current_strategy_id] = results
                # 通过QTimer.singleShot确保在主线程中更新UI
                QTimer.singleShot(0, self._refresh_table)
                if self._stop_requested:
                    QTimer.singleShot(0, lambda: self.status_label.setText(f'已停止，共筛选{len(results)}只股票'))
                else:
                    QTimer.singleShot(0, lambda: self.status_label.setText(f'生成完成，共{len(results)}只股票'))
            except InterruptedError:
                print("[SCAN] 用户停止生成（进度回调中断）")
                self.pool_data[self.current_strategy_id] = []
                QTimer.singleShot(0, self._refresh_table)
                QTimer.singleShot(0, lambda: self.status_label.setText('已停止'))
            except Exception as e:
                import traceback
                QTimer.singleShot(0, lambda: self.status_label.setText(f'生成失败: {e}'))
                traceback.print_exc()
            finally:
                self._is_generating = False
                self._stop_requested = False
                QTimer.singleShot(0, lambda: self.generate_btn.setDisabled(False))
                QTimer.singleShot(0, lambda: self.generate_btn.setText('⚡ 生成选股池'))
                QTimer.singleShot(0, lambda: self.generate_btn.setStyleSheet("""
                    QPushButton {
                        background: #238636; border: none; border-radius: 4px;
                        padding: 6px 16px; color: white; font-weight: bold;
                    }
                    QPushButton:hover { background: #2ea043; }
                    QPushButton:disabled { background: #30363d; color: #8b949e; }
                """))

        threading.Thread(target=_do, daemon=True).start()

    def _refresh_table(self):
        data = self.pool_data.get(self.current_strategy_id, [])
        self.table.setSortingEnabled(False)  # 刷新时暂时禁用排序
        self.table.setRowCount(len(data))

        for row, stock in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(stock.get('code', '')))
            self.table.setItem(row, 1, QTableWidgetItem(stock.get('name', '')))

            price = stock.get('price', 0)
            pct = stock.get('pct_chg', 0)
            item = QTableWidgetItem(f'{price:.2f}')
            color = '#f85149' if pct >= 0 else '#3fb950'
            item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 2, item)

            item = QTableWidgetItem(f'{pct:+.2f}%')
            item.setForeground(QBrush(QColor(color)))
            self.table.setItem(row, 3, item)

            self.table.setItem(row, 4, QTableWidgetItem(f'{stock.get("turnover", 0):.2f}%'))
            self.table.setItem(row, 5, QTableWidgetItem(f'{stock.get("market_cap", 0):.1f}'))

            # 所属概念（异步加载，先显示占位）
            concept_text = stock.get('concept_text', '加载中...')
            item = QTableWidgetItem(concept_text)
            if concept_text == '加载中...':
                item.setForeground(QBrush(QColor('#8b949e')))
            else:
                item.setForeground(QBrush(QColor('#58a6ff')))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 6, item)

            # 信号标签（多信号标签样式）
            signals = stock.get('signal_names', [])
            if signals:
                sig_text = ' '.join([f'[{s}]' for s in signals[:6]])
            else:
                sig_text = stock.get('pool', '')
            sig_item = QTableWidgetItem(sig_text)
            sig_item.setForeground(QBrush(QColor('#f0883e')))
            sig_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 7, sig_item)

            self.table.setItem(row, 8, QTableWidgetItem(stock.get('pool', '')))

        self.table.setSortingEnabled(True)  # 恢复排序

        # 异步加载所属概念
        self._load_concepts_async()

    def _load_concepts_async(self):
        """异步批量加载股票所属概念"""
        data = self.pool_data.get(self.current_strategy_id, [])
        codes_need = []
        for stock in data:
            if not stock.get('concept_text'):
                codes_need.append(stock.get('code', ''))

        if not codes_need:
            return

        def _do_load():
            try:
                from service.concept_service import get_stock_concepts
                concept_map = {}
                for code in codes_need[:100]:  # 限制每次最多100只
                    try:
                        concepts, _ = get_stock_concepts(code)
                        if concepts and isinstance(concepts, list):
                            concept_map[code] = ' | '.join(concepts[:8])
                        else:
                            concept_map[code] = '暂无概念'
                    except Exception:
                        concept_map[code] = '暂无概念'

                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._update_concept_cells(concept_map))
            except Exception as e:
                print(f"[AI选股池] 加载概念失败: {e}")

        import threading
        threading.Thread(target=_do_load, daemon=True).start()

    def _update_concept_cells(self, concept_map):
        """更新概念单元格"""
        data = self.pool_data.get(self.current_strategy_id, [])
        for row, stock in enumerate(data):
            code = stock.get('code', '')
            if code in concept_map:
                stock['concept_text'] = concept_map[code]
                item = self.table.item(row, 6)
                if item:
                    item.setText(concept_map[code])
                    item.setForeground(QBrush(QColor('#58a6ff')))

    def _on_cell_clicked(self, row, col):
        """单击单元格：跳转到股票详情页"""
        # 从表格单元格直接获取代码和名称（不受排序影响）
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item or not name_item:
            return
        code = code_item.text()
        name = name_item.text()
        self.stock_clicked.emit(code, name)

    def _on_cell_double_clicked(self, row, col):
        # 从表格单元格直接获取代码和名称（不受排序影响）
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item or not name_item:
            return
        code = code_item.text()
        name = name_item.text()
        # 双击打开K线查看窗口
        self._open_kline_viewer(code, name)

    def _open_kline_viewer(self, code, name):
        """打开K线查看窗口"""
        try:
            from ui.kline_viewer_dialog import KlineViewerDialog
            dlg = KlineViewerDialog(code, name, self)
            dlg.show()
        except Exception as e:
            print(f"[AI选股池] 打开K线窗口失败: {e}")
            # 降级：打开同花顺网页
            self._open_kline(code)

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

    def _push_to_wechat(self):
        """推送到微信"""
        pusher = get_wechat_pusher()
        if not pusher.is_configured():
            self._show_wechat_settings()
            return

        data = self.pool_data.get(self.current_strategy_id, [])
        if not data:
            self.status_label.setText('没有可推送的数据，请先生成选股池')
            return

        strategy = self.strategy_mgr.get_by_id(self.current_strategy_id)
        pool_name = strategy.get('name', '自定义策略') if strategy else '选股池'
        self.status_label.setText('正在推送到微信...')

        import threading
        def _do():
            success, msg = pusher.send_stock_list(pool_name, data)
            QTimer.singleShot(0, lambda: self.status_label.setText(f'微信推送：{msg}'))

        threading.Thread(target=_do, daemon=True).start()

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
            '3. 输入机器人名称（如「量化盯盘」），点击添加\n'
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
