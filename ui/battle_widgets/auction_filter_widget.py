# -*- coding: utf-8 -*-
"""
⚡ 竞价（作战中控台右上模块）
- 9:25 集合竞价结束后，用全市场快照 + 本地K线缓存 + 题材匹配，输出当日具备爆发潜力的标的排序
- 基础过滤：ST / 一字新高 / 高位股 / 高开>7% / 竞价换手率 0.5%~15%（不限制流通市值）
- 量价因子：高开幅度、竞价量比、情绪值(换手×量比)、竞价量能占比、竞价分时形态(代理)
- 题材因子：concept_matcher 匹配 + 题材热度聚合 + Top3加权 + 多题材协同加分
- 综合评分：量价分*0.72 + 题材分*0.28 - 风险扣分，降序 Top20

【V6 升级：竞价追踪模块】
- 右键菜单：今日竞价表「📌 添加到竞价追踪」/ 竞价追踪表「❌ 从竞价追踪中移除」
- 新增「题材」列（名称与代码之间），数据来自 get_last_limit_up_reason
- 盈亏重构：P0=首次加入基准价(base_price)；累计盈亏=(实时价-P0)/P0；5/15/30日盈亏按 T+N 收盘价
- 高性能架构：仅在追踪Tab启动 QTimer(3s) 节流；实时行情与盈亏计算放 QThread 后台；
  内存缓存 self.track_list；增量 setText 只更新变化单元格
"""
import os
import sys
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QButtonGroup, QTableWidgetItem, QMenu, QHeaderView,
)
from PyQt6.QtGui import QColor, QBrush

from .base import (
    fetch_ctrl_cached,
    BattleModuleBase, make_table, set_table_item, CTRL_COL_TITLE,
    pct_color, BC, HeaderSorter,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 交易日历：休市日不扫描、不创建当天竞价记录（复盘模式保留最近交易日数据）
from utils import trade_calendar as _trade_cal  # noqa: E402

# 输出列（9列，末列为发现时间）
HEADER_LABELS = [
    '股票名称', '股票代码', '综合得分', '竞价涨幅',
    '当前涨幅', '竞价金额', '当前金额', '强势题材',
    CTRL_COL_TITLE,
]  # [UI-COL] 删竞价换手率/分时形态/风险标记，加当前涨幅/竞价金额/当前金额
COL_CTRL = 8
COL_FOUND_TIME = None  # [UI-DEL] 发现时间列已删，保留常量占位防止引用报错

# 竞价追踪表表头（9列）：
# 筛选日期|股票名称|题材|股票代码|竞价金额(P0)|当前实时价|5日盈亏%|30日盈亏%|累计盈亏%
TRACK_HEADERS = [
    '筛选日期', '股票名称', '题材', '股票代码', '竞价金额(P0)',
    '当前实时价', '5日盈亏%', '30日盈亏%', '累计盈亏%', CTRL_COL_TITLE,
]
TRACK_COL_N = 10
# 追踪表列索引常量
C_DATE, C_NAME, C_THEME, C_CODE, C_P0 = 0, 1, 2, 3, 4
C_NOW, C_P5, C_P30, C_CUM = 5, 6, 7, 8
C_TRACK_CTRL = 9

# 主板 + 创业板：沪市 600/601/603/605，深市 000/001/002/003，创业板 300/301
# 剔除科创板(688)、北交所(8/4/9开头)
MAIN_BOARD_PREFIXES = ('600', '601', '603', '605', '000', '001', '002', '003',
                       '300', '301')


def _is_main_a_share(code: str) -> bool:
    """保留沪深A股主板 + 创业板，剔除科创板/北交所"""
    if not code or len(code) != 6 or not code.isdigit():
        return False
    return code.startswith(MAIN_BOARD_PREFIXES)


def _is_st(name: str) -> bool:
    nm = (name or '').upper()
    return ('ST' in nm) or ('退' in nm)


# [CYB-GATE] 创业板是 20cm 板，主板是 10cm 板，涨停幅度比 = 2.0。
# 竞价的「高开幅度」「换手上限」「最优高开区间」按这个比例等比缩放，两侧口径才可比。
#   高开区间   主板 2~7%     → 创业板 4~14%
#   换手上限   主板 15%      → 创业板 30%（下限 0.5% 不变，那是"有没有人交易"）
#   高开分满分 主板 3~4%     → 创业板 6~8%
CYB_PREFIXES = ('300', '301')
GAP_BAND_MAIN = (2.0, 7.0)
GAP_BAND_CYB = (4.0, 14.0)
TURNOVER_MAX_MAIN = 15.0
TURNOVER_MAX_CYB = 30.0
GAP_SCORE_MAIN = (3.0, 4.0, 2.0, 5.0)    # 满分下限/上限、次优下限/上限
GAP_SCORE_CYB = (6.0, 8.0, 4.0, 10.0)


def _is_cyb(code) -> bool:
    """是否创业板（20cm 板）"""
    return str(code or '').startswith(CYB_PREFIXES)


def _gap_band(code):
    """按板性返回允许的高开幅度区间 (下限, 上限)，单位 %"""
    return GAP_BAND_CYB if _is_cyb(code) else GAP_BAND_MAIN


def _turnover_max(code) -> float:
    """按板性返回集合竞价换手率上限，单位 %"""
    return TURNOVER_MAX_CYB if _is_cyb(code) else TURNOVER_MAX_MAIN


def _gap_score_bands(code):
    """按板性返回高开分区间 (满分下限, 满分上限, 次优下限, 次优上限)"""
    return GAP_SCORE_CYB if _is_cyb(code) else GAP_SCORE_MAIN


# ================================================================
# 后台行情 Worker（QThread）：实时行情获取与盈亏计算全部在本线程内完成
# 线程安全：worker 只在它自己的线程里执行 run_fetch；主线程通过信号请求、
# worker 通过 quotes_ready 信号回传，二者不共享可变状态，天然线程安全。
# ================================================================
class _QuoteFetchWorker(QObject):
    """实时行情拉取 Worker，moveToThread 到独立 QThread 运行"""

    # 回传 {code: float_price}，从 worker 线程 emit，自动排队到主线程
    quotes_ready = pyqtSignal(object)

    def run_fetch(self, codes):
        """在后台线程内批量拉实时价，算完 emit。codes 为 list[str]"""
        prices = {}
        try:
            from utils.http_market_data import get_realtime_quotes_http
            q = get_realtime_quotes_http(list(codes)) or {}
            for c, v in q.items():
                try:
                    p = float((v or {}).get('price') or 0)
                    if p > 0:
                        prices[c] = p
                except Exception:
                    continue
        except Exception as e:
            print(f'[竞价追踪] 实时行情拉取失败: {e}', flush=True)
        self.quotes_ready.emit(prices)


class AuctionFilterWidget(BattleModuleBase):
    # 点击表格"股票名称"单元格 -> 通知主窗口跳转个股分析(code, name)
    stock_clicked = pyqtSignal(str, str)
    """⚡ 竞价"""

    # 跨线程请求行情信号：主线程 emit(codes)，自动排队到 worker 线程执行 run_fetch
    sig_request_quotes = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__('⚡ 竞价', parent)
        self._rows = []
        # 当日发现持久化：发现时间列 + 盘中筛到的个股当日保留不清空
        self._found_time = {}       # {code: 'HH:MM'}
        self._persist_rows = {}     # {code: row_dict}
        self._persist_date = None   # 'YYYY-MM-DD'
        self._snap_saved_at = ''    # 当前展示数据的快照写入时间（用于状态栏明示是否实时）
        # 发现时间持久化到 DuckDB：程序重启后恢复今天的 09:25 记录
        from services.discovery_time_db import MOD_AUCTION
        self._db_module = MOD_AUCTION
        self._load_found_time_from_db()
        # 竞价追踪持久化：独立 DuckDB 库（写入），kline_cache 只读算收益
        # 内存缓存：只在添加/移除时操作数据库，盘中计算纯用内存
        self.track_list = []        # [{trade_date,code,name,theme,base_price,open_price,cur_price,r5,r30,cum_pnl}]
        self._tracking_db = os.path.join(
            PROJECT_ROOT, 'data', 'cache', 'auction_tracking.duckdb')
        # 高性能架构：追踪专用定时器(3s) + 后台行情线程（按需启停）
        self._track_timer = None
        self._quote_thread = None
        self._quote_worker = None
        self._build_content()
        self.update_time_label.hide()  # 隐藏标题栏右侧状态行（休市/更新时间），set_status 后台照常更新，不留占位
        QTimer.singleShot(150, self.refresh)
        # 9:25 后每分钟自动刷新一次；盘中手动刷新
        self.start_refresh(60000)

    # ---------------------------------------------------------------
    # UI 构建
    # ---------------------------------------------------------------
    def _build_content(self):
        # ---- 标题栏右侧添加 Tab 切换按钮（今日竞价 / 竞价追踪）----
        self._setup_tab_buttons()

        # ===== Tab1 容器：今日竞价 TOP12 表格 =====
        self._today_widget = QWidget()
        today_layout = QVBoxLayout(self._today_widget)
        today_layout.setContentsMargins(0, 0, 0, 0)
        today_layout.setSpacing(0)

        self.table = make_table(9, HEADER_LABELS, min_row_height=24)
        widths = [86, 70, 60, 75, 75, 80, 80, 260, 78]  # [UI-W] 强势题材加宽，末列控盘
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        # [UI-LAYOUT] 强势题材列(6)拉伸吃剩余空间
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        # 今日竞价表：右键「📌 添加到竞价追踪」
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_today_context_menu)
        today_layout.addWidget(self.table, 1)
        # 仅点击"股票名称"列跳转个股分析，其他列不跳转
        self.table.cellClicked.connect(self._on_today_cell_clicked)
        self.content_layout.addWidget(self._today_widget, 1)

        # ===== Tab2 容器：竞价追踪历史表格 =====
        self._track_widget = QWidget()
        track_layout = QVBoxLayout(self._track_widget)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)
        self.track_table = make_table(TRACK_COL_N, TRACK_HEADERS, min_row_height=24)
        track_widths = [92, 80, 150, 70, 86, 86, 76, 76, 84, 78]
        for i, w in enumerate(track_widths):
            self.track_table.setColumnWidth(i, w)
        # 控盘列插到末尾后，改成「累计盈亏」列吃剩余宽度
        _th = self.track_table.horizontalHeader()
        _th.setStretchLastSection(False)
        _th.setSectionResizeMode(C_CUM, QHeaderView.ResizeMode.Stretch)
        # 竞价追踪表：右键「❌ 从竞价追踪中移除」
        self.track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self._on_track_context_menu)
        track_layout.addWidget(self.track_table, 1)
        # 仅点击"股票名称"列跳转个股分析，其他列不跳转
        self.track_table.cellClicked.connect(self._on_track_cell_clicked)
        self.content_layout.addWidget(self._track_widget, 0)

        # 默认显示“今日竞价”，隐藏“竞价追踪”
        self._track_widget.setVisible(False)

        self.sorter = HeaderSorter(
            self.table,
            keys={
                0: lambda r: r['name'],
                2: lambda r: r['score'],
                3: lambda r: r['gap'],
                4: lambda r: r['jj_turnover'],
                8: lambda r: ((r.get('ctrl') or {}).get('score') or 0),
            },
            getter=lambda: self._rows,
            render=self._render_rows,
        )
        # 竞价追踪表列头排序：日期/题材/代码/P0/5/15/30日盈亏/累计盈亏
        # 未到观察期（None）的盈亏排序时放到最后
        _sort_num = lambda v: v if v is not None else -1e9
        self.track_sorter = HeaderSorter(
            self.track_table,
            keys={
                C_DATE: lambda r: r['trade_date'],
                C_NAME: lambda r: r['name'],
                C_THEME: lambda r: r.get('theme', '--'),
                C_CODE: lambda r: r['code'],
                C_P0: lambda r: r.get('base_price', 0),
                C_P5: lambda r: _sort_num(r['r5']),
                C_P30: lambda r: _sort_num(r['r30']),
                C_CUM: lambda r: _sort_num(r.get('cum_pnl')),
            },
            getter=lambda: self.track_list,
            render=self._render_tracking,
        )

    # ---------------------------------------------------------------
    # Tab 切换（参考 ATR做T助手：QButtonGroup 互斥 + checkable 按钮）
    # ---------------------------------------------------------------
    # ============================================================
    # 点击股票名称 -> 跳转个股分析
    # ============================================================
    def _on_today_cell_clicked(self, row, col):
        """今日竞价：仅点击"股票名称"单元格跳转，其他列不跳转"""
        if col != 0:
            return
        it = self.table.item(row, 1)
        code = it.text() if it else ''
        nit = self.table.item(row, 0)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    def _on_track_cell_clicked(self, row, col):
        """竞价追踪：仅点击"股票名称"单元格跳转，其他列不跳转"""
        if col != C_NAME:
            return
        it = self.track_table.item(row, C_CODE)
        code = it.text() if it else ''
        nit = self.track_table.item(row, C_NAME)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    def _setup_tab_buttons(self):
        """在标题栏 title_label 右侧插入 [今日竞价] / [竞价追踪] 两个 Tab 按钮"""
        # base.py 中 _card_frame 的主 layout 第一个 item 就是 title_bar (QHBoxLayout)
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

        self._btn_today = QPushButton('今日竞价')
        self._btn_today.setCheckable(True)
        self._btn_today.setStyleSheet(self._tab_style_checked)
        self._btn_today.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_today, 0)

        self._btn_track = QPushButton('竞价追踪')
        self._btn_track.setCheckable(True)
        self._btn_track.setStyleSheet(self._tab_style_normal)
        self._btn_track.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_group.addButton(self._btn_track, 1)

        self._btn_today.setChecked(True)

        # 插入位置：title_label(0) 之后、stretch 之前
        title_bar_layout.insertWidget(1, self._btn_today)
        title_bar_layout.insertWidget(2, self._btn_track)

        self._tab_group.idClicked.connect(self._switch_tab)

    def _switch_tab(self, idx):
        """切换 Tab：0=今日竞价（TOP12表格），1=竞价追踪（历史收益表格）。
        按需计算：仅进入追踪Tab才启动实时定时器与后台线程；切走立即停止释放CPU。"""
        if idx == 0:
            self._today_widget.setVisible(True)
            self._track_widget.setVisible(False)
            self._btn_today.setStyleSheet(self._tab_style_checked)
            self._btn_track.setStyleSheet(self._tab_style_normal)
            # 切回今日竞价：停止追踪定时器，暂停实时计算
            self._stop_track_timer()
        else:
            self._today_widget.setVisible(False)
            self._track_widget.setVisible(True)
            self._btn_today.setStyleSheet(self._tab_style_normal)
            self._btn_track.setStyleSheet(self._tab_style_checked)
            # 异步加载历史追踪数据，不阻塞 UI
            self.refresh_tracking()

    # ---------------------------------------------------------------
    # 异步入口
    # ---------------------------------------------------------------
    def _load_found_time_from_db(self, trade_day=None):
        """程序启动 / 跨交易日时从 DuckDB 加载指定交易日的发现时间到内存。
        休市日加载最近交易日记录，保证复盘模式时间正确。"""
        mod = getattr(self, '_db_module', None)
        if not mod:
            return
        try:
            from services import discovery_time_db as db
            day = trade_day or datetime.now().strftime('%Y-%m-%d')
            self._found_time = db.load_today(mod, today=day)
            self._persist_date = day
        except Exception as e:
            print(f'[作战中台] 加载发现时间持久化失败({mod}): {e}', flush=True)

    def _check_date_reset(self):
        """跨交易日自动清空持久化数据（交易日判断用真实日历）；
        休市日不清空，保留最近交易日的复盘数据。"""
        now = datetime.now()
        if _trade_cal.is_trading_day(now):
            target = now.strftime('%Y-%m-%d')
        else:
            # 休市日：沿用最近交易日，不重置
            target = _trade_cal.get_latest_trading_date(now)
            if getattr(self, '_persist_date', None) == target:
                return
            self._persist_rows = {}
            self._found_time = {}
            self._persist_date = target
            self._load_found_time_from_db(target)
            return
        if getattr(self, '_persist_date', None) != target:
            self._persist_rows = {}
            self._found_time = {}
            self._persist_date = target
            # 跨天后从库里把该交易日已有的发现时间捞回来（重启不丢时间）
            self._load_found_time_from_db(target)

    # 时间窗口常量
    from datetime import time as _dt_time
    AUCTION_START = _dt_time(9, 15)
    AUCTION_END   = _dt_time(9, 30)
    TAIL_START    = _dt_time(14, 57)
    TAIL_END      = _dt_time(15, 0)

    def refresh(self):
        now = datetime.now()
        # 1. 非交易日：只读最近快照，不清空
        if not _trade_cal.is_trading_day(now):
            # [FIX] latest 必须无条件先算好：原写法只在 self._rows 为空的分支里赋值，
            # 当 _rows 已有数据时引用 latest 会抛 UnboundLocalError 导致刷新中断
            latest = _trade_cal.get_latest_trading_date(now)
            if not self._rows:
                self._restore_auction_snapshot(latest)
            if self._rows:
                self.title_label.setText(
                    f'⚡ 竞价 TOP{len(self._rows)}（{latest} 复盘）')
                self.set_status(f'休市 · 数据日期 {latest} · 复盘 · {len(self._rows)}条')
            else:
                self.title_label.setText('⚡ 竞价')
                self.set_status(f'休市 · 最近交易日 {latest} 无竞价记录')
            return

        # 2. 判断当前阶段
        t = now.time()
        if self.AUCTION_START <= t <= self.AUCTION_END:
            phase = 'auction'
        elif self.TAIL_START <= t <= self.TAIL_END:
            phase = 'tail'
        else:
            phase = 'snapshot'

        # 3. 早盘竞价：拉新数据，覆盖
        if phase == 'auction':
            # [FIX] 竞价阶段细分提示：9:25 前新浪不发布竞价价，必须让用户看到"在跑但没价"
            self.set_status('集合竞价 · %s · 扫描中...' % self._auction_stage())
            self.run_async(self._fetch_auction, self._on_loaded, self._on_failed)
            return

        # 4. 尾盘：拉尾盘数据，合并去重加"尾盘"标签
        if phase == 'tail':
            self.set_status('扫描尾盘数据...')
            self.run_async(self._fetch_auction, self._on_loaded_tail, self._on_failed)
            return

        # 5. snapshot：9:30~14:57 或 15:00后，只读快照不拉新数据
        if not self._rows:
            today = now.strftime('%Y-%m-%d')
            if not self._restore_auction_snapshot(today):
                latest = _trade_cal.get_latest_trading_date(now)
                if latest != today:
                    self._restore_auction_snapshot(latest)
        if self._rows:
            self.title_label.setText(
                f'⚡ 竞价 TOP{len(self._rows)}（竞价已结束·复盘）')
            _snap_t = getattr(self, '_snap_saved_at', '') or '--'
            self.set_status(
                '竞价已结束 · 名单冻结(%s) · %d只 · 行情实时刷新中'
                % (_snap_t, len(self._rows)))
            # [FIX-实时] 竞价结束只冻结"入选名单"，不冻结行情。
            # 原实现此处直接结束，_render_rows 及其末尾的行情刷新永不执行，
            # 表格"当前涨幅/当前价"会永远停在 9:29 的快照值（死数据）。
            self._fetch_realtime_from_tencent()
        else:
            self.title_label.setText('⚡ 竞价')
            self.set_status('今日竞价未开始或无数据')

    def _save_auction_snapshot(self):
        """把当天真实竞价筛选结果保存到交易日快照（供休市/重启复盘恢复）。"""
        try:
            from services import intraday_snapshot as snap
            now = datetime.now()
            if _trade_cal.is_trading_day(now):
                td = now.strftime('%Y-%m-%d')
            else:
                td = _trade_cal.get_latest_trading_date(now)
            snap.save_section(td, 'auction', {
                'rows': self._rows,
                'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'schema_version': 2,  # [UI-COL] v2: 加 cur_pct/jj_amount/cur_amount/时间戳
            })
        except Exception:
            pass

    def _restore_auction_snapshot(self, trading_date):
        """休市复盘：从最近交易日快照恢复当天真实竞价筛选结果。
        v2快照含cur_pct/jj_amount/cur_amount；v1旧快照兼容补默认值。"""
        try:
            from services import intraday_snapshot as snap
            data = snap.load_section(trading_date, 'auction') or {}
            rows = data.get('rows') or []
            if not rows:
                return False
            self._snap_saved_at = data.get('saved_at') or ''
            ver = data.get('schema_version', 1)
            # [UI-COL] 旧v1快照兼容：cur_pct不补gap（gap是开盘涨幅≠当前涨幅），显示--
            if ver < 2:
                for r in rows:
                    if 'cur_pct' not in r:
                        r['cur_pct'] = None  # None=显示--，不用gap糊弄
                    if 'jj_amount' not in r:
                        r['jj_amount'] = 0.0
                    if 'cur_amount' not in r:
                        r['cur_amount'] = 0.0
                    if 'jj_amount_time' not in r:
                        r['jj_amount_time'] = ''
                    if 'cur_time' not in r:
                        r['cur_time'] = ''  # 空=不标快照
                self._rows = rows
                self._render_rows()
                self.ctrl_fill_and_async(self._rows, self._render_rows)
                self.set_status(
                    f'休市 · 数据日期 {trading_date} · 模式：复盘（旧快照v1，金额字段缺失）· {len(rows)}条')
                return True
            self._rows = rows
            self._render_rows()
            self.ctrl_fill_and_async(self._rows, self._render_rows)
            self.set_status(
                f'休市 · 数据日期 {trading_date} · 模式：复盘 · {len(rows)}条')
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------
    # 数据采集与打分（后台线程）
    # ---------------------------------------------------------------
    @staticmethod
    def _auction_stage():
        """当前集合竞价阶段文字（9:25 前新浪不发布竞价价，用于状态栏提示）"""
        hm = datetime.now().hour * 60 + datetime.now().minute
        if hm < 9 * 60 + 20:
            return '可撤单阶段(9:15~9:20)'
        if hm < 9 * 60 + 25:
            return '不可撤单阶段(9:20~9:25)'
        if hm < 9 * 60 + 26:
            return '9:25出竞价价'
        if hm < 9 * 60 + 30:
            return '等待开盘(9:25~9:30)'
        return '已过竞价窗口'

    # ---------------------------------------------------------------
    @staticmethod
    def _fetch_tencent_rank(fun=None):
        """[腾讯兜底源] 新浪在 9:25 出竞价价前整页 changepercent=0，此时用本源。

        接口：https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList
              已实测参数：sort_type=priceRatio&direct=down = 涨幅降序；
              count 上限 200（300/500 报错）；offset 分页连续且单调递减。
        字段映射：
              zxj=最新价(竞价阶段即竞价价)  zd=涨跌额  zdf=涨跌幅%
              hsl=换手率%  lb=量比  volume=成交量(手)  turnover=成交额(万元)
              ltsz=流通市值(亿)  code 形如 sh600519 / sz000001
        注意：本接口不返回"今开"。竞价阶段现价即竞价价，故 open 用 zxj 顶替，
              gap 直接取 zdf，与 (open-昨收)/昨收 等价。
        返回：与新浪路径同结构的 raw 列表；无有效数据返回 []。
        """
        import json as _json
        from utils.http_market_data import http_get_with_retry

        items = []
        for off in range(0, 600, 200):          # 最多 3 页 × 200 = 600 只
            url = ('https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?'
                   'board_code=aStock&sort_type=priceRatio&direct=down'
                   '&offset=%d&count=200' % off)
            try:
                text = http_get_with_retry(url, encoding='utf-8',
                                           referer='https://gu.qq.com', timeout=10)
                arr = ((_json.loads(text) if text else {}) or {}).get('data', {})                         .get('rank_list') or []
            except Exception as e:
                print('[竞价] 腾讯涨幅榜 offset=%d 失败: %s' % (off, e), flush=True)
                break
            if not arr:
                break
            items.extend(arr)
            try:
                if float(arr[-1].get('zdf') or 0) < 1.5:
                    break
            except Exception:
                pass

        if fun is not None:
            fun['raw'] = len(items)
            fun['source'] = 'tencent'
        if not items:
            return []

        # 有效性校验：腾讯在竞价前也可能返回全 0，全 0 视为无数据，不污染筛选
        _nz = 0
        for it in items:
            try:
                if float(it.get('zdf') or 0) != 0:
                    _nz += 1
            except Exception:
                pass
        if _nz == 0:
            if fun is not None:
                fun['source'] = 'tencent_nodata'
            return []

        now = datetime.now()
        _in_auction = (now.hour == 9 and 25 <= now.minute <= 29)
        raw = []
        for it in items:
            code_raw = str(it.get('code', '') or '').strip()
            name = str(it.get('name', '') or '').strip()
            code = code_raw[2:] if (len(code_raw) > 2 and
                                    code_raw[:2] in ('sh', 'sz', 'bj')) else code_raw
            if not _is_main_a_share(code):
                continue
            if _is_st(name):
                continue
            if fun is not None:
                fun['main'] += 1
            try:
                price = float(it.get('zxj') or 0)
                zd = float(it.get('zd') or 0)
                gap = float(it.get('zdf') or 0)
                jj_turnover = float(it.get('hsl') or 0)
                vol_lots = float(it.get('volume') or 0)
                amt_wan = float(it.get('turnover') or 0)
                lb = float(it.get('lb') or 0)
                circ_mv_yi = float(it.get('ltsz') or 0)
            except Exception:
                continue
            last_close = price - zd
            if last_close <= 0 or price <= 0:
                continue
            if fun is not None:
                fun['px'] += 1
            _glo, _ghi = _gap_band(code)          # [CYB-GATE] 创业板 4~14%
            if gap > _ghi or gap < _glo:
                continue
            if fun is not None:
                fun['gap'] += 1
            _tmax = _turnover_max(code)            # [CYB-GATE] 创业板 30%
            if jj_turnover < 0.5 or jj_turnover > _tmax:
                continue
            if fun is not None:
                fun['turn'] += 1
            amount_yuan = amt_wan * 1e4
            raw.append({
                'code': code, 'name': name,
                'price': price, 'open': price, 'last_close': last_close,
                'gap': gap,
                'cur_pct': gap,
                'jj_amount': (amount_yuan / 1e8) if _in_auction else 0.0,
                'cur_amount': amount_yuan / 1e8,
                'jj_amount_time': now.strftime('%H:%M:%S') if _in_auction else '',
                'cur_time': now.strftime('%H:%M:%S'),
                'jj_vol_lots': vol_lots,
                'jj_vol_shares': vol_lots * 100.0,      # 手 -> 股，与 kline_cache 口径一致
                'jj_turnover': jj_turnover,
                'em_vol_ratio': lb,                     # 腾讯量比（新浪此字段恒为 0）
                'circ_mv_yi': circ_mv_yi,
                'industry': '',
                'concepts_raw': '',
                'src': 'tencent',
            })
        return raw

    # ---------------------------------------------------------------
    @staticmethod
    def _fetch_auction():
        # [V2.4] 弃用东财clist（竞价高峰限流），改用新浪全市场涨幅排行
        import json as _json
        from utils.http_market_data import http_get_with_retry

        all_items = []
        _all_zero = False   # [FIX] 新浪 9:25 前返回全 0，第 1 页即可判定
        for pn in range(1, 16):  # 最多15页*80=1200只
            url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'Market_Center.getHQNodeData?page=%d&num=80&sort=changepercent&asc=0'
                   '&node=hs_a&symbol=&_s_r_a=auto' % pn)
            try:
                text = http_get_with_retry(url, encoding='gbk',
                                           referer='https://finance.sina.com.cn', timeout=10)
                arr = _json.loads(text) if text else []
            except Exception as e:
                print('[竞价] 新浪第%d页失败: %s' % (pn, e), flush=True)
                break
            if not arr:
                break
            all_items.extend(arr)
            try:
                _last_cp = float(arr[-1].get('changepercent', 0))
            except Exception:
                _last_cp = 0.0
            # [FIX] 第 1 页若整页涨幅全 0，说明此刻新浪没有竞价数据，
            # 直接退出，避免再打 14 次无效请求（并让状态栏给出准确原因）
            if pn == 1:
                _nz = 0
                for _it in arr:
                    try:
                        if float(_it.get('changepercent') or 0) != 0:
                            _nz += 1
                    except Exception:
                        pass
                if _nz == 0:
                    _all_zero = True
                    break
            if _last_cp < 1.5:
                break

        fun = {'raw': len(all_items), 'main': 0, 'px': 0, 'gap': 0, 'turn': 0,
               'final': 0, 'source': 'sina'}

        # [腾讯兜底] 新浪在 9:25 出竞价价前整页 changepercent=0（不发布竞价数据），
        # 此时改用腾讯 A 股涨幅榜 priceRatio 取数；新浪有数据时永远优先用新浪，口径不变。
        raw = []
        if _all_zero or not all_items:
            # [口径保护] 腾讯 zdf 是"当前涨幅"，新浪路径 gap 是"开盘涨幅"，
            # 9:30 后两者不是一回事，故腾讯兜底只在 9:25 前启用，绝不跨口径。
            _hm = datetime.now().hour * 60 + datetime.now().minute
            _pre_25 = _hm < 9 * 60 + 25
            if _pre_25:
                raw = AuctionFilterWidget._fetch_tencent_rank(fun)
            if not raw:
                if _pre_25:
                    _note = ('9:25出竞价价前无竞价数据（新浪无价·腾讯无价，当前：%s）'
                             % AuctionFilterWidget._auction_stage())
                else:
                    _note = ('新浪源无数据且已过9:25，不做跨口径兜底（当前：%s）'
                             % AuctionFilterWidget._auction_stage())
                return {'rows': [], 'funnel': fun, 'note': _note}

        for it in ([] if raw else all_items):
            code = str(it.get('code', '') or '').strip()
            name = str(it.get('name', '') or '').strip()
            if not _is_main_a_share(code):
                continue
            if _is_st(name):
                continue
            fun['main'] += 1
            try:
                last_close = float(it.get('settlement') or 0)
                open_px = float(it.get('open') or 0)
                price = float(it.get('trade') or open_px)
                cur_pct = float(it.get('changepercent') or 0)
                jj_vol_shares = float(it.get('volume') or 0)  # 股
                jj_turnover = float(it.get('turnoverratio') or 0)  # %
                amount_yuan = float(it.get('amount') or 0)
                # 新浪不直接给量比，用换手率*换手排名粗估，后面_enrich_with_kline会覆盖
                em_vol_ratio = 0.0
                circ_mv_yi = float(it.get('nmc') or 0)  # 流通市值(万)
                circ_mv = circ_mv_yi * 1e4
            except Exception:
                continue
            if last_close <= 0 or open_px <= 0:
                continue
            fun['px'] += 1
            gap = (open_px - last_close) / last_close * 100.0

            _glo, _ghi = _gap_band(code)          # [CYB-GATE] 创业板 4~14%
            if gap > _ghi or gap < _glo:
                continue
            fun['gap'] += 1
            _tmax = _turnover_max(code)            # [CYB-GATE] 创业板 30%
            if jj_turnover < 0.5 or jj_turnover > _tmax:
                continue
            fun['turn'] += 1

            _now = datetime.now()
            _in_auction = (_now.hour == 9 and 25 <= _now.minute <= 29)
            _jj_amt = (amount_yuan / 1e8) if _in_auction else 0.0
            raw.append({
                'code': code, 'name': name,
                'price': price, 'open': open_px, 'last_close': last_close,
                'gap': gap,
                'cur_pct': cur_pct,
                'jj_amount': _jj_amt,
                'cur_amount': amount_yuan / 1e8,
                'jj_amount_time': _now.strftime('%H:%M:%S') if _in_auction else '',
                'cur_time': _now.strftime('%H:%M:%S'),
                'jj_vol_lots': jj_vol_shares / 100.0,
                'jj_vol_shares': jj_vol_shares,
                'jj_turnover': jj_turnover,
                'em_vol_ratio': em_vol_ratio,
                'circ_mv_yi': circ_mv_yi,
                'industry': '',
                'concepts_raw': '',
            })

        if not raw:
            return {'rows': [], 'funnel': fun,
                    'note': '竞价0只入选（候选%d→主板%d→缺口%d→换手%d）'
                            % (fun['raw'], fun['main'], fun['gap'], fun['turn'])}

        # 3) 批量从 kline_cache 取近5日均量、昨量、60日最低
        AuctionFilterWidget._enrich_with_kline(raw)

        # 4) 题材匹配 + 题材热度聚合
        AuctionFilterWidget._enrich_with_themes(raw)

        # 4.5) 强势题材：优先取最近一次涨停原因，fallback 概念标签
        AuctionFilterWidget._enrich_with_limit_up_reason(raw)

        # 5) 量价打分 + 题材打分 + 综合排序
        rows = []
        for r in raw:
            bp, risk, shape = AuctionFilterWidget._score_volume_price(r)
            # 直接剔除次新股（上市不足60个交易日）和高位风险股（距60日最低涨幅>100%）
            if r.get('is_new_stock', False):
                continue
            if r.get('high_pos', False):
                continue
            # [NEW] 硬过滤：现价低于MA20剔除
            ma20 = r.get('ma20', 0) or 0
            cur_price = r.get('price', 0) or 0
            if ma20 > 0 and cur_price < ma20:
                continue
            tp = AuctionFilterWidget._score_theme(r)
            total = bp * 0.72 + tp * 0.28 - risk
            r['score'] = round(total, 1)
            r['shape'] = shape
            r['risk_flag'] = risk
            rows.append(r)

        rows.sort(key=lambda x: -x['score'])
        fun['final'] = len(rows)
        return {'rows': rows[:20], 'funnel': fun, 'note': ''}

    @staticmethod
    def _enrich_with_kline(raw):
        """从 kline_cache.duckdb 批量取：近5日均量(股)、昨量(股)、60日最低、上市天数"""
        try:
            import duckdb
        except Exception:
            for r in raw:
                r.update(avg_vol5=0.0, ref_vol=0.0, low60=0.0, hist_days=999)
            return
        db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
        if not os.path.exists(db_path):
            for r in raw:
                r.update(avg_vol5=0.0, ref_vol=0.0, low60=0.0, hist_days=999)
            return
        try:
            con = duckdb.connect(db_path, read_only=True)
            codes = [r['code'] for r in raw]
            # 一次取回所有候选股近 70 个交易日
            placeholders = ','.join(['?'] * len(codes))
            rows_db = con.execute(
                f"SELECT code, date, low, close, volume FROM kline_cache "
                f"WHERE code IN ({placeholders}) ORDER BY code, date DESC",
                codes
            ).fetchall()
            con.close()
        except Exception as e:
            print(f'[集合竞价] kline_cache读取失败: {e}', flush=True)
            for r in raw:
                r.update(avg_vol5=0.0, ref_vol=0.0, low60=0.0, hist_days=999)
            return

        # 按 code 分组
        by_code = {}
        for code, date, low, close, vol in rows_db:
            by_code.setdefault(code, []).append((date, float(low or 0), float(close or 0), float(vol or 0)))

        for r in raw:
            recs = by_code.get(r['code'], [])
            # recs 已按 date DESC。最新一条可能是今日（盘中），历史统计取 recs[1:] 即前一交易日起
            hist = recs[1:] if recs else []
            hist_days = len(recs)
            # 近5日均量（股）
            last5 = hist[:5]
            vols = [v for _, _, _, v in last5 if v and v > 0]
            avg_vol5 = sum(vols) / len(vols) if vols else 0.0
            # 昨量 = 最近一个完整交易日成交量
            ref_vol = hist[0][2] if hist else 0.0
            # 60日最低
            last60 = hist[:60]
            lows = [lo for _, lo, _, _ in last60 if lo and lo > 0]
            low60 = min(lows) if lows else 0.0
            # [NEW] MA20：近20日收盘均价
            last20 = hist[:20]
            closes = [c for _, _, c, _ in last20 if c and c > 0]
            ma20 = sum(closes) / len(closes) if len(closes) >= 20 else 0.0
            r.update(avg_vol5=avg_vol5, ref_vol=ref_vol, low60=low60, hist_days=hist_days, ma20=ma20)

    @staticmethod
    def _enrich_with_themes(raw):
        """题材因子：用东财 f103 概念标签 + 行业(f100)，剔除宽泛标签，聚合题材热度"""
        # 宽泛标签黑名单（太宽泛、无区分度，剔除）
        BLACKLIST = {
            '融资融券', '深股通', '沪股通', 'MSCI', '富时罗素',
            '基金重仓', '机构重仓', '预盈预亏', '年报预增', '高送转预期',
            '参股金融', '上证180', '沪深300', '中证500', '中证1000',
            '微盘股', '小盘股', '大盘蓝筹', '举牌', 'AB股', 'B股',
            '转融券标的', '证金持股', '汇金概念', '社保重仓', 'QFII重仓',
            '昨日涨停', '昨日连板', '破净股', '含H股', 'AH股',
        }
        # 地域/宏观类标签，只在行情驱动时保留（这里直接剔除，避免堆砌）
        GEO_REJECT = ('板块', '特区', '新区', '自贸区', '滨海', '长江三角',
                      '珠江三角', '京津冀', '西部', '中部', '东北', '海南')

        def clean_tags(raw_str, industry):
            tags = []
            for t in (raw_str or '').split(','):
                t = t.strip()
                if not t or t in BLACKLIST:
                    continue
                if any(g in t for g in GEO_REJECT) and len(t) <= 6:
                    continue
                # 去掉“概念”“板块”后缀，统一展示名
                t = t.replace('概念', '').replace('板块', '').strip()
                if len(t) >= 2 and t not in BLACKLIST:
                    tags.append(t)
            # 行业作为兜底题材
            if industry and industry not in tags:
                tags.append(industry)
            # 去重保序
            seen = set(); out = []
            for t in tags:
                if t not in seen:
                    seen.add(t); out.append(t)
            return out

        # 1) 逐股清洗题材标签
        for r in raw:
            r['_themes_raw'] = clean_tags(r.get('concepts_raw', ''), r.get('industry', ''))

        # 2) 聚合题材热度：题材内平均高开 + 强势家数占比
        theme_stats = {}
        for r in raw:
            for t in r['_themes_raw']:
                ts = theme_stats.setdefault(t, {'gaps': [], 'strong': 0, 'n': 0})
                ts['gaps'].append(r['gap'])
                ts['n'] += 1
                if r['gap'] >= 2 or r.get('em_vol_ratio', 0) >= 2:
                    ts['strong'] += 1

        # 热度 0~100：平均高开(满分5%) + 强势占比
        heat_map = {}
        for name, ts in theme_stats.items():
            if ts['n'] == 0:
                continue
            avg_gap = sum(ts['gaps']) / ts['n']
            strong_ratio = ts['strong'] / ts['n']
            heat = min(100.0, (avg_gap / 5.0 * 50.0) + (strong_ratio * 50.0))
            heat_map[name] = round(heat, 1)

        # 3) 个股题材分：Top3 热度加权 0.5/0.3/0.2 + 协同加分
        for r in raw:
            scored = [(t, heat_map.get(t, 0)) for t in r['_themes_raw']]
            scored.sort(key=lambda x: -x[1])
            # 只保留热度>=50 的有效题材参与加分
            valid = [(n, h) for n, h in scored if h >= 50]
            theme_score = 0.0
            if len(valid) >= 1:
                theme_score += valid[0][1] * 0.5
            if len(valid) >= 2:
                theme_score += valid[1][1] * 0.3
            if len(valid) >= 3:
                theme_score += valid[2][1] * 0.2
            # 多题材协同
            strong_gt70 = sum(1 for _, h in valid if h > 70)
            strong_gt65 = sum(1 for _, h in valid if h > 65)
            if strong_gt70 >= 2:
                theme_score += 5
            if strong_gt70 >= 3 or strong_gt65 >= 3:
                theme_score += 8
            # 惩罚：题材堆砌但都不热
            if len(valid) > 6 and (sum(h for _, h in valid) / len(valid)) < 40:
                theme_score -= 8
            theme_score = min(theme_score, 100.0)

            # 强势题材展示（全部有效题材，不带分数，作为 fallback）
            r['theme_fallback'] = [n for n, h in valid]
            r['theme_score'] = round(theme_score, 1)
            r['_valid_themes'] = valid

    @staticmethod
    def _enrich_with_limit_up_reason(raw):
        """强势题材：优先调用 get_last_limit_up_reason 取最近一次涨停原因；
        无涨停记录则 fallback 到概念标签（全部，不带分数）。
        涨停原因中的 '+' 号替换为顿号显示。"""
        try:
            from data.limit_up_reason_db import get_last_limit_up_reason
        except Exception as e:
            print(f'[集合竞价] 导入limit_up_reason_db失败: {e}', flush=True)
            for r in raw:
                r['theme_display'] = '、'.join(r.get('theme_fallback', [])) or '--'
            return
        for r in raw:
            try:
                reason, _dt, _lbc, _ind = get_last_limit_up_reason(r['code'])
            except Exception as e:
                print(f'[集合竞价] 查询涨停原因失败 {r["code"]}: {e}', flush=True)
                reason = None
            if reason:
                # reason 形如 "AI+算力+数据中心"，把 + 换成顿号
                r['theme_display'] = reason.replace('+', '、').strip()
            else:
                # fallback 到概念标签（全部，不带分数）
                r['theme_display'] = '、'.join(r.get('theme_fallback', [])) or '--'

    @staticmethod
    def _elapsed_trading_minutes(now=None):
        """计算当日已交易分钟数（含集合竞价5分钟），用于量比归一化"""
        now = now or datetime.now()
        hm = now.hour * 60 + now.minute
        t_open = 9 * 60 + 30
        t_close = 15 * 60
        if hm < t_open:
            # 盘前：9:25-9:30 算竞价5分钟，更早按0
            return 5 if hm >= (9 * 60 + 25) else 0
        if hm <= 11 * 60 + 30:
            return 5 + (hm - t_open)              # 上午：竞价5分钟 + 盘中
        if hm < 13 * 60:
            return 5 + 120                        # 午休：上午已交易120分钟
        if hm <= t_close:
            return 5 + 120 + (hm - 13 * 60)        # 下午
        return 5 + 240                            # 收盘后：全天240分钟 + 竞价5分钟

    @staticmethod
    def _score_volume_price(r):
        """量价基础分(0~100)、风险扣分、分时形态标签。返回 (base_score, risk_penalty, shape_label)"""
        avg_vol5 = r.get('avg_vol5', 0)
        elapsed = AuctionFilterWidget._elapsed_trading_minutes()
        # 按已交易分钟数归一化预期成交量（全天240分钟 + 竞价5分钟）
        if avg_vol5 and avg_vol5 > 0 and elapsed > 0:
            expected_vol = avg_vol5 / 240.0 * elapsed
            vol_ratio = r['jj_vol_shares'] / expected_vol if expected_vol > 0 else 0.0
        else:
            vol_ratio = r.get('em_vol_ratio', 0)
        r['vol_ratio'] = round(vol_ratio, 2)

        # 竞价量能占比 = 竞价量 / 昨量
        ref_vol = r.get('ref_vol', 0)
        vol_ratio_ref = (r['jj_vol_shares'] / ref_vol) if ref_vol and ref_vol > 0 else 0.0
        r['vol_ratio_ref'] = round(vol_ratio_ref * 100, 1)  # %

        # 情绪值 = 竞价换手率 * 竞价量比
        emotion = r['jj_turnover'] * vol_ratio
        r['emotion'] = round(emotion, 2)

        gap = r['gap']
        # [CYB-GATE] 创业板 20cm：最优高开区间按 2 倍缩放（主板 3~4% → 创业板 6~8%）
        _cyb = _is_cyb(r.get('code'))
        _o1, _o2, _s1, _s2 = _gap_score_bands(r.get('code'))

        # --- 高开幅度分 (20) ---
        if _o1 <= gap <= _o2:
            gap_score = 20
        elif (_s1 <= gap < _o1) or (_o2 < gap <= _s2):
            gap_score = 15
        else:
            gap_score = 8

        # --- 竞价量比分 (25) ---
        if vol_ratio >= 5:
            vr_score = 25
        elif vol_ratio >= 3:
            vr_score = 18
        elif vol_ratio >= 2:
            vr_score = 10
        else:
            vr_score = 0  # <2 量能不足

        # --- 情绪值分 (25) ---
        if emotion >= 12:
            em_score = 25
        elif emotion >= 10:
            em_score = 18
        elif emotion >= 8:
            em_score = 10
        else:
            em_score = 0

        # --- 量能占比分 (15) ---
        if vol_ratio_ref >= 0.5:
            ar_score = 15
        elif vol_ratio_ref >= 0.3:
            ar_score = 10
        else:
            ar_score = 5

        # --- 分时形态分 (15) + 标签（无逐笔tick时用高开+量比作代理）---
        # [CYB-GATE] 创业板 20cm：高开阈值按 2 倍缩放（主板 3/2/2.5 → 创业板 6/4/5）
        _sh, _sl, _sf = (6.0, 4.0, 5.0) if _cyb else (3.0, 2.0, 2.5)
        if gap >= _sh and vol_ratio >= 5:
            shape_score = 15
            shape = '红柱递增'
        elif gap >= _sl and vol_ratio >= 2:
            shape_score = 10
            shape = '价格攀升'
        elif gap < _sf:
            shape_score = 0
            shape = '绿柱扩大'
        else:
            shape_score = 5
            shape = '平稳'

        base = gap_score + vr_score + em_score + ar_score + shape_score

        # --- 风险扣分 ---
        risk = 0
        flags = []
        # 高位股：距60日最低涨幅 >100%
        low60 = r.get('low60', 0)
        high_pos = False
        if low60 and low60 > 0:
            gain60 = (r['price'] - low60) / low60 * 100
            if gain60 > 100:
                risk += 10
                flags.append('高位风险')
                high_pos = True
        # 次新股（上市不足60个交易日）
        is_new = r.get('hist_days', 999) < 60
        if is_new:
            flags.append('次新股')
            risk += 5
        r['is_new_stock'] = is_new
        # 题材偏弱
        if r.get('theme_score', 0) < 40:
            risk += 5
            if '题材偏弱' not in flags:
                flags.append('题材偏弱')

        r['high_pos'] = high_pos
        r['risk_flags_list'] = flags
        return base, risk, shape

    @staticmethod
    def _score_theme(r):
        return r.get('theme_score', 0)

    def _merge_persist_auction(self, fresh_rows, key='code'):
        """集合竞价专用合并：所有股票发现时间固定为09:25（竞价数据9:25才出）。"""
        self._check_date_reset()
        AUCTION_TIME = '09:25'
        for r in fresh_rows:
            k = r.get(key) if isinstance(r, dict) else None
            if k is None:
                continue
            if k in self._persist_rows:
                # 更新行情字段，但不覆盖 _found_time
                # [UI-COL] jj_amount/jj_amount_time 是9:25首次快照，不被后续刷新覆盖
                r.pop('jj_amount', None)
                r.pop('jj_amount_time', None)
                self._persist_rows[k].update(r)
            else:
                self._persist_rows[k] = r
                # 集合竞价数据9:25才出，固定显示09:25
                self._found_time[k] = AUCTION_TIME
                # 写库（INSERT OR IGNORE）：重启后仍显示09:25
                self._persist_new_found_time(k, AUCTION_TIME)
        return list(self._persist_rows.values())

    # ---------------------------------------------------------------
    # UI 回调
    # ---------------------------------------------------------------
    def _on_loaded(self, payload):
        rows = payload.get('rows', []) if isinstance(payload, dict) else []
        note = (payload or {}).get('note', '')
        # 合并到当日持久化表：集合竞价时间固定09:25，老的更新行情数据但保留发现时间
        self._snap_saved_at = datetime.now().strftime('%H:%M:%S')
        self._rows = self._merge_persist_auction(rows, key='code')
        # 渲染前按综合得分降序（持久化表中的历史股也一起排序展示）
        self._rows.sort(key=lambda x: -(x.get('score') or 0))
        self._render_rows()
        # 控盘度：先用缓存立刻填，再后台补算缺的（不阻塞 UI）
        self.ctrl_fill_and_async(self._rows, self._render_rows)
        if self._rows:
            self.title_label.setText(f'⚡ 竞价 TOP{len(self._rows)}')
            self.set_update_time()
            # [FIX] 把筛选漏斗写进状态栏，用户一眼看到"确实在筛选"
            _fun = (payload or {}).get('funnel') or {}
            if _fun:
                _src = {'sina': '新浪', 'tencent': '腾讯涨幅榜'}.get(
                    _fun.get('source'), _fun.get('source') or '-')
                self.set_status('集合竞价 · %s · 源:%s · 候选%d→主板%d→缺口%d→换手%d→入选%d' % (
                    self._auction_stage(), _src, _fun.get('raw', 0), _fun.get('main', 0),
                    _fun.get('gap', 0), _fun.get('turn', 0), _fun.get('final', 0)))
            # 后台线程把当日入选股票写入 auction_tracking 表（幂等，不阻塞UI）
            self._async_persist_tracking()
            # V2.3：当天真实筛选结果保存到交易日快照（休市/重启复盘恢复）
            self._save_auction_snapshot()
        else:
            self.title_label.setText('⚡ 竞价')
            self.set_status(note or '暂无数据')

    def _on_loaded_tail(self, payload):
        """尾盘数据加载：合并到早盘结果，去重，新加的标'尾盘'标签"""
        rows = payload.get('rows', []) if isinstance(payload, dict) else []
        if not rows:
            return
        # 已有的code集合（早盘结果）
        existing = {r.get('code') for r in self._rows}
        for r in rows:
            r['is_tail'] = True  # 尾盘标记
            if r.get('code') not in existing:
                self._rows.append(r)
        self._rows.sort(key=lambda x: -(x.get('score') or 0))
        self._render_rows()
        self.ctrl_fill_and_async(self._rows, self._render_rows)
        self.title_label.setText(f'⚡ 竞价 TOP{len(self._rows)}（含尾盘）')
        self.set_update_time()
        self._save_auction_snapshot()

    def _on_failed(self, err):
        self.title_label.setText('⚡ 竞价')
        self.set_status('数据加载失败')
        # 加载失败不清空已持久化的当日数据，仅在无历史时提示
        if not self._rows:
            self.table.setRowCount(1)
            set_table_item(self.table, 0, 0, f'加载失败: {err}', BC.TEXT3,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            self.table.setSpan(0, 0, 1, 9)

    def _render_rows(self):
        fetch_ctrl_cached(self._rows)
        rows = self._rows
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        if not rows:
            return
        for row, r in enumerate(rows):
            code = r.get('code', '')
            # 0 名称
            set_table_item(self.table, row, 0, r['name'], BC.RED, bold=True,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 1 代码
            set_table_item(self.table, row, 1, r['code'], '#000000',
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 2 综合得分
            score = r['score']
            score_color = BC.RED if score >= 60 else (BC.ORANGE if score >= 45 else BC.TEXT)
            set_table_item(self.table, row, 2, f'{score:.1f}', score_color, bold=True,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 3 竞价涨幅（=原开盘涨幅）
            set_table_item(self.table, row, 3, f"+{r['gap']:.2f}%", BC.RED,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 4 当前涨幅（f3，若数据是竞价快照则加后缀；None=旧快照无此列）
            cur_pct = r.get('cur_pct')
            _jj_time = r.get('jj_amount_time', '')
            _cur_time = r.get('cur_time', '')
            def _is_auction_t(t):
                try:
                    h, m = int(t[:2]), int(t[3:5])
                    return h == 9 and 25 <= m <= 29
                except Exception:
                    return False
            # [FIX-口径] 已由后台行情成功刷新过(rt_live)就不再标〔快照〕
            _is_snapshot = (not r.get('rt_live')) and _is_auction_t(_cur_time)
            if cur_pct is None:
                set_table_item(self.table, row, 4, '--', BC.TEXT3,
                               align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                self.table.item(row, 4).setToolTip('旧快照v1无实时涨幅数据')
            else:
                cur_color = BC.RED if cur_pct >= 0 else BC.GREEN
                _pct_suffix = ' 〔快照〕' if _is_snapshot else ''
                set_table_item(self.table, row, 4, f"{cur_pct:+.2f}%{_pct_suffix}", cur_color,
                               align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                if _is_snapshot:
                    self.table.item(row, 4).setToolTip(
                        f'数据时间 {_cur_time or _jj_time}，竞价快照（实时行情不可用）')
            # 5 竞价金额（=今开价，旧快照有open字段）
            open_px = r.get('open', 0) or 0
            jj_text = f'{open_px:.2f}' if open_px > 0 else '--'
            set_table_item(self.table, row, 5, jj_text, BC.TEXT,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 6 当前金额（=当前价，腾讯实时；旧快照无此列显示--）
            cur_px = r.get('cur_price', 0) or 0
            cur_text = f'{cur_px:.2f}' if cur_px > 0 else '--'
            set_table_item(self.table, row, 6, cur_text, BC.TEXT,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            # 7 强势题材
            themes = r.get('theme_display', '--') or '--'
            set_table_item(self.table, row, 7, themes, BC.TEXT)
            self.table.item(row, 7).setToolTip(themes)
            # 8 控盘（新增列）
            from services.control_profile import ctrl_cell, ctrl_tooltip
            _ci = r.get('ctrl')
            _ct, _cc = ctrl_cell(_ci)
            _ctr = (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, row, COL_CTRL, _ct, _cc, align=_ctr)
            self.table.item(row, COL_CTRL).setToolTip(ctrl_tooltip(_ci))
        # [UI-COL] 渲染完后异步调腾讯补当前涨幅/当前价（东财被封时腾讯可用）
        self._fetch_realtime_from_tencent()

    def _fetch_realtime_from_tencent(self):
        """批量补当前涨幅/当前价。

        [FIX-异步] 原实现自称"异步"，实际是在主线程里同步发网络请求；
                   竞价结束后每 60s 刷新一次，网络一慢就卡 UI。
                   现改为 run_async 真后台线程拉取，回主线程更新表格。
        """
        codes = [r.get('code', '') for r in self._rows if r.get('code')]
        if not codes:
            return
        self.run_async(AuctionFilterWidget._fetch_rt_quotes,
                       self._apply_rt_quotes, None, codes)

    @staticmethod
    def _fetch_rt_quotes(codes):
        """后台线程：拉批量实时行情"""
        from utils.http_market_data import get_realtime_quotes_http
        return get_realtime_quotes_http(codes) or {}

    def _apply_rt_quotes(self, q):
        """主线程：把实时行情写回表格。

        [FIX-口径] 只有真拿到实时价(price>0)才清掉〔快照〕标记并打实时时间；
                   没拿到就保持原样，绝不把 9:29 的旧值伪装成实时值。
        """
        if not isinstance(q, dict) or not q:
            return
        _now = datetime.now().strftime('%H:%M:%S')
        _idx = {}
        for i, r in enumerate(self._rows):
            _idx[r.get('code')] = i
        _n = 0
        for c, v in q.items():
            i = _idx.get(c)
            if i is None:
                continue
            try:
                price = float((v or {}).get('price') or 0)
                pct = float((v or {}).get('pct_chg') or 0)
            except Exception:
                continue
            if price <= 0:
                continue                       # 停牌 / 取价失败：保持原样
            r = self._rows[i]
            r['rt_live'] = True
            r['rt_time'] = _now
            r['cur_price'] = price
            r['cur_pct'] = pct
            it = self.table.item(i, 6)
            if it:
                it.setText(f'{price:.2f}')
                it.setToolTip(f'实时行情 {_now}')
            it = self.table.item(i, 4)
            if it:
                it.setText(f'{pct:+.2f}%')     # 实时值：不再带〔快照〕
                it.setForeground(QBrush(QColor(BC.RED if pct >= 0 else BC.GREEN)))
                it.setToolTip(f'实时行情 {_now}')
            _n += 1
        if _n:
            self.set_update_time()

    # ================================================================
    # 右键菜单：今日竞价表「📌 添加到竞价追踪」
    # ================================================================
    def _on_today_context_menu(self, pos):
        """今日竞价表右键：把当前行加入竞价追踪"""
        row = self.table.rowAt(int(pos.y()))
        if row < 0 or row >= len(self._rows):
            return
        menu = QMenu(self.table)
        act_add = menu.addAction('📌 添加到竞价追踪')
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == act_add:
            self._add_to_track(row)

    def _add_to_track(self, row):
        """右键添加：把今日竞价表第 row 行写入追踪库。
        P0(base_price) = 添加时的当前价（盘中实时价），fallback 今开价。"""
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        code = (r.get('code') or '').strip()
        name = (r.get('name') or '').strip()
        price = float(r.get('price') or r.get('open') or 0)
        if not code or price <= 0:
            print(f'[竞价追踪] 添加失败：无有效价格 code={code}', flush=True)
            self.set_status('添加失败：无有效价格')
            return
        # 休市：不能添加竞价追踪记录（避免创建伪造的当天竞价记录）
        if not _trade_cal.is_trading_day(datetime.now()):
            self.set_status('休市：不能添加竞价追踪记录')
            return
        trade_date = datetime.now().strftime('%Y-%m-%d')
        threading.Thread(
            target=AuctionFilterWidget._insert_one_track,
            args=(self._tracking_db, trade_date, code, name, price),
            daemon=True,
        ).start()

    @staticmethod
    def _insert_one_track(db_path, trade_date, code, name, base_price):
        """后台线程：插入一条手动追踪记录（同 code 当日已存在则跳过，幂等）。
        P0 = base_price = 添加时现价。"""
        try:
            import duckdb
            con = duckdb.connect(db_path)
            AuctionFilterWidget._ensure_tracking_schema(con)
            exists = con.execute(
                "SELECT 1 FROM auction_tracking WHERE trade_date=? AND code=?",
                [trade_date, code]).fetchone()
            if exists is None:
                con.execute(
                    "INSERT INTO auction_tracking "
                    "(trade_date, code, name, open_price, base_close, created_at, base_price) "
                    "VALUES (?,?,?,?,?,?,?)",
                    [trade_date, code, name, base_price, 0.0,
                     datetime.now(), base_price])
                print(f'[竞价追踪] ✅ 添加成功 {trade_date} {code} {name} P0={base_price:.2f}', flush=True)
            else:
                print(f'[竞价追踪] 已存在，跳过 {trade_date} {code}', flush=True)
            con.close()
        except Exception as e:
            print(f'[竞价追踪] 添加写入失败: {e}', flush=True)

    # ================================================================
    # 右键菜单：竞价追踪表「❌ 从竞价追踪中移除」
    # ================================================================
    def _on_track_context_menu(self, pos):
        """竞价追踪表右键：从追踪库删除当前行并刷新"""
        row = self.track_table.rowAt(int(pos.y()))
        if row < 0 or row >= len(self.track_list):
            return
        menu = QMenu(self.track_table)
        act_del = menu.addAction('❌ 从竞价追踪中移除')
        act = menu.exec(self.track_table.viewport().mapToGlobal(pos))
        if act == act_del:
            self._remove_from_track(row)

    def _remove_from_track(self, row):
        """右键移除：删库 + 内存列表删除 + 刷新表格"""
        if row < 0 or row >= len(self.track_list):
            return
        r = self.track_list[row]
        code = r.get('code'); td = r.get('trade_date')
        print(f'[竞价追踪] ❌ 移除 {td} {code} {r.get("name","")}', flush=True)
        threading.Thread(
            target=AuctionFilterWidget._delete_one_track,
            args=(self._tracking_db, td, code),
            daemon=True,
        ).start()
        # 内存缓存立即删除并重建表格（低频操作，整表重建可接受）
        self.track_list.pop(row)
        self._render_tracking()

    @staticmethod
    def _delete_one_track(db_path, trade_date, code):
        """后台线程：删除一条追踪记录"""
        try:
            import duckdb
            con = duckdb.connect(db_path)
            con.execute(
                "DELETE FROM auction_tracking WHERE trade_date=? AND code=?",
                [trade_date, code])
            con.close()
            print(f'[竞价追踪] 已从库删除 {trade_date} {code}', flush=True)
        except Exception as e:
            print(f'[竞价追踪] 删除失败: {e}', flush=True)

    # ================================================================
    # 竞价追踪：DuckDB 持久化（写入）+ 收益/盈亏计算（kline_cache 只读）
    # ================================================================
    @staticmethod
    def _ensure_tracking_schema(con):
        """幂等建表 + 列升级：确保存在 base_price(P0) 字段"""
        con.execute("""
            CREATE TABLE IF NOT EXISTS auction_tracking (
                trade_date   VARCHAR,
                code         VARCHAR,
                name         VARCHAR,
                open_price   FLOAT,
                base_close   FLOAT,
                created_at   TIMESTAMP
            )
        """)
        # 老表升级：补 base_price(P0) 字段（已存在则忽略）
        try:
            con.execute("ALTER TABLE auction_tracking ADD COLUMN IF NOT EXISTS base_price FLOAT")
        except Exception as e:
            print(f'[竞价追踪] 补 base_price 列失败(忽略): {e}', flush=True)

    def _async_persist_tracking(self):
        """起 daemon 后台线程把当日入选股票写入 auction_tracking.duckdb（不阻塞UI）"""
        try:
            now = datetime.now()
            if not _trade_cal.is_trading_day(now):
                return  # 休市/非交易日：不创建当天竞价追踪记录
            trade_date = now.strftime('%Y-%m-%d')
            snapshot = [dict(r) for r in self._rows]
            threading.Thread(
                target=AuctionFilterWidget._persist_tracking,
                args=(snapshot, trade_date, self._tracking_db),
                daemon=True,
            ).start()
        except Exception as e:
            print(f'[竞价追踪] 启动持久化线程失败: {e}', flush=True)

    @staticmethod
    def _persist_tracking(rows, trade_date, db_path):
        """后台线程：把当日 TOP 股票写入 auction_tracking 表。
        - 表不存在自动 CREATE；缺 base_price 列自动 ALTER 补齐
        - 同 (trade_date, code) 只插一次；P0(base_price)=入选当日开盘价(竞价金额)
        - 清理历史测试数据（TEST 开头）
        - 休市日不创建当天竞价记录（交易日历校验）
        """
        try:
            if not _trade_cal.is_trading_day(trade_date):
                print(f'[竞价追踪] 非交易日 {trade_date}：拒绝写入竞价追踪记录', flush=True)
                return  # 休市：不创建当天竞价记录
        except Exception as e:
            # fail-closed：交易日校验异常一律拒绝写入，防止休市伪造当天记录
            print(f'[竞价追踪] 交易日校验异常，拒绝写入: {e}', flush=True)
            return
        try:
            import duckdb
        except Exception as e:
            print(f'[竞价追踪] 无 duckdb: {e}', flush=True)
            return
        try:
            con = duckdb.connect(db_path)
            AuctionFilterWidget._ensure_tracking_schema(con)
            # 清理测试数据（幂等）
            try:
                con.execute("DELETE FROM auction_tracking "
                            "WHERE trade_date LIKE 'TEST%' OR code LIKE 'TEST%' OR name LIKE 'TEST%'")
            except Exception:
                pass
        except Exception as e:
            print(f'[竞价追踪] 建表失败: {e}', flush=True)
            return

        try:
            for r in rows:
                code = r.get('code')
                name = r.get('name', '')
                # P0 = 入选当日开盘价（竞价金额）；盘中用加入时现价兜底
                base_price = float(r.get('open') or r.get('price') or 0)
                open_price = base_price
                if not code or base_price <= 0:
                    continue
                exists = con.execute(
                    "SELECT base_price FROM auction_tracking "
                    "WHERE trade_date=? AND code=?",
                    [trade_date, code]).fetchone()
                if exists is None:
                    con.execute(
                        "INSERT INTO auction_tracking "
                        "(trade_date, code, name, open_price, base_close, created_at, base_price) "
                        "VALUES (?,?,?,?,?,?,?)",
                        [trade_date, code, name, open_price, 0.0,
                         datetime.now(), base_price])
                else:
                    # 老记录缺 base_price 则回填 open_price
                    old_bp = float(exists[0] or 0)
                    if old_bp <= 0:
                        con.execute(
                            "UPDATE auction_tracking SET base_price=? "
                            "WHERE trade_date=? AND code=?",
                            [base_price, trade_date, code])
            con.close()
        except Exception as e:
            print(f'[竞价追踪] 写入失败: {e}', flush=True)
            try:
                con.close()
            except Exception:
                pass

    # ---------------------------------------------------------------
    # 竞价追踪 Tab：异步读取 + 计算盈亏 + 渲染 + 启动实时行情
    # ---------------------------------------------------------------
    def refresh_tracking(self):
        """点击“竞价追踪”Tab 时调用：后台线程读库算盈亏，回主线程渲染，随后启动实时定时器"""
        self.run_async(self._fetch_tracking, self._on_tracking_loaded, None)

    @staticmethod
    def _fetch_tracking():
        """后台线程：读 auction_tracking.duckdb + kline_cache.duckdb(只读)，
        计算每只追踪股票的 5/15/30 日盈亏（相对 P0），并取题材。"""
        import duckdb
        db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'auction_tracking.duckdb')
        records = []
        if os.path.exists(db_path):
            try:
                # 只保留 30 天内的追踪记录，超期自动移除（清理失败不影响读取）
                try:
                    con_w = duckdb.connect(db_path)
                    try:
                        con_w.execute("DELETE FROM auction_tracking "
                                      "WHERE trade_date < CAST(CURRENT_DATE - INTERVAL 30 DAY AS VARCHAR)")
                    finally:
                        con_w.close()
                except Exception as e:
                    print(f'[竞价追踪] 清理30天前记录失败: {e}', flush=True)
                con = duckdb.connect(db_path, read_only=True)
                # 兼容老库无 base_price 列
                cols = [c[0] for c in con.execute('DESCRIBE auction_tracking').fetchall()]
                sel_bp = 'base_price' if 'base_price' in cols else 'open_price AS base_price'
                records = con.execute(
                    f"SELECT trade_date, code, name, open_price, {sel_bp} "
                    f"FROM auction_tracking ORDER BY trade_date DESC").fetchall()
                con.close()
            except Exception as e:
                print(f'[竞价追踪] 读追踪表失败: {e}', flush=True)
                return []
        if not records:
            return []

        # 批量取这些股票的日线（升序）：code -> [(date, low, close), ...]
        kline_map = {}
        kpath = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
        if os.path.exists(kpath):
            try:
                codes = list({r[1] for r in records if r[1]})
                con2 = duckdb.connect(kpath, read_only=True)
                ph = ','.join(['?'] * len(codes))
                for code, date, low, close in con2.execute(
                        f"SELECT code, date, low, close FROM kline_cache "
                        f"WHERE code IN ({ph}) ORDER BY code, date ASC",
                        codes).fetchall():
                    kline_map.setdefault(code, []).append(
                        (str(date), float(low or 0), float(close or 0)))
                con2.close()
            except Exception as e:
                print(f'[竞价追踪] 读kline失败: {e}', flush=True)

        # 题材查询函数（try/except 包裹，失败显示 --）
        try:
            from data.limit_up_reason_db import get_last_limit_up_reason
        except Exception as e:
            print(f'[竞价追踪] 导入limit_up_reason_db失败: {e}', flush=True)
            get_last_limit_up_reason = None  # noqa: N816

        def _theme_of(code):
            if get_last_limit_up_reason is None:
                return '--'
            try:
                reason, _dt, _lbc, _ind = get_last_limit_up_reason(code)
                if reason:
                    return reason.replace('+', '、').strip()
            except Exception as e:
                print(f'[竞价追踪] 题材查询失败 {code}: {e}', flush=True)
            return '--'

        out = []
        for trade_date, code, name, open_price, base_price in records:
            td = str(trade_date)[:10]
            # P0：优先 base_price，缺失时退回 open_price
            bp = float(base_price or 0) or float(open_price or 0)
            bars = kline_map.get(code, [])
            # 定位加入日（入选当日）在升序日线中的下标
            idx = None
            for i, (d, _lo, _cl) in enumerate(bars):
                if d == td:
                    idx = i
                    break

            # 5/15/30 日盈亏：相对 P0 的 T+N 收盘价收益；不足 N 天 -> None(持有中)
            r5 = r30 = None
            if bp > 0 and idx is not None:
                def _ret(n):
                    j = idx + n
                    if j < len(bars) and bars[j][2] > 0:
                        return round((bars[j][2] - bp) / bp * 100.0, 2)
                    return None  # 不足N天 -> 持有中
                r5, r30 = _ret(5), _ret(30)

            out.append({
                'trade_date': td,
                'code': code,
                'name': name,
                'theme': _theme_of(code),
                'base_price': bp,
                'open_price': float(open_price or bp),
                'cur_price': 0.0,
                'r5': r5, 'r30': r30,
                'cum_pnl': None,
            })
        return out

    def _on_tracking_loaded(self, rows):
        """主线程：拿到算好的追踪数据，按筛选日期降序后渲染，并启动实时行情定时器"""
        self.track_list = rows or []
        self.track_list.sort(key=lambda r: r['trade_date'], reverse=True)
        self._render_tracking()
        # 进入追踪Tab：启动 3s 节流定时器 + 后台行情线程，立即拉一次实时价
        self._start_track_timer()
        self._tick_realtime()

    # ---------------------------------------------------------------
    # 高性能架构：按需 QTimer(3s) 节流 + QThread 后台行情 + 增量更新
    # ---------------------------------------------------------------
    def _start_track_timer(self):
        """启动追踪专用 3s 节流定时器（只在追踪Tab激活时调用）"""
        if self._track_timer is None:
            self._track_timer = QTimer(self)
            self._track_timer.setInterval(3000)   # 每3秒批量更新一次，而非每个tick
            self._track_timer.timeout.connect(self._tick_realtime)
        self._track_timer.start(3000)
        self._ensure_quote_thread()

    def _stop_track_timer(self):
        """切回今日竞价：停止定时器，暂停后台计算释放CPU（线程保留复用，不反复销毁）"""
        if self._track_timer is not None:
            self._track_timer.stop()

    def _ensure_quote_thread(self):
        """懒启动后台行情 QThread（worker 只在自己线程跑，信号回主线程）"""
        if self._quote_thread is not None and self._quote_thread.isRunning():
            return
        self._quote_thread = QThread()
        self._quote_worker = _QuoteFetchWorker()
        self._quote_worker.moveToThread(self._quote_thread)
        # 主线程信号 -> worker槽：跨线程自动 QueuedConnection，线程安全
        self.sig_request_quotes.connect(self._quote_worker.run_fetch)
        self._quote_worker.quotes_ready.connect(self._apply_realtime_quotes)
        self._quote_thread.start()

    def _tick_realtime(self):
        """定时器触发：把追踪股代码列表发往后台线程拉实时价（不阻塞UI）"""
        if not self._track_widget.isVisible():
            return
        codes = [r['code'] for r in self.track_list if r.get('code')]
        if not codes:
            return
        self._ensure_quote_thread()
        # 主线程 emit -> worker 线程 run_fetch（自动排队）
        self.sig_request_quotes.emit(codes)

    def _apply_realtime_quotes(self, prices):
        """主线程槽：后台线程算好实时价后，增量更新当前实时价与累计盈亏单元格。
        只 setText 数值变化的单元格，不重建表格。"""
        if not self._track_widget.isVisible():
            return
        if not isinstance(prices, dict):
            return
        for row, r in enumerate(self.track_list):
            code = r['code']
            price = prices.get(code)
            if not price or price <= 0:
                continue
            r['cur_price'] = float(price)
            bp = float(r.get('base_price') or 0)
            # col5 当前实时价
            self._patch_cell(row, C_NOW, f'{price:.2f}', BC.TEXT, align='right')
            # col9 累计盈亏 = (实时价 - P0) / P0 * 100，正红负绿
            if bp > 0:
                cum = (price - bp) / bp * 100.0
                r['cum_pnl'] = round(cum, 2)
                self._patch_pnl_cell(row, C_CUM, r['cum_pnl'])

    # ---------------------------------------------------------------
    # 增量更新辅助（只改文本/颜色，不新建 item、不重建行）
    # ---------------------------------------------------------------
    def _patch_cell(self, row, col, text, color=None, align=None):
        tbl = self.track_table
        if row >= tbl.rowCount():
            return
        it = tbl.item(row, col)
        if it is None:
            align_flag = (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight) \
                if align == 'right' else (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            set_table_item(tbl, row, col, text, color, align=align_flag)
            return
        # 增量：文本没变就不重绘
        if it.text() == text:
            return
        it.setText(text)
        if color:
            it.setForeground(QColor(color))

    def _patch_pnl_cell(self, row, col, v):
        """增量更新盈亏单元格：正红负绿"""
        tbl = self.track_table
        if row >= tbl.rowCount():
            return
        text = '--' if v is None else f'{v:+.2f}%'
        color = pct_color(v)
        it = tbl.item(row, col)
        if it is not None and it.text() == text:
            # 文本相同也要保证颜色正确（价格回摆时同值不同色概率极低，仅在颜色漂移时更新）
            cur = it.foreground().color()
            target = QColor(color)
            if cur.red() == target.red() and cur.green() == target.green() and cur.blue() == target.blue():
                return
            it.setForeground(target)
            return
        align_flag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        item = set_table_item(tbl, row, col, text, color, bold=True, align=align_flag)

    def _render_tracking(self):
        """渲染竞价追踪表格：9 列。盈亏正红负绿；实时价/累计盈亏先占位，由后台行情增量更新"""
        self.track_table.clearSpans()
        rows = self.track_list
        self.track_table.setRowCount(len(rows))
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight

        if not rows:
            self.track_table.setRowCount(1)
            set_table_item(self.track_table, 0, 0, '暂无历史追踪数据（右键今日竞价行可添加）', BC.TEXT3,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            self.track_table.setSpan(0, 0, 1, TRACK_COL_N)
            return

        for row, r in enumerate(rows):
            # 9 控盘（新增列）
            from services.control_profile import ctrl_cell as _cc2, ctrl_tooltip as _ct2
            _i2 = r.get('ctrl')
            _t2, _c2 = _cc2(_i2)
            set_table_item(self.track_table, row, C_TRACK_CTRL, _t2, _c2, align=center)
            self.track_table.item(row, C_TRACK_CTRL).setToolTip(_ct2(_i2))
            # 0 筛选日期
            set_table_item(self.track_table, row, C_DATE, r['trade_date'], '#000000', align=center)
            # 1 股票名称
            set_table_item(self.track_table, row, C_NAME, r['name'], '#000000', bold=True, align=center)
            # 2 题材（get_last_limit_up_reason，失败/空显示 --）
            set_table_item(self.track_table, row, C_THEME,
                           r.get('theme', '--') or '--', BC.CYAN)
            # 3 股票代码
            set_table_item(self.track_table, row, C_CODE, r['code'], '#000000', align=center)
            # 4 竞价金额(P0)
            bp = r.get('base_price') or 0
            set_table_item(self.track_table, row, C_P0,
                           f'{bp:.2f}' if bp > 0 else '--', BC.TEXT, align=right)
            # 5 当前实时价（后台行情增量更新，先占位）
            cur = r.get('cur_price') or 0
            set_table_item(self.track_table, row, C_NOW,
                           f'{cur:.2f}' if cur > 0 else '--', BC.TEXT, align=right)
            # 6/7 两档盈亏：None -> 持有中
            def _pnl_cell(col, v):
                if v is None:
                    set_table_item(self.track_table, row, col, '持有中',
                                   BC.TEXT3, align=center)
                else:
                    set_table_item(self.track_table, row, col, f'{v:+.2f}%',
                                   pct_color(v), bold=True, align=right)
            _pnl_cell(C_P5, r['r5'])
            _pnl_cell(C_P30, r['r30'])
            # 8 累计盈亏（后台实时增量更新，先占位）
            cum = r.get('cum_pnl')
            if cum is None:
                set_table_item(self.track_table, row, C_CUM, '--', BC.TEXT3, align=right)
            else:
                set_table_item(self.track_table, row, C_CUM, f'{cum:+.2f}%',
                               pct_color(cum), bold=True, align=right)

    # ---------------------------------------------------------------
    # 资源清理：程序退出时停止定时器并回收后台线程
    # ---------------------------------------------------------------
    def closeEvent(self, event):
        try:
            self._stop_track_timer()
            if self._quote_thread is not None:
                self._quote_thread.quit()
                self._quote_thread.wait(2000)
        except Exception as e:
            print(f'[竞价追踪] 清理资源异常: {e}', flush=True)
        super().closeEvent(event)
