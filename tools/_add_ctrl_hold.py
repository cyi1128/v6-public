# -*- coding: utf-8 -*-
"""分时做T（持仓表）：加「控盘」列。日K建仓表已有控盘列，这里只动做T表。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
sys.stdout.reconfigure(encoding='utf-8')
raw = open(P, 'rb').read()
_crlf = raw.count(b'\r\n')
_lf = raw.count(b'\n') - _crlf
print('行尾: CRLF=%d 裸LF=%d' % (_crlf, _lf))
shutil.copy2(P, P + '.bak_before_ctrl_hold')
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
    "    pct_color, BC, L,\n"
    ")\n",
    "from .base import (\n"
    "    BattleModuleBase, make_table, set_table_item,\n"
    "    pct_color, BC, L, CTRL_COL_TITLE, fetch_ctrl_for,\n"
    ")\n",
    'A1 import')

# 2) 做T表列常量 + 表头
rep("COL_H_NAME, COL_H_CODE, COL_H_PRICE, COL_H_PCT, \\\n"
    "    COL_H_BUY, COL_H_SELL, COL_H_MOM, COL_H_RISK, COL_H_SIG, \\\n"
    "    COL_H_ACT = range(10)\n"
    "HEADER_HOLD = ['股票名称', '代码', '现价', '涨跌幅',\n"
    "               '做T买点', '做T卖点', '动能信号', '风控状态',\n"
    "               '信号灯', '操作建议']\n",
    "COL_H_NAME, COL_H_CODE, COL_H_PRICE, COL_H_PCT, \\\n"
    "    COL_H_BUY, COL_H_SELL, COL_H_MOM, COL_H_RISK, COL_H_SIG, \\\n"
    "    COL_H_ACT, COL_H_CTRL = range(11)\n"
    "HEADER_HOLD = ['股票名称', '代码', '现价', '涨跌幅',\n"
    "               '做T买点', '做T卖点', '动能信号', '风控状态',\n"
    "               '信号灯', '操作建议', CTRL_COL_TITLE]\n",
    'A2 列常量+表头')

# 3) 做T表格：列数 + 宽度 + 拉伸目标改到「操作建议」
rep("        self.table = make_table(10, HEADER_HOLD)\n"
    "        widths_h = [80, 65, 60, 70, 70, 70, 90, 90, 70, 100]\n"
    "        for i, w in enumerate(widths_h):\n"
    "            self.table.setColumnWidth(i, w)\n",
    "        self.table = make_table(11, HEADER_HOLD)\n"
    "        widths_h = [80, 65, 60, 70, 70, 70, 90, 90, 70, 100, 78]\n"
    "        for i, w in enumerate(widths_h):\n"
    "            self.table.setColumnWidth(i, w)\n"
    "        # 「控盘」列插到末尾后，不能让末列自动拉伸（会把它撑开），\n"
    "        # 改成「操作建议」列吃剩余宽度\n"
    "        _hh = self.table.horizontalHeader()\n"
    "        _hh.setStretchLastSection(False)\n"
    "        _hh.setSectionResizeMode(COL_H_ACT, QHeaderView.ResizeMode.Stretch)\n",
    'A3 表格列数宽度')

# 4) 后台取数：挂控盘度
rep("        self._hold_rows = hold_rows\n",
    "        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）\n"
    "        fetch_ctrl_for(hold_rows)\n"
    "        self._hold_rows = hold_rows\n",
    'A4 后台取数挂控盘')

# 5) 渲染：控盘单元格 + 闪烁背景覆盖到新列
rep("            set_table_item(self.table, i, COL_H_ACT, act_short, act_color, bold=True, align=left)\n"
    "\n"
    "            # 触发行背景\n"
    "            if row_bg:\n"
    "                for col in range(10):\n",
    "            set_table_item(self.table, i, COL_H_ACT, act_short, act_color, bold=True, align=left)\n"
    "\n"
    "            # 控盘（新增列）\n"
    "            from services.control_profile import ctrl_cell, ctrl_tooltip\n"
    "            _ci = r.get('ctrl')\n"
    "            _ct, _cc = ctrl_cell(_ci)\n"
    "            _cit = set_table_item(self.table, i, COL_H_CTRL, _ct, _cc,\n"
    "                                  align=Qt.AlignmentFlag.AlignVCenter\n"
    "                                  | Qt.AlignmentFlag.AlignCenter)\n"
    "            _cit.setToolTip(ctrl_tooltip(_ci))\n"
    "\n"
    "            # 触发行背景\n"
    "            if row_bg:\n"
    "                for col in range(11):\n",
    'A5 渲染控盘+闪烁列数')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 分时做T 已加「控盘」列')
