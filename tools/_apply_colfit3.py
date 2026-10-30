# -*- coding: utf-8 -*-
"""一次性补丁 3：列宽量字从「采样 400 行」改为「全量量字」。执行一次即失效，勿重跑。

上一版采样 400 行（step=8），结果漏掉了没抽到的那些最长格（实测全量 3294 行 × 13 列
只剩 5 格差 1~3px 被截断）。改为全量量字；只有行数超过 _FIT_MAX_ROWS 才退化为采样。
"""
import io
import os
import shutil

ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
P = os.path.join('ui', 'battle_widgets', 'control_screen_widget.py')
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '本文件应为纯 LF，停止'

old = ("_FIT_SAMPLE = 400       # 逐格量字的采样行数上限（3300 行全量太慢，均匀采样够代表最长文本）\n")
new = ("_FIT_MAX_ROWS = 6000    # 行数 ≤ 这个值就**全量逐格量字**（3294 行实测 ~0.15s，保证不漏最长格）；\n"
       "                        # 超过才退化为采样（防止将来列表上万行时卡 UI）\n"
       "_FIT_SAMPLE = 400       # 退化采样时的采样行数\n")
assert s.count(old) == 1, '常量锚点不唯一'
s = s.replace(old, new)

old = "            step = max(1, n // _FIT_SAMPLE)\n"
new = "            step = 1 if n <= _FIT_MAX_ROWS else max(1, n // _FIT_SAMPLE)\n"
assert s.count(old) == 1, 'step 锚点不唯一'
s = s.replace(old, new)

old = "        · 行数多，均匀采样 _FIT_SAMPLE 行取最长文本（3294 行全量 4 万次量字没必要）；\n"
new = "        · 行数 ≤ _FIT_MAX_ROWS 时**全量量字**（采样会漏掉没抽到的最长格，实测差 1~3px）；\n"
assert s.count(old) == 1, 'docstring 锚点不唯一'
s = s.replace(old, new)

shutil.copy2(P, P + '.bak_before_colfit3')
io.open(P, 'w', encoding='utf-8', newline='').write(s)
chk = io.open(P, encoding='utf-8', newline='').read()
print('新 %d 行 ｜ CRLF=%d ｜ 替换 ok=%s'
      % (chk.count('\n'), chk.count('\r\n'),
         all(k in chk for k in ['_FIT_MAX_ROWS = 6000',
                                'step = 1 if n <= _FIT_MAX_ROWS'])))
