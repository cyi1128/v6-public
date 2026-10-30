# -*- coding: utf-8 -*-
import io
p = r'D:\QuantMonitorV6\AGENTS.md'
s = io.open(p, encoding='utf-8').read()
bad = '`tools\\tools` 下 `_calib_markup.py`'
good = '`tools\\_calib_markup.py`'
print('命中', s.count(bad))
if s.count(bad) == 1:
    s = s.replace(bad, good)
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    print('已修正')
else:
    import re
    for m in re.finditer(r'[^\n]*tools[^\n]*calib[^\n]*', s):
        print('实际行:', m.group(0)[:120])
