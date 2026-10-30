# -*- coding: utf-8 -*-
"""一次性补丁：分时做T 的添加入口改成「从我的自选一键加入」。【勿重跑】

- 标题栏按钮 tooltip 更新
- 导入补 QInputDialog
- 新增 _watchlist_items / _add_watch_codes / _update_cost_qty
- 重写 _build_holding_dialog：左=我的自选(多选)、右=已在做T列表；已存在代码跳过（不覆盖成本）
"""
import os
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = P + '.bak_before_picker'
src = open(P, newline='', encoding='utf-8').read()
if not os.path.exists(BAK):
    open(BAK, 'w', newline='', encoding='utf-8').write(src)
    print('已备份 ->', BAK)
print('补丁前 行数 %d | CRLF %d | 裸LF %d' % (
    src.count('\r\n') + 1, src.count('\r\n'), src.count('\n') - src.count('\r\n')))

# ---------- 1) 导入 ----------
old_imp = 'QHeaderView, QCheckBox, QDialog, QLineEdit, QFormLayout, QTableWidget,'
assert src.count(old_imp) == 1, '导入锚点不唯一'
src = src.replace(old_imp, 'QHeaderView, QCheckBox, QDialog, QLineEdit, QFormLayout, QTableWidget,\n'
                            '    QInputDialog,')

# 上面用了 \n，先统一再转 CRLF
src = src.replace('\r\n', '\n')

# ---------- 2) tooltip ----------
old_tip = "self._btn_add.setToolTip('添加做T个股（代码/成本/数量）到分时做T列表；也可在弹窗里移除')"
assert src.count(old_tip) == 1, 'tooltip 锚点不唯一'
src = src.replace(old_tip,
    "self._btn_add.setToolTip('从「我的自选」勾选加入分时做T列表（可一键全同步）；也能移除、补成本')")

# ---------- 3) 替换弹窗区 ----------
A = '    def _build_holding_dialog(self):'
B = '    def _open_holding_manager(self):'
ia, ib = src.index(A), src.index(B)
assert ia < ib, '顺序异常'
NEW = '''    # ---------- 自选 → 做T列表 ----------
    def _watchlist_items(self):
        """我的自选：[(code, name)]，去重且只保留 6 位数字代码。"""
        try:
            from core.watchlist import get_watchlist_manager
            out, seen = [], set()
            for s in (get_watchlist_manager().stocks or []):
                c = str((s or {}).get('code') or '').strip()
                if len(c) == 6 and c.isdigit() and c not in seen:
                    seen.add(c)
                    out.append((c, str((s or {}).get('name') or c)))
            return out
        except Exception as e:
            print('[ATR做T] 读自选失败: %s' % e, flush=True)
            return []

    def _add_watch_codes(self, items):
        """把自选 (code, name) 批量加入做T列表，成本/数量留空。
        已在列表里的代码一律跳过 —— 绝不覆盖已有成本。返回 (新增数, 跳过数, 提示)。"""
        import duckdb
        have = {r['code'] for r in (self._holding_db_rows or [])}
        todo, skipped = [], 0
        for c, n in items:
            if c in have:
                skipped += 1
                continue
            have.add(c)
            todo.append((c, n))
        if not todo:
            self._refresh_holding_db()
            return 0, skipped, '选中的股票都已在做T列表里，没有新增'
        con = duckdb.connect(self._track_db_path)
        try:
            for c, n in todo:
                nm = n if (n and n != c) else self._resolve_stock_name(c)
                con.execute('DELETE FROM holding WHERE code = ?', [c])
                con.execute(
                    'INSERT INTO holding(code,name,cost,qty,buy_time,updated_at) '
                    'VALUES (?,?,?,?,?,?)', [c, nm, None, None, None, datetime.now()])
        finally:
            con.close()
        self._refresh_holding_db()
        tip = '已从自选加入 %d 只' % len(todo)
        if skipped:
            tip += '；%d 只已存在被跳过（原有成本/数量未动）' % skipped
        return len(todo), skipped, tip

    def _update_cost_qty(self, code, cost=None, qty=None):
        """只更新成本/数量，不动名称与买入时间。"""
        import duckdb
        con = duckdb.connect(self._track_db_path)
        try:
            if cost is not None:
                con.execute('UPDATE holding SET cost = ?, updated_at = ? WHERE code = ?',
                            [float(cost), datetime.now(), code])
            if qty is not None:
                con.execute('UPDATE holding SET qty = ?, updated_at = ? WHERE code = ?',
                            [int(qty), datetime.now(), code])
        finally:
            con.close()
        self._refresh_holding_db()

    def _build_holding_dialog(self):
        """「从我的自选添加」弹窗：左=自选(多选)、右=已在做T列表。"""
        dlg = QDialog(self)
        dlg.setWindowTitle('分时做T · 从我的自选添加')
        dlg.resize(800, 470)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        tip = QLabel('左边勾选自选股票 → 点「添加选中」即进入分时做T列表，'
                     '不用填成本（引擎按中性处理并提示补成本）。'
                     '已在列表里的股票会自动跳过，原有成本不会被清掉。')
        tip.setWordWrap(True)
        tip.setStyleSheet('color:#6B7280;font-size:11px;')
        root.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(10)

        # ---------- 左：我的自选 ----------
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel('我的自选（Ctrl/Shift 多选）'))
        lst_watch = QTableWidget(dlg)
        lst_watch.setObjectName('lst_watch')
        lst_watch.setColumnCount(2)
        lst_watch.setHorizontalHeaderLabels(['代码', '名称'])
        lst_watch.verticalHeader().setVisible(False)
        lst_watch.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lst_watch.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        lst_watch.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lst_watch.horizontalHeader().setStretchLastSection(True)
        lst_watch.setColumnWidth(0, 80)
        left.addWidget(lst_watch, 1)
        bar_l = QHBoxLayout()
        bar_l.setSpacing(6)
        btn_all = QPushButton('全选')
        btn_all.setObjectName('btn_all')
        btn_none = QPushButton('清空选择')
        btn_none.setObjectName('btn_none')
        btn_reload = QPushButton('🔄 刷新自选')
        btn_reload.setObjectName('btn_reload')
        for _b in (btn_all, btn_none, btn_reload):
            _b.setStyleSheet(self._tab_style_normal)
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar_l.addWidget(_b)
        bar_l.addStretch(1)
        left.addLayout(bar_l)
        body.addLayout(left, 1)

        # ---------- 中：动作 ----------
        mid = QVBoxLayout()
        mid.addStretch(1)
        btn_add_sel = QPushButton('添加选中 →')
        btn_add_sel.setObjectName('btn_add_sel')
        btn_add_sel.setStyleSheet(
            'QPushButton{background:#2f6bff;color:#ffffff;border:1px solid #2f6bff;'
            'border-radius:4px;padding:6px 12px;font-size:12px;font-weight:bold;}'
            'QPushButton:hover{background:#1f5ae0;}')
        btn_add_all = QPushButton('全部同步 →')
        btn_add_all.setObjectName('btn_add_all')
        for _b in (btn_add_sel, btn_add_all):
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_all.setStyleSheet(self._tab_style_normal)
        mid.addWidget(btn_add_sel)
        mid.addWidget(btn_add_all)
        mid.addStretch(1)
        body.addLayout(mid)

        # ---------- 右：已在做T列表 ----------
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(QLabel('已在分时做T'))
        lst_hold = QTableWidget(dlg)
        lst_hold.setObjectName('lst_holdings')
        lst_hold.setColumnCount(4)
        lst_hold.setHorizontalHeaderLabels(['代码', '名称', '成本', '数量'])
        lst_hold.verticalHeader().setVisible(False)
        lst_hold.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lst_hold.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        lst_hold.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lst_hold.horizontalHeader().setStretchLastSection(True)
        for _i, _w in enumerate([80, 110, 80]):
            lst_hold.setColumnWidth(_i, _w)
        right.addWidget(lst_hold, 1)
        bar_r = QHBoxLayout()
        bar_r.setSpacing(6)
        btn_edit = QPushButton('✎ 补成本/数量')
        btn_edit.setObjectName('btn_edit')
        btn_del = QPushButton('🗑 移除选中')
        btn_del.setObjectName('btn_del')
        for _b in (btn_edit, btn_del):
            _b.setStyleSheet(self._tab_style_normal)
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar_r.addWidget(_b)
        bar_r.addStretch(1)
        right.addLayout(bar_r)
        body.addLayout(right, 1)

        root.addLayout(body, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton('关闭')
        btn_close.setStyleSheet(self._tab_style_normal)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        # ---------- 行为 ----------
        def _fill_watch():
            self._watch_items = self._watchlist_items()
            lst_watch.setRowCount(len(self._watch_items))
            for _i, (_c, _n) in enumerate(self._watch_items):
                for _j, _v in enumerate((_c, _n)):
                    _it = QTableWidgetItem(_v)
                    _it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    lst_watch.setItem(_i, _j, _it)
            return self._watch_items

        def _reload_hold():
            self._refresh_holding_db()
            rs = self._holding_db_rows or []
            lst_hold.setRowCount(len(rs))
            for _r, _row in enumerate(rs):
                vals = [
                    str(_row.get('code') or ''),
                    str(_row.get('name') or ''),
                    ('%.3f' % float(_row['cost'])) if _row.get('cost') else '—',
                    str(int(_row['qty'])) if _row.get('qty') else '—',
                ]
                for _c, _v in enumerate(vals):
                    _it = QTableWidgetItem(_v)
                    _it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    lst_hold.setItem(_r, _c, _it)

        def _selected_watch():
            out = []
            for _r in sorted({i.row() for i in lst_watch.selectedIndexes()}):
                _c = lst_watch.item(_r, 0)
                if _c is None:
                    continue
                _n = lst_watch.item(_r, 1)
                out.append((_c.text(), _n.text() if _n else _c.text()))
            return out

        def _add_items(items, what):
            try:
                n, _sk, msg = self._add_watch_codes(items)
            except Exception as _e:
                QMessageBox.critical(
                    dlg, '写入失败',
                    'DuckDB 写入失败：%s: %s\\n（主程序占用数据库时请稍后重试）'
                    % (type(_e).__name__, _e))
                return
            self.set_status(msg)
            _reload_hold()
            if n:
                self.refresh()
            else:
                QMessageBox.information(dlg, '提示', '%s：%s' % (what, msg))

        def _do_add_sel():
            sel = _selected_watch()
            if not sel:
                QMessageBox.information(
                    dlg, '提示', '先在左边选中要加入的股票（Ctrl/Shift 多选，或点「全选」）。')
                return
            _add_items(sel, '添加选中')

        def _do_add_all():
            items = _fill_watch()
            if not items:
                QMessageBox.information(dlg, '提示', '自选列表是空的，先在主程序里加自选。')
                return
            _add_items(items, '全部同步')

        def _do_del():
            rows = sorted({i.row() for i in lst_hold.selectedIndexes()})
            codes = [lst_hold.item(_r, 0).text() for _r in rows if lst_hold.item(_r, 0)]
            if not codes:
                QMessageBox.information(dlg, '提示', '先在右边选中要移除的行。')
                return
            if QMessageBox.question(
                    dlg, '确认移除',
                    '从分时做T列表移除 %d 只？\\n%s' % (len(codes), '、'.join(codes))
            ) != QMessageBox.StandardButton.Yes:
                return
            try:
                for _c in codes:
                    self._remove_holding(_c)
            except Exception as _e:
                QMessageBox.critical(dlg, '删除失败', '%s: %s' % (type(_e).__name__, _e))
                return
            self.set_status('已移除 %d 只' % len(codes))
            _reload_hold()
            self.refresh()

        def _do_edit():
            rows = sorted({i.row() for i in lst_hold.selectedIndexes()})
            if len(rows) != 1:
                QMessageBox.information(dlg, '提示', '先在右边选中一行，再补成本/数量。')
                return
            _r = rows[0]
            _c = lst_hold.item(_r, 0).text() if lst_hold.item(_r, 0) else ''
            if not _c:
                return
            _cur_c = lst_hold.item(_r, 2).text() if lst_hold.item(_r, 2) else '—'
            _cur_q = lst_hold.item(_r, 3).text() if lst_hold.item(_r, 3) else '—'
            s1, ok1 = QInputDialog.getText(
                dlg, '补成本/数量', '%s 持仓成本（当前 %s，留空不改）：' % (_c, _cur_c))
            if not ok1:
                return
            s2, ok2 = QInputDialog.getText(
                dlg, '补成本/数量', '%s 持仓数量（当前 %s，留空不改）：' % (_c, _cur_q))
            if not ok2:
                return
            cost = qty = None
            try:
                if (s1 or '').strip():
                    cost = float(s1.strip())
                    if cost <= 0:
                        raise ValueError
                if (s2 or '').strip():
                    qty = int(float(s2.strip()))
                    if qty <= 0:
                        raise ValueError
            except ValueError:
                QMessageBox.warning(dlg, '格式错误', '成本填大于 0 的数字；数量填大于 0 的整数。')
                return
            if cost is None and qty is None:
                return
            try:
                self._update_cost_qty(_c, cost, qty)
            except Exception as _e:
                QMessageBox.critical(dlg, '写入失败', '%s: %s' % (type(_e).__name__, _e))
                return
            self.set_status('已更新 %s 的成本/数量' % _c)
            _reload_hold()
            self.refresh()

        btn_all.clicked.connect(lambda: lst_watch.selectAll())
        btn_none.clicked.connect(lst_watch.clearSelection)
        btn_reload.clicked.connect(_fill_watch)
        btn_add_sel.clicked.connect(_do_add_sel)
        btn_add_all.clicked.connect(_do_add_all)
        btn_del.clicked.connect(_do_del)
        btn_edit.clicked.connect(_do_edit)
        btn_close.clicked.connect(dlg.accept)

        _fill_watch()
        _reload_hold()
        return dlg

'''
src = src[:ia] + NEW + src[ib:]
src = src.replace('\n', '\r\n')
open(P, 'w', newline='', encoding='utf-8').write(src)

chk = open(P, newline='', encoding='utf-8').read()
naked = chk.count('\n') - chk.count('\r\n')
print('补丁后 行数 %d | CRLF %d | 裸LF %d' % (chk.count('\r\n') + 1, chk.count('\r\n'), naked))
compile(chk, P, 'exec')
print('编译 OK')
print('关键点：_watchlist_items %d | _add_watch_codes %d | _update_cost_qty %d | 新弹窗 %d | 残留旧表单 ed_code %d' % (
    chk.count('def _watchlist_items'), chk.count('def _add_watch_codes'), chk.count('def _update_cost_qty'),
    chk.count('def _build_holding_dialog'), chk.count("setObjectName('ed_code')")))
if naked:
    print('!! 行尾被破坏')
    sys.exit(1)
