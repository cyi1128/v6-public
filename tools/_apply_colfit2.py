# -*- coding: utf-8 -*-
"""一次性补丁 2：修正列宽上限口径。执行一次即失效，勿重跑。

上一版给 13 列都设了上限，结果「代码/现价/涨跌幅/位置/数据日」的上限比它们
自己的内容需要还小 → 被夹住反而截断。改为：
  · 只有三个长文本列（主营收入 / 观察 / 最新公告）设上限，防某一格异常长挤没别人；
  · 其余 9 列内容形态固定（6 位代码 / 价格 / 百分比 / 位置 / 日期），按实测需要给宽，不设上限。
"""
import io
import os
import shutil

ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
P = os.path.join('ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '本文件应为纯 LF，停止'

old = ("PAGE_WIDTHS_MAX = {C_NAME: 132, C_CODE: 80, C_PRICE: 86, C_PCT: 90, C_BIZ: 330,\n"
       "                   C_SCORE: 80, C_STAGE: 60, C_POS: 60, C_LABEL: 108,\n"
       "                   C_OBS: 330, C_ANN: 460, C_DATE: 100}\n")
new = ("# 只有这三列是「长文本列」：给一个上限，防止某一格异常长把别的列挤没。\n"
       "# 其余 9 列内容形态固定（6 位代码 / 价格 / 涨跌幅 / 控盘分 / 位置 / 日期 / 短标签），\n"
       "# 按实测需要给宽即可 —— 给它们设上限反而会把内容夹断（第一批就踩了这个坑）。\n"
       "PAGE_WIDTHS_MAX = {C_BIZ: 330, C_OBS: 330, C_ANN: 460}\n")
assert s.count(old) == 1, '上限常量锚点不唯一'
s = s.replace(old, new)

old = ("                need[c] = min(max(w + _WIDTH_PAD, PAGE_WIDTHS_MIN[c]),\n"
       "                              PAGE_WIDTHS_MAX[c])\n")
new = ("                _n = max(w + _WIDTH_PAD, PAGE_WIDTHS_MIN[c])\n"
       "                _cap = PAGE_WIDTHS_MAX.get(c)\n"
       "                need[c] = min(_n, _cap) if _cap else _n\n")
assert s.count(old) == 1, '夹取锚点不唯一'
s = s.replace(old, new)

old = "        · 列宽有上下限：短列不吃空间，长列给足，避免出现省略号；\n"
new = "        · 下限防列被压没；上限只加在三个长文本列上，避免被上限反夹断；\n"
assert s.count(old) == 1, 'docstring 锚点不唯一'
s = s.replace(old, new)

shutil.copy2(P, P + '.bak_before_colfit2')
io.open(P, 'w', encoding='utf-8', newline='').write(s)
chk = io.open(P, encoding='utf-8', newline='').read()
print('新 %d 行 ｜ CRLF=%d ｜ 三处替换 ok=%s'
      % (chk.count('\n'), chk.count('\r\n'),
         all(k in chk for k in ['PAGE_WIDTHS_MAX = {C_BIZ: 330',
                                '_cap = PAGE_WIDTHS_MAX.get(c)'])))
