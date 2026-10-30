# -*- coding: utf-8 -*-
"""一次性补丁：分时做T 加「➕ 添加个股」按钮 + 持仓管理弹窗（新增/移除）。【勿重跑】

改动 4 处：
  1) 导入补 QDialog / QLineEdit / QFormLayout / QTableWidget
  2) 标题栏加「➕ 添加个股」按钮（分时做T Tab 可见，日K建仓 Tab 隐藏）
  3) _switch_tab 同步按钮可见性
  4) 新增 _resolve_stock_name / _parse_buy_time / _save_holding / _remove_holding /
     _build_holding_dialog / _open_holding_manager 六个方法
"""
import os
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = P + '.bak_before_holdui'

src = open(P, newline='', encoding='utf-8').read()
if not os.path.exists(BAK):
    open(BAK, 'w', newline='', encoding='utf-8').write(src)
    print('已备份 ->', BAK)
lines = src.split('\r\n')
print('补丁前：行数 %d，CRLF %d，裸LF %d' % (len(lines), src.count('\r\n'), src.count('\n') - src.count('\r\n')))


def idx_of(marker, expect=1):
    hits = [i for i, l in enumerate(lines) if marker in l]
    assert len(hits) == expect, '锚点 %r 命中 %d 次（预期 %d）' % (marker, len(hits), expect)
    return hits[0]


def add_lines(text):
    return text.split('\n')


# ---------- 1) 导入 ----------
i = idx_of('    QHeaderView, QCheckBox,')
lines[i] = lines[i].replace(
    'QHeaderView, QCheckBox,',
    'QHeaderView, QCheckBox, QDialog, QLineEdit, QFormLayout, QTableWidget,')

# ---------- 2) 按钮 ----------
i = idx_of('self._btn_export.setVisible(False)')
lines[i + 1:i + 1] = add_lines(
    '''        # 「添加个股」按钮：分时做T Tab 专用入口（写入 holding 表 = 做T列表数据源）
        self._btn_add = QPushButton('➕ 添加个股')
        self._btn_add.setStyleSheet(self._tab_style_normal)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.setToolTip('添加做T个股（代码/成本/数量）到分时做T列表；也可在弹窗里移除')
        self._btn_add.clicked.connect(self._open_holding_manager)
        title_bar_layout.insertWidget(3, self._btn_add)
''')

# ---------- 3) Tab 切换时同步可见性 ----------
i = idx_of('self._btn_export.setVisible(idx == 1)')
lines[i + 1:i + 1] = add_lines(
    '''        if hasattr(self, '_btn_add'):
            self._btn_add.setVisible(idx == 0)
''')

# ---------- 4) 新增方法 ----------
i = idx_of('# 导出日K建仓股票代码（供同花顺批量导入自选股）')
i -= 1                                     # 移到注释块上一行
METHODS = '''
    # ============================================================
    # 持仓管理（添加 / 移除做T个股 → holding 表）
    # ============================================================
    def _resolve_stock_name(self, code):
        """从实时行情取股票名称；失败退回代码本身。"""
        try:
            from utils.http_market_data import get_realtime_quotes_http
            d = (get_realtime_quotes_http([code]) or {}).get(code) or {}
            return d.get('name') or code
        except Exception:
            return code

    def _parse_buy_time(self, s):
        """'YYYY-MM-DD[ HH:MM:SS]' -> datetime；空串返回 None；格式错抛 ValueError。"""
        s = (s or '').strip()
        if not s:
            return None
        s = s.replace('/', '-')
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValueError('买入时间格式应为 2026-10-08 或 2026-10-08 10:30:00')

    def _save_holding(self, code, cost, qty, buy_time_str=''):
        """写入/覆盖 holding 表（同一代码覆盖）。返回 (ok, 消息)。"""
        import duckdb
        bt = self._parse_buy_time(buy_time_str)
        name = self._resolve_stock_name(code)
        con = duckdb.connect(self._track_db_path)
        try:
            con.execute('DELETE FROM holding WHERE code = ?', [code])
            con.execute(
                'INSERT INTO holding(code,name,cost,qty,buy_time,updated_at) '
                'VALUES (?,?,?,?,?,?)',
                [code, name, float(cost), int(qty), bt, datetime.now()])
        finally:
            con.close()
        self._refresh_holding_db()
        tip = '' if bt else '（未填买入时间 → 引擎按「全部可用」处理）'
        return True, '已添加 %s %s：成本 %.3f × %d 股%s' % (code, name, float(cost), int(qty), tip)

    def _remove_holding(self, code):
        """从 holding 表删除一个代码。"""
        import duckdb
        con = duckdb.connect(self._track_db_path)
        try:
            con.execute('DELETE FROM holding WHERE code = ?', [code])
        finally:
            con.close()
        self._refresh_holding_db()

    def _build_holding_dialog(self):
        """构建「分时做T · 添加/移除个股」弹窗（返回 dialog，便于测试时不 exec）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle('分时做T · 添加/移除个股')
        dlg.resize(620, 450)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        tip = QLabel('这里的股票就是分时做T列表的数据源。买入时间可留空（按「全部可用」处理）；'
                     '若是今天买的，请填成交时间，否则反T 会卖出当日买入股（T+1 违规）。')
        tip.setWordWrap(True)
        tip.setStyleSheet('color:#6B7280;font-size:11px;')
        root.addWidget(tip)

        lst = QTableWidget(dlg)
        lst.setObjectName('lst_holdings')
        lst.setColumnCount(5)
        lst.setHorizontalHeaderLabels(['代码', '名称', '成本', '数量', '买入时间'])
        lst.verticalHeader().setVisible(False)
        lst.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lst.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lst.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        _lh = lst.horizontalHeader()
        _lh.setStretchLastSection(True)
        for _i, _w in enumerate([80, 100, 90, 90]):
            lst.setColumnWidth(_i, _w)
        root.addWidget(lst, 1)

        def _reload():
            self._refresh_holding_db()
            rs = self._holding_db_rows or []
            lst.setRowCount(len(rs))
            for _r, _row in enumerate(rs):
                vals = [
                    str(_row.get('code') or ''),
                    str(_row.get('name') or ''),
                    ('%.3f' % float(_row['cost'])) if _row.get('cost') is not None else '-',
                    str(int(_row['qty'])) if _row.get('qty') else '-',
                    str(_row.get('buy_time') or '-'),
                ]
                for _c, _v in enumerate(vals):
                    _it = QTableWidgetItem(_v)
                    _it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    lst.setItem(_r, _c, _it)

        bar = QHBoxLayout()
        btn_del = QPushButton('🗑 移除选中')
        btn_del.setObjectName('btn_del')
        btn_del.setStyleSheet(self._tab_style_normal)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close = QPushButton('关闭')
        btn_close.setStyleSheet(self._tab_style_normal)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        bar.addWidget(btn_close)
        root.addLayout(bar)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        ed_code = QLineEdit(dlg)
        ed_code.setObjectName('ed_code')
        ed_code.setPlaceholderText('6 位代码，如 002838')
        ed_cost = QLineEdit(dlg)
        ed_cost.setObjectName('ed_cost')
        ed_cost.setPlaceholderText('持仓成本，如 25.823')
        ed_qty = QLineEdit(dlg)
        ed_qty.setObjectName('ed_qty')
        ed_qty.setPlaceholderText('数量（股），如 8500')
        ed_bt = QLineEdit(dlg)
        ed_bt.setObjectName('ed_bt')
        ed_bt.setPlaceholderText('可留空；2026-10-08 或 2026-10-08 10:30:00')
        form.addRow('股票代码', ed_code)
        form.addRow('持仓成本', ed_cost)
        form.addRow('持仓数量', ed_qty)
        form.addRow('买入时间', ed_bt)
        root.addLayout(form)

        btn_add = QPushButton('➕ 添加到分时做T')
        btn_add.setObjectName('btn_add')
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            'QPushButton{background:#2f6bff;color:#ffffff;border:1px solid #2f6bff;'
            'border-radius:4px;padding:5px 14px;font-size:12px;font-weight:bold;}'
            'QPushButton:hover{background:#1f5ae0;}')
        root.addWidget(btn_add)

        def _do_add():
            code = (ed_code.text() or '').strip()
            if len(code) != 6 or not code.isdigit():
                QMessageBox.warning(dlg, '格式错误', '股票代码必须是 6 位数字，例如 002838。')
                return
            try:
                cost = float((ed_cost.text() or '').strip())
                if cost <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(dlg, '格式错误', '持仓成本必须是大于 0 的数字，例如 25.823。')
                return
            try:
                qty = int(float((ed_qty.text() or '').strip()))
                if qty <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(dlg, '格式错误', '持仓数量必须是大于 0 的整数，例如 8500。')
                return
            bts = (ed_bt.text() or '').strip()
            try:
                self._parse_buy_time(bts)
            except ValueError as _e:
                QMessageBox.warning(dlg, '格式错误', str(_e))
                return
            if code[:2] not in ('60', '00', '30', '68'):
                if QMessageBox.question(
                        dlg, '确认',
                        '代码前缀 %s 不是常见的主板/创业板/科创板，仍要添加？' % code[:2]
                ) != QMessageBox.StandardButton.Yes:
                    return
            if qty % 100 != 0:
                QMessageBox.information(dlg, '提示', '数量 %d 不是 100 的整数倍（零股），已按实际数量记录。' % qty)
            try:
                _ok, msg = self._save_holding(code, cost, qty, bts)
            except Exception as _e:
                QMessageBox.critical(
                    dlg, '写入失败',
                    'DuckDB 写入失败：%s: %s\\n（主程序占用数据库时请稍后重试）'
                    % (type(_e).__name__, _e))
                return
            self.set_status(msg)
            _reload()
            ed_code.clear()
            ed_cost.clear()
            ed_qty.clear()
            ed_bt.clear()
            self.refresh()

        def _do_del():
            _i = lst.currentRow()
            if _i < 0:
                QMessageBox.information(dlg, '提示', '请先在上面的列表里选中一行。')
                return
            _c = lst.item(_i, 0).text() if lst.item(_i, 0) else ''
            if not _c:
                return
            if QMessageBox.question(
                    dlg, '确认移除',
                    '从分时做T列表移除 %s？' % _c) != QMessageBox.StandardButton.Yes:
                return
            try:
                self._remove_holding(_c)
            except Exception as _e:
                QMessageBox.critical(dlg, '删除失败', '%s: %s' % (type(_e).__name__, _e))
                return
            self.set_status('已移除 %s' % _c)
            _reload()
            self.refresh()

        btn_add.clicked.connect(_do_add)
        btn_del.clicked.connect(_do_del)
        btn_close.clicked.connect(dlg.accept)
        _reload()
        return dlg

    def _open_holding_manager(self):
        """「➕ 添加个股」入口。"""
        self._build_holding_dialog().exec()
'''
lines[i:i] = add_lines(METHODS)

out = '\r\n'.join(lines)
open(P, 'w', newline='', encoding='utf-8').write(out)
chk = open(P, newline='', encoding='utf-8').read()
naked = chk.count('\n') - chk.count('\r\n')
print('补丁后：行数 %d，CRLF %d，裸LF %d' % (chk.count('\r\n') + 1, chk.count('\r\n'), naked))
print('按钮命中 %d | 弹窗方法命中 %d | 导入命中 %d' % (
    chk.count("'➕ 添加个股'"), chk.count('def _build_holding_dialog'), chk.count('QFormLayout, QTableWidget,')))
if naked:
    print('!! 行尾被破坏')
    sys.exit(1)
print('行尾完好（纯 CRLF）')
