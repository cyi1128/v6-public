# -*- coding: utf-8 -*-
"""
📈 市场节奏（「盘中机会 + 金铲子 + 板块异动」三模块合并后的唯一模块）

单列纵向、不分左右分栏。三个 Tab，各回答一个不同的问题：

  Tab1「市场节奏」—— 现在市场在干嘛？
      题材 / 主线 / 状态 / 今昨 / 连续 / 最高板 / 龙头 / 题材内强势股
      / 近10日家数 / 同簇题材
      状态机：🆕首日启动 ♻️复活 🔥发酵中 ⚡持续 🚀高潮 📉退潮 💀熄火
      「近10日家数」把每个题材自己的多日家数序列写在行内（旧→新），
      哪天起、哪天断、退了多久，一行看完 —— 这就是「记住哪天涨了哪个题材」。
      顶部黄条给出轮动方向：钱从哪些方向走、走到哪些方向去。
      数据源 services/market_rhythm_engine（只读 data/limit_up_reason.db）。

  Tab2「可介入」—— 我能下手买什么？
      板块/题材 / 家数 / 均涨幅 / 龙头 / 可介入 / 成分股
      「可介入」= 该板块里还没涨停、但已经在动的票
      （非涨停 ｜ 涨幅1~9% ｜ 量比≥1.2 ｜ 现价≥MA20）—— 这一列才是能下手的，
      「成分股」列是已经封板的龙头，只能看。
      数据源 services/board_anomaly_engine。
      题材爆发(家数≥3)推送企业微信，同一题材 30 分钟去重，仅交易时段。

  Tab3「可介入」追踪 —— 这个信号到底准不准？
      把每天筛出的可介入候选入库（收盘后写，P0=当日收盘价），
      跟踪入选后 5 个交易日 / 30 个交易日的盈亏与累计盈亏。
      数据在 data/cache/picks_tracking.duckdb，
      收益计算在 services/picks_tracking_service.py（只读 kline_cache）。

三种 Tab 只在切过去时才算数据（追踪页切回即停表），不占 CPU。
涨停库由 services/limit_up_collector.py 每日写入，已挂进「盘后扫描_波段四模式.bat」。

注：原「盘中机会」和「金铲子(实时)」的界面与筛选逻辑已按用户要求移除。
    但「异动检测」那一段保留在 main.py 的后台线程里（只喂 anchor_tracker，
    不显示任何界面）—— 否则盘后「基准阳跟踪 / 日K建仓」会失去信号源。
"""
import threading
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QLabel, QVBoxLayout, QHBoxLayout, QWidget,
                             QHeaderView, QPushButton, QButtonGroup)

from .base import (
    BattleModuleBase, make_table, set_table_item,
    BC, HeaderSorter, CTRL_COL_TITLE,
)

# ----------------------------------------------------------------------
# Tab1 市场节奏
# ----------------------------------------------------------------------
(C_THEME, C_LINE, C_STATE, C_YD, C_RUN, C_LBC,
 C_LEAD, C_LADDER, C_TREND, C_CLUSTER) = range(10)
HEADERS = ['题材', '主线', '状态', '今/昨', '连续', '最高板',
           '龙头', '题材内强势股', '近10日家数', '同簇题材']
# 汉字约 14px / 字符约 12px：
#   题材 7字=110 | 主线 5字=84 | 状态 🆕首日启动=98 | 今/昨 12/9=62
#   连续 4日=48 | 最高板 12板=52 | 龙头 德才股份2板=122
#   强势股 5只×9字=330（拉伸列）| 趋势 10个数字=205 | 同簇 3题材=180
GRID = [112, 84, 98, 62, 48, 52, 122, 330, 205, 180]

STATE_COLOR = {
    '🆕首日启动': BC.BLUE,
    '♻️复活': BC.PURPLE,
    '🔥发酵中': BC.RED,
    '⚡持续': BC.RED,
    '🚀高潮': BC.ORANGE,
    '📉退潮': BC.GREEN,
    '💀熄火': BC.FLAT,
    '·零星': BC.FLAT,
}

TREND_DAYS = 10

# ----------------------------------------------------------------------
# Tab2 可介入
# ----------------------------------------------------------------------
(P_BOARD, P_COUNT, P_AVG, P_LEAD, P_PICKS, P_CTRL, P_MEMBERS) = range(7)
P_HEADERS = ['板块/题材', '家数', '均涨幅', '龙头', '可介入',
             CTRL_COL_TITLE, '成分股']
#   板块/题材 最长 7 字=104 | 家数 10=46 | 均涨幅 +10.92%=100
#   龙头 海峡创新 +20.0%=150 | 可介入 3只（含控盘分，全量在悬停）
#   控盘 该题材候选里最高分=100 | 成分股 拉伸
P_GRID = [104, 46, 100, 150, 470, 104, 260]


# ----------------------------------------------------------------------
# 控盘度（与 日K建仓 / 自选 / 竞价 / 今日涨停 / 分时做T / 追踪 同一套）
# 这两个 Tab 是「按题材成行」，行里只有成分股名单，所以控盘落两个地方：
#   ① 单元格内联：个股名字后面直接跟控盘分（Tab1 连板梯队 / Tab2 可介入候选）
#   ② Tab2 新增「控盘」列：该题材可介入候选里控盘分最高者
# 全部只读 control_profile 的内存缓存（cached_only），UI 线程绝不计算；
# 缺的由 MarketRhythmWidget._ctrl_async_fill() 在后台补算后重绘一次。
# ----------------------------------------------------------------------
def _ctrl_lookup(codes):
    """{code: info}，**只读已有缓存、绝不计算**（UI 线程安全）。"""
    try:
        from services.control_profile import get_ctrl_map
        _cs = [str(c) for c in (codes or []) if c]
        if not _cs:
            return {}
        return get_ctrl_map(_cs, cached_only=True) or {}
    except Exception:
        return {}


def _ctrl_inline(info):
    """单元格内联文本：'88候选' / '88'；没算出或没数据返回 ''（不占位）。"""
    if not info or not info.get('ok') or info.get('score') is None:
        return ''
    try:
        from services.control_profile import ctrl_cell
        _t, _c = ctrl_cell(info)
        _t = str(_t or '')
        return '' if _t in ('', '--') else _t
    except Exception:
        return ''


def _ctrl_one_line(info):
    """tooltip 一行：'88.3（wash）'；没有则 '--'。"""
    if not info or not info.get('ok') or info.get('score') is None:
        return '--'
    try:
        return '%.1f（%s）' % (float(info['score']), info.get('stage') or '--')
    except Exception:
        return '--'


def _ctrl_pos_txt(info):
    """tooltip 尾巴：' ｜ 位置 32% ｜ 候选'；没有就不加。"""
    if not info or not info.get('ok') or info.get('score') is None:
        return ''
    out = ''
    try:
        if info.get('pos') is not None:
            out += ' ｜ 位置 %.0f%%' % (float(info['pos']) * 100)
        from services.control_profile import ctrl_cell
        _t, _c = ctrl_cell(info)
        if '·' in str(_t):
            out += ' ｜ ' + str(_t).split('·', 1)[1]
    except Exception:
        pass
    return out


def _ladder_ctrl(rows):
    """Tab1：连板梯队里出现的个股 -> (内联映射, info 映射)。"""
    codes = []
    for b in (rows or []):
        for x in (b.get('ladder') or []):
            _c = str(x.get('code') or '')
            if _c:
                codes.append(_c)
    m = _ctrl_lookup(codes)
    return ({c: _ctrl_inline(i) for c, i in m.items()}, m)


def _picks_ctrl(r):
    """Tab2 一行（一个板块）可介入候选的 [(code, info)]，只读缓存。"""
    picks = r.get('picks') or []
    codes = [str(p[0]) for p in picks if p and p[0]]
    m = _ctrl_lookup(codes)
    return [(str(p[0]), m.get(str(p[0]))) for p in picks if p and p[0]]


def _top_ctrl(pairs):
    """[(code, info)] 里挑控盘分最高的一条 -> (code, info) 或 None。"""
    best = None
    for c, i in (pairs or []):
        try:
            if i and i.get('ok') and i.get('score') is not None:
                if best is None or float(i['score']) > float(best[1]['score']):
                    best = (c, i)
        except Exception:
            continue
    return best


def _top_ctrl_score(r):
    """「控盘」列排序用：候选里最高控盘分；没有则 -1。"""
    b = _top_ctrl(_picks_ctrl(r))
    try:
        return float(b[1]['score']) if b else -1.0
    except Exception:
        return -1.0


class MarketRhythmWidget(BattleModuleBase):
    # 点股票 -> 通知主窗口跳个股分析(code, name)
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__('📈 市场节奏', parent)
        self._data = {}
        self._board_meta = {}
        self._rows = []          # Tab1 行
        self._regime = {}        # V18 三轴状态闸门读数
        self._pick_rows = []     # Tab2 行
        self._tab_active = 0
        self._busy = False
        self._lock = threading.Lock()
        self._pushed = {}
        self._persist_date = ''
        self._build_content()
        QTimer.singleShot(500, self.refresh)
        # 涨停库盘后写入，盘中基本不变；60 秒足够
        self.start_refresh(60000)

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    def _build_content(self):
        self._setup_tab_buttons()

        # ================= Tab1：市场节奏 =================
        self._rhythm_page = QWidget()
        _r = QVBoxLayout(self._rhythm_page)
        _r.setContentsMargins(0, 0, 0, 0)
        _r.setSpacing(4)

        self.market_label = QLabel('数据：--')
        self.market_label.setStyleSheet(
            'background:#f5f5f5;border-radius:4px;padding:2px 8px;'
            'color:#666;font-size:11px;')
        _r.addWidget(self.market_label)

        self.rot_label = QLabel('轮动方向：--')
        self.rot_label.setStyleSheet(
            'background:#fff8e1;border:1px solid #ffe082;border-radius:4px;'
            'padding:3px 8px;color:#8a6d00;font-size:12px;font-weight:bold;')
        _r.addWidget(self.rot_label)

        self.table = make_table(len(HEADERS), HEADERS)
        for i, w in enumerate(GRID):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setSectionResizeMode(
            C_LADDER, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.cellClicked.connect(self._on_rhythm_cell)
        _r.addWidget(self.table, 1)
        self.content_layout.addWidget(self._rhythm_page, 1)

        self.sorter = HeaderSorter(
            self.table,
            keys={C_THEME: lambda r: r['theme'],
                  C_STATE: lambda r: r['state'],
                  C_YD: lambda r: r['count'],
                  C_RUN: lambda r: r['run'],
                  C_LBC: lambda r: r['lbc_max'],
                  C_TREND: lambda r: r['count']},
            getter=lambda: self._rows,
            render=self._render_rhythm_rows,
        )

        # ================= Tab2：可介入 =================
        self._pick_page = QWidget()
        _p = QVBoxLayout(self._pick_page)
        _p.setContentsMargins(0, 0, 0, 0)
        _p.setSpacing(4)

        self.pick_label = QLabel('数据：--')
        self.pick_label.setStyleSheet(
            'background:#f5f5f5;border-radius:4px;padding:2px 8px;'
            'color:#666;font-size:11px;')
        _p.addWidget(self.pick_label)

        self.pick_table = make_table(len(P_HEADERS), P_HEADERS)
        for i, w in enumerate(P_GRID):
            self.pick_table.setColumnWidth(i, w)
        self.pick_table.horizontalHeader().setSectionResizeMode(
            P_MEMBERS, QHeaderView.ResizeMode.Stretch)
        self.pick_table.horizontalHeader().setStretchLastSection(False)
        self.pick_table.cellClicked.connect(self._on_pick_cell)
        _p.addWidget(self.pick_table, 1)
        self.content_layout.addWidget(self._pick_page, 1)
        self._pick_page.setVisible(False)

        self.pick_sorter = HeaderSorter(
            self.pick_table,
            keys={P_BOARD: lambda r: r['name'],
                  P_COUNT: lambda r: r['count'],
                  P_AVG: lambda r: r['avg_pct'],
                  P_CTRL: _top_ctrl_score},
            getter=lambda: self._pick_rows,
            render=self._render_pick_rows,
        )

        # ================= Tab3：可介入追踪 =================
        from .picks_track_widget import PicksTrackWidget
        self._track_widget = PicksTrackWidget(self)
        self._track_widget.stock_clicked.connect(self.stock_clicked.emit)
        self.content_layout.addWidget(self._track_widget, 1)
        self._track_widget.setVisible(False)

    # ------------------------------------------------------------------
    # Tab 切换（照竞价追踪的 QButtonGroup 互斥 + checkable 按钮做法）
    # ------------------------------------------------------------------
    def _setup_tab_buttons(self):
        try:
            title_bar_layout = self._card_frame.layout().itemAt(0).layout()
        except Exception:
            return
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

        labels = ['市场节奏', '可介入', '追踪']
        self._tab_btns = []
        for i, txt in enumerate(labels):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(self._tab_style_checked if i == 0
                            else self._tab_style_normal)
            self._tab_group.addButton(b, i)
            title_bar_layout.insertWidget(i + 1, b)
            self._tab_btns.append(b)
        self._tab_btns[0].setChecked(True)
        self._tab_group.idClicked.connect(self._switch_tab)

    def _switch_tab(self, idx):
        """0=市场节奏（题材状态） 1=可介入（能下手的票） 2=追踪（历史盈亏）。
        切到追踪才拉库算收益并启实时价；切走立即停表释放 CPU。"""
        self._tab_active = idx
        for i, b in enumerate(self._tab_btns):
            b.setStyleSheet(self._tab_style_checked if i == idx
                            else self._tab_style_normal)
        self._rhythm_page.setVisible(idx == 0)
        self._pick_page.setVisible(idx == 1)
        self._track_widget.setVisible(idx == 2)
        if idx == 2:
            self._track_widget.refresh()
        elif idx == 1:
            self._render_pick_rows(self._pick_rows)
        else:
            self._render_rhythm_rows(self._rows)
        if idx != 2:
            self._track_widget.stop_timer()

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    def refresh(self, force=False):
        with self._lock:
            if self._busy:
                return
            self._busy = True

        def work():
            out = {}
            try:
                from services.market_rhythm_engine import get_rhythm
                out['rhythm'] = get_rhythm(force=bool(force))
            except Exception as e:
                out['rhythm_err'] = str(e)[:200]
            try:
                from services.regime_gate import compute as _rg
                out['regime'] = _rg()
            except Exception as e:
                out['regime_err'] = str(e)[:200]
            try:
                from services.board_anomaly_engine import (get_board_anomaly,
                                                           get_flat_rows)
                d = get_board_anomaly()
                out['boards'] = get_flat_rows(d)
                out['board_meta'] = d
            except Exception as e:
                out['board_err'] = str(e)[:200]
            return out

        def ok(d):
            self._busy = False
            self._apply(d)
            self.set_update_time()

        def fail(msg):
            self._busy = False
            self.set_status('节奏加载失败: %s' % str(msg)[:80])

        self.run_async(work, ok, fail)

    def _apply(self, d):
        self._regime = d.get('regime') or {}
        # ---- Tab1 ----
        rh = d.get('rhythm') or {}
        if rh.get('ok'):
            self._data = rh
            self._render_rhythm(rh)
        else:
            self.set_status('节奏数据不可用: %s'
                            % (rh.get('error') or d.get('rhythm_err') or '空'))
        # ---- Tab2 ----
        rows = d.get('boards')
        self._board_meta = d.get('board_meta') or {}
        if rows is not None:
            self._pick_rows = rows
            self._render_pick_rows(rows)
            try:
                self._persist_picks(rows)
            except Exception as e:
                print(f'[市场节奏] 追踪入库异常: {e}', flush=True)
            try:
                self._push_boards(rows)
            except Exception as e:
                print(f'[市场节奏] 推送异常: {e}', flush=True)
        else:
            self.set_status('可介入数据不可用: %s' % (d.get('board_err') or '空'))

        # 控盘度：上面两个 render 已经把「缓存里已有的」画出来了，
        # 这里再后台把没算过的补齐，完成后回 UI 线程重绘一次（不阻塞界面）。
        self._ctrl_async_fill()

    # ------------------------------------------------------------------
    # Tab1 渲染
    # ------------------------------------------------------------------
    def _render_rhythm(self, d):
        rot = d.get('rotation', {})
        self.rot_label.setText('轮动方向：%s' % (rot.get('summary') or '--'))
        mem = d.get('memory') or {}
        dates = mem.get('dates') or []
        span = ('%s→%s' % (dates[0], dates[-1])) if dates else '--'
        self.market_label.setText(
            '数据：%s  ｜ 涨停 %d 家 ｜ 最高 %d 板 ｜ 板块 %d 个'
            '  ｜ 近10日家数：%s（旧→新）' % (
                d.get('date', '--'), d.get('lu_count', 0),
                d.get('max_lbc', 0), d.get('theme_count', 0), span))
        _rg = getattr(self, '_regime', None) or {}
        if _rg.get('state'):
            self.market_label.setText(
                self.market_label.text()
                + '  ｜ 状态闸门：%s（%s）' % (_rg.get('state', ''),
                                          _rg.get('note', '')))
        self._rows = list(d.get('boards', []))
        if self._tab_active == 0:
            self._render_rhythm_rows(self._rows)

    def _render_rhythm_rows(self, rows):
        # 控盘度：只读缓存（没算过的先空着，后台补完会重绘）
        _ck, _cki = _ladder_ctrl(rows)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for r, b in enumerate(rows):
            set_table_item(self.table, r, C_THEME, b['theme'],
                           color=BC.RED if not b.get('is_attribute') else BC.FLAT,
                           bold=True)
            set_table_item(self.table, r, C_LINE, b.get('mainline') or '—',
                           color=BC.PURPLE)
            set_table_item(self.table, r, C_STATE, b['state'],
                           color=STATE_COLOR.get(b['state'], BC.TEXT), bold=True)
            set_table_item(self.table, r, C_YD,
                           '%d/%d' % (b['count'], b['prev_count']),
                           color=BC.RED if b['count'] > b['prev_count']
                           else (BC.GREEN if b['count'] < b['prev_count']
                                 else BC.TEXT),
                           align=Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, r, C_RUN, '%d日' % b['run'],
                           align=Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, r, C_LBC, '%d板' % b['lbc_max'],
                           color=BC.ORANGE if b['lbc_max'] >= 3 else BC.TEXT,
                           bold=b['lbc_max'] >= 3,
                           align=Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, r, C_LEAD,
                           '%s%d板' % (b['lead'], b['lead_lbc']),
                           color=BC.CYAN, bold=True)

            lad = b.get('ladder') or []
            _lparts = []
            for x in lad[:5]:
                _lt = _ck.get(str(x.get('code') or '')) or ''
                _lparts.append('%s%d板%s' % (x['name'], x['lbc'],
                                             (' ' + _lt) if _lt else ''))
            txt = ' '.join(_lparts)
            if len(lad) > 5:
                txt += ' …共%d只' % len(lad)
            set_table_item(self.table, r, C_LADDER, txt)
            self.table.item(r, C_LADDER).setToolTip(
                '\n'.join('%s %s %d板 %s  %s%s' % (
                    x['name'], x['code'], x['lbc'], x['time'] or '',
                    x['reason'] or '',
                    ('  ｜ 控盘 ' + _ctrl_one_line(
                        _cki.get(str(x.get('code') or ''))))
                    if _cki.get(str(x.get('code') or '')) else '')
                    for x in lad[:15]) or '—')

            tr = (b.get('trend') or [])[-TREND_DAYS:]
            set_table_item(self.table, r, C_TREND,
                           ' '.join(str(x) if x else '·' for x in tr),
                           color=BC.TEXT, bold=(b['count'] >= 3),
                           align=Qt.AlignmentFlag.AlignCenter)
            self.table.item(r, C_TREND).setToolTip(
                '近%d个交易日家数（旧→新，· = 当天没成板块）' % len(tr))

            set_table_item(self.table, r, C_CLUSTER,
                           '、'.join(b.get('cluster') or []) or '—',
                           color=BC.FLAT)
            self.table.item(r, C_THEME).setToolTip(
                '近%d日家数: %s' % (len(b.get('trend') or []),
                                 ' → '.join(str(x) for x in
                                            (b.get('trend') or []))))

    # ------------------------------------------------------------------
    # Tab2 渲染
    # ------------------------------------------------------------------
    def _render_pick_rows(self, rows):
        rows = rows or []
        self.pick_table.clearSpans()
        self.pick_table.setRowCount(len(rows))
        center = Qt.AlignmentFlag.AlignCenter
        left = Qt.AlignmentFlag.AlignLeft
        for row, r in enumerate(rows):
            set_table_item(self.pick_table, row, P_BOARD, r['name'],
                           BC.RED, bold=True, align=left)
            set_table_item(self.pick_table, row, P_COUNT, str(r['count']),
                           BC.BLUE, bold=True, align=center)
            set_table_item(self.pick_table, row, P_AVG,
                           f"{r['avg_pct']:+.2f}%",
                           BC.RED if r['avg_pct'] >= 0 else BC.GREEN,
                           bold=True, align=center)
            # ---- 龙头：首封最早 > 连板最高 > 封单最大 ----
            dragons = r.get('dragons') or []
            lead_name = r.get('lead_name') or ''
            lead_pct = r.get('lead_pct')
            if lead_pct is None:
                lead_pct = r.get('max_pct', 0.0)
            set_table_item(self.pick_table, row, P_LEAD,
                           f"{lead_name} {lead_pct:+.1f}%" if lead_name else '--',
                           BC.TEXT_PRIMARY, bold=True, align=left)
            _it = self.pick_table.item(row, P_LEAD)
            if _it is not None:
                _it.setData(Qt.ItemDataRole.UserRole, r.get('lead_code', '') or '')
                _it.setData(Qt.ItemDataRole.UserRole + 1, lead_name)
                if dragons:
                    d0 = dragons[0]
                    _tip = ('【情绪龙头】%s %+.2f%%\n'
                            '判定依据：首封 %s（%s）｜ %d连板 ｜ '
                            '封单 %.2f亿\n'
                            '　　　　　封成比 %.2f · 封单强度 %.2f%%%s%s\n'
                            '（排序：连板身位 > 烂板沉底 > 封板时段 > '
                            '封成比 > 封单强度）'
                            % (d0['name'], d0['pct'], d0['time'] or '--',
                               d0.get('slot_name') or '--', d0['lbc'],
                               d0['fund'] / 1e8,
                               d0.get('ratio') or 0.0,
                               (d0.get('strength') or 0.0) * 100,
                               (' ｜ 炸板%d次' % d0['zbc']) if d0['zbc'] else '',
                               '  ⚠烂板' if (d0['lbc'] >= 2
                                             and (d0.get('ratio') or 0.0) < 0.10)
                               else ''))
                    _e = r.get('entry')
                    if _e:
                        _tip += ('\n\n【次日接力参考】%s %s\n'
                                 '　　%d板 ｜ 首封 %s（%s）\n'
                                 '　　封单 %.2f亿 · 封成比 %.2f · 强度 %.2f%%%s'
                                 % (_e['name'], _e['code'], _e['lbc'],
                                    _e['time'] or '--',
                                    _e.get('slot_name') or '--',
                                    _e['fund'] / 1e8,
                                    _e.get('ratio') or 0.0,
                                    (_e.get('strength') or 0.0) * 100,
                                    (' ｜ 炸板%d次' % _e['zbc'])
                                    if _e.get('zbc') else ''))
                    _tip += ('\n\n情绪龙头 = 这个题材谁最强（判断高度）\n'
                             '接力参考 = 明天能打的（低位 + 早封 + 封单强）')
                    _it.setToolTip(_tip)
            # ---- 可介入：还没涨停、但已经在动的票 ----
            picks = r.get('picks') or []
            _pc = _picks_ctrl(r)
            _pcm = {c: i for c, i in _pc}
            if picks:
                _pbody = []
                for p in picks[:3]:
                    _pt = _ctrl_inline(_pcm.get(str(p[0])))
                    _pbody.append('%s %+.1f%%%s%s'
                                  % (p[1], p[2],
                                     (' ' + _pt) if _pt else '',
                                     '✅' if (len(p) > 10 and p[10]) else ''))
                set_table_item(self.pick_table, row, P_PICKS,
                               '  '.join(_pbody), BC.CYAN, align=left)
                _pi = self.pick_table.item(row, P_PICKS)
                if _pi is not None:
                    _pi.setData(Qt.ItemDataRole.UserRole, picks[0][0] or '')
                    _pi.setData(Qt.ItemDataRole.UserRole + 1, picks[0][1] or '')
                    _lines = []
                    for p in picks:
                        _t = ('  %s %s  %+.2f%%  量比%.2f  现价%.2f'
                              % (p[1], p[0], p[2], p[3], p[4]))
                        if len(p) > 5 and p[5] is not None:
                            _t += '  距MA20 %+.1f%%' % p[5]
                        if len(p) > 9 and p[6] is not None:
                            _t += ('\n      成交额 %.2f亿 ｜ 流通市值 %.0f亿 ｜ '
                                   '换手 %.2f%%' % (p[6], p[7], p[8]))
                        if len(p) > 9 and p[9] is not None:
                            _t += ' ｜ VWAP偏离 %+.2f%%' % p[9]
                            _t += ('　✅算法单痕迹' if (len(p) > 10 and p[10])
                                   else '')
                        _ci = _pcm.get(str(p[0]))
                        _t += ('\n      控盘 %s%s'
                               % (_ctrl_one_line(_ci), _ctrl_pos_txt(_ci)))
                        _lines.append(_t)
                    _pi.setToolTip(
                        '【可介入】%s 里还没涨停、但已在动的标的：\n' % r['name']
                        + '\n'.join(_lines)
                        + '\n\n口径：非涨停 ｜ 涨幅 1~9% ｜ 量比≥1.2 ｜ '
                          '现价≥MA20\n'
                          '机构门槛：成交额 ≥2 亿 ｜ 流通市值 ≥20 亿\n'
                          '✅ = |最新价 − VWAP| ≤0.5% 且量比 ≥1.5，'
                          '算法单执行痕迹（价格贴当日均价走）\n'
                          '（点此格跳转候选第一名个股分析）')
            else:
                set_table_item(self.pick_table, row, P_PICKS, '—',
                               BC.TEXT3, align=left)
                _pi = self.pick_table.item(row, P_PICKS)
                if _pi is not None:
                    _pi.setToolTip('该板块成分池里暂无符合「未涨停 + 涨幅1~9%'
                                   ' + 量比≥1.2 + 站上MA20 + 成交额≥2亿'
                                   ' + 流通市值≥20亿」的标的')
            # ---- 控盘：该题材可介入候选里控盘分最高的一只 ----
            _best = _top_ctrl(_pc)
            if not _pc:
                set_table_item(self.pick_table, row, P_CTRL, '—', BC.TEXT3,
                               align=center)
                self.pick_table.item(row, P_CTRL).setToolTip(
                    '该板块今日没有「可介入」候选，无可比控盘度\n'
                    '（可介入口径：非涨停 ｜ 涨幅 1~9% ｜ 量比≥1.2 ｜ '
                    '现价≥MA20 ｜ 成交额≥2亿 ｜ 流通市值≥20亿 ｜ 股价≥6元）')
            else:
                from services.control_profile import (ctrl_cell as _ccell,
                                                      NO_DATA_TEXT as _NDT,
                                                      NO_DATA_COLOR as _NDC)
                if _best is None:
                    _ct, _cc = _NDT, _NDC
                else:
                    _ct, _cc = _ccell(_best[1])
                set_table_item(self.pick_table, row, P_CTRL, _ct, _cc,
                               bold=True, align=center)
                _bname = next((p[1] for p in picks
                               if _best and str(p[0]) == _best[0]), '')
                _ctip = ['【控盘】该题材可介入候选里控盘分最高：%s%s'
                         % (_bname, (' ' + _ctrl_one_line(_best[1]))
                            if _best else ''),
                         '口径：与 日K建仓 / 自选 / 竞价 / 今日涨停 / 分时做T / '
                         '追踪 完全同一套 —— 同一份 estimate_control_score + '
                         '同一份阈值；只读本地K线缓存，无网络兜底。',
                         '逐只候选（控盘分（阶段）｜位置｜标签）：']
                for p in picks:
                    _pi2 = _pcm.get(str(p[0]))
                    _ctip.append('  %s %s  %s%s'
                                 % (p[1], str(p[0]), _ctrl_one_line(_pi2),
                                    _ctrl_pos_txt(_pi2)))
                _ctip.append('分越高 = 筹码越集中；带「出货」标签要警惕高位。'
                             '（控盘列可点表头排序）')
                self.pick_table.item(row, P_CTRL).setToolTip('\n'.join(_ctip))
            # ---- 成分股：前 3 名标「龙一/龙二/龙三」----
            _rank = {}
            for _i, _d in enumerate(dragons[:3]):
                _rank[_d['code']] = ('龙一', '龙二', '龙三')[_i]
            _parts = []
            for m in r['members'][:8]:
                _tag = _rank.get(m[0])
                _parts.append(f"{_tag} {m[1]}" if _tag else m[1])
            set_table_item(self.pick_table, row, P_MEMBERS, '  '.join(_parts),
                           BC.TEXT, align=left)
            self.pick_table.item(row, P_MEMBERS).setToolTip(
                '  '.join('%s%s %+.2f%%' % (
                    ('[' + _rank[m[0]] + ']') if _rank.get(m[0]) else '',
                    m[1], m[2]) for m in r['members']))
            self.pick_table.item(row, P_BOARD).setToolTip(
                '%s（%s）\n今日涨停 %d 家，均涨 %+.2f%%，最高 %+.2f%%'
                % (r['name'], r['kind'], r['count'], r['avg_pct'], r['max_pct'])
                + (f"\n该行业全市场均涨 {r['all_avg_pct']:+.2f}%（样本 "
                   f"{r['all_count']} 只）"
                   if r.get('all_avg_pct') is not None else ''))

        _n_pick = sum(len(r.get('picks') or []) for r in rows)
        _n_row = sum(1 for r in rows if r.get('picks'))
        meta = (getattr(self, '_board_meta', None) or {})
        dt = meta.get('ludate') or meta.get('date') or '--'
        if len(str(dt)) == 8:
            dt = str(dt)[4:6] + '-' + str(dt)[6:]
        self.pick_label.setText(
            '涨停名单：%s ｜ 今日涨停：%s家 ｜ 可介入 %d 只（%d 个板块）'
            ' ｜ 口径：非涨停 ｜ 涨幅1~9%% ｜ 量比≥1.2 ｜ 现价≥MA20'
            ' ｜ 机构门槛：成交额≥2亿·流通市值≥20亿 ｜ ✅=算法单痕迹'
            % (dt, meta.get('lu_count', '--'), _n_pick, _n_row))
        _rg = getattr(self, '_regime', None) or {}
        if _rg.get('state'):
            self.pick_label.setText(
                self.pick_label.text() + '  ｜ 闸门：%s' % _rg.get('state', ''))

    # ------------------------------------------------------------------
    # 追踪入库（收盘后写，P0=当日收盘价）
    # ------------------------------------------------------------------
    def _persist_picks(self, rows):
        """把当天各板块的「可介入」候选幂等写入追踪库（后台线程）。

        只在 15:00 之后写：P0（入选价）要取当日收盘价，盘中价会虚增/虚减收益。
        每天只写一次；写入本身在 services/picks_tracking_service 里幂等，
        同一 (交易日, 代码) 不会重复，P0 一旦落库就不再被覆盖。
        """
        if not rows:
            return
        try:
            from utils.trade_calendar import is_trading_day
            now = datetime.now()
            if not is_trading_day(now):
                return
            if now.strftime('%H:%M') < '15:00':
                return
            today = now.strftime('%Y-%m-%d')
            if self._persist_date == today:
                return
            self._persist_date = today
        except Exception as e:
            print(f'[市场节奏] 追踪入库前置检查失败: {e}', flush=True)
            return

        snapshot = [dict(r) for r in rows]

        def _w():
            try:
                from services.picks_tracking_service import persist_picks
                persist_picks(snapshot, today)
            except Exception as e:
                print(f'[市场节奏] 可介入追踪入库失败: {e}', flush=True)

        threading.Thread(target=_w, daemon=True).start()

    # ------------------------------------------------------------------
    # 板块级推送（题材/行业爆发）
    # ------------------------------------------------------------------
    _PUSH_MIN_STOCK = 3      # 至少 3 家才推，避免 2 家噪音刷屏
    _PUSH_COOLDOWN = 1800    # 同一板块 30 分钟只推一次

    def _push_boards(self, rows):
        if not rows:
            return
        from services.board_anomaly_engine import is_trading_now
        if not is_trading_now():
            return
        # V18 三轴状态闸门：冰点期只记录不推送
        try:
            from services.regime_gate import compute as _rg
            _r = _rg()
            if not _r.get('push', True):
                print('[市场节奏] 状态闸门 %s：本轮只记录不推送'
                      % _r.get('state', ''), flush=True)
                return
        except Exception as _e:
            print('[市场节奏] 状态闸门不可用，按放行处理: %s' % _e, flush=True)
        try:
            from services.wechat_bus import get_wechat_bus
        except Exception as e:
            print(f'[市场节奏] 推送模块不可用: {e}', flush=True)
            return
        bus = get_wechat_bus()
        now = time.time()
        sent = 0
        for r in rows:
            if r['count'] < self._PUSH_MIN_STOCK:
                continue
            key = '%s|%s' % (r['kind'], r['name'])
            if now - float(self._pushed.get(key, 0) or 0) < self._PUSH_COOLDOWN:
                continue
            mem = ' '.join(m[1] for m in r['members'][:6])
            try:
                res = bus.send_theme_rotation(
                    theme=r['name'],
                    rotation_path=mem,
                    first_stocks=[f"{r['lead_name']} {r['max_pct']:+.1f}%"],
                    new_stocks=[m[1] for m in r['members'][1:6]],
                    chain_pos=r['kind'],
                    status='今日异动',
                    reason=(f"今日涨停 {r['count']} 家，均涨 "
                            f"{r['avg_pct']:+.2f}%，最高 {r['max_pct']:+.2f}%"
                            + (f"，该行业全市场均涨 {r['all_avg_pct']:+.2f}%"
                               if r.get('all_avg_pct') is not None else '')),
                    risk='仅按涨停原因聚合，未确认资金性质')
                if res and res.get('sent'):
                    self._pushed[key] = now
                    sent += 1
                    print(f"[市场节奏] 已推送: {r['kind']} {r['name']}", flush=True)
            except Exception as e:
                print(f"[市场节奏] {r['name']} 推送失败: {e}", flush=True)
        if sent:
            print(f'[市场节奏] 本轮推送 {sent} 个板块', flush=True)

    # ------------------------------------------------------------------
    # 控盘度：后台补算（同一套算法 / 同一份阈值，跟日K建仓完全一致）
    # ------------------------------------------------------------------
    def _all_stock_codes(self):
        """两个 Tab 单元格里出现过的全部个股代码（Tab1 连板梯队 + Tab2 可介入候选）。"""
        codes = []
        for b in (self._rows or []):
            for x in (b.get('ladder') or []):
                _c = str(x.get('code') or '')
                if _c:
                    codes.append(_c)
        for b in (self._pick_rows or []):
            for p in (b.get('picks') or []):
                _c = str(p[0] or '') if p else ''
                if _c:
                    codes.append(_c)
        return list(dict.fromkeys(codes))

    def _ctrl_async_fill(self):
        """后台把还没算过的控盘补齐，完成后回 UI 线程重绘一次。

        控盘单只首次约 28ms（本地 duckdb），必须在后台线程算；
        同一交易日同一只只算一次（control_profile 内部按
        (代码, 最后一根K线日期) 缓存），所以日常刷新这里几乎立即返回。
        """
        try:
            from services.control_profile import get_ctrl_map
        except Exception:
            return
        codes = self._all_stock_codes()
        if not codes:
            return
        try:
            _m = get_ctrl_map(codes, cached_only=True)
        except Exception:
            return
        missing = [c for c in codes if _m.get(c) is None]
        if not missing:
            return

        def work():
            try:
                get_ctrl_map(missing)
            except Exception:
                pass
            return {'n': len(missing)}

        def ok(_d):
            try:
                self._render_rhythm_rows(self._rows)
                self._render_pick_rows(self._pick_rows)
            except Exception as e:
                print('[市场节奏] 控盘重绘异常: %s' % e, flush=True)

        try:
            self.run_async(work, ok, lambda _m2: None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_rhythm_cell(self, row, col):
        """点「龙头」列 -> 跳个股分析"""
        if col != C_LEAD or row < 0 or row >= len(self._rows):
            return
        b = self._rows[row]
        if b.get('lead_code'):
            self.stock_clicked.emit(str(b['lead_code']), b.get('lead', ''))

    def _on_pick_cell(self, row, col):
        """点「龙头」跳龙头，点「可介入」跳候选第一名"""
        if col not in (P_LEAD, P_PICKS):
            return
        it = self.pick_table.item(row, col)
        if it is None:
            return
        code = it.data(Qt.ItemDataRole.UserRole) or ''
        name = it.data(Qt.ItemDataRole.UserRole + 1) or ''
        if code:
            self.stock_clicked.emit(str(code), str(name) or str(code))
