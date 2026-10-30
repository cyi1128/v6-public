# -*- coding: utf-8 -*-
"""1) base.py 加 ctrl_async_fill；2) 竞价筛选加「控盘」列（今日竞价表 + 竞价追踪表）。"""
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

# ---------------- base.py：异步补控盘 ----------------
PB = r'D:\QuantMonitorV6\ui\battle_widgets\base.py'
raw = open(PB, 'rb').read()
_c = raw.count(b'\r\n')
_l = raw.count(b'\n') - _c
shutil.copy2(PB, PB + '.bak_before_ctrl2')
s = raw.decode('utf-8')
if _c and not _l:
    s = s.replace('\r\n', '\n')

HW = 4 * ' '
method = (
    HW + "def ctrl_async_fill(self, rows, on_done=None):\n"
    + HW + '    """\u540e\u53f0\u5f02\u6b65\u7ed9 rows \u8865\u63a7\u76d8\u5ea6\uff0c\u5b8c\u6210\u540e\u56de UI \u7ebf\u7a0b\u56de\u8c03 on_done\u3002\n'
    "\n"
    + HW + "    \u9002\u7528\u4e8e\u6570\u636e\u8def\u5f84\u591a\u6837\uff08\u5feb\u7167 / \u63a5\u53e3 / \u6570\u636e\u5e93\uff09\u3001\u4e0d\u597d\u5728\u53d6\u6570\u51fd\u6570\u91cc\u7edf\u4e00\u63d2\u5165\u7684\u6a21\u5757\uff1a\n"
    + HW + "    \u5148\u7528\u65e7\u6570\u636e\u6e32\u67d3\u4e00\u904d\uff08\u7acb\u5373\u53ef\u89c1\uff09\uff0c\u63a7\u76d8\u5206\u7b97\u5b8c\u540e\u518d\u5237\u4e00\u6b21\u3002\n"
    + HW + '    """\n'
    + HW + "    try:\n"
    + HW + "        if not rows:\n"
    + HW + "            if on_done:\n"
    + HW + "                on_done()\n"
    + HW + "            return\n"
    "\n"
    + HW + "        def _bg():\n"
    + HW + "            return fetch_ctrl_for(rows)\n"
    "\n"
    + HW + "        def _ok(_res):\n"
    + HW + "            if on_done:\n"
    + HW + "                try:\n"
    + HW + "                    on_done()\n"
    + HW + "                except Exception:\n"
    + HW + "                    pass\n"
    "\n"
    + HW + "        self.run_async(_bg, _ok, None)\n"
    + HW + "    except Exception:\n"
    + HW + "        if on_done:\n"
    + HW + "            try:\n"
    + HW + "                on_done()\n"
    + HW + "            except Exception:\n"
    + HW + "                pass\n"
    "\n"
    "\n"
)
anchor = HW + "def run_async(self, func, on_success, on_failed=None, *args, **kwargs):\n"
assert s.count(anchor) == 1, 'base run_async 锚点 %d' % s.count(anchor)
s = s.replace(anchor, method + anchor, 1)
open(PB, 'wb').write((s.replace('\n', '\r\n') if (_c and not _l) else s).encode('utf-8'))
py_compile.compile(PB, doraise=True)
print('OK base.py 已加 ctrl_async_fill')

# ---------------- 竞价筛选 ----------------
P = r'D:\QuantMonitorV6\ui\battle_widgets\auction_filter_widget.py'
raw = open(P, 'rb').read()
_crlf = raw.count(b'\r\n')
_lf = raw.count(b'\n') - _crlf
print('竞价 行尾: CRLF=%d 裸LF=%d' % (_crlf, _lf))
shutil.copy2(P, P + '.bak_before_ctrl')
s = raw.decode('utf-8')
if _crlf and not _lf:
    s = s.replace('\r\n', '\n')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# B1 import
rep("from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item,\n",
    "from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item, CTRL_COL_TITLE,\n",
    'B1 import')

# B2 表头 + 列常量
rep("HEADER_LABELS = [\n"
    "    '\u80a1\u7968\u540d\u79f0', '\u80a1\u7968\u4ee3\u7801', '\u7efc\u5408\u5f97\u5206', '\u7ade\u4ef7\u6da8\u5e45',\n"
    "    '\u5f53\u524d\u6da8\u5e45', '\u7ade\u4ef7\u91d1\u989d', '\u5f53\u524d\u91d1\u989d', '\u5f3a\u52bf\u9898\u6750',\n"
    "]  # [UI-COL] \u5220\u7ade\u4ef7\u6362\u624b\u7387/\u5206\u65f6\u5f62\u6001/\u98ce\u9669\u6807\u8bb0\uff0c\u52a0\u5f53\u524d\u6da8\u5e45/\u7ade\u4ef7\u91d1\u989d/\u5f53\u524d\u91d1\u989d\n",
    "HEADER_LABELS = [\n"
    "    '\u80a1\u7968\u540d\u79f0', '\u80a1\u7968\u4ee3\u7801', '\u7efc\u5408\u5f97\u5206', '\u7ade\u4ef7\u6da8\u5e45',\n"
    "    '\u5f53\u524d\u6da8\u5e45', '\u7ade\u4ef7\u91d1\u989d', '\u5f53\u524d\u91d1\u989d', '\u5f3a\u52bf\u9898\u6750',\n"
    "    CTRL_COL_TITLE,\n"
    "]  # [UI-COL] \u5220\u7ade\u4ef7\u6362\u624b\u7387/\u5206\u65f6\u5f62\u6001/\u98ce\u9669\u6807\u8bb0\uff0c\u52a0\u5f53\u524d\u6da8\u5e45/\u7ade\u4ef7\u91d1\u989d/\u5f53\u524d\u91d1\u989d\n"
    "COL_CTRL = 8\n",
    'B2 主表头+列常量')

# B3 主表建表
rep("        self.table = make_table(8, HEADER_LABELS, min_row_height=24)\n"
    "        widths = [86, 70, 60, 75, 75, 80, 80, 260]  # [UI-W] \u5f3a\u52bf\u9898\u6750\u52a0\u5bbd\uff0c\u98ce\u9669\u6807\u8bb0\u6536\u7a84\n",
    "        self.table = make_table(9, HEADER_LABELS, min_row_height=24)\n"
    "        widths = [86, 70, 60, 75, 75, 80, 80, 260, 78]  # [UI-W] \u5f3a\u52bf\u9898\u6750\u52a0\u5bbd\uff0c\u672b\u5217\u63a7\u76d8\n",
    'B3 主表建表')

# B4 主表排序键
rep("                4: lambda r: r['jj_turnover'],\n"
    "            },\n"
    "            getter=lambda: self._rows,\n",
    "                4: lambda r: r['jj_turnover'],\n"
    "                8: lambda r: ((r.get('ctrl') or {}).get('score') or 0),\n"
    "            },\n"
    "            getter=lambda: self._rows,\n",
    'B4 主表排序键')

# B5 主表渲染加控盘列
rep("            themes = r.get('theme_display', '--') or '--'\n"
    "            set_table_item(self.table, row, 7, themes, BC.TEXT)\n"
    "            self.table.item(row, 7).setToolTip(themes)\n",
    "            themes = r.get('theme_display', '--') or '--'\n"
    "            set_table_item(self.table, row, 7, themes, BC.TEXT)\n"
    "            self.table.item(row, 7).setToolTip(themes)\n"
    "            # 8 控盘（新增列）\n"
    "            from services.control_profile import ctrl_cell, ctrl_tooltip\n"
    "            _ci = r.get('ctrl')\n"
    "            _ct, _cc = ctrl_cell(_ci)\n"
    "            set_table_item(self.table, row, COL_CTRL, _ct, _cc, align=center)\n"
    "            self.table.item(row, COL_CTRL).setToolTip(ctrl_tooltip(_ci))\n",
    'B5 主表渲染')

# B6 主表加载后异步补控盘
rep("        self._rows.sort(key=lambda x: -(x.get('score') or 0))\n"
    "        self._render_rows()\n"
    "        if self._rows:\n"
    "            self.title_label.setText(f'\u26a1 \u7ade\u4ef7 TOP{len(self._rows)}')\n",
    "        self._rows.sort(key=lambda x: -(x.get('score') or 0))\n"
    "        self._render_rows()\n"
    "        # \u63a7\u76d8\u5ea6\uff1a\u540e\u53f0\u7b97\u5b8c\u518d\u5237\u4e00\u6b21\uff08\u4e0d\u963b\u585e UI\uff09\n"
    "        self.ctrl_async_fill(self._rows, self._render_rows)\n"
    "        if self._rows:\n"
    "            self.title_label.setText(f'\u26a1 \u7ade\u4ef7 TOP{len(self._rows)}')\n",
    'B6 主表异步补控盘')

# B7 尾盘加载后也补
rep("            if r.get('code') not in existing:\n"
    "                self._rows.append(r)\n"
    "        self._rows.sort(key=lambda x: -(x.get('score') or 0))\n"
    "        self._render_rows()\n",
    "            if r.get('code') not in existing:\n"
    "                self._rows.append(r)\n"
    "        self._rows.sort(key=lambda x: -(x.get('score') or 0))\n"
    "        self._render_rows()\n"
    "        self.ctrl_async_fill(self._rows, self._render_rows)\n",
    'B7 尾盘异步补控盘')

# B8 追踪表：表头 + 列常量
rep("TRACK_HEADERS = [\n"
    "    '\u7b5b\u9009\u65e5\u671f', '\u80a1\u7968\u540d\u79f0', '\u9898\u6750', '\u80a1\u7968\u4ee3\u7801', '\u7ade\u4ef7\u91d1\u989d(P0)',\n"
    "    '\u5f53\u524d\u5b9e\u65f6\u4ef7', '5\u65e5\u76c8\u4e8f%', '30\u65e5\u76c8\u4e8f%', '\u7d2f\u8ba1\u76c8\u4e8f%',\n"
    "]\n"
    "TRACK_COL_N = 9\n"
    "# \u8ffd\u8e2a\u8868\u5217\u7d22\u5f15\u5e38\u91cf\n"
    "C_DATE, C_NAME, C_THEME, C_CODE, C_P0 = 0, 1, 2, 3, 4\n"
    "C_NOW, C_P5, C_P30, C_CUM = 5, 6, 7, 8\n",
    "TRACK_HEADERS = [\n"
    "    '\u7b5b\u9009\u65e5\u671f', '\u80a1\u7968\u540d\u79f0', '\u9898\u6750', '\u80a1\u7968\u4ee3\u7801', '\u7ade\u4ef7\u91d1\u989d(P0)',\n"
    "    '\u5f53\u524d\u5b9e\u65f6\u4ef7', '5\u65e5\u76c8\u4e8f%', '30\u65e5\u76c8\u4e8f%', '\u7d2f\u8ba1\u76c8\u4e8f%', CTRL_COL_TITLE,\n"
    "]\n"
    "TRACK_COL_N = 10\n"
    "# \u8ffd\u8e2a\u8868\u5217\u7d22\u5f15\u5e38\u91cf\n"
    "C_DATE, C_NAME, C_THEME, C_CODE, C_P0 = 0, 1, 2, 3, 4\n"
    "C_NOW, C_P5, C_P30, C_CUM = 5, 6, 7, 8\n"
    "C_TRACK_CTRL = 9\n",
    'B8 追踪表头')

# B9 追踪表建表 + 拉伸目标改到累计盈亏
rep("        self.track_table = make_table(TRACK_COL_N, TRACK_HEADERS, min_row_height=24)\n"
    "        track_widths = [92, 80, 150, 70, 86, 86, 76, 76, 84]\n"
    "        for i, w in enumerate(track_widths):\n"
    "            self.track_table.setColumnWidth(i, w)\n",
    "        self.track_table = make_table(TRACK_COL_N, TRACK_HEADERS, min_row_height=24)\n"
    "        track_widths = [92, 80, 150, 70, 86, 86, 76, 76, 84, 78]\n"
    "        for i, w in enumerate(track_widths):\n"
    "            self.track_table.setColumnWidth(i, w)\n"
    "        # \u63a7\u76d8\u5217\u63d2\u5230\u672b\u5c3e\u540e\uff0c\u6539\u6210\u300c\u7d2f\u8ba1\u76c8\u4e8f\u300d\u5217\u5403\u5269\u4f59\u5bbd\u5ea6\n"
    "        _th = self.track_table.horizontalHeader()\n"
    "        _th.setStretchLastSection(False)\n"
    "        _th.setSectionResizeMode(C_CUM, QHeaderView.ResizeMode.Stretch)\n",
    'B9 追踪建表')

# B10 追踪渲染加控盘列
rep("        for row, r in enumerate(rows):\n"
    "            # 0 \u7b5b\u9009\u65e5\u671f\n"
    "            set_table_item(self.track_table, row, C_DATE, r['trade_date'], '#000000', align=center)\n",
    "        for row, r in enumerate(rows):\n"
    "            # 9 \u63a7\u76d8\uff08\u65b0\u589e\u5217\uff09\n"
    "            from services.control_profile import ctrl_cell as _cc2, ctrl_tooltip as _ct2\n"
    "            _i2 = r.get('ctrl')\n"
    "            _t2, _c2 = _cc2(_i2)\n"
    "            set_table_item(self.track_table, row, C_TRACK_CTRL, _t2, _c2, align=center)\n"
    "            self.track_table.item(row, C_TRACK_CTRL).setToolTip(_ct2(_i2))\n"
    "            # 0 \u7b5b\u9009\u65e5\u671f\n"
    "            set_table_item(self.track_table, row, C_DATE, r['trade_date'], '#000000', align=center)\n",
    'B10 追踪渲染')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 竞价筛选（今日竞价 + 竞价追踪）已加「控盘」列')
