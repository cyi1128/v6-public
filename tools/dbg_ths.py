# -*- coding: utf-8 -*-
import json
import sys
import urllib.request

sys.path.insert(0, r"D:\QuantMonitorV6")

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')

variants = {
    'limit200 (测试里成功的)': (
        'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool?'
        'page=1&limit=200&field=199112,10,9001,330323,330324,330325,9002,330329,'
        '133971,133970,1968584,3475914,9003,9004&filter=HS,GEM2STAR&'
        'order_field=330324&order_type=0&date=20261009'),
    'limit300 (采集器用的)': (
        'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool?'
        'page=1&limit=300&field=199112,10,9001,330323,330324,330325,9002,330329,'
        '133971,133970,1968584,3475914,9003,9004&filter=HS,GEM2STAR&'
        'order_field=330324&order_type=0&date=20261009'),
}

for label, url in variants.items():
    print('=' * 74)
    print(label)
    print('=' * 74)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA,
            'Referer': 'https://data.10jqka.com.cn/market/longhu/',
            'Accept': '*/*'})
        raw = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
        print('  原始长度 %d' % len(raw))
        print('  前 260 字: %s' % raw[:260].replace('\n', ' '))
        j = json.loads(raw)
        print('  status_code=%s status_msg=%s' % (j.get('status_code'), j.get('status_msg')))
        d = j.get('data')
        print('  data 类型=%s' % type(d).__name__)
        if isinstance(d, dict):
            print('  data keys=%s' % sorted(d.keys()))
            info = d.get('info')
            print('  data.info 条数=%s' % (len(info) if info else 0))
            if info:
                print('  首条: %s' % json.dumps(info[0], ensure_ascii=False)[:400])
    except Exception as e:
        import traceback
        traceback.print_exc()
    print()
