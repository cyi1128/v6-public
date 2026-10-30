# -*- coding: utf-8 -*-
"""修正 AGENTS.md 里「控盘选股页」小节的字节数（一次性）。"""
import io
import os
import re

AG = r'D:\QuantMonitorV6\AGENTS.md'
s = io.open(AG, 'r', encoding='utf-8').read()
svc = os.path.getsize(r'D:\QuantMonitorV6\services\control_screen_service.py')
wdg = os.path.getsize(r'D:\QuantMonitorV6\ui\battle_widgets\control_screen_widget.py')

n1 = re.subn(r'（服务，\d+ 字节）', '（服务，%d 字节）' % svc, s)
n2 = re.subn(r'（页面，\d+ 字节）', '（页面，%d 字节）' % wdg, n1[0])
print('服务替换 %d 处 / 页面替换 %d 处' % (n1[1], n2[1]))
assert n1[1] == 1 and n2[1] == 1
io.open(AG, 'w', encoding='utf-8', newline='').write(n2[0])
raw = io.open(AG, 'rb').read()
print('AGENTS.md: 行数=%d CRLF=%d 字节=%d'
      % (n2[0].count('\n'), raw.count(b'\r\n'), len(raw)))
for ln in n2[0].split('\n'):
    if '新增文件' in ln:
        print(ln[:200])
