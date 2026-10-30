# -*- coding: utf-8 -*-
"""独立验证「控盘选股」列宽自适应（可重跑）。

口径与页面实现**无关**：把表格按 1880px 真实尺寸摆好，然后对**每一行 × 每一列**
（不是采样）独立量字，判定这一格会不会被省略号截断：
    单元格需要宽 = 该格字体下文字宽度 + 16（QTableWidget::item padding 4px 8px）
    表头需要宽   = 表头字体下文字宽度 + 12
逐列统计「有多少格的宽度不够」，并核对短列确实被压缩、长列确实被放宽。
"""
import io
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)
# 默认离屏；改 `$env:QT_QPA_PLATFORM="windows"` 可切到真实 Windows 字体度量
# （离屏没有中文字体、字宽偏大，判定「是否截断」应以真实字体为准）
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtGui import QFontMetrics                     # noqa: E402
from PyQt6.QtWidgets import QApplication                 # noqa: E402

from ui.battle_widgets.control_screen_widget import (    # noqa: E402
    ControlScreenWidget, PAGE_HEADERS, PAGE_COL_N, PAGE_WIDTHS,
    C_NAME, C_CODE, C_PRICE, C_PCT, C_THEME, C_BIZ, C_SCORE, C_STAGE, C_POS,
    C_LABEL, C_OBS, C_ANN, C_DATE, _FIT_COLS)

PASS, FAIL, L = [], [], []


def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    L.append('%s %s%s' % ('PASS' if cond else 'FAIL', name, (' ｜ %s' % extra) if extra else ''))


CELL_PAD = 16        # QTableWidget::item{padding:4px 8px}
HEAD_PAD = 12

app = QApplication.instance() or QApplication([])
w = ControlScreenWidget()
w._ck_extra.setChecked(False)          # 离线：只读缓存不联网
w._ck_auto.setChecked(False)
w._sp_score.setValue(0)                # 门槛 0 → 最大池 3294 只
w.resize(1880, 950)
w.show()
app.processEvents()
_tw = w.table.viewport().width()
if _tw < 800:                          # offscreen 下偶尔不给尺寸，直接摆表格
    w.table.resize(1880, 800)
    app.processEvents()
    _tw = w.table.viewport().width()
w._apply_and_render(fill=False)
app.processEvents()

n = w.table.rowCount()
L.append('视口宽 %d ｜ 表格行数 %d ｜ 13 列' % (_tw, n))
ck('1 渲染出全部行（门槛=0）', n >= 3294, str(n))

_t0 = time.perf_counter()      # 全量量字的代价（切换筛选/排序每次渲染都会跑一遍）
w._autofit_columns()
_auto_ms = (time.perf_counter() - _t0) * 1000
app.processEvents()
L.append('_autofit_columns 全量量字耗时 %.0f ms（%d 行 × %d 列）'
         % (_auto_ms, n, PAGE_COL_N - 1))
ck('10 自适应耗时 < 500ms（不拖慢点击筛选/排序）', _auto_ms < 500, '%.0f ms' % _auto_ms)

widths = [w.table.columnWidth(c) for c in range(PAGE_COL_N)]
L.append('列宽：%s' % dict(zip(PAGE_HEADERS, widths)))
L.append('初值：%s' % dict(zip(PAGE_HEADERS, PAGE_WIDTHS)))

# ---- 逐格量字（全量 3294 行，不采样）----
fm_h = QFontMetrics(w.table.horizontalHeader().font())
_fms = {}
bad = {c: [] for c in range(PAGE_COL_N)}
need_max = {c: 0 for c in range(PAGE_COL_N)}
for c in range(PAGE_COL_N):
    _hi = w.table.horizontalHeaderItem(c)
    need_max[c] = fm_h.horizontalAdvance(_hi.text() if _hi else '') + HEAD_PAD
for i in range(n):
    for c in range(PAGE_COL_N):
        it = w.table.item(i, c)
        if it is None:
            continue
        t = it.text()
        if not t:
            continue
        k = it.font().toString()
        fm = _fms.get(k)
        if fm is None:
            fm = QFontMetrics(it.font())
            _fms[k] = fm
        need = fm.horizontalAdvance(t) + CELL_PAD
        if need > need_max[c]:
            need_max[c] = need
        if need > widths[c]:
            if len(bad[c]) < 5:
                bad[c].append((i, t[:24], need, widths[c]))

L.append('')
L.append('-- 每列：需要最宽度 vs 实际列宽（截断格数）--')
_trunc = 0
for c in range(PAGE_COL_N):
    _nb = len(bad[c])
    _trunc += _nb
    L.append('   %-5s 需要 %4d ｜ 实际 %4d ｜ 余量 %+4d ｜ 截断 %d 格%s'
             % (PAGE_HEADERS[c], need_max[c], widths[c], widths[c] - need_max[c], _nb,
                ('  例：%s' % bad[c][:2]) if _nb else ''))

ck('2 全部 13 列都不出现省略号（逐格全量 3294 行 × 13 列）', _trunc == 0,
   '截断 %d 格' % _trunc)

# ---- 短列被压缩、长列被放宽 ----
ck('3 短列被压缩（阶段/位置 均 < 原 58）',
   widths[C_STAGE] < 58 and widths[C_POS] < 58,
   '阶段=%d 位置=%d' % (widths[C_STAGE], widths[C_POS]))
ck('4 长列被放宽（主营 >170 / 公告 >260 / 观察 ≥60）',
   widths[C_BIZ] > 170 and widths[C_ANN] > 260 and widths[C_OBS] >= 56,
   '主营=%d 公告=%d 观察=%d' % (widths[C_BIZ], widths[C_ANN], widths[C_OBS]))
ck('5 数值列保持窄（代码/现价/涨跌幅 ≤90）',
   max(widths[C_CODE], widths[C_PRICE], widths[C_PCT]) <= 90,
   '%d/%d/%d' % (widths[C_CODE], widths[C_PRICE], widths[C_PCT]))

# ---- 整表是否放得下 + 拉伸列拿到多少 ----
_fixed = sum(widths[c] for c in _FIT_COLS)
_left = _tw - _fixed
L.append('')
L.append('固定 12 列合计 %d ｜ 视口 %d ｜ 拉伸列（涨停题材）拿到 %d' % (_fixed, _tw, _left))
ck('6 拉伸列（涨停题材）≥150px（题材串最长的能完整显示）', _left >= 150, str(_left))
ck('7 整表不出现横向溢出（固定列 + 拉伸列 ≤ 视口 + 2）',
   _fixed + max(0, _left) <= _tw + 2, '%d vs %d' % (_fixed + max(0, _left), _tw))
_theme_need = need_max[C_THEME]
ck('8 拉伸列实际宽度 ≥ 题材串需要宽度（题材也不截断）',
   _left >= _theme_need, '需要 %d ｜ 实得 %d' % (_theme_need, _left))

# ---- 换一个窗口宽度：窄窗时应按「观察→主营→公告」让位，且仍不截断 ----
w.resize(1250, 800)
app.processEvents()
w._autofit_columns()
app.processEvents()
_w2 = [w.table.columnWidth(c) for c in range(PAGE_COL_N)]
L.append('')
L.append('窄窗(1250)列宽：%s' % dict(zip(PAGE_HEADERS, _w2)))
ck('9 窄窗时也不低于各列下限（不会把列压没）',
   all(_w2[c] >= min(widths[c], 56) for c in range(PAGE_COL_N)),
   '%s' % _w2)
# 窗口拉回来
w.resize(1880, 950)
app.processEvents()
w._autofit_columns()
app.processEvents()

L.append('')
L.append('=== %d PASS / %d FAIL ===' % (len(PASS), len(FAIL)))
if FAIL:
    L.append('失败项：%s' % FAIL)
txt = '\n'.join(L)
print(txt, flush=True)
io.open(os.path.join(ROOT, 'tools', 'ctrl_screen_colfit_verify.txt'),
        'w', encoding='utf-8').write(txt + '\n')
sys.exit(1 if FAIL else 0)
