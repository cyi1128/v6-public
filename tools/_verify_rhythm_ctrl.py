# -*- coding: utf-8 -*-
"""校验「市场节奏」模块的控盘度接入（Tab1 连板梯队 + Tab2 可介入 / 控盘列）。

只做验证，不改代码。可重跑。
  1) 源码级：列常量 / 表头 / 列宽 / 排序键 / 后台补算入口 是否真的接上
  2) 离屏真实渲染：用**真实K线**算真实控盘分，逐格比对控件里显示的内容
  3) 独立交叉验证：不走 control_profile 缓存，逐只重算，比对分数字符串
  4) 后台补算链路：清空缓存 -> 渲染（应为占位）-> _ctrl_async_fill -> 重绘后值出现
  5) 点击回归：可介入格仍能跳转，控盘格不会误触发
输出：tools\\rhythm_ctrl_verify.txt
"""
import io
import os
import re
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

OUT = []
PASS = [0]
FAIL = [0]


def chk(cond, msg):
    (PASS if cond else FAIL)[0] += 1
    OUT.append('%s  %s' % ('PASS' if cond else 'FAIL', msg))
    if not cond:
        print('FAIL: %s' % msg, flush=True)


# ======================================================================
# 1) 源码级检查
# ======================================================================
SRC = r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py'
raw = io.open(SRC, 'rb').read()
src = raw.decode('utf-8')

chk(raw.count(b'\r\n') == 0, '文件仍是纯 LF 写回（CRLF=%d）' % raw.count(b'\r\n'))
chk('(P_BOARD, P_COUNT, P_AVG, P_LEAD, P_PICKS, P_CTRL, P_MEMBERS) = range(7)'
    in src, 'Tab2 列常量已扩到 7 列并新增 P_CTRL')
chk("CTRL_COL_TITLE, '成分股']" in src, '表头第 6 列用统一常量 CTRL_COL_TITLE')
chk('self.pick_table = make_table(len(P_HEADERS), P_HEADERS)' in src,
    'make_table 列数跟随 P_HEADERS（不会漏改）')
chk('P_GRID = [104, 46, 100, 150, 470, 104, 260]' in src, 'P_GRID 已补控盘列宽度（可介入列加宽到 470，避免内联控盘被截断）')
chk('P_CTRL: _top_ctrl_score' in src, '控盘列已挂排序键')
chk(src.count('def _ctrl_async_fill') == 1 and 'self._ctrl_async_fill()' in src,
    '后台补算方法存在且被 _apply 调用')
chk('set_table_item(self.pick_table, row, P_CTRL' in src, '控盘列确实被写入')
chk('_ck, _cki = _ladder_ctrl(rows)' in src, 'Tab1 渲染顶部取了控盘缓存')
chk('_ctrl_inline(_pcm.get(str(p[0])))' in src, 'Tab2 可介入单元格内联控盘')
chk("_ck.get(str(x.get('code') or ''))" in src, 'Tab1 连板梯队内联控盘')

# ======================================================================
# 2) 真实数据准备
# ======================================================================
from services.kline_cache_service import (get_all_cached_codes,
                                          get_latest_kline)

codes_all = list(get_all_cached_codes() or [])
print('本地K线缓存股票数: %d' % len(codes_all), flush=True)
real = []
for c in codes_all:
    try:
        b = get_latest_kline(c, count=120)
    except Exception:
        b = None
    if b and len(b) >= 60:
        real.append((c, len(b)))
    if len(real) >= 8:
        break
chk(len(real) >= 6, '取到 ≥6 只本地有 ≥60 根K线的真实股票（实得 %d）' % len(real))

# 真实股票名（取不到就用代码当名字，不影响校验）
NAME = {}
try:
    from data.stock_list_provider import get_stock_name_map
    NAME = get_stock_name_map() or {}
except Exception:
    NAME = {}


def nm(code):
    try:
        return NAME.get(code) or NAME.get(str(code)) or ('股%s' % code[-2:])
    except Exception:
        return '股%s' % code[-2:]


pick_codes = [c for c, _n in real[:6]]
lad_codes = [c for c, _n in real[6:8]] or pick_codes[:2]

# ======================================================================
# 3) 预热真实控盘（走本地缓存，不联网）
# ======================================================================
from services.control_profile import (NO_DATA_TEXT, compute_one, ctrl_cell,
                                      get_ctrl_map)

all_codes = list(dict.fromkeys(pick_codes + lad_codes))
warm = get_ctrl_map(all_codes)
chk(sum(1 for c in all_codes if warm.get(c) and warm[c].get('ok')) >= 6,
    '预热成功：%d/%d 只算出真实控盘分' % (
        sum(1 for c in all_codes if warm.get(c) and warm[c].get('ok')),
        len(all_codes)))
OUT.append('样本股票控盘分：' + '  '.join(
    '%s %s=%.1f(%s)' % (c, nm(c), warm[c]['score'], warm[c]['stage'])
    for c in all_codes if warm.get(c) and warm[c].get('ok')))

# ---- 独立重算（不复用缓存），用于反证控件里显示的就是真实算出来的 ----
IND = {}
for c in all_codes:
    IND[c] = compute_one(c)


def ind_txt(c):
    return ctrl_cell(IND.get(c))[0]


# ======================================================================
# 4) 构造两个 Tab 的行（结构与真实引擎一致），离屏渲染
# ======================================================================
def mk_pick(code, i):
    return [code, nm(code), 2.0 + i * 0.7, 1.5 + i * 0.2, 12.3 + i,
            1.2 + i, 3.1e8 + i, 45.0 + i, 3.4 + i, 0.12, 1 if i == 0 else 0]


pick_rows = [
    {'kind': 'theme', 'name': '测试题材A', 'count': 5, 'avg_pct': 6.12, 'max_pct': 9.98,
     'lead_name': nm(pick_codes[0]), 'lead_code': pick_codes[0],
     'lead_pct': 9.98, 'members': [[c, nm(c), 2.0] for c in pick_codes[:4]],
     'picks': [mk_pick(c, i) for i, c in enumerate(pick_codes[:3])]},
    {'kind': 'industry', 'name': '测试行业B', 'count': 3, 'avg_pct': -1.35, 'max_pct': 5.10,
     'lead_name': nm(pick_codes[3]), 'lead_code': pick_codes[3],
     'lead_pct': 5.10, 'members': [[c, nm(c), 1.0] for c in pick_codes[3:7]],
     'picks': [mk_pick(c, i) for i, c in enumerate(pick_codes[3:8])]},
    {'kind': 'theme', 'name': '测试题材C', 'count': 2, 'avg_pct': 3.30, 'max_pct': 10.00,
     'lead_name': nm(pick_codes[-1]), 'lead_code': pick_codes[-1],
     'lead_pct': 10.0, 'members': [[pick_codes[-1], nm(pick_codes[-1]), 1.0]],
     'picks': []},
]

rhythm_rows = [
    {'theme': '测试题材A', 'mainline': '主线', 'state': '加速', 'count': 5,
     'prev_count': 3, 'run': 2, 'lbc_max': 3, 'lead': nm(lad_codes[0]),
     'lead_code': lad_codes[0], 'lead_lbc': 3, 'lead_time': '09:35',
     'is_attribute': 0, 'trend': [1, 2, 5], 'cluster': ['测试集群'],
     'ladder': [{'code': c, 'name': nm(c), 'lbc': 2 + i, 'time': '09:3%d' % i,
                 'reason': '测试涨停原因'} for i, c in enumerate(lad_codes)]},
    {'theme': '测试题材D', 'mainline': '', 'state': '启动', 'count': 2,
     'prev_count': 1, 'run': 1, 'lbc_max': 1, 'lead': nm(pick_codes[0]),
     'lead_code': pick_codes[0], 'lead_lbc': 1, 'lead_time': '10:05',
     'is_attribute': 1, 'trend': [1, 2], 'cluster': [],
     'ladder': [{'code': pick_codes[0], 'name': nm(pick_codes[0]), 'lbc': 1,
                 'time': '10:05', 'reason': ''}]},
]

from PyQt6.QtWidgets import QApplication          # noqa: E402

app = QApplication.instance() or QApplication([])

from ui.battle_widgets import market_rhythm_widget as MW      # noqa: E402

# 屏蔽自动刷新（否则 500ms 后 singleShot 会去拉行情/引擎，可能联网）
MW.MarketRhythmWidget.refresh = lambda self, force=False: None

w = MW.MarketRhythmWidget()
try:
    w.stop_timer()
except Exception:
    pass
app.processEvents()

chk(w.pick_table.columnCount() == 7, 'Tab2 实际列数 = 7（实得 %d）'
    % w.pick_table.columnCount())
chk(w.pick_table.horizontalHeaderItem(5).text() == '控盘',
    'Tab2 第 6 列表头 = 控盘（实得 %r）'
    % w.pick_table.horizontalHeaderItem(5).text())
chk(w.pick_table.horizontalHeaderItem(4).text() == '可介入'
    and w.pick_table.horizontalHeaderItem(6).text() == '成分股',
    '可介入 / 成分股 列号没被移位')

w._rows = rhythm_rows
w._pick_rows = pick_rows
w._render_rhythm_rows(rhythm_rows)
w._render_pick_rows(pick_rows)
app.processEvents()

# ---------------- Tab2 控盘列：逐行与独立重算比对 ----------------
for i, r in enumerate(pick_rows):
    got = w.pick_table.item(i, MW.P_CTRL)
    got = got.text() if got else ''
    picks = r['picks']
    if not picks:
        chk(got == '—', '第%d行（无候选）控盘格显示占位「—」（实得 %r）' % (i + 1, got))
        continue
    exp = [p[0] for p in picks]
    best = max((c for c in exp), key=lambda c: IND[c]['score']
               if IND.get(c) and IND[c].get('ok') else -1)
    chk(got == ind_txt(best),
        '第%d行控盘格 = 该题材候选里独立重算的最高分（显示 %r ｜ 期望 %r ｜ 最高分股 %s）'
        % (i + 1, got, ind_txt(best), best))
    tip = w.pick_table.item(i, MW.P_CTRL).toolTip() or ''
    chk('控盘' in tip and all(c in tip for c in exp[:3]),
        '第%d行控盘 tooltip 列出候选逐只控盘（含代码）' % (i + 1))

# ---------------- Tab2 可介入格：每只候选后带控盘 ----------------
for i, r in enumerate(pick_rows):
    cell = w.pick_table.item(i, MW.P_PICKS)
    txt = cell.text() if cell else ''
    if not r['picks']:
        continue
    ok = True
    for p in r['picks'][:3]:
        _s = ind_txt(p[0])   # 内联与控盘列同一套写法（带分隔符），不再去点
        if _s not in txt:
            ok = False
    chk(ok, '第%d行可介入格内联了每只候选的控盘分（%s）' % (i + 1, txt[:70]))
    tip = cell.toolTip() or ''
    chk('控盘' in tip and tip.count('控盘') >= len(r['picks']),
        '第%d行可介入 tooltip 每只候选都带控盘行（%d 处）'
        % (i + 1, tip.count('控盘')))

# ---------------- Tab1 连板梯队：内联控盘 + tooltip ----------------
cell0 = w.table.item(0, MW.C_LADDER)
t0 = cell0.text() if cell0 else ''
chk(all(ind_txt(c).replace('·', '') in t0 for c in lad_codes),
    'Tab1 连板梯队格内联每只个股控盘分（%s）' % t0[:70])
tip0 = cell0.toolTip() if cell0 else ''
chk('控盘' in tip0, 'Tab1 连板梯队 tooltip 带控盘')
_i0 = IND.get(lad_codes[0]) or {}
_exp0 = '控盘 %.1f（%s）' % (float(_i0.get('score') or -1), _i0.get('stage') or '--')
chk(_exp0 in tip0,
    'Tab1 tooltip 里第一只的控盘分与独立重算一致（期望 %r ｜ tooltip=%r）'
    % (_exp0, tip0[:150]))

# ---------------- 点击回归 ----------------
emitted = []
w.stock_clicked.connect(lambda c, n: emitted.append((c, n)))
w._on_pick_cell(0, MW.P_CTRL)
chk(not emitted, '点「控盘」列不会误触发跳转')
w._on_pick_cell(0, MW.P_PICKS)
chk(len(emitted) == 1 and emitted[0][0] == pick_rows[0]['picks'][0][0],
    '点「可介入」列仍能跳候选第一名（%r）' % (emitted[0] if emitted else None,))

# ======================================================================
# 5) 后台补算链路：清空缓存 -> 占位 -> _ctrl_async_fill -> 值出现
# ======================================================================
from services.control_profile import clear_cache        # noqa: E402

clear_cache()
w._render_pick_rows(pick_rows)
w._render_rhythm_rows(rhythm_rows)
app.processEvents()
_got = w.pick_table.item(0, MW.P_CTRL)
chk((_got.text() if _got else '') == NO_DATA_TEXT,
    '清缓存后先显示占位 %r（不阻塞、不出错）' % NO_DATA_TEXT)

w._ctrl_async_fill()
t0s = time.time()
_shown = list(w._all_stock_codes())
_out = []
while time.time() - t0s < 60:
    app.processEvents()
    _m = get_ctrl_map(_shown, cached_only=True)
    if all(_m.get(c) is not None for c in _shown):
        break
    time.sleep(0.05)
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
_got = w.pick_table.item(0, MW.P_CTRL)
_out = [p[0] for p in pick_rows[0]['picks']]
_best = max(_out, key=lambda c: IND[c]['score']
            if IND.get(c) and IND[c].get('ok') else -1)
chk((_got.text() if _got else '') == ind_txt(_best),
    '后台补算完成后自动重绘，控盘格出现真实值（%r ｜ 期望 %r ｜ 表格内代码 %d 只 ｜ 耗时 %.1fs）'
    % ((_got.text() if _got else ''), ind_txt(_best), len(_shown),
       time.time() - t0s))
cell0 = w.table.item(0, MW.C_LADDER)
chk(all(ind_txt(c).replace('·', '') in (cell0.text() if cell0 else '')
        for c in lad_codes), '后台重绘后 Tab1 连板梯队也带上了控盘分')

# ======================================================================
OUT.append('')
OUT.append('汇总：%d PASS / %d FAIL' % (PASS[0], FAIL[0]))
io.open(r'D:\QuantMonitorV6\tools\rhythm_ctrl_verify.txt', 'w',
        encoding='utf-8').write('\n'.join(OUT) + '\n')
print('\n'.join(OUT[-6:]), flush=True)
print('结果文件: tools\\rhythm_ctrl_verify.txt', flush=True)
