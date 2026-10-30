# -*- coding: utf-8 -*-
"""验证 UI 空间与按钮改动（可重跑）：
A 源文件结构  B 操作建议短标签  C 分时做T表真实渲染（820px 容器）逐格不截断
D 标题栏按钮  E 我的自选表  F 真实库 + 右键两项能力（临时库往返）
用法：python tools\\_verify_ui_space.py
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)

PASS, FAIL = [], []


def ok(tag, cond, extra=''):
    (PASS if cond else FAIL).append(tag)
    print('[%s] %-8s %s' % ('PASS' if cond else 'FAIL', tag, extra))


from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
_f = r'C:\Windows\Fonts\msyh.ttc'
if os.path.exists(_f):
    _id = QFontDatabase.addApplicationFont(_f)
    if _id >= 0 and QFontDatabase.applicationFontFamilies(_id):
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(_id)[0], 9))

BTN_ADD = "QPushButton('\u2795 \u6dfb\u52a0\u4e2a\u80a1')"   # QPushButton('➕ 添加个股')

print('==== A. 源文件结构 ====')
SRC = open(os.path.join(ROOT, 'ui', 'battle_widgets', 'atr_t_widget.py'),
           newline='', encoding='utf-8').read()
ok('A1 无 _btn_add 残留', SRC.count('_btn_add') == 0)
ok('A2 「添加个股」按钮已删', BTN_ADD not in SRC)
ok('A3 弹窗/加库死代码已清',
   all(k not in SRC for k in ('_build_holding_dialog', '_watchlist_items',
                              '_add_watch_codes', '_open_holding_manager',
                              '_resolve_stock_name')))
ok('A4 右键菜单已挂', 'CustomContextMenu' in SRC and '_on_hold_context_menu' in SRC)
ok('A5 右键三项齐全', all(k in SRC for k in ('补成本/数量', '从做T列表移除', '↻ 刷新')))
ok('A6 增删方法仍在', SRC.count('_update_cost_qty') >= 2 and SRC.count('_remove_holding') >= 2)
ok('A7 列宽自适应已接', SRC.count('_fit_hold_columns') >= 2 and '_HOLD_MAXW' in SRC)
ok('A8 两处兜底都放宽到 8 字',
   SRC.count('return act[:8]') == 2 and SRC.count('return act[:6]') == 0)
ok('A9 建表不再给 Stretch 列塞宽度', 'if i != COL_H_ACT' in SRC)
ok('A10 纯 CRLF', SRC.count('\n') - SRC.count('\r\n') == 0)
WATCH = open(os.path.join(ROOT, 'ui', 'battle_widgets', 'watchlist_widget.py'),
             newline='', encoding='utf-8').read()
ok('A11 自选表题材挂 tooltip', '_tit.setToolTip(theme)' in WATCH)
ok('A12 自选表仍纯 CRLF', WATCH.count('\n') - WATCH.count('\r\n') == 0)

print('\n==== B. 操作建议短标签 ====')
from ui.battle_widgets.atr_t_widget import AtrTWidget, COL_H_ACT, HEADER_HOLD  # noqa: E402

for raw, want in [
        ('不做T，等条件恢复', '不做T·等条件'),
        ('先卖后买 1000股：卖 26.23 → 回落买回 24.37，成本 → 25.610 (-0.826%)', '反T·先卖后买'),
        ('先买后卖 500股：买 26.00 → 反弹卖出 26.80，需资金 13000元', '正T·先买后卖'),
        ('接近条件，等 VWAP/量价配合', '等VWAP量价'),
        ('观望', '观望')]:
    got = AtrTWidget._short_action(raw)
    ok('B %s' % want, got == want, '「%s…」→ %s' % (raw[:12], got))
ok('B6 旧文案仍走老分支',
   AtrTWidget._short_action('防T飞') == '防T飞' and AtrTWidget._short_action('锁仓不动') == '锁仓')

print('\n==== C. 真实渲染：分时做T表（容器 820px ≈ 你屏幕右半屏） ====')
w = AtrTWidget()
try:
    w.stop_refresh()
    w._daily_timer.stop()
except Exception:
    pass
rows, _tr, _ow = w._fetch_and_calc()
w._on_hold_loaded((rows, _tr, _ow))
w.resize(1600, 900)
w.show()
app.processEvents()
t = w.table
t.resize(820, 560)
app.processEvents()
w._fit_hold_columns()
app.processEvents()
print('  行数 %d ｜ 表视口 %d ｜ 列宽合计 %d' % (
    t.rowCount(), t.viewport().width(), sum(t.columnWidth(c) for c in range(t.columnCount()))))

bad = []
for c in range(t.columnCount()):
    if c == COL_H_ACT:
        continue
    need = QFontMetrics(t.font()).horizontalAdvance(HEADER_HOLD[c]) + AtrTWidget._HOLD_PAD
    for r in range(t.rowCount()):
        it = t.item(r, c)
        if it is None or not it.text():
            continue
        need = max(need, QFontMetrics(it.font()).horizontalAdvance(it.text())
               + AtrTWidget._HOLD_PAD)
    if t.columnWidth(c) + 0.5 < need:
        bad.append((HEADER_HOLD[c], t.columnWidth(c), int(need)))
ok('C1 除操作建议外每格文字都放得下', not bad, '不足处 %s' % (bad if bad else '无'))
act_need = 40
for r in range(t.rowCount()):
    it = t.item(r, COL_H_ACT)
    if it is not None and it.text():
        act_need = max(act_need, QFontMetrics(it.font()).horizontalAdvance(it.text()) + 14)
ok('C2 操作建议列宽足够（不截断）', t.columnWidth(COL_H_ACT) >= act_need,
   '列宽 %d ≥ 需要 %d' % (t.columnWidth(COL_H_ACT), act_need))
ok('C3 30 行都渲染', t.rowCount() >= 20, '实际 %d 行' % t.rowCount())
tips = {'动能': 0, '风控': 0, '信号灯': 0, '操作建议': 0}
for r in range(t.rowCount()):
    for c, k in ((6, '动能'), (7, '风控'), (8, '信号灯'), (COL_H_ACT, '操作建议')):
        it = t.item(r, c)
        if it is not None and it.toolTip():
            tips[k] += 1
ok('C4 四列都有悬停全文', all(v > 0 for v in tips.values()), str(tips))
ok('C5b 表头短名且悬停有全称',
   HEADER_HOLD[0] == '名称' and all(t.horizontalHeaderItem(c).toolTip()
                                    for c in (0, 4, 5)))
ok('C5 操作建议无 6 字硬切',
   all((t.item(r, COL_H_ACT) is None) or len(t.item(r, COL_H_ACT).text()) <= 8
       for r in range(t.rowCount())))

print('\n==== D. 标题栏按钮 ====')
btns = [b.text() for b in w.findChildren(QPushButton)]
ok('D1 标题栏没有「添加个股」', not any('添加个股' in x for x in btns), str(btns))
ok('D2 分时做T/日K建仓 Tab 还在',
   any('分时做T' in x for x in btns) and any('日K建仓' in x for x in btns))
ok('D3 导出按钮还在（日K建仓用）', any('导出' in x for x in btns))

print('\n==== E. 我的自选表（容器 945px ≈ 你屏幕左半屏） ====')
import ui.battle_widgets.watchlist_widget as WW  # noqa: E402

w2 = WW.WatchlistWidget()
w2.resize(945, 500)
w2.show()
app.processEvents()
t2 = w2.table
t2.resize(945, 400)
app.processEvents()
ok('E1 题材列比改前宽（原 110）', t2.columnWidth(WW.COL_THEME) >= 110,
   '题材 %d ｜ 名称 %d 代码 %d 现价 %d 涨幅 %d 振幅 %d 市值 %d 控盘 %d' % (
       t2.columnWidth(WW.COL_THEME), t2.columnWidth(0), t2.columnWidth(1),
       t2.columnWidth(2), t2.columnWidth(3), t2.columnWidth(4),
       t2.columnWidth(5), t2.columnWidth(WW.COL_CTRL)))
ok('E2 数字列未被压到缺字',
   t2.columnWidth(0) >= 68 and t2.columnWidth(3) >= 60 and t2.columnWidth(WW.COL_CTRL) >= 56)

print('\n==== F. 真实库 + 右键两项能力 ====')
import duckdb  # noqa: E402

DB = os.path.join(ROOT, 'data', 'cache', 'atr_t_tracking.duckdb')
con = duckdb.connect(DB, read_only=True)
n = con.execute('SELECT COUNT(*) FROM holding').fetchone()[0]
r1 = con.execute("SELECT code,name,cost,qty FROM holding WHERE code='000811'").fetchone()
r2 = con.execute("SELECT code,name,cost,qty FROM holding WHERE code='002838'").fetchone()
con.close()
ok('F1 真实库仍 30 行', n == 30, '实际 %d' % n)
ok('F2 000811 成本未动', r1 == ('000811', '冰轮环境', 37.571, 4300), str(r1))
ok('F3 002838 成本未动', r2 == ('002838', '道恩股份', 25.823, 8500), str(r2))

tmp = os.path.join(tempfile.gettempdir(), '_t_seat_test.duckdb')
if os.path.exists(tmp):
    os.remove(tmp)
shutil.copy(DB, tmp)
try:
    w3 = AtrTWidget()
    try:
        w3.stop_refresh()
        w3._daily_timer.stop()
    except Exception:
        pass
    w3._track_db_path = tmp                      # 只改临时库路径，真实库一行不碰
    w3._refresh_holding_db = lambda *a, **k: None
    _upd = _del = False
    try:
        w3._update_cost_qty('000062', 9.999, 1200)
        _upd = True
    except Exception as e:
        print('   _update_cost_qty 异常：%s: %s' % (type(e).__name__, e))
    c2 = duckdb.connect(tmp, read_only=True)
    row = c2.execute("SELECT cost,qty FROM holding WHERE code='000062'").fetchone()
    c2.close()
    ok('F4 右键「补成本/数量」可用（临时库）', _upd and row == (9.999, 1200), '写入 %s' % (row,))
    try:
        w3._remove_holding('000062')
        _del = True
    except Exception as e:
        print('   _remove_holding 异常：%s: %s' % (type(e).__name__, e))
    c2 = duckdb.connect(tmp, read_only=True)
    left = c2.execute("SELECT COUNT(*) FROM holding WHERE code='000062'").fetchone()[0]
    cnt_all = c2.execute('SELECT COUNT(*) FROM holding').fetchone()[0]
    c2.close()
    ok('F5 右键「从做T列表移除」可用（临时库）', _del and left == 0,
       '剩余 %d 行 ｜ 全表 %d 行' % (left, cnt_all))
    ok('F6 其他 29 行未受影响', cnt_all == 29, '全表 %d' % cnt_all)
    c3 = duckdb.connect(DB, read_only=True)
    n_after = c3.execute('SELECT COUNT(*) FROM holding').fetchone()[0]
    r1b = c3.execute("SELECT cost,qty FROM holding WHERE code='000811'").fetchone()
    c3.close()
    ok('F7 真实库未被测试污染', n_after == 30 and r1b == (37.571, 4300),
       '真实库 %d 行, 000811=%s' % (n_after, r1b))
finally:
    if os.path.exists(tmp):
        os.remove(tmp)

print('\n==== UI 空间与按钮  PASS %d / FAIL %d ====' % (len(PASS), len(FAIL)))
if FAIL:
    print('未通过：', FAIL)
LOG = os.path.join(ROOT, 'tools', 'ui_space_verify.log')
with open(LOG, 'w', encoding='utf-8') as f:
    f.write('==== UI 空间与按钮  PASS %d / FAIL %d ====\n' % (len(PASS), len(FAIL)))
    for x in FAIL:
        f.write('[FAIL] %s\n' % x)
    if not FAIL:
        f.write('（全部通过）\n')
print('日志 ->', LOG)
sys.exit(1 if FAIL else 0)
