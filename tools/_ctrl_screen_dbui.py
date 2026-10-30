# -*- coding: utf-8 -*-
"""控盘选股页 UI 离屏验证（可重跑，需 QT_QPA_PLATFORM=offscreen）。

覆盖：
  [A] 源码级：列数/表头/列宽常量、拉伸列（题材）、阶段文案表、点击列
  [B] 用真实快照渲染：行数=筛选数、13 列全填、无空列
  [C] 前 15 行逐格与源数据比对（含颜色与 tooltip）+ 涨停题材列专项
  [K] 新增「主营收入 / 最新公告」两列（真实补数缓存 + 空态构造）+ 补数开关/进度
  [D] 改条件后行数=服务层 apply_filters 结果（分数/位置/ST/观察 四条）
  [E] 点击名称/代码发信号、点其它列不发
  [F] 列排序（控盘分、名称、题材、主营、公告）
  [G] 单元格只读、单行选择
  [H] 扫描进度信号 → 进度条与状态文本
  [I] 挂进 QTabWidget 后离屏渲染不崩（模拟主窗口 addTab）
  [J] 导出按钮全链路（打桩 QFileDialog/QMessageBox）→ 文件内容正确
结果写 tools\\ctrl_screen_dbui.txt。
"""
import io
import os
import sys
import tempfile
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import (QApplication, QTabWidget, QFileDialog,   # noqa: E402
                             QMessageBox)
from PyQt6.QtCore import Qt                                          # noqa: E402

import services.control_screen_service as SS                          # noqa: E402
from ui.battle_widgets.control_screen_widget import (                 # noqa: E402
    ControlScreenWidget, PAGE_HEADERS, PAGE_COL_N, PAGE_WIDTHS, C_NAME, C_CODE,
    C_PRICE, C_PCT, C_THEME, C_BIZ, C_SCORE, C_STAGE, C_POS, C_LABEL, C_OBS,
    C_ANN, C_DATE, _obs_color, _theme_tip, _THEME_COLOR, _BIZ_COLOR, _ANN_COLOR,
    _BIZ_EMPTY_TIP, _ANN_EMPTY_TIP)

PASS, FAIL, LINES = [], [], []
HEADERS_13 = ['股票名称', '代码', '现价', '涨跌幅', '涨停题材', '主营收入', '控盘分',
              '阶段', '位置', '控盘提示', '观察', '最新公告', '数据日']


def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    LINES.append('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                              (' ｜ %s' % extra) if extra else ''))


def main():
    t0 = time.perf_counter()
    app = QApplication.instance() or QApplication([])
    src = io.open(os.path.join(r'D:\QuantMonitorV6', 'ui', 'battle_widgets',
                               'control_screen_widget.py'),
                  'r', encoding='utf-8').read()

    # ---------- [A] 源码级 ----------
    ck('A1 列数=13 且表头与常量一致（第5列题材 / 第6列主营 / 第12列公告）',
       PAGE_COL_N == 13 and len(PAGE_HEADERS) == 13 and PAGE_HEADERS == HEADERS_13,
       '列数=%d' % PAGE_COL_N)
    ck('A2 列宽常量 13 项', len(PAGE_WIDTHS) == PAGE_COL_N, str(PAGE_WIDTHS))
    ck('A3 涨停题材是拉伸列（题材串最长）、末列不再拉伸',
       'setStretchLastSection(False)' in src
       and 'hh.setSectionResizeMode(C_THEME, QHeaderView.ResizeMode.Stretch)' in src)
    ck('A4 阶段文案：出货/洗盘/—',
       "_STAGE_TXT = {'distribute': '出货', 'wash': '洗盘', 'unknown': '—'}" in src)
    ck('A5 点击列只有名称与代码',
       'if col not in (C_NAME, C_CODE):' in src)
    ck('A6 只按需扫描、无定时刷新（refresh 为空实现）',
       'def refresh(self):' in src and '本页只按需扫描' in src)
    ck('A7 主营/公告要联网 → 只在切到本页(showEvent)或扫描完成时补、载入快照不补',
       'QTimer.singleShot(300, self._ensure_extras)' in src
       and '_apply_and_render(fill=False)' in src
       and src.count('self._ensure_extras') >= 4          # 快照载入/切页/扫完/补完 四处触发
       and "if not self._ck_extra.isChecked() or self._filling:" in src)

    # ---------- [B] 真实快照渲染 ----------
    snap = SS.load_snapshot()
    ck('B0 存在真实快照（data/cache/control_screen.json）', snap is not None,
       '行数=%d' % (len(snap['rows']) if snap else 0))
    if not snap:
        _dump(t0)
        return 1
    all_rows = snap['rows']
    w = ControlScreenWidget()
    exp = SS.apply_filters(all_rows, min_score=85.0, pos_max=None, exclude_dist=True,
                           min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    ck('B1 默认条件行数 = 服务层筛选数', w.table.rowCount() == len(exp),
       '表格=%d 服务层=%d' % (w.table.rowCount(), len(exp)))
    ck('B2 表格列数 = 13', w.table.columnCount() == 13,
       '列数=%d' % w.table.columnCount())
    ck('B3 表头文字逐列一致',
       [w.table.horizontalHeaderItem(i).text() for i in range(13)] == PAGE_HEADERS)
    _null = [(i, c) for i in range(min(50, w.table.rowCount()))
             for c in range(13) if w.table.item(i, c) is None]
    ck('B4 前 50 行 13 列全部有单元格（无空列）', not _null, str(_null[:5]))
    ck('B5 统计条包含「符合条件/数据日/主营已补」',
       '符合条件' in w._count_label.text() and '数据日' in w._count_label.text()
       and '主营已补' in w._count_label.text(), w._count_label.text()[:140])

    # ---------- [C] 前 15 行逐格比对 ----------
    bad = []
    for i in range(min(15, w.table.rowCount())):
        r = exp[i]
        _rec = w._extra_rec(r)
        _want = {
            C_NAME: (str(r['name']),),
            C_CODE: (str(r['code']),),
            C_PRICE: ('%.2f' % float(r['price']),),
            C_PCT: ('%+.2f%%' % float(r['pct']),),
            C_THEME: (str(r.get('theme') or '') or '--',),
            C_BIZ: (SS.fmt_biz(_rec)[0] or '--',),
            C_SCORE: ('%.1f' % float(r['score']),),
            C_STAGE: ({'distribute': '出货', 'wash': '洗盘', 'unknown': '—'}.get(r['stage'], r['stage']),),
            C_POS: ('%.2f' % float(r['pos']),),
            C_LABEL: (str(r['label']) if r['label'] else '—',),
            C_OBS: (' ｜ '.join(r['observe']) if r['observe'] else '—',),
            C_ANN: (SS.fmt_ann(_rec)[0] or '--',),
            C_DATE: (str(r['data_date']),),
        }
        for c, (want,) in _want.items():
            got = w.table.item(i, c).text()
            if got != want:
                bad.append((i, c, want, got))
        if str(r.get('note') or '') != w.table.item(i, C_LABEL).toolTip():
            bad.append((i, C_LABEL, 'tooltip=%r' % r.get('note'), w.table.item(i, C_LABEL).toolTip()))
        if _theme_tip(r) != w.table.item(i, C_THEME).toolTip():
            bad.append((i, C_THEME, 'tooltip=%r' % _theme_tip(r),
                        w.table.item(i, C_THEME).toolTip()))
        if (SS.fmt_biz(_rec)[1] or _BIZ_EMPTY_TIP) != w.table.item(i, C_BIZ).toolTip():
            bad.append((i, C_BIZ, 'biz tooltip', w.table.item(i, C_BIZ).toolTip()[:40]))
        if (SS.fmt_ann(_rec)[1] or _ANN_EMPTY_TIP) != w.table.item(i, C_ANN).toolTip():
            bad.append((i, C_ANN, 'ann tooltip', w.table.item(i, C_ANN).toolTip()[:40]))
    ck('C1 前 15 行 × 13 列 逐格文本一致 + 4 类 tooltip 一致', not bad, str(bad[:4]))
    _r0 = exp[0]
    _sc_col = w.table.item(0, C_SCORE).foreground().color().name()
    _want_col = ('#e53935' if float(_r0['score']) >= 90
                 else ('#ff6d00' if float(_r0['score']) >= 85 else '#333333'))
    ck('C2 控盘分颜色按档（≥90 红 / ≥85 橙 / 其它灰）', _sc_col.lower() == _want_col.lower(),
       '%s vs %s' % (_sc_col, _want_col))
    _pct_col = w.table.item(0, C_PCT).foreground().color().name()
    _want_pct = ('#e53935' if float(_r0['pct']) > 0
                 else ('#43a047' if float(_r0['pct']) < 0 else '#999999'))
    ck('C3 涨跌幅颜色 红涨绿跌', _pct_col.lower() == _want_pct.lower(),
       '%s vs %s' % (_pct_col, _want_pct))
    _obs_col0 = w.table.item(0, C_OBS).foreground().color().name()
    ck('C4 观察列颜色 = _obs_color 规则',
       _obs_col0.lower() == _obs_color(_r0['observe']).lower())
    _pi = next((i for i in range(min(200, w.table.rowCount()))
                if float(exp[i]['pos']) < 0.25), None)
    if _pi is not None:
        ck('C5 位置 <0.25 显示红色', w.table.item(_pi, C_POS).foreground().color().name()
           .lower() == '#e53935')
    else:
        ck('C5 位置 <0.25 显示红色', False, '前200行没有 pos<0.25 样本')

    # ---------- [C-题材] ----------
    _ti = next((i for i in range(w.table.rowCount()) if exp[i].get('theme')), None)
    ck('C6 有题材行：文本=题材串（含+）、色=#6a1b9a、tooltip 带来源/连板/行业',
       _ti is not None
       and w.table.item(_ti, C_THEME).text() == exp[_ti]['theme']
       and '+' in exp[_ti]['theme']
       and w.table.item(_ti, C_THEME).foreground().color().name().lower() == _THEME_COLOR
       and '涨停题材' in w.table.item(_ti, C_THEME).toolTip()
       and '连板' in w.table.item(_ti, C_THEME).toolTip(),
       'idx=%s' % _ti)
    _tn = next((i for i in range(w.table.rowCount()) if not exp[i].get('theme')), None)
    ck('C7 无题材行：显示 -- 且为灰（不是紫色）',
       _tn is not None
       and w.table.item(_tn, C_THEME).text() == '--'
       and w.table.item(_tn, C_THEME).foreground().color().name().lower() == '#999999',
       'idx=%s' % _tn)
    _al = int(w.table.item(_ti, C_THEME).textAlignment()) if _ti is not None else 0
    ck('C8 题材列左对齐（长串可读）', bool(_al & 0x1) and not (_al & 0x2), 'align=%d' % _al)
    ck('C9 题材列宽度 ≥200px（能显示长题材串）', w.table.columnWidth(C_THEME) >= 200,
       'w=%d' % w.table.columnWidth(C_THEME))

    # ---------- [K] 主营收入 + 最新公告 ----------
    _cache_n = len(w._extras)
    ck('K1 页面启动即加载补数缓存（内存态，不联网）',
       _cache_n > 0 and 'SS.load_extras()' in src, '缓存 %d 条' % _cache_n)
    _biz_i = next((i for i in range(w.table.rowCount()) if w._extra_rec(exp[i]).get('biz')), None)
    ck('K2 有主营行：文本=「第一大项 营收」、色 #00695c、tooltip 带报告期与分项',
       _biz_i is not None
       and w.table.item(_biz_i, C_BIZ).text() == SS.fmt_biz(w._extra_rec(exp[_biz_i]))[0]
       and w.table.item(_biz_i, C_BIZ).foreground().color().name().lower() == _BIZ_COLOR
       and '主营构成' in w.table.item(_biz_i, C_BIZ).toolTip(),
       'idx=%s 文本=%s' % (_biz_i, (w.table.item(_biz_i, C_BIZ).text()
                                   if _biz_i is not None else '')))
    _ann_i = next((i for i in range(w.table.rowCount()) if w._extra_rec(exp[i]).get('ann')), None)
    ck('K3 有公告行：文本=「MM-DD 标题」（已去「简称:」前缀）、色 #1565c0、tooltip 带来源/日期',
       _ann_i is not None
       and w.table.item(_ann_i, C_ANN).text() == SS.fmt_ann(w._extra_rec(exp[_ann_i]))[0]
       and w.table.item(_ann_i, C_ANN).text()[:5].count('-') == 1
       and w.table.item(_ann_i, C_ANN).foreground().color().name().lower() == _ANN_COLOR
       and '最新公告' in w.table.item(_ann_i, C_ANN).toolTip(),
       'idx=%s 文本=%s' % (_ann_i, (w.table.item(_ann_i, C_ANN).text()
                                   if _ann_i is not None else '')[:40]))
    # 空态：临时摘掉某一行的缓存再重绘（验证「--/灰色/默认 tooltip」分支，不改数据文件）
    _code = str(exp[0]['code'])
    _keep = w._extras.pop(_code, None)
    w._render()
    ck('K4 无数据行：显示 -- 、灰色、tooltip 为默认空态文案',
       w.table.item(0, C_BIZ).text() == '--' and w.table.item(0, C_ANN).text() == '--'
       and w.table.item(0, C_BIZ).foreground().color().name().lower() == '#999999'
       and w.table.item(0, C_ANN).foreground().color().name().lower() == '#999999'
       and w.table.item(0, C_BIZ).toolTip() == _BIZ_EMPTY_TIP
       and w.table.item(0, C_ANN).toolTip() == _ANN_EMPTY_TIP,
       'code=%s' % _code)
    if _keep is not None:
        w._extras[_code] = _keep
    w._render()
    ck('K5 恢复缓存后同一行又显示数据（缓存驱动，非一次性快照）',
       w.table.item(0, C_BIZ).text() != '--' or not (w._extra_rec(exp[0]).get('biz')))
    # 排序
    _keybiz = lambda r: str((w._extra_rec(r) or {}).get('biz') or '')
    _bizs = sorted(_keybiz(r) for r in w._rows)
    w.sorter._state_col = C_BIZ
    w.sorter._state_order = 'asc'
    w.sorter._apply()
    _gotb = [_keybiz(r) for r in w._rows]
    ck('K6 主营列升序生效（全量 %d 行之比对）' % len(_gotb), _gotb == _bizs,
       str(_gotb[:3]))
    w.sorter._state_col = C_ANN
    w.sorter._state_order = 'asc'
    w.sorter._apply()
    _anns = [str(((w._extra_rec(r) or {}).get('ann') or [['']])[0][0] or '') for r in w._rows[:20]]
    ck('K7 公告列升序生效（按日期）', _anns == sorted(_anns), str(_anns[:4]))
    w.sorter._state_col = C_SCORE
    w.sorter._state_order = 'desc'
    w.sorter._apply()
    # 补数开关
    ck('K8 补数开关默认勾选 + 取消勾选后 _ensure_extras 不发请求',
       w._ck_extra.isChecked() and w._filling is False, 'checked=%s' % w._ck_extra.isChecked())
    w._ck_extra.setChecked(False)
    _before = len(w._extras)
    w._extras.clear()
    w._ensure_extras()
    ck('K9 关闭开关时不补数（缓存被清也不会启动线程池）',
       w._filling is False and len(w._extras) == 0, 'filling=%s' % w._filling)
    w._extras.update(SS.load_extras())
    w._ck_extra.setChecked(True)
    ck('K10 打开开关 + 缓存完整时 _ensure_extras 立刻返回（extras_missing=0，不联网）',
       SS.extras_missing([str(r['code']) for r in exp], w._extras) == []
       and (w._ensure_extras() or w._filling is False))
    ck('K11 tooltip 不含本机路径（不泄露 D:\\ 之类）',
       all('D:\\' not in w.table.item(i, c).toolTip()
           for i in range(5) for c in (C_BIZ, C_ANN)))

    # ---------- [D] 条件联动 ----------
    # 关掉补数开关：D 段会放宽条件、可能引入缓存里没有的新代码 → 否则测试会联网
    w._ck_extra.setChecked(False)
    w._sp_score.setValue(95.0)
    exp95 = SS.apply_filters(all_rows, min_score=95.0, pos_max=None, exclude_dist=True,
                            min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    ck('D1 控盘分改 95 → 行数同步', w.table.rowCount() == len(exp95),
       '表格=%d 服务层=%d' % (w.table.rowCount(), len(exp95)))
    w._sp_score.setValue(85.0)
    w._cb_pos.setCurrentText('0.25')
    exp25 = SS.apply_filters(all_rows, min_score=85.0, pos_max=0.25, exclude_dist=True,
                            min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    ck('D2 位置改 0.25 → 行数同步', w.table.rowCount() == len(exp25),
       '表格=%d 服务层=%d' % (w.table.rowCount(), len(exp25)))
    w._cb_pos.setCurrentText('不限')
    w._ck_st.setChecked(False)
    expst = SS.apply_filters(all_rows, min_score=85.0, pos_max=None, exclude_dist=True,
                             min_price=6.0, drop_st=False, obs=SS.OBS_ALL)
    ck('D3 取消剔除ST → 行数同步', w.table.rowCount() == len(expst),
       '表格=%d 服务层=%d' % (w.table.rowCount(), len(expst)))
    w._ck_st.setChecked(True)
    w._cb_obs.setCurrentText(SS.OBS_NO_MARKUP)
    expnm = SS.apply_filters(all_rows, min_score=85.0, pos_max=None, exclude_dist=True,
                             min_price=6.0, drop_st=True, obs=SS.OBS_NO_MARKUP)
    ck('D4 观察=排除拉升 → 行数同步', w.table.rowCount() == len(expnm),
       '表格=%d 服务层=%d' % (w.table.rowCount(), len(expnm)))
    ck('D5 排除拉升后表内无「拉升」标签',
       all('拉升' not in (w.table.item(i, C_OBS).text() or '')
           for i in range(w.table.rowCount())))
    w._cb_obs.setCurrentText(SS.OBS_ALL)
    w._ck_extra.setChecked(True)

    # ---------- [E] 点击发信号 ----------
    _got = []
    w.stock_clicked.connect(lambda c, n: _got.append((c, n)))
    w._on_cell_clicked(0, C_NAME)
    w._on_cell_clicked(1, C_CODE)
    w._on_cell_clicked(2, C_SCORE)   # 不该发信号
    w._on_cell_clicked(3, C_BIZ)     # 不该发信号
    w._on_cell_clicked(4, C_ANN)     # 不该发信号
    ck('E1 点名称/代码发信号、点其它列（含新增两列）不发', len(_got) == 2
       and _got[0] == (str(w._rows[0]['code']), str(w._rows[0]['name']))
       and _got[1] == (str(w._rows[1]['code']), str(w._rows[1]['name'])), str(_got))
    ck('E2 行数超界不崩', (w._on_cell_clicked(99999, C_NAME) or True))

    # ---------- [F] 排序 ----------
    w.sorter._state_col = C_SCORE
    w.sorter._state_order = 'asc'
    w.sorter._apply()
    _asc = [float(r['score']) for r in w._rows[:20]]
    ck('F1 控盘分升序生效', _asc == sorted(_asc), str(_asc[:6]))
    w.sorter._state_col = C_SCORE
    w.sorter._state_order = 'desc'
    w.sorter._apply()
    _desc = [float(r['score']) for r in w._rows[:20]]
    ck('F2 控盘分降序生效', _desc == sorted(_desc, reverse=True), str(_desc[:6]))
    w.sorter._state_col = C_NAME
    w.sorter._state_order = 'asc'
    w.sorter._apply()
    _nm = [str(r['name']) for r in w._rows[:20]]
    ck('F3 名称升序生效', _nm == sorted(_nm), str(_nm[:5]))
    ck('F4 排序后表格同步（首行名称=排序后首行）',
       w.table.item(0, C_NAME).text() == (str(w._rows[0]['name']) if w._rows else ''))
    w.sorter._state_col = C_THEME
    w.sorter._state_order = 'asc'
    w.sorter._apply()
    _ths = [str(r.get('theme') or '') for r in w._rows[:20]]
    ck('F5 题材列升序生效', _ths == sorted(_ths), str([t[:6] for t in _ths[:5]]))
    w.sorter._state_col = C_SCORE
    w.sorter._state_order = 'desc'
    w.sorter._apply()

    # ---------- [G] 单元格属性 ----------
    from PyQt6.QtWidgets import QAbstractItemView as _AIV
    _bsrc = io.open(os.path.join(r'D:\QuantMonitorV6', 'ui', 'battle_widgets', 'base.py'),
                    'r', encoding='utf-8').read()
    ck('G1 表格只读（视图 editTriggers=NoEditTriggers）',
       w.table.editTriggers() == _AIV.EditTrigger.NoEditTriggers
       and 'NoEditTriggers' in _bsrc, str(w.table.editTriggers()))
    ck('G2 选择模式=单行', w.table.selectionMode() == _AIV.SelectionMode.SingleSelection,
       str(w.table.selectionMode()))
    ck('G3 选中行为整行选择',
       w.table.selectionBehavior() == _AIV.SelectionBehavior.SelectRows,
       str(w.table.selectionBehavior()))

    # ---------- [H] 进度信号 ----------
    w._ck_extra.setChecked(False)     # H/I/J 段不联网
    w._scanning = True
    w._on_scan_progress(500, 1000, '正在计算 500/1000')
    ck('H1 进度条 = 50%', w._bar.value() == 50, 'value=%d' % w._bar.value())
    ck('H2 状态文本带进度', '500/1000' in w.update_time_label.text(),
       w.update_time_label.text())
    w._scanning = False
    w._on_fill_progress(120, 300, '补主营/公告 120/300')
    ck('H3 补数进度也走状态栏', '补主营/公告 120/300' in w.update_time_label.text(),
       w.update_time_label.text())
    w._on_extras_fail('测试失败')
    ck('H4 补数失败回调不崩且提示原因', '测试失败' in w.update_time_label.text(),
       w.update_time_label.text())

    # ---------- [I] 挂进 QTabWidget ----------
    w._ck_auto.setChecked(False)     # 截图/测试环境不触发自动扫描
    w._ck_extra.setChecked(False)    # 也不触发补数联网
    tabs = QTabWidget()
    tabs.addTab(w, '🎛 控盘选股')
    tabs.resize(1900, 900)
    tabs.show()
    app.processEvents()
    ck('I1 addTab 后无异常、页签名正确',
       tabs.count() == 1 and tabs.tabText(0) == '🎛 控盘选股')
    ck('I2 离屏渲染后行数不变', w.table.rowCount() == len(exp),
       '%d' % w.table.rowCount())
    ck('I3 表格实际宽度>0（控件被正确布局）', w.table.width() > 500,
       'w=%d h=%d' % (w.table.width(), w.table.height()))
    _vis_cols = sum(1 for c in range(13) if not w.table.isColumnHidden(c))
    ck('I4 13 列均未隐藏', _vis_cols == 13, '%d' % _vis_cols)

    # ---------- [J] 导出全链路 ----------
    _out = os.path.join(tempfile.gettempdir(), 'ctrl_screen_ui_export.txt')
    _orig_dlg = QFileDialog.getSaveFileName
    _orig_info = QMessageBox.information
    _orig_warn = QMessageBox.warning
    _msgs = []
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_out, 'txt'))
    QMessageBox.information = staticmethod(lambda *a, **k: _msgs.append(('info', a[2] if len(a) > 2 else '')))
    QMessageBox.warning = staticmethod(lambda *a, **k: _msgs.append(('warn', a[2] if len(a) > 2 else '')))
    try:
        w._export_codes()
    finally:
        QFileDialog.getSaveFileName = _orig_dlg
        QMessageBox.information = _orig_info
        QMessageBox.warning = _orig_warn
    try:
        _txt = io.open(_out, 'r', encoding='utf-8').read().strip().split('\n')
    except Exception:
        _txt = []
    ck('J1 导出按钮写出文件且条数=当前筛出行数',
       len(_txt) == len(w._rows) and len(_txt) > 0,
       '文件 %d 行 vs 表格 %d 行' % (len(_txt), len(w._rows)))
    ck('J2 导出内容 = 当前表格代码列、同序',
       _txt == [w.table.item(i, C_CODE).text() for i in range(w.table.rowCount())])
    ck('J3 导出后提示了成功弹窗', any(m[0] == 'info' for m in _msgs), str(_msgs[:2]))

    _dump(t0)
    return 1 if FAIL else 0


def _dump(t0=None):
    LINES.append('')
    LINES.append('=== %d PASS / %d FAIL%s ==='
                 % (len(PASS), len(FAIL), (' ｜ %.0fs' % (time.perf_counter() - t0)) if t0 else ''))
    if FAIL:
        LINES.append('失败项：%s' % FAIL)
    txt = '\n'.join(LINES)
    print(txt, flush=True)
    with io.open(r'D:\QuantMonitorV6\tools\ctrl_screen_dbui.txt', 'w', encoding='utf-8') as f:
        f.write(txt + '\n')


if __name__ == '__main__':
    sys.exit(main())
