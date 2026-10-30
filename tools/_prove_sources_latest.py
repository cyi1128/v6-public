# -*- coding: utf-8 -*-
"""逐个数据源测：盘中最后一根日K是哪天"""
import sys
sys.path.insert(0, r'D:\QuantMonitorV6')

from utils.kline_fetcher import (fetch_kline, fetch_kline_pytdx,
                                 fetch_kline_sina, fetch_kline_tencent)

CODE = '600675'
print('当前时间: 2026-09-24 盘中')
print('测试股票:', CODE)
print()
print('%-26s %-14s %s' % ('数据源', '最后一根日期', '是否含9/24'))
print('-' * 60)

srcs = [
    ('pytdx（降级链第1位·首选）', fetch_kline_pytdx),
    ('新浪（第2位）', fetch_kline_sina),
    ('腾讯（第3位）', fetch_kline_tencent),
]
for name, fn in srcs:
    try:
        b = fn(CODE, days=10)
        if b:
            last = b[-1]['date']
            has = '是' if any(x['date'] == '2026-09-24' for x in b) else '否'
            print('%-26s %-14s %s' % (name, last, has))
        else:
            print('%-26s %-14s %s' % (name, '(返回空)', '-'))
    except Exception as e:
        print('%-26s %-14s %s' % (name, 'ERR', type(e).__name__))

print('-' * 60)
b = fetch_kline(CODE, days=10)
print('%-26s %-14s %s' % ('fetch_kline（引擎实际调用）',
                          b[-1]['date'] if b else '(空)',
                          '是' if b and any(x['date'] == '2026-09-24' for x in b) else '否'))
print()
print('=== 引擎 _load_bars 的第一步：本地缓存 ===')
try:
    from services.kline_cache_service import get_latest_kline
    lb = get_latest_kline(CODE, count=5)
    print('  本地缓存返回:', [(x['date'], x['close']) for x in lb] if lb else '(空 —— 主程序占用锁)')
except Exception as e:
    print('  ERR', type(e).__name__, e)
