# -*- coding: utf-8 -*-
"""探：巨潮 topSearch 解析 orgId + hisAnnouncement 查询，对 478 只「空公告」的覆盖率。"""
import io
import json
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402
import services.control_screen_service as SS   # noqa: E402

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
       'Referer': 'http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search',
       'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
       'Accept': 'application/json, text/javascript, */*; q=0.01',
       'X-Requested-With': 'XMLHttpRequest'}


def resolve_org(code):
    u = 'http://www.cninfo.com.cn/new/information/topSearch/query'
    r = requests.post(u, data={'keyWord': str(code), 'maxNum': '10'}, headers=HDR, timeout=8)
    if r.status_code != 200:
        return None, 'status=%s' % r.status_code
    try:
        arr = r.json()
    except Exception:
        return None, 'not-json(%s)' % r.text[:40].replace('\n', ' ')
    for it in (arr or []):
        if str(it.get('code')) == str(code) and it.get('orgId'):
            return str(it['orgId']), 'ok'
    return None, 'no-match(%s)' % str(arr)[:60]


def query_ann(code, org, count=5):
    market = 'szse' if code.startswith(('0', '3')) else 'sse'
    data = {'pageNum': '1', 'pageSize': str(count), 'column': market, 'tabName': 'fulltext',
            'plate': '', 'stock': '%s,%s' % (code, org), 'searchkey': '', 'secid': '',
            'category': '', 'trade': '', 'seDate': '', 'sortName': '', 'sortType': '',
            'isHLtitle': 'true'}
    r = requests.post('http://www.cninfo.com.cn/new/hisAnnouncement/query', data=data,
                      headers=HDR, timeout=10)
    if r.status_code != 200:
        return None, 'status=%s' % r.status_code
    try:
        j = r.json()
    except Exception:
        return None, 'not-json'
    arr = j.get('announcements') or []
    out = []
    for a in arr[:count]:
        ts = a.get('announcementTime') or 0
        d = time.strftime('%Y-%m-%d', time.localtime(ts / 1000.0)) if ts else ''
        out.append([d, str(a.get('announcementTitle') or ''), '', str(a.get('announcementType') or '')])
    return out, 'ok'


items = SS.load_extras()
empty = [c for c in items if not (items[c].get('ann') or [])]
print('空公告 %d 只，抽 20 只测：' % len(empty), flush=True)
ok_org = ok_ann = 0
for c in empty[:20]:
    org, st = resolve_org(c)
    time.sleep(0.15)
    if not org:
        print('   %s orgId失败: %s' % (c, st), flush=True)
        continue
    ok_org += 1
    lst, st2 = query_ann(c, org)
    time.sleep(0.15)
    if lst:
        ok_ann += 1
        print('   %s orgId=%s 公告%d条 %s ｜ %s'
              % (c, org, len(lst), lst[0][0], lst[0][1][:34]), flush=True)
    else:
        print('   %s orgId=%s 公告0条 (%s)' % (c, org, st2), flush=True)
print()
print('orgId 命中 %d/20 ｜ 有公告 %d/20' % (ok_org, ok_ann))
