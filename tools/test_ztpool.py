# -*- coding: utf-8 -*-
"""测试今日涨停池能否取到 -> 决定涨停库能不能补上今天的数据"""
import os
import sys
import time

sys.path.insert(0, r"D:\QuantMonitorV6")
os.chdir(r"D:\QuantMonitorV6")

print('=' * 72)
print('A) market/limit_up_center.get_today_limit_up_stocks()')
print('=' * 72)
try:
    from market.limit_up_center import get_today_limit_up_stocks
    t0 = time.time()
    s = get_today_limit_up_stocks()
    print('  返回 %s 条，耗时 %.2fs' % (len(s) if s else 0, time.time() - t0))
    if s:
        k0 = s[0]
        print('  首条字段: %s' % sorted(k0.keys()))
        for r in s[:5]:
            print('   %s %-8s 涨幅%s%% 连板%s 行业%s 首封%s 封单%s' % (
                r.get('code'), r.get('name'), r.get('pct_chg', r.get('pct', '?')),
                r.get('lbc'), r.get('industry', r.get('hybk', '?')),
                r.get('time', r.get('fbt', '?')), r.get('fund', '?')))
except Exception as e:
    import traceback
    traceback.print_exc()

print()
print('=' * 72)
print('B) 直接打东财涨停池原始接口')
print('=' * 72)
try:
    import json
    import urllib.request
    from utils.trade_calendar import get_latest_trading_date
    d = get_latest_trading_date()
    ds = d.strftime('%Y%m%d') if hasattr(d, 'strftime') else str(d).replace('-', '')
    url = ('http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
           '&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date=%s' % ds)
    print('  url date=%s' % ds)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'})
    raw = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
    j = json.loads(raw)
    pool = (j.get('data') or {}).get('pool') or []
    print('  返回 %d 只涨停' % len(pool))
    if pool:
        print('  原始字段: %s' % sorted(pool[0].keys()))
        for r in pool[:5]:
            print('   %s %-8s 连板%-2s 涨%s 换手%s 炸板%s 首封%s 行业%s' % (
                r.get('c'), r.get('n'), r.get('lbc'), r.get('zdp'),
                r.get('hs'), r.get('zbc'), r.get('fbt'), r.get('hybk')))
except Exception as e:
    import traceback
    traceback.print_exc()

print()
print('=' * 72)
print('C) 前一交易日对比（看接口是否可按日期回溯）')
print('=' * 72)
try:
    import json
    import urllib.request
    for ds in ['20260930', '20260929', '20261008']:
        url = ('http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
               '&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date=%s' % ds)
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'})
            j = json.loads(urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore'))
            pool = (j.get('data') or {}).get('pool') or []
            print('  %s -> %d 只' % (ds, len(pool)))
        except Exception as e:
            print('  %s -> 失败 %s' % (ds, str(e)[:60]))
except Exception as e:
    print('  失败', e)
