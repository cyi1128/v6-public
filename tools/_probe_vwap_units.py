# -*- coding: utf-8 -*-
"""探针：核实 amount / volume 口径能否算出真实日内 VWAP（必须落在当日 low~high 之间）。"""
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')
from utils.http_market_data import get_realtime_quotes_http          # noqa: E402

CODES = ['600519', '300750', '000001', '601318', '002594']
q = get_realtime_quotes_http(CODES) or {}
print('拿到 %d 只' % len(q))
print('%-8s %-9s %-9s %-9s %-9s %-14s %-12s %-8s' % ('code', 'price', 'low', 'high', 'prev', 'amount(元)', 'volume(手)', 'vwap'))
for c in CODES:
    d = q.get(c)
    if not d:
        print('%-8s 无数据' % c)
        continue
    price = d.get('price', 0) or 0
    low = d.get('low', 0) or 0
    high = d.get('high', 0) or 0
    amt = d.get('amount', 0) or 0
    vol_lots = d.get('volume', 0) or 0
    vwap = amt / (vol_lots * 100.0) if vol_lots > 0 else 0
    ok = (low * 0.995 <= vwap <= high * 1.005) if (vwap > 0 and low > 0 and high > 0) else False
    print('%-8s %-9.2f %-9.2f %-9.2f %-9.2f %-14.0f %-12.0f %-8.3f  %s' % (
        c, price, low, high, d.get('last_close', 0) or 0, amt, vol_lots, vwap,
        'OK(在当日区间内)' if ok else '!! 不合理'))
    print('         vol_ratio=%.2f turnover=%.2f%%' % (d.get('vol_ratio', 0) or 0, d.get('turnover', 0) or 0))
