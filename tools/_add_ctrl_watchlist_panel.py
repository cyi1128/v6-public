# -*- coding: utf-8 -*-
"""主界面「⭐ 自选评分」（ui\\watchlist_panel.py）加「控盘」列。纯 CRLF 文件。"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\ui\watchlist_panel.py'
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


# 1) 列数
rep("        self.table = QTableWidget()\n"
    "        self.table.setColumnCount(9)\n"
    "        self.table.setHorizontalHeaderLabels([\n"
    "            '\u4ee3\u7801', '\u540d\u79f0', '\u73b0\u4ef7', '\u6da8\u8dcc\u5e45', '\u6da8\u505c\u5f02\u52a8\u9898\u6750', "
    "'\u8d8b\u52bf', '\u6da8\u505c\u6b21\u6570', '\u5173\u952e\u4ef7\u683c', 'AI\u64cd\u4f5c\u5efa\u8bae'\n"
    "        ])\n",
    "        self.table = QTableWidget()\n"
    "        self.table.setColumnCount(10)\n"
    "        self.table.setHorizontalHeaderLabels([\n"
    "            '\u4ee3\u7801', '\u540d\u79f0', '\u73b0\u4ef7', '\u6da8\u8dcc\u5e45', '\u6da8\u505c\u5f02\u52a8\u9898\u6750', "
    "'\u8d8b\u52bf', '\u6da8\u505c\u6b21\u6570', '\u5173\u952e\u4ef7\u683c', 'AI\u64cd\u4f5c\u5efa\u8bae', '\u63a7\u76d8'\n"
    "        ])\n",
    'W1 列数+表头')

# 2) 列宽（接在现有最后一列 8 的列宽设置之后）
rep("        self.table.setColumnWidth(8, 120)  # AI\u64cd\u4f5c\u5efa\u8bae\n",
    "        self.table.setColumnWidth(8, 120)  # AI\u64cd\u4f5c\u5efa\u8bae\n"
    "        self.table.setColumnWidth(9, 78)    # \u63a7\u76d8\n",
    'W2 列宽')

# 3) 行渲染：末列加控盘
rep("            self.table.setItem(row, 8, ai_item)\n"
    "\n"
    "            # 8\u7ef4\u8bc4\u5206\u548c\u7b56\u7565\u7248\u672c\u5217\u5df2\u5220\u9664\uff08V2.7.1 UI\u7b2c\u4e8c\u8f6e\uff09\n",
    "            self.table.setItem(row, 8, ai_item)\n"
    "\n"
    "            # 9 \u63a7\u76d8\uff08\u65b0\u589e\uff0c\u540e\u53f0\u7b97\u597d\u540e\u518d\u5237\u4e00\u6b21\uff09\n"
    "            from services.control_profile import ctrl_cell, ctrl_tooltip\n"
    "            _ci = stock.get('ctrl')\n"
    "            _ct, _ccolor = ctrl_cell(_ci)\n"
    "            ctrl_item = QTableWidgetItem(_ct)\n"
    "            ctrl_item.setForeground(QBrush(QColor(_ccolor)))\n"
    "            ctrl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)\n"
    "            ctrl_item.setToolTip(ctrl_tooltip(_ci))\n"
    "            self.table.setItem(row, 9, ctrl_item)\n"
    "\n"
    "            # 8\u7ef4\u8bc4\u5206\u548c\u7b56\u7565\u7248\u672c\u5217\u5df2\u5220\u9664\uff08V2.7.1 UI\u7b2c\u4e8c\u8f6e\uff09\n",
    'W3 行渲染')

# 4) 渲染完发起后台补算
rep("        self.table.setSortingEnabled(True)\n"
    "\n"
    "        # \u4fdd\u5b58\u5f53\u524d\u9009\u4e2d\u7684\u80a1\u7968\u4ee3\u7801\n",
    "        self.table.setSortingEnabled(True)\n"
    "        # \u63a7\u76d8\u5ea6\uff1a\u540e\u53f0\u8865\u7b97\uff08\u4e0d\u963b\u585e UI\uff09\uff0c\u7b97\u5b8c\u7528\u5df2\u6709\u7684 theme_ready \u4fe1\u53f7\u91cd\u7ed8\n"
    "        self._ctrl_async(stocks)\n"
    "\n"
    "        # \u4fdd\u5b58\u5f53\u524d\u9009\u4e2d\u7684\u80a1\u7968\u4ee3\u7801\n",
    'W4 触发补算')

# 5) 异步方法
rep("    def _update_table(self, stocks=None):\n",
    "    def _ctrl_async(self, stocks):\n"
    "        \"\"\"\u540e\u53f0\u7ed9\u884c\u6570\u636e\u8865\u63a7\u76d8\u5ea6\uff0c\u7b97\u5b8c\u7528 theme_ready \u4fe1\u53f7\u89e6\u53d1\u91cd\u7ed8\u3002\n"
    "\n"
    "        \u672c\u7c7b\u7ee7\u627f QWidget \u4e14\u9875\u9762\u5df2\u6709 `theme_ready -> _update_table` \u8fde\u63a5\uff0c\n"
    "        \u6240\u4ee5\u4e0d\u65b0\u589e\u4fe1\u53f7\uff1b\u5df2\u586b\u8fc7 ctrl \u7684\u884c\u4e0b\u6b21\u76f4\u63a5\u8df3\u8fc7\uff0c\u4e0d\u4f1a\u5faa\u73af\u91cd\u7ed8\u3002\n"
    "        \"\"\"\n"
    "        try:\n"
    "            if getattr(self, '_ctrl_busy', False):\n"
    "                return\n"
    "            need = [x for x in (stocks or []) if x.get('ctrl') is None and x.get('code')]\n"
    "            if not need:\n"
    "                return\n"
    "            self._ctrl_busy = True\n"
    "\n"
    "            def _do():\n"
    "                try:\n"
    "                    from services.control_profile import get_ctrl_map\n"
    "                    m = get_ctrl_map([x['code'] for x in need])\n"
    "                    for x in need:\n"
    "                        x['ctrl'] = m.get(x['code'])\n"
    "                except Exception as e:\n"
    "                    print('[自选评分] 控盘度补算失败: %s' % e, flush=True)\n"
    "                finally:\n"
    "                    self._ctrl_busy = False\n"
    "                try:\n"
    "                    self.theme_ready.emit()\n"
    "                except Exception:\n"
    "                    pass\n"
    "\n"
    "            threading.Thread(target=_do, daemon=True).start()\n"
    "        except Exception:\n"
    "            self._ctrl_busy = False\n"
    "\n"
    "    def _update_table(self, stocks=None):\n",
    'W5 异步方法')

out = s.replace('\n', '\r\n') if (_crlf and not _lf) else s
open(P, 'wb').write(out.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK 自选评分（主界面 ⭐ Tab）已加「控盘」列')
