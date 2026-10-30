# -*- coding: utf-8 -*-
"""定向备份：控盘选股「主营收入 + 最新公告」两列这一批（可重跑，会覆盖同名目录）。"""
import os
import shutil
import time

ROOT = r'D:\QuantMonitorV6'
dst = os.path.join(ROOT, 'backups',
                   'ctrlscreen_extras_20261011_%s' % time.strftime('%H%M'))
files = [
    'services/control_screen_service.py',
    'services/control_screen_service.py.bak_before_extras',
    'services/control_screen_service.py.bak_before_extras2',
    'services/control_screen_service.py.bak_before_extras3',
    'services/control_screen_service.py.bak_before_extras3b',
    'ui/battle_widgets/control_screen_widget.py',
    'ui/battle_widgets/control_screen_widget.py.bak_before_extras',
    'ui/battle_widgets/control_screen_widget.py.bak_before_extras3b',
    'ui/battle_widgets/control_screen_widget.py.bak_before_extras3c',
    'data/cache/ctrl_screen_extras.json',
    'AGENTS.md',
    'tools/_ctrl_screen_extra_unit.py', 'tools/_ctrl_screen_dbui.py',
    'tools/_refill_ctrl_screen_extras.py', 'tools/_fill_ctrl_screen_extras.py',
    'tools/_apply_ctrl_screen_extras_svc.py', 'tools/_apply_ctrl_screen_extras_svc2.py',
    'tools/_apply_ctrl_screen_extras_svc3.py', 'tools/_apply_ctrl_screen_extras_v3b.py',
    'tools/_apply_ctrl_screen_extras_v3c.py', 'tools/_apply_ctrl_screen_extras_wdg.py',
    'tools/ctrl_screen_extra_unit.txt', 'tools/ctrl_screen_dbui.txt',
    'tools/ctrl_screen_unit.txt', 'tools/_shot_ctrl_screen.png',
    'tools/_shot_ctrl_screen.py',
]
os.makedirs(dst, exist_ok=True)
n = tot = 0
for f in files:
    s = os.path.join(ROOT, f.replace('/', os.sep))
    if not os.path.isfile(s):
        print('  缺失: %s' % f)
        continue
    d = os.path.join(dst, os.path.basename(s))
    shutil.copy2(s, d)
    n += 1
    tot += os.path.getsize(d)
print('定向备份: %s' % dst)
print('文件 %d 个 / %.1f MB' % (n, tot / 1048576.0))
for f in sorted(os.listdir(dst)):
    print('   %-46s %9d' % (f, os.path.getsize(os.path.join(dst, f))))
