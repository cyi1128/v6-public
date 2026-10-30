# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_watch_v2.py'
s = io.open(P, encoding='utf-8').read()
old = "'A级·强'"
new = "'强，等回踩再上'"
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('patched')
