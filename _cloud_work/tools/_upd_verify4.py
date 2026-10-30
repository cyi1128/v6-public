# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_v2_board.py'
s = io.open(P, encoding='utf-8').read()
old = "check('8 次用尽 → ask 返回 '' 且置 exhausted', (cdr.ask_deepseek({'x': 1}, purpose='board') == '') and cdr._DS_EXHAUSTED)"
new = "check('DS 预算已停用：无 MODELSCOPE_KEY → ask 返回 '' 且不置 exhausted', (cdr.ask_deepseek({'x': 1}, purpose='board') == '') and not cdr._DS_EXHAUSTED)"
assert old in s, 'anchor not found'
s = s.replace(old, new)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('updated')
