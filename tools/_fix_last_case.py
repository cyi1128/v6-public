# -*- coding: utf-8 -*-
"""修正 tools/_test_ctrl_dist.py 最后一个期望值（C3 后 pos=0.30 不在候选区 <0.25）。一次性，勿重跑。"""
import io

P = r'D:\QuantMonitorV6\tools\_test_ctrl_dist.py'
raw = io.open(P, 'rb').read()
crlf = b'\r\n' in raw
s = raw.decode('utf-8').replace('\r\n', '\n')
old = " (90.0,'wash',0.30, '高度控盘候选'),   # 2026-10-11 wash 文案关闭"
new = " (90.0,'wash',0.30, ''),   # 2026-10-11 wash 文案关闭（C3 后 pos 0.30 也进不了候选区）"
print('命中 %d 次' % s.count(old))
s = s.replace(old, new)
io.open(P, 'wb').write((s.replace('\n', '\r\n') if crlf else s).encode('utf-8'))

Q = r'D:\QuantMonitorV6\tools\_fix_stale_ctrl_dist.py'
q = io.open(Q, 'r', encoding='utf-8').read()
q = q.replace('同步 tools\\_test_ctrl_dist.py', '同步 tools/_test_ctrl_dist.py')
io.open(Q, 'w', encoding='utf-8', newline='\n').write(q)
print('OK')
