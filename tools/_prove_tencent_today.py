# -*- coding: utf-8 -*-
"""直接打腾讯日K原始接口，看盘中是否返回今天(9/24)这根未完成K线"""
import sys, json
sys.path.insert(0, r'D:\QuantMonitorV6')
import requests

for code in ['600675', '002099']:
    if code.startswith('6'):
        symbol = 'sh' + code
    else:
        symbol = 'sz' + code
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           "?param=%s,day,,,10,qfq" % symbol)
    try:
        r = requests.get(url, headers={'Referer': 'https://gu.qq.com/',
                                       'User-Agent': 'Mozilla/5.0'}, timeout=10)
        j = r.json()
        d = (j.get('data') or {}).get(symbol) or {}
        kl = d.get('qfqday') or d.get('day') or []
        print('=== %s (%s) 原始接口最后 6 根 ===' % (code, symbol))
        for line in kl[-6:]:
            print('   ', line[0], ' O=%s H=%s L=%s C=%s V=%s' % (line[1], line[3], line[4], line[2], line[5]))
        dates = [x[0] for x in kl]
        print('   最后一根日期:', dates[-1] if dates else '(无)')
        print('   是否含 2026-09-24:', '2026-09-24' in dates)
    except Exception as e:
        print(code, 'ERR', type(e).__name__, e)
    print()

print('=== fetch_kline_tencent 包装后返回 ===')
from utils.kline_fetcher import fetch_kline_tencent
b = fetch_kline_tencent('600675', days=10)
if b:
    print('   最后3根:', [(x['date'], x['close']) for x in b[-3:]])
    print('   最后一根日期:', b[-1]['date'])
else:
    print('   返回空')
