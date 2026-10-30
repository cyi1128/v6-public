# -*- coding: utf-8 -*-
"""复测：巨潮查询接口在「provider 原样请求头」下是否可用（对比 3 种头组合）。"""
import os
import sys
import time

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402
import services.control_screen_service as SS   # noqa: E402

CODE = '600338'
ORG = 'gssh0600338'
URL = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
DATA = {'pageNum': '1', 'pageSize': '5', 'column': 'sse', 'tabName': 'fulltext',
        'plate': '', 'stock': '%s,%s' % (CODE, ORG), 'searchkey': '', 'secid': '',
        'category': '', 'trade': '', 'seDate': '', 'sortName': '', 'sortType': '',
        'isHLtitle': 'true'}

H1 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'Referer': 'http://www.cninfo.com.cn/new/disclosure/stock?stockCode=%s&orgId=%s' % (CODE, ORG),
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}

H2 = dict(H1)
H2['X-Requested-With'] = 'XMLHttpRequest'
H2['Accept'] = 'application/json, text/javascript, */*; q=0.01'

print('=== 变体1：provider 原样头 ===')
r = requests.post(URL, data=DATA, headers=H1, timeout=10)
print('   status=%s len=%d  head=%s' % (r.status_code, len(r.text), r.text[:90].replace('\n', ' ')))

print('=== 变体2：原样头 + XHR/Accept ===')
r2 = requests.post(URL, data=DATA, headers=H2, timeout=10)
print('   status=%s len=%d  head=%s' % (r2.status_code, len(r2.text), r2.text[:90].replace('\n', ' ')))

print('=== 变体3：先访问首页拿 cookie，再用原样头 ===')
s = requests.Session()
s.headers.update(H1)
try:
    g = s.get('http://www.cninfo.com.cn/new/index', timeout=10)
    print('   首页 status=%s cookies=%s' % (g.status_code, list(s.cookies.keys())))
except Exception as e:
    print('   首页失败 %s' % str(e)[:60])
r3 = s.post(URL, data=DATA, timeout=10)
print('   status=%s len=%d  head=%s' % (r3.status_code, len(r3.text), r3.text[:90].replace('\n', ' ')))

print()
print('=== 变体4：换个已知能出的代码 000779（今天 provider 拿到过）===')
D4 = dict(DATA, stock='000779,gssz0000779', column='szse')
r4 = requests.post(URL, data=D4, headers=H1, timeout=10)
print('   status=%s len=%d  head=%s' % (r4.status_code, len(r4.text), r4.text[:120].replace('\n', ' ')))

print()
print('=== 变体5：东财公告接口是否已恢复 ===')
try:
    r5 = requests.get(SS.ANN_URL % (3, '000779'), headers=SS.ANN_HDR, timeout=8)
    print('   status=%s json=%s head=%s' % (r5.status_code, r5.text[:1] == '{',
                                            r5.text[:70].replace('\n', ' ')))
except Exception as e:
    print('   异常 %s' % str(e)[:80])
