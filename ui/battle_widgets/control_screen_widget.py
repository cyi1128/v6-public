# -*- coding: utf-8 -*-
"""🎛 控盘选股 —— 独立页面：全市场按「控盘标准」筛股。

页面定位
--------
前面几批把「控盘」列铺到了 9 张已有列表里（自选 / 竞价 / 涨停 / 分时做T /
日K建仓 / 市场节奏三 Tab），那些都是「其它模块选出来的股票，顺带看控盘」。
本页面反过来：**先用控盘标准筛全市场**，再决定看不看。

列（13 列）：股票名称 / 代码 / 现价 / 涨跌幅 / **涨停题材** / **主营收入** /
控盘分 / 阶段 / 位置 / 控盘提示 / 观察 / **最新公告** / 数据日。
  · 涨停题材与「日K建仓」「竞价」同源：data.limit_up_reason_db.get_last_limit_up_reason(code)
  · 主营收入 = 主营构成第一大项（东财 F10 fetch_main_business_composition，取占比最高那项）
  · 最新公告 = 最近一条公告（东财公告接口，巨潮兜底）
后两列要联网，**不进 25 秒的全市场扫描**：切到本页/扫描完成后，按当前筛选结果
在后台 6 线程补缺项（实测 0.025s/只，993 只约 25 秒），落
data/cache/ctrl_screen_extras.json（主营 TTL 30 天、公告 TTL 6 小时），
第二次打开直接命中缓存。

控盘标准（三层，全部复用项目单一来源，不另写一套）
------------------------------------------------
  控盘分  TechnicalIndicators.estimate_control_score（换手 40% + 量价 35% + 振幅 25%，位置加权）
  阶段    TechnicalIndicators.judge_wash_or_distribute（wash / distribute / unknown）
  位置    近120日位置 pos120 =（close − min120）/（max120 − min120）
  提示    band_pattern_engine._ctrl_note（阈值只在引擎里定义一处）
  观察    C4 / C6 / 试盘 / 出货形态 / 拉升 五个观察因子
  短标签  control_profile.ctrl_label（白名单，不会把观察类文案误判成「候选」）

数据来源：本地 data/cache/kline_cache.duckdb（只读，不做网络兜底）。
全市场（主板+创业板约 4400 只）一次扫描实测 23 秒（批量读库 2 秒 + 逐只算因子 21 秒），
结果落 data/cache/control_screen.json 快照，重开程序不用再等。

不改动任何选股/扫描逻辑：本页只是把已经存在的因子摆成一个筛股台。
"""
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                             QPushButton, QHeaderView)

from PyQt6.QtGui import QFontMetrics

from .base import (BC, L, HeaderSorter, BattleModuleBase, make_table,
                   set_table_item, pct_color)

import services.control_screen_service as SS

PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '主营收入', '控盘分',
                '阶段', '位置', '控盘提示', '观察', '最新公告', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_THEME, C_BIZ, C_SCORE,
 C_STAGE, C_POS, C_LABEL, C_OBS, C_ANN, C_DATE) = range(PAGE_COL_N)
# 题材串很长（如「参股算力建设（金额较小）+工程咨询+AI应用+甘肃国资」），
# 所以拉伸列给题材；「主营收入」放第一大项名 + 营收（如「智能终端 65.80亿」，170 够），
# 「最新公告」放 MM-DD + 标题（标题很长会被省略号截断，悬停看全文，260 够）。
PAGE_WIDTHS = [96, 66, 70, 74, 230, 170, 70, 58, 58, 96, 250, 260, 90]
# 列宽自适应（_autofit_columns）：上面 PAGE_WIDTHS 只是首帧初值，渲染后按
# 「这一列的内容实际需要多宽」重设 —— 短列（阶段/位置/控盘分）不占空，
# 长列（主营收入/最新公告/观察）尽量给足，目标是不出现省略号。
# 「涨停题材」仍是拉伸列（Stretch），吃掉剩余空间，所以不为它设宽度。
_HEAD_MIN_PAD = 6       # 量字结果外再留一点呼吸空间（Qt 的 hint 已含 padding）
_FIT_MAX_ROWS = 6000    # 行数 ≤ 这个值就**全量逐格量字**（3294 行实测 ~0.15s，保证不漏最长格）；
                        # 超过才退化为采样（防止将来列表上万行时卡 UI）
_FIT_SAMPLE = 400       # 退化采样时的采样行数
_THEME_MIN_W = 150      # 拉伸列（涨停题材）至少留这么宽，窗口太窄时不再压别的列
_FIT_COLS = [c for c in range(PAGE_COL_N) if c != C_THEME]
PAGE_WIDTHS_MIN = {C_NAME: 80, C_CODE: 58, C_PRICE: 60, C_PCT: 64, C_BIZ: 118,
                   C_SCORE: 56, C_STAGE: 42, C_POS: 42, C_LABEL: 56,
                   C_OBS: 56, C_ANN: 148, C_DATE: 74}
# 只有这三列是「长文本列」：给一个上限，防止某一格异常长把别的列挤没。
# 其余 9 列内容形态固定（6 位代码 / 价格 / 涨跌幅 / 控盘分 / 位置 / 日期 / 短标签），
# 按实测需要给宽即可 —— 给它们设上限反而会把内容夹断（第一批就踩了这个坑）。
PAGE_WIDTHS_MAX = {C_BIZ: 330, C_OBS: 430, C_ANN: 460}
_THEME_COLOR = '#6a1b9a'   # 与「日K建仓」题材列同色
_BIZ_COLOR = '#00695c'     # 主营收入：深青（与「日K建仓」模式列同色系）
_ANN_COLOR = '#1565c0'     # 最新公告：深蓝（与「日K建仓」触发条件列同色）
# 空态 tooltip（提为常量，验证脚本直接引用，避免两处字符串各写一份）
_BIZ_EMPTY_TIP = '尚无主营构成数据（东财 F10 未返回，或还没补数）'
_ANN_EMPTY_TIP = '尚无公告数据（东财/新浪/巨潮都没给出，或还没补数）'

_STAGE_TXT = {'distribute': '出货', 'wash': '洗盘', 'unknown': '—'}

_BTN_STYLE = (f'QPushButton{{background:{BC.BG_CARD};color:{BC.TEXT};'
              f'border:1px solid {BC.BORDER};border-radius:4px;'
              f'padding:3px 10px;font-size:11px;}}'
              f'QPushButton:hover{{color:{BC.BLUE};border-color:{BC.BLUE};}}'
              f'QPushButton:disabled{{color:{BC.TEXT3};border-color:{BC.BORDER};}}')
_COMBO_STYLE = (f'QComboBox{{background:{BC.BG_CARD};color:{BC.TEXT};'
                f'border:1px solid {BC.BORDER};border-radius:4px;'
                f'padding:2px 6px;font-size:11px;}}')
_SPIN_STYLE = (f'QDoubleSpinBox{{background:{BC.BG_CARD};color:{BC.TEXT};'
               f'border:1px solid {BC.BORDER};border-radius:4px;'
               f'padding:2px 4px;font-size:11px;}}')
_BAR_STYLE = (f'QProgressBar{{background:{BC.BG_HEADER};border:1px solid {BC.BORDER};'
              f'border-radius:3px;height:10px;text-align:center;font-size:10px;color:{BC.TEXT2};}}'
              f'QProgressBar::chunk{{background:{BC.BLUE};border-radius:2px;}}')


class ControlScreenWidget(BattleModuleBase):
    """控盘选股页（独立顶层 Tab）"""

    stock_clicked = pyqtSignal(str, str)      # code, name
    _scan_progress = pyqtSignal(int, int, str)  # done, total, msg（从扫描线程 emit）
    _fill_progress = pyqtSignal(int, int, str)  # 主营/公告补数进度（从补数线程池 emit）

    def __init__(self, parent=None):
        self._all_rows = []       # 全量扫描结果
        self._rows = []           # 当前筛选后（表格数据源，排序会原地改它）
        self._stats = {}
        self._saved_at = ''
        self._scanning = False
        self._cancel = False
        self._auto_done = False
        self._extras = {}         # {code: {biz/ann...}} 主营+公告缓存（内存态）
        self._filling = False     # 补数线程池是否在跑
        self._cancel_fill = False
        super().__init__('🎛 控盘选股', parent)
        self._build_controls()
        self._build_table()
        self._scan_progress.connect(self._on_scan_progress)
        self._fill_progress.connect(self._on_fill_progress)
        try:
            self._extras = SS.load_extras()
        except Exception:
            self._extras = {}
        self._load_snapshot_into_ui()

    # ============================================================
    # 界面
    # ============================================================
    def _build_controls(self):
        self.title_label.setText('🎛 控盘选股')
        self.title_label.setToolTip(
            '控盘标准 = 控盘分 + 洗盘/出货阶段 + 近120日位置，并可叠加 C4/C6/试盘/出货形态/拉升\n'
            '控盘分：换手中枢 40%% + 量价配合 35%% + 振幅 25%%，再按位置加权\n'
            '数据：本地日K缓存（只读），全市场主板+创业板')
        self.set_status('尚未扫描')

        bar1 = QHBoxLayout()
        bar1.setContentsMargins(0, 0, 0, 0)
        bar1.setSpacing(6)
        bar1.addWidget(L('控盘分 ≥', BC.TEXT2, 11))
        self._sp_score = QDoubleSpinBox()
        self._sp_score.setRange(0.0, 100.0)
        self._sp_score.setSingleStep(1.0)
        self._sp_score.setDecimals(0)
        self._sp_score.setValue(85.0)
        self._sp_score.setFixedWidth(62)
        self._sp_score.setStyleSheet(_SPIN_STYLE)
        self._sp_score.setToolTip('默认 85 = 引擎里的「高度控盘线」band_pattern_engine._CTRL_HIGH')
        bar1.addWidget(self._sp_score)

        bar1.addWidget(L('位置 ≤', BC.TEXT2, 11))
        self._cb_pos = QComboBox()
        self._cb_pos.addItems(['不限', '0.65', '0.45', '0.25'])
        self._cb_pos.setFixedWidth(66)
        self._cb_pos.setStyleSheet(_COMBO_STYLE)
        self._cb_pos.setToolTip('近120日位置。越低越在底部；0.25 是引擎「高度控盘候选」用的位置上限')
        bar1.addWidget(self._cb_pos)

        self._ck_dist = QCheckBox('排除出货')
        self._ck_dist.setChecked(True)
        self._ck_dist.setStyleSheet(f'color:{BC.TEXT};font-size:11px;')
        self._ck_dist.setToolTip("stage_guess == 'distribute' 的一律不显示（出货结构）")
        bar1.addWidget(self._ck_dist)

        self._ck_price = QCheckBox('价格≥6元')
        self._ck_price.setChecked(True)
        self._ck_price.setStyleSheet(f'color:{BC.TEXT};font-size:11px;')
        bar1.addWidget(self._ck_price)

        self._ck_st = QCheckBox('剔除ST')
        self._ck_st.setChecked(True)
        self._ck_st.setStyleSheet(f'color:{BC.TEXT};font-size:11px;')
        bar1.addWidget(self._ck_st)

        # 「仅看今日主线」：只保留今日决策页识别出的最强1~2个主线题材的股票
        # （叠加在原有全部默认筛选之上，不替代）；主线列表来自
        # data/cache/today_main_themes.json（打开今日决策页时自动写入）
        self._ck_mainline = QCheckBox('仅看今日主线')
        self._ck_mainline.setChecked(False)
        self._ck_mainline.setStyleSheet(f'color:{BC.TEXT};font-size:11px;font-weight:600;')
        self._ck_mainline.setToolTip(
            '开启后只保留属于今日主线题材（含同簇题材）的股票；\n'
            '仍完整保留：控盘分≥85、位置、排除出货、价格≥6、剔除ST。\n'
            '若提示「今日决策页未跑过」，先打开最前面的「🎯 今日决策」页刷新一次。')
        self._ck_mainline.toggled.connect(self._apply_and_render)
        bar1.addWidget(self._ck_mainline)

        bar1.addWidget(L('观察', BC.TEXT2, 11))
        self._cb_obs = QComboBox()
        self._cb_obs.addItems(list(SS.OBS_OPTIONS))
        self._cb_obs.setFixedWidth(128)
        self._cb_obs.setStyleSheet(_COMBO_STYLE)
        self._cb_obs.setToolTip(
            '观察类因子（五阶段：建仓堆量/红肥绿瘦、试盘、洗盘收复/地量、拉升/缩量上涨、'
            '破位警示/天量/出货形态 + C4/C6），只做筛选不改分数')
        bar1.addWidget(self._cb_obs)

        # 「阶段」筛选（A 项）：按操盘手法五阶段归属筛；选项与归属映射都在
        # services.control_profile（TAG_STAGE / STAGE_PICK）里定义一处。
        bar1.addWidget(L('阶段', BC.TEXT2, 11))
        self._cb_stage = QComboBox()
        self._cb_stage.addItems(list(SS.STAGE_OPTIONS))
        self._cb_stage.setFixedWidth(88)
        self._cb_stage.setStyleSheet(_COMBO_STYLE)
        self._cb_stage.setToolTip(
            '按「手法阶段」筛：建仓/试盘/洗盘/拉升/出货（一只股票可同时属于多个阶段，'
            '例如同时命中拉升与出货形态）\n'
            '注意：选具体阶段时会自动松开「排除出货」—— 两条筛法互斥，否则一选「出货」整表就空了')
        bar1.addWidget(self._cb_stage)

        bar1.addStretch()

        self._ck_seed = QCheckBox('补当日K线')
        self._ck_seed.setChecked(True)
        self._ck_seed.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        self._ck_seed.setToolTip(
            '扫描前先用腾讯批量行情把「今天的K线」写进本地缓存（80 只/请求，全市场约 1 分钟）\n'
            '为什么需要：日线接口逐个代码抓时 —— 新浪不含当天未收盘 bar、腾讯日线高频会被 WAF 限流、\n'
            'pytdx 无数据，所以盘中缓存常常只有上一交易日的 bar，「数据日」就会停在昨天。\n'
            '只在交易日 09:15~15:05 生效，其余时段自动跳过（不联网、不影响扫描）；\n'
            '补齐失败也不影响扫描，照旧用缓存里已有的数据。')
        bar1.addWidget(self._ck_seed)

        self._ck_auto = QCheckBox('打开页面自动扫描')
        self._ck_auto.setChecked(True)
        self._ck_auto.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        bar1.addWidget(self._ck_auto)

        self._ck_extra = QCheckBox('补主营/公告')
        self._ck_extra.setChecked(True)
        self._ck_extra.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        self._ck_extra.setToolTip(
            '对当前筛选结果联网补「主营收入 + 最新公告」（东财 F10 / 东财公告接口，巨潮兜底）\n'
            '实测 0.025s/只、6 线程，993 只约 25 秒；结果写 data/cache/ctrl_screen_extras.json\n'
            '主营 TTL 30 天、公告 TTL 6 小时，第二次打开直接命中缓存（不联网）')
        bar1.addWidget(self._ck_extra)

        self._btn_scan = QPushButton('🔍 开始扫描')
        self._btn_scan.setStyleSheet(_BTN_STYLE)
        self._btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_scan.clicked.connect(self._on_scan_clicked)
        bar1.addWidget(self._btn_scan)

        self._btn_export = QPushButton('📤 导出代码')
        self._btn_export.setStyleSheet(_BTN_STYLE)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setToolTip('导出当前筛选结果的 6 位代码（每行一个、无表头，可直接导入同花顺）')
        self._btn_export.clicked.connect(self._export_codes)
        bar1.addWidget(self._btn_export)

        self.content_layout.addLayout(bar1)

        bar2 = QHBoxLayout()
        bar2.setContentsMargins(0, 0, 0, 0)
        bar2.setSpacing(6)
        self._bar = QProgressBar()
        self._bar.setStyleSheet(_BAR_STYLE)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(12)
        self._bar.setVisible(False)
        bar2.addWidget(self._bar, 1)
        self._count_label = L('', BC.TEXT2, 11)
        bar2.addWidget(self._count_label)
        self.content_layout.addLayout(bar2)

        # 条件变化即重筛（不重扫）
        self._sp_score.valueChanged.connect(self._apply_and_render)
        self._cb_pos.currentIndexChanged.connect(self._apply_and_render)
        self._cb_obs.currentIndexChanged.connect(self._apply_and_render)
        self._cb_stage.currentIndexChanged.connect(self._on_stage_changed)
        self._ck_dist.stateChanged.connect(self._apply_and_render)
        self._ck_price.stateChanged.connect(self._apply_and_render)
        self._ck_st.stateChanged.connect(self._apply_and_render)
        # 只有勾上才补数（默认勾）；取消勾选不打断已经在跑的补数
        self._ck_extra.stateChanged.connect(
            lambda *_: self._ensure_extras() if self._ck_extra.isChecked() else None)

    def _build_table(self):
        self.table = make_table(PAGE_COL_N, PAGE_HEADERS, min_row_height=26)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        for i, w in enumerate(PAGE_WIDTHS):
            self.table.setColumnWidth(i, w)
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(C_THEME, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.content_layout.addWidget(self.table, 1)

        self.sorter = HeaderSorter(
            self.table,
            keys={C_NAME: lambda r: str(r.get('name') or ''),
                  C_CODE: lambda r: str(r.get('code') or ''),
                  C_PRICE: lambda r: float(r.get('price') or 0),
                  C_PCT: lambda r: float(r.get('pct') or 0),
                  C_SCORE: lambda r: float(r.get('score') or 0),
                  C_STAGE: lambda r: str(r.get('stage') or ''),
                  C_POS: lambda r: float(r.get('pos') or 0),
                  C_LABEL: lambda r: str(r.get('label') or ''),
                  C_THEME: lambda r: str(r.get('theme') or ''),
                  C_BIZ: lambda r: str(self._extra_rec(r).get('biz') or ''),
                  C_ANN: lambda r: str((self._extra_rec(r).get('ann') or [['']])[0][0] or ''),
                  C_OBS: lambda r: len(r.get('observe') or []),
                  C_DATE: lambda r: str(r.get('data_date') or '')},
            getter=lambda: self._rows,
            render=self._render)

    # ============================================================
    # 扫描
    # ============================================================
    def showEvent(self, event):
        """Tab 首次切到本页时，若开了自动扫描就后台跑一次（每个进程只自动跑一次）。"""
        super().showEvent(event)
        try:
            if (self._ck_auto.isChecked() and not self._auto_done
                    and not self._scanning):
                self._auto_done = True
                QTimer.singleShot(200, self._start_scan)
            # 主营/公告要联网，所以只在真的切到本页时才补（程序没打开本页就不联网）
            QTimer.singleShot(300, self._ensure_extras)
            # 首帧布局完成后再校一次列宽（初始化时 viewport 还没尺寸）
            QTimer.singleShot(120, self._autofit_columns)
        except Exception:
            pass

    def _on_scan_clicked(self):
        if self._scanning:
            self._cancel = True
            self.set_status('正在停止…')
            return
        self._start_scan()

    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._cancel = False
        self._btn_scan.setText('🛑 停止扫描')
        self._bar.setVisible(True)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self.set_status('批量读本地K线…')

        _seed_on = True
        try:
            _seed_on = bool(self._ck_seed.isChecked())
        except Exception:
            pass

        def _job():
            def _p(done, total, msg):
                try:
                    self._scan_progress.emit(done, total, msg)
                except Exception:
                    pass

            # 扫描前先补当日K线：不补的话，盘中缓存里最新还是上一交易日的 bar，
            # 页面「数据日」就会停在昨天（2026-10-12 定位到的根因）。
            # 只在交易时段生效；任何失败都不影响扫描，照旧用缓存里已有数据。
            if _seed_on:
                try:
                    from services.kline_cache_service import seed_today_bar
                    _r = seed_today_bar(progress_cb=_p) or {}
                    if _r.get('ok'):
                        _p(0, 0, '当日K线已补 %d 只（覆盖 %d→%d），开始扫描…'
                           % (_r.get('written', 0), _r.get('before', 0), _r.get('after', 0)))
                    else:
                        _p(0, 0, '当日K线未补：%s' % (_r.get('reason') or '无数据'))
                except Exception as _e:
                    _p(0, 0, '当日K线补齐异常：%s' % str(_e)[:60])

            bars = SS.load_all_bars()
            return SS.scan_market(bars=bars, progress_cb=_p,
                                  cancel_cb=lambda: self._cancel)

        self.run_async(_job, self._on_scan_ok, self._on_scan_fail)

    def _on_scan_progress(self, done, total, msg):
        try:
            if total > 0:
                self._bar.setValue(int(done * 100 / total))
            self.set_status('%s ｜ 用时按扫描线程计' % msg)
        except Exception:
            pass

    def _on_scan_ok(self, result):
        _cancelled = bool(self._cancel)
        self._scanning = False
        self._btn_scan.setText('🔍 开始扫描')
        self._bar.setVisible(False)
        rows, stats = (result if isinstance(result, tuple) and len(result) == 2
                       else (result, {}))
        rows = list(rows or [])
        # 中止扫描 / 空结果不覆盖快照：否则点一次「停止扫描」就把上一次的完整结果换成了
        # 残缺结果，下次打开页面看到的是空表（2026-10-12 实测踩到过：cancel 后 scan_market
        # 返回 0 行，快照被写成 122 字节的空壳）。
        if _cancelled or not rows:
            self._cancel = False
            self._apply_and_render()
            # 提示要放在渲染之后：_apply_and_render → _update_count 会重写状态条
            self.set_status('扫描已中止：本次 %d 只，快照与列表保持上一次结果' % len(rows))
            return
        self._all_rows = rows
        self._stats = dict(stats or {})
        self._saved_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            SS.save_snapshot(self._all_rows, self._stats)
        except Exception:
            pass
        self._apply_and_render()
        # 扫描可能带出缓存里没有的新代码，扫描完再补一轮
        QTimer.singleShot(100, self._ensure_extras)

    def _on_scan_fail(self, err_msg):
        self._scanning = False
        self._btn_scan.setText('🔍 开始扫描')
        self._bar.setVisible(False)
        self.set_status('扫描失败：%s' % err_msg)

    def _load_snapshot_into_ui(self):
        """程序刚启动：先把上一次的快照显示出来（不用等 30 秒）。"""
        snap = SS.load_snapshot()
        if not snap:
            self.set_status('尚未扫描（点「开始扫描」，约 25 秒）')
            return
        self._all_rows = list(snap.get('rows') or [])
        self._stats = {'universe': snap.get('universe', 0),
                       'ok': snap.get('ok', len(self._all_rows)),
                       'data_date': snap.get('data_date', ''),
                       'elapsed': snap.get('elapsed', 0.0)}
        self._saved_at = str(snap.get('saved_at') or '')
        self._apply_and_render(fill=False)   # 补数等切到本页（showEvent）再跑

    # ============================================================
    # 筛选 + 渲染
    # ============================================================
    def _on_stage_changed(self):
        """切换「阶段」筛选时松开「排除出货」。

        两条筛法互斥：勾着「排除出货」再选「阶段=出货」，结果必然接近空表
        （只有「出货形态/天量/破位警示」标签而不属于 distribute 的票才会留下）。
        只自动取消勾选，不隐藏控件 —— 用户立刻可以再勾回来。
        """
        try:
            if (self._cb_stage.currentText() != SS.STAGE_OPTIONS[0]
                    and self._ck_dist.isChecked()):
                self._ck_dist.setChecked(False)
        except Exception:
            pass
        self._apply_and_render()

    def _pos_max(self):
        t = self._cb_pos.currentText()
        return None if t == '不限' else float(t)

    def _filtered(self):
        rows = SS.apply_filters(
            self._all_rows,
            min_score=float(self._sp_score.value()),
            pos_max=self._pos_max(),
            exclude_dist=bool(self._ck_dist.isChecked()),
            min_price=6.0 if self._ck_price.isChecked() else 0.0,
            drop_st=bool(self._ck_st.isChecked()),
            obs=self._cb_obs.currentText(),
            stage=self._cb_stage.currentText())
        # 仅看今日主线：在原有默认筛选结果之上再按题材过滤
        if self._ck_mainline.isChecked():
            try:
                from services.decision_page_service import (filter_rows_by_themes,
                                                           load_main_themes)
                if not load_main_themes():
                    self.set_status('今日决策页尚未跑过，主线列表为空，本开关未生效')
                else:
                    rows = filter_rows_by_themes(rows)
            except Exception as e:
                self.set_status('主线过滤异常: %s' % e)
        return rows

    def enable_mainline_filter(self):
        """决策页跳转入口：自动勾选「仅看今日主线」并重渲染。"""
        try:
            self._ck_mainline.setChecked(True)
            self._apply_and_render()
        except Exception as e:
            self.set_status('开启主线过滤失败: %s' % e)

    def _apply_and_render(self, *args, fill=True):
        self._rows = self._filtered()
        self._render()
        if fill:
            self._ensure_extras()

    def _render(self):
        rows = self._rows
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            _sc = float(r.get('score') or 0)
            _sc_color = BC.RED if _sc >= 90 else (BC.ORANGE if _sc >= 85 else BC.TEXT)
            _pos = float(r.get('pos') or 0)
            _pos_color = BC.RED if _pos < 0.25 else (BC.GOLD if _pos >= 0.65 else BC.TEXT)
            set_table_item(self.table, i, C_NAME, str(r.get('name') or ''),
                           BC.BLUE, bold=True)
            set_table_item(self.table, i, C_CODE, str(r.get('code') or ''), BC.TEXT2)
            set_table_item(self.table, i, C_PRICE, '%.2f' % float(r.get('price') or 0),
                           BC.TEXT, align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            _pct = float(r.get('pct') or 0)
            set_table_item(self.table, i, C_PCT, '%+.2f%%' % _pct, pct_color(_pct),
                           align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            # 涨停题材：最近一次涨停原因（limit_up_reason_db），空显示 --
            _th = str(r.get('theme') or '')
            _th_item = set_table_item(self.table, i, C_THEME, _th or '--',
                                      _THEME_COLOR if _th else BC.TEXT3)
            _th_item.setToolTip(_theme_tip(r))
            # 主营收入：主营构成第一大项（占比最高那项）+ 营收
            _rec = self._extra_rec(r)
            _biz_txt, _biz_tip = SS.fmt_biz(_rec)
            _biz_item = set_table_item(self.table, i, C_BIZ, _biz_txt or '--',
                                       _BIZ_COLOR if _biz_txt else BC.TEXT3)
            _biz_item.setToolTip(_biz_tip or _BIZ_EMPTY_TIP)
            set_table_item(self.table, i, C_SCORE, '%.1f' % _sc, _sc_color, bold=(_sc >= 90),
                           align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            _stg = str(r.get('stage') or '')
            set_table_item(self.table, i, C_STAGE, _STAGE_TXT.get(_stg, _stg or '—'),
                           (BC.RED if _stg == 'distribute'
                            else (BC.ORANGE if _stg == 'wash' else BC.TEXT3)))
            set_table_item(self.table, i, C_POS, '%.2f' % _pos, _pos_color,
                           align=Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            _lab = str(r.get('label') or '')
            _lab_color = (BC.RED if _lab == '出货'
                          else (BC.ORANGE if _lab == '洗盘' else BC.GREEN))
            _lab_item = set_table_item(self.table, i, C_LABEL, _lab or '—',
                                       _lab_color if _lab else BC.TEXT3,
                                       bold=bool(_lab))
            _lab_item.setToolTip(str(r.get('note') or ''))
            _obs = r.get('observe') or []
            _obs_item = set_table_item(self.table, i, C_OBS,
                                       ' ｜ '.join(_obs) if _obs else '—',
                                       _obs_color(_obs))
            _obs_item.setToolTip(_obs_tip(r))
            # 最新公告：MM-DD + 标题（标题太长会被省略号截断，悬停看全文 + 链接）
            _ann_txt, _ann_tip = SS.fmt_ann(_rec)
            _ann_item = set_table_item(self.table, i, C_ANN, _ann_txt or '--',
                                       _ANN_COLOR if _ann_txt else BC.TEXT3)
            _ann_item.setToolTip(_ann_tip or _ANN_EMPTY_TIP)
            set_table_item(self.table, i, C_DATE, str(r.get('data_date') or ''),
                           BC.TEXT3)
        self._autofit_columns()
        self._update_count()

    def _autofit_columns(self):
        """按内容把 12 个固定列调到「刚好显示得下」，拉伸列（涨停题材）吃剩余空间。

        · 逐格用**该格自己的字体**量字（表里有加粗格，用统一字体会低估宽度）；
        · 量字用 Qt 原生 sizeHintForColumn（C++ 侧，precision=-1 = 全部行都量）；
          这一条是有来历的：自己用 Python 逐格量 4 万次要 662ms，还会因采样漏掉最长格；
        · 下限防列被压没；上限只加在三个长文本列上，避免被上限反夹断；
        · 只有窗口真的放不下时，才按「观察 → 主营收入 → 最新公告」顺序压回下限，
          再放不下就让横向滚动条接管（不为了塞进去而截断内容）。
        """
        rows = self._rows
        n = len(rows)
        if n <= 0:
            return
        try:
            # 量字交给 Qt 自己做（C++ 侧），Python 只做夹取与让位。
            # 默认只采样 1000 行，改成 -1 = 全部行都量，保证不漏最长格。
            try:
                if n > _FIT_MAX_ROWS:
                    self.table.setResizeContentsPrecision(_FIT_SAMPLE)
                else:
                    self.table.setResizeContentsPrecision(-1)
            except Exception:
                pass
            fm_h = QFontMetrics(self.table.horizontalHeader().font())
            need = {}
            for c in _FIT_COLS:
                _hit = self.table.horizontalHeaderItem(c)
                w = fm_h.horizontalAdvance(_hit.text() if _hit else '') + 10
                w = max(w, self.table.sizeHintForColumn(c))
                _n = max(w, PAGE_WIDTHS_MIN[c]) + _HEAD_MIN_PAD
                _cap = PAGE_WIDTHS_MAX.get(c)
                need[c] = min(_n, _cap) if _cap else _n
            vw = int(self.table.viewport().width())
            if vw >= 400:                       # 布局已完成才算「放不放得下」
                over = sum(need.values()) + _THEME_MIN_W - vw
                for c in (C_OBS, C_BIZ, C_ANN):
                    if over <= 0:
                        break
                    _cut = min(need[c] - PAGE_WIDTHS_MIN[c], over)
                    need[c] -= _cut
                    over -= _cut
            for c in _FIT_COLS:
                self.table.setColumnWidth(c, int(round(need[c])))
        except Exception:
            pass

    def _update_count(self):
        _st = self._stats or {}
        parts = ['符合条件 %d 只' % len(self._rows),
                 '全量 %d 只' % len(self._all_rows)]
        if _st.get('universe'):
            parts.append('扫描 %d 只' % _st.get('universe'))
        if _st.get('data_date'):
            parts.append('数据日 %s' % _st.get('data_date'))
        if _st.get('elapsed'):
            parts.append('耗时 %.0fs' % float(_st.get('elapsed') or 0))
        if self._saved_at:
            parts.append('扫描于 %s' % self._saved_at)
        _extra_n = sum(1 for r in self._rows if self._extra_rec(r).get('biz'))
        parts.append('主营已补 %d/%d' % (_extra_n, len(self._rows)))
        self._count_label.setText(' ｜ '.join(parts))
        if not self._scanning and not self._filling:
            self.set_status('控盘分≥%d ｜ %s' % (int(self._sp_score.value()),
                                              '已扫描' if self._all_rows else '尚未扫描'))

    def _on_cell_clicked(self, row, col):
        if col not in (C_NAME, C_CODE):
            return
        try:
            r = self._rows[row]
        except Exception:
            return
        self.stock_clicked.emit(str(r.get('code') or ''), str(r.get('name') or ''))

    # ============================================================
    # 主营收入 + 最新公告（后台补数，不阻塞扫描/不卡 UI）
    # ============================================================
    def _extra_rec(self, r):
        """取该行的主营/公告缓存记录（没有返回 {}）。"""
        try:
            return self._extras.get(str(r.get('code') or '')) or {}
        except Exception:
            return {}

    def _ensure_extras(self):
        """对当前筛选结果补「主营收入 + 最新公告」：缓存命中立即显示，缺的后台并发补。"""
        try:
            if not self._ck_extra.isChecked() or self._filling:
                return
            codes = [str(r.get('code') or '') for r in self._rows]
            miss = SS.extras_missing(codes, self._extras)
            if not miss:
                return
            self._filling = True
            self._cancel_fill = False
            self.set_status('补主营/公告 0/%d（联网，已补的走缓存不重拉）' % len(miss))

            def _job():
                # workers 只影响本地排队，真正防限流的是服务层「按主机限速」
                # （公告 0.3s/次、主营 0.2s/次 + 失败退避 15 分钟 + 连续失败熔断）
                return SS.fetch_extras(
                    miss, self._extras, workers=3,
                    progress_cb=lambda d, t, m: self._fill_progress.emit(d, t, m),
                    cancel_cb=lambda: self._cancel_fill)

            self.run_async(_job, self._on_extras_ok, self._on_extras_fail)
        except Exception:
            self._filling = False

    def _on_fill_progress(self, done, total, msg):
        try:
            self.set_status('%s（可继续筛股，不影响）' % msg)
        except Exception:
            pass

    def _on_extras_ok(self, result):
        self._filling = False
        items, stats = (result if isinstance(result, tuple) and len(result) == 2
                        else (self._extras, {}))
        if isinstance(items, dict):
            self._extras = items
        _ab = str(stats.get('aborted') or '')
        _tail = ('｜被上游限流，本轮已停手（%d 分钟后自动重试）' % int(SS.ANN_FAIL_COOLDOWN / 60)
                 if _ab else '｜来源 东财，公告新浪/巨潮兜底')
        self.set_status('主营/公告补数完成：主营 %d ｜ 公告 %d ｜ 失败 %d（异常 %d）/ %.1fs %s'
                        % (int(stats.get('biz_ok') or 0), int(stats.get('ann_ok') or 0),
                           int(stats.get('ann_fail') or 0), int(stats.get('err') or 0),
                           float(stats.get('elapsed') or 0), _tail))
        self._render()
        # 补数期间筛选条件可能被改过（rows 变了）→ 再对一次缺项
        QTimer.singleShot(120, self._ensure_extras)

    def _on_extras_fail(self, err_msg):
        self._filling = False
        self.set_status('主营/公告补数失败：%s' % err_msg)

    # ============================================================
    # 导出（与日K建仓导出同一格式：每行一个 6 位代码、无表头）
    # ============================================================
    def _export_codes(self):
        if not self._rows:
            QMessageBox.information(self, '导出代码', '当前筛选结果为空，没有可导出的代码。')
            return
        default_name = '控盘选股_%s_%s.txt' % (
            int(self._sp_score.value()), datetime.now().strftime('%Y%m%d_%H%M'))
        path, _ = QFileDialog.getSaveFileName(
            self, '导出股票代码（每行一个，可直接导入同花顺）', default_name,
            '文本文件 (*.txt)')
        if not path:
            return
        if not path.lower().endswith('.txt'):
            path += '.txt'
        try:
            n = SS.export_codes(self._rows, path)
        except Exception as e:
            QMessageBox.warning(self, '导出失败', str(e))
            return
        if n <= 0:
            QMessageBox.warning(self, '导出失败', '没有可导出的 6 位代码。')
            return
        QMessageBox.information(
            self, '导出成功',
            '已导出 %d 只股票代码到：\n%s\n\n每行一个代码、无表头，可直接导入同花顺。'
            % (n, path))

    def refresh(self):
        """基类定时刷新入口 —— 本页只按需扫描，不做定时刷新。"""
        pass


def _theme_tip(rec):
    """涨停题材列 tooltip：题材串 + 最近一次涨停的日期/连板/行业（便于核对）。"""
    _th = str(rec.get('theme') or '')
    if not _th:
        return '本地涨停原因库（data/limit_up_reason.db）里没有该股的含「+」题材'
    _d = str(rec.get('theme_date') or '')
    _d = '%s-%s-%s' % (_d[0:4], _d[4:6], _d[6:8]) if len(_d) == 8 else (_d or '-')
    _txt = '涨停题材：%s\n来源：最近一次涨停 %s ｜ %s连板' % (
        _th, _d, int(rec.get('theme_lbc') or 0) or '-')
    _ind = str(rec.get('theme_ind') or '')
    if _ind:
        _txt += ' ｜ 行业：%s' % _ind
    return _txt


def _obs_color(tags):
    """观察标签配色（按 level）：风险红 > 拉升/缩量上涨橙 > 试盘金 > 中性蓝。

    level 由 services.control_profile.OBS_TAG_LEVEL 给（词表唯一来源），
    这里只做「一张格子一个颜色」的降级 —— 取整格里级别最高的那个颜色。
    """
    from services.control_profile import OBS_TAG_LEVEL
    tags = tags or []
    _lv = []
    for t in tags:
        _k = str(t).split(':')[0].split('\uff1a')[0].strip()
        _lv.append(OBS_TAG_LEVEL.get(_k, 'info'))
    if 'risk' in _lv:
        return BC.RED
    if 'warn' in _lv:
        return BC.ORANGE
    if 'gold' in _lv:
        return BC.GOLD
    if _lv:
        return BC.BLUE
    return BC.TEXT3


def _obs_tip(rec):
    """观察列 tooltip：把各因子的原始数值摆出来，便于核对。"""
    try:
        return ('阶段=%s ｜ 位置=%.3f ｜ 控盘分=%.1f\n'
                'C4 n_ok=%d ｜ C6 n_ok=%d ｜ 试盘=%s(%s)\n'
                '出货形态=%s ｜ 拉升=%s\n'
                '底部堆量分=%.1f%s ｜ 红肥绿瘦比=%.2f%s\n'
                '破位/收复=%s ｜ 量能分位=%s%s\n'
                '手法阶段=%s\n'
                '提示：%s'
                % (rec.get('stage') or '', float(rec.get('pos') or 0),
                   float(rec.get('score') or 0),
                   int(rec.get('c4_n') or 0), int(rec.get('c6_n') or 0),
                   '是' if rec.get('probe_ok') else '否', rec.get('probe_stage') or '-',
                   rec.get('dist_type') or '-', rec.get('markup_type') or '-',
                   float(rec.get('stack_score') or 0),
                   '（达标）' if rec.get('stack_ok') else '',
                   float(rec.get('redfat_ratio') or 0),
                   '（达标）' if rec.get('redfat_ok') else '',
                   rec.get('brk_type') or '-', rec.get('vreg_tags') or '-',
                   ('（分位 %.0f%%）' % float(rec.get('vreg_pct'))
                    if rec.get('vreg_pct') is not None else ''),
                   '·'.join(SS.stages_of(rec)) or '-',
                   rec.get('note') or '（无）'))
    except Exception:
        return ''
