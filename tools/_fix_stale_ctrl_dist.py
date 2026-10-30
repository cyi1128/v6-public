# -*- coding: utf-8 -*-
"""同步 tools/_test_ctrl_dist.py 里 4 个「C1/C2、C3/C5 改规则后一直没更新」的旧期望值。

已用本批改动前的引擎（.bak_before_washnote）证明：这 4 个用例在本次改动前就对不上，
不是本批引入的回归。一次性补丁，勿重跑。
"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\tools\_test_ctrl_dist.py'
raw = io.open(P, 'rb').read()
crlf = b'\r\n' in raw
s = raw.decode('utf-8').replace('\r\n', '\n')
shutil.copy2(P, P + '.bak_before_washnote')

pairs = [
    (" (59.9,'distribute',0.90, ''),",
     " (59.9,'distribute',0.90, '出货风险警示'),   # C1(2026-10-10) 出货改为位置主导 pos>=0.65，不再看分数", 1),
    (" (55.0,'distribute',0.90, ''),",
     " (55.0,'distribute',0.90, '出货风险警示'),   # 同上", 1),
    (" (95.0,'distribute',0.35, '出货风险警示 ｜ 高度控盘候选'),",
     " (95.0,'distribute',0.35, ''),   # pos 0.35 既不到出货 0.65，也不在候选区 <0.25", 1),
    (" (95.0,'unknown',0.35, '高度控盘候选'),",
     " (95.0,'unknown',0.35, ''),   # C3(2026-10-10) 候选位置门槛改为 <0.25", 1),
]
for old, new, exp in pairs:
    cnt = s.count(old)
    if cnt != exp:
        print('  !! 命中 %d 次（期望 %d）：%s' % (cnt, exp, old.strip()))
    s = s.replace(old, new)

out = s.replace('\n', '\r\n') if crlf else s
io.open(P, 'wb').write(out.encode('utf-8'))
chk = io.open(P, 'rb').read()
print('tools\\_test_ctrl_dist.py  CRLF=%d 裸LF=%d'
      % (chk.count(b'\r\n'), chk.count(b'\n') - chk.count(b'\r\n')))
