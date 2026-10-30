# -*- coding: utf-8 -*-
"""探查 2：orgId 覆盖率 + 公告正确性 + 主营取数成本（只读）。"""
import io
import json
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

print('[1] stock_identity.json 覆盖情况')
p = os.path.join(ROOT, 'data', 'cache', 'stock_identity.json')
d = json.load(io.open(p, encoding='utf-8'))
print('   条目=%d  mtime=%s' % (len(d), time.strftime('%Y-%m-%d %H:%M',
                                              time.localtime(os.path.getmtime(p)))))
from collections import Counter
pre = Counter()
for c, v in d.items():
    pre[str(c)[:3]] += 1
print('   代码前缀 Top10: %s' % pre.most_common(10))
print('   样例 300854 -> %s' % json.dumps(d.get('300854'), ensure_ascii=False))
print('   样例 000779 -> %s' % json.dumps(d.get('000779'), ensure_ascii=False))

print()
print('[2] 公告正确性抽查（含创业板）')
from data.announcement_provider import get_announcement_provider   # noqa: E402
ap = get_announcement_provider()
for c in ('300854', '300302', '603887', '002828', '601029'):
    t0 = time.perf_counter()
    got = ap.get_announcements(c, count=2)
    print('   %s  %d 条  %.2fs' % (c, len(got), time.perf_counter() - t0))
    for a in got[:2]:
        print('        %s  %s' % (a['date'], a['title'][:46]))

print()
print('[3] 主营构成取数成本（网络，5 只，含缓存命中）')
from utils.main_business_service import fetch_main_business_composition   # noqa: E402
for c in ('600203', '000779', '300854', '603887', '002828'):
    t0 = time.perf_counter()
    r = fetch_main_business_composition(c, timeout=8)
    dt = time.perf_counter() - t0
    top = (r.get('items') or [{}])[0]
    print('   %s  %.2fs  报告期=%s  items=%d  top1=%s %s %s'
          % (c, dt, r.get('report_date'), len(r.get('items') or []),
             top.get('name'), top.get('income_str'), top.get('ratio')))
