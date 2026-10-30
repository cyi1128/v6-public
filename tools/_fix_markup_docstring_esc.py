# -*- coding: utf-8 -*-
"""一次性：修掉 base.py docstring 里 tools\\markup_calib.txt 的无效转义警告（\\m）。"""
import io
p = r'D:\QuantMonitorV6\strategy\base.py'
s = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
bad = '依据 tools\\markup_calib.txt：整体命中的均值增量只有 +0.06pp（噪音）'
good = '依据 tools\\\\markup_calib.txt：整体命中的均值增量只有 +0.06pp（噪音）'
assert s.count(bad) == 1, s.count(bad)
io.open(p, 'wb').write(s.replace(bad, good).replace('\n', '\r\n').encode('utf-8'))
raw = io.open(p, 'rb').read()
print('已修：行数=%d CRLF=%d 裸LF=%d' % (raw.decode('utf-8').count('\n'), raw.count(b'\r\n'),
      raw.count(b'\n') - raw.count(b'\r\n')))
