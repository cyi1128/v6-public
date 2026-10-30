# -*- coding: utf-8 -*-
"""临时：新浪国际指数/中概股代码实测"""
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
codes = 'int_nasdaq,int_dow,int_sp500,int_n225,int_hangseng,int_dax,int_fchi,int_ukx'
try:
    u = 'https://hq.sinajs.cn/list=' + codes
    txt = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read().decode('gbk', 'ignore')
    for ln in txt.splitlines():
        ln = ln.strip()
        if '=' not in ln:
            continue
        key = ln.split('=')[0].strip().split('_')[-1]
        body = ln.split('"')[1]
        f = body.split(',')
        if len(f) > 2 and f[0]:
            print(key, f[0], 'price', f[1], 'pct%', f[2])
        else:
            print(key, 'EMPTY')
except Exception as e:
    print('int fail', e)

# 中概美股
try:
    u = 'https://hq.sinajs.cn/list=gb_baba,gb_pdd,gb_nio,gb_xpeng'
    txt = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8).read().decode('gbk', 'ignore')
    for ln in txt.splitlines():
        ln = ln.strip()
        if '=' not in ln:
            continue
        key = ln.split('=')[0].strip().split('_')[-1]
        body = ln.split('"')[1]
        f = body.split(',')
        if len(f) > 3 and f[1]:
            print(key, f[0], 'price', f[1], 'pct%', f[2])
        else:
            print(key, 'EMPTY', body[:30])
except Exception as e:
    print('gb fail', e)
