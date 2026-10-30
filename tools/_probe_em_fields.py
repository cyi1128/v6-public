# -*- coding: utf-8 -*-
"""探东财涨停池字段 —— 看封单额能不能从这边补。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

URL = ('http://push2ex.eastmoney.com/getTopicZTPool?'
       'ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&'
       'pagesize=200&sort=fbt:asc&date=20261009')
REQ = urllib.request.Request(URL, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'http://quote.eastmoney.com/'})
try:
    with urllib.request.urlopen(REQ, timeout=15) as r:
        j = json.loads(r.read().decode('utf-8', 'ignore'))
except Exception as e:
    print('请求失败: %s' % e)
    sys.exit(0)

pool = (j.get('data') or {}).get('pool') or []
print('返回 %d 条' % len(pool))
if not pool:
    print('空')
    sys.exit(0)

print()
print('=== 第一条全部字段 ===')
for k, v in sorted(pool[0].items()):
    print('  %-14s = %r' % (k, v))

print()
print('=== 每列在多少条里有值 ===')
keys = set()
for r in pool:
    keys |= set(r.keys())
for k in sorted(keys):
    n = sum(1 for r in pool if r.get(k) not in (None, '', 0))
    print('  %-14s 有值 %3d / %d' % (k, n, len(pool)))
