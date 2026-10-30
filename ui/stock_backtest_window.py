# -*- coding: utf-8 -*-
"""
股票CTA回测研究中心 - 专业策略研究工作站

参考专业CTA回测软件设计：
- 左侧：策略配置 + 数据设置 + 交易参数 + 操作控制
- 右侧：7个分析Tab（业绩概览/净值曲线/净值回撤/每日盈亏/委托记录/成交记录/K线回测图）
- 接入现有backtest引擎（数据层→策略层→撮合引擎→报告）
"""
import os
import sys
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox,
    QPushButton, QGroupBox, QTextEdit, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter, QFrame, QScrollArea,
    QMessageBox, QProgressBar, QRadioButton, QButtonGroup, QDialog
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from backtest.annotation.kline_editor import KlineEditorWidget
from ui.force_behavior_panel import ForceBehaviorPanel

from ui.theme.design_tokens import (
    BG_WINDOW, BG_PANEL, BG_PANEL_ALT, BG_CARD, BG_INTERACTIVE,
    BORDER, BORDER_SOFT, BORDER_STRONG, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD, ACCENT_ORANGE,
    ACCENT_PURPLE,
)

# 深色主题（保持兼容命名）
DARK_BG = BG_WINDOW
DARK_CARD = BG_CARD
DARK_BORDER = BORDER
ACCENT_YELLOW = ACCENT_GOLD


# ========== 回测后台线程 ==========
class BacktestThread(QThread):
    """回测执行线程"""
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._stop = False

    def run(self):
        try:
            self.log.emit("=" * 55)
            self.log.emit(f"策略: {self.params['strategy_name']}")
            self.log.emit(f"股票: {self.params['code']}")
            self.log.emit(f"周期: {self.params['start_date']} ~ {self.params['end_date']}")
            self.log.emit(f"资金: {self.params['capital']:,.0f} 元")
            # 输出策略参数（确认真实生效）
            sp = self.params.get('strategy_params', {})
            if sp:
                param_str = ", ".join(f"{k}={v}" for k, v in sp.items())
                self.log.emit(f"策略参数: {param_str}")
            self.log.emit("=" * 55)

            # 1. 加载数据
            self.log.emit("[1/4] 正在加载K线数据...")
            kline = self._load_kline()
            if not kline:
                code = self.params['code']
                market = '沪市(主板/科创板)' if code.startswith('6') else '深市(主板/创业板)' if code.startswith(('0','3')) else '未知'
                self.error.emit(
                    f"K线数据加载失败！\n\n"
                    f"股票代码: {code}\n"
                    f"市场判断: {market}\n\n"
                    f"可能原因：\n"
                    f"1. 股票代码错误或该股票已退市\n"
                    f"2. 该时间段内无交易数据（新股/停牌）\n"
                    f"3. 通达信数据源未连接或网络异常\n\n"
                    f"支持板块：主板(600/000/001/002)、创业板(300)、科创板(688)\n"
                    f"请检查代码后重试，或点击'下载数据'按钮重新获取。"
                )
                return
            self.log.emit(f"  加载成功: {len(kline.get('close', []))} 根K线")
            self.progress.emit(25)

            if self._stop:
                return

            # 2. 创建策略
            self.log.emit("[2/4] 初始化策略...")
            strategy = self._create_strategy()
            self.progress.emit(40)

            # 3. 运行回测
            self.log.emit("[3/4] 运行回测引擎...")
            result = self._run_backtest(strategy, kline)
            self.progress.emit(80)

            if self._stop:
                return

            # 4. 生成报告
            self.log.emit("[4/4] 生成回测报告...")
            report = self._build_report(result, kline)
            self.progress.emit(100)

            self.log.emit("\n✅ 回测完成!")
            self.finished_ok.emit(report)

        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _load_kline(self):
        """加载K线数据"""
        try:
            from backtest.data.data_loader import TDXDataLoader
            loader = TDXDataLoader()
            code = self.params['code']
            # 确保6位代码，如果是名称则转换（安全降级）
            if not (code.isdigit() and len(code) == 6):
                try:
                    from utils.stock_name_manager import get_all_stock_names
                    stock_names = get_all_stock_names()
                    if stock_names and isinstance(stock_names, dict):
                        if code in stock_names:
                            new_code = str(stock_names[code])
                            if new_code.isdigit() and len(new_code) == 6:
                                code = new_code
                                self.log.emit(f"  名称转换: {self.params['code']} → {code}")
                        else:
                            for name, c in stock_names.items():
                                try:
                                    if code in str(name) or str(name) in code:
                                        new_code = str(c)
                                        if new_code.isdigit() and len(new_code) == 6:
                                            code = new_code
                                            self.log.emit(f"  名称匹配: {self.params['code']} → {name}({code})")
                                            break
                                except Exception:
                                    continue
                except Exception as e:
                    self.log.emit(f"  名称转换跳过: {type(e).__name__}")
            # 确保6位代码
            code = code.zfill(6)
            if not (code.isdigit() and len(code) == 6):
                self.log.emit(f"  ❌ 无效股票代码: {code}")
                return None
            data = loader.get_kline(
                code=code,
                start=self.params['start_date'],
                end=self.params['end_date'],
                adjust=self.params.get('adjust', 'qfq'),
                count=0
            )
            return data
        except Exception as e:
            self.log.emit(f"  数据加载异常: {e}")
            return None

    def _create_strategy(self):
        """创建策略实例（优先使用用户配置的策略参数，交易参数面板止盈止损优先级最高）"""
        strategy_name = self.params['strategy_name']
        user_params = self.params.get('strategy_params', {})
        if user_params:
            strategy_params = dict(user_params)
        else:
            strategy_params = {'volume_ratio': 3.0}
        
        # 交易参数面板的止盈止损持仓天数优先级最高，覆盖策略配置
        if 'stop_loss' in self.params:
            strategy_params['stop_loss_pct'] = self.params['stop_loss'] * 100
        if 'take_profit' in self.params:
            strategy_params['take_profit_pct'] = self.params['take_profit'] * 100
        if 'hold_days' in self.params:
            strategy_params['max_hold_days'] = self.params['hold_days']
        
        self.log.emit(f"策略参数: volume_ratio={strategy_params.get('volume_ratio', 3.0)}, "
                      f"ma_period={strategy_params.get('ma_period', 5)}, "
                      f"take_profit_pct={strategy_params.get('take_profit_pct', 20)}, "
                      f"stop_loss_pct={strategy_params.get('stop_loss_pct', 5)}, "
                      f"max_hold_days={strategy_params.get('max_hold_days', 20)}")

        if '三倍量' in strategy_name:
            from backtest.strategy.triple_volume import TripleVolumeStrategy
            return TripleVolumeStrategy(strategy_params)
        elif '五买' in strategy_name or '倍量回踩' in strategy_name:
            from backtest.strategy.five_buy import FiveBuyStrategy
            return FiveBuyStrategy(strategy_params)
        elif '回调五日线' in strategy_name or '回调5日' in strategy_name:
            from backtest.strategy.pullback_ma5 import PullbackMA5Strategy
            return PullbackMA5Strategy(strategy_params)
        elif '五九' in strategy_name or '回踩' in strategy_name:
            from backtest.strategy.pullback_59 import Pullback59Strategy
            return Pullback59Strategy(strategy_params)
        else:
            from backtest.strategy.triple_volume import TripleVolumeStrategy
            return TripleVolumeStrategy(strategy_params)

    def _run_backtest(self, strategy, kline):
        """运行回测"""
        from backtest.strategy.adapter import StrategyAdapter
        from backtest.engine.cost import AStockCostConfig

        cost = AStockCostConfig(
            commission_rate=self.params.get('commission', 0.0003),
            stamp_tax_rate=self.params.get('stamp_tax', 0.001),
            slippage_rate=self.params.get('slippage', 0.0005),
        )

        adapter = StrategyAdapter(
            strategy=strategy,
            initial_cash=self.params['capital'],
            cost_config=cost,
            max_positions=1,
            single_position_pct=self.params.get('position_pct', 0.95),
        )

        code = self.params['code'].zfill(6)
        adapter.load_data(kline, code=code)
        result = adapter.run(
            start_date=self.params['start_date'],
            end_date=self.params['end_date']
        )
        # 附加订单信息（委托记录）
        result.all_orders = [o.to_dict() for o in adapter.broker.account.trades]
        result.pending_orders = [o.to_dict() for o in adapter.broker.pending_orders]
        return result

    def _build_report(self, result, kline):
        """构建完整报告"""
        # 计算夏普比率等扩展指标
        daily_assets = result.daily_assets if hasattr(result, 'daily_assets') else []
        trades = result.trades if hasattr(result, 'trades') else []

        # 净值曲线
        equity_curve = []
        for i, asset in enumerate(daily_assets):
            equity_curve.append({
                'date': asset.get('date', ''),
                'asset': asset.get('total_asset', self.params['capital']),
                'cash': asset.get('cash', 0),
                'position_value': asset.get('position_value', 0),
            })

        # 计算回撤
        max_asset = self.params['capital']
        drawdowns = []
        for eq in equity_curve:
            if eq['asset'] > max_asset:
                max_asset = eq['asset']
            dd = (eq['asset'] - max_asset) / max_asset * 100 if max_asset > 0 else 0
            drawdowns.append({'date': eq['date'], 'drawdown': dd})

        # 每日盈亏
        daily_pnl = []
        prev_asset = self.params['capital']
        for eq in equity_curve:
            pnl = eq['asset'] - prev_asset
            daily_pnl.append({
                'date': eq['date'],
                'asset': eq['asset'],
                'daily_pnl': pnl,
                'pnl_pct': pnl / prev_asset * 100 if prev_asset > 0 else 0,
            })
            prev_asset = eq['asset']

        # 计算夏普
        returns = [d['pnl_pct'] / 100 for d in daily_pnl if d['pnl_pct'] != 0]
        import numpy as np
        sharpe = 0.0
        if len(returns) > 1:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(252)

        # 年化收益
        days = len(equity_curve)
        annual_return = 0.0
        if days > 0 and result.total_return_pct:
            annual_return = (1 + result.total_return_pct / 100) ** (252 / days) - 1
            annual_return *= 100

        return {
            'strategy_name': result.strategy_name,
            'code': result.code,
            'start_date': result.start_date,
            'end_date': result.end_date,
            'initial_cash': result.initial_cash,
            'final_asset': result.final_asset,
            'total_return': result.total_return,
            'total_return_pct': result.total_return_pct,
            'annual_return': round(annual_return, 2),
            'max_drawdown': result.max_drawdown,
            'sharpe': round(sharpe, 2),
            'trade_count': result.trade_count,
            'win_count': result.win_count,
            'loss_count': result.loss_count,
            'win_rate': result.win_rate,
            'profit_loss_ratio': result.profit_loss_ratio,
            'avg_hold_days': result.avg_hold_days,
            'max_consecutive_loss': result.max_consecutive_loss,
            'equity_curve': equity_curve,
            'drawdowns': drawdowns,
            'daily_pnl': daily_pnl,
            'trades': trades,
            'orders': getattr(result, 'all_orders', []),
            'pending_orders': getattr(result, 'pending_orders', []),
            'kline': kline,
        }

    def stop(self):
        self._stop = True


# ========== 参数优化线程 ==========
class OptimizeThread(QThread):
    """参数优化后台线程 - 每次组合运行真实回测"""
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 当前, 总数
    finished_ok = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, params, param_ranges):
        super().__init__()
        self.params = params  # 基础回测参数
        self.param_ranges = param_ranges  # 优化范围
        self._stop = False

    def run(self):
        try:
            # 生成参数组合
            combos = []
            vol = self.param_ranges['vol_min']
            while vol <= self.param_ranges['vol_max'] + 0.001:
                tp = self.param_ranges['tp_min']
                while tp <= self.param_ranges['tp_max'] + 0.001:
                    sl = self.param_ranges['sl_min']
                    while sl <= self.param_ranges['sl_max'] + 0.001:
                        combos.append((round(vol, 2), round(tp, 2), round(sl, 2)))
                        sl += self.param_ranges['sl_step']
                    tp += self.param_ranges['tp_step']
                vol += self.param_ranges['vol_step']

            total = len(combos)
            self.log.emit(f"共 {total} 组参数，开始真实回测...")

            # 加载K线（只加载一次）
            from backtest.data.data_loader import TDXDataLoader
            loader = TDXDataLoader()
            kline = loader.get_kline(
                code=self.params['code'].zfill(6),
                start=self.params['start_date'],
                end=self.params['end_date'],
                adjust='qfq'
            )
            if not kline:
                self.error.emit("K线数据加载失败")
                return

            results = []
            for idx, (vol, tp, sl) in enumerate(combos):
                if self._stop:
                    break
                self.progress.emit(idx + 1, total)
                self.log.emit(f"[{idx+1}/{total}] 量比{vol} 止盈{tp}% 止损{sl}%")

                try:
                    from backtest.strategy.triple_volume import TripleVolumeStrategy
                    from backtest.strategy.adapter import StrategyAdapter
                    from backtest.engine.cost import AStockCostConfig

                    strategy = TripleVolumeStrategy({
                        'volume_ratio': vol,
                        'stop_loss_pct': sl,
                        'take_profit_pct': tp,
                        'max_hold_days': 20,
                    })
                    cost = AStockCostConfig(
                        commission_rate=self.params.get('commission', 0.0003),
                        stamp_tax_rate=self.params.get('stamp_tax', 0.001),
                        slippage_rate=self.params.get('slippage', 0.0005),
                    )
                    adapter = StrategyAdapter(
                        strategy=strategy,
                        initial_cash=self.params['capital'],
                        cost_config=cost,
                        max_positions=1,
                        single_position_pct=0.95,
                    )
                    adapter.load_data(kline, code=self.params['code'].zfill(6))
                    result = adapter.run(
                        start_date=self.params['start_date'],
                        end_date=self.params['end_date']
                    )
                    results.append([
                        vol, tp, sl,
                        round(result.total_return_pct, 2),
                        round(result.max_drawdown, 2),
                        round(result.win_rate, 1),
                        result.trade_count
                    ])
                except Exception as e:
                    self.log.emit(f"  跳过: {e}")
                    results.append([vol, tp, sl, 0, 0, 0, 0])

            # 按收益排序
            results.sort(key=lambda x: x[3], reverse=True)
            self.finished_ok.emit(results)

        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def stop(self):
        self._stop = True


# ========== 参数优化窗口 ==========
class ParamOptimizeDialog(QDialog):
    """参数优化窗口 - 真实回测"""
    def __init__(self, parent=None, backtest_params=None):
        super().__init__(parent)
        self.setWindowTitle('🔧 参数优化（真实回测）')
        self.setMinimumSize(750, 550)
        self.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        self.backtest_params = backtest_params or {}
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 参数范围设置
        param_group = QGroupBox('优化参数范围（三倍量突破策略）')
        param_group.setStyleSheet(self._group_style())
        grid = QGridLayout(param_group)

        grid.addWidget(QLabel('成交量倍数:'), 0, 0)
        self.vol_min = QDoubleSpinBox(); self.vol_min.setRange(1, 10); self.vol_min.setValue(2)
        self.vol_max = QDoubleSpinBox(); self.vol_max.setRange(1, 10); self.vol_max.setValue(4)
        self.vol_step = QDoubleSpinBox(); self.vol_step.setRange(0.1, 2); self.vol_step.setValue(1)
        grid.addWidget(self.vol_min, 0, 1); grid.addWidget(QLabel('~'), 0, 2)
        grid.addWidget(self.vol_max, 0, 3); grid.addWidget(QLabel('步长'), 0, 4)
        grid.addWidget(self.vol_step, 0, 5)

        grid.addWidget(QLabel('止盈比例(%):'), 1, 0)
        self.tp_min = QDoubleSpinBox(); self.tp_min.setRange(1, 100); self.tp_min.setValue(10)
        self.tp_max = QDoubleSpinBox(); self.tp_max.setRange(1, 100); self.tp_max.setValue(20)
        self.tp_step = QDoubleSpinBox(); self.tp_step.setRange(1, 20); self.tp_step.setValue(10)
        grid.addWidget(self.tp_min, 1, 1); grid.addWidget(QLabel('~'), 1, 2)
        grid.addWidget(self.tp_max, 1, 3); grid.addWidget(QLabel('步长'), 1, 4)
        grid.addWidget(self.tp_step, 1, 5)

        grid.addWidget(QLabel('止损比例(%):'), 2, 0)
        self.sl_min = QDoubleSpinBox(); self.sl_min.setRange(1, 50); self.sl_min.setValue(5)
        self.sl_max = QDoubleSpinBox(); self.sl_max.setRange(1, 50); self.sl_max.setValue(10)
        self.sl_step = QDoubleSpinBox(); self.sl_step.setRange(0.5, 10); self.sl_step.setValue(5)
        grid.addWidget(self.sl_min, 2, 1); grid.addWidget(QLabel('~'), 2, 2)
        grid.addWidget(self.sl_max, 2, 3); grid.addWidget(QLabel('步长'), 2, 4)
        grid.addWidget(self.sl_step, 2, 5)

        layout.addWidget(param_group)

        # 进度
        self.opt_progress = QProgressBar()
        self.opt_progress.setStyleSheet(f'''
            QProgressBar {{ background: {DARK_CARD}; border: 1px solid {DARK_BORDER};
                border-radius: 4px; text-align: center; color: {TEXT_PRIMARY}; height: 20px; }}
            QProgressBar::chunk {{ background: {ACCENT_YELLOW}; border-radius: 3px; }}
        ''')
        layout.addWidget(self.opt_progress)

        # 日志
        self.opt_log = QTextEdit()
        self.opt_log.setReadOnly(True)
        self.opt_log.setMaximumHeight(100)
        self.opt_log.setStyleSheet(f'''
            QTextEdit {{ background: #010409; color: #3fb950;
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, monospace; font-size: 11px; }}
        ''')
        layout.addWidget(self.opt_log)

        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(7)
        self.result_table.setHorizontalHeaderLabels(
            ['成交量倍数', '止盈%', '止损%', '总收益%', '最大回撤%', '胜率%', '交易次数']
        )
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setStyleSheet(self._table_style())
        layout.addWidget(self.result_table, 1)

        # 按钮
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton('▶ 开始优化')
        self.btn_run.setStyleSheet(self._btn_style(ACCENT_GREEN))
        self.btn_run.clicked.connect(self._run_optimize)
        btn_layout.addWidget(self.btn_run)

        self.btn_stop = QPushButton('⏹ 停止')
        self.btn_stop.setStyleSheet(self._btn_style(ACCENT_RED))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_optimize)
        btn_layout.addWidget(self.btn_stop)

        self.btn_close = QPushButton('关闭')
        self.btn_close.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _run_optimize(self):
        if not self.backtest_params.get('code'):
            QMessageBox.warning(self, '提示', '请先在主界面输入股票代码')
            return

        param_ranges = {
            'vol_min': self.vol_min.value(),
            'vol_max': self.vol_max.value(),
            'vol_step': self.vol_step.value(),
            'tp_min': self.tp_min.value(),
            'tp_max': self.tp_max.value(),
            'tp_step': self.tp_step.value(),
            'sl_min': self.sl_min.value(),
            'sl_max': self.sl_max.value(),
            'sl_step': self.sl_step.value(),
        }

        self.opt_log.clear()
        self.opt_progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.worker = OptimizeThread(self.backtest_params, param_ranges)
        self.worker.log.connect(lambda t: self.opt_log.append(t))
        self.worker.progress.connect(self._on_opt_progress)
        self.worker.finished_ok.connect(self._on_opt_finished)
        self.worker.error.connect(self._on_opt_error)
        self.worker.start()

    def _stop_optimize(self):
        if self.worker:
            self.worker.stop()
            self.opt_log.append("正在停止...")

    def _on_opt_progress(self, current, total):
        pct = int(current / total * 100) if total > 0 else 0
        self.opt_progress.setValue(pct)
        self.opt_progress.setFormat(f"{current}/{total} ({pct}%)")

    def _on_opt_finished(self, results):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.opt_log.append(f"✅ 优化完成，共 {len(results)} 组结果")

        self.result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            for j, v in enumerate(r):
                item = QTableWidgetItem(f"{v:.2f}" if isinstance(v, float) else str(v))
                if j == 3:
                    item.setForeground(QColor(ACCENT_RED if v > 0 else ACCENT_GREEN))
                self.result_table.setItem(i, j, item)

    def _on_opt_error(self, error):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.opt_log.append(f"❌ {error}")
        QMessageBox.critical(self, '错误', error[:300])

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        event.accept()

    def _group_style(self):
        return f'''
            QGroupBox {{ color: {TEXT_PRIMARY}; font-weight: bold;
                background: {BG_PANEL}; border: 1px solid {DARK_BORDER}; border-radius: 6px;
                margin-top: 12px; padding-top: 10px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        '''

    def _table_style(self):
        return f'''
            QTableWidget {{ background: {DARK_BG}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                gridline-color: {DARK_BORDER}; font-size: 12px; }}
            QHeaderView::section {{ background: {DARK_CARD}; color: {TEXT_SECONDARY};
                border: 1px solid {DARK_BORDER}; padding: 6px; font-weight: bold; }}
        '''

    def _btn_style(self, color):
        return f'''
            QPushButton {{ background: {color}; color: white; border: none;
                border-radius: 4px; padding: 8px 16px; font-size: 12px; font-weight: bold; }}
            QPushButton:disabled {{ background: {DARK_BORDER}; color: {TEXT_SECONDARY}; }}
        '''


# ========== 主窗口 ==========
class StockBacktestWindow(QMainWindow):
    """股票CTA回测研究中心"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📊 股票CTA回测研究中心')
        self.setMinimumSize(1500, 950)
        self.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')

        self.worker = None
        self.report = None
        # 策略可配置参数（从JSON加载，用户可编辑）
        from backtest.strategy.strategy_config import get_params
        self.strategy_params = get_params('三倍量突破策略')
        # 交易参数配置文件路径
        import os as _os
        self._trade_config_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            'data', 'backtest_trade_config.json'
        )

        self._init_ui()
        self._load_trade_config()  # 加载保存的交易参数

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 顶部策略状态栏
        self.status_bar = QLabel()
        self.status_bar.setStyleSheet(f'''
            QLabel {{ background: {DARK_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 6px;
                padding: 8px 12px; font-size: 12px; }}
        ''')
        self.status_bar.setMinimumHeight(36)
        self._update_status_bar()
        main_layout.addWidget(self.status_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([340, 1160])
        main_layout.addWidget(splitter, 1)
        
        # 连接交易参数变化信号，自动保存配置
        self._connect_trade_config_signals()

    def _load_trade_config(self):
        """加载保存的交易参数配置"""
        try:
            import os as _os
            import json as _json
            if _os.path.exists(self._trade_config_path):
                with open(self._trade_config_path, 'r', encoding='utf-8') as f:
                    config = _json.load(f)
                # 恢复交易参数
                if hasattr(self, 'capital') and 'capital' in config:
                    self.capital.setValue(config['capital'])
                if hasattr(self, 'commission') and 'commission' in config:
                    self.commission.setValue(config['commission'])
                if hasattr(self, 'stamp_tax') and 'stamp_tax' in config:
                    self.stamp_tax.setValue(config['stamp_tax'])
                if hasattr(self, 'slippage') and 'slippage' in config:
                    self.slippage.setValue(config['slippage'])
                if hasattr(self, 'position_pct') and 'position_pct' in config:
                    self.position_pct.setValue(config['position_pct'])
                if hasattr(self, 'take_profit') and 'take_profit' in config:
                    self.take_profit.setValue(config['take_profit'])
                if hasattr(self, 'stop_loss') and 'stop_loss' in config:
                    self.stop_loss.setValue(config['stop_loss'])
                if hasattr(self, 'hold_days') and 'hold_days' in config:
                    self.hold_days.setValue(config['hold_days'])
                print(f'[回测配置] 已加载交易参数: {self._trade_config_path}')
        except Exception as e:
            print(f'[回测配置] 加载交易参数失败: {e}')
    
    def _save_trade_config(self):
        """保存交易参数配置到文件"""
        try:
            import os as _os
            import json as _json
            _os.makedirs(_os.path.dirname(self._trade_config_path), exist_ok=True)
            config = {
                'capital': self.capital.value() if hasattr(self, 'capital') else 100000,
                'commission': self.commission.value() if hasattr(self, 'commission') else 3,
                'stamp_tax': self.stamp_tax.value() if hasattr(self, 'stamp_tax') else 1,
                'slippage': self.slippage.value() if hasattr(self, 'slippage') else 0.05,
                'position_pct': self.position_pct.value() if hasattr(self, 'position_pct') else 95,
                'take_profit': self.take_profit.value() if hasattr(self, 'take_profit') else 20,
                'stop_loss': self.stop_loss.value() if hasattr(self, 'stop_loss') else 5,
                'hold_days': self.hold_days.value() if hasattr(self, 'hold_days') else 20,
            }
            with open(self._trade_config_path, 'w', encoding='utf-8') as f:
                _json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[回测配置] 保存交易参数失败: {e}')
    
    def _connect_trade_config_signals(self):
        """连接交易参数变化信号，自动保存"""
        widgets = ['capital', 'commission', 'stamp_tax', 'slippage',
                   'position_pct', 'take_profit', 'stop_loss', 'hold_days']
        for name in widgets:
            widget = getattr(self, name, None)
            if widget:
                widget.valueChanged.connect(self._save_trade_config)
    
    def _update_status_bar(self):
        """更新顶部策略状态栏"""
        from backtest.strategy.strategy_config import get_strategy_config
        strategy_name = self.strategy_combo.currentText() if hasattr(self, 'strategy_combo') else '三倍量突破策略'
        config = get_strategy_config(strategy_name)
        params = self.strategy_params
        # 构建简短参数显示
        param_parts = []
        for key, pdef in config["params"].items():
            val = params.get(key, pdef["default"])
            unit = pdef.get("unit", "")
            if isinstance(val, float):
                param_parts.append(f"{pdef['name']}:{val:.1f}{unit}")
            else:
                param_parts.append(f"{pdef['name']}:{val}{unit}")
        self.status_bar.setText(f"📊 当前策略: <b>{strategy_name}</b> &nbsp;&nbsp;|&nbsp;&nbsp; " + " &nbsp; ".join(param_parts))

    def _on_strategy_changed(self, strategy_name):
        """策略切换时自动加载对应参数"""
        from backtest.strategy.strategy_config import get_params
        self.strategy_params = get_params(strategy_name)
        # 同步交易参数区的止盈止损
        if hasattr(self, 'take_profit') and 'take_profit_pct' in self.strategy_params:
            self.take_profit.setValue(self.strategy_params['take_profit_pct'])
        if hasattr(self, 'stop_loss') and 'stop_loss_pct' in self.strategy_params:
            self.stop_loss.setValue(self.strategy_params['stop_loss_pct'])
        if hasattr(self, 'hold_days') and 'max_hold_days' in self.strategy_params:
            self.hold_days.setValue(self.strategy_params['max_hold_days'])
        self._update_status_bar()
        self._append_log(f"策略切换为: {strategy_name}，参数已加载")

    # ---------- 左侧：策略配置区 ----------
    def _create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f'QScrollArea {{ border: none; background: transparent; }}')
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)

        # 1. 策略选择
        scroll_layout.addWidget(self._create_strategy_group())
        # 2. 股票参数
        scroll_layout.addWidget(self._create_stock_group())
        # 3. 数据设置
        scroll_layout.addWidget(self._create_data_group())
        # 4. 交易参数
        scroll_layout.addWidget(self._create_trade_group())

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)  # stretch=1，占主要空间

        # 5. 操作控制（固定在底部，始终可见）
        layout.addWidget(self._create_control_group())

        # 进度条
        self.progress = QProgressBar()
        self.progress.setStyleSheet(f'''
            QProgressBar {{ background: {DARK_CARD}; border: 1px solid {DARK_BORDER};
                border-radius: 4px; text-align: center; color: {TEXT_PRIMARY}; height: 18px; }}
            QProgressBar::chunk {{ background: {ACCENT_GREEN}; border-radius: 3px; }}
        ''')
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # 控制台（固定高度）
        console_group = QGroupBox('控制台')
        console_group.setStyleSheet(self._group_style())
        cl = QVBoxLayout(console_group)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(120)
        self.console.setStyleSheet(f'''
            QTextEdit {{ background: #010409; color: #3fb950;
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, monospace; font-size: 11px; }}
        ''')
        cl.addWidget(self.console)
        layout.addWidget(console_group)

        return panel

    def _create_strategy_group(self):
        group = QGroupBox('① 策略选择')
        group.setStyleSheet(self._group_style())
        layout = QGridLayout(group)
        layout.setSpacing(6)

        layout.addWidget(QLabel('策略名称:'), 0, 0)
        self.strategy_combo = QComboBox()
        self.strategy_combo.setStyleSheet(self._combo_style())
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed)
        layout.addWidget(self.strategy_combo, 0, 1)
        # 从STRATEGY_REGISTRY动态加载策略列表
        self._refresh_strategy_combo()

        return group

    def _create_stock_group(self):
        group = QGroupBox('② 股票参数')
        group.setStyleSheet(self._group_style())
        layout = QGridLayout(group)
        layout.setSpacing(6)

        layout.addWidget(QLabel('股票代码:'), 0, 0)
        self.code_input = QLineEdit('600580')
        self.code_input.setStyleSheet(self._input_style())
        self.code_input.setPlaceholderText('输入6位代码或股票名称')
        self._converting_code = False
        self.code_input.editingFinished.connect(self._auto_convert_stock_code)
        layout.addWidget(self.code_input, 0, 1)

        layout.addWidget(QLabel('股票池:'), 1, 0)
        stock_pool_layout = QHBoxLayout()
        self.rb_single = QRadioButton('单股票')
        self.rb_single.setChecked(True)
        self.rb_ai = QRadioButton('AI选股池')
        self.rb_watch = QRadioButton('自选股')
        self.rb_realtime = QRadioButton('实时监控')
        self.rb_all = QRadioButton('全市场')
        for rb in [self.rb_single, self.rb_ai, self.rb_watch, self.rb_realtime, self.rb_all]:
            rb.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 11px;')
        self.stock_pool_group = QButtonGroup()
        self.stock_pool_group.addButton(self.rb_single, 1)
        self.stock_pool_group.addButton(self.rb_ai, 2)
        self.stock_pool_group.addButton(self.rb_watch, 3)
        self.stock_pool_group.addButton(self.rb_realtime, 4)
        self.stock_pool_group.addButton(self.rb_all, 5)
        stock_pool_layout.addWidget(self.rb_single)
        stock_pool_layout.addWidget(self.rb_ai)
        stock_pool_layout.addWidget(self.rb_watch)
        stock_pool_layout.addWidget(self.rb_realtime)
        stock_pool_layout.addWidget(self.rb_all)
        layout.addLayout(stock_pool_layout, 1, 1)

        return group

    def _create_data_group(self):
        group = QGroupBox('③ 数据设置')
        group.setStyleSheet(self._group_style())
        layout = QGridLayout(group)
        layout.setSpacing(6)

        layout.addWidget(QLabel('K线周期:'), 0, 0)
        self.period_combo = QComboBox()
        self.period_combo.addItems(['日线', '60分钟', '30分钟', '周线'])
        self.period_combo.setStyleSheet(self._combo_style())
        layout.addWidget(self.period_combo, 0, 1)

        layout.addWidget(QLabel('复权:'), 1, 0)
        self.adjust_combo = QComboBox()
        self.adjust_combo.addItems(['前复权', '后复权', '不复权'])
        self.adjust_combo.setStyleSheet(self._combo_style())
        layout.addWidget(self.adjust_combo, 1, 1)

        layout.addWidget(QLabel('开始日期:'), 2, 0)
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate(2024, 1, 1))
        self.start_date.setCalendarPopup(True)
        self.start_date.setStyleSheet(self._input_style())
        self.start_date.setMaximumWidth(160)
        # 限制日历弹出框宽度，防止被右边掩盖
        start_cal = self.start_date.calendarWidget()
        if start_cal:
            start_cal.setMaximumWidth(240)
            start_cal.setStyleSheet(self._input_style())
        layout.addWidget(self.start_date, 2, 1)

        layout.addWidget(QLabel('结束日期:'), 3, 0)
        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        self.end_date.setStyleSheet(self._input_style())
        self.end_date.setMaximumWidth(160)
        end_cal = self.end_date.calendarWidget()
        if end_cal:
            end_cal.setMaximumWidth(240)
            end_cal.setStyleSheet(self._input_style())
        layout.addWidget(self.end_date, 3, 1)

        return group

    def _create_trade_group(self):
        group = QGroupBox('④ 交易参数')
        group.setStyleSheet(self._group_style())
        layout = QGridLayout(group)
        layout.setSpacing(6)

        layout.addWidget(QLabel('初始资金:'), 0, 0)
        self.capital = QDoubleSpinBox()
        self.capital.setRange(10000, 100000000)
        self.capital.setValue(100000)
        self.capital.setSingleStep(10000)
        self.capital.setStyleSheet(self._input_style())
        layout.addWidget(self.capital, 0, 1)

        layout.addWidget(QLabel('手续费(万):'), 1, 0)
        self.commission = QDoubleSpinBox()
        self.commission.setRange(0, 10)
        self.commission.setValue(3)
        self.commission.setSingleStep(0.5)
        self.commission.setStyleSheet(self._input_style())
        layout.addWidget(self.commission, 1, 1)

        layout.addWidget(QLabel('印花税(千):'), 2, 0)
        self.stamp_tax = QDoubleSpinBox()
        self.stamp_tax.setRange(0, 10)
        self.stamp_tax.setValue(1)
        self.stamp_tax.setSingleStep(0.1)
        self.stamp_tax.setStyleSheet(self._input_style())
        layout.addWidget(self.stamp_tax, 2, 1)

        layout.addWidget(QLabel('滑点(%):'), 3, 0)
        self.slippage = QDoubleSpinBox()
        self.slippage.setRange(0, 5)
        self.slippage.setValue(0.05)
        self.slippage.setSingleStep(0.01)
        self.slippage.setDecimals(3)
        self.slippage.setStyleSheet(self._input_style())
        layout.addWidget(self.slippage, 3, 1)

        layout.addWidget(QLabel('单票仓位(%):'), 4, 0)
        self.position_pct = QDoubleSpinBox()
        self.position_pct.setRange(10, 100)
        self.position_pct.setValue(95)
        self.position_pct.setStyleSheet(self._input_style())
        layout.addWidget(self.position_pct, 4, 1)

        layout.addWidget(QLabel('止盈(%):'), 5, 0)
        self.take_profit = QDoubleSpinBox()
        self.take_profit.setRange(1, 100)
        self.take_profit.setValue(20)
        self.take_profit.setSingleStep(1)
        self.take_profit.setStyleSheet(self._input_style())
        layout.addWidget(self.take_profit, 5, 1)

        layout.addWidget(QLabel('止损(%):'), 6, 0)
        self.stop_loss = QDoubleSpinBox()
        self.stop_loss.setRange(1, 50)
        self.stop_loss.setValue(5)
        self.stop_loss.setSingleStep(1)
        self.stop_loss.setStyleSheet(self._input_style())
        layout.addWidget(self.stop_loss, 6, 1)

        layout.addWidget(QLabel('持仓天数:'), 7, 0)
        self.hold_days = QSpinBox()
        self.hold_days.setRange(1, 60)
        self.hold_days.setValue(20)
        self.hold_days.setStyleSheet(self._input_style())
        layout.addWidget(self.hold_days, 7, 1)

        return group

    def _create_control_group(self):
        group = QGroupBox('⑤ 操作控制')
        group.setStyleSheet(self._group_style())
        layout = QGridLayout(group)
        layout.setSpacing(6)

        self.btn_download = QPushButton('⬇ 下载数据')
        self.btn_download.setStyleSheet(self._btn_style(ACCENT_BLUE))
        self.btn_download.clicked.connect(self._download_data)
        layout.addWidget(self.btn_download, 0, 0)

        self.btn_start = QPushButton('▶ 开始回测')
        self.btn_start.setStyleSheet(self._btn_style(ACCENT_GREEN))
        self.btn_start.clicked.connect(self._start_backtest)
        layout.addWidget(self.btn_start, 0, 1)

        self.btn_stop = QPushButton('⏹ 停止回测')
        self.btn_stop.setStyleSheet(self._btn_style(ACCENT_RED))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_backtest)
        layout.addWidget(self.btn_stop, 1, 0)

        self.btn_optimize = QPushButton('🔧 参数优化')
        self.btn_optimize.setStyleSheet(self._btn_style(ACCENT_YELLOW))
        self.btn_optimize.clicked.connect(self._open_optimize)
        layout.addWidget(self.btn_optimize, 1, 1)

        self.btn_code = QPushButton('⚙ 策略配置')
        self.btn_code.setStyleSheet(self._btn_style(ACCENT_PURPLE))
        self.btn_code.clicked.connect(self._open_strategy_config)
        layout.addWidget(self.btn_code, 2, 0)

        self.btn_reload = QPushButton('🔄 策略重载')
        self.btn_reload.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        self.btn_reload.clicked.connect(self._reload_strategy)
        layout.addWidget(self.btn_reload, 2, 1)

        self.btn_ai_analyze = QPushButton('🧠 AI策略分析')
        self.btn_ai_analyze.setStyleSheet(self._btn_style(ACCENT_PURPLE))
        self.btn_ai_analyze.clicked.connect(self._ai_analyze_strategy)
        layout.addWidget(self.btn_ai_analyze, 3, 0, 1, 2)

        return group

    # ---------- 右侧：分析结果区 ----------
    def _create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f'''
            QTabWidget::pane {{ border: 1px solid {DARK_BORDER}; border-radius: 6px; background: {DARK_CARD}; }}
            QTabBar::tab {{ background: {DARK_CARD}; color: {TEXT_SECONDARY};
                padding: 8px 14px; border: 1px solid {DARK_BORDER}; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px; font-size: 12px; }}
            QTabBar::tab:selected {{ background: {ACCENT_BLUE}; color: white; }}
        ''')

        self.tab_overview = self._create_overview_tab()
        self.tab_equity = self._create_equity_tab()
        self.tab_drawdown = self._create_drawdown_tab()
        self.tab_daily = self._create_daily_tab()
        self.tab_orders = self._create_orders_tab()
        self.tab_trades = self._create_trades_tab()
        self.tab_kline = self._create_kline_tab()
        self.tab_annotation = self._create_annotation_tab()
        self.tab_force_behavior = self._create_force_behavior_tab()

        self.tabs.addTab(self.tab_overview, '📊 业绩概览')
        self.tabs.addTab(self.tab_equity, '📈 账户净值')
        self.tabs.addTab(self.tab_drawdown, '📉 净值回撤')
        self.tabs.addTab(self.tab_daily, '💰 每日盈亏')
        self.tabs.addTab(self.tab_orders, '📋 委托记录')
        self.tabs.addTab(self.tab_trades, '✅ 成交记录')
        self.tabs.addTab(self.tab_kline, '🕯 K线回测图')
        self.tabs.addTab(self.tab_annotation, '✏️ K线标注编辑')
        self.tabs.addTab(self.tab_force_behavior, '🎯 主力行为选股')

        layout.addWidget(self.tabs)
        return panel

    def _create_overview_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # === 16指标卡片网格（4x4）===
        grid_widget = QWidget()
        grid_widget.setMinimumHeight(360)
        self.metrics_grid = QGridLayout(grid_widget)
        self.metrics_grid.setSpacing(8)
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)

        self.metric_cards = {}
        # 按图2布局：4行x4列
        metrics = [
            # 行1
            ('回测周期', 'N/A', 'neutral'),
            ('总收益率', 'N/A', 'profit'),
            ('年化收益', 'N/A', 'profit'),
            ('总盈亏', 'N/A', 'profit'),
            # 行2
            ('最大回撤', 'N/A', 'loss'),
            ('收益回撤比', 'N/A', 'neutral'),
            ('盈亏比', 'N/A', 'neutral'),
            ('总交易次数', 'N/A', 'neutral'),
            # 行3
            ('胜率', 'N/A', 'profit'),
            ('最优仓位比例', 'N/A', 'neutral'),
            ('平均持仓天数', 'N/A', 'neutral'),
            ('夏普比率', 'N/A', 'profit'),
            # 行4
            ('索提诺比率', 'N/A', 'profit'),
            ('卡尔玛比率', 'N/A', 'profit'),
            ('综合评分', 'N/A', 'profit'),
            ('初始资金', 'N/A', 'neutral'),
        ]

        for i, (name, value, mtype) in enumerate(metrics):
            row, col = i // 4, i % 4
            card = self._create_metric_card(name, value, mtype)
            self.metrics_grid.addWidget(card, row, col)
            self.metric_cards[name] = card

        layout.addWidget(grid_widget)

        # === 账户净值曲线图 ===
        equity_group = QGroupBox('账户净值')
        equity_group.setStyleSheet(self._group_style())
        equity_layout = QVBoxLayout(equity_group)
        equity_layout.setContentsMargins(5, 15, 5, 5)
        self.overview_equity_chart = self._create_mpl_canvas(height=2.5)
        self.overview_equity_chart.setMinimumHeight(220)
        equity_layout.addWidget(self.overview_equity_chart)
        layout.addWidget(equity_group, stretch=1)

        # === 每日盈亏柱状图 ===
        daily_group = QGroupBox('每日盈亏')
        daily_group.setStyleSheet(self._group_style())
        daily_layout = QVBoxLayout(daily_group)
        daily_layout.setContentsMargins(5, 15, 5, 5)
        self.overview_daily_chart = self._create_mpl_canvas(height=2.5)
        self.overview_daily_chart.setMinimumHeight(220)
        daily_layout.addWidget(self.overview_daily_chart)
        layout.addWidget(daily_group, stretch=1)

        return widget

    def _create_mpl_canvas(self, height=2.5):
        """创建matplotlib画布用于嵌入Qt"""
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        from PyQt6.QtWidgets import QSizePolicy
        import matplotlib
        matplotlib.use('Agg')
        # 设置中文字体，解决乱码
        matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        matplotlib.rcParams['axes.unicode_minus'] = False
        fig = Figure(figsize=(8, height), dpi=100, facecolor='#0d1117')
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet('background: #0d1117;')
        canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return canvas

    def _plot_equity_curve(self, canvas, equity_history):
        """绘制净值曲线（参考图二样式）"""
        fig = canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0d1117')
        if equity_history and len(equity_history) > 1:
            dates = list(range(len(equity_history)))
            values = []
            for e in equity_history:
                if isinstance(e, dict):
                    v = e.get('asset', e.get('equity', e.get('value', e.get('total_asset', 100000))))
                else:
                    v = e
                values.append(float(v))
            # 黄色曲线，无填充
            ax.plot(dates, values, color='#fbbf24', linewidth=1.5, label='账户净值')
            ax.set_ylabel('净值', color='#8b949e', fontsize=10)
            ax.set_xlabel('时间', color='#8b949e', fontsize=10)
            # Y轴范围：从初始资金开始，上限留出空间
            initial = values[0]
            v_max = max(values)
            v_min = min(values)
            y_bottom = min(initial, v_min) * 0.98
            y_top = v_max * 1.05
            ax.set_ylim(y_bottom, y_top)
            # Y轴千分位格式化
            from matplotlib.ticker import FuncFormatter
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:,.0f}'))
            # 右上角图例
            ax.legend(loc='upper right', facecolor='#161b22', edgecolor='#30363d',
                     labelcolor='#f0f6fc', fontsize=10)
            # 最终值标注
            ax.annotate(f'{values[-1]:,.0f}', xy=(len(values)-1, values[-1]),
                       color='#fbbf24', fontsize=10, fontweight='bold', ha='right', va='bottom')
        else:
            ax.text(0.5, 0.5, '回测完成后显示净值曲线', ha='center', va='center',
                    color='#8b949e', fontsize=12, transform=ax.transAxes)
        ax.tick_params(colors='#8b949e', labelsize=9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('#30363d')
        ax.spines['left'].set_color('#30363d')
        ax.grid(True, alpha=0.1, color='#30363d')
        fig.tight_layout(pad=0.5)
        canvas.draw()

    def _plot_daily_pnl(self, canvas, daily_pnl):
        """绘制每日盈亏柱状图（参考图二样式：红上绿下）"""
        fig = canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0d1117')
        if daily_pnl and len(daily_pnl) > 0:
            dates = list(range(len(daily_pnl)))
            values = []
            for d in daily_pnl:
                if isinstance(d, dict):
                    v = d.get('pnl', d.get('profit', d.get('daily_pnl', d.get('net_profit', 0))))
                else:
                    v = d
                try:
                    values.append(float(v))
                except (ValueError, TypeError):
                    values.append(0.0)
            colors = ['#ef4444' if v >= 0 else '#22c55e' for v in values]
            # 柱子宽度
            bar_width = 0.8 if len(values) < 100 else 0.6
            ax.bar(dates, values, color=colors, width=bar_width, alpha=0.9, edgecolor='none')
            # 零轴虚线
            ax.axhline(y=0, color='#6e7681', linewidth=1.0, linestyle='--')
            ax.set_ylabel('盈亏', color='#8b949e', fontsize=10)
            ax.set_xlabel('时间', color='#8b949e', fontsize=10)
            # Y轴千分位格式化
            from matplotlib.ticker import FuncFormatter
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:,.0f}'))
            # Y轴对称范围
            v_max_abs = max(abs(min(values)), abs(max(values))) if values else 1
            ax.set_ylim(-v_max_abs * 1.1, v_max_abs * 1.1)
            # 右上角图例
            from matplotlib.patches import Patch
            legend_elements = [Patch(facecolor='#ef4444', label='每日盈亏')]
            ax.legend(handles=legend_elements, loc='upper right',
                     facecolor='#161b22', edgecolor='#30363d',
                     labelcolor='#f0f6fc', fontsize=10)
        else:
            ax.text(0.5, 0.5, '回测完成后显示每日盈亏', ha='center', va='center',
                    color='#8b949e', fontsize=12, transform=ax.transAxes)
        ax.tick_params(colors='#8b949e', labelsize=9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('#30363d')
        ax.spines['left'].set_color('#30363d')
        ax.grid(True, alpha=0.1, color='#30363d', axis='y')
        fig.tight_layout(pad=0.5)
        canvas.draw()

    def _create_metric_card(self, name, value, mtype='neutral'):
        card = QFrame()
        # 高亮关键指标
        highlight = name in ('回测周期', '总收益率', '最大回撤', '夏普比率', '综合评分')
        border_color = '#1f6feb' if highlight else DARK_BORDER
        card.setStyleSheet(f'''
            QFrame {{ background: {DARK_CARD}; border: 1px solid {border_color};
                border-radius: 6px; }}
        ''')
        card.setMinimumHeight(68)
        card.setMaximumHeight(75)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        name_label = QLabel(name)
        name_label.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFixedHeight(16)
        layout.addWidget(name_label)

        value_label = QLabel(value)
        value_label.setWordWrap(True)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if mtype == 'profit':
            color = '#f85149'
        elif mtype == 'loss':
            color = '#3fb950'
        else:
            color = TEXT_PRIMARY
        font_size = 13 if name == '回测周期' else 18
        value_label.setStyleSheet(f'color: {color}; font-size: {font_size}px; font-weight: bold;')
        value_label.setObjectName('value_label')
        layout.addWidget(value_label)
        return card

    def _create_equity_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        self.equity_chart = QTextEdit()
        self.equity_chart.setReadOnly(True)
        self.equity_chart.setStyleSheet(self._chart_style())
        self.equity_chart.setPlaceholderText('净值曲线（回测完成后显示）')
        layout.addWidget(self.equity_chart)
        return widget

    def _create_drawdown_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        self.drawdown_chart = QTextEdit()
        self.drawdown_chart.setReadOnly(True)
        self.drawdown_chart.setStyleSheet(self._chart_style())
        self.drawdown_chart.setPlaceholderText('回撤曲线（回测完成后显示）')
        layout.addWidget(self.drawdown_chart)
        return widget

    def _create_daily_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        self.daily_table = QTableWidget()
        self.daily_table.setColumnCount(5)
        self.daily_table.setHorizontalHeaderLabels(['日期', '总资产', '当日盈亏', '累计盈亏', '收益率%'])
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.daily_table.setStyleSheet(self._table_style())
        layout.addWidget(self.daily_table)
        return widget

    def _create_orders_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(6)
        self.orders_table.setHorizontalHeaderLabels(['时间', '代码', '方向', '委托价', '委托量', '状态'])
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.orders_table.setStyleSheet(self._table_style())
        layout.addWidget(self.orders_table)
        return widget

    def _update_orders(self, r):
        """更新委托记录（来自真实订单数据）"""
        orders = r.get('orders', [])
        self.orders_table.setRowCount(len(orders))
        for i, o in enumerate(orders):
            self.orders_table.setItem(i, 0, QTableWidgetItem(str(o.get('filled_date', o.get('date', '')))))
            self.orders_table.setItem(i, 1, QTableWidgetItem(str(o.get('code', r['code']))))
            side = o.get('side', '')
            side_cn = '买入' if side == 'buy' else ('卖出' if side == 'sell' else side)
            self.orders_table.setItem(i, 2, QTableWidgetItem(side_cn))
            self.orders_table.setItem(i, 3, QTableWidgetItem(f"{o.get('price', o.get('filled_price', 0)):.2f}"))
            self.orders_table.setItem(i, 4, QTableWidgetItem(str(o.get('quantity', o.get('filled_quantity', 0)))))
            status = o.get('status', 'filled')
            status_cn = {'filled': '已成交', 'pending': '待成交', 'cancelled': '已取消', 'rejected': '已拒绝'}.get(status, status)
            status_item = QTableWidgetItem(status_cn)
            if status == 'filled':
                status_item.setForeground(QColor(ACCENT_GREEN))
            elif status in ('cancelled', 'rejected'):
                status_item.setForeground(QColor(ACCENT_RED))
            self.orders_table.setItem(i, 5, status_item)

    def _create_trades_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        hint = QLabel('💡 双击"代码"列可打开K线详情图，显示买卖点位')
        hint.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px; padding: 4px;')
        layout.addWidget(hint)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(7)
        self.trades_table.setHorizontalHeaderLabels(
            ['日期', '代码', '方向', '成交价', '数量', '金额', '盈亏']
        )
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trades_table.setStyleSheet(self._table_style())
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.cellDoubleClicked.connect(self._on_trade_double_clicked)
        layout.addWidget(self.trades_table)
        return widget

    def _create_kline_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # B/S标记样式设置栏
        style_bar = QHBoxLayout()
        style_bar.setSpacing(8)

        style_title = QLabel('🎨 B/S标记:')
        style_title.setStyleSheet('color: #8b949e; font-size: 11px;')
        style_bar.addWidget(style_title)

        # B点颜色
        style_bar.addWidget(QLabel('B色:'))
        self.bs_buy_color = QComboBox()
        self.bs_buy_color.addItems(['#ef4444 红', '#f85149 亮红', '#ff6b6b 粉红', '#ffd700 金黄', '#ffffff 白'])
        self.bs_buy_color.setFixedWidth(100)
        self.bs_buy_color.setStyleSheet('QComboBox { background: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; }')
        style_bar.addWidget(self.bs_buy_color)

        # S点颜色
        style_bar.addWidget(QLabel('S色:'))
        self.bs_sell_color = QComboBox()
        self.bs_sell_color.addItems(['#22c55e 绿', '#3fb950 亮绿', '#00e676 翠绿', '#58a6ff 蓝', '#ff8c00 橙'])
        self.bs_sell_color.setFixedWidth(100)
        self.bs_sell_color.setStyleSheet('QComboBox { background: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; }')
        style_bar.addWidget(self.bs_sell_color)

        # 字体大小
        style_bar.addWidget(QLabel('字号:'))
        self.bs_font_size = QComboBox()
        self.bs_font_size.addItems(['12', '14', '16', '18', '20', '24', '28'])
        self.bs_font_size.setCurrentText('18')
        self.bs_font_size.setFixedWidth(60)
        self.bs_font_size.setStyleSheet('QComboBox { background: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; }')
        style_bar.addWidget(self.bs_font_size)

        # 距离
        style_bar.addWidget(QLabel('距离:'))
        self.bs_distance = QComboBox()
        self.bs_distance.addItems(['0', '2', '4', '6', '8', '10', '15'])
        self.bs_distance.setCurrentText('2')
        self.bs_distance.setFixedWidth(60)
        self.bs_distance.setStyleSheet('QComboBox { background: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; }')
        style_bar.addWidget(self.bs_distance)

        # 应用按钮
        self.bs_apply_btn = QPushButton('应用')
        self.bs_apply_btn.setFixedWidth(60)
        self.bs_apply_btn.setStyleSheet('QPushButton { background: #238636; color: white; border: none; border-radius: 4px; padding: 4px 12px; } QPushButton:hover { background: #2ea043; }')
        self.bs_apply_btn.clicked.connect(self._apply_bs_style)
        style_bar.addWidget(self.bs_apply_btn)

        style_bar.addStretch()
        layout.addLayout(style_bar)

        # K线图
        from ui.backtest_kline_echarts import BacktestKlineECharts
        self.kline_widget = BacktestKlineECharts()
        layout.addWidget(self.kline_widget, stretch=1)
        return widget

    def _apply_bs_style(self):
        """应用B/S标记样式设置"""
        try:
            buy_color = self.bs_buy_color.currentText().split()[0]
            sell_color = self.bs_sell_color.currentText().split()[0]
            font_size = int(self.bs_font_size.currentText())
            distance = int(self.bs_distance.currentText())
            self.kline_widget.set_bs_style(
                buy_color=buy_color,
                sell_color=sell_color,
                font_size=font_size,
                distance=distance
            )
        except Exception as e:
            print(f"[回测] 应用B/S样式失败: {e}")

    def _create_annotation_tab(self):
        """创建K线标注编辑Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 顶部说明
        tip_label = QLabel(
            "💡 使用说明: 点击【编辑B点】后点击K线添加买入点 | "
            "点击【编辑S点】后点击K线添加卖出点 | "
            "点击【选择区域】后依次点击两根K线选择区间 | "
            "回测完成后自动加载K线数据"
        )
        tip_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        # K线编辑器
        self.kline_editor = KlineEditorWidget()
        layout.addWidget(self.kline_editor, stretch=1)

        return widget

    def _create_force_behavior_tab(self):
        """创建强势主力行为选股Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 顶部说明
        tip_label = QLabel(
            "🎯 强势主力行为选股系统 V1.0 | 三大模型：涨停回调/箱体突破/量价突破 | "
            "AI 6维度评分，70分以下自动过滤"
        )
        tip_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        # 主力行为选股面板
        self.force_behavior_panel = ForceBehaviorPanel()
        layout.addWidget(self.force_behavior_panel, stretch=1)

        return widget

    # ---------- 操作方法 ----------
    def _download_data(self):
        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, '提示', '请输入股票代码')
            return
        self._append_log(f"正在下载 {code} 的K线数据...")
        try:
            from backtest.data.data_loader import TDXDataLoader
            loader = TDXDataLoader()
            data = loader.get_kline(
                code=code.zfill(6),
                start=self.start_date.date().toString('yyyy-MM-dd'),
                end=self.end_date.date().toString('yyyy-MM-dd'),
                adjust='qfq'
            )
            if data:
                count = len(data.get('close', []))
                self._append_log(f"✅ 下载成功: {count} 根K线")
            else:
                self._append_log("❌ 下载失败")
        except Exception as e:
            self._append_log(f"❌ 下载异常: {e}")

    def _start_backtest(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, '提示', '回测正在进行中')
            return

        # 处理股票池选项
        pool_id = self.stock_pool_group.checkedId()
        if pool_id == 4:  # 实时监控
            stocks = self._load_realtime_stocks()
            if not stocks:
                QMessageBox.information(self, '提示',
                    '实时监控股票池为空\n请先在"实时监控"页面筛选股票')
                return
            # 显示股票选择对话框
            code = self._select_stock_from_pool(stocks, '实时监控股票池')
            if not code:
                return
            self.code_input.setText(code)
        elif pool_id == 2:  # AI选股池
            stocks = self._load_ai_stocks()
            if stocks:
                code = self._select_stock_from_pool(stocks, 'AI选股池')
                if code:
                    self.code_input.setText(code)
        elif pool_id == 3:  # 自选股
            stocks = self._load_watchlist()
            if stocks:
                code = self._select_stock_from_pool(stocks, '自选股')
                if code:
                    self.code_input.setText(code)

        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, '提示', '请输入股票代码')
            return

        adjust_map = {'前复权': 'qfq', '后复权': 'hfq', '不复权': 'none'}

        params = {
            'strategy_name': self.strategy_combo.currentText(),
            'code': code,
            'start_date': self.start_date.date().toString('yyyy-MM-dd'),
            'end_date': self.end_date.date().toString('yyyy-MM-dd'),
            'capital': self.capital.value(),
            'commission': self.commission.value() / 10000,
            'stamp_tax': self.stamp_tax.value() / 1000,
            'slippage': self.slippage.value() / 100,
            'position_pct': self.position_pct.value() / 100,
            'take_profit': self.take_profit.value() / 100,
            'stop_loss': self.stop_loss.value() / 100,
            'hold_days': self.hold_days.value(),
            'adjust': adjust_map.get(self.adjust_combo.currentText(), 'qfq'),
            'period': self.period_combo.currentText(),
            # 用户配置的策略参数（优先级最高）
            'strategy_params': dict(self.strategy_params),
        }

        self.console.clear()
        self.progress.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.worker = BacktestThread(params)
        self.worker.log.connect(self._append_log)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _auto_convert_stock_code(self):
        """股票代码输入框：自动将股票名称转换为6位代码（安全降级，不崩溃）"""
        if getattr(self, '_converting_code', False):
            return
        text = self.code_input.text().strip()
        if not text:
            return
        # 已经是6位数字，直接通过
        if text.isdigit() and len(text) == 6:
            return
        self._converting_code = True
        try:
            # 尝试名称转代码（加保护，失败不影响程序）
            try:
                from utils.stock_name_manager import get_all_stock_names
                stock_names = get_all_stock_names()
                if not stock_names or not isinstance(stock_names, dict):
                    self._append_log(f"[代码] 名称字典未就绪，保留输入: {text}")
                    return
                # 精确匹配
                if text in stock_names:
                    code = str(stock_names[text])
                    if code.isdigit() and len(code) == 6:
                        self.code_input.setText(code)
                        self._append_log(f"[代码] {text} → {code}")
                        return
                # 模糊匹配（包含）
                for name, code in stock_names.items():
                    try:
                        if text in str(name) or str(name) in text:
                            code = str(code)
                            if code.isdigit() and len(code) == 6:
                                self.code_input.setText(code)
                                self._append_log(f"[代码] {text} 匹配到 {name} → {code}")
                                return
                    except Exception:
                        continue
                # 没找到，提示但不崩溃
                self._append_log(f"[代码] 未找到股票 '{text}'，请输入6位数字代码")
            except Exception as e:
                self._append_log(f"[代码转换] 跳过（{type(e).__name__}），请手动输入6位代码")
        finally:
            self._converting_code = False

    def _load_realtime_stocks(self):
        """加载实时监控筛选的股票列表"""
        stocks = []
        try:
            # 尝试从实时监控缓存加载
            cache_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'cache', 'realtime_monitor.json'
            )
            if os.path.exists(cache_file):
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            code = item.get('code', item.get('stock_code', ''))
                            name = item.get('name', item.get('stock_name', ''))
                            if code:
                                stocks.append({'code': str(code).zfill(6), 'name': name})
                        elif isinstance(item, str):
                            stocks.append({'code': item.zfill(6), 'name': ''})
            # 尝试从Pro股票池缓存加载
            pro_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'cache', 'pro_stock_pool.json'
            )
            if not stocks and os.path.exists(pro_file):
                import json
                with open(pro_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data[:50]:  # 最多50只
                        code = item.get('code', '') if isinstance(item, dict) else str(item)
                        name = item.get('name', '') if isinstance(item, dict) else ''
                        if code:
                            stocks.append({'code': str(code).zfill(6), 'name': name})
        except Exception as e:
            self._append_log(f"加载实时监控股票池失败: {e}")
        return stocks

    def _load_ai_stocks(self):
        """加载AI选股池"""
        stocks = []
        try:
            cache_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'cache', 'ai_stock_pool.json'
            )
            if os.path.exists(cache_file):
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data[:50]:
                        code = item.get('code', '') if isinstance(item, dict) else str(item)
                        name = item.get('name', '') if isinstance(item, dict) else ''
                        if code:
                            stocks.append({'code': str(code).zfill(6), 'name': name})
        except Exception:
            pass
        return stocks

    def _load_watchlist(self):
        """加载自选股"""
        stocks = []
        try:
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'watchlist.json'
            )
            if os.path.exists(config_file):
                import json
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        code = item.get('code', '') if isinstance(item, dict) else str(item)
                        name = item.get('name', '') if isinstance(item, dict) else ''
                        if code:
                            stocks.append({'code': str(code).zfill(6), 'name': name})
        except Exception:
            pass
        return stocks

    def _select_stock_from_pool(self, stocks, pool_name):
        """从股票池中选择一只股票，返回代码"""
        if not stocks:
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle(f'选择股票 - {pool_name} ({len(stocks)}只)')
        dlg.setMinimumSize(400, 500)
        dlg.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        layout = QVBoxLayout(dlg)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['代码', '名称'])
        table.setRowCount(len(stocks))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(self._table_style())
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, s in enumerate(stocks):
            table.setItem(i, 0, QTableWidgetItem(s['code']))
            table.setItem(i, 1, QTableWidgetItem(s.get('name', '')))
        layout.addWidget(table)

        selected_code = [None]
        def _on_select():
            row = table.currentRow()
            if row >= 0:
                selected_code[0] = stocks[row]['code']
                dlg.accept()
        table.cellDoubleClicked.connect(lambda r, c: _on_select())

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton('确定回测')
        btn_ok.setStyleSheet(self._btn_style(ACCENT_GREEN))
        btn_ok.clicked.connect(_on_select)
        btn_cancel = QPushButton('取消')
        btn_cancel.setStyleSheet(self._btn_style(ACCENT_RED))
        btn_cancel.clicked.connect(dlg.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        dlg.exec()
        return selected_code[0]

    def _stop_backtest(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.btn_start.setEnabled(True)
            self._append_log("回测已停止")

    def _open_optimize(self):
        adjust_map = {'前复权': 'qfq', '后复权': 'hfq', '不复权': 'none'}
        params = {
            'code': self.code_input.text().strip(),
            'start_date': self.start_date.date().toString('yyyy-MM-dd'),
            'end_date': self.end_date.date().toString('yyyy-MM-dd'),
            'capital': self.capital.value(),
            'commission': self.commission.value() / 10000,
            'stamp_tax': self.stamp_tax.value() / 1000,
            'slippage': self.slippage.value() / 100,
            'adjust': adjust_map.get(self.adjust_combo.currentText(), 'qfq'),
        }
        dlg = ParamOptimizeDialog(self, backtest_params=params)
        dlg.exec()

    def _open_strategy_config(self):
        """打开策略配置对话框：动态读取策略参数定义 + 保存到JSON + 查看源码"""
        from backtest.strategy.strategy_config import (
            get_strategy_config, get_default_params, save_params, get_strategy_key
        )
        strategy_name = self.strategy_combo.currentText()
        config = get_strategy_config(strategy_name)
        param_defs = config["params"]

        dlg = QDialog(self)
        dlg.setWindowTitle(f'⚙ 策略配置 - {strategy_name}')
        dlg.setMinimumSize(540, 520)
        dlg.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        # --- 参数配置区（动态生成）---
        param_group = QGroupBox(f'{config["title"]} - 参数配置')
        param_group.setStyleSheet(self._group_style())
        pg = QGridLayout(param_group)
        pg.setSpacing(8)

        spin_boxes = {}  # 保存参数key -> 输入控件
        for row, (key, pdef) in enumerate(param_defs.items()):
            label = QLabel(f"{pdef['name']}{'(' + pdef['unit'] + ')' if pdef.get('unit') else ''}:")
            pg.addWidget(label, row, 0)

            current_val = self.strategy_params.get(key, pdef["default"])
            if pdef["type"] == "int":
                sp = QSpinBox()
                sp.setRange(pdef["min"], pdef["max"])
                sp.setSingleStep(pdef.get("step", 1))
                sp.setValue(int(current_val))
            else:
                sp = QDoubleSpinBox()
                sp.setRange(pdef["min"], pdef["max"])
                sp.setSingleStep(pdef.get("step", 0.1))
                sp.setDecimals(2)
                sp.setValue(float(current_val))
            sp.setStyleSheet(self._input_style())
            pg.addWidget(sp, row, 1)
            spin_boxes[key] = sp

        hint = QLabel('提示：修改参数后点击"保存并应用"，参数永久保存，下次回测生效')
        hint.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
        pg.addWidget(hint, len(param_defs), 0, 1, 2)

        layout.addWidget(param_group)

        # --- 当前参数预览 ---
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMaximumHeight(120)
        preview.setStyleSheet(f'''
            QTextEdit {{ background: #010409; color: #3fb950;
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, monospace; font-size: 11px; }}
        ''')
        def _update_preview():
            lines = [f'当前策略参数 ({strategy_name}):']
            for key, pdef in param_defs.items():
                val = spin_boxes[key].value()
                unit = pdef.get("unit", "")
                lines.append(f'  {key} = {val}{unit}')
            preview.setPlainText("\n".join(lines))
        _update_preview()
        # 实时更新预览
        for sp in spin_boxes.values():
            if isinstance(sp, QDoubleSpinBox):
                sp.valueChanged.connect(_update_preview)
            else:
                sp.valueChanged.connect(_update_preview)
        layout.addWidget(preview)

        # --- 按钮区 ---
        btn_layout = QHBoxLayout()

        btn_edit_code = QPushButton('✏️ 编辑源码')
        btn_edit_code.setStyleSheet(self._btn_style(ACCENT_ORANGE))
        btn_edit_code.clicked.connect(lambda: self._edit_strategy_source(strategy_name))
        btn_layout.addWidget(btn_edit_code)

        btn_view_code = QPushButton('📝 查看源码')
        btn_view_code.setStyleSheet(self._btn_style(ACCENT_BLUE))
        btn_view_code.clicked.connect(lambda: self._view_strategy_source(strategy_name))
        btn_layout.addWidget(btn_view_code)

        btn_new_strategy = QPushButton('➕ 上传新策略')
        btn_new_strategy.setStyleSheet(self._btn_style(ACCENT_GREEN))
        btn_new_strategy.clicked.connect(self._upload_new_strategy)
        btn_layout.addWidget(btn_new_strategy)

        btn_reset = QPushButton('↺ 恢复默认')
        btn_reset.setStyleSheet(self._btn_style(TEXT_SECONDARY))
        btn_layout.addWidget(btn_reset)

        btn_cancel = QPushButton('取消')
        btn_cancel.setStyleSheet(self._btn_style(ACCENT_RED))
        btn_cancel.clicked.connect(dlg.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton('💾 保存并应用')
        btn_save.setStyleSheet(self._btn_style(ACCENT_GREEN))
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

        # 恢复默认
        def _reset_defaults():
            defaults = get_default_params(strategy_name)
            for key, sp in spin_boxes.items():
                sp.setValue(defaults.get(key, param_defs[key]["default"]))
        btn_reset.clicked.connect(_reset_defaults)

        # 保存
        def _save_and_apply():
            new_params = {}
            for key, sp in spin_boxes.items():
                new_params[key] = sp.value()
            # 保存到内存
            self.strategy_params = new_params
            # 永久保存到JSON
            strategy_key = get_strategy_key(strategy_name)
            save_params(strategy_key, new_params)
            # 同步交易参数区的止盈止损
            if 'take_profit_pct' in new_params and hasattr(self, 'take_profit'):
                self.take_profit.setValue(new_params['take_profit_pct'])
            if 'stop_loss_pct' in new_params and hasattr(self, 'stop_loss'):
                self.stop_loss.setValue(new_params['stop_loss_pct'])
            if 'max_hold_days' in new_params and hasattr(self, 'hold_days'):
                self.hold_days.setValue(new_params['max_hold_days'])
            # 更新状态栏
            self._update_status_bar()
            # 日志
            param_str = ", ".join(f"{k}={v}" for k, v in new_params.items())
            self._append_log(f"策略参数已保存并应用: {param_str}")
            dlg.accept()
        btn_save.clicked.connect(_save_and_apply)

        dlg.exec()

    def _view_strategy_source(self, strategy_name=None):
        """查看策略源码（只读）"""
        if strategy_name is None:
            strategy_name = self.strategy_combo.currentText()
        file_map = {
            '三倍量突破策略': 'backtest/strategy/triple_volume.py',
            '五九回踩策略': 'backtest/strategy/pullback_59.py',
            'MACD金叉策略': 'backtest/strategy/triple_volume.py',
            '缠论一买策略': 'backtest/strategy/triple_volume.py',
            '缠论二买策略': 'backtest/strategy/triple_volume.py',
            'AI自然语言策略': 'backtest/strategy/triple_volume.py',
        }
        filename = file_map.get(strategy_name, 'backtest/strategy/triple_volume.py')
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            dlg = QDialog(self)
            dlg.setWindowTitle(f'策略源码 - {strategy_name}')
            dlg.setMinimumSize(700, 500)
            dlg.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
            layout = QVBoxLayout(dlg)
            text = QTextEdit()
            text.setReadOnly(True)
            text.setStyleSheet(f'''
                QTextEdit {{ background: #010409; color: #c9d1d9;
                    border: 1px solid {DARK_BORDER}; border-radius: 4px;
                    font-family: Consolas, monospace; font-size: 12px; }}
            ''')
            text.setPlainText(code)
            layout.addWidget(text)
            btn = QPushButton('关闭')
            btn.setStyleSheet(self._btn_style(ACCENT_BLUE))
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, '提示', f'读取策略源码失败: {e}')

    def _edit_strategy_source(self, strategy_name=None):
        """编辑策略源码（可修改保存）"""
        if strategy_name is None:
            strategy_name = self.strategy_combo.currentText()
        file_map = {
            '三倍量突破策略': 'backtest/strategy/triple_volume.py',
            '五九回踩策略': 'backtest/strategy/pullback_59.py',
            'MACD金叉策略': 'backtest/strategy/triple_volume.py',
            '缠论一买策略': 'backtest/strategy/triple_volume.py',
            '缠论二买策略': 'backtest/strategy/triple_volume.py',
            'AI自然语言策略': 'backtest/strategy/triple_volume.py',
        }
        filename = file_map.get(strategy_name, 'backtest/strategy/triple_volume.py')
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename)
        try:
            from ui.strategy_code_editor import StrategyCodeEditorDialog
            dlg = StrategyCodeEditorDialog(strategy_name, filepath, self)
            dlg.exec()
            # 编辑后重新加载策略模块
            if dlg.result() == QDialog.DialogCode.Accepted:
                self._reload_strategy()
                self._append_log(f"[策略] {strategy_name} 源码已更新并重新加载")
        except Exception as e:
            QMessageBox.warning(self, '提示', f'打开策略编辑器失败: {e}')

    def _upload_new_strategy(self):
        """上传新策略（输入源代码生成）"""
        try:
            from ui.strategy_code_editor import NewStrategyDialog
            dlg = NewStrategyDialog(self)
            dlg.strategy_created.connect(self._on_strategy_created)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, '提示', f'打开新策略对话框失败: {e}')

    def _on_strategy_created(self, name, class_name, file_name):
        """策略创建完成回调：刷新策略下拉框"""
        self._append_log(f"[策略] 新策略已创建: {name} ({class_name})")
        # 刷新策略下拉框
        self._refresh_strategy_combo()
        # 自动选中新创建的策略
        index = self.strategy_combo.findText(name)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        QMessageBox.information(self, '成功',
            f'策略 "{name}" 已创建并添加到下拉框！\n\n可直接选择使用。')

    def _refresh_strategy_combo(self):
        """从STRATEGY_REGISTRY刷新策略下拉框"""
        try:
            from backtest.strategy.strategy_config import STRATEGY_REGISTRY
            current = self.strategy_combo.currentText()
            self.strategy_combo.blockSignals(True)
            self.strategy_combo.clear()
            # 从注册表加载所有策略
            strategy_names = []
            for key, config in STRATEGY_REGISTRY.items():
                title = config.get('title', key)
                strategy_names.append(title)
            # 添加内置策略（如果不在注册表中）
            builtin = ['三倍量突破策略', '五九回踩策略', '回调五日线策略',
                       '五买：倍量回踩五日线承接', 'MACD金叉策略',
                       '缠论一买策略', '缠论二买策略', 'AI自然语言策略']
            for name in builtin:
                if name not in strategy_names:
                    strategy_names.append(name)
            self.strategy_combo.addItems(strategy_names)
            # 恢复之前的选择
            index = self.strategy_combo.findText(current)
            if index >= 0:
                self.strategy_combo.setCurrentIndex(index)
            self.strategy_combo.blockSignals(False)
            self._append_log(f"[策略] 策略列表已刷新，共{self.strategy_combo.count()}个策略")
        except Exception as e:
            print(f"[策略] 刷新下拉框失败: {e}")

    def _reload_strategy(self):
        """重新加载策略模块（清除import缓存）"""
        import importlib
        try:
            # 重新导入策略相关模块
            modules_to_reload = [
                'backtest.strategy.triple_volume',
                'backtest.strategy.pullback_59',
                'backtest.strategy.base',
                'backtest.strategy.adapter',
                'backtest.strategy.signal',
                'backtest.strategy.context',
            ]
            reloaded = []
            for mod_name in modules_to_reload:
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])
                    reloaded.append(mod_name.split('.')[-1])
            self._append_log(f"策略已重载: {', '.join(reloaded)}")
            QMessageBox.information(self, '提示', f'策略重载完成\n已刷新: {", ".join(reloaded)}')
        except Exception as e:
            self._append_log(f"策略重载失败: {e}")
            QMessageBox.warning(self, '提示', f'策略重载失败: {e}')

    def _ai_analyze_strategy(self):
        """AI策略分析"""
        from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox, QApplication
        from ai.strategy_backtest_explainer import get_strategy_backtest_explainer

        if not hasattr(self, 'report') or not self.report:
            QMessageBox.information(self, '提示', '请先运行回测，获取回测结果后再分析')
            return

        report = self.report
        strategy_name = report.get('strategy_name', '未知策略')

        # 构建回测结果
        backtest_result = {
            'total_return': report.get('total_return_pct', 0),
            'annual_return': report.get('annual_return', 0),
            'win_rate': report.get('win_rate', 0),
            'max_drawdown': report.get('max_drawdown', 0),
            'sharpe_ratio': report.get('sharpe', 0),
            'total_trades': report.get('trade_count', 0),
            'profit_trades': report.get('win_count', 0),
            'loss_trades': report.get('loss_count', 0),
            'profit_factor': report.get('profit_loss_ratio', 0),
        }

        explainer = get_strategy_backtest_explainer()
        analysis = explainer.analyze_backtest(strategy_name, backtest_result)

        # 显示对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f'🧠 AI策略分析 - {strategy_name}')
        dialog.resize(650, 600)
        dialog.setStyleSheet("""
            QDialog { background: #0d1117; }
            QTextEdit {
                background: #161b22; color: #f0f6fc;
                border: 1px solid #30363d; border-radius: 4px;
                padding: 8px; font-size: 12px;
            }
        """)

        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(explainer.format_report(analysis))
        layout.addWidget(text_edit)

        # AI深度分析按钮
        from PyQt6.QtWidgets import QPushButton, QHBoxLayout
        btn_layout = QHBoxLayout()
        ai_btn = QPushButton('🧠 AI深度解读')
        ai_btn.setStyleSheet("""
            QPushButton {
                background: #8957e5; color: white;
                border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: #a371f7; }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(ai_btn)
        layout.addLayout(btn_layout)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)

        def do_ai_deep():
            ai_btn.setEnabled(False)
            ai_btn.setText('分析中...')
            QApplication.processEvents()
            try:
                report_text = explainer.generate_ai_report(analysis)
                text_edit.setPlainText(report_text)
            except Exception as e:
                text_edit.setPlainText(f'AI分析失败: {e}')
            ai_btn.setEnabled(True)
            ai_btn.setText('🧠 AI深度解读')

        ai_btn.clicked.connect(do_ai_deep)

        dialog.exec()

    def _on_finished(self, report):
        self.report = report
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self._update_all_tabs(report)

    def _on_error(self, error):
        self._append_log(f"❌ 错误: {error}")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.critical(self, '错误', f'回测失败:\n{error[:500]}')

    def _update_all_tabs(self, r):
        self._update_overview(r)
        self._update_equity(r)
        self._update_drawdown(r)
        self._update_daily(r)
        self._update_orders(r)
        self._update_trades(r)
        self._update_kline(r)

    def _update_overview(self, r):
        # 计算衍生指标
        total_ret = r.get('total_return_pct', 0)
        max_dd = r.get('max_drawdown', 0)
        calmar = total_ret / max_dd if max_dd > 0 else 0
        sortino = r.get('sortino', r.get('sharpe', 0) * 0.8)
        # 综合评分：夏普*30 + 胜率*0.3 + 收益回撤比*5 + 盈亏比*10，上限100
        score = min(100, r.get('sharpe',0)*30 + r.get('win_rate',0)*0.3 + calmar*5 + r.get('profit_loss_ratio',0)*10)
        # 最优仓位比例估算（根据胜率和盈亏比）
        win_rate = r.get('win_rate', 0) / 100
        pl_ratio = r.get('profit_loss_ratio', 1)
        kelly = win_rate - (1-win_rate)/max(pl_ratio, 0.01)
        optimal_pos = max(10, min(100, kelly * 100)) if kelly > 0 else 10

        updates = {
            '回测周期': f"{r.get('start_date', '')}\n~{r.get('end_date', '')}",
            '总收益率': f"{total_ret:.2f}%",
            '年化收益': f"{r.get('annual_return', 0):.2f}%",
            '总盈亏': f"{r.get('total_return', 0):+,.0f}",
            '最大回撤': f"-{max_dd:.2f}%",
            '收益回撤比': f"{calmar:.2f}",
            '盈亏比': f"{r.get('profit_loss_ratio', 0):.2f}",
            '总交易次数': str(r.get('trade_count', 0)),
            '胜率': f"{r.get('win_rate', 0):.1f}%",
            '最优仓位比例': f"{optimal_pos:.1f}%",
            '平均持仓天数': f"{r.get('avg_hold_days', 0):.1f}",
            '夏普比率': f"{r.get('sharpe', 0):.2f}",
            '索提诺比率': f"{sortino:.2f}",
            '卡尔玛比率': f"{calmar:.2f}",
            '综合评分': f"{score:.2f}",
            '初始资金': f"{r.get('initial_cash', 100000):,.0f}",
        }
        for name, val in updates.items():
            if name in self.metric_cards:
                lbl = self.metric_cards[name].findChild(QLabel, 'value_label')
                if lbl:
                    lbl.setText(val)
                    color = TEXT_PRIMARY
                    if name in ['总收益率', '年化收益', '夏普比率', '索提诺比率', '卡尔玛比率', '综合评分', '胜率', '盈亏比', '收益回撤比']:
                        try:
                            num = float(val.replace('%', '').replace(',', '').replace('+', ''))
                            color = '#f87171' if num > 0 else '#4ade80'
                        except: pass
                    elif name in ['最大回撤']:
                        color = '#4ade80'
                    elif name == '总盈亏':
                        try:
                            num = float(val.replace(',', '').replace('+', ''))
                            color = '#f87171' if num > 0 else '#4ade80'
                        except: pass
                    fs = 14 if name == '回测周期' else 18
                    lbl.setStyleSheet(f'color: {color}; font-size: {fs}px; font-weight: bold;')

        # 绘制净值曲线
        equity_curve = r.get('equity_curve', [])
        if hasattr(self, 'overview_equity_chart'):
            self._plot_equity_curve(self.overview_equity_chart, equity_curve)

        # 绘制每日盈亏
        daily_pnl = r.get('daily_pnl', [])
        if hasattr(self, 'overview_daily_chart'):
            self._plot_daily_pnl(self.overview_daily_chart, daily_pnl)

    def _update_equity(self, r):
        curve = r.get('equity_curve', [])
        if not curve:
            return
        assets = [c['asset'] for c in curve]
        self._render_ascii_chart(self.equity_chart, curve, assets, '账户净值曲线')

    def _update_drawdown(self, r):
        dds = r.get('drawdowns', [])
        if not dds:
            return
        values = [d['drawdown'] for d in dds]
        self._render_ascii_chart(self.drawdown_chart, dds, values, '净值回撤曲线', inverse=True)

    def _render_ascii_chart(self, widget, data, values, title, inverse=False):
        if not values:
            return
        min_v, max_v = min(values), max(values)
        height, width = 18, 70
        lines = [f"=== {title} ===", f"最高: {max_v:,.2f}  最低: {min_v:,.2f}", ""]
        for row in range(height, -1, -1):
            threshold = min_v + (max_v - min_v) * row / height
            line = f"{threshold:>12,.2f} |"
            for col in range(width):
                idx = int(col * len(values) / width)
                if idx < len(values):
                    v = values[idx]
                    if inverse:
                        filled = v <= threshold if threshold < 0 else v >= threshold
                    else:
                        filled = v >= threshold
                    line += "█" if filled else " "
                else:
                    line += " "
            lines.append(line)
        lines.append(" " * 14 + "-" * width)
        lines.append(f"{'开始':>14} {'结束':>{width-6}}")
        widget.setPlainText("\n".join(lines))

    def _update_daily(self, r):
        daily = r.get('daily_pnl', [])
        self.daily_table.setRowCount(len(daily))
        for i, d in enumerate(daily):
            self.daily_table.setItem(i, 0, QTableWidgetItem(d['date']))
            self.daily_table.setItem(i, 1, QTableWidgetItem(f"{d['asset']:,.0f}"))
            pnl_item = QTableWidgetItem(f"{d['daily_pnl']:,.0f}")
            pnl_item.setForeground(QColor(ACCENT_RED if d['daily_pnl'] >= 0 else ACCENT_GREEN))
            self.daily_table.setItem(i, 2, pnl_item)
            cum = d['asset'] - r['initial_cash']
            cum_item = QTableWidgetItem(f"{cum:,.0f}")
            cum_item.setForeground(QColor(ACCENT_RED if cum >= 0 else ACCENT_GREEN))
            self.daily_table.setItem(i, 3, cum_item)
            self.daily_table.setItem(i, 4, QTableWidgetItem(f"{d['pnl_pct']:.2f}"))

    def _update_trades(self, r):
        trades = r.get('trades', [])
        self.trades_table.setRowCount(len(trades))
        for i, t in enumerate(trades):
            self.trades_table.setItem(i, 0, QTableWidgetItem(str(t.get('filled_date', t.get('date', '')))))
            self.trades_table.setItem(i, 1, QTableWidgetItem(str(t.get('code', r['code']))))
            side = t.get('side', t.get('direction', ''))
            direction_cn = '买入' if side == 'buy' else ('卖出' if side == 'sell' else side)
            self.trades_table.setItem(i, 2, QTableWidgetItem(direction_cn))
            price = t.get('filled_price', t.get('price', 0))
            self.trades_table.setItem(i, 3, QTableWidgetItem(f"{price:.2f}"))
            qty = t.get('filled_quantity', t.get('quantity', t.get('qty', 0)))
            self.trades_table.setItem(i, 4, QTableWidgetItem(str(qty)))
            amount = t.get('total_cost', price * qty)
            self.trades_table.setItem(i, 5, QTableWidgetItem(f"{amount:,.0f}"))
            pnl = t.get('pnl', 0)
            pnl_item = QTableWidgetItem(f"{pnl:,.0f}" if pnl else '-')
            if pnl > 0:
                pnl_item.setForeground(QColor(ACCENT_RED))
            elif pnl < 0:
                pnl_item.setForeground(QColor(ACCENT_GREEN))
            self.trades_table.setItem(i, 6, pnl_item)

    def _update_kline(self, r):
        """更新K线回测图（真实K线图 + 买卖点标记）"""
        kline = r.get('kline', {})
        trades = r.get('trades', [])
        if not kline or not hasattr(self, 'kline_widget'):
            return

        # 构建买卖点列表
        trade_points = []
        for t in trades:
            d = str(t.get('filled_date', t.get('date', '')))
            side = t.get('side', t.get('direction', ''))
            price = t.get('filled_price', t.get('price', 0))
            pnl = t.get('pnl', 0)
            trade_points.append({
                'date': d,
                'type': 'buy' if side == 'buy' else 'sell',
                'price': price,
                'pnl': pnl,
            })

        # 传入K线数据和买卖点
        self.kline_widget.set_data(kline, trade_points)
        self._append_log(f"K线回测图已生成: {len(kline.get('close',[]))}根K线, {len(trade_points)}个买卖点")

        # 同时加载到标注编辑器
        if hasattr(self, 'kline_editor') and kline:
            code = self.code_input.text().strip()
            name = code
            try:
                from market.stock_info import get_stock_name
                stock_name = get_stock_name(code)
                if stock_name:
                    name = stock_name
            except:
                pass
            self.kline_editor.load_kline(kline, code, name)
            # 自动导入回测买卖点到标注编辑器
            for tp in trade_points:
                if tp['type'] == 'buy':
                    self.kline_editor.annotation_manager.add_buy_point(
                        tp['date'], tp['price'], '回测生成'
                    )
                else:
                    self.kline_editor.annotation_manager.add_sell_point(
                        tp['date'], tp['price'], '回测生成'
                    )
            self.kline_editor._sync_points()
            self.kline_editor._update_status()

        # 同时加载到主力行为选股面板
        if hasattr(self, 'force_behavior_panel') and kline:
            code = self.code_input.text().strip()
            name = code
            try:
                from market.stock_info import get_stock_name
                stock_name = get_stock_name(code)
                if stock_name:
                    name = stock_name
            except:
                pass
            # 使用策略引擎独立分析K线
            try:
                from strategy.main_force_behavior import analyze_kline
                result = analyze_kline(kline, name=name, code=code)
                if result and 'error' not in result:
                    self._append_log(f"主力行为分析完成: 匹配{result.get('matched_count',0)}个模型, 评分{result.get('score',{}).get('total',0):.1f}分")
                else:
                    self._append_log(f"主力行为分析: {result.get('error', '分析完成')}")
            except Exception as e:
                self._append_log(f"主力行为分析失败: {e}")

    def _on_trade_double_clicked(self, row, col):
        """双击成交记录打开K线详情图"""
        if col != 1:  # 只响应代码列
            return
        if not self.report:
            QMessageBox.information(self, '提示', '请先运行回测')
            return
        code_item = self.trades_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text()
        kline = self.report.get('kline', {})
        trades = self.report.get('trades', [])
        if not kline:
            QMessageBox.information(self, '提示', '没有K线数据')
            return

        # 打开K线详情对话框
        dlg = QDialog(self)
        dlg.setWindowTitle(f'🕯 K线详情 - {code} (买卖点标记)')
        dlg.setMinimumSize(1000, 650)
        dlg.setStyleSheet(f'background: {DARK_BG}; color: {TEXT_PRIMARY};')
        layout = QVBoxLayout(dlg)

        from ui.backtest_kline_echarts import BacktestKlineECharts
        kline_widget = BacktestKlineECharts()

        # 构建所有买卖点
        trade_points = []
        for t in trades:
            d = str(t.get('filled_date', t.get('date', '')))
            side = t.get('side', t.get('direction', ''))
            price = t.get('filled_price', t.get('price', 0))
            pnl = t.get('pnl', 0)
            trade_points.append({
                'date': d, 'type': 'buy' if side == 'buy' else 'sell',
                'price': price, 'pnl': pnl,
            })
        kline_widget.set_data(kline, trade_points)
        layout.addWidget(kline_widget)

        # 交易信息
        info = QLabel(f'股票: {code} | K线: {len(kline.get("close",[]))}根 | 买卖点: {len(trade_points)}个 | '
                     f'双击成交记录代码列可打开此详情')
        info.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px; padding: 4px;')
        layout.addWidget(info)

        btn_close = QPushButton('关闭')
        btn_close.setStyleSheet(self._btn_style(ACCENT_BLUE))
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)

        dlg.exec()

    def _append_log(self, text):
        ts = datetime.now().strftime('%H:%M:%S')
        self.console.append(f"[{ts}] {text}")

    # ---------- 样式 ----------
    def _group_style(self):
        return f'''
            QGroupBox {{ color: {TEXT_PRIMARY}; font-weight: bold;
                border: 1px solid {DARK_BORDER}; border-radius: 6px;
                margin-top: 10px; padding-top: 8px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
        '''

    def _input_style(self):
        return f'''
            QLineEdit, QDateEdit, QDoubleSpinBox, QSpinBox {{
                background: {DARK_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                padding: 4px 6px; font-size: 12px;
                min-height: 20px; }}
            QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
                border: 1px solid {ACCENT_BLUE}; }}
            QDateEdit::drop-down {{ width: 20px; }}
            QCalendarWidget QWidget {{
                background-color: {DARK_CARD}; color: {TEXT_PRIMARY}; }}
            QCalendarWidget QToolButton {{
                background: {DARK_BG}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 3px;
                padding: 2px 8px; font-size: 11px; }}
            QCalendarWidget QToolButton:hover {{
                background: {DARK_BORDER}; }}
            QCalendarWidget QMenu {{
                background: {DARK_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; }}
            QCalendarWidget QMenu::item:selected {{
                background: {ACCENT_BLUE}; }}
            QCalendarWidget QSpinBox {{
                background: {DARK_BG}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 3px;
                padding: 1px; font-size: 11px; }}
            QCalendarWidget QAbstractItemView:enabled {{
                background: {DARK_BG}; color: {TEXT_PRIMARY};
                selection-background-color: {ACCENT_BLUE};
                selection-color: white;
                outline: none; }}
            QCalendarWidget QAbstractItemView:disabled {{
                color: {TEXT_SECONDARY}; }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: {DARK_CARD}; }}
            QCalendarWidget QLabel {{
                color: {TEXT_SECONDARY}; font-size: 11px; }}
        '''

    def _combo_style(self):
        return f'''
            QComboBox {{ background: {DARK_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                padding: 4px 6px; font-size: 12px; }}
            QComboBox QAbstractItemView {{ background: {DARK_CARD}; color: {TEXT_PRIMARY};
                selection-background-color: {ACCENT_BLUE}; }}
        '''

    def _btn_style(self, color):
        return f'''
            QPushButton {{ background: {color}; color: white; border: none;
                border-radius: 4px; padding: 7px 8px; font-size: 11px; font-weight: bold; }}
            QPushButton:disabled {{ background: {DARK_BORDER}; color: {TEXT_SECONDARY}; }}
        '''

    def _table_style(self):
        return f'''
            QTableWidget {{ background: {DARK_BG}; color: {TEXT_PRIMARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                gridline-color: {DARK_BORDER}; font-size: 12px; }}
            QHeaderView::section {{ background: {DARK_CARD}; color: {TEXT_SECONDARY};
                border: 1px solid {DARK_BORDER}; padding: 6px; font-weight: bold; }}
            QTableWidget::item:selected {{ background: {ACCENT_BLUE}; }}
        '''

    def _chart_style(self):
        return f'''
            QTextEdit {{ background: {DARK_BG}; color: {TEXT_SECONDARY};
                border: 1px solid {DARK_BORDER}; border-radius: 4px;
                font-family: Consolas, monospace; font-size: 10px; }}
        '''
