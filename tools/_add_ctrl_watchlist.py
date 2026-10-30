# -*- coding: utf-8 -*-
"""自选评分模块：加「控盘」列（加在最后一列，不动原有列号）。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\watchlist_widget.py'
sys.stdout.reconfigure(encoding='utf-8')
raw = open(P, 'rb').read()
_crlf = raw.count(b'\r\n')
_lf = raw.count(b'\n') - _crlf
print('行尾: CRLF=%d 裸LF=%d' % (_crlf, _lf))
shutil.copy2(P, P + '.bak_before_ctrl')
s = raw.decode('utf-8')
if _crlf and not _lf:
    s = s.replace('\r\n', '\n')


def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '%s 命中 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  OK', tag)


# 1) import
rep("from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item,\n"
    "    pct_color, format_pct, BC, L,\n"
    ")\n",
    "from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item,\n"
    "    pct_color, format_pct, BC, L, CTRL_COL_TITLE,\n"
    ")\n",
    'W1 import')

# 2) 列常量 + 表头
rep("COL_AMP, COL_MV, COL_THEME = 4, 5, 6\n"
    "HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '振幅', '市值', '题材']\n",
    "COL_AMP, COL_MV, COL_THEME = 4, 5, 6\n"
    "COL_CTRL = 7\n"
    "HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '振幅', '市值', '题材',\n"
    "                 CTRL_COL_TITLE]\n",
    'W2 列常量+表头')

# 3) 列数 + 列宽 + stretch 目标
rep("        self.table = make_table(7, HEADER_LABELS)\n"
    "        self.table.setColumnWidth(0, 95)\n"
    "        self.table.setColumnWidth(1, 70)\n"
    "        self.table.setColumnWidth(2, 60)\n"
    "        self.table.setColumnWidth(3, 65)\n"
    "        self.table.setColumnWidth(4, 60)\n"
    "        self.table.setColumnWidth(5, 70)\n"
    "        self.table.setColumnWidth(6, 120)\n",
    "        self.table = make_table(8, HEADER_LABELS)\n"
    "        self.table.setColumnWidth(0, 95)\n"
    "        self.table.setColumnWidth(1, 70)\n"
    "        self.table.setColumnWidth(2, 60)\n"
    "        self.table.setColumnWidth(3, 65)\n"
    "        self.table.setColumnWidth(4, 60)\n"
    "        self.table.setColumnWidth(5, 70)\n"
    "        self.table.setColumnWidth(6, 110)\n"
    "        self.table.setColumnWidth(COL_CTRL, 78)\n"
    "        # 「控盘」插到末尾后不能再让末列自动拉伸（会把它撑开），\n"
    "        # 改成指定「题材」列吃剩余宽度\n"
    "        self.table.horizontalHeader().setStretchLastSection(False)\n"
    "        self.table.horizontalHeader().setSectionResizeMode(\n"
    "            COL_THEME, QHeaderView.ResizeMode.Stretch)\n",
    'W3 列数+列宽')

# 4) 排序键：支持按控盘分排序
rep("            elif col == COL_PCT:\n"
    "                v = q.get('pct_chg')\n"
    "            else:\n"
    "                v = 0\n",
    "            elif col == COL_PCT:\n"
    "                v = q.get('pct_chg')\n"
    "            elif col == COL_CTRL:\n"
    "                v = (q.get('ctrl') or {}).get('score')\n"
    "            else:\n"
    "                v = 0\n",
    'W4 排序键')

# 5) 后台取数：把控盘度挂到每只行情上
rep("                themes[c] = industry or '--'\n"
    "        return quotes, themes\n",
    "                themes[c] = industry or '--'\n"
    "        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）\n"
    "        from services.control_profile import get_ctrl_map\n"
    "        _cm = get_ctrl_map([str(c) for c in codes])\n"
    "        for _c, _q in (quotes or {}).items():\n"
    "            if isinstance(_q, dict):\n"
    "                _q['ctrl'] = _cm.get(str(_c))\n"
    "        return quotes, themes\n",
    'W5 后台取数挂控盘')

# 6) 渲染：填控盘单元格（本模块行序是 display_order，必须按行内 code 取）
rep("                # 题材（选股雷达同源）\n"
    "                theme = (self._themes or {}).get(code, '--') or '--'\n"
    "                set_table_item(self.table, view_row, COL_THEME, theme, BC.RED, bold=True)\n",
    "                # 题材（选股雷达同源）\n"
    "                theme = (self._themes or {}).get(code, '--') or '--'\n"
    "                set_table_item(self.table, view_row, COL_THEME, theme, BC.RED, bold=True)\n"
    "\n"
    "                # 控盘（新增列）：'98·候选' / '80·出货' / '97·洗盘' / '71' / '--'\n"
    "                from services.control_profile import ctrl_cell, ctrl_tooltip\n"
    "                _ci = q.get('ctrl')\n"
    "                _ct, _cc = ctrl_cell(_ci)\n"
    "                _cit = set_table_item(self.table, view_row, COL_CTRL, _ct, _cc,\n"
    "                                      align=Qt.AlignmentFlag.AlignVCenter\n"
    "                                      | Qt.AlignmentFlag.AlignCenter)\n"
    "                _cit.setToolTip(ctrl_tooltip(_ci))\n",
    'W6 渲染填控盘')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 自选评分 已加「控盘」列')
