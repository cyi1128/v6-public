# -*- coding: utf-8 -*-
"""探查「主营收入 / 最新公告」两个数据源的可用性与成本（只读，不写任何库）。"""
import glob
import io
import json
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

print('=' * 70)
print('[1] 主营构成缓存 data/cache/main_business/')
fs = glob.glob(os.path.join(ROOT, 'data', 'cache', 'main_business', '*.json'))
print('   文件数=%d' % len(fs))
_today = time.strftime('%Y%m%d')
print('   今日(%s)文件数=%d' % (_today, len([f for f in fs if _today in os.path.basename(f)])))
if fs:
    _one = sorted(fs)[-1]
    d = json.load(io.open(_one, encoding='utf-8'))
    print('   样例 %s report_date=%s items=%d' % (os.path.basename(_one),
                                                 d.get('report_date'), len(d.get('items') or [])))

print('=' * 70)
print('[2] stock_identity_provider（公告需要 orgId）')
try:
    from data.stock_identity_provider import get_stock_identity_provider
    p = get_stock_identity_provider()
    src = io.open(os.path.join(ROOT, 'data', 'stock_identity_provider.py'), encoding='utf-8').read()
    print('   源码行数=%d' % src.count('\n'))
    for kw in ('def get_org_id', 'requests.', 'CACHE', 'json', 'sqlite', 'duckdb', 'http'):
        print('   含 %-12s : %s' % (kw, kw in src))
    for c in ('600203', '000779', '300854'):
        t0 = time.perf_counter()
        try:
            oid = p.get_org_id(c)
        except Exception as e:
            oid = 'ERR:%s' % e
        print('   %s orgId=%s  %.3fs' % (c, oid, time.perf_counter() - t0))
except Exception as e:
    print('   导入失败: %s' % e)

print('=' * 70)
print('[3] 公告 provider 单只成本（走网络，2 只）')
try:
    from data.announcement_provider import get_announcement_provider
    ap = get_announcement_provider()
    for c in ('600203', '000779'):
        t0 = time.perf_counter()
        got = ap.get_announcements(c, count=3)
        print('   %s 返回 %d 条  %.2fs' % (c, len(got), time.perf_counter() - t0))
        for a in got[:3]:
            print('        %s  %s' % (a['date'], a['title'][:40]))
except Exception as e:
    print('   失败: %s' % e)

print('=' * 70)
print('[4] 现有 UI 怎么展示主营 / 公告（找可复用写法）')
for f in ('ui/stock_detail_pro.py', 'services/stock_deep_analysis.py',
          'ui/watchlist_panel.py', 'services/news_matcher.py'):
    p = os.path.join(ROOT, f.replace('/', os.sep))
    if not os.path.isfile(p):
        print('   %-40s 不存在' % f)
        continue
    lines = io.open(p, encoding='utf-8').read().split('\n')
    hit = [(i + 1, l.strip()[:110]) for i, l in enumerate(lines)
           if ('main_business' in l or 'fetch_main_business' in l
               or 'announcement' in l.lower() or '公告' in l)]
    print('   %-40s 命中 %d 行' % (f, len(hit)))
    for i, l in hit[:6]:
        print('        L%-5d %s' % (i, l))

print('=' * 70)
print('[5] 有没有本地批量主营/公告库可用')
for pat in ('data/*.db', 'data/*.json', 'data/cache/*.db', 'data/cache/*.parquet',
            'data/cache/*.duckdb'):
    for p in glob.glob(os.path.join(ROOT, pat.replace('/', os.sep))):
        n = os.path.basename(p)
        if any(k in n.lower() for k in ('main', 'biz', 'announce', 'notice', 'financ',
                                        'fundamental', 'profile', 'info')):
            print('   %-46s %d 字节' % (n, os.path.getsize(p)))
