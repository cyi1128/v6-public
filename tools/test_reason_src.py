# -*- coding: utf-8 -*-
"""测「涨停原因」能不能拿到 —— 决定新模块的题材口径"""
import json
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')


def get(url, ref, extra=None):
    h = {'User-Agent': UA, 'Referer': ref, 'Accept': '*/*'}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')


print('=' * 74)
print('1) 同花顺涨停池 limit_up_pool（带涨停原因 reason_type）')
print('=' * 74)
for date in ['20260930', '20261009']:
    url = ('https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool?'
           'page=1&limit=200&field=199112,10,9001,330323,330324,330325,9002,330329,'
           '133971,133970,1968584,3475914,9003,9004&filter=HS,GEM2STAR&'
           'order_field=330324&order_type=0&date=%s' % date)
    try:
        raw = get(url, 'https://data.10jqka.com.cn/market/longhu/')
        j = json.loads(raw)
        items = (j.get('data') or {}).get('info') or []
        print('  %s -> %d 只  status_code=%s' % (date, len(items), j.get('status_code')))
        if items:
            print('  字段: %s' % sorted(items[0].keys())[:20])
            for r in items[:6]:
                nm = (r.get('name') or r.get('stock_short') or '?')
                rt = r.get('reason_type') or r.get('reason') or '?'
                print('    %-8s 原因=%s' % (nm, str(rt)[:70]))
    except Exception as e:
        print('  %s -> 失败 %s: %s' % (date, type(e).__name__, str(e)[:80]))

print()
print('=' * 74)
print('2) 东财涨停池 hybk 是否够当板块用（今日 69 只的行业分布）')
print('=' * 74)
try:
    from collections import Counter
    url = ('http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
           '&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date=20261009')
    j = json.loads(get(url, 'http://quote.eastmoney.com/'))
    pool = (j.get('data') or {}).get('pool') or []
    cc = Counter(r.get('hybk', '?') for r in pool)
    print('  今日 %d 只涨停，分属 %d 个行业板块' % (len(pool), len(cc)))
    for k, v in cc.most_common(14):
        print('    %-12s %d 家' % (k, v))
except Exception as e:
    print('  失败:', e)
