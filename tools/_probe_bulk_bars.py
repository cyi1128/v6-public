# -*- coding: utf-8 -*-
"""批量读 K 线 + 名称来源 探查（一次性）。"""
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')

import duckdb   # noqa: E402

DB = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'


def bulk(limit=120):
    con = duckdb.connect(DB, read_only=True)
    try:
        t0 = time.perf_counter()
        rows = con.execute("""
            SELECT code, date, open, high, low, close, volume FROM (
                SELECT code, date, open, high, low, close, volume,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                FROM kline_cache
            ) WHERE rn <= ?
            ORDER BY code, date
        """, [limit]).fetchall()
        t1 = time.perf_counter()
        return rows, (t1 - t0)
    finally:
        con.close()


rows, dt = bulk(120)
print('批量取 %d 行，用时 %.2f 秒' % (len(rows), dt), flush=True)
codes = {}
for r in rows:
    codes.setdefault(str(r[0]), []).append(r)
print('覆盖代码 %d 只' % len(codes), flush=True)
k = next(iter(codes))
print('样例 %s 首行=%s 末行=%s' % (k, codes[k][0], codes[k][-1]), flush=True)

# 与逐只读对比同一只
from services.kline_cache_service import get_latest_kline   # noqa: E402
_one = get_latest_kline(k, count=120)
print('逐只读 %s: %d 根 ｜ 批量读: %d 根 ｜ 末根收盘 %s vs %s'
      % (k, len(_one), len(codes[k]), _one[-1]['close'], codes[k][-1][5]), flush=True)

# 名称来源
try:
    from utils.stock_name_manager import get_all_stock_names   # noqa: E402
    t0 = time.perf_counter()
    m = get_all_stock_names()
    print('get_all_stock_names: %d 条（%.2fs）样例=%s'
          % (len(m), time.perf_counter() - t0, list(m.items())[:3]), flush=True)
except Exception as e:
    print('get_all_stock_names 失败:', e, flush=True)
