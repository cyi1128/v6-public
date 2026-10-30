# -*- coding: utf-8 -*-
"""验证「分时做T · 从我的自选添加」（可重跑；不污染真实库）。

跑法：python tools\\_verify_holdpicker.py   → 结果写 tools\\holdpicker_verify.log
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)

LOG = os.path.join(ROOT, 'tools', 'holdpicker_verify.log')
SRC = os.path.join(ROOT, 'ui', 'battle_widgets', 'atr_t_widget.py')
REAL_DB = os.path.join(ROOT, 'data', 'cache', 'atr_t_tracking.duckdb')

RES = []


def chk(name, cond, extra=''):
    RES.append((bool(cond), name, extra))
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra), flush=True)


src = open(SRC, newline='', encoding='utf-8').read()
seg = src[src.index('from PyQt6.QtWidgets import ('):]
seg = seg[:seg.index(')')]
chk('A1 导入 QInputDialog', 'QInputDialog' in seg)
for m in ('_watchlist_items', '_add_watch_codes', '_update_cost_qty',
          '_build_holding_dialog', '_open_holding_manager', '_remove_holding'):
    chk('A2 方法 %s' % m, src.count('def %s(self' % m) == 1)
chk('A3 旧手填表单及其死代码已彻底移除',
    src.count("setObjectName('ed_code')") == 0 and src.count('_parse_buy_time') == 0
    and src.count('_save_holding') == 0)
chk('A4 按钮 tooltip 已指向自选', '从「我的自选」勾选加入' in src)
chk('A5 双列表 + 6 个按钮齐全', all(k in src for k in (
    "setObjectName('lst_watch')", "setObjectName('lst_holdings')", "setObjectName('btn_add_sel')",
    "setObjectName('btn_add_all')", "setObjectName('btn_del')", "setObjectName('btn_edit')",
    "setObjectName('btn_all')", "setObjectName('btn_reload')")))
chk('A6 跳过已存在（不覆盖成本）写在同步逻辑里',
    'if c in have:' in src and 'skipped += 1' in src and '原有成本/数量未动' in src)
chk('A7 仍纯 CRLF', src.count('\n') - src.count('\r\n') == 0,
    'CRLF=%d 裸LF=%d' % (src.count('\r\n'), src.count('\n') - src.count('\r\n')))

from PyQt6.QtWidgets import QApplication, QMessageBox, QTableWidget, QInputDialog  # noqa: E402
app = QApplication.instance() or QApplication(sys.argv)
import ui.battle_widgets.atr_t_widget as mod  # noqa: E402
from ui.battle_widgets.atr_t_widget import AtrTWidget  # noqa: E402

rec = []
QMessageBox.warning = staticmethod(lambda *a, **k: (rec.append(('warning', a[2] if len(a) > 2 else '')), QMessageBox.StandardButton.Ok)[1])
QMessageBox.information = staticmethod(lambda *a, **k: (rec.append(('information', a[2] if len(a) > 2 else '')), QMessageBox.StandardButton.Ok)[1])
QMessageBox.critical = staticmethod(lambda *a, **k: (rec.append(('critical', a[2] if len(a) > 2 else '')), QMessageBox.StandardButton.Ok)[1])
QMessageBox.question = staticmethod(lambda *a, **k: (rec.append(('question', a[2] if len(a) > 2 else '')), QMessageBox.StandardButton.Yes)[1])

w = AtrTWidget()
w.stop_refresh()
try:
    w._daily_timer.stop()
except Exception:
    pass

# ---------- B. 按钮 ----------
chk('B1 Tab0 下按钮可见（isHidden=False）', not w._btn_add.isHidden())
chk('B2 按钮 index=3', w._card_frame.layout().itemAt(0).layout().indexOf(w._btn_add) == 3)
w._switch_tab(1)
chk('B3 日K建仓 Tab 下隐藏', w._btn_add.isHidden() and (not w._btn_export.isHidden()))
w._switch_tab(0)
chk('B4 切回分时做T 显示', (not w._btn_add.isHidden()) and w._btn_export.isHidden())

# ---------- C. 弹窗行为（临时库）----------
real_path = w._track_db_path
tmp_db = os.path.join(tempfile.gettempdir(), 'holdpicker_verify.duckdb')
for p in (tmp_db, tmp_db + '.wal'):
    if os.path.exists(p):
        os.remove(p)
w._track_db_path = tmp_db
w._init_tracking_db()
refreshed = []
w.refresh = lambda *a, **k: refreshed.append(1)


def db_rows():
    import duckdb
    con = duckdb.connect(tmp_db)
    try:
        return con.execute('SELECT code,name,cost,qty,buy_time FROM holding ORDER BY code').fetchall()
    finally:
        con.close()


watch = w._watchlist_items()
chk('C0 自选读取正常（%d 只）' % len(watch), len(watch) > 0, str(watch[:3]))

dlg = w._build_holding_dialog()
lst_watch = dlg.findChild(QTableWidget, 'lst_watch')
lst_hold = dlg.findChild(QTableWidget, 'lst_holdings')
btns = {}
for b in dlg.findChildren(mod.QPushButton):
    if b.objectName():
        btns[b.objectName()] = b
chk('C1 弹窗两个列表 + 按钮都在', lst_watch is not None and lst_hold is not None
    and all(k in btns for k in ('btn_add_sel', 'btn_add_all', 'btn_del', 'btn_edit', 'btn_all', 'btn_reload')))
chk('C2 左列表 = 自选全量且代码/名称正确',
    lst_watch.rowCount() == len(watch)
    and lst_watch.item(0, 0).text() == watch[0][0] and lst_watch.item(0, 1).text() == watch[0][1])
chk('C3 右列表初始为空（临时库无数据）', lst_hold.rowCount() == 0)

# 未选就点添加 → 提示
rec.clear()
btns['btn_add_sel'].click()
chk('C4 未选中就添加 → 给提示不写库',
    db_rows() == [] and any(x[0] == 'information' for x in rec))

# 全选 → 添加选中
btns['btn_all'].click()
chk('C5 全选生效', len({i.row() for i in lst_watch.selectedIndexes()}) == len(watch))
btns['btn_add_sel'].click()
r = db_rows()
chk('C6 添加选中 → 全部写入临时库', len(r) == len(watch), '库内 %d 行 / 自选 %d 只' % (len(r), len(watch)))
chk('C7 写入成本/数量为 NULL（自选股没有成本）', all(x[2] is None and x[3] is None for x in r))
chk('C8 名称取自自选（未走网络）',
    all(any(x[0] == c and x[1] == n for c, n in watch) for x in r))
chk('C9 右列表刷新且成本显示「—」',
    lst_hold.rowCount() == len(watch) and lst_hold.item(0, 2).text() == '—' and lst_hold.item(0, 3).text() == '—')
chk('C10 触发主表重算', len(refreshed) == 1)

# 再点「全部同步」→ 应全部跳过
rec.clear()
btns['btn_add_all'].click()
chk('C11 重复同步 → 0 新增且提示「没有新增」',
    len(db_rows()) == len(watch) and any('没有新增' in x[1] and str(len(watch)) in x[1] for x in rec),
    str([x for x in rec if x[0] == 'information'])[:140])

# 成本保护：先给一只填成本，再同步 → 不能被清空
first = watch[0][0]
import duckdb  # noqa: E402
con = duckdb.connect(tmp_db)
try:
    con.execute('UPDATE holding SET cost=?, qty=?, buy_time=? WHERE code=?',
                [12.345, 1600, '2026-10-01 09:35:00', first])
finally:
    con.close()
w._refresh_holding_db()
btns['btn_add_all'].click()
row = [x for x in db_rows() if x[0] == first][0]
chk('C12 同步不覆盖已填成本/数量/买入时间',
    abs(row[2] - 12.345) < 1e-9 and row[3] == 1600 and str(row[4]).startswith('2026-10-01'), str(row))

# 补成本/数量（打桩 QInputDialog）
QInputDialog.getText = staticmethod(lambda *a, **k: ('25.823', True))
i = [j for j in range(lst_hold.rowCount()) if lst_hold.item(j, 0).text() == first][0]
lst_hold.setCurrentCell(i, 0)
btns['btn_edit'].click()
row = [x for x in db_rows() if x[0] == first][0]
chk('C13 补成本/数量生效且买入时间保留',
    abs(row[2] - 25.823) < 1e-9 and str(row[4]).startswith('2026-10-01'), str(row))
QInputDialog.getText = staticmethod(lambda *a, **k: ('abc', True))
btns['btn_edit'].click()
row = [x for x in db_rows() if x[0] == first][0]
chk('C14 非法成本被拦（值未变）', abs(row[2] - 25.823) < 1e-9 and any(x[0] == 'warning' for x in rec))
QInputDialog.getText = staticmethod(lambda *a, **k: ('', True))

# 移除选中
lst_hold.clearSelection()
lst_hold.setCurrentCell(i, 0)
rec.clear()
before = len(db_rows())
btns['btn_del'].click()
after = db_rows()
chk('C15 移除选中生效', len(after) == before - 1 and all(x[0] != first for x in after))
chk('C16 移除后右列表刷新', lst_hold.rowCount() == len(after))
chk('C17 未选中就移除 → 提示', (
    rec.clear(), lst_hold.clearSelection(), btns['btn_del'].click(),
    any(x[0] == 'information' for x in rec))[-1])

w._track_db_path = real_path
del dlg
for p in (tmp_db, tmp_db + '.wal'):
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception as e:
        print('临时库清理失败:', e)

# ---------- D. 真实库：两只真实持仓的成本必须一字不动 ----------
con = duckdb.connect(REAL_DB)
try:
    real = con.execute('SELECT code,name,cost,qty FROM holding ORDER BY code').fetchall()
finally:
    con.close()
realmap = {r[0]: r for r in real}
chk('D1 真实库已按自选补齐（%d 行）' % len(real), len(real) >= 2)
chk('D2 000811 成本/数量一字未动',
    '000811' in realmap and abs(realmap['000811'][2] - 37.571) < 1e-9 and realmap['000811'][3] == 4300,
    str(realmap.get('000811')))
chk('D3 002838 成本/数量一字未动',
    '002838' in realmap and abs(realmap['002838'][2] - 25.823) < 1e-9 and realmap['002838'][3] == 8500,
    str(realmap.get('002838')))
chk('D4 其余自选股入表时无成本（None）',
    all(realmap[c][2] is None and realmap[c][3] is None
        for c in realmap if c not in ('000811', '002838')))
w2 = w._watchlist_items()
chk('D5 自选数量未变（仍 %d 只）' % len(watch), len(w2) == len(watch))

npass = sum(1 for ok, _, _ in RES if ok)
nfail = len(RES) - npass
lines = ['分时做T「从自选添加」验证  %s' % ('PASS %d / FAIL %d' % (npass, nfail))]
for ok, name, extra in RES:
    lines.append('[%s] %s %s' % ('PASS' if ok else 'FAIL', name, extra))
open(LOG, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\n==== %s ====' % lines[0], flush=True)
sys.exit(1 if nfail else 0)
