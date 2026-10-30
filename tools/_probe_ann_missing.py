# -*- coding: utf-8 -*-
"""查：为什么 40 只里 15 只拿不到公告（orgId 缺失？上游返回空？）。"""
import io
import json
import os
import sys

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

items = json.load(io.open(os.path.join(ROOT, 'data', 'cache', '_bench_extras.json'),
                          encoding='utf-8'))['items']
miss = [c for c, v in items.items() if not v.get('ann')]
hit = [c for c, v in items.items() if v.get('ann')]
print('无公告 %d 只: %s' % (len(miss), ','.join(sorted(miss))))
print('有公告 %d 只: %s' % (len(hit), ','.join(sorted(hit[:8]))))

from data.stock_identity_provider import get_stock_identity_provider   # noqa: E402
p = get_stock_identity_provider()
print()
print('%-8s %-12s %-20s %s' % ('code', '板性', 'orgId', '缓存里有身份吗'))
for c in sorted(miss)[:15]:
    oid = p.get_org_id(c)
    print('%-8s %-12s %-20s %s' % (c, c[:3], oid or '(空)', bool(p.has_identity(c))))
print()
print('对照（有公告）:')
for c in sorted(hit)[:5]:
    print('%-8s orgId=%s' % (c, p.get_org_id(c) or '(空)'))

# 直接手打 cninfo 看返回
print()
print('直接查 cninfo（无公告的 3 只 + 有公告的 1 只）:')
import requests   # noqa: E402
for c in (sorted(miss)[:3] + sorted(hit)[:1]):
    oid = p.get_org_id(c)
    if not oid:
        print('   %s orgId 空 → 上游查询直接跳过（provider 逻辑）' % c)
        continue
    mkt = 'szse' if c.startswith(('0', '3')) else 'sse'
    try:
        r = requests.post('http://www.cninfo.com.cn/new/hisAnnouncement/query',
                          data={'pageNum': '1', 'pageSize': '3', 'column': mkt,
                                'tabName': 'fulltext', 'plate': '', 'stock': '%s,%s' % (c, oid),
                                'searchkey': '', 'secid': '', 'category': '', 'trade': '',
                                'seDate': '', 'sortName': '', 'sortType': '', 'isHLtitle': 'true'},
                          headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'http://www.cninfo.com.cn/'},
                          timeout=15)
        j = r.json()
        al = j.get('announcements') or []
        print('   %s column=%s -> %d 条  totalAnnouncement=%s'
              % (c, mkt, len(al), j.get('totalAnnouncement')))
        for a in al[:2]:
            print('        %s' % a.get('announcementTitle', '')[:50])
    except Exception as e:
        print('   %s 请求失败 %s' % (c, e))
