# -*- coding: utf-8 -*-
"""一次性补丁（v3c，页面）：空态 tooltip 提为模块常量（验证脚本直接引用，不重复字符串）。"""
import io
import os
import shutil
import tempfile

ROOT = r'D:\QuantMonitorV6'
WDG = os.path.join(ROOT, 'ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(WDG, 'r', encoding='utf-8').read()
assert '_ANN_EMPTY_TIP' not in s

A = """_BIZ_COLOR = '#00695c'     # 主营收入：深青（与「日K建仓」模式列同色系）
_ANN_COLOR = '#1565c0'     # 最新公告：深蓝（与「日K建仓」触发条件列同色）"""
N = """_BIZ_COLOR = '#00695c'     # 主营收入：深青（与「日K建仓」模式列同色系）
_ANN_COLOR = '#1565c0'     # 最新公告：深蓝（与「日K建仓」触发条件列同色）
# 空态 tooltip（提为常量，验证脚本直接引用，避免两处字符串各写一份）
_BIZ_EMPTY_TIP = '尚无主营构成数据（东财 F10 未返回，或还没补数）'
_ANN_EMPTY_TIP = '尚无公告数据（东财/新浪/巨潮都没给出，或还没补数）'"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

A = """            _biz_item.setToolTip(_biz_tip or '尚无主营构成数据（东财 F10 未返回，或还没补数）')"""
N = """            _biz_item.setToolTip(_biz_tip or _BIZ_EMPTY_TIP)"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

A = """            _ann_item.setToolTip(_ann_tip or '尚无公告数据（东财/巨潮都为空，或还没补数）')"""
N = """            _ann_item.setToolTip(_ann_tip or _ANN_EMPTY_TIP)"""
assert s.count(A) == 1
s = s.replace(A, N, 1)

if not os.path.isfile(WDG + '.bak_before_extras3c'):
    shutil.copy2(WDG, WDG + '.bak_before_extras3c')
io.open(WDG, 'w', encoding='utf-8', newline='').write(s)
import py_compile   # noqa: E402
py_compile.compile(WDG, cfile=os.path.join(tempfile.gettempdir(), 'wdg3c.pyc'), doraise=True)
b = io.open(WDG, 'rb').read()
print('页面: 行=%d CRLF=%d 字节=%d ｜ 语法通过' % (b.count(b'\n'), b.count(b'\r\n'), len(b)))
