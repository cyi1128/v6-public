# -*- coding: utf-8 -*-
"""探一下同花顺涨停池到底给了哪些字段（决定封单额/炸板能不能补回来）。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

URL = ('https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool?'
       'page=1&limit=200&field=199112,10,9001,330323,330324,330325,9002,330329,'
       '133,330326,330327,330328,1968584,3475914,3541450&filter=HS,GEM2STAR&'
       'order_field=330324&order_type=0&date=20261009')
REQ = urllib.request.Request(URL, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://data.10jqka.com.cn/market/longhu/'})

try:
    with urllib.request.urlopen(REQ, timeout=15) as r:
        j = json.loads(r.read().decode('utf-8', 'ignore'))
except Exception as e:
    print('请求失败: %s' % e)
    sys.exit(1)

info = (j.get('data') or {}).get('info') or []
print('返回 %d 条' % len(info))
if not info:
    print('空')
    sys.exit(0)

print()
print('=== 第一条的全部字段 ===')
for k, v in info[0].items():
    print('  %-26s = %r' % (k, v))

print()
print('=== 可疑字段：封单/炸板/换手/流通市值/成交额 ===')
keys = set()
for r in info:
    keys |= set(r.keys())
sus = [k for k in sorted(keys)
       if any(w in k.lower() for w in ('amount', 'fund', 'order', 'zbc',
                                       'hs', 'turn', 'ltsz', 'mkt', 'money'))]
for k in sus:
    vals = [r.get(k) for r in info[:5]]
    print('  %-26s 样例 %s' % (k, vals))

print()
print('=== 全部字段名 ===')
print('  ' + '  '.join(sorted(keys)))
