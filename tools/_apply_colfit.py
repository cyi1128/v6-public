# -*- coding: utf-8 -*-
"""一次性补丁：控盘选股页列宽改为「按内容自适应」。执行一次即失效，勿重跑。

改 4 处（都在 ui\battle_widgets\control_screen_widget.py，纯 LF）：
  1. 新增 from PyQt6.QtGui import QFontMetrics
  2. PAGE_WIDTHS 之后新增 _WIDTH_PAD / _FIT_SAMPLE / _THEME_MIN_W / _FIT_COLS /
     PAGE_WIDTHS_MIN / PAGE_WIDTHS_MAX（上下限）
  3. _render() 末尾调用 _autofit_columns()，并新增该方法
  4. showEvent 里加一次延迟自适应（首帧布局完成后再校一次）
"""
import io
import os
import shutil
import sys

ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
P = os.path.join('ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '本文件应为纯 LF，行尾不符，停止'
orig = s

# ---- 1. QFontMetrics ----
old = ("from .base import (BC, L, HeaderSorter, BattleModuleBase, make_table,\n"
       "                   set_table_item, pct_color)")
new = ("from PyQt6.QtGui import QFontMetrics\n\n"
       "from .base import (BC, L, HeaderSorter, BattleModuleBase, make_table,\n"
       "                   set_table_item, pct_color)")
assert s.count(old) == 1, 'import 锚点不唯一'
s = s.replace(old, new)

# ---- 2. 常量块 ----
old = "PAGE_WIDTHS = [96, 66, 70, 74, 230, 170, 70, 58, 58, 96, 190, 260, 90]\n"
new = old + (
    "# 列宽自适应（_autofit_columns）：上面 PAGE_WIDTHS 只是首帧初值，渲染后按\n"
    "# 「这一列的内容实际需要多宽」重设 —— 短列（阶段/位置/控盘分）不占空，\n"
    "# 长列（主营收入/最新公告/观察）尽量给足，目标是不出现省略号。\n"
    "# 「涨停题材」仍是拉伸列（Stretch），吃掉剩余空间，所以不为它设宽度。\n"
    "_WIDTH_PAD = 22         # 单元格左右 padding 8+8 + 一点呼吸空间\n"
    "_FIT_SAMPLE = 400       # 逐格量字的采样行数上限（3300 行全量太慢，均匀采样够代表最长文本）\n"
    "_THEME_MIN_W = 150      # 拉伸列（涨停题材）至少留这么宽，窗口太窄时不再压别的列\n"
    "_FIT_COLS = [c for c in range(PAGE_COL_N) if c != C_THEME]\n"
    "PAGE_WIDTHS_MIN = {C_NAME: 80, C_CODE: 58, C_PRICE: 60, C_PCT: 64, C_BIZ: 118,\n"
    "                   C_SCORE: 56, C_STAGE: 42, C_POS: 42, C_LABEL: 56,\n"
    "                   C_OBS: 56, C_ANN: 148, C_DATE: 74}\n"
    "PAGE_WIDTHS_MAX = {C_NAME: 132, C_CODE: 80, C_PRICE: 86, C_PCT: 90, C_BIZ: 330,\n"
    "                   C_SCORE: 80, C_STAGE: 60, C_POS: 60, C_LABEL: 108,\n"
    "                   C_OBS: 330, C_ANN: 460, C_DATE: 100}\n")
assert s.count(old) == 1, 'PAGE_WIDTHS 锚点不唯一'
s = s.replace(old, new)

# ---- 3. _render 末尾调用 + 新增方法 ----
old = ("        self._update_count()\n"
       "\n"
       "    def _update_count(self):\n")
new = ("        self._autofit_columns()\n"
       "        self._update_count()\n"
       "\n"
       "    def _autofit_columns(self):\n"
       '        """按内容把 12 个固定列调到「刚好显示得下」，拉伸列（涨停题材）吃剩余空间。\n'
       "\n"
       "        · 逐格用**该格自己的字体**量字（表里有加粗格，用统一字体会低估宽度）；\n"
       "        · 行数多，均匀采样 _FIT_SAMPLE 行取最长文本（3294 行全量 4 万次量字没必要）；\n"
       "        · 列宽有上下限：短列不吃空间，长列给足，避免出现省略号；\n"
       "        · 只有窗口真的放不下时，才按「观察 → 主营收入 → 最新公告」顺序压回下限，\n"
       "          再放不下就让横向滚动条接管（不为了塞进去而截断内容）。\n"
       '        """\n'
       "        rows = self._rows\n"
       "        n = len(rows)\n"
       "        if n <= 0:\n"
       "            return\n"
       "        try:\n"
       "            step = max(1, n // _FIT_SAMPLE)\n"
       "            fm_h = QFontMetrics(self.table.horizontalHeader().font())\n"
       "            _fms = {}\n"
       "\n"
       "            def _fm(f):\n"
       "                k = f.toString()\n"
       "                fm = _fms.get(k)\n"
       "                if fm is None:\n"
       "                    fm = QFontMetrics(f)\n"
       "                    _fms[k] = fm\n"
       "                return fm\n"
       "\n"
       "            need = {}\n"
       "            for c in _FIT_COLS:\n"
       "                _hit = self.table.horizontalHeaderItem(c)\n"
       "                w = fm_h.horizontalAdvance(_hit.text() if _hit else '') + 10\n"
       "                for i in range(0, n, step):\n"
       "                    it = self.table.item(i, c)\n"
       "                    if it is None:\n"
       "                        continue\n"
       "                    t = it.text()\n"
       "                    if t:\n"
       "                        w = max(w, _fm(it.font()).horizontalAdvance(t))\n"
       "                need[c] = min(max(w + _WIDTH_PAD, PAGE_WIDTHS_MIN[c]),\n"
       "                              PAGE_WIDTHS_MAX[c])\n"
       "            vw = int(self.table.viewport().width())\n"
       "            if vw >= 400:                       # 布局已完成才算「放不放得下」\n"
       "                over = sum(need.values()) + _THEME_MIN_W - vw\n"
       "                for c in (C_OBS, C_BIZ, C_ANN):\n"
       "                    if over <= 0:\n"
       "                        break\n"
       "                    _cut = min(need[c] - PAGE_WIDTHS_MIN[c], over)\n"
       "                    need[c] -= _cut\n"
       "                    over -= _cut\n"
       "            for c in _FIT_COLS:\n"
       "                self.table.setColumnWidth(c, int(round(need[c])))\n"
       "        except Exception:\n"
       "            pass\n"
       "\n"
       "    def _update_count(self):\n")
assert s.count(old) == 1, '_render 尾锚点不唯一'
s = s.replace(old, new)

# ---- 4. showEvent 延迟自适应 ----
old = ("            # 主营/公告要联网，所以只在真的切到本页时才补（程序没打开本页就不联网）\n"
       "            QTimer.singleShot(300, self._ensure_extras)\n")
new = ("            # 主营/公告要联网，所以只在真的切到本页时才补（程序没打开本页就不联网）\n"
       "            QTimer.singleShot(300, self._ensure_extras)\n"
       "            # 首帧布局完成后再校一次列宽（初始化时 viewport 还没尺寸）\n"
       "            QTimer.singleShot(120, self._autofit_columns)\n")
assert s.count(old) == 1, 'showEvent 锚点不唯一'
s = s.replace(old, new)

shutil.copy2(P, P + '.bak_before_colfit')
io.open(P, 'w', encoding='utf-8', newline='').write(s)
chk = io.open(P, encoding='utf-8', newline='').read()
print('原 %d 行 / 新 %d 行 ｜ CRLF=%d' % (orig.count('\n'), chk.count('\n'), chk.count('\r\n')))
print('落地自检：', all(k in chk for k in
                    ['_autofit_columns', 'PAGE_WIDTHS_MIN', 'PAGE_WIDTHS_MAX',
                     'QFontMetrics', '_THEME_MIN_W']))
