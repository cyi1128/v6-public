# -*- coding: utf-8 -*-
"""一次性补丁【勿重跑】：
1) 删除标题栏「➕ 添加个股」按钮 + 只服务它的死代码链（弹窗/自选读取/加库/取名）
2) 保留增删能力：分时做T表右键菜单（补成本数量 / 从做T列表移除 / 刷新）
3) 修 _short_action 对机构引擎文案的 6 字硬切（「不做T，等条件恢复」→ 完整短标签）
4) 列宽按真实文本宽度自适应（_fit_hold_columns），把剩余宽度留给「操作建议」
5) 动能/风控/信号灯/操作建议 四列挂 tooltip（完整原文）
"""
import os
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = P + '.bak_before_uifix'
src0 = open(P, newline='', encoding='utf-8').read()
if not os.path.exists(BAK):
    open(BAK, 'w', newline='', encoding='utf-8').write(src0)
    print('已备份 ->', BAK)
s = src0.replace('\r\n', '\n')
print('补丁前 行数 %d | 裸LF %d' % (s.count('\n') + 1, src0.count('\n') - src0.count('\r\n')))


def cut(a, b, keep_b=True, label=''):
    """删除 [a, b) 之间的内容（keep_b=True 时保留 b 锚点，且不重复它）"""
    global s
    ia, ib = s.index(a), s.index(b)
    assert ia < ib, label
    removed = s[ia:ib]
    s = s[:ia] + (s[ib:] if keep_b else s[ib + len(b):])
    print('  删 %-22s %5d 字符' % (label, len(removed)))


# ---------- 1) 导入 ----------
s = s.replace('    QInputDialog,\n)', '    QInputDialog, QMenu,\n)')
s = s.replace('from PyQt6.QtGui import QColor, QBrush',
              'from PyQt6.QtGui import QColor, QBrush, QFontMetrics')

# ---------- 2) 删按钮 ----------
cut('        # 「添加个股」按钮：分时做T Tab 专用入口（写入 holding 表 = 做T列表数据源）',
    '        self._tab_group.idClicked.connect(self._switch_tab)',
    label='标题栏按钮')

# ---------- 3) _switch_tab 里的引用 ----------
cut("        if hasattr(self, '_btn_add'):\n            self._btn_add.setVisible(idx == 0)\n",
    '        if idx == 0:', label='switch_tab 引用')

# ---------- 4~6) 删死代码链 ----------
cut('    def _resolve_stock_name(self, code):', '    def _remove_holding(self, code):', label='_resolve_stock_name')
cut('    def _watchlist_items(self):', '    def _update_cost_qty(self, code, cost=None, qty=None):',
    label='_watchlist_items+_add_watch_codes')
cut('    def _build_holding_dialog(self):',
    '    # ============================================================\n    # 导出日K建仓股票代码', label='弹窗+入口')

# ---------- 7) 段落标题 ----------
s = s.replace('    # 持仓管理（添加 / 移除做T个股 → holding 表）',
              '    # 持仓管理（分时做T表右键：补成本数量 / 从做T列表移除 → holding 表）')

# ---------- 8) _short_action ----------
old_act = """        if not act:
            return '观望'
"""
new_act = """        if not act:
            return '观望'
        # 机构级引擎（strategy/intraday_t_engine）的完整文案：给语义完整的短标签。
        # 这些必须放在下面的关键词猜测之前，否则「反弹卖出」会被误判成「高抛」、
        # 未命中的会被 act[:6] 硬切成「不做T，等条」。
        if '不做T' in act:
            return '不做T·等条件'
        if '先卖后买' in act:
            return '反T·先卖后买'
        if '先买后卖' in act:
            return '正T·先买后卖'
        if '接近条件' in act:
            return '等VWAP量价'
"""
# 只改 _short_action 函数体（同一段文字在别的 helper 里也出现过，必须切片定位）
_f0 = s.index('    def _short_action(act):')
_f1 = s.index('    # ============================================================\n    # 闪烁', _f0)
_body = s[_f0:_f1]
assert _body.count(old_act) == 1, _body.count(old_act)
assert _body.count('        return act[:6]') == 1
_body = _body.replace(old_act, new_act).replace(
    '        return act[:6]', '        return act[:8]   # 兜底：放宽到 8 字（原来 6 字，容易切断词）')
s = s[:_f0] + _body + s[_f1:]
print('  _short_action 已补 4 条引擎文案映射 + 兜底放宽到 8 字')

# ---------- 9) 列宽自适应 ----------
old_w = """        widths_h = [84, 65, 62, 74, 72, 72, 96, 104, 104, 120, 78]
        for i, w in enumerate(widths_h):
            self.table.setColumnWidth(i, w)"""
new_w = """        # 列宽不写死：创建时给最小可用宽，每次渲染由 _fit_hold_columns() 按
        # 「表头 + 实际文字」的像素宽度收紧/放宽（上下限见 _HOLD_MINW / _HOLD_MAXW），
        # 剩余宽度全部交给「操作建议」列（它是 Stretch）。
        for _i, _w in enumerate(self._HOLD_MINW.get(i, 60) for i in range(11)):
            self.table.setColumnWidth(_i, _w)"""
assert s.count(old_w) == 1
s = s.replace(old_w, new_w)

old_click = """        self.table.cellClicked.connect(self._on_hold_cell_clicked)"""
new_click = """        self.table.cellClicked.connect(self._on_hold_cell_clicked)
        # 右键菜单：补成本/数量、从做T列表移除、刷新。
        # （原来的「➕ 添加个股」按钮已按用户要求删除，功能移到右键，标题栏不再堆按钮）
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_hold_context_menu)"""
assert s.count(old_click) == 1
s = s.replace(old_click, new_click)

# ---------- 10) tooltip ----------
r1 = """            set_table_item(self.table, i, COL_H_MOM, mom_short, mom_color, align=left)"""
n1 = """            _mit = set_table_item(self.table, i, COL_H_MOM, mom_short, mom_color, align=left)
            _mit.setToolTip(mom or mom_short)"""
assert s.count(r1) == 1
s = s.replace(r1, n1)

r2 = """            set_table_item(self.table, i, COL_H_RISK, risk_short, risk_color,
                           bold=True, align=left)"""
n2 = """            _rit = set_table_item(self.table, i, COL_H_RISK, risk_short, risk_color,
                                  bold=True, align=left)
            _rit.setToolTip(r.get('risk_status') or risk_short)"""
assert s.count(r2) == 1
s = s.replace(r2, n2)

r3 = """            self.table.setItem(i, COL_H_SIG, sig_item)"""
n3 = """            _sig_tip = r['signal_text']
            if r.get('t_score'):
                _sig_tip += ' ｜ 强度 %s 分（%s轨）' % (r['t_score'], r.get('t_side') or '')
            if r.get('t_window'):
                _sig_tip += ' ｜ 时段 %s' % r['t_window']
            sig_item.setToolTip(_sig_tip)
            self.table.setItem(i, COL_H_SIG, sig_item)"""
assert s.count(r3) == 1
s = s.replace(r3, n3)

r4 = """            set_table_item(self.table, i, COL_H_ACT, act_short, act_color, bold=True, align=left)"""
n4 = """            _ait = set_table_item(self.table, i, COL_H_ACT, act_short, act_color,
                                  bold=True, align=left)
            _act_tip = r.get('action') or act_short
            if r.get('t_plan'):
                _act_tip += '\\n' + str(r['t_plan'])
            if r.get('est_cost_after'):
                _act_tip += '\\n预估成本 → %s（%+.3f%%）' % (
                    r['est_cost_after'], r.get('est_cost_delta_pct') or 0.0)
            _ait.setToolTip(_act_tip)"""
assert s.count(r4) == 1
s = s.replace(r4, n4)

# ---------- 11) 渲染末尾调用列宽自适应 + 新方法 ----------
tail = """            # 触发行背景
            if row_bg:
                for col in range(11):
                    it = self.table.item(i, col)
                    if it is not None:
                        it.setBackground(QBrush(row_bg))


    @staticmethod
    def _short_momentum(mom):"""
new_tail = """            # 触发行背景
            if row_bg:
                for col in range(11):
                    it = self.table.item(i, col)
                    if it is not None:
                        it.setBackground(QBrush(row_bg))

        # 行填完后按真实文字宽度定列宽（剩余宽度给「操作建议」）
        self._fit_hold_columns()

    # 列宽：下限保证不缺字，上限防某一列吃掉整表
    _HOLD_PAD = 14          # 单元格左右留白（含加粗字的额外宽度）
    _HOLD_MINW = {COL_H_NAME: 64, COL_H_CODE: 58, COL_H_PRICE: 56, COL_H_PCT: 58,
                  COL_H_BUY: 78, COL_H_SELL: 78, COL_H_MOM: 64, COL_H_RISK: 64,
                  COL_H_SIG: 84, COL_H_CTRL: 56}
    _HOLD_MAXW = {COL_H_NAME: 110, COL_H_CODE: 84, COL_H_PRICE: 84, COL_H_PCT: 90,
                  COL_H_BUY: 96, COL_H_SELL: 96, COL_H_MOM: 132, COL_H_RISK: 110,
                  COL_H_SIG: 150, COL_H_CTRL: 100}

    def _fit_hold_columns(self):
        \"\"\"按「表头 + 每行实际文字」的像素宽度定列宽；「操作建议」列保持 Stretch 吃剩余宽度。
        这样窗口再窄也不会把文字切掉（模型：内容需要多少就给多少，剩下的全给操作建议）。\"\"\"
        t = self.table
        n = t.columnCount()
        for c in range(n):
            if c == COL_H_ACT:
                continue
            w = self._HOLD_MINW.get(c, 60)
            if c < len(HEADER_HOLD):
                w = max(w, QFontMetrics(t.font()).horizontalAdvance(HEADER_HOLD[c]) + self._HOLD_PAD)
            for r in range(t.rowCount()):
                it = t.item(r, c)
                if it is None or not it.text():
                    continue
                w = max(w, QFontMetrics(it.font()).horizontalAdvance(it.text()) + self._HOLD_PAD)
            t.setColumnWidth(c, int(min(w, self._HOLD_MAXW.get(c, 120))))

    def _on_hold_context_menu(self, pos):
        \"\"\"分时做T表右键：补成本/数量、从做T列表移除、刷新。\"\"\"
        it = self.table.itemAt(pos)
        if it is None:
            return
        row = it.row()
        if row < 0 or row >= len(self._hold_rows):
            return
        r = self._hold_rows[row]
        code = str(r.get('code') or '')
        name = str(r.get('name') or '')
        menu = QMenu(self)
        act_edit = menu.addAction('✎ 补成本/数量（%s %s）' % (code, name))
        act_del = menu.addAction('🗑 从做T列表移除（%s %s）' % (code, name))
        menu.addSeparator()
        act_ref = menu.addAction('↻ 刷新')
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self._edit_holding_cost(code, r)
        elif chosen is act_del:
            if QMessageBox.question(
                    self, '确认移除',
                    '从分时做T列表移除 %s %s？\\n（只从做T列表删除，不影响「我的自选」）'
                    % (code, name)) != QMessageBox.StandardButton.Yes:
                return
            try:
                self._remove_holding(code)
            except Exception as e:
                QMessageBox.critical(self, '删除失败', '%s: %s' % (type(e).__name__, e))
                return
            self.set_status('已从做T列表移除 %s' % code)
            self.refresh()
        elif chosen is act_ref:
            self.refresh()

    def _edit_holding_cost(self, code, row=None):
        \"\"\"补/改成本与数量（两次输入，留空不改；只更新这两列，不动买入时间）。\"\"\"
        cur = row or {}
        _c = ('%.3f' % cur['cost']) if cur.get('cost') else '—'
        _q = str(int(cur['qty'])) if cur.get('qty') else '—'
        s1, ok1 = QInputDialog.getText(
            self, '补成本/数量', '%s 持仓成本（当前 %s，留空不改）：' % (code, _c))
        if not ok1:
            return
        s2, ok2 = QInputDialog.getText(
            self, '补成本/数量', '%s 持仓数量（当前 %s，留空不改）：' % (code, _q))
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
            QMessageBox.warning(self, '格式错误', '成本填大于 0 的数字；数量填大于 0 的整数。')
            return
        if cost is None and qty is None:
            return
        try:
            self._update_cost_qty(code, cost, qty)
        except Exception as e:
            QMessageBox.critical(self, '写入失败', '%s: %s' % (type(e).__name__, e))
            return
        self.set_status('已更新 %s 的成本/数量' % code)
        self.refresh()

    @staticmethod
    def _short_momentum(mom):"""
assert s.count(tail) == 1
s = s.replace(tail, new_tail)

out = s.replace('\n', '\r\n')
compile(out, P, 'exec')                      # 先编译校验，通过后再落盘
assert out.count('\n') - out.count('\r\n') == 0, '出现裸 LF'
# 残留/新增自检
for k in ('_btn_add', '_build_holding_dialog', '_watchlist_items', '_add_watch_codes',
          '_resolve_stock_name', '_open_holding_manager'):
    assert out.count(k) == 0, '残留 ' + k
for k, want in (('_fit_hold_columns', 2), ('_on_hold_context_menu', 2),
                ('_edit_holding_cost', 2), ('_update_cost_qty', 2),
                ('_remove_holding', 2), ('act[:8]', 1), ('反T·先卖后买', 1),
                ('CustomContextMenu', 1), ('QMenu,', 1)):
    assert out.count(k) >= want, '缺 ' + k
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
print('\n补丁后 行数 %d | CRLF %d | 裸LF %d | 编译 OK' % (
    chk.count('\r\n') + 1, chk.count('\r\n'), chk.count('\n') - chk.count('\r\n')))
for k in ('_btn_add', '_build_holding_dialog', '_watchlist_items', '_add_watch_codes',
          '_resolve_stock_name', '_open_holding_manager'):
    print('  残留 %-24s %d' % (k, chk.count(k)))
for k in ('_fit_hold_columns', '_on_hold_context_menu', '_edit_holding_cost',
          '_update_cost_qty', '_remove_holding'):
    print('  新增 %-24s %d' % (k, chk.count(k)))
