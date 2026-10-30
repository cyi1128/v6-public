# -*- coding: utf-8 -*-
"""实测东财公告接口：覆盖率 / 延迟 / 并发稳定性（对照巨潮）。"""
import json
import os
import sys
import time
import concurrent.futures as cf

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests   # noqa: E402

MISS = ['002716', '300042', '300062', '300254', '300373', '300433', '300561', '300655',
        '300663', '300766', '300786', '301345', '301596', '600539', '605255']
HIT = ['000779', '002828', '002969', '300854', '301029', '600203', '603887', '603950']
CODES = MISS + HIT
URL = ('http://np-anotice-stock.eastmoney.com/api/security/ann'
       '?sr=-1&page_size=5&page_index=1&ann_type=A&client_source=web&stock_list=%s')
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def fetch_em(code):
    t0 = time.perf_counter()
    try:
        r = requests.get(URL % code, headers=HDR, timeout=6)
        j = r.json()
        lst = ((j or {}).get('data') or {}).get('list') or []
        out = []
        for it in lst[:5]:
            d = str(it.get('notice_date') or '')[:10]
            out.append({'date': d, 'title': it.get('title', ''),
                        'art': it.get('art_code', '')})
        return code, out, round(time.perf_counter() - t0, 3), ''
    except Exception as e:
        return code, [], round(time.perf_counter() - t0, 3), str(e)[:60]


print('[1] 单线程 23 只（东财）')
ok = 0
for c in CODES:
    code, out, dt, err = fetch_em(c)
    flag = 'OK ' if out else '空 '
    if out:
        ok += 1
    print('   %s %s %-8s %5.2fs %2d条  %s' % (flag, '', c, dt, len(out),
                                              (out[0]['date'] + ' ' + out[0]['title'][:34]) if out else err))
print('   单线程命中 %d/%d' % (ok, len(CODES)))

print()
print('[2] 并发 6 线程（同 23 只）')
t0 = time.perf_counter()
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    res = list(ex.map(fetch_em, CODES))
el = time.perf_counter() - t0
hits = [r for r in res if r[1]]
print('   耗时 %.2fs ｜ 命中 %d/%d ｜ 单只均 %.3fs' % (el, len(hits), len(CODES), el / len(CODES)))
errs = [r for r in res if r[3]]
print('   报错 %d 只: %s' % (len(errs), [e[0] for e in errs][:8]))

print()
print('[3] 那 15 只「巨潮拿不到」的，东财能拿到吗')
_miss_got = {c: len([x for x in res if x[0] == c and x[1]][0][1]) for c in MISS}
print('   %s' % _miss_got)
print('   东财补上 %d/%d' % (sum(1 for v in _miss_got.values() if v > 0), len(MISS)))

print()
print('[4] 样例完整字段（000779）')
j = requests.get(URL % '000779', headers=HDR, timeout=6).json()
print('   顶层键: %s' % list(j.keys()))
print('   data.list[0] 键: %s' % list(j['data']['list'][0].keys()))
print('   %s' % json.dumps(j['data']['list'][0], ensure_ascii=False)[:400])
