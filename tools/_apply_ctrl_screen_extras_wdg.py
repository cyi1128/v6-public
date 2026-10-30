# -*- coding: utf-8 -*-
"""一次性补丁（2/2）：控盘选股页加「主营收入」「最新公告」两列 + 后台补数。

列数 11 → 13：
  股票名称 代码 现价 涨跌幅 涨停题材 **主营收入** 控盘分 阶段 位置 控盘提示 观察 **最新公告** 数据日

补数策略：
  - 只在「切到本页」或「扫描完成」后联网补，程序不打开本页就不联网；
  - 缓存命中即时显示，缺的走 extras_missing → 后台 6 线程补 → 重绘；
  - 结果落 data/cache/ctrl_screen_extras.json（主营 TTL 30 天 / 公告 TTL 6 小时）。

执行一次即失效，勿重跑。
"""
import io
import os
import shutil
import tempfile

ROOT = r'D:\QuantMonitorV6'
WDG = os.path.join(ROOT, 'ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(WDG, 'r', encoding='utf-8').read()
assert '_ensure_extras' not in s, '疑似已打过补丁（2/2）'
orig = s

# ---------------- 1) 模块 docstring ----------------
A1 = """列（11 列）：股票名称 / 代码 / 现价 / 涨跌幅 / **涨停题材** / 控盘分 / 阶段 /
位置 / 控盘提示 / 观察 / 数据日。涨停题材与「日K建仓」「竞价」同源：
data.limit_up_reason_db.get_last_limit_up_reason(code)（最近一次涨停原因）。"""
N1 = """列（13 列）：股票名称 / 代码 / 现价 / 涨跌幅 / **涨停题材** / **主营收入** /
控盘分 / 阶段 / 位置 / 控盘提示 / 观察 / **最新公告** / 数据日。
  · 涨停题材与「日K建仓」「竞价」同源：data.limit_up_reason_db.get_last_limit_up_reason(code)
  · 主营收入 = 主营构成第一大项（东财 F10 fetch_main_business_composition，取占比最高那项）
  · 最新公告 = 最近一条公告（东财公告接口，巨潮兜底）
后两列要联网，**不进 25 秒的全市场扫描**：切到本页/扫描完成后，按当前筛选结果
在后台 6 线程补缺项（实测 0.025s/只，993 只约 25 秒），落
data/cache/ctrl_screen_extras.json（主营 TTL 30 天、公告 TTL 6 小时），
第二次打开直接命中缓存。"""
assert s.count(A1) == 1
s = s.replace(A1, N1, 1)

# ---------------- 2) 列定义 ----------------
A2 = """PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '控盘分',
                '阶段', '位置', '控盘提示', '观察', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_THEME, C_SCORE,
 C_STAGE, C_POS, C_LABEL, C_OBS, C_DATE) = range(PAGE_COL_N)
# 题材串很长（如「参股算力建设（金额较小）+工程咨询+AI应用+甘肃国资」），
# 所以拉伸列给题材、观察列固定宽度（观察标签最多 3 个短词，190 够）。
PAGE_WIDTHS = [96, 66, 70, 74, 230, 70, 58, 58, 96, 190, 90]
_THEME_COLOR = '#6a1b9a'   # 与「日K建仓」题材列同色"""
N2 = """PAGE_HEADERS = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '主营收入', '控盘分',
                '阶段', '位置', '控盘提示', '观察', '最新公告', '数据日']
PAGE_COL_N = len(PAGE_HEADERS)
(C_NAME, C_CODE, C_PRICE, C_PCT, C_THEME, C_BIZ, C_SCORE,
 C_STAGE, C_POS, C_LABEL, C_OBS, C_ANN, C_DATE) = range(PAGE_COL_N)
# 题材串很长（如「参股算力建设（金额较小）+工程咨询+AI应用+甘肃国资」），
# 所以拉伸列给题材；「主营收入」放第一大项名 + 营收（如「智能终端 65.80亿」，170 够），
# 「最新公告」放 MM-DD + 标题（标题很长会被省略号截断，悬停看全文，260 够）。
PAGE_WIDTHS = [96, 66, 70, 74, 230, 170, 70, 58, 58, 96, 190, 260, 90]
_THEME_COLOR = '#6a1b9a'   # 与「日K建仓」题材列同色
_BIZ_COLOR = '#00695c'     # 主营收入：深青（与「日K建仓」模式列同色系）
_ANN_COLOR = '#1565c0'     # 最新公告：深蓝（与「日K建仓」触发条件列同色）"""
assert s.count(A2) == 1
s = s.replace(A2, N2, 1)

# ---------------- 3) __init__ / 信号 ----------------
A3 = """    stock_clicked = pyqtSignal(str, str)      # code, name
    _scan_progress = pyqtSignal(int, int, str)  # done, total, msg（从扫描线程 emit）

    def __init__(self, parent=None):
        self._all_rows = []       # 全量扫描结果
        self._rows = []           # 当前筛选后（表格数据源，排序会原地改它）
        self._stats = {}
        self._saved_at = ''
        self._scanning = False
        self._cancel = False
        self._auto_done = False
        super().__init__('🎛 控盘选股', parent)
        self._build_controls()
        self._build_table()
        self._scan_progress.connect(self._on_scan_progress)
        self._load_snapshot_into_ui()"""
N3 = """    stock_clicked = pyqtSignal(str, str)      # code, name
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
        self._load_snapshot_into_ui()"""
assert s.count(A3) == 1
s = s.replace(A3, N3, 1)

# ---------------- 4) 控件：补数开关 ----------------
A4 = """        self._ck_auto = QCheckBox('打开页面自动扫描')
        self._ck_auto.setChecked(True)
        self._ck_auto.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        bar1.addWidget(self._ck_auto)"""
N4 = """        self._ck_auto = QCheckBox('打开页面自动扫描')
        self._ck_auto.setChecked(True)
        self._ck_auto.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        bar1.addWidget(self._ck_auto)

        self._ck_extra = QCheckBox('补主营/公告')
        self._ck_extra.setChecked(True)
        self._ck_extra.setStyleSheet(f'color:{BC.TEXT2};font-size:11px;')
        self._ck_extra.setToolTip(
            '对当前筛选结果联网补「主营收入 + 最新公告」（东财 F10 / 东财公告接口，巨潮兜底）\\n'
            '实测 0.025s/只、6 线程，993 只约 25 秒；结果写 data/cache/ctrl_screen_extras.json\\n'
            '主营 TTL 30 天、公告 TTL 6 小时，第二次打开直接命中缓存（不联网）')
        bar1.addWidget(self._ck_extra)"""
assert s.count(A4) == 1
s = s.replace(A4, N4, 1)

# ---------------- 5) 条件变化重筛时也允许触发补数 ----------------
A5 = """        self._ck_dist.stateChanged.connect(self._apply_and_render)
        self._ck_price.stateChanged.connect(self._apply_and_render)
        self._ck_st.stateChanged.connect(self._apply_and_render)"""
N5 = """        self._ck_dist.stateChanged.connect(self._apply_and_render)
        self._ck_price.stateChanged.connect(self._apply_and_render)
        self._ck_st.stateChanged.connect(self._apply_and_render)
        # 只有勾上才补数（默认勾）；取消勾选不打断已经在跑的补数
        self._ck_extra.stateChanged.connect(
            lambda *_: self._ensure_extras() if self._ck_extra.isChecked() else None)"""
assert s.count(A5) == 1
s = s.replace(A5, N5, 1)

# ---------------- 6) 排序键 ----------------
A6 = """                  C_SCORE: lambda r: float(r.get('score') or 0),
                  C_STAGE: lambda r: str(r.get('stage') or ''),
                  C_POS: lambda r: float(r.get('pos') or 0),
                  C_LABEL: lambda r: str(r.get('label') or ''),
                  C_THEME: lambda r: str(r.get('theme') or ''),
                  C_OBS: lambda r: len(r.get('observe') or []),"""
N6 = """                  C_SCORE: lambda r: float(r.get('score') or 0),
                  C_STAGE: lambda r: str(r.get('stage') or ''),
                  C_POS: lambda r: float(r.get('pos') or 0),
                  C_LABEL: lambda r: str(r.get('label') or ''),
                  C_THEME: lambda r: str(r.get('theme') or ''),
                  C_BIZ: lambda r: str(self._extra_rec(r).get('biz') or ''),
                  C_ANN: lambda r: str((self._extra_rec(r).get('ann') or [['']])[0][0] or ''),
                  C_OBS: lambda r: len(r.get('observe') or []),"""
assert s.count(A6) == 1
s = s.replace(A6, N6, 1)

# ---------------- 7) showEvent：切到本页才开始补 ----------------
A7 = """            if (self._ck_auto.isChecked() and not self._auto_done
                    and not self._scanning):
                self._auto_done = True
                QTimer.singleShot(200, self._start_scan)
        except Exception:
            pass"""
N7 = """            if (self._ck_auto.isChecked() and not self._auto_done
                    and not self._scanning):
                self._auto_done = True
                QTimer.singleShot(200, self._start_scan)
            # 主营/公告要联网，所以只在真的切到本页时才补（程序没打开本页就不联网）
            QTimer.singleShot(300, self._ensure_extras)
        except Exception:
            pass"""
assert s.count(A7) == 1
s = s.replace(A7, N7, 1)

# ---------------- 8) 扫描完成后也补 ----------------
A8 = """        try:
            SS.save_snapshot(self._all_rows, self._stats)
        except Exception:
            pass
        self._apply_and_render()"""
N8 = """        try:
            SS.save_snapshot(self._all_rows, self._stats)
        except Exception:
            pass
        self._apply_and_render()
        # 扫描可能带出缓存里没有的新代码，扫描完再补一轮
        QTimer.singleShot(100, self._ensure_extras)"""
assert s.count(A8) == 1
s = s.replace(A8, N8, 1)

# ---------------- 9) _apply_and_render：加 fill 开关 ----------------
A9 = """    def _apply_and_render(self, *args):
        self._rows = self._filtered()
        self._render()"""
N9 = """    def _apply_and_render(self, *args, fill=True):
        self._rows = self._filtered()
        self._render()
        if fill:
            self._ensure_extras()"""
assert s.count(A9) == 1
s = s.replace(A9, N9, 1)

# 启动时载入快照不要立刻联网（等切到本页再补）
A9b = """        self._saved_at = str(snap.get('saved_at') or '')
        self._apply_and_render()"""
N9b = """        self._saved_at = str(snap.get('saved_at') or '')
        self._apply_and_render(fill=False)   # 补数等切到本页（showEvent）再跑"""
assert s.count(A9b) == 1
s = s.replace(A9b, N9b, 1)

# ---------------- 10) _render：两列单元格 ----------------
A10 = """            _th_item = set_table_item(self.table, i, C_THEME, _th or '--',
                                      _THEME_COLOR if _th else BC.TEXT3)
            _th_item.setToolTip(_theme_tip(r))"""
N10 = """            _th_item = set_table_item(self.table, i, C_THEME, _th or '--',
                                      _THEME_COLOR if _th else BC.TEXT3)
            _th_item.setToolTip(_theme_tip(r))
            # 主营收入：主营构成第一大项（占比最高那项）+ 营收
            _rec = self._extra_rec(r)
            _biz_txt, _biz_tip = SS.fmt_biz(_rec)
            _biz_item = set_table_item(self.table, i, C_BIZ, _biz_txt or '--',
                                       _BIZ_COLOR if _biz_txt else BC.TEXT3)
            _biz_item.setToolTip(_biz_tip or '尚无主营构成数据（东财 F10 未返回，或还没补数）')"""
assert s.count(A10) == 1
s = s.replace(A10, N10, 1)

A11 = """            _obs_item.setToolTip(_obs_tip(r))
            set_table_item(self.table, i, C_DATE, str(r.get('data_date') or ''),
                           BC.TEXT3)"""
N11 = """            _obs_item.setToolTip(_obs_tip(r))
            # 最新公告：MM-DD + 标题（标题太长会被省略号截断，悬停看全文 + 链接）
            _ann_txt, _ann_tip = SS.fmt_ann(_rec)
            _ann_item = set_table_item(self.table, i, C_ANN, _ann_txt or '--',
                                       _ANN_COLOR if _ann_txt else BC.TEXT3)
            _ann_item.setToolTip(_ann_tip or '尚无公告数据（东财/巨潮都为空，或还没补数）')
            set_table_item(self.table, i, C_DATE, str(r.get('data_date') or ''),
                           BC.TEXT3)"""
assert s.count(A11) == 1
s = s.replace(A11, N11, 1)

# ---------------- 11) 计数栏：补数时不覆盖补数进度 ----------------
A12 = """        self._count_label.setText(' ｜ '.join(parts))
        if not self._scanning:
            self.set_status('控盘分≥%d ｜ %s' % (int(self._sp_score.value()),
                                              '已扫描' if self._all_rows else '尚未扫描'))"""
N12 = """        _extra_n = sum(1 for r in self._rows if self._extra_rec(r).get('biz'))
        parts.append('主营已补 %d/%d' % (_extra_n, len(self._rows)))
        self._count_label.setText(' ｜ '.join(parts))
        if not self._scanning and not self._filling:
            self.set_status('控盘分≥%d ｜ %s' % (int(self._sp_score.value()),
                                              '已扫描' if self._all_rows else '尚未扫描'))"""
assert s.count(A12) == 1
s = s.replace(A12, N12, 1)

# ---------------- 12) 补数逻辑 + 缓存读取 ----------------
A13 = """    # ============================================================
    # 导出（与日K建仓导出同一格式：每行一个 6 位代码、无表头）
    # ============================================================"""
N13 = """    # ============================================================
    # 主营收入 + 最新公告（后台补数，不阻塞扫描/不卡 UI）
    # ============================================================
    def _extra_rec(self, r):
        \"\"\"取该行的主营/公告缓存记录（没有返回 {}）。\"\"\"
        try:
            return self._extras.get(str(r.get('code') or '')) or {}
        except Exception:
            return {}

    def _ensure_extras(self):
        \"\"\"对当前筛选结果补「主营收入 + 最新公告」：缓存命中立即显示，缺的后台并发补。\"\"\"
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
                return SS.fetch_extras(
                    miss, self._extras, workers=6,
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
        self.set_status('主营/公告补数完成：%d 只 / %.1fs（异常 %d）｜来源 东财，公告巨潮兜底'
                        % (int(stats.get('ok') or 0), float(stats.get('elapsed') or 0),
                           int(stats.get('err') or 0)))
        self._render()
        # 补数期间筛选条件可能被改过（rows 变了）→ 再对一次缺项
        QTimer.singleShot(120, self._ensure_extras)

    def _on_extras_fail(self, err_msg):
        self._filling = False
        self.set_status('主营/公告补数失败：%s' % err_msg)

    # ============================================================
    # 导出（与日K建仓导出同一格式：每行一个 6 位代码、无表头）
    # ============================================================"""
assert s.count(A13) == 1
s = s.replace(A13, N13, 1)

assert s != orig
if not os.path.isfile(WDG + '.bak_before_extras'):
    shutil.copy2(WDG, WDG + '.bak_before_extras')
    print('备份: %s.bak_before_extras' % WDG)
io.open(WDG, 'w', encoding='utf-8', newline='').write(s)

import py_compile   # noqa: E402
b = io.open(WDG, 'rb').read()
print('control_screen_widget.py: 行=%d CRLF=%d 字节=%d' % (b.count(b'\n'), b.count(b'\r\n'), len(b)))
assert b.count(b'\r\n') == 0
py_compile.compile(WDG, cfile=os.path.join(tempfile.gettempdir(), 'cs_wdg_extras.pyc'), doraise=True)
print('语法校验通过')
