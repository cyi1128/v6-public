# -*- coding: utf-8 -*-
"""实测：178 只批量拉实时行情的耗时与成功率"""
import sys, time
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.band_pattern_engine import query_signals
sigs = query_signals() or []
show = [s for s in sigs if s.get('signal_level') in ('建仓触发', '等待确认')]
codes = [s['code'] for s in show]
print('待拉取股票数:', len(codes))

from utils.http_market_data import get_realtime_quotes_http
t0 = time.time()
q = get_realtime_quotes_http(codes) or {}
dt = time.time() - t0
print('耗时: %.2f 秒' % dt)
print('返回条数:', len(q))

ok = 0
zero = 0
miss = 0
for c in codes:
    v = q.get(c)
    if not v:
        miss += 1
    elif float(v.get('price') or 0) > 0:
        ok += 1
    else:
        zero += 1
print('拿到有效价: %d   价=0: %d   未返回: %d' % (ok, zero, miss))
print('覆盖率: %.1f%%' % (ok * 100.0 / len(codes)))

# 抽样看字段
print()
print('样例返回字段:')
for c in codes[:3]:
    print('  ', c, q.get(c))
