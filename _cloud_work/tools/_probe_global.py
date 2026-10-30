# -*- coding: utf-8 -*-
"""临时：实测腾讯国际行情代码"""
import urllib.request

codes = ['usIXIC', 'usDJI', 'usINX', 'usHSI', 'usN225', 'usUKX', 'usFCHI', 'usGDAXI',
         'hf_CL', 'hf_GC', 'hf_DINI', 'usDCNH', 'baba', 'pdd', 'nio']
q = ','.join(codes)
u = 'http://qt.gtimg.cn/q=' + q
req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
txt = urllib.request.urlopen(req, timeout=10).read().decode('gbk', 'ignore')
for ln in txt.split(';'):
    ln = ln.strip()
    if '=' not in ln:
        continue
    key = ln.split('=')[0].strip().split('_')[-1]
    body = ln.split('"')[1] if '"' in ln else ''
    if not body:
        print(key, 'EMPTY')
        continue
    if key.startswith('us') or key in ('baba', 'pdd', 'nio'):
        f = body.split('~')
        try:
            price = f[3] if len(f) > 3 else '?'
            prev = f[4] if len(f) > 4 else '?'
            pct = (float(price) / float(prev) - 1) * 100 if prev and prev not in ('0.00', '') else 0
            print(key, 'price', price, 'pct', round(pct, 2))
        except Exception:
            print(key, 'parse?', body[:60])
    else:
        print(key, 'hf', body[:50])
