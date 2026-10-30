# -*- coding: utf-8 -*-
"""今日涨停模块：加「控盘」列（加在最后一列，不动原有列号）。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\limit_up_widget.py'
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
    "    pct_color, format_pct, BC, HeaderSorter,\n"
    ")\n",
    "from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item,\n"
    "    pct_color, format_pct, BC, HeaderSorter,\n"
    "    fetch_ctrl_for, attach_ctrl, CTRL_COL_TITLE,\n"
    ")\n",
    'H1 import')

# 2) 列常量 + 表头
rep("COL_MV, COL_THEME = 4, 5\n"
    "HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '市值', '题材']\n",
    "COL_MV, COL_THEME = 4, 5\n"
    "COL_CTRL = 6\n"
    "HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '市值', '题材', CTRL_COL_TITLE]\n",
    'H2 列常量+表头')

# 3) 列数
rep("        self.table = make_table(6, HEADER_LABELS)\n",
    "        self.table = make_table(7, HEADER_LABELS)\n",
    'H3 列数')

# 4) 列宽 + 改 stretch 目标
rep("        self.table.setColumnWidth(COL_MV, 84)\n"
    "        # 末列「题材」由 make_table 的 stretchLastSection 自动吃掉剩余宽度\n",
    "        self.table.setColumnWidth(COL_MV, 84)\n"
    "        # 「控盘」列插到末尾后，stretchLastSection 会把控盘列撑开，\n"
    "        # 所以改成显式指定「题材」列吃剩余宽度（与日K建仓表同一做法）\n"
    "        self.table.setColumnWidth(COL_CTRL, 80)\n"
    "        from PyQt6.QtWidgets import QHeaderView\n"
    "        _h = self.table.horizontalHeader()\n"
    "        _h.setStretchLastSection(False)\n"
    "        _h.setSectionResizeMode(COL_THEME, QHeaderView.ResizeMode.Stretch)\n",
    'H4 列宽+stretch')

# 5) 排序键
rep("                5: lambda r: r.get('_theme', ''),\n",
    "                5: lambda r: r.get('_theme', ''),\n"
    "                6: lambda r: ((r.get('ctrl') or {}).get('score') or 0),\n",
    'H5 排序键')

# 6) 后台取数：挂控盘度
rep("        # 按涨幅降序，同涨幅按代码\n"
    "        result.sort(key=lambda x: (-x['pct'], x['code']))\n"
    "        return result, 'em'\n",
    "        # 按涨幅降序，同涨幅按代码\n"
    "        result.sort(key=lambda x: (-x['pct'], x['code']))\n"
    "        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）\n"
    "        fetch_ctrl_for(result)\n"
    "        return result, 'em'\n",
    'H6 后台取数挂控盘')

# 7) 渲染：填控盘列
rep("            # 题材\n"
    "            set_table_item(self.table, row, COL_THEME, s.get('_theme', '--'), BC.RED, bold=True)\n",
    "            # 题材\n"
    "            set_table_item(self.table, row, COL_THEME, s.get('_theme', '--'), BC.RED, bold=True)\n"
    "            # 控盘（新增列，填在最后一列）\n"
    "            attach_ctrl(self.table, stocks, col=COL_CTRL)\n",
    'H7 渲染填控盘')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 今日涨停 已加「控盘」列')
