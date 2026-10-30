# -*- coding: utf-8 -*-
"""逐文件 diff 复核：把本次改动对着备份逐行打出来（只显示真实差异）。"""
import difflib
import os

PAIRS = [
    (r'ui\echarts_kline.py', r'ui\echarts_kline.py.bak_before_kline_code2'),
    (r'ui\kline_container.py', r'ui\kline_container.py.bak_before_kline_code'),
    (r'ui\battle_console_v2.py', r'ui\battle_console_v2.py.bak_before_kline_code'),
    (r'ui\stock_detail_v1.py', r'ui\stock_detail_v1.py.bak_before_kline_code'),
    (r'ui\professional_kline_dialog.py', r'ui\professional_kline_dialog.py.bak_before_kline_code'),
    (r'ui\pro_stock_pool.py', r'ui\pro_stock_pool.py.bak_before_kline_code'),
]
ROOT = r'D:\QuantMonitorV6'

total = 0
for new, old in PAIRS:
    pn, po = os.path.join(ROOT, new), os.path.join(ROOT, old)
    a = open(po, newline='', encoding='utf-8').read().replace('\r\n', '\n').split('\n')
    b = open(pn, newline='', encoding='utf-8').read().replace('\r\n', '\n').split('\n')
    d = list(difflib.unified_diff(a, b, fromfile=os.path.basename(old), tofile=os.path.basename(new),
                                  lineterm='', n=2))
    added = sum(1 for x in d if x.startswith('+') and not x.startswith('+++'))
    removed = sum(1 for x in d if x.startswith('-') and not x.startswith('---'))
    total += added + removed
    print('\n' + '=' * 96)
    print('%s  →  +%d 行 / -%d 行' % (new, added, removed))
    print('=' * 96)
    for line in d[2:]:
        print(line[:170])
print('\n改动行合计：%d' % total)
