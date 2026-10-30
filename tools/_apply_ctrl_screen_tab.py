# -*- coding: utf-8 -*-
"""一次性补丁：把「🎛 控盘选股」页挂进主窗口 Tab（battle_console_v2.py，纯 CRLF）。

两处改动：
  1) L6576 `self.tabs.addTab(self.home_page, '🤖 清一盘')` 之后插入页面创建 + addTab
  2) `_connect_signals` 里作战中控台那段之后，插入 stock_clicked → 个股分析

执行一次即失效，勿重跑。回退：copy /Y ...bak_before_ctrlscreen ...
"""
import io
import os
import shutil
import sys

TARGET = r'D:\QuantMonitorV6\ui\battle_console_v2.py'
BAK = TARGET + '.bak_before_ctrlscreen'

with io.open(TARGET, 'r', encoding='utf-8', newline='') as f:
    src = f.read()

A1 = "        self.tabs.addTab(self.home_page, '🤖 清一盘')\r\n"
NEW1 = A1 + """        # 【控盘选股页】以控盘标准单独筛全市场的独立页面（2026-10-11 新增）
        # 口径：控盘分 + 洗盘/出货阶段 + 近120日位置，叠加 C4/C6/试盘/出货形态/拉升观察因子
        try:
            from ui.battle_widgets.control_screen_widget import ControlScreenWidget
            self.ctrl_screen_page = ControlScreenWidget()
            self.tabs.addTab(self.ctrl_screen_page, '🎛 控盘选股')
            print("[主窗口] 控盘选股页已添加", flush=True)
        except Exception as _cs_err:
            print(f"[主窗口] 控盘选股页加载失败: {_cs_err}", flush=True)
            import traceback; traceback.print_exc()
            self.ctrl_screen_page = QWidget()
            _cs_lay = QVBoxLayout(self.ctrl_screen_page)
            _cs_lay.addWidget(L(f'控盘选股页加载失败: {_cs_err}', C.RED, 12,
                                align=Qt.AlignmentFlag.AlignCenter))
            self.tabs.addTab(self.ctrl_screen_page, '🎛 控盘选股')
"""

A2 = ("        except Exception as _e:\r\n"
      "            print(f'[信号连接] 作战中控台 stock_clicked 连接失败: {_e}', flush=True)\r\n")
NEW2 = A2 + """        # 【控盘选股页】点击股票名称跳转个股分析
        try:
            if getattr(self, 'ctrl_screen_page', None) and hasattr(self.ctrl_screen_page, 'stock_clicked'):
                self.ctrl_screen_page.stock_clicked.connect(self._show_stock_detail)
                print('[信号连接] 控盘选股页 stock_clicked 已连接个股分析', flush=True)
        except Exception as _e:
            print(f'[信号连接] 控盘选股页 stock_clicked 连接失败: {_e}', flush=True)
"""

# 关键：待插入的文本块本身是用 \n 写的，必须统一成文件原生行尾（本文件纯 CRLF），
# 否则写回后出现「裸 LF」，破坏文件行尾（2026-10-11 第一次打补丁就踩到这个坑，已还原重打）。
NEW1 = NEW1.replace('\r\n', '\n').replace('\n', '\r\n')
NEW2 = NEW2.replace('\r\n', '\n').replace('\n', '\r\n')

n1 = src.count(A1)
n2 = src.count(A2)
assert n1 == 1, '锚点1命中 %d 次（期望 1）' % n1
assert n2 == 1, '锚点2命中 %d 次（期望 1）' % n2
assert 'ctrl_screen_page' not in src, '目标文件已含 ctrl_screen_page，疑似已打过补丁'

if not os.path.isfile(BAK):
    shutil.copy2(TARGET, BAK)
    print('备份: %s' % BAK)

out = src.replace(A1, NEW1, 1).replace(A2, NEW2, 1)
with io.open(TARGET, 'w', encoding='utf-8', newline='') as f:
    f.write(out)

# 校验行尾与语法
with io.open(TARGET, 'rb') as f:
    raw = f.read()
crlf = raw.count(b'\r\n')
lf = raw.count(b'\n')
print('写回: CRLF=%d 裸LF=%d 字节=%d' % (crlf, lf - crlf, len(raw)))
assert (lf - crlf) == 0, '行尾被破坏（出现裸 LF）'

import py_compile
sys.dont_write_bytecode = True
py_compile.compile(TARGET, doraise=True, cfile=os.devnull)
print('语法校验通过；插入后行数 %d' % out.count('\r\n'))
