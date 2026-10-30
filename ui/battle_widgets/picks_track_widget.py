# -*- coding: utf-8 -*-
"""板块异动 · 「可介入」标的跟踪 Tab

把板块异动表里每天筛出的「可介入」候选票（未涨停 / 涨幅1~9% / 量比≥1.2 /
价≥6元 / 非ST / 站上MA20）存下来，跟踪它们入选后 5 个交易日、30 个交易日
的盈亏，以及到目前的累计盈亏，用来判断这个信号到底准不准。

架构（照竞价追踪的成熟做法）
--------------------------
  services.picks_tracking_service  负责持久化与收益计算
        · picks_tracking.duckdb     入库（与引擎同口径，P0=入选日收盘价）
        · kline_cache.duckdb 只读   算 T+5 / T+30
  本文件负责界面：统计条 + 表格 + 3 秒实时价 + 右键移除

性能要点
--------
· 读库与算收益全部在后台线程，回主线程只做渲染，不冻界面
· 只对当前显示的（最近 N 只）拉实时价，不对全库 3000+ 只拉
· 表格只渲染最近 _SHOW_MAX 行，统计条用全量样本，两者口径在界面上写明
"""
import os
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QLabel, QVBoxLayout, QWidget, QHeaderView,
                             QMenu)

from .base import (make_table, set_table_item, BC, HeaderSorter, CTRL_COL_TITLE,
                      fetch_ctrl_cached)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

TRACK_HEADERS = ['筛选日期', '股票名称', '股票代码', '板块', '入选价',
                 '当前价', '距MA20%', '5日盈亏%', '30日盈亏%', '累计盈亏%',
                 CTRL_COL_TITLE]
TRACK_COL_N = 11
(T_DATE, T_NAME, T_CODE, T_BOARD, T_P0,
 T_NOW, T_M20, T_R5, T_R30, T_CUM, T_CTRL) = range(TRACK_COL_N)
TRACK_WIDTHS = [92, 84, 74, 116, 74, 74, 76, 82, 84, 84, 78]

_SHOW_MAX = 300          # 表格最多渲染多少行（全量样本只用于统计条）
_RT_INTERVAL = 3000      # 实时价刷新间隔(ms)

_UP = '#c62828'          # 涨（项目惯例：红涨绿跌）
_DN = '#2f9e44'
_FLAT = BC.TEXT3


class PicksTrackWidget(QWidget):
    """可介入标的跟踪表（嵌在板块异动卡片内，不自己建卡片框）"""

    stock_clicked = pyqtSignal(str, str)
    _async_data_ready = pyqtSignal(int, object)
    _async_error = pyqtSignal(int, str)
    _rt_ready = pyqtSignal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []              # 全量（fetch_tracking 结果）
        self._shown = []             # 实际渲染的（前 _SHOW_MAX 行）
        self._stat = {}
        self._token = 0
        self._cbs = {}
        self._rt_token = 0
        self._timer = None
        self._refreshed_at = 0.0
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._stat_label = QLabel('可介入追踪：加载中...')
        self._stat_label.setStyleSheet(
            'background:#f5f8fc;border-radius:4px;padding:3px 8px;'
            'color:#333;font-size:11px;')
        self._stat_label.setWordWrap(True)
        lay.addWidget(self._stat_label)

        self.table = make_table(TRACK_COL_N, TRACK_HEADERS, min_row_height=24)
        for i, w in enumerate(TRACK_WIDTHS):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setSectionResizeMode(
            T_BOARD, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellClicked.connect(self._on_cell_clicked)
        lay.addWidget(self.table, 1)

        self.sorter = HeaderSorter(
            self.table,
            keys={T_DATE: lambda r: r['trade_date'],
                  T_NAME: lambda r: r['name'],
                  T_CODE: lambda r: r['code'],
                  T_BOARD: lambda r: r['board'],
                  T_P0: lambda r: r['base_price'],
                  T_M20: lambda r: (((r['cur_price'] - r['ma20']) / r['ma20'] * 100.0)
                                    if (r.get('ma20') and r.get('cur_price')) else -1e9),
                  T_R5: lambda r: r['r5'] if r['r5'] is not None else -1e9,
                  T_R30: lambda r: r['r30'] if r['r30'] is not None else -1e9,
                  T_CUM: lambda r: r['cum'] if r['cum'] is not None else -1e9},
            getter=lambda: self._shown,
            render=self._render,
        )

        # 信号接回调
        self._async_data_ready.connect(self._on_data)
        self._async_error.connect(self._on_err)
        self._rt_ready.connect(self._on_rt)

    # ------------------------------------------------------------------
    # 异步
    # ------------------------------------------------------------------
    def _run(self, func, on_ok, *args):
        self._token += 1
        tok = self._token
        self._cbs[tok] = on_ok

        def worker():
            try:
                self._async_data_ready.emit(tok, func(*args))
            except Exception as e:
                self._async_error.emit(tok, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_data(self, tok, result):
        cb = self._cbs.pop(tok, None)
        if cb is None:
            return
        try:
            cb(result)
        except Exception as e:
            print(f'[可介入追踪] UI回调异常: {e}', flush=True)

    def _on_err(self, tok, msg):
        cb = self._cbs.pop(tok, None)
        if cb is None:
            return
        self._stat_label.setText(f'可介入追踪：读取失败 {msg}')
        self.table.setRowCount(1)
        set_table_item(self.table, 0, 0, f'追踪数据读取失败: {msg}', BC.TEXT3)
        self.table.setSpan(0, 0, 1, TRACK_COL_N)

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    def refresh(self):
        """进入本 Tab 时调用：后台读库算收益"""
        self._stat_label.setText('可介入追踪：计算中...')
        self._run(self._fetch, self._on_loaded)

    @staticmethod
    def _fetch():
        from services.picks_tracking_service import fetch_tracking, summarize
        rows = fetch_tracking()
        return rows, summarize(rows)

    def _on_loaded(self, result):
        rows, stat = result
        self._rows = rows or []
        self._stat = stat or {}
        self._shown = self._rows[:_SHOW_MAX]
        self._render_stat()
        self._render()
        # 控盘度：后台算完再刷一次（不阻塞 UI）
        self._ctrl_fill(self._rows, self._render)
        self._start_timer()
        self._tick()

    def _ctrl_fill(self, rows, on_done):
        """后台给 rows 补控盘度，完成后回 UI 线程渲染。

        本 widget 继承 QWidget（不是 BattleModuleBase），没有 run_async，
        这里用它自带的 _run(线程池)实现同样效果。
        """
        try:
            if not rows:
                return

            def _bg():
                from .base import fetch_ctrl_for
                fetch_ctrl_for(rows)
                return True

            def _ok(_res):
                try:
                    on_done()
                except Exception:
                    pass

            self._run(_bg, _ok)
        except Exception:
            pass

    def _render_stat(self):
        s = self._stat
        if not s or not s.get('total'):
            self._stat_label.setText(
                '可介入追踪：暂无样本。本模块会每天自动记录当天筛出的可介入标的，'
                '收盘后累积即可看到 5日 / 30日 盈亏。')
            return
        days = len({r['trade_date'] for r in self._rows})
        parts = [f"共 {s['total']} 只（{days} 个交易日）"]
        for k, lbl in (('r5', '5日'), ('r30', '30日'), ('cum', '累计')):
            v = s.get(k) or {}
            if v.get('n'):
                parts.append(f"{lbl}：胜率 {v['win']}% 均 {v['avg']:+.2f}%"
                             f"（n={v['n']}）")
            else:
                parts.append(f"{lbl}：样本不足")
        shown = len(self._shown)
        tail = (f"｜ 表格显示最近 {shown} 只"
                + (f"（按列头排序可改）" if shown < s['total'] else ''))
        self._stat_label.setText(' ｜ '.join(parts) + tail)

    # ------------------------------------------------------------------
    def _render(self):
        fetch_ctrl_cached(self._shown)
        rows = self._shown
        self.table.clearSpans()
        self.table.setRowCount(max(len(rows), 1))
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        if not rows:
            set_table_item(self.table, 0, 0,
                           '暂无追踪数据（每天收盘后自动记录当天可介入标的）',
                           BC.TEXT3, align=center)
            self.table.setSpan(0, 0, 1, TRACK_COL_N)
            return
        for row, r in enumerate(rows):
            set_table_item(self.table, row, T_DATE, r['trade_date'],
                           BC.TEXT, align=center)
            set_table_item(self.table, row, T_NAME, r['name'],
                           BC.TEXT_PRIMARY, bold=True, align=center)
            set_table_item(self.table, row, T_CODE, r['code'],
                           BC.TEXT, align=center)
            set_table_item(self.table, row, T_BOARD, r['board'],
                           BC.RED, align=center)
            set_table_item(self.table, row, T_P0, f"{r['base_price']:.2f}",
                           BC.TEXT, align=right)
            # 当前价 / 累计盈亏由实时线程增量更新，先填最近收盘
            _cur = r['cur_price']
            set_table_item(self.table, row, T_NOW,
                           f'{_cur:.2f}' if _cur > 0 else '--',
                           BC.TEXT, align=right)
            # 距 MA20%：入选时它就是硬门槛，这里做成可见列便于验收
            _m20 = r.get('ma20')
            if _m20 and _cur > 0:
                _g20 = (_cur - _m20) / _m20 * 100.0
                set_table_item(self.table, row, T_M20, f'{_g20:+.2f}%',
                               _UP if _g20 >= 0 else _DN, align=right)
            else:
                set_table_item(self.table, row, T_M20, '--',
                               BC.TEXT3, align=right)
            for col, key in ((T_R5, 'r5'), (T_R30, 'r30'), (T_CUM, 'cum')):
                v = r.get(key)
                if v is None:
                    set_table_item(self.table, row, col, '持有中',
                                   BC.TEXT3, align=right)
                else:
                    set_table_item(self.table, row, col, f'{v:+.2f}%',
                                   _UP if v >= 0 else _DN, bold=True, align=right)
            # 控盘（新增列）
            from services.control_profile import ctrl_cell, ctrl_tooltip
            _ci = r.get('ctrl')
            _ct, _cc = ctrl_cell(_ci)
            set_table_item(self.table, row, T_CTRL, _ct, _cc, align=center)
            self.table.item(row, T_CTRL).setToolTip(ctrl_tooltip(_ci))
            # 悬停：把口径写清楚
            it = self.table.item(row, T_NAME)
            if it is not None:
                it.setToolTip(
                    f"{r['name']} {r['code']}\n"
                    f"入选板块：{r['board']}（{r['kind']}）\n"
                    f"入选日：{r['trade_date']}  入选时涨幅 {r['pct0']:+.2f}%  "
                    f"量比 {r['vol_ratio']:.2f}\n"
                    f"入选价 P0：{r['base_price']:.2f}（入选当日收盘价）\n"
                    f"5日盈亏：{r['r5'] if r['r5'] is not None else '持有中'}\n"
                    f"30日盈亏：{r['r30'] if r['r30'] is not None else '持有中'}\n"
                    f"累计盈亏：{r['cum'] if r['cum'] is not None else '--'}\n\n"
                    f"距MA20：{r['ma20'] and ('%.2f' % r['ma20']) or '--'}"
                    f"（现价{'在' if (r.get('ma20') and r['cur_price'] >= r['ma20']) else '不在'}"
                    f"均线上）\n"
                    f"口径：非涨停 ｜ 涨幅1~9% ｜ 量比≥1.2 ｜ 价≥6元 ｜ "
                    f"站上MA20\n盈亏 = (T+N 收盘 / P0 - 1)，机械持有，"
                    f"不含止盈止损")

    # ------------------------------------------------------------------
    # 实时价：只刷当前显示的 ≤300 只
    # ------------------------------------------------------------------
    def _start_timer(self):
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(_RT_INTERVAL)
            self._timer.timeout.connect(self._tick)
        self._timer.start(_RT_INTERVAL)

    def stop_timer(self):
        if self._timer is not None:
            self._timer.stop()

    def _tick(self):
        if not self.isVisible() or not self._shown:
            return
        codes = [r['code'] for r in self._shown if r.get('code')]
        if not codes:
            return
        self._rt_token += 1
        tok = self._rt_token

        def worker():
            try:
                from utils.http_market_data import get_realtime_quotes_http
                self._rt_ready.emit(tok, get_realtime_quotes_http(codes) or {})
            except Exception as e:
                print(f'[可介入追踪] 实时行情失败: {e}', flush=True)

        threading.Thread(target=worker, daemon=True).start()

    def _on_rt(self, tok, quotes):
        if tok != self._rt_token or not self.isVisible() or not quotes:
            return
        for row, r in enumerate(self._shown):
            q = quotes.get(r['code'])
            if not q:
                continue
            try:
                px = float(q.get('price') or 0)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            r['cur_price'] = px
            it = self.table.item(row, T_NOW)
            if it is not None:
                it.setText(f'{px:.2f}')
            # 距 MA20% 跟着实时价一起刷新（MA20 当日不变）
            ig = self.table.item(row, T_M20)
            if ig is not None:
                _m20r = r.get('ma20')
                if _m20r and _m20r > 0:
                    _g20r = (px - _m20r) / _m20r * 100.0
                    ig.setText(f'{_g20r:+.2f}%')
                    ig.setForeground(QColor(_UP if _g20r >= 0 else _DN))
                else:
                    ig.setText('--')
            bp = r['base_price']
            if bp > 0 and r.get('cum') is not None:
                # 只在有持有期时更新累计盈亏（当天刚入选的保持「持有中」）
                cum = round((px - bp) / bp * 100.0, 2)
                if abs(cum) < 0.005:
                    cum = 0.0
                r['cum'] = cum
                ic = self.table.item(row, T_CUM)
                if ic is not None:
                    ic.setText(f'{cum:+.2f}%')
                    ic.setForeground(QColor(_UP if cum >= 0 else _DN))

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_cell_clicked(self, row, col):
        if col != T_NAME or row >= len(self._shown):
            return
        r = self._shown[row]
        if r.get('code'):
            self.stock_clicked.emit(str(r['code']), str(r.get('name') or ''))

    def _on_context_menu(self, pos):
        row = self.table.rowAt(int(pos.y()))
        if row < 0 or row >= len(self._shown):
            return
        menu = QMenu(self.table)
        act = menu.addAction('❌ 从追踪中移除')
        if menu.exec(self.table.viewport().mapToGlobal(pos)) == act:
            self._remove(row)

    def _remove(self, row):
        r = self._shown[row]
        code, td = r['code'], r['trade_date']

        def worker():
            try:
                from services.picks_tracking_service import TRACK_DB
                import duckdb
                con = duckdb.connect(TRACK_DB)
                try:
                    con.execute('DELETE FROM picks_tracking '
                                'WHERE trade_date=? AND code=?', [td, code])
                finally:
                    con.close()
                print(f'[可介入追踪] 已移除 {td} {code} {r.get("name", "")}',
                          flush=True)
            except Exception as e:
                print(f'[可介入追踪] 移除失败: {e}', flush=True)

        threading.Thread(target=worker, daemon=True).start()
        self._rows = [x for x in self._rows
                      if not (x['code'] == code and x['trade_date'] == td)]
        self._shown = [x for x in self._rows[:_SHOW_MAX]]
        self._render_stat()
        self._render()
