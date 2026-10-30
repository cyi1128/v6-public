# -*- coding: utf-8 -*-
"""市场节奏 →「追踪」Tab（可介入追踪）：加「控盘」列。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\battle_widgets\picks_track_widget.py'
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
rep("from .base import make_table, set_table_item, BC, HeaderSorter\n",
    "from .base import make_table, set_table_item, BC, HeaderSorter, CTRL_COL_TITLE\n",
    'P1 import')

# 2) 表头 / 列常量 / 宽度
rep("TRACK_HEADERS = ['\u7b5b\u9009\u65e5\u671f', '\u80a1\u7968\u540d\u79f0', '\u80a1\u7968\u4ee3\u7801', '\u677f\u5757', '\u5165\u9009\u4ef7',\n"
    "                 '\u5f53\u524d\u4ef7', '5\u65e5\u76c8\u4e8f%', '30\u65e5\u76c8\u4e8f%', '\u7d2f\u8ba1\u76c8\u4e8f%']\n"
    "TRACK_COL_N = 9\n"
    "(T_DATE, T_NAME, T_CODE, T_BOARD, T_P0,\n"
    " T_NOW, T_R5, T_R30, T_CUM) = range(TRACK_COL_N)\n"
    "TRACK_WIDTHS = [92, 84, 74, 116, 74, 74, 82, 84, 84]\n",
    "TRACK_HEADERS = ['\u7b5b\u9009\u65e5\u671f', '\u80a1\u7968\u540d\u79f0', '\u80a1\u7968\u4ee3\u7801', '\u677f\u5757', '\u5165\u9009\u4ef7',\n"
    "                 '\u5f53\u524d\u4ef7', '5\u65e5\u76c8\u4e8f%', '30\u65e5\u76c8\u4e8f%', '\u7d2f\u8ba1\u76c8\u4e8f%',\n"
    "                 CTRL_COL_TITLE]\n"
    "TRACK_COL_N = 10\n"
    "(T_DATE, T_NAME, T_CODE, T_BOARD, T_P0,\n"
    " T_NOW, T_R5, T_R30, T_CUM, T_CTRL) = range(TRACK_COL_N)\n"
    "TRACK_WIDTHS = [92, 84, 74, 116, 74, 74, 82, 84, 84, 78]\n",
    'P2 表头列常量')

# 3) 加载后异步补控盘
rep("        self._render_stat()\n"
    "        self._render()\n"
    "        self._start_timer()\n",
    "        self._render_stat()\n"
    "        self._render()\n"
    "        # \u63a7\u76d8\u5ea6\uff1a\u540e\u53f0\u7b97\u5b8c\u518d\u5237\u4e00\u6b21\uff08\u4e0d\u963b\u585e UI\uff09\n"
    "        self._ctrl_fill(self._rows, self._render)\n"
    "        self._start_timer()\n",
    'P3 异步补控盘')

# 4) 渲染加控盘列
rep("            # \u60ac\u505c\uff1a\u628a\u53e3\u5f84\u5199\u6e05\u695a\n"
    "            it = self.table.item(row, T_NAME)\n",
    "            # \u63a7\u76d8\uff08\u65b0\u589e\u5217\uff09\n"
    "            from services.control_profile import ctrl_cell, ctrl_tooltip\n"
    "            _ci = r.get('ctrl')\n"
    "            _ct, _cc = ctrl_cell(_ci)\n"
    "            set_table_item(self.table, row, T_CTRL, _ct, _cc, align=center)\n"
    "            self.table.item(row, T_CTRL).setToolTip(ctrl_tooltip(_ci))\n"
    "            # \u60ac\u505c\uff1a\u628a\u53e3\u5f84\u5199\u6e05\u695a\n"
    "            it = self.table.item(row, T_NAME)\n",
    'P4 渲染控盘')

# 5) 这个 widget 继承的是 QWidget，没有 run_async，自带 _run 线程池 -> 加一个专用的异步补数
rep("    def _render_stat(self):\n",
    "    def _ctrl_fill(self, rows, on_done):\n"
    "        \"\"\"\u540e\u53f0\u7ed9 rows \u8865\u63a7\u76d8\u5ea6\uff0c\u5b8c\u6210\u540e\u56de UI \u7ebf\u7a0b\u6e32\u67d3\u3002\n"
    "\n"
    "        \u672c widget \u7ee7\u627f QWidget\uff08\u4e0d\u662f BattleModuleBase\uff09\uff0c\u6ca1\u6709 run_async\uff0c\n"
    "        \u8fd9\u91cc\u7528\u5b83\u81ea\u5e26\u7684 _run(\u7ebf\u7a0b\u6c60)\u5b9e\u73b0\u540c\u6837\u6548\u679c\u3002\n"
    "        \"\"\"\n"
    "        try:\n"
    "            if not rows:\n"
    "                return\n"
    "\n"
    "            def _bg():\n"
    "                from .base import fetch_ctrl_for\n"
    "                fetch_ctrl_for(rows)\n"
    "                return True\n"
    "\n"
    "            def _ok(_res):\n"
    "                try:\n"
    "                    on_done()\n"
    "                except Exception:\n"
    "                    pass\n"
    "\n"
    "            self._run(_bg, _ok)\n"
    "        except Exception:\n"
    "            pass\n"
    "\n"
    "    def _render_stat(self):\n",
    'P5 专用异步补数')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 市场节奏·追踪 已加「控盘」列')
