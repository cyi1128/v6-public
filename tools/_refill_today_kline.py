# -*- coding: utf-8 -*-
"""盘中补齐当日K线到 kline_cache（可重跑）。
为什么需要：2026-10-12 实测 fetch_kline 的源顺序把「新浪（末根=上一交易日）」
排在「腾讯（末根=当天）」前面 → 盘中缓存永远拿不到当天 bar → 控盘选股数据日停在上一交易日。
取数已修（utils/kline_fetcher.py 新鲜度优先），本脚本把当天 bar 真正写进缓存。
"""
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import duckdb  # noqa: E402

DB = 'data/cache/kline_cache.duckdb'


def state(tag):
    c = duckdb.connect(DB, read_only=True)
    mx = c.execute('SELECT MAX(date) FROM kline_cache').fetchone()[0]
    n_max = c.execute('SELECT COUNT(*) FROM kline_cache WHERE date = ?', [str(mx)]).fetchone()[0]
    tot = c.execute('SELECT COUNT(*) FROM kline_cache').fetchone()[0]
    codes = c.execute('SELECT COUNT(DISTINCT code) FROM kline_cache').fetchone()[0]
    meta_mx = c.execute('SELECT MAX(last_date) FROM kline_cache_meta').fetchone()[0]
    c.close()
    print('[%s] 末根日期=%s (%d 只) | 总行=%d | 代码=%d | meta末根=%s'
          % (tag, mx, n_max, tot, codes, meta_mx), flush=True)
    return str(mx), n_max


t0 = time.time()
print('=' * 78)
state('补齐前')
print('=' * 78)

from services.kline_cache_service import incremental_update_kline  # noqa: E402

res = incremental_update_kline(codes=None, max_workers=4, verbose=True)
print('=' * 78)
print('更新结果: 总数=%d 有新数据=%d 无新数据=%d 失败=%d 新增K线=%d 用时%.1f分'
      % (res.get('total', 0), res.get('updated', 0), res.get('no_new_data', 0),
         res.get('failed', 0), res.get('new_kline_total', 0), (time.time() - t0) / 60), flush=True)
if res.get('failed_list'):
    print('失败样例:', res['failed_list'][:5], flush=True)
mx, n_max = state('补齐后')
print('=' * 78)
print('今日 bar 只数 = %d' % n_max if mx >= time.strftime('%Y-%m-%d') else
      '⚠ 末根仍是 %s，未取到当天 bar' % mx)
