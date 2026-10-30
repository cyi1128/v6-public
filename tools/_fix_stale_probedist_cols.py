# -*- coding: utf-8 -*-
"""一次性：同步 _probedist_unit.py 里写死的列数期望值（56 -> 59，1010l 加 markup 三列）。"""
import io
p = r'D:\QuantMonitorV6\tools\_probedist_unit.py'
s = io.open(p, encoding='utf-8', newline='').read()
old = "check('列数 = 56', len(E._ALL_COLS) == 56, '%d' % len(E._ALL_COLS))"
new = ("check('列数 = 59', len(E._ALL_COLS) == 59, '%d' % len(E._ALL_COLS))"
       "  # 1010i=56 -> 1010l 加 markup 三列 = 59")
assert s.count(old) == 1, s.count(old)
io.open(p, 'w', encoding='utf-8', newline='').write(s.replace(old, new))
print('已同步：56 -> 59')
