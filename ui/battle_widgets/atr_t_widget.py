# -*- coding: utf-8 -*-
"""
ATR做T助手（仅保留「我的持仓」）
================================================================
V3.0 保留：多因子共振（空间+动能+结构）+ 风控一票否决
V3.1 保留：题材强度动态k参数 + 执行价锚定（9:35锚定 + 30分钟桶 + 阈值紧急刷新）
V4.0 保留：DuckDB持久化 data/cache/atr_t_tracking.duckdb（holding 表）
- 执行价：锚定VWAP + 30分钟桶 + 阈值紧急刷新，高亮，触发声音
- 已删除「临时观察」「机会发现」两个 Tab，仅保留「我的持仓」
"""
import io
import os
import time
import numpy as np
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QLabel, QWidget,
    QTableWidgetItem, QMessageBox,
    QPushButton, QButtonGroup, QVBoxLayout, QHBoxLayout, QFileDialog,
    QHeaderView, QCheckBox, QDialog, QLineEdit, QFormLayout, QTableWidget,
    QInputDialog, QMenu,
)
from PyQt6.QtGui import QColor, QBrush, QFontMetrics

from .base import (
    fetch_ctrl_cached,
    BattleModuleBase, make_table, set_table_item,
    pct_color, BC, L, CTRL_COL_TITLE, fetch_ctrl_for,
)

# ============================================================
# 持仓表列（10列：删除成本/数量，新增涨跌幅）
# ============================================================
COL_H_NAME, COL_H_CODE, COL_H_PRICE, COL_H_PCT, \
    COL_H_BUY, COL_H_SELL, COL_H_MOM, COL_H_RISK, COL_H_SIG, \
    COL_H_ACT, COL_H_CTRL = range(11)
# 表头刻意用短名：本表在半屏里只有 ~820px 宽，而样式表每格左右要吃掉 16px 内边距
# （QTableWidget::item{padding:4px 8px}）。6 字表头 × 11 列的宽度会直接挤掉「操作建议」，
# 所以 股票名称→名称、做T买点→买点、做T卖点→卖点（面板本身就叫「分时做T」，前缀冗余）。
# 全称悬停可看（见 AtrTWidget 里给表头挂的 tooltip），不要为了改名去动这一行以外的地方。
HEADER_HOLD = ['名称', '代码', '现价', '涨跌幅',
               '买点', '卖点', '动能信号', '风控状态',
               '信号灯', '操作建议', CTRL_COL_TITLE]

# 机构级分时做T引擎（2026-10-12 接入，实现在 strategy/intraday_t_engine.py）：
# True  = 引擎结论覆盖「信号灯 / 操作建议 / 买卖点」（成本偏离+VWAP+量价+时段+反T优先）
# False = 只写 t_plan / t_score / cost_dev_pct 等字段，保留原判定（一键回退，不改代码）
_T_ENGINE_AUTHORITATIVE = True

# ============================================================
# 日K建仓表列（13列）
# 顺序：股票名称 代码 现价 涨跌幅 建仓价 止盈价 题材 模式 触发条件 控盘 观察 环境分 基准日
# 「观察」（2026-10-11 新增，用户选的 B）：把原本只写进 note 的因子文案拆成可见标签，
# 词表来自 services.control_profile（与「控盘选股」页共用一份），
# 覆盖五阶段：建仓(堆量/红肥绿瘦)·试盘·洗盘(洗盘收复/地量)·拉升(形态/缩量上涨)·
# 出货(破位警示/天量/出货形态) + 观察规则 C4/C6。风险类单独上色，悬停看完整 note。
COL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, COL_D_TRIG_PRICE, \
    COL_D_TAKE_PROFIT, COL_D_THEME, COL_D_PATTERN, COL_D_TRIGGER, \
    COL_D_CTRL, COL_D_OBS, COL_D_ENV, COL_D_BASE_DATE = range(13)
HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅', '建仓价', '止盈价',
                '题材', '模式', '触发条件', '控盘', '观察', '环境分', '基准日']
# 0 = 该列不固定，改为 Stretch（吃掉剩余宽度）。题材列放 0。
# 「观察」给 200：最多四个标签（如「堆量·试盘·拉升:阶梯式上行·C6」）也放得下。
DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 74, 200, 52, 92]

# 日K建仓显示精简：去掉"模式一/二/三/四"字样（字数过多）
_PATTERN_SHORT = {
    # V8：原「模式一 跳空高开」与「模式二 大阳整理」已合并为「激进」（pattern_id=1）
    '激进': '激进',
    # V7：原「模式三 底部横盘」与「模式四 周K确认」已合并为「横盘周K」（pattern_id=3）
    '横盘周K': '横盘周K',
    # 合并前写入 DB 的旧记录，保留以便正常显示
    '跳空回踩': '跳空回踩',
    '大阳整理': '大阳整理',
    '底部横盘': '底部横盘',
    '周K确认': '周K确认',
}
_TRIGGER_SHORT = {
    # V7 合并后的模式三（横盘周K）；V9（2026-09-27）第三关由「周K已突破上沿」
    # 改为「现价结构位落在 70~98% 的近上沿区间」，语义从"追突破"变成"启动前"，文案同步
    '横盘周K·建仓': '周K建仓',
    # V8 合并后的模式一（激进）
    '激进·建仓触发': '激进建仓',
    # 合并前的模式一 / 模式二
    '精准建仓触发': '精准建仓',
    '等待MA5回踩': '等五踩',
    '缺口保护中': '缺口保护',
    # 合并前写入 DB 的旧记录，保留以便正常显示
    '模式四确认·建仓触发': '周K建仓',
    '周K确认·建仓触发': '周K建仓',
    '建仓试错触发': '试错',
    '等回踩至结构位置70%': '回踩70%',
    '等最近3日1.3倍放量': '等3日放量',
    '等量价确认': '等量价',
    '横盘中等放量阳': '等放量阳',
}

# 信号灯背景/前景色
# [CYB-GATE] 创业板是 20cm 板，主板是 10cm 板，涨停幅度比 = 2.0。
# 下面这些「个股当日涨跌幅」阈值原按主板写死，创业板必须等比放大，
# 否则一只 +9% 的创业板股票（离涨停还有 11%）会被误判成「涨停锁仓、不做T」。
CYB_PREFIXES = ('300', '301')
PCT_LOCK_MAIN = 8.0        # 涨停锁仓（涨停的 80%：主板 10% → 8%）
PCT_LOCK_CYB = 16.0        # 涨停锁仓（涨停的 80%：创业板 20% → 16%）
PCT_MAINUP_MAIN = 5.0      # 主升浪（涨停的 50%：主板 10% → 5%）
PCT_MAINUP_CYB = 10.0      # 主升浪（涨停的 50%：创业板 20% → 10%）
PCT_WEAK_MAIN = -5.0       # 弱势降分
PCT_WEAK_CYB = -10.0       # 弱势降分（创业板）


def _is_cyb(code) -> bool:
    """是否创业板（20cm 板）"""
    return str(code or '').startswith(CYB_PREFIXES)


def _pct_thresholds(code):
    """按板性返回 (涨停锁仓线, 主升浪线, 弱势降分线)"""
    if _is_cyb(code):
        return PCT_LOCK_CYB, PCT_MAINUP_CYB, PCT_WEAK_CYB
    return PCT_LOCK_MAIN, PCT_MAINUP_MAIN, PCT_WEAK_MAIN


SIGNAL_BG = {
    'green':  '#E8F5E9',
    'yellow': '#FFF8E1',
    'red':    '#FFEBEE',
    'gray':   '#F5F5F5',
    'orange': '#FFF3E0',
}
SIGNAL_FG = {
    'green':  '#2E7D32',
    'yellow': '#F57F17',
    'red':    '#C62828',
    'gray':   '#757575',
    'orange': '#E65100',
}

# 触发行闪烁色（买点绿/卖点红）
FLASH_BG_BUY = QColor('#C8E6C9')   # 浅绿
FLASH_BG_SELL = QColor('#FFCDD2')  # 浅红


# ============================================================
# 纯函数：技术指标计算（保留 V3.0 全部逻辑）
# ============================================================
def _ema(arr, period):
    if len(arr) == 0:
        return np.array([])
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def calc_macd(closes, fast=8, slow=21, signal=5):
    closes = np.asarray(closes, dtype=float)
    if len(closes) < slow + signal:
        return np.array([]), np.array([]), np.array([])
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif = ema_fast - ema_slow
    dea = _ema(dif, signal)
    hist = (dif - dea) * 2.0
    return dif, dea, hist


def detect_cross(dif, dea):
    if len(dif) < 3:
        return None
    d_prev, d_curr = dif[-2], dif[-1]
    e_prev, e_curr = dea[-2], dea[-1]
    golden = (d_prev <= e_prev) and (d_curr > e_curr)
    dead = (d_prev >= e_prev) and (d_curr < e_curr)
    if golden:
        return 'golden_below_zero' if d_curr < 0 else 'golden'
    if dead:
        return 'dead_above_zero' if d_curr > 0 else 'dead'
    return None


def calc_td(bars_close):
    n = len(bars_close)
    if n < 5:
        return dict(count=0, direction=None, level=0,
                    is_low9=False, is_high9=False, is_low78=False, is_high78=False)
    count = 0
    direction = None
    for i in range(n - 1, 3, -1):
        if bars_close[i] < bars_close[i - 4]:
            if direction is None:
                direction = 'down'
            if direction == 'down':
                count += 1
            else:
                break
        elif bars_close[i] > bars_close[i - 4]:
            if direction is None:
                direction = 'up'
            if direction == 'up':
                count += 1
            else:
                break
        else:
            break
    is_low9 = direction == 'down' and count >= 9
    is_high9 = direction == 'up' and count >= 9
    is_low78 = direction == 'down' and count in (7, 8)
    is_high78 = direction == 'up' and count in (7, 8)
    return dict(count=count, direction=direction, level=count,
                is_low9=is_low9, is_high9=is_high9,
                is_low78=is_low78, is_high78=is_high78)


def check_divergence(closes, difs, lookback=20):
    n = min(len(closes), lookback)
    if n < 10:
        return None
    c = closes[-n:]
    d = difs[-n:]

    def _is_low(idx):
        return 0 < idx < n - 1 and c[idx] < c[idx - 1] and c[idx] < c[idx + 1]
    def _is_high(idx):
        return 0 < idx < n - 1 and c[idx] > c[idx - 1] and c[idx] > c[idx + 1]

    lows = [i for i in range(1, n - 1) if _is_low(i)]
    highs = [i for i in range(1, n - 1) if _is_high(i)]

    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if c[i2] < c[i1] and d[i2] > d[i1]:
            if n - 1 - i2 <= 3:
                return 'bottom'
            return 'bottom_emerging'
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if c[i2] > c[i1] and d[i2] < d[i1]:
            if n - 1 - i2 <= 3:
                return 'top'
            return 'top_emerging'
    return None


def support_resistance(bars_low, bars_high, n=20):
    if len(bars_low) < n:
        n = len(bars_low)
    if n == 0:
        return 0.0, 0.0
    return float(np.min(bars_low[-n:])), float(np.max(bars_high[-n:]))


# ============================================================
# 主Widget
# ============================================================
class AtrTWidget(BattleModuleBase):
    # 点击表格"股票名称"单元格 -> 通知主窗口跳转个股分析(code, name)
    stock_clicked = pyqtSignal(str, str)
    """ATR做T助手 V4.0：三Tab闭环 + DuckDB持久化"""

    def __init__(self, parent=None):
        super().__init__('🎯 分时做T', parent)
        self._watch_list = []          # 旧字段保留（兼容）
        self._lock_state = {}
        self._global_warn = False
        self._db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            'data', 'cache', 'kline_cache.duckdb',
        )
        self._kline_cache = {}
        self._theme_cache = {}
        self._anchor_state = {}

        # ===== V4.0 DuckDB 持久化 =====
        self._track_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            'data', 'cache', 'atr_t_tracking.duckdb',
        )
        self._init_tracking_db()

        # 内存缓存（从DB加载）
        self._holding_db_rows = []     # [{code,name,cost,qty,buy_time,...}]
        self._refresh_holding_db()

        # 渲染缓存
        self._hold_rows = []           # 当前持仓表行
        self._flash_codes = {}        # code -> 'buy'/'sell'
        self._flash_on = False

        self._build_content()
        QTimer.singleShot(300, self.refresh)
        # 持仓 5秒
        self.start_refresh(5000)
        # 闪烁 timer 600ms
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._toggle_flash)
        self._flash_timer.start(600)

        self._first_loaded = False
        self._last_source_codes = set()   # 盘后轻量刷新：上次已渲染的持仓 code 集合

    # ============================================================
    # DuckDB 持久化
    # ============================================================
    def _init_tracking_db(self):
        """建表（IF NOT EXISTS）"""
        try:
            import duckdb
            con = duckdb.connect(self._track_db_path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS holding(
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    cost DOUBLE,
                    qty INTEGER,
                    buy_time TIMESTAMP,
                    exec_buy DOUBLE,
                    exec_sell DOUBLE,
                    anchor_vwap DOUBLE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.close()
        except Exception as e:
            print(f'[ATR做T] 初始化tracking db失败: {e}', flush=True)

    def _db_query(self, sql, params=None):
        """短连接查询，返回 list[tuple]"""
        import duckdb
        con = duckdb.connect(self._track_db_path)
        try:
            if params:
                rows = con.execute(sql, params).fetchall()
            else:
                rows = con.execute(sql).fetchall()
            return rows
        finally:
            con.close()

    def _refresh_holding_db(self):
        try:
            rows = self._db_query(
                'SELECT code, name, cost, qty, buy_time, exec_buy, exec_sell, anchor_vwap FROM holding'
            )
            self._holding_db_rows = [
                dict(code=r[0], name=r[1], cost=r[2], qty=r[3],
                     buy_time=r[4], exec_buy=r[5], exec_sell=r[6],
                     anchor_vwap=r[7])
                for r in rows
            ]
        except Exception as e:
            print(f'[ATR做T] 读holding失败: {e}', flush=True)
            self._holding_db_rows = []

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_content(self):
        # ---- 标题栏右侧添加 Tab 切换按钮（分时做T / 日K建仓）----
        self._setup_tab_buttons()

        # ===== Tab1 容器：分时做T（持仓表）=====
        self._hold_widget = QWidget()
        hold_layout = QVBoxLayout(self._hold_widget)
        hold_layout.setContentsMargins(0, 0, 0, 0)
        hold_layout.setSpacing(0)
        # 顶部全局警告横幅（保留）
        self.warn_banner = QFrame()
        self.warn_banner.setStyleSheet(
            'background:#FFF3CD;color:#856404;border:1px solid #FFC107;border-radius:4px;')
        self.warn_banner.setFixedHeight(28)
        warn_label = QLabel('⚠️ 大盘情绪退潮，做T成功率降低，建议降低仓位或停止做T',
                            self.warn_banner)
        warn_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warn_label.setStyleSheet('color:#856404;font-size:11px;font-weight:bold;')
        self.warn_banner.setVisible(False)
        hold_layout.addWidget(self.warn_banner)

        # ---- 持仓表（仅保留「我的持仓」，已删除「临时观察」「机会发现」Tab）----
        self.table = make_table(11, HEADER_HOLD)
        # 表头用了短名（省宽度），悬停给出全称
        for _hc, _full in ((COL_H_NAME, '股票名称'), (COL_H_BUY, '做T买点'),
                           (COL_H_SELL, '做T卖点')):
            _hi = self.table.horizontalHeaderItem(_hc)
            if _hi is not None:
                _hi.setToolTip(_full)
        # 列宽按「最长文案」给量：风控状态/信号灯要放下「非交易时段」「🔴 放量下跌」，
        # 涨跌幅要放下「+10.05%」，动能要放下「顶背离/TD..」；
        # 操作建议仍是 Stretch（吃剩余宽度），窗口变窄不会挤掉前面的短列。
        # 列宽不写死：创建时给最小可用宽，每次渲染由 _fit_hold_columns() 按
        # 「表头 + 实际文字」的像素宽度收紧/放宽（上下限见 _HOLD_MINW / _HOLD_MAXW），
        # 剩余宽度全部交给「操作建议」列（它是 Stretch）。
        for _i, _w in enumerate(self._HOLD_MINW.get(i, 60)
                               for i in range(11) if i != COL_H_ACT):
            self.table.setColumnWidth(_i, _w)
        # 「控盘」列插到末尾后，不能让末列自动拉伸（会把它撑开），
        # 改成「操作建议」列吃剩余宽度
        _hh = self.table.horizontalHeader()
        _hh.setStretchLastSection(False)
        _hh.setSectionResizeMode(COL_H_ACT, QHeaderView.ResizeMode.Stretch)
        hold_layout.addWidget(self.table, 1)
        # 仅点击"股票名称"列跳转个股分析，其他列不跳转
        self.table.cellClicked.connect(self._on_hold_cell_clicked)
        # 右键菜单：补成本/数量、从做T列表移除、刷新。
        # （原来的「➕ 添加个股」按钮已按用户要求删除，功能移到右键，标题栏不再堆按钮）
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_hold_context_menu)
        self.content_layout.addWidget(self._hold_widget, 1)

        # ===== Tab2 容器：日K建仓表 =====
        self._daily_widget = QWidget()
        daily_layout = QVBoxLayout(self._daily_widget)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        daily_layout.setSpacing(0)
        self.daily_table = make_table(13, HEADER_DAILY)
        for i, w in enumerate(DAILY_WIDTHS):
            if w:
                self.daily_table.setColumnWidth(i, w)
        # 列宽策略：其余列固定窄宽，「题材」列吃掉剩余空间 → 整表刚好一屏、不横向滚动，
        # 「基准日」这类固定列因此能完整显示，不会被挤出可视区。
        _dh = self.daily_table.horizontalHeader()
        _dh.setStretchLastSection(False)
        _dh.setSectionResizeMode(COL_D_THEME, QHeaderView.ResizeMode.Stretch)  # 题材列吃剩余宽度
        # 环境分阀门：按当日市场/行业温度过滤，只保留"可建仓"档
        _filter_bar = QWidget()
        _fbl = QHBoxLayout(_filter_bar)
        _fbl.setContentsMargins(4, 2, 4, 2)
        _fbl.setSpacing(8)
        self._chk_env = QCheckBox('只看环境分\u22653（可建仓）')
        self._chk_env.setStyleSheet('color:#444;font-size:11px;')
        self._chk_env.setToolTip(
            '环境分按当日大盘/行业温度计算：\n'
            '  \u22656  正常建仓\n'
            '  3~5  谨慎（半仓）\n'
            '  \u22642  不建议建仓')
        self._chk_env.stateChanged.connect(self._on_env_filter_changed)
        _fbl.addWidget(self._chk_env)
        self._env_hint = QLabel('')
        self._env_hint.setStyleSheet('color:#888;font-size:11px;')
        _fbl.addWidget(self._env_hint)
        _fbl.addStretch(1)
        daily_layout.addWidget(_filter_bar)
        daily_layout.addWidget(self.daily_table, 1)
        # 仅点击"股票名称"列跳转个股分析，其他列不跳转
        self.daily_table.cellClicked.connect(self._on_daily_cell_clicked)
        self.content_layout.addWidget(self._daily_widget, 0)

        # 默认显示「分时做T」，隐藏「日K建仓」
        self._daily_widget.setVisible(False)

        # 日K建仓模块初始化（状态/缓存/定时器/DB）
        self._init_daily_module()


    # ============================================================
    # 点击股票名称 -> 跳转个股分析
    # ============================================================
    def _on_hold_cell_clicked(self, row, col):
        """分时做T：仅点击"股票名称"单元格跳转，其他列不跳转"""
        if col != COL_H_NAME:
            return
        it = self.table.item(row, COL_H_CODE)
        code = it.text() if it else ''
        nit = self.table.item(row, COL_H_NAME)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    def _on_daily_cell_clicked(self, row, col):
        """日K建仓：仅点击"股票名称"单元格跳转，其他列不跳转"""
        if col != COL_D_NAME:
            return
        it = self.daily_table.item(row, COL_D_CODE)
        code = it.text() if it else ''
        nit = self.daily_table.item(row, COL_D_NAME)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    # ============================================================
    # 刷新调度
    # ============================================================
    def refresh(self):
        """5秒：持仓"""
        now = datetime.now()
        h, m = now.hour, now.minute
        weekday = now.weekday()
        is_trade_time = True
        if weekday >= 5:
            is_trade_time = False
        elif not (((h == 9 and m >= 30) or h == 10 or (h == 11 and m <= 30)
                   or h == 13 or h == 14) and h < 15):
            is_trade_time = False
        if not is_trade_time and self._first_loaded:
            # 盘后/休市：行情不再变动，跳过网络拉取；
            # 但 自选/持仓/观察 成员变化时仍须重读本地来源刷新，
            # 否则加/删自选要重启程序才能生效
            if self._source_codes() == self._last_source_codes:
                self.set_status('盘后复盘')
                return
        self.set_status('计算中...')
        self.run_async(self._fetch_and_calc, self._on_hold_loaded, self._on_hold_failed)

    def _source_codes(self):
        """本地轻量重读：持仓来源 的 code 集合（不拉行情）。
        盘后 5 秒 tick 用它判断列表成员是否变化，成员变了才触发全量刷新。"""
        codes = set()
        try:
            for hd in self._get_holdings_source():
                codes.add(hd['code'])
        except Exception as e:
            print(f'[ATR做T] 重读持仓来源失败: {e}', flush=True)
        return codes

    # ============================================================
    # 持仓+观察 数据获取与计算（后台线程）
    # ============================================================
    def _load_bars(self, code, n=80):
        cached = self._kline_cache.get(code)
        if cached and time.time() - cached[1] < 60:
            return cached[0]
        bars = []
        try:
            from utils.kline_provider import _get_kline_from_duckdb
            bars = _get_kline_from_duckdb(code, count=n) or []
        except Exception as e:
            print(f'[ATR做T] duckdb读取失败 {code}: {e}', flush=True)
            bars = []
        if len(bars) < 30:
            try:
                from utils.kline_provider import get_daily_kline
                kd = get_daily_kline(code, count=n) or {}
                dates = kd.get('dates') or []
                opens = kd.get('open') or []
                highs = kd.get('high') or []
                lows = kd.get('low') or []
                closes = kd.get('close') or []
                vols = kd.get('volume') or []
                if len(closes) >= 30:
                    bars = [dict(
                        date=str(dates[i]) if i < len(dates) else '',
                        open=float(opens[i]) if i < len(opens) else float(closes[i]),
                        high=float(highs[i]) if i < len(highs) else float(closes[i]),
                        low=float(lows[i]) if i < len(lows) else float(closes[i]),
                        close=float(closes[i]),
                        volume=float(vols[i]) if i < len(vols) else 0.0,
                    ) for i in range(len(closes))]
            except Exception as e:
                print(f'[ATR做T] HTTP兜底失败 {code}: {e}', flush=True)
        if len(bars) >= 30:
            self._kline_cache[code] = (bars, time.time())
        return bars

    def _get_holdings_source(self):
        """持仓来源：DB holding 表优先；空则 fallback watchlist（兼容老用户）"""
        self._refresh_holding_db()
        if self._holding_db_rows:
            return [dict(code=r['code'], name=r['name'],
                         cost=r['cost'], qty=r['qty'],
                         buy_time=r['buy_time'], from_db=True)
                    for r in self._holding_db_rows]
        # fallback: watchlist
        try:
            from core.watchlist import get_watchlist_manager
            mgr = get_watchlist_manager()
            self._watch_list = list(mgr.stocks)  # 无上限：持仓表为空时自选全部纳入，不再截断20只
        except Exception:
            self._watch_list = []
        return [dict(code=s['code'], name=s['name'],
                     cost=None, qty=None, buy_time=None, from_db=False)
                for s in self._watch_list]

    def _calc_one_stock(self, code, name, price=None, prev_close=None,
                        day_high=None, day_low=None, bars=None,
                        force_exec=True):
        """计算单只股票的做T指标。
        force_exec=True：使用锚定执行价（持仓/观察）
        force_exec=False：使用实时参考价
        返回 dict 或 None
        """
        if bars is None:
            bars = self._load_bars(code, n=80)
        if len(bars) < 30:
            return None

        closes = np.array([b['close'] for b in bars], dtype=float)
        highs = np.array([b['high'] for b in bars], dtype=float)
        lows = np.array([b['low'] for b in bars], dtype=float)

        last_bar = bars[-1]
        if price is None or price <= 0:
            price = float(last_bar['close'])
        if prev_close is None or prev_close <= 0:
            prev_close = float(bars[-2]['close']) if len(bars) >= 2 else price
        if day_high is None or day_high <= 0:
            day_high = float(last_bar['high'])
        if day_low is None or day_low <= 0:
            day_low = float(last_bar['low'])

        if price <= 0 or prev_close <= 0:
            return None

        pct = (price - prev_close) / prev_close * 100.0
        atr = self._calc_atr(bars, period=14)
        if atr <= 0:
            atr = prev_close * 0.02
        vwap = (day_high + day_low + price) / 3.0
        if vwap <= 0:
            vwap = price

        f, theme_tag, theme_dir = self._compute_theme_strength(code, price=price, pct=pct)

        if force_exec:
            anchor = self._get_or_anchor(code, price, vwap, atr, f)
            if anchor is not None:
                buy_point = anchor['buy_point']
                sell_point = anchor['sell_point']
                k_buy_used = anchor['k_buy']
                k_sell_used = anchor['k_sell']
            else:
                k_buy_used = 0.3 - 0.1 * f
                k_sell_used = 0.3 + 0.1 * f
                buy_point = round(vwap - k_buy_used * atr, 2)
                sell_point = round(vwap + k_sell_used * atr, 2)
            anchor_vwap = vwap
        else:
            # 参考价：实时 VWAP ± 0.3*ATR（k=0.3 基础，可按 f 微调）
            k_buy_used = 0.3 - 0.1 * f
            k_sell_used = 0.3 + 0.1 * f
            buy_point = round(vwap - k_buy_used * atr, 2)
            sell_point = round(vwap + k_sell_used * atr, 2)
            anchor_vwap = vwap

        # MACD / TD / 背离 / 支撑压力
        dif, dea, hist = calc_macd(closes, 8, 21, 5)
        cross = detect_cross(dif, dea) if len(dif) else None
        td = calc_td(closes.tolist())
        div = check_divergence(closes, dif) if len(dif) else None
        sup, res = support_resistance(lows, highs, n=20)
        near_support = (sup > 0) and (price <= sup * 1.01) and (price >= sup * 0.99)
        near_resist = (res > 0) and (price >= res * 0.99) and (price <= res * 1.01)

        in_buy_radar = price <= buy_point * 1.005
        in_sell_radar = price >= sell_point * 0.995

        # 动能文本
        momentum_parts = []
        if cross == 'golden_below_zero':
            momentum_parts.append('MACD零轴下金叉')
        elif cross == 'dead_above_zero':
            momentum_parts.append('MACD零轴上死叉')
        elif cross == 'golden':
            momentum_parts.append('MACD金叉')
        elif cross == 'dead':
            momentum_parts.append('MACD死叉')
        if div == 'bottom':
            momentum_parts.append('日线底背离')
        elif div == 'top':
            momentum_parts.append('日线顶背离')
        elif div == 'bottom_emerging':
            momentum_parts.append('底背离雏形')
        elif div == 'top_emerging':
            momentum_parts.append('顶背离雏形')
        if td['is_low9']:
            momentum_parts.append('TD低9')
        elif td['is_high9']:
            momentum_parts.append('TD高9')
        elif td['is_low78']:
            momentum_parts.append(f"TD低{td['level']}预警")
        elif td['is_high78']:
            momentum_parts.append(f"TD高{td['level']}预警")
        if near_support:
            momentum_parts.append('触及日线支撑')
        elif near_resist:
            momentum_parts.append('触及日线压力')
        momentum_text = ' + '.join(momentum_parts) if momentum_parts else '暂无'

        struct_score = 0
        if near_support or near_resist:
            struct_score += 1
        if div in ('bottom', 'top'):
            struct_score += 1
        if td['is_low9'] or td['is_high9']:
            struct_score += 1

        return dict(
            code=code, name=name,
            price=round(price, 2), pct=round(pct, 2),
            buy_point=buy_point, sell_point=sell_point,
            momentum=momentum_text,
            vwap=round(vwap, 2), atr=round(atr, 2),
            f=round(f, 2), theme_tag=theme_tag, theme_dir=theme_dir,
            k_buy=round(k_buy_used, 2), k_sell=round(k_sell_used, 2),
            anchor_vwap=anchor_vwap,
            in_buy_radar=in_buy_radar, in_sell_radar=in_sell_radar,
            cross=cross, div=div, td=td, struct_score=struct_score,
            near_support=near_support, near_resist=near_resist,
        )

    def _apply_risk_and_signal(self, r, in_open_window):
        """对 _calc_one_stock 的结果应用风控+信号灯（持仓Tab用）。
        直接修改 r 并返回。"""
        price = r['price']
        vwap = r['vwap']
        pct = r['pct']
        in_buy_radar = r['in_buy_radar']
        in_sell_radar = r['in_sell_radar']
        cross = r['cross']
        div = r['div']
        td = r['td']
        struct_score = r['struct_score']
        theme_dir = r['theme_dir']
        f = r['f']
        buy_point = r['buy_point']
        sell_point = r['sell_point']

        # [CYB-GATE] 涨停锁仓线/主升浪线按板性：主板 8/5%，创业板 16/10%
        _lock_pct, _mainup_pct, _ = _pct_thresholds(r.get('code'))

        risk_status = '正常(VWAP上方)' if price >= vwap else '正常(VWAP下方)'
        risk_color = SIGNAL_FG['green'] if price >= vwap else SIGNAL_FG['yellow']
        signal_level = 'gray'
        signal_text = '⚪ 待机'
        signal_dir = None
        action = '观望'
        blocked = None
        dir_note = ''

        if price < vwap * 0.985:
            risk_status = '⛔ 趋弱单边下跌，暂停买入'
            risk_color = SIGNAL_FG['red']
            signal_level = 'red'
            signal_text = '🔴 防飞刀'
            action = '严禁买入，等VWAP收复'
            blocked = 'buy'
        elif pct >= _lock_pct:
            risk_status = '🚀 强势涨停锁仓，不做T'
            risk_color = SIGNAL_FG['red']
            signal_level = 'red'
            signal_text = '🔴 锁仓'
            action = '主升浪锁仓，放弃做T'
            blocked = 'sell'
        elif pct >= _mainup_pct and in_sell_radar:
            risk_status = '🔥 主升浪中，谨慎卖出'
            risk_color = SIGNAL_FG['orange']
            signal_level = 'orange'
            signal_text = '🟠 主升浪'
            action = '谨慎卖出防T飞'
            blocked = 'sell'
        else:
            if price >= vwap:
                risk_status = '正常(VWAP上方)'
                risk_color = SIGNAL_FG['green']
            else:
                risk_status = '正常(VWAP下方)'
                risk_color = SIGNAL_FG['yellow']

            red_buy = in_buy_radar and (cross == 'golden_below_zero') and struct_score >= 2
            red_sell = in_sell_radar and (cross == 'dead_above_zero') and struct_score >= 2

            if theme_dir == 'strong':
                if red_sell:
                    red_sell = False
                dir_note = '正T(低吸优先)'
            elif theme_dir == 'weak':
                if red_buy:
                    red_buy = False
                dir_note = '反T(高抛优先)'
            if f <= -0.6:
                blocked = 'buy'
                if '低吸' in action or '买入' in action:
                    action = '退潮期停低吸'
                dir_note = '退潮停低吸'

            yellow_buy = in_buy_radar and (
                div == 'bottom_emerging' or td['is_low78'] or td['is_low9']
            )
            yellow_sell = in_sell_radar and (
                div == 'top_emerging' or td['is_high78'] or td['is_high9']
            )
            if theme_dir == 'strong' and in_sell_radar and (
                cross == 'dead_above_zero' and struct_score >= 2
            ):
                yellow_sell = True
            if theme_dir == 'weak' and in_buy_radar and (
                cross == 'golden_below_zero' and struct_score >= 2
            ):
                yellow_buy = True
            green_buy = in_buy_radar
            green_sell = in_sell_radar

            lock = self._lock_state.get(r['code'])
            locked_buy = (lock and lock['dir'] == 'buy')
            locked_sell = (lock and lock['dir'] == 'sell')

            if red_buy and not locked_buy:
                signal_level = 'red'
                signal_text = '🔴 买入执行'
                signal_dir = 'buy'
                action = f"回踩买点 {buy_point}，可正T买入"
                self._lock_state[r['code']] = {'dir': 'buy', 'price': price}
                self._play_sound('buy', r['code'])
                # V3.0 推送：分时做T买入观察 -> 🎯【分时做T｜买入观察】(走统一总线, 只读真实ATR/VWAP, 不改算法)
                try:
                    from services.wechat_bus import get_wechat_bus
                    get_wechat_bus().send_t_timing(
                        event='买入观察', code=r['code'], name=r.get('name', ''),
                        price=price, vwap=vwap, atr=r.get('atr', 0), ref_price=buy_point,
                        cur_status=risk_status, reason=action,
                        risk=risk_status, action=action)
                except Exception:
                    pass
            elif red_sell and not locked_sell:
                signal_level = 'red'
                signal_text = '🔴 卖出执行'
                signal_dir = 'sell'
                action = f"冲高卖点 {sell_point}，可反T卖出"
                self._lock_state[r['code']] = {'dir': 'sell', 'price': price}
                self._play_sound('sell', r['code'])
                # V3.0 推送：分时做T卖出观察 -> 🎯【分时做T｜卖出观察】
                try:
                    from services.wechat_bus import get_wechat_bus
                    get_wechat_bus().send_t_timing(
                        event='卖出观察', code=r['code'], name=r.get('name', ''),
                        price=price, vwap=vwap, atr=r.get('atr', 0), ref_price=sell_point,
                        cur_status=risk_status, reason=action,
                        risk=risk_status, action=action)
                except Exception:
                    pass
            elif yellow_buy or yellow_sell:
                signal_level = 'yellow'
                signal_text = '🟡 准备'
                if yellow_buy:
                    signal_dir = 'buy'
                    action = '准备低吸(等金叉/低9确认)'
                else:
                    signal_dir = 'sell'
                    action = '准备高抛(等死叉/高9确认)'
            elif green_buy or green_sell:
                signal_level = 'green'
                signal_text = '🟢 观察'
                if green_buy:
                    signal_dir = 'buy'
                    action = '观察买点，等动能确认'
                else:
                    signal_dir = 'sell'
                    action = '观察卖点，等动能确认'
            else:
                signal_level = 'gray'
                signal_text = '⚪ 待机'
                signal_dir = None
                action = '观望'

            if locked_buy and price >= lock['price'] * 1.005:
                self._lock_state.pop(r['code'], None)
            elif locked_sell and price <= lock['price'] * 0.995:
                self._lock_state.pop(r['code'], None)

        if in_open_window and blocked is None:
            risk_status = '⏰ 开盘波动期(9:30-9:45)'
            risk_color = SIGNAL_FG['yellow']
            signal_level = 'yellow'
            signal_text = '🟡 暂停'
            action = '等9:45后再操作'

        if self._global_warn and ('低吸' in action or '买入' in action):
            action = '谨慎观望(大盘退潮)'

        r['risk_status'] = risk_status
        r['risk_color'] = risk_color
        r['signal_level'] = signal_level
        r['signal_text'] = signal_text
        r['signal_dir'] = signal_dir
        r['action'] = action
        r['dir_note'] = dir_note
        return r

    def _fetch_and_calc(self):
        """后台：持仓行"""
        holdings = self._get_holdings_source()
        self._check_market_sentiment()

        now = time.localtime()
        h, m = now.tm_hour, now.tm_min
        in_open_window = (h == 9 and 30 <= m <= 45)
        is_trading = ((h == 9 and m >= 30) or (10 <= h <= 11 and m <= 30)
                      or h == 13 or h == 14) and (h < 15)

        # 持仓 code 列表，批量拉行情
        all_items = []
        for hd in holdings:
            all_items.append(hd)

        if not all_items:
            return [], is_trading, in_open_window

        codes = [it['code'] for it in all_items]
        try:
            from utils.http_market_data import get_realtime_quotes_http
            quotes = get_realtime_quotes_http(codes) or {}
        except Exception as e:
            print(f'[ATR做T] 实时行情失败: {e}', flush=True)
            quotes = {}

        hold_rows = []

        for item in all_items:
            code = item['code']
            name = item['name']
            bars = self._load_bars(code, n=80)
            if len(bars) < 30:
                continue
            q = quotes.get(code, {}) or {}
            price = float(q.get('price', 0) or 0)
            prev_close = float(q.get('last_close', 0) or 0)
            day_high = float(q.get('high', 0) or 0)
            day_low = float(q.get('low', 0) or 0)

            r = self._calc_one_stock(
                code, name, price=price, prev_close=prev_close,
                day_high=day_high, day_low=day_low, bars=bars,
                force_exec=True,
            )
            if r is None:
                continue

            r['cost'] = item.get('cost')
            r['qty'] = item.get('qty')
            r['buy_time'] = item.get('buy_time')
            r = self._apply_risk_and_signal(r, in_open_window)
            # ===== 机构级分时做T引擎接入（务必在 _apply_risk_and_signal 之后：否则信号会被旧判定覆盖）=====
            try:
                from strategy.intraday_t_engine import (
                    THolding, TQuote, get_engine, apply_plan_to_row,
                )
                _t_plan = get_engine().evaluate(
                    holding=THolding(
                        code=code, name=name,
                        cost=item.get('cost'), qty=item.get('qty'),
                        buy_time=item.get('buy_time'),
                    ),
                    quote=TQuote(
                        price=price, prev_close=prev_close,
                        high=day_high, low=day_low,
                        volume_lots=q.get('volume', 0), amount=q.get('amount', 0),
                        vol_ratio=q.get('vol_ratio', 0), turnover=q.get('turnover', 0),
                    ),
                    now=datetime.now(), atr=r.get('atr'),
                    structure={
                        'near_support': r.get('near_support'),
                        'near_resist': r.get('near_resist'),
                        'cross': r.get('cross'),
                        'div': r.get('div'),
                        'td_low9': (r.get('td') or {}).get('is_low9'),
                        'td_high9': (r.get('td') or {}).get('is_high9'),
                    },
                    market={'weak': bool(getattr(self, '_global_warn', False))},
                )
                if _T_ENGINE_AUTHORITATIVE:
                    apply_plan_to_row(r, _t_plan)
                else:
                    _keep = {k: r.get(k) for k in (
                        'signal_level', 'signal_text', 'signal_dir',
                        'action', 'risk_status', 'buy_point', 'sell_point')}
                    apply_plan_to_row(r, _t_plan)
                    for _k, _v in _keep.items():
                        if _v is not None:
                            r[_k] = _v
                self._tengine_plans = getattr(self, '_tengine_plans', {})
                self._tengine_plans[code] = _t_plan
            except Exception as _e:
                # 刻意不静默：打印类型+原因+堆栈，避免「改了没变化」
                import traceback
                print('[intraday_t_engine] %s 评估失败: %s: %s' % (
                    code, type(_e).__name__, _e), flush=True)
                traceback.print_exc()
            # ===== 接入结束 =====
            hold_rows.append(r)

        return hold_rows, is_trading, in_open_window

    # ============================================================
    # UI 渲染（主线程）
    # ============================================================
    def _on_hold_loaded(self, result):
        hold_rows, is_trading, in_open_window = result
        self._first_loaded = True
        self._last_source_codes = self._source_codes()
        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）
        fetch_ctrl_for(hold_rows)
        self._hold_rows = hold_rows
        self.warn_banner.setVisible(self._global_warn)

        # 更新 flash_codes
        self._flash_codes = {}
        for r in hold_rows:
            if r.get('signal_dir') == 'buy' and r['signal_level'] in ('red', 'yellow'):
                self._flash_codes[r['code']] = 'buy'
            elif r.get('signal_dir') == 'sell' and r['signal_level'] in ('red', 'yellow'):
                self._flash_codes[r['code']] = 'sell'

        if is_trading:
            tag = '盘中监控'
            if in_open_window:
                tag = '开盘波动期'
        else:
            tag = '盘后复盘'
        self.title_label.setText(f'🎯 分时做T ({tag}) · 持仓{len(hold_rows)}')

        self._render_hold_table()
        self.set_update_time()

    def _on_hold_failed(self, err):
        self.set_status('持仓数据获取失败')

    def _render_hold_table(self):
        fetch_ctrl_cached(self._hold_rows)
        rows = self._hold_rows
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        for i, r in enumerate(rows):
            # 触发行背景闪烁
            flash_dir = self._flash_codes.get(r['code'])
            row_bg = None
            if flash_dir and self._flash_on:
                row_bg = FLASH_BG_BUY if flash_dir == 'buy' else FLASH_BG_SELL

            # 名称
            item_name = set_table_item(self.table, i, COL_H_NAME, r['name'],
                                       BC.TEXT_PRIMARY, bold=True, align=left)
            set_table_item(self.table, i, COL_H_CODE, r['code'], '#000000', bold=True, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, i, COL_H_PRICE, f"{r['price']:.2f}",
                           '#000000', bold=True, align=right)
            # 涨跌幅
            set_table_item(self.table, i, COL_H_PCT,
                           f"{r['pct']:+.2f}%", pct_color(r['pct']), bold=True, align=right)
            # 买/卖点（执行价，高亮）
            set_table_item(self.table, i, COL_H_BUY, f"{r['buy_point']:.2f}",
                           '#000000', bold=True, align=right)
            set_table_item(self.table, i, COL_H_SELL, f"{r['sell_point']:.2f}",
                           '#000000', bold=True, align=right)
            # 动能（精简：只留短词，无信号显示--）
            mom = r['momentum'] or ''
            mom_short = self._short_momentum(mom)
            mom_color = '#e65100' if ('顶背离' in mom_short or 'TD' in mom_short or '金叉' in mom_short or '死叉' in mom_short) else '#607d8b'
            _mit = set_table_item(self.table, i, COL_H_MOM, mom_short, mom_color, align=left)
            _mit.setToolTip(mom or mom_short)
            # 风控（精简：只留名词短语）
            risk_short = self._short_risk(r)
            risk_color = r['risk_color'] if r.get('risk_color') else '#1a1a1a'
            _rit = set_table_item(self.table, i, COL_H_RISK, risk_short, risk_color,
                                  bold=True, align=left)
            _rit.setToolTip(r.get('risk_status') or risk_short)
            # 信号灯
            sig_item = QTableWidgetItem(r['signal_text'])
            lvl = r['signal_level']
            bg = SIGNAL_BG.get(lvl, SIGNAL_BG['gray'])
            fg = '#000000'
            sig_item.setBackground(QBrush(QColor(bg)))
            sig_item.setForeground(QColor(fg))
            f = sig_item.font()
            f.setBold(True)
            sig_item.setFont(f)
            sig_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            _sig_tip = r['signal_text']
            if r.get('t_score'):
                _sig_tip += ' ｜ 强度 %s 分（%s轨）' % (r['t_score'], r.get('t_side') or '')
            if r.get('t_window'):
                _sig_tip += ' ｜ 时段 %s' % r['t_window']
            sig_item.setToolTip(_sig_tip)
            self.table.setItem(i, COL_H_SIG, sig_item)
            # 操作建议（精简）
            act_short = self._short_action(r['action'] or '')
            if '防T飞' in act_short or '锁仓' in act_short:
                act_color = '#e65100'
            elif '等确认' in act_short or '等金叉' in act_short:
                act_color = '#f9a825'
            elif '低吸' in act_short or '买入' in act_short:
                act_color = '#e53935'
            elif '卖出' in act_short or '高抛' in act_short:
                act_color = '#43a047'
            else:
                act_color = '#607d8b'
            _ait = set_table_item(self.table, i, COL_H_ACT, act_short, act_color,
                                  bold=True, align=left)
            _act_tip = r.get('action') or act_short
            if r.get('t_plan'):
                _act_tip += '\n' + str(r['t_plan'])
            if r.get('est_cost_after'):
                _act_tip += '\n预估成本 → %s（%+.3f%%）' % (
                    r['est_cost_after'], r.get('est_cost_delta_pct') or 0.0)
            _ait.setToolTip(_act_tip)

            # 控盘（新增列）
            from services.control_profile import ctrl_cell, ctrl_tooltip
            _ci = r.get('ctrl')
            _ct, _cc = ctrl_cell(_ci)
            _cit = set_table_item(self.table, i, COL_H_CTRL, _ct, _cc,
                                  align=Qt.AlignmentFlag.AlignVCenter
                                  | Qt.AlignmentFlag.AlignCenter)
            _cit.setToolTip(ctrl_tooltip(_ci))

            # 触发行背景
            if row_bg:
                for col in range(11):
                    it = self.table.item(i, col)
                    if it is not None:
                        it.setBackground(QBrush(row_bg))

        # 行填完后按真实文字宽度定列宽（剩余宽度给「操作建议」）
        self._fit_hold_columns()

    # 列宽：下限保证不缺字，上限防某一列吃掉整表
    # 单元格左右留白：样式表 QTableWidget::item{padding:4px 8px} 就要 16px，
    # 再加 2px 边框 + 2px 加粗余量。这个值不能再调小，否则文字会被省略号截断。
    _HOLD_PAD = 20
    _HOLD_MINW = {COL_H_NAME: 64, COL_H_CODE: 58, COL_H_PRICE: 56, COL_H_PCT: 58,
                  COL_H_BUY: 78, COL_H_SELL: 78, COL_H_MOM: 64, COL_H_RISK: 64,
                  COL_H_SIG: 84, COL_H_CTRL: 56}
    _HOLD_MAXW = {COL_H_NAME: 110, COL_H_CODE: 84, COL_H_PRICE: 84, COL_H_PCT: 90,
                  COL_H_BUY: 96, COL_H_SELL: 96, COL_H_MOM: 132, COL_H_RISK: 110,
                  COL_H_SIG: 150, COL_H_CTRL: 100}

    def _fit_hold_columns(self):
        """按「表头 + 每行实际文字」的像素宽度定列宽；「操作建议」列保持 Stretch 吃剩余宽度。
        这样窗口再窄也不会把文字切掉（模型：内容需要多少就给多少，剩下的全给操作建议）。"""
        t = self.table
        n = t.columnCount()
        for c in range(n):
            if c == COL_H_ACT:
                continue
            w = self._HOLD_MINW.get(c, 60)
            if c < len(HEADER_HOLD):
                w = max(w, QFontMetrics(t.font()).horizontalAdvance(HEADER_HOLD[c]) + self._HOLD_PAD)
            for r in range(t.rowCount()):
                it = t.item(r, c)
                if it is None or not it.text():
                    continue
                w = max(w, QFontMetrics(it.font()).horizontalAdvance(it.text()) + self._HOLD_PAD)
            t.setColumnWidth(c, int(min(w, self._HOLD_MAXW.get(c, 120))))

    def _on_hold_context_menu(self, pos):
        """分时做T表右键：补成本/数量、从做T列表移除、刷新。"""
        it = self.table.itemAt(pos)
        if it is None:
            return
        row = it.row()
        if row < 0 or row >= len(self._hold_rows):
            return
        r = self._hold_rows[row]
        code = str(r.get('code') or '')
        name = str(r.get('name') or '')
        menu = QMenu(self)
        act_edit = menu.addAction('✎ 补成本/数量（%s %s）' % (code, name))
        act_del = menu.addAction('🗑 从做T列表移除（%s %s）' % (code, name))
        menu.addSeparator()
        act_ref = menu.addAction('↻ 刷新')
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._edit_holding_cost(code, r)
        elif chosen is act_del:
            if QMessageBox.question(
                    self, '确认移除',
                    '从分时做T列表移除 %s %s？\n（只从做T列表删除，不影响「我的自选」）'
                    % (code, name)) != QMessageBox.StandardButton.Yes:
                return
            try:
                self._remove_holding(code)
            except Exception as e:
                QMessageBox.critical(self, '删除失败', '%s: %s' % (type(e).__name__, e))
                return
            self.set_status('已从做T列表移除 %s' % code)
            self.refresh()
        elif chosen is act_ref:
            self.refresh()

    def _edit_holding_cost(self, code, row=None):
        """补/改成本与数量（两次输入，留空不改；只更新这两列，不动买入时间）。"""
        cur = row or {}
        _c = ('%.3f' % cur['cost']) if cur.get('cost') else '—'
        _q = str(int(cur['qty'])) if cur.get('qty') else '—'
        s1, ok1 = QInputDialog.getText(
            self, '补成本/数量', '%s 持仓成本（当前 %s，留空不改）：' % (code, _c))
        if not ok1:
            return
        s2, ok2 = QInputDialog.getText(
            self, '补成本/数量', '%s 持仓数量（当前 %s，留空不改）：' % (code, _q))
        if not ok2:
            return
        cost = qty = None
        try:
            if (s1 or '').strip():
                cost = float(s1.strip())
                if cost <= 0:
                    raise ValueError
            if (s2 or '').strip():
                qty = int(float(s2.strip()))
                if qty <= 0:
                    raise ValueError
        except ValueError:
            QMessageBox.warning(self, '格式错误', '成本填大于 0 的数字；数量填大于 0 的整数。')
            return
        if cost is None and qty is None:
            return
        try:
            self._update_cost_qty(code, cost, qty)
        except Exception as e:
            QMessageBox.critical(self, '写入失败', '%s: %s' % (type(e).__name__, e))
            return
        self.set_status('已更新 %s 的成本/数量' % code)
        self.refresh()

    @staticmethod
    def _short_momentum(mom):
        """动能信号精简映射"""
        if not mom or mom == '暂无':
            return '--'
        out = []
        for kw, short in [
            ('MACD零轴下金叉', '零下金叉'), ('MACD零轴上死叉', '零上死叉'),
            ('MACD金叉', '金叉'), ('MACD死叉', '死叉'),
            ('日线底背离', '底背离'), ('日线顶背离', '顶背离'),
            ('底背离雏形', '底背离'), ('顶背离雏形', '顶背离'),
            ('TD低9', 'TD9'), ('TD高9', 'TD9'),
            ('TD低', 'TD低'), ('TD高', 'TD高'),
            ('触及日线支撑', '触支撑'), ('触及日线压力', '触压力'),
        ]:
            if kw in mom:
                out.append(short)
        return '/'.join(out) if out else '--'

    @staticmethod
    def _short_risk(r):
        """风控状态精简"""
        rs = r.get('risk_status', '') or ''
        if '锁仓' in rs or '涨停' in rs:
            base = '锁仓'
        elif '主升浪' in rs:
            base = '主升浪'
        elif '暂停买入' in rs or '防飞刀' in rs:
            base = '防飞刀'
        elif '开盘波动' in rs:
            base = '开盘波动'
        elif 'VWAP上方' in rs:
            base = 'V上'
        elif 'VWAP下方' in rs:
            base = 'V下'
        else:
            base = '正常'
        return base

    @staticmethod
    def _short_action(act):
        """操作建议精简"""
        if not act:
            return '观望'
        # 机构级引擎（strategy/intraday_t_engine）的完整文案：给语义完整的短标签。
        # 这些必须放在下面的关键词猜测之前，否则「反弹卖出」会被误判成「高抛」、
        # 未命中的会被 act[:6] 硬切成「不做T，等条」。
        if '不做T' in act:
            return '不做T·等条件'
        if '先卖后买' in act:
            return '反T·先卖后买'
        if '先买后卖' in act:
            return '正T·先买后卖'
        if '接近条件' in act:
            return '等VWAP量价'
        if '防T飞' in act:
            return '防T飞'
        if '锁仓' in act:
            return '锁仓'
        if '停低吸' in act or '谨慎观望' in act:
            return '停低吸'
        if '分批低吸' in act or '正T买入' in act or '低吸' in act:
            return '低吸'
        if '反T卖出' in act or '高抛' in act or '卖出' in act:
            return '高抛'
        if '等动能确认' in act or '准备低吸' in act:
            return '等确认'
        if '观望' in act:
            return '观望'
        return act[:8]   # 兜底：放宽到 8 字（原来 6 字，容易切断词）

    # ============================================================
    # 闪烁
    # ============================================================
    def _toggle_flash(self):
        if not self._flash_codes:
            if self._flash_on:
                self._flash_on = False
                self._render_hold_table()
            return
        self._flash_on = not self._flash_on
        self._render_hold_table()

    # ============================================================
    # 工具函数（保留 V3.1）
    # ============================================================
    def _calc_atr(self, bars, period=14):
        if len(bars) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(bars)):
            h = bars[i]['high']
            l = bars[i]['low']
            pc = bars[i - 1]['close']
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if not trs:
            return 0.0
        return float(np.mean(trs[-period:]))

    def _check_market_sentiment(self):
        try:
            from utils.http_market_data import eastmoney_request
            data = eastmoney_request('/api/qt/stock/get', {
                'secid': '1.000001', 'fields': 'f2,f3'
            }, timeout=5)
            if data and 'data' in data:
                pct = float(data['data'].get('f3', 0)) / 100.0
                self._global_warn = (pct < -1.0)
                return
        except Exception:
            pass
        self._global_warn = False

    def _compute_theme_strength(self, code, price=0.0, pct=0.0):
        cached = self._theme_cache.get(code)
        if cached and time.time() - cached['ts'] < 1800:
            return cached['f'], cached['tag'], cached['direction']

        f = 0.0
        tag = '中性'
        direction = 'neutral'
        lbc = 0
        try:
            from data.limit_up_reason_db import get_last_limit_up_reason
            reason, date, lbc, industry = get_last_limit_up_reason(code)
            if reason:
                f += 0.10
                tag = str(reason).split('+')[0].strip()[:8]
                try:
                    lbc_int = int(lbc or 0)
                except Exception:
                    lbc_int = 0
                if lbc_int >= 5:
                    f += 0.15
                elif lbc_int >= 3:
                    f += 0.12
                elif lbc_int == 2:
                    f += 0.08
                elif lbc_int == 1:
                    f += 0.04
        except Exception as e:
            print(f'[ATR做T] 题材原因查询失败 {code}: {e}', flush=True)
            reason = None
            lbc = 0

        try:
            sector_score = self._fetch_sector_strength_factor(code)
            f += sector_score
        except Exception as e:
            print(f'[ATR做T] 板块强度因子失败 {code}: {e}', flush=True)

        try:
            lbc_int = int(lbc or 0)
        except Exception:
            lbc_int = 0
        if lbc_int >= 3:
            f += 0.20
        elif lbc_int == 1:
            f += 0.10
        # [CYB-GATE] 弱势降分线按板性：主板 -5%，创业板 -10%
        if pct <= _pct_thresholds(code)[2]:
            f -= 0.10

        f = max(-1.0, min(1.0, float(f)))
        if f >= 0.3:
            direction = 'strong'
            tag = f'强{tag}' if tag and tag != '中性' else '强势'
        elif f <= -0.3:
            direction = 'weak'
            tag = f'弱{tag}' if tag and tag != '中性' else '弱势'
        else:
            direction = 'neutral'
            if not tag or tag == '中性':
                tag = '中性'

        self._theme_cache[code] = {
            'f': f, 'ts': time.time(), 'tag': tag, 'direction': direction,
        }
        return f, tag, direction

    def _fetch_sector_strength_factor(self, code):
        try:
            from utils.http_market_data import eastmoney_request
            data = eastmoney_request('/api/qt/clist/get', {
                'pn': 1, 'pz': 30, 'po': 1, 'np': 1,
                'fltt': 2, 'invt': 2,
                'fs': 'm:90+t:2',
                'fields': 'f12,f14,f3,f104,f105',
            }, timeout=6)
            if not data or 'data' not in data or not data['data']:
                return 0.0
            diff = data['data'].get('diff') or []
            if not diff:
                return 0.0
            industry_name = None
            try:
                from data.limit_up_reason_db import get_last_limit_up_reason
                _, _, _, ind = get_last_limit_up_reason(code)
                if ind:
                    industry_name = str(ind).strip()
            except Exception:
                industry_name = None

            factor = 0.0
            matched = None
            if industry_name:
                for idx, item in enumerate(diff):
                    name = item.get('f14', '') or ''
                    if name and (name in industry_name or industry_name in name):
                        matched = (idx, item)
                        break
            if matched:
                idx, item = matched
                if idx < 5:
                    factor += 0.25
                elif idx < 10:
                    factor += 0.15
                elif idx < 20:
                    factor += 0.05
                elif idx >= len(diff) - 5:
                    factor -= 0.15
                try:
                    up_cnt = float(item.get('f104', 0) or 0)
                    down_cnt = float(item.get('f105', 0) or 0)
                    total = up_cnt + down_cnt
                    if total > 0:
                        up_ratio = up_cnt / total
                        if up_ratio >= 0.7:
                            factor += 0.20
                        elif up_ratio <= 0.3:
                            factor -= 0.20
                except Exception:
                    pass
            else:
                try:
                    top_pct = float(diff[0].get('f3', 0) or 0)
                    if top_pct >= 2.0:
                        factor += 0.05
                    elif top_pct <= -1.5:
                        factor -= 0.05
                except Exception:
                    pass
            return max(-0.5, min(0.5, factor))
        except Exception as e:
            print(f'[ATR做T] 板块因子HTTP失败 {code}: {e}', flush=True)
            return 0.0

    def _get_or_anchor(self, code, price, vwap, atr, f):
        now = time.time()
        lt = time.localtime(now)
        minutes = lt.tm_hour * 60 + lt.tm_min
        if minutes < 9 * 60 + 35:
            return None
        anchor = self._anchor_state.get(code)
        need_anchor = False
        reason = ''
        if anchor is None:
            need_anchor = True
            reason = 'init'
        else:
            if now - anchor['ts'] >= 30 * 60:
                need_anchor = True
                reason = '30min'
            else:
                old_vwap = anchor['vwap']
                old_atr = anchor['atr']
                if old_vwap > 0 and vwap > 0:
                    dev = abs(vwap - old_vwap) / old_vwap
                    threshold = max(0.02, 0.0005, 0.1 * old_atr / old_vwap)
                    if dev > threshold:
                        need_anchor = True
                        reason = f'dev{dev*100:.1f}%'
        if need_anchor:
            k_buy = 0.3 - 0.1 * f
            k_sell = 0.3 + 0.1 * f
            buy_point = round(vwap - k_buy * atr, 2)
            sell_point = round(vwap + k_sell * atr, 2)
            anchor = {
                'ts': now, 'vwap': vwap, 'atr': atr,
                'k_buy': k_buy, 'k_sell': k_sell, 'f': f,
                'buy_point': buy_point, 'sell_point': sell_point,
                'reason': reason,
            }
            self._anchor_state[code] = anchor
        return anchor

    def _play_sound(self, kind, code):
        now_key = f'{code}_sound'
        last = self._lock_state.get(now_key)
        now = time.time()
        if last and now - last < 60:
            return
        self._lock_state[now_key] = now
        print(f'[ATR做T] 提醒 {code}: {kind}', flush=True)
        try:
            import winsound
            if kind == 'buy':
                winsound.Beep(800, 200)
            else:
                winsound.Beep(1200, 300)
        except Exception:
            pass


    # ============================================================
    # 日K建仓模块 V1.0（纯建仓 + 终级清仓）
    # 基于分时做T思路升级：20日VWAP价值中枢 + 14日ATR波动单位
    # 三档建仓（试仓/加仓/重仓） + 两档止盈 + 一档止损
    # 原则：完全不动分时做T任何逻辑；状态/缓存/锁 全部独立
    # ============================================================
    def _setup_tab_buttons(self):
        """在标题栏 title_label 右侧插入 [分时做T] / [日K建仓] 两个 Tab 按钮（仿竞价Tab样式）"""
        card_layout = self._card_frame.layout()
        title_bar_layout = card_layout.itemAt(0).layout()
        if title_bar_layout is None:
            return

        self._tab_style_normal = (
            'QPushButton{'
            'background:#f0f4f9;color:#666666;'
            'border:1px solid #d0d7e0;border-radius:4px;'
            'padding:3px 12px;font-size:11px;}'
            'QPushButton:hover{background:#e6f0ff;color:#2f6bff;}'
        )
        self._tab_style_checked = (
            'QPushButton{'
            'background:#2f6bff;color:#ffffff;'
            'border:1px solid #2f6bff;border-radius:4px;'
            'padding:3px 12px;font-size:11px;font-weight:bold;}'
        )

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)

        self._btn_hold = QPushButton('分时做T')
        self._btn_hold.setCheckable(True)
        self._btn_hold.setStyleSheet(self._tab_style_checked)
        self._btn_hold.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_hold, 0)

        self._btn_daily = QPushButton('日K建仓')
        self._btn_daily.setCheckable(True)
        self._btn_daily.setStyleSheet(self._tab_style_normal)
        self._btn_daily.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_daily, 1)

        self._btn_hold.setChecked(True)

        # 插入位置：title_label(0) 之后、stretch 之前
        title_bar_layout.insertWidget(1, self._btn_hold)
        title_bar_layout.insertWidget(2, self._btn_daily)

        # 导出按钮：把日K建仓表的股票代码导出为 txt（每行一个，可直接导入同花顺）
        self._btn_export = QPushButton('📤 导出代码')
        self._btn_export.setStyleSheet(self._tab_style_normal)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setToolTip('导出日K建仓表的股票代码（每行一个，无表头，可直接导入同花顺）')
        self._btn_export.clicked.connect(self._export_daily_codes)
        title_bar_layout.insertWidget(3, self._btn_export)
        self._btn_export.setVisible(False)   # 默认在分时做T Tab，先隐藏
        self._tab_group.idClicked.connect(self._switch_tab)

    # ============================================================
    # 持仓管理（分时做T表右键：补成本数量 / 从做T列表移除 → holding 表）
    # ============================================================
    def _remove_holding(self, code):
        """从 holding 表删除一个代码。"""
        import duckdb
        con = duckdb.connect(self._track_db_path)
        try:
            con.execute('DELETE FROM holding WHERE code = ?', [code])
        finally:
            con.close()
        self._refresh_holding_db()

    # ---------- 自选 → 做T列表 ----------
    def _update_cost_qty(self, code, cost=None, qty=None):
        """只更新成本/数量，不动名称与买入时间。"""
        import duckdb
        con = duckdb.connect(self._track_db_path)
        try:
            if cost is not None:
                con.execute('UPDATE holding SET cost = ?, updated_at = ? WHERE code = ?',
                            [float(cost), datetime.now(), code])
            if qty is not None:
                con.execute('UPDATE holding SET qty = ?, updated_at = ? WHERE code = ?',
                            [int(qty), datetime.now(), code])
        finally:
            con.close()
        self._refresh_holding_db()

    # ============================================================
    # 导出日K建仓股票代码（供同花顺批量导入自选股）
    # ============================================================
    def _export_daily_codes(self):
        """把日K建仓表的股票代码导出为 txt：每行一个 6 位代码、无表头。
        格式与同花顺「自选股 - 从文本中导入」兼容；自动去重、保持表格顺序。"""
        rows = getattr(self, '_daily_rows', None) or []
        codes, seen = [], set()
        for r in rows:
            c = str(r.get('code', '') or '').strip()
            if len(c) == 6 and c.isdigit() and c not in seen:
                seen.add(c)
                codes.append(c)
        if not codes:
            QMessageBox.information(self, '导出代码', '当前日K建仓表没有可导出的股票代码。')
            return
        default_name = '日K建仓_%s.txt' % datetime.now().strftime('%Y%m%d_%H%M')
        path, _ = QFileDialog.getSaveFileName(
            self, '导出股票代码（每行一个，可直接导入同花顺）',
            default_name, '文本文件 (*.txt)')
        if not path:
            return
        if not path.lower().endswith('.txt'):
            path += '.txt'
        try:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write('\n'.join(codes))
                f.write('\n')
        except Exception as e:
            QMessageBox.warning(self, '导出失败', str(e))
            return
        QMessageBox.information(
            self, '导出成功',
            '已导出 %d 只股票代码到：\n%s\n\n每行一个代码、无表头，可直接导入同花顺。'
            % (len(codes), path))

    def _switch_tab(self, idx):
        """切换 Tab：0=分时做T（持仓表），1=日K建仓（底仓表）。
        按需启停：切到日K暂停分时刷新与金铲子（释放CPU），切回恢复。"""
        # 导出按钮只属于日K建仓，在分时做T Tab 下不出现，避免误点
        if hasattr(self, '_btn_export'):
            self._btn_export.setVisible(idx == 1)
        if idx == 0:
            self._tab_active = 0
            self._hold_widget.setVisible(True)
            self._daily_widget.setVisible(False)
            self._btn_hold.setStyleSheet(self._tab_style_checked)
            self._btn_daily.setStyleSheet(self._tab_style_normal)
            # 恢复分时刷新
            self.start_refresh(5000)
            self._daily_timer.stop()
            if getattr(self, '_last_hold_title', None):
                self.title_label.setText(self._last_hold_title)
        else:
            self._tab_active = 1
            self._hold_widget.setVisible(False)
            self._daily_widget.setVisible(True)
            self._btn_hold.setStyleSheet(self._tab_style_normal)
            self._btn_daily.setStyleSheet(self._tab_style_checked)
            # 暂停分时刷新（标题不再被覆盖，省CPU），启动日K计算
            self.stop_refresh()
            if not self._daily_timer.isActive():
                self._daily_timer.start(300000)
            if getattr(self, '_last_hold_title', None) is None:
                self._last_hold_title = self.title_label.text()
            self.title_label.setText(getattr(self, '_last_daily_title', None) or '📈 日K建仓')
            QTimer.singleShot(0, self._daily_refresh)

    def _init_daily_module(self):
        """日K建仓模块初始化：独立缓存/锁/锚定/DB，与分时做T完全隔离"""
        self._daily_rows = []
        self._daily_kline_cache = {}      # {code: (bars, ts)} 10分钟缓存
        self._daily_anchor_state = {}     # 周度锚定
        self._daily_lock_state = {}       # {code_event: ts} 24小时信号冷却
        self._daily_market_warn = False
        self._daily_market_ts = 0.0
        self._daily_rt_stat = None         # 最近一次实时行情覆盖率 {ok, total}
        self._last_hold_title = None
        self._last_daily_title = None
        self._tab_active = 0              # 0=分时做T，1=日K建仓
        self._init_daily_tracking_db()
        self._daily_timer = QTimer(self)
        self._daily_timer.timeout.connect(self._daily_refresh)

    def _init_daily_tracking_db(self):
        """日K建仓跟踪表（独立于 holding 表，不污染分时数据）"""
        try:
            import duckdb
            con = duckdb.connect(self._track_db_path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS daily_base_position(
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    t1 DOUBLE, t2 DOUBLE, t3 DOUBLE,
                    stop DOUBLE, take1 DOUBLE, take2 DOUBLE,
                    vwap20 DOUBLE, atr DOUBLE, f DOUBLE,
                    struct_score INTEGER,
                    signal_text TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.close()
        except Exception as e:
            print(f'[日K建仓] 初始化daily_base_position失败: {e}', flush=True)

    def _daily_bars(self, code, price=None, prev_close=None, day_high=None, day_low=None):
        """日K建仓专用K线：120根日K，10分钟缓存；盘中用实时价更新最后一根（拷贝副本，不污染分时缓存）"""
        cached = self._daily_kline_cache.get(code)
        if cached and time.time() - cached[1] < 600:
            bars = [dict(b) for b in cached[0]]
        else:
            bars = self._load_bars(code, n=120)
            if len(bars) < 30:
                return []
            bars = [dict(b) for b in bars]
            self._daily_kline_cache[code] = (bars, time.time())
        if bars and price and price > 0:
            last = bars[-1]
            last['close'] = price
            if day_high and day_high > 0 and day_high > last['high']:
                last['high'] = day_high
            if day_low and day_low > 0 and day_low < last['low']:
                last['low'] = day_low
        return bars

    def _daily_calc_one_stock(self, code, name, price=None, prev_close=None,
                              day_high=None, day_low=None, bars=None):
        """日K建仓核心算法（分时做T思路升级到日K周期）：
        20日VWAP价值中枢 + 14日ATR波动单位 → 三档建仓价 + 两档止盈 + 一档止损；
        题材强度f动态修正建仓价与档位上限；结构分做动能确认。"""
        if bars is None:
            bars = self._daily_bars(code, price=price, prev_close=prev_close,
                                    day_high=day_high, day_low=day_low)
        if len(bars) < 30:
            return None

        closes = np.array([b['close'] for b in bars], dtype=float)
        highs = np.array([b['high'] for b in bars], dtype=float)
        lows = np.array([b['low'] for b in bars], dtype=float)
        vols = np.array([b['volume'] for b in bars], dtype=float)

        last_bar = bars[-1]
        if price is None or price <= 0:
            price = float(last_bar['close'])
        if prev_close is None or prev_close <= 0:
            prev_close = float(bars[-2]['close']) if len(bars) >= 2 else price
        if day_high is None or day_high <= 0:
            day_high = float(last_bar['high'])
        if day_low is None or day_low <= 0:
            day_low = float(last_bar['low'])
        if price <= 0 or prev_close <= 0:
            return None

        pct = (price - prev_close) / prev_close * 100.0
        atr = self._calc_atr(bars, period=14)
        if atr <= 0:
            atr = prev_close * 0.02

        # 20日典型价VWAP（日K价值中枢）
        tp = (highs + lows + closes) / 3.0
        vwap20 = float(np.mean(tp[-20:]))
        if vwap20 <= 0:
            vwap20 = price

        f, theme_tag, theme_dir = self._compute_theme_strength(code, price=price, pct=pct)

        # 题材强度修正：f>0上移建仓价（强势不深调），f<0下移（弱势加厚安全垫）
        shift = (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)

        # 三档建仓价（只在中枢下方）：试仓/加仓/重仓
        t1 = vwap20 - 1.2 * atr + shift          # 试仓（价值中枢下沿）
        t2 = vwap20 - 1.8 * atr + shift          # 加仓（错杀回调位）
        platform = float(np.min(lows[-20:])) + 0.2 * atr   # 前期平台支撑
        t3 = min(platform, vwap20 - 2.4 * atr) + shift   # 重仓（极端回调位，取平台与中枢-2.4ATR更低者）
        stop = t3 - 0.5 * atr                    # 止损（极限支撑击穿）
        take1 = vwap20 + 2.5 * atr + 0.5 * max(f, 0.0) * atr   # 止盈1（减半）
        take2 = vwap20 + 3.5 * atr + 0.5 * max(f, 0.0) * atr   # 止盈2（清仓）

        # 周度锚定：锚定生效期间价位不随日间波动刷新
        anchor = self._daily_anchor(code, vwap20, atr, f, platform)
        if anchor is not None:
            t1, t2, t3 = anchor['t1'], anchor['t2'], anchor['t3']
            stop, take1, take2 = anchor['stop'], anchor['take1'], anchor['take2']

        # 档位上限（仓位管理：强趋势可满三档，弱势仅试仓，退潮禁建）
        if f >= 0.3:
            max_tier = 3
        elif f >= 0:
            max_tier = 2
        elif f >= -0.3:
            max_tier = 1
        else:
            max_tier = 0

        # MACD / TD / 背离（复用分时纯函数）
        dif, dea, hist = calc_macd(closes, 8, 21, 5)
        cross = detect_cross(dif, dea) if len(dif) else None
        td = calc_td(closes.tolist())
        div = check_divergence(closes, dif) if len(dif) else None

        # 量能：5日均量缩量判断
        vol5 = float(np.mean(vols[-5:])) if len(vols) >= 5 else 0.0
        shrink = (vol5 > 0) and (float(vols[-1]) < vol5 * 0.8)

        # 均线结构
        ma10 = float(np.mean(closes[-10:])) if len(closes) >= 10 else price
        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else price
        trend_up = (ma10 > ma20) and (price > ma10)

        # 结构分（满分6分）
        struct_score = 0
        near_t1 = price <= t1 * 1.01
        near_t2 = price <= t2 * 1.01
        near_t3 = price <= t3 * 1.01
        if near_t1 or near_t2 or near_t3:
            struct_score += 1
        if div in ('bottom', 'top'):
            struct_score += 1
        if shrink:
            struct_score += 1
        if td['is_low9'] or td['is_high9']:
            struct_score += 1
        if trend_up:
            struct_score += 1

        # 动能文本
        momentum_parts = []
        if div == 'bottom':
            momentum_parts.append('日线底背离')
        elif div == 'top':
            momentum_parts.append('日线顶背离')
        elif div == 'bottom_emerging':
            momentum_parts.append('底背离雏形')
        elif div == 'top_emerging':
            momentum_parts.append('顶背离雏形')
        if td['is_low9']:
            momentum_parts.append('TD低9')
        elif td['is_high9']:
            momentum_parts.append('TD高9')
        if shrink:
            momentum_parts.append('缩量')
        if trend_up:
            momentum_parts.append('多头排列')
        elif ma10 < ma20:
            momentum_parts.append('空头排列')
        momentum_text = ' + '.join(momentum_parts) if momentum_parts else '暂无'

        return dict(
            code=code, name=name,
            price=round(price, 2), pct=round(pct, 2),
            t1=round(t1, 2), t2=round(t2, 2), t3=round(t3, 2),
            stop=round(stop, 2), take1=round(take1, 2), take2=round(take2, 2),
            vwap20=round(vwap20, 2), atr=round(atr, 2),
            f=round(f, 2), theme_tag=theme_tag, theme_dir=theme_dir,
            max_tier=max_tier, struct_score=struct_score,
            momentum=momentum_text,
            div=div, td=td, cross=cross, shrink=shrink,
            ma10=round(ma10, 2), ma20=round(ma20, 2),
            trend_up=trend_up,
            near_t1=near_t1, near_t2=near_t2, near_t3=near_t3,
        )

    def _daily_anchor(self, code, vwap20, atr, f, platform):
        """日K周度锚定：每周重算一次；偏离8%或拐头才临时刷新，保证建仓计划稳定不飘"""
        now = time.time()
        anchor = self._daily_anchor_state.get(code)
        need = False
        reason = ''
        if anchor is None:
            need = True
            reason = 'init'
        else:
            if now - anchor['ts'] >= 7 * 24 * 3600:
                need = True
                reason = 'weekly'
            else:
                old_vwap = anchor['vwap']
                if old_vwap > 0 and vwap20 > 0:
                    dev = abs(vwap20 - old_vwap) / old_vwap
                    if dev > 0.08:
                        need = True
                        reason = f'dev{dev*100:.1f}%'
        if need:
            shift = (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)
            t1 = vwap20 - 1.2 * atr + shift
            t2 = vwap20 - 1.8 * atr + shift
            t3 = min(platform, vwap20 - 2.4 * atr) + shift
            stop = t3 - 0.5 * atr
            take1 = vwap20 + 2.5 * atr + 0.5 * max(f, 0.0) * atr
            take2 = vwap20 + 3.5 * atr + 0.5 * max(f, 0.0) * atr
            anchor = {
                'ts': now, 'vwap': vwap20, 'atr': atr, 'f': f,
                't1': t1, 't2': t2, 't3': t3,
                'stop': stop, 'take1': take1, 'take2': take2,
                'reason': reason,
            }
            self._daily_anchor_state[code] = anchor
        return anchor

    def _daily_apply_risk(self, r):
        """日K风控一票否决 + 信号灯（对齐分时三色语义，新增波段级风控）"""
        price = r['price']
        t1, t2, t3 = r['t1'], r['t2'], r['t3']
        stop = r['stop']
        take1, take2 = r['take1'], r['take2']
        f = r['f']
        div = r['div']
        td = r['td']
        cross = r['cross']
        struct_score = r['struct_score']
        shrink = r['shrink']
        max_tier = r['max_tier']
        ma10 = r['ma10']
        theme_dir = r['theme_dir']

        risk_status = '正常(中枢上方)' if price >= r['vwap20'] else '正常(中枢下方)'
        risk_color = SIGNAL_FG['green'] if price >= r['vwap20'] else SIGNAL_FG['yellow']
        signal_level = 'gray'
        signal_text = '⚪ 待机'
        signal_dir = None
        action = '持有观察'
        blocked = None

        name = r.get('name', '') or ''
        is_st = ('ST' in name.upper()) or ('退' in name)
        if is_st:
            signal_level = 'yellow'
            signal_text = '🟡 禁入'
            action = 'ST/退市股，禁止建仓'
            risk_status = '⛔ 禁入标的'
            risk_color = SIGNAL_FG['yellow']
            blocked = 'buy'
        elif self._daily_market_warn or f <= -0.6:
            signal_level = 'red'
            signal_text = '🔴 环境风控'
            action = '大盘/题材退潮，暂停建仓'
            risk_status = '🌊 环境风控'
            risk_color = SIGNAL_FG['red']
            blocked = 'buy'
        elif price <= stop:
            signal_level = 'red'
            signal_text = '🔴 止损清仓'
            action = f'跌破止损{stop:.2f}，全部清仓'
            risk_status = '💥 止损清仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K止损清仓', stop, action)
        elif price >= take2 or (price < ma10 and cross == 'dead'):
            signal_level = 'red'
            signal_text = '🔴 清仓执行'
            action = f'到目标位{take2:.2f}或破位，清仓离场'
            risk_status = '🎯 清仓执行'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K清仓执行', take2, action)
        elif price >= take1 and div == 'top':
            signal_level = 'orange'
            signal_text = '🟠 减仓执行'
            action = f'到止盈1 {take1:.2f}+顶背离，减半仓'
            risk_status = '💰 减仓执行'
            risk_color = SIGNAL_FG['orange']
            signal_dir = 'sell'
            self._daily_signal_push(r, '日K减仓提醒', take1, action)
        elif theme_dir == 'weak' or max_tier <= 0:
            signal_level = 'yellow'
            signal_text = '🟡 只清不建'
            action = '弱势/禁建仓，仅可减仓'
            risk_status = '🛑 弱势禁建'
            risk_color = SIGNAL_FG['yellow']
            blocked = 'buy'
        elif max_tier >= 3 and price <= t3 and struct_score >= 4 and shrink:
            signal_level = 'red'
            signal_text = '🔴 重仓执行'
            action = f'到重仓{t3:.2f}，买第三档'
            risk_status = '🟢 重仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K重仓建仓', t3, action)
        elif max_tier >= 2 and price <= t2 and struct_score >= 3 and shrink:
            signal_level = 'red'
            signal_text = '🔴 加仓执行'
            action = f'到加仓{t2:.2f}，买第二档'
            risk_status = '🟢 加仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K加仓建仓', t2, action)
        elif max_tier >= 1 and price <= t1 and struct_score >= 2:
            signal_level = 'red'
            signal_text = '🔴 试仓执行'
            action = f'到试仓{t1:.2f}，买第一档'
            risk_status = '🟢 试仓建仓'
            risk_color = SIGNAL_FG['red']
            signal_dir = 'buy'
            self._daily_signal_push(r, '日K试仓建仓', t1, action)
        elif price <= t1 * 1.01 and (div in ('bottom_emerging', 'bottom') or td['is_low78'] or td['is_low9']):
            signal_level = 'yellow'
            signal_text = '🟡 准备建仓'
            action = '接近试仓价，等企稳确认'
            risk_status = '⏳ 准备建仓'
            risk_color = SIGNAL_FG['yellow']
        else:
            signal_level = 'green'
            signal_text = '🟢 持有观察'
            action = '底仓持有，日K不动'
            risk_status = '🧊 持有观察'
            risk_color = SIGNAL_FG['green']

        r['risk_status'] = risk_status
        r['risk_color'] = risk_color
        r['signal_level'] = signal_level
        r['signal_text'] = signal_text
        r['signal_dir'] = signal_dir
        r['action'] = action
        r['blocked'] = blocked
        return r

    def _daily_signal_push(self, r, event, ref_price, action):
        """日K触发信号：24小时同事件冷却 + 蜂鸣 + 统一总线推送 + 计划写库"""
        code = r['code']
        now = time.time()
        key = f'{code}_{event}'
        last = self._daily_lock_state.get(key)
        if last and now - last < 24 * 3600:
            return
        self._daily_lock_state[key] = now
        kind = 'buy' if '建仓' in event else 'sell'
        self._play_sound(kind, code)
        try:
            from services.wechat_bus import get_wechat_bus
            get_wechat_bus().send_t_timing(
                event=event, code=code, name=r.get('name', ''),
                price=r['price'], vwap=r['vwap20'], atr=r['atr'],
                ref_price=ref_price, cur_status=r['risk_status'],
                reason=action, risk=r['risk_status'], action=action)
        except Exception:
            pass
        try:
            import duckdb
            con = duckdb.connect(self._track_db_path)
            con.execute("""
                INSERT OR REPLACE INTO daily_base_position
                (code, name, t1, t2, t3, stop, take1, take2,
                 vwap20, atr, f, struct_score, signal_text)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (code, r['name'], r['t1'], r['t2'], r['t3'], r['stop'],
                  r['take1'], r['take2'], r['vwap20'], r['atr'], r['f'],
                  r['struct_score'], r.get('signal_text', '')))
            con.close()
        except Exception as e:
            print(f'[日K建仓] 写daily_base_position失败: {e}', flush=True)

    def _daily_check_market(self):
        """大盘环境风控：上证指数跌超2% → 暂停建仓（10分钟缓存）"""
        now = time.time()
        if now - self._daily_market_ts < 600:
            return self._daily_market_warn
        warn = False
        try:
            from utils.http_market_data import eastmoney_request
            data = eastmoney_request('/api/qt/stock/get', {
                'secid': '1.000001', 'fields': 'f2,f3'
            }, timeout=5)
            if data and 'data' in data:
                pct = float(data['data'].get('f3', 0)) / 100.0
                warn = pct < -2.0
        except Exception:
            pass
        self._daily_market_warn = warn
        self._daily_market_ts = now
        return warn

    def _daily_fetch_and_calc(self):
        """[V5.0] 数据源：band_pattern_engine.query_signals()"""
        self._daily_check_market()
        try:
            from services.band_pattern_engine import query_signals
            sigs = query_signals() or []
        except Exception as e:
            print(f'[日K建仓] 读信号失败: {e}', flush=True)
            sigs = []
        if not sigs:
            return []
        # 题材来源：data/limit_up_reason_db.get_last_limit_up_reason(code)
        try:
            from data.limit_up_reason_db import get_last_limit_up_reason
        except Exception as e:
            print(f'[日K建仓] 题材模块导入失败: {e}', flush=True)
            get_last_limit_up_reason = None
        _theme_cache = {}
        rows = []
        for s in sigs:
            # 默认只显示"建仓触发 + 等待确认"，观察/失效不进表格
            if s.get('signal_level', '') not in ('建仓触发', '等待确认'):
                continue
            code = s['code']
            theme = ''
            if get_last_limit_up_reason is not None:
                if code not in _theme_cache:
                    try:
                        _r = get_last_limit_up_reason(code)
                        _theme_cache[code] = (_r[0] or '') if _r else ''
                    except Exception:
                        _theme_cache[code] = ''
                theme = _theme_cache.get(code, '')
            rows.append({
                'name': s.get('name') or code,
                'code': code,
                'price': s.get('push_price') or 0,
                'pct': s.get('push_pct') or 0,
                'pattern_name': _PATTERN_SHORT.get(s.get('pattern_name', ''), s.get('pattern_name', '')),
                'signal_level': s.get('signal_level', ''),
                'base_date': s.get('base_date', ''),
                'push_date': s.get('push_date', ''),   # 扫描数据基准日（标题用）
                'theme': theme,
                'trigger_type': _TRIGGER_SHORT.get(s.get('trigger_type', ''), s.get('trigger_type', '')),
                'trigger_price': s.get('trigger_price') or 0,
                'take_profit': s.get('take_profit') or 0,
                'env_score': s.get('env_score'),
                'env_note': s.get('env_note', '') or '',
                'note': s.get('note', ''),
                # 控盘：estimate_control_score 的分数 + judge_wash_or_distribute 的阶段
                'control_score': s.get('control_score') or 0,
                'stage_guess': s.get('stage_guess') or '',
                # 引擎写库的控盘短标签（原来漏带 → 控盘列只能退回 note 白名单比对）
                'ctrl_tag': s.get('ctrl_tag') or '',
                # 「观察」列要用的五阶段因子字段（query_signals 是 SELECT *，都在 s 里）
                'probe_ok': bool(s.get('probe_ok')),
                'c4_ok': bool(s.get('c4_ok')),
                'c6_ok': bool(s.get('c6_ok')),
                'brk_type': s.get('brk_type') or '',
                'vreg_tags': s.get('vreg_tags') or '',
                'dist_type': s.get('dist_pattern_type') or '',
                'markup_type': s.get('markup_ok') and (s.get('markup_type') or '') or '',
            })
        # [实时行情] 批量拉最新价，覆盖盘后扫描时存的 push_price/push_pct。
        # push_price 是"扫描那一刻"的价格（可能是上一交易日收盘价），
        # 这里统一换成最新实时价；拿不到实时价(price<=0)时保留 DB 原值，不置 0。
        # 本函数运行在 run_async 后台线程，178 只实测约 0.23 秒，不阻塞 UI。
        rt_ok = 0
        if rows:
            _codes = [r['code'] for r in rows]
            try:
                from utils.http_market_data import get_realtime_quotes_http
                _quotes = get_realtime_quotes_http(_codes) or {}
            except Exception as e:
                print(f'[日K建仓] 实时行情失败: {e}', flush=True)
                _quotes = {}
            for r in rows:
                _q = _quotes.get(r['code']) or {}
                _p = float(_q.get('price') or 0)
                if _p <= 0:
                    continue
                _pc = _q.get('pct_chg')
                if _pc is None:
                    _lc = float(_q.get('last_close') or 0)
                    _pc = (_p - _lc) / _lc * 100.0 if _lc else 0.0
                r['price'] = _p
                r['pct'] = float(_pc)
                rt_ok += 1
        self._daily_rt_stat = {'ok': rt_ok, 'total': len(rows)}
        return rows

    def _daily_refresh(self):
        """日K建仓刷新（仅日K Tab激活时运行，5分钟一次）"""
        if getattr(self, '_tab_active', 0) != 1:
            return
        self.run_async(self._daily_fetch_and_calc, self._daily_on_loaded, self._daily_on_failed)

    def _daily_on_loaded(self, rows):
        """主线程：渲染日K建仓表 + 更新标题"""
        self._daily_rows = rows or []
        now = datetime.now()
        h, m = now.hour, now.minute
        if now.weekday() >= 5:
            tag = '休市'
        elif ((h == 9 and m >= 30) or h == 10 or (h == 11 and m <= 30)
              or h == 13 or h == 14) and h < 15:
            tag = '盘中'
        else:
            tag = '盘后'
        # 数据基准日：取本次展示记录里最新的 push_date（扫描那一刻的数据日期）
        # 目的：让标题如实说明"信号是哪天的数据"，避免被误读为盘中实时选股
        _dd = ''
        for _r in self._daily_rows:
            _p = _r.get('push_date') or ''
            if _p > _dd:
                _dd = _p
        _dd_short = _dd[5:] if len(_dd) >= 10 else _dd
        if _dd_short:
            self._last_daily_title = (
                f'📈 日K建仓 ({tag}·数据{_dd_short}) · {len(self._daily_rows)}只')
        else:
            self._last_daily_title = f'📈 日K建仓 ({tag}) · {len(self._daily_rows)}只'
        if getattr(self, '_tab_active', 0) == 1:
            self.title_label.setText(self._last_daily_title)
        # 阀门开启时，标题补上过滤后的可见只数
        try:
            if getattr(self, '_chk_env', None) is not None and self._chk_env.isChecked():
                _vis = self._daily_visible_rows()
                self._last_daily_title = (
                    self._last_daily_title.split(' ·')[0] + ' · 可建仓%d只' % len(_vis))
                if getattr(self, '_tab_active', 0) == 1:
                    self.title_label.setText(self._last_daily_title)
        except Exception:
            pass
        self._daily_render_table()
        self.set_update_time()
        # 建仓触发推送（仅「建仓触发」+ 环境分>=3，同基准日去重，后台线程发送不阻塞）
        try:
            self._daily_push_entries(self._daily_rows)
        except Exception as _pe:
            print('[日K建仓] 推送异常: %s' % _pe, flush=True)
        # 实时行情覆盖率（主线程写状态栏；_daily_rt_stat 由后台线程赋值）
        _rt = getattr(self, '_daily_rt_stat', None) or {}
        if _rt.get('total'):
            self.set_status('实时行情 %d/%d 只' % (_rt.get('ok', 0), _rt['total']))

    def _daily_push_entries(self, rows):
        """日K建仓推送：仅「建仓触发」+ 环境分>=3。

        同一 (code, base_date) 24 小时内只推一次；记录持久化到
        data/cache/daily_entry_pushed.json，程序重启不会重复推送。
        推送内容：建仓价（引擎挂单价）/ 止盈价（建仓价×1.03）/ 环境分。
        """
        if not rows:
            return
        try:
            from services.wechat_bus import get_wechat_bus
            import services.wechat_bus as _wb
            import json as _json
        except Exception as e:
            print('[日K建仓] 推送模块不可用: %s' % e, flush=True)
            return

        _pf = os.path.join(_wb.PROJECT_ROOT, 'data', 'cache', 'daily_entry_pushed.json')
        _done = {}
        try:
            with open(_pf, encoding='utf-8') as _f:
                _done = _json.load(_f) or {}
        except Exception:
            _done = {}

        bus = get_wechat_bus()
        _now = time.time()
        _sent = 0
        _seen = set()
        for r in rows:
            if r.get('signal_level') != '建仓触发':
                continue
            if (r.get('env_score') or 0) < 3:
                continue
            _k = '%s|%s' % (r.get('code', ''), r.get('base_date', ''))
            if _k in _seen:
                continue
            _seen.add(_k)
            try:
                if _now - float(_done.get(_k, 0) or 0) < 86400:
                    continue
            except Exception:
                pass
            try:
                _res = bus.send_daily_entry(
                    code=r.get('code', ''), name=r.get('name', ''),
                    price=r.get('price'), pct=r.get('pct'),
                    pattern=r.get('pattern_name', ''),
                    trigger_type=r.get('trigger_type', ''),
                    entry=r.get('trigger_price'),
                    take_profit=r.get('take_profit'),
                    env_score=r.get('env_score'),
                    env_note=r.get('env_note', ''),
                    theme=r.get('theme', ''),
                    base_date=r.get('base_date', ''),
                    push_date=r.get('push_date', ''),
                    note=r.get('note', ''),
                    dedup_key=r.get('base_date', ''))
                if _res and _res.get('sent'):
                    _done[_k] = _now
                    _sent += 1
            except Exception as _e:
                print('[日K建仓] 推送失败 %s: %s' % (r.get('code'), _e), flush=True)

        if _sent:
            try:
                with open(_pf, 'w', encoding='utf-8') as _f:
                    _json.dump(_done, _f, ensure_ascii=False)
            except Exception as _e:
                print('[日K建仓] 推送记录写入失败: %s' % _e, flush=True)
            print('[日K建仓] 已推送 %d 条建仓触发（环境分>=3）' % _sent, flush=True)

    def _daily_on_failed(self, err):
        self.set_status('日K建仓数据获取失败')

    def _on_env_filter_changed(self, _state=0):
        """环境分阀门开关：重渲染（不重新拉数据）"""
        self._daily_render_table()

    def _daily_visible_rows(self):
        """按环境分阀门过滤后的可见行"""
        rows = self._daily_rows
        try:
            on = self._chk_env.isChecked()
        except Exception:
            on = False
        if on:
            rows = [r for r in rows if (r.get('env_score') or 0) >= 3]
        return rows

    def _daily_render_table(self):
        """[V5.0] 渲染日K建仓表（13列，含环境分阀门过滤 + 五阶段观察列）"""
        rows = self._daily_visible_rows()
        # 阀门提示（环境分是"当日市场温度"，不是个股评分）
        try:
            if self._chk_env.isChecked():
                self._env_hint.setText(
                    '已过滤：%d/%d（环境分\u22653 可建仓）' % (len(rows), len(self._daily_rows)))
            else:
                _ge3 = sum(1 for r in self._daily_rows if (r.get('env_score') or 0) >= 3)
                self._env_hint.setText('可建仓(\u22653) %d 只 / 共 %d 只' % (
                    _ge3, len(self._daily_rows)))
        except Exception:
            pass
        self.daily_table.clearSpans()
        self.daily_table.setRowCount(len(rows))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter
        for i, r in enumerate(rows):
            set_table_item(self.daily_table, i, COL_D_NAME, r['name'],
                           BC.TEXT_PRIMARY, bold=True, align=left)
            set_table_item(self.daily_table, i, COL_D_CODE, r['code'],
                           '#000000', bold=True, align=center)
            set_table_item(self.daily_table, i, COL_D_PRICE,
                           f"{r['price']:.2f}" if r.get('price') else '--',
                           '#000000', bold=True, align=right)
            set_table_item(self.daily_table, i, COL_D_PCT,
                           f"{r['pct']:+.2f}%" if r.get('pct') is not None else '--',
                           pct_color(r.get('pct', 0)), bold=True, align=right)
            # 建仓价
            tp = r.get('trigger_price', 0)
            set_table_item(self.daily_table, i, COL_D_TRIG_PRICE,
                           f"{tp:.2f}" if tp else '--',
                           '#2e7d32' if tp else '#999', bold=bool(tp), align=right)
            # 止盈价（建仓价 +3%，锁定浮盈；2025全年回测验证）
            tpx = r.get('take_profit', 0)
            set_table_item(self.daily_table, i, COL_D_TAKE_PROFIT,
                           f"{tpx:.2f}" if tpx else '--',
                           '#e65100' if tpx else '#999', bold=bool(tpx), align=right)
            # 题材：最近一次涨停原因（limit_up_reason_db）
            _th = r.get('theme', '') or '--'
            _th_item = QTableWidgetItem(_th)
            _th_item.setForeground(QColor('#6a1b9a'))
            _th_item.setTextAlignment(left)
            _th_item.setToolTip(_th)
            self.daily_table.setItem(i, COL_D_THEME, _th_item)
            set_table_item(self.daily_table, i, COL_D_PATTERN, r.get('pattern_name', ''),
                           '#00897b', bold=True, align=center)
            # 触发条件（原「结构状态」列的说明已删列，这里用 tooltip 保留）
            _tg_item = QTableWidgetItem(r.get('trigger_type', ''))
            _tg_item.setForeground(QColor('#1565c0'))
            _tg_item.setTextAlignment(left)
            _note = r.get('note', '')
            if _note:
                _tg_item.setToolTip(_note)
            self.daily_table.setItem(i, COL_D_TRIGGER, _tg_item)
            # 环境分：>=6 正常建仓(绿) / 3~5 谨慎(橙) / <=2 不建仓(红)
            _es = r.get('env_score')
            if _es is None:
                _etxt, _ecol = '--', '#999'
            else:
                _etxt = str(_es)
                if _es >= 6:
                    _ecol = '#2e7d32'
                elif _es >= 3:
                    _ecol = '#ef6c00'
                else:
                    _ecol = '#c62828'
            _e_item = QTableWidgetItem(_etxt)
            _e_item.setForeground(QColor(_ecol))
            _e_item.setTextAlignment(center)
            if _es is not None:
                _lv = '正常建仓' if _es >= 6 else ('谨慎' if _es >= 3 else '不建仓')
                _en = r.get('env_note', '')
                _e_item.setToolTip(('环境分 %s（%s）' % (_etxt, _lv)) + ('\n' + _en if _en else ''))
            self.daily_table.setItem(i, COL_D_ENV, _e_item)
            # 控盘：分数 + 提示短标签（悬停看完整文案）
            # 有提示显示成「98·候选 / 80·出货 / 98·洗盘」，颜色分档；无提示只显示分数。
            _cs = float(r.get('control_score') or 0)
            _nt = r.get('note') or ''
            _full_tt = (_nt.split('[控盘]')[-1].strip().replace('\n', ' ')
                        if '[控盘]' in _nt else '')
            # 短标签只能用「控盘提示」判定：优先读引擎写库的 ctrl_tag，旧库/快照没有
            # 该列时退回白名单比对（见 services.control_profile.ctrl_label）。
            # 不能拿整串 note 关键词反推 —— C4/C6 观察文案混在同一串里，会把只命中
            # 观察规则的股票染成绿色「候选」（2026-10-10 实测：72 分也显示 候选）。
            from services.control_profile import ctrl_label as _ctrl_label
            _clabel, _ccol = _ctrl_label(r.get('ctrl_tag') or '', _full_tt)
            if _clabel:
                _ctxt = '%d·%s' % (int(round(_cs)), _clabel)
            else:
                _ccol = '#9e9e9e'
                _ctxt = str(int(round(_cs))) if _cs else '--'
            _c_item = QTableWidgetItem(_ctxt)
            _c_item.setForeground(QColor(_ccol))
            _c_item.setTextAlignment(center)
            _c_item.setToolTip(('控盘分 %.1f（%s）' % (
                _cs, r.get('stage_guess') or '--'))
                + (('\n[控盘] ' + _full_tt) if _full_tt else ''))
            self.daily_table.setItem(i, COL_D_CTRL, _c_item)
            # 观察（五阶段短标签）：只是「结构状态」的事实标注，不是买入建议。
            # 一格一个颜色 -> 取该格里级别最高的（风险红 > 拉升橙 > 试盘金 > 中性蓝）。
            from services.control_profile import (obs_tag_pairs as _obs_pairs,
                                                  obs_stages as _obs_stages,
                                                  obs_tag_color as _obs_color_of)
            _pairs = _obs_pairs(
                probe_ok=bool(r.get('probe_ok')), c4_ok=bool(r.get('c4_ok')),
                c6_ok=bool(r.get('c6_ok')), brk_type=r.get('brk_type') or '',
                vreg_tags=r.get('vreg_tags') or '', dist_type=r.get('dist_type') or '',
                markup_type=r.get('markup_type') or '')
            if _pairs:
                _lv = [lv for _t, lv in _pairs]
                _ob_col = _obs_color_of(
                    'risk' if 'risk' in _lv else (
                        'warn' if 'warn' in _lv else (
                            'gold' if 'gold' in _lv else 'info')))
                _ob_txt = '·'.join(t for t, _lv2 in _pairs)
                _ob_tip = ('手法阶段：%s\n%s' % ('/'.join(_obs_stages(_pairs)) or '-',
                                               '\n'.join('· ' + t for t, _l in _pairs)))
                if r.get('note'):
                    _ob_tip += '\n\n' + str(r.get('note'))
            else:
                _ob_col, _ob_txt = '#9e9e9e', '—'
                _ob_tip = '本行没有任何阶段标注（建仓/试盘/洗盘/拉升/出货 均未命中）'
            _ob_item = QTableWidgetItem(_ob_txt)
            _ob_item.setForeground(QColor(_ob_col))
            _ob_item.setTextAlignment(left)
            _ob_item.setToolTip(_ob_tip)
            self.daily_table.setItem(i, COL_D_OBS, _ob_item)
            set_table_item(self.daily_table, i, COL_D_BASE_DATE, r.get('base_date', ''),
                           '#607d8b', align=center)

    @staticmethod
    def _daily_short_momentum(mom):
        """日K动能精简"""
        if not mom or mom == '暂无':
            return '--'
        out = []
        for kw, short in [
            ('日线底背离', '底背离'), ('日线顶背离', '顶背离'),
            ('底背离雏形', '底背离'), ('顶背离雏形', '顶背离'),
            ('TD低9', 'TD9'), ('TD高9', 'TD9'),
            ('缩量', '缩量'), ('多头排列', '多头'), ('空头排列', '空头'),
        ]:
            if kw in mom:
                out.append(short)
        return '/'.join(out) if out else '--'

    @staticmethod
    def _daily_short_action(act):
        """日K操作建议精简"""
        if not act:
            return '观望'
        if '止损' in act or '清仓' in act:
            return '清仓'
        if '减半' in act or '减仓' in act:
            return '减仓'
        if '重仓' in act:
            return '重仓'
        if '加仓' in act:
            return '加仓'
        if '试仓' in act:
            return '试仓'
        if '等企稳' in act:
            return '等确认'
        if '持有' in act:
            return '持有'
        if '禁' in act:
            return '禁入'
        return act[:8]   # 兜底：放宽到 8 字（原来 6 字，容易把词切断）
